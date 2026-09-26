# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer
"""Cr50 KEYMGR component

KEYMGR is used for 2 main purposes:
- AES/GCM operations
- SHA operations

For the SHA engine, it has been rewritten from the old gscemu v2 impl.
FOr the AES engine, it has fundamentally not changed from gscemu v2.
"""

import hashlib
import hmac
import queue
import struct
import threading
import typing

import unicorn as qemu
from Crypto.Cipher import AES as domeAES

from env import *
from lib.emulator_context import ComponentObjects, EmulatorContext
from lib.helpers import (
    args_lambda_gen,
    idx_regs_to_regmap,
    unhandled_register_exit,
    unhandled_register_io,
)
from lib.logger import GscemuLogger
from lib.threadutils import FifoLock

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)


class ShaEngine:
    def __init__(self, ctx):
        self.ctx = ctx

        self.opqueue = queue.Queue()
        self.opthread = None

        self.recieve_data = False  # Used for LIVESTREAM mode
        self.start_hash = False

        self.itop = 0
        self.trig = 0

        self.msglen_lo = 0
        self.msglen_hi = 0
        self.msglen_full = 0  # Combination of LO + HI.
        self.en = 0
        self.wr_en = 0

        self.use_hidden_key = 0

        self.input_fifo = bytearray()
        self.sts_h = [0] * 8
        self.key_w = [0] * 8

        self.use_cert = {
            "INDEX": 0,
            "ENABLE": 0,
            "CHECK_ONLY": 0,
        }
        self.rand_stall_ctl = {
            "STALL_EN": 0,
            "FREQ": 0,
        }
        self.cert_override_ptr = {
            "DIGEST": 0,
            "KEY": 0,
        }

    def sha_worker(self) -> None:
        while True:
            try:
                # Wait for the next operation to enter the queue
                target_fn, args = self.opqueue.get()

                target_fn(*args)  # Splat our arguments into the target_fn

                # For write operations, this doesn't do anything. For read
                # operations, we need to tell the handler that we have processed
                # the value, and execution can proceed.
                self.opqueue.task_done()

                # Now, the SHA engine needs to check if we need to proceed with
                # any operations.

                # Check if TRIG has a value. If so, we need to process that
                # operation.
                if self.trig:
                    self.trig_process()

                # If LIVESTREAM is not enabled, then check if oneshot has
                # started processing data. If so, then we check if the buffer
                # has reached the msglen.
                if not (self.en & 16):  # BIT(4)
                    if self.recieve_data:
                        self.oneshot_check()

                # Check if we should start hashing data now.
                if self.start_hash:
                    self.hash_data()

            except Exception as e:
                prints.fatal(e)

    def start_worker(self) -> None:
        if not self.opthread:
            self.opthread = threading.Thread(target=self.sha_worker)
            self.opthread.daemon = True
            self.opthread.start()

    def queue_read_worker_op(self, size: int, target_fn) -> int:
        retqueue = queue.Queue()
        self.opqueue.put([target_fn, (size, retqueue)])
        self.opqueue.join()
        return retqueue.get_nowait()

    def queue_write_worker_op(self, size: int, value: int, target_fn) -> None:
        self.opqueue.put([target_fn, (size, value)])

    def trig_process(self) -> None:
        if self.trig == 1:  # BIT(0)
            # If this is a USE_CERT operation, just ignore it and say
            # the op is done.
            if self.use_cert["ENABLE"]:
                # Use a debug instead of warning since this is intended.
                prints.debug("SHA_USE_CERT usage is not supported!")
                self.use_cert["ENABLE"] = 0
                self.itop = 1
            else:
                # Not a USE_CERT operation.
                # Enable recieving data for LIVESTREAM or oneshot.
                self.recieve_data = True

            self.trig &= ~1  # Clear the TRIG bit

        elif self.trig == 2:  # BIT(1)
            # Wipe all the values in the SHA engine.
            self.recieve_data = False
            self.itop = 0
            self.msglen_lo = 0
            self.msglen_hi = 0
            self.msglen_full = 0
            self.en = 0
            self.wr_en = 0
            self.input_fifo = bytearray()
            self.sts_h = [0] * 8

            self.use_cert["ENABLE"] = 0
            self.use_cert["INDEX"] = 0
            self.use_cert["CHECK_ONLY"] = 0

            self.trig &= ~2  # Clear the TRIG bit

        elif self.trig == 4:  # BIT(2)
            # Undocumented and unused TRIG value.
            self.trig &= ~4  # Clear the TRIG bit

        elif self.trig == 8:  # BIT(3)
            # This means the firmware has finished streaming the data to
            # hash. We should kick off the SHA engine. This is only
            # applicable in LIVESTREAM mode.

            if self.en & 16:  # BIT(4)
                self.recieve_data = False
                self.start_hash = True

            self.trig &= ~8  # Clear the TRIG bit

        else:
            prints.fatal("SHA_TRIG received an invalid value")

    def oneshot_check(self) -> None:
        if len(self.input_fifo) == self.msglen_full:
            prints.debug("SHA INPUT_FIFO fully populated in oneshot mode!")
            self.recieve_data = False
            self.start_hash = True

    def hash_data(self) -> None:
        prints.debug("SHA engine hashing kicked off!")
        prints.debug(f"SHA engine running with self.en=0x{self.en:x}")
        engine: hashlib._Hash | hmac.HMAC | None = None
        engine_settings = self.en & (2 | 32)  # BIT(1) | BIT(5)

        if engine_settings == 0:  # SHA256
            engine = hashlib.sha256(self.input_fifo)
        elif engine_settings == 2:  # SHA1
            engine = hashlib.sha1(self.input_fifo)
        elif engine_settings == 32:  # SHA256 + HMAC
            derived_hmac_key = bytearray()
            for i in self.key_w:
                derived_hmac_key.extend(struct.pack("<I", i))

            engine = hmac.new(derived_hmac_key, self.input_fifo, hashlib.sha256)
        else:
            prints.fatal("unsupported ShaEngine CFG_EN state")
            return # This is very bad.

        digest = engine.digest()
        for i in range(8):
            self.sts_h[i] = int.from_bytes(
                digest[i * 4 : (i + 1) * 4], "little"
            )

        if self.en & 65536:  # BIT(16)
            self.itop = 1

        self.start_hash = False
        self.input_fifo = bytearray()

    def read_cfg_msglen_lo(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.msglen_lo)

    def write_cfg_msglen_lo(self, size: int, value: int) -> None:
        if self.recieve_data:
            return

        self.msglen_lo = value
        self.msglen_full = (self.msglen_hi << 32) | self.msglen_lo

    def read_cfg_msglen_hi(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.msglen_hi)

    def write_cfg_msglen_hi(self, size: int, value: int) -> None:
        if self.recieve_data:
            return

        self.msglen_hi = value
        self.msglen_full = (self.msglen_hi << 32) | self.msglen_lo

    def read_cfg_en(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.en)

    def write_cfg_en(self, size: int, value: int) -> None:
        if self.recieve_data:
            return

        self.en = value

    def read_cfg_wr_en(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.wr_en)

    def write_cfg_wr_en(self, size: int, value: int) -> None:
        self.wr_en = value

    def read_trig(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.trig)

    def write_trig(self, size: int, value: int) -> None:
        self.trig = value

    def read_itop(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.itop)

    def write_itop(self, size: int, value: int) -> None:
        self.itop = value

    def read_use_hidden_key(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.use_hidden_key)

    def write_use_hidden_key(self, size: int, value: int) -> None:
        self.use_hidden_key = value

    def read_input_fifo(self, size: int, queue: queue.Queue) -> None:
        unhandled_register_io(prints, "READ", "KEYMGR0", "INPUT_FIFO")
        queue.put(0)

    def write_input_fifo(self, size: int, value: int) -> None:
        if not self.recieve_data:
            return

        if size == 1:
            self.input_fifo.append(value & 0xFF)
        elif size == 4:
            self.input_fifo.extend(struct.pack("<I", value))
        else:
            prints.warning(f"Unexpected write size={size}, ignoring val.")

    def read_sts_h(self, size: int, queue: queue.Queue, index: int) -> None:
        queue.put(self.sts_h[index])

    def write_sts_h(self, size: int, value: int, index: int) -> None:
        unhandled_register_io(prints, "WRITE", "KEYMGR0", f"STS_H_{index}")

    def read_key_w(self, size: int, queue: queue.Queue, index: int) -> None:
        queue.put(self.key_w[index])

    def write_key_w(self, size: int, value: int, index: int) -> None:
        self.key_w[index] = value

    def read_rand_stall_ctl(self, size: int, queue: queue.Queue) -> None:
        val = self.rand_stall_ctl["STALL_EN"] | (
            self.rand_stall_ctl["FREQ"] << 1
        )
        queue.put(val)

    def write_rand_stall_ctl(self, size: int, value: int) -> None:
        stall_en = value & 0x1
        stall_freq = (value & 0x6) >> 0x1

        if stall_en:
            # If STALL_EN, that means random nops enabled. Only accept
            # writes to STALL_EN
            self.rand_stall_ctl["STALL_EN"] = stall_en
        else:
            # STALL_EN not enabled, therefore allow writes to STALL_EN and FREQ
            self.rand_stall_ctl["STALL_EN"] = stall_en
            self.rand_stall_ctl["FREQ"] = stall_freq

    def read_cert_override(self, size: int, queue: queue.Queue) -> None:
        val = (
            self.cert_override_ptr["DIGEST"]
            | self.cert_override_ptr["KEY"] << 0x10
        )
        queue.put(val)

    def write_cert_override(self, size: int, value: int) -> None:
        self.cert_override_ptr["DIGEST"] = value & 0x3F
        self.cert_override_ptr["KEY"] = (value & 0x3F0000) >> 0x10

    def read_use_cert(self, size: int, queue: queue.Queue) -> None:
        val = (
            self.use_cert["INDEX"]
            | self.use_cert["ENABLE"] << 0x6
            | self.use_cert["CHECK_ONLY"] << 0x7
        )
        queue.put(val)

    def write_use_cert(self, size: int, value: int) -> None:
        self.use_cert["INDEX"] = value & 0x3F
        self.use_cert["ENABLE"] = (value & 0x40) >> 0x6
        self.use_cert["CHECK_ONLY"] = (value & 0x80) >> 0x7


class AesEngine:
    def __init__(self, ctx: EmulatorContext):
        self.ctx = ctx
        self.opqueue = queue.Queue()
        self.opthread = None

        self.aes_cipher = None

        self.ctrl = {
            "RESET": 0,
            "KEYSIZE": 0,  # 0 = AES-128, 1 = AES-192, 2 = AES-256
            "CIPHER_MODE": 0,  # 0 = ECB, 1 = CTR, 2 = CBC, 3 = GCM
            "ENC_MODE": 0,  # 0 = DECRYPT, 1 = ENCRYPT
            "CTR_BIG_ENDIAN": 0,  # 0 = LE, 1 = BE
            "ENABLE": 0,
        }

        self.key_start = 0
        self.aes_key = [0] * 8

        self.counter = [0] * 4
        self.counter_updated = False

        self.gcm_h = [0] * 4
        self.gcm_mac = [0] * 4
        self.gcm_hash_in = [0] * 4
        self.gcm_do_acc = 0

        self.rand_stall = 0
        self.use_hidden_key = 0

        self.wfifo = queue.Queue()
        self.rfifo = queue.Queue()
        self.rfifo_empty = True
        self.wfifo_empty = True

    def aes_worker(self) -> None:
        while True:
            try:
                # Wait for the next operation to enter the queue
                target_fn, args = self.opqueue.get()

                target_fn(*args)  # Splat our arguments into the target_fn

                # For write operations, this doesn't do anything. For read
                # operations, we need to tell the handler that we have processed
                # the value, and execution can proceed.
                self.opqueue.task_done()

                if self.ctrl["RESET"]:
                    self.aes_cipher = None
                    self.ctrl["ENABLE"] = 0
                    self.ctrl["KEYSIZE"] = 0
                    self.ctrl["CIPHER_MODE"] = 0
                    self.ctrl["ENC_MODE"] = 0
                    self.ctrl["CTR_BIG_ENDIAN"] = 0
                    self.aes_key = [0] * 8
                    self.key_start = 0
                    self.use_hidden_key = 0
                    self.counter = [0] * 4
                    self.gcm_h = [0] * 4
                    self.gcm_mac = [0] * 4
                    self.gcm_hash_in = [0] * 4
                    self.ctrl["RESET"] = 0

                    while not self.wfifo.empty():
                        self.wfifo.get_nowait()
                    while not self.rfifo.empty():
                        self.rfifo.get_nowait()
                    self.wfifo_empty = True
                    self.rfifo_empty = True
                    continue

                if self.gcm_do_acc:
                    self._galois_multiply()
                    self.gcm_do_acc = 0

                if self.key_start and self.ctrl["ENABLE"]:
                    # Reset the aes cipher mode on a new key_start.
                    self.aes_cipher = None
                    self.key_start = 0

                if (not self.ctrl["ENABLE"]) or self.ctrl["RESET"]:
                    continue

                if self.ctrl["CIPHER_MODE"] == 1:  # CTR
                    while self.wfifo.qsize() >= 4:
                        block_in = bytearray()
                        for _ in range(4):
                            block_in.extend(
                                struct.pack("<I", self.wfifo.get_nowait())
                            )

                        if self.wfifo.qsize() == 0:
                            self.wfifo_empty = True

                        counter_bytes = bytearray()
                        for i in range(4):
                            counter_bytes.extend(
                                struct.pack("<I", self.counter[i])
                            )

                        encrypted_counter = self._aes_block_encrypt(
                            counter_bytes
                        )

                        block_out = bytearray()
                        for i in range(16):
                            block_out.append(block_in[i] ^ encrypted_counter[i])

                        for i in range(4):
                            word = struct.unpack(
                                "<I", block_out[i * 4 : (i + 1) * 4]
                            )[0]
                            self.rfifo.put(word)
                        self.rfifo_empty = False

                        if self.ctrl["CTR_BIG_ENDIAN"]:
                            carry = 1
                            for i in range(3, -1, -1):
                                val = struct.unpack(
                                    ">I", struct.pack("<I", self.counter[i])
                                )[0]
                                val += carry
                                carry = 1 if val > 0xFFFFFFFF else 0
                                val &= 0xFFFFFFFF
                                self.counter[i] = struct.unpack(
                                    "<I", struct.pack(">I", val)
                                )[0]
                        else:
                            self.counter[3] = (self.counter[3] + 1) & 0xFFFFFFFF

                elif self.ctrl["CIPHER_MODE"] in [0, 2]:  # ECB or CBC
                    if self.aes_cipher is None or self.counter_updated:
                        key = self._get_key_bytes()

                        if self.ctrl["CIPHER_MODE"] == 0:  # ECB
                            self.aes_cipher = domeAES.new(
                                bytes(key), domeAES.MODE_ECB
                            )
                        else:  # CBC
                            iv = bytearray()
                            for i in range(4):
                                iv.extend(struct.pack("<I", self.counter[i]))
                            self.aes_cipher = domeAES.new(
                                bytes(key), domeAES.MODE_CBC, bytes(iv)
                            )

                        self.counter_updated = False

                    while self.wfifo.qsize() >= 4:
                        block = bytearray()
                        for _ in range(4):
                            block.extend(
                                struct.pack("<I", self.wfifo.get_nowait())
                            )

                        if self.wfifo.qsize() == 0:
                            self.wfifo_empty = True

                        if self.ctrl["ENC_MODE"] == 1:  # encrypt
                            result = self.aes_cipher.encrypt(bytes(block))
                        else:  # decrypt
                            result = self.aes_cipher.decrypt(bytes(block))

                        for i in range(4):
                            word = struct.unpack(
                                "<I", result[i * 4 : (i + 1) * 4]
                            )[0]
                            self.rfifo.put(word)
                        self.rfifo_empty = False

                if self.wfifo.qsize() == 0:
                    self.wfifo_empty = True

            except Exception as e:
                prints.fatal(e)

    def start_worker(self) -> None:
        if not self.opthread:
            self.opthread = threading.Thread(target=self.aes_worker)
            self.opthread.daemon = True
            self.opthread.start()

    def queue_read_worker_op(self, size: int, target_fn) -> int:
        retqueue = queue.Queue()
        self.opqueue.put([target_fn, (size, retqueue)])
        self.opqueue.join()
        return retqueue.get_nowait()

    def queue_write_worker_op(self, size: int, value: int, target_fn) -> None:
        self.opqueue.put([target_fn, (size, value)])

    def _galois_multiply(self) -> None:
        mac = bytearray()
        for i in range(4):
            mac.extend(struct.pack(">I", self.gcm_mac[i]))

        hash_in = bytearray()
        for i in range(4):
            hash_in.extend(struct.pack(">I", self.gcm_hash_in[i]))

        h = bytearray()
        for i in range(4):
            h.extend(struct.pack(">I", self.gcm_h[i]))

        for i in range(16):
            mac[i] ^= hash_in[i]

        result = bytearray(16)
        for i in range(128):
            if mac[i // 8] & (0x80 >> (i % 8)):
                for j in range(16):
                    result[j] ^= h[j]

            carry = 0
            for j in range(16):
                new_carry = h[j] & 1
                h[j] = (h[j] >> 1) | (carry << 7)
                carry = new_carry

            if carry:
                h[0] ^= 0xE1

        for i in range(4):
            self.gcm_mac[i] = struct.unpack(">I", result[i * 4 : (i + 1) * 4])[
                0
            ]

    def _get_key_bytes(self) -> bytes:
        key_words = {0: 4, 1: 6, 2: 8}[self.ctrl["KEYSIZE"]]
        if self.use_hidden_key & 0x400:  # ENABLE bit
            # The AES engine implements a HIDDEN_KEY mode, where it uses a
            # key within KEYMGR instead of the key in the KEY registers.
            # We need to return a special key, not just use a key in the KEY
            # register as other ops may clobber it, causing the app_cipher to
            # be invalidated. We shall just return an empty bytes array of the
            # requested keysize here.
            return bytes(key_words * 4)

        key = bytearray()
        for i in range(key_words):
            key.extend(struct.pack("<I", self.aes_key[i]))
        return bytes(key)

    def _aes_block_encrypt(self, block_bytes) -> bytes:
        key = self._get_key_bytes()
        cipher = domeAES.new(key, domeAES.MODE_ECB)
        return cipher.encrypt(bytes(block_bytes))

    def read_ctrl(self, size: int, queue: queue.Queue) -> None:
        val = (
            (self.ctrl["RESET"] << 0)
            | (self.ctrl["KEYSIZE"] << 1)
            | (self.ctrl["CIPHER_MODE"] << 3)
            | (self.ctrl["ENC_MODE"] << 5)
            | (self.ctrl["CTR_BIG_ENDIAN"] << 6)
            | (self.ctrl["ENABLE"] << 7)
        )
        queue.put(val)

    def write_ctrl(self, size: int, value: int) -> None:
        self.ctrl["RESET"] = (value >> 0) & 1
        self.ctrl["KEYSIZE"] = (value >> 1) & 0x3
        self.ctrl["CIPHER_MODE"] = (value >> 3) & 0x3
        self.ctrl["ENC_MODE"] = (value >> 5) & 1
        self.ctrl["CTR_BIG_ENDIAN"] = (value >> 6) & 1
        self.ctrl["ENABLE"] = (value >> 7) & 1

    def read_wfifo(self, size: int, queue: queue.Queue) -> None:
        queue.put(0)

    def write_wfifo(self, size: int, value: int) -> None:
        self.wfifo.put(value, block=False)
        self.wfifo_empty = False

    def read_rfifo(self, size: int, queue: queue.Queue) -> None:
        try:
            val = self.rfifo.get_nowait()
            if self.rfifo.qsize() == 0:
                self.rfifo_empty = True
        except Exception:
            val = 0

        queue.put(val)

    def write_rfifo(self, size: int, value: int) -> None:
        return

    def read_key(self, size: int, queue: queue.Queue, index: int) -> None:
        queue.put(self.aes_key[index])

    def write_key(self, size: int, value: int, index: int) -> None:
        self.aes_key[index] = value

    def read_ctr(self, size: int, queue: queue.Queue, index: int) -> None:
        queue.put(self.counter[index])

    def write_ctr(self, size: int, value: int, index: int) -> None:
        self.counter[index] = value
        self.counter_updated = True

    def read_key_start(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.key_start)

    def write_key_start(self, size: int, value: int) -> None:
        self.key_start = value & 1

    def read_rand_stall(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.rand_stall)

    def write_rand_stall(self, size: int, value: int) -> None:
        self.rand_stall = value

    def read_wfifo_level(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.wfifo.qsize())

    def write_wfifo_level(self, size: int, value: int) -> None:
        return

    def read_wfifo_full(self, size: int, queue: queue.Queue) -> None:
        if self.wfifo.qsize() >= 16:
            queue.put(1)
        else:
            queue.put(0)

    def write_wfifo_full(self, size: int, value: int) -> None:
        return

    def read_rfifo_level(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.rfifo.qsize())

    def write_rfifo_level(self, size: int, value: int) -> None:
        return

    def read_rfifo_empty(self, size: int, queue: queue.Queue) -> None:
        queue.put(int(self.rfifo_empty))

    def write_rfifo_empty(self, size: int, value: int) -> None:
        return

    def read_gcm_do_acc(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.gcm_do_acc)

    def write_gcm_do_acc(self, size: int, value: int) -> None:
        self.gcm_do_acc = value & 1

    def read_gcm_h(self, size: int, queue: queue.Queue, index: int) -> None:
        queue.put(self.gcm_h[index])

    def write_gcm_h(self, size: int, value: int, index: int) -> None:
        self.gcm_h[index] = value

    def read_gcm_mac(self, size: int, queue: queue.Queue, index: int) -> None:
        queue.put(self.gcm_mac[index])

    def write_gcm_mac(self, size: int, value: int, index: int) -> None:
        self.gcm_mac[index] = value

    def read_gcm_hash_in(
        self, size: int, queue: queue.Queue, index: int
    ) -> None:
        queue.put(self.gcm_hash_in[index])

    def write_gcm_hash_in(self, size: int, value: int, index: int) -> None:
        self.gcm_hash_in[index] = value

    def read_wipe_secrets(self, size: int, queue: queue.Queue) -> None:
        queue.put(0)

    def write_wipe_secrets(self, size: int, value: int) -> None:
        if value:
            self.ctrl["RESET"] = 1

    def read_use_hidden_key(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.use_hidden_key)

    def write_use_hidden_key(self, size: int, value: int) -> None:
        self.use_hidden_key = value


class KeymgrController:
    def __init__(self, ctx):
        self.ctx = ctx

        self.mutex = FifoLock()  # Only use this for KeyManager specific ops.
        self.shaengine = ShaEngine(ctx)
        self.aesengine = AesEngine(ctx)

        self.cert_revoke_ctrl = [0xA8028A82, 0xAAAAAAAA, 0xAAAA]

        self.fw_major_version = 0

        self.hkey_rwr = [0] * 8
        self.hkey_fwr = [0] * 8
        self.hkey_frr = [0] * 8
        self.hkey_err_flags = 0

        self.fwr_vld = 0
        self.rwr_vld = 0
        self.fwr_lock = 0
        self.rwr_lock = 0

        self.shaengine.start_worker()
        self.aesengine.start_worker()

    def read_hkey_rwr(self, size: int, index: int) -> int:
        with self.mutex:
            return self.hkey_rwr[index]

    def write_hkey_rwr(self, size: int, value: int, index: int) -> None:
        with self.mutex:
            self.hkey_rwr[index] = value

    def read_hkey_fwr(self, size: int, index: int) -> int:
        with self.mutex:
            return self.hkey_fwr[index]

    def write_hkey_fwr(self, size: int, value: int, index: int) -> None:
        with self.mutex:
            self.hkey_fwr[index] = value

    def read_hkey_frr(self, size: int, index: int) -> int:
        with self.mutex:
            return self.hkey_frr[index]

    def write_hkey_frr(self, size: int, value: int, index: int) -> None:
        with self.mutex:
            return

    def read_fw_major_version(self, size: int) -> int:
        with self.mutex:
            return self.fw_major_version

    def write_fw_major_version(self, size: int, value: int) -> None:
        with self.mutex:
            self.fw_major_version = value

    def read_hkey_err_flags(self, size: int) -> int:
        with self.mutex:
            return self.hkey_err_flags

    def write_hkey_err_flags(self, size: int, value: int) -> None:
        with self.mutex:
            self.hkey_err_flags = value

    def read_fwr_vld(self, size: int) -> int:
        with self.mutex:
            return self.fwr_vld

    def write_fwr_vld(self, size: int, value: int) -> None:
        with self.mutex:
            self.fwr_vld = value

    def read_rwr_vld(self, size: int) -> int:
        with self.mutex:
            return self.rwr_vld

    def write_rwr_vld(self, size: int, value: int) -> None:
        with self.mutex:
            self.rwr_vld = value

    def read_fwr_lock(self, size: int) -> int:
        with self.mutex:
            return self.fwr_lock

    def write_fwr_lock(self, size: int, value: int) -> None:
        with self.mutex:
            self.fwr_lock = value

    def read_rwr_lock(self, size: int) -> int:
        with self.mutex:
            return self.rwr_lock

    def write_rwr_lock(self, size: int, value: int) -> None:
        with self.mutex:
            self.rwr_lock = value

    def read_cert_revoke_ctrl(self, size: int, index: int) -> int:
        with self.mutex:
            return self.cert_revoke_ctrl[index]

    def write_cert_revoke_ctrl(self, size: int, value: int, index: int) -> None:
        # with self.mutex:

        # We should be able to write to this register, but we do not implement
        # that for now.
        pass


def init_KeymgrController(ctx: EmulatorContext, regs: dict) -> ComponentObjects:
    c_emu = KeymgrController(ctx)

    reg_fn_map = {
        regs["FWR_VLD"]: [c_emu.read_fwr_vld, c_emu.write_fwr_vld],
        regs["RWR_VLD"]: [c_emu.read_rwr_vld, c_emu.write_rwr_vld],
        regs["FWR_LOCK"]: [c_emu.read_fwr_lock, c_emu.write_fwr_lock],
        regs["RWR_LOCK"]: [c_emu.read_rwr_lock, c_emu.write_rwr_lock],
        regs["HKEY_ERR_FLAGS"]: [
            c_emu.read_hkey_err_flags,
            c_emu.write_hkey_err_flags,
        ],
        regs["FW_MAJOR_VERSION"]: [
            c_emu.read_fw_major_version,
            c_emu.write_fw_major_version,
        ],
    }

    shaengine_fn_map = {
        regs["SHA"]["CFG"]["MSGLEN_LO"]: [
            c_emu.shaengine.read_cfg_msglen_lo,
            c_emu.shaengine.write_cfg_msglen_lo,
        ],
        regs["SHA"]["CFG"]["MSGLEN_HI"]: [
            c_emu.shaengine.read_cfg_msglen_hi,
            c_emu.shaengine.write_cfg_msglen_hi,
        ],
        regs["SHA"]["CFG"]["EN"]: [
            c_emu.shaengine.read_cfg_en,
            c_emu.shaengine.write_cfg_en,
        ],
        regs["SHA"]["CFG"]["WR_EN"]: [
            c_emu.shaengine.read_cfg_wr_en,
            c_emu.shaengine.write_cfg_wr_en,
        ],
        regs["SHA"]["TRIG"]: [
            c_emu.shaengine.read_trig,
            c_emu.shaengine.write_trig,
        ],
        regs["SHA"]["INPUT_FIFO"]: [
            c_emu.shaengine.read_input_fifo,
            c_emu.shaengine.write_input_fifo,
        ],
        regs["SHA"]["ITOP"]: [
            c_emu.shaengine.read_itop,
            c_emu.shaengine.write_itop,
        ],
        regs["SHA"]["USE_CERT"]: [
            c_emu.shaengine.read_use_cert,
            c_emu.shaengine.write_use_cert,
        ],
        regs["SHA"]["CERT_OVERRIDE"]: [
            c_emu.shaengine.read_cert_override,
            c_emu.shaengine.write_cert_override,
        ],
        regs["SHA"]["RAND_STALL_CTL"]: [
            c_emu.shaengine.read_rand_stall_ctl,
            c_emu.shaengine.write_rand_stall_ctl,
        ],
        regs["SHA"]["USE_HIDDEN_KEY"]: [
            c_emu.shaengine.read_use_hidden_key,
            c_emu.shaengine.write_use_hidden_key,
        ],
    }

    idx_regs_to_regmap(
        reg_fn_map, regs["HKEY_RWR"], c_emu.read_hkey_rwr, c_emu.write_hkey_rwr
    )

    idx_regs_to_regmap(
        reg_fn_map, regs["HKEY_FWR"], c_emu.read_hkey_fwr, c_emu.write_hkey_fwr
    )

    idx_regs_to_regmap(
        reg_fn_map, regs["HKEY_FRR"], c_emu.read_hkey_frr, c_emu.write_hkey_frr
    )

    idx_regs_to_regmap(
        reg_fn_map,
        regs["CERT_REVOKE_CTRL"],
        c_emu.read_cert_revoke_ctrl,
        c_emu.write_cert_revoke_ctrl,
    )

    idx_regs_to_regmap(
        shaengine_fn_map,
        regs["SHA"]["STS_H"],
        c_emu.shaengine.read_sts_h,
        c_emu.shaengine.write_sts_h,
    )

    idx_regs_to_regmap(
        shaengine_fn_map,
        regs["SHA"]["KEY_W"],
        c_emu.shaengine.read_key_w,
        c_emu.shaengine.write_key_w,
    )

    for k, v in shaengine_fn_map.items():
        reg_fn_map[k] = [
            args_lambda_gen(c_emu.shaengine.queue_read_worker_op, v[0]),
            args_lambda_gen(c_emu.shaengine.queue_write_worker_op, v[1]),
        ]

    aesengine_fn_map = {
        regs["AES"]["CTRL"]: [
            c_emu.aesengine.read_ctrl,
            c_emu.aesengine.write_ctrl,
        ],
        regs["AES"]["WFIFO_DATA"]: [
            c_emu.aesengine.read_wfifo,
            c_emu.aesengine.write_wfifo,
        ],
        regs["AES"]["RFIFO_DATA"]: [
            c_emu.aesengine.read_rfifo,
            c_emu.aesengine.write_rfifo,
        ],
        regs["AES"]["KEY_START"]: [
            c_emu.aesengine.read_key_start,
            c_emu.aesengine.write_key_start,
        ],
        regs["AES"]["RAND_STALL_CTL"]: [
            c_emu.aesengine.read_rand_stall,
            c_emu.aesengine.write_rand_stall,
        ],
        regs["AES"]["WFIFO_LEVEL"]: [
            c_emu.aesengine.read_wfifo_level,
            c_emu.aesengine.write_wfifo_level,
        ],
        regs["AES"]["WFIFO_FULL"]: [
            c_emu.aesengine.read_wfifo_full,
            c_emu.aesengine.write_wfifo_full,
        ],
        regs["AES"]["RFIFO_LEVEL"]: [
            c_emu.aesengine.read_rfifo_level,
            c_emu.aesengine.write_rfifo_level,
        ],
        regs["AES"]["RFIFO_EMPTY"]: [
            c_emu.aesengine.read_rfifo_empty,
            c_emu.aesengine.write_rfifo_empty,
        ],
        regs["AES"]["GCM_DO_ACC"]: [
            c_emu.aesengine.read_gcm_do_acc,
            c_emu.aesengine.write_gcm_do_acc,
        ],
        regs["AES"]["WIPE_SECRETS"]: [
            c_emu.aesengine.read_wipe_secrets,
            c_emu.aesengine.write_wipe_secrets,
        ],
        regs["AES"]["USE_HIDDEN_KEY"]: [
            c_emu.aesengine.read_use_hidden_key,
            c_emu.aesengine.write_use_hidden_key,
        ],
    }

    idx_regs_to_regmap(
        aesengine_fn_map,
        regs["AES"]["KEY"],
        c_emu.aesengine.read_key,
        c_emu.aesengine.write_key,
    )

    idx_regs_to_regmap(
        aesengine_fn_map,
        regs["AES"]["CTR"],
        c_emu.aesengine.read_ctr,
        c_emu.aesengine.write_ctr,
    )

    idx_regs_to_regmap(
        aesengine_fn_map,
        regs["AES"]["GCM_H"],
        c_emu.aesengine.read_gcm_h,
        c_emu.aesengine.write_gcm_h,
    )

    idx_regs_to_regmap(
        aesengine_fn_map,
        regs["AES"]["GCM_MAC"],
        c_emu.aesengine.read_gcm_mac,
        c_emu.aesengine.write_gcm_mac,
    )

    idx_regs_to_regmap(
        aesengine_fn_map,
        regs["AES"]["GCM_HASH_IN"],
        c_emu.aesengine.read_gcm_hash_in,
        c_emu.aesengine.write_gcm_hash_in,
    )

    for k, v in aesengine_fn_map.items():
        reg_fn_map[k] = [
            args_lambda_gen(c_emu.aesengine.queue_read_worker_op, v[0]),
            args_lambda_gen(c_emu.aesengine.queue_write_worker_op, v[1]),
        ]

    def component_read_handler(
        uc: qemu.Uc, offset: int, size: int, user_data: typing.Any
    ) -> int | None:
        try:
            return reg_fn_map[offset][0](size)
        except KeyError:
            unhandled_register_exit(ctx, prints, "KEYMGR", offset)

    def component_write_handler(
        uc: qemu.Uc, offset: int, size: int, value: int, user_data: typing.Any
    ) -> None:
        try:
            reg_fn_map[offset][1](size, value)
        except KeyError:
            unhandled_register_exit(ctx, prints, "KEYMGR", offset)

    return ComponentObjects(
        c_emu, component_read_handler, component_write_handler
    )
