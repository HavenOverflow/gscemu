# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer
"""CRYTPO bignum accelerator implementation."""

import queue
import threading
import time
import traceback
import typing

import unicorn as qemu
from ot_dsim import CryptoEngine

from env import *
from lib.emulator_context import ComponentObjects, EmulatorContext
from lib.helpers import (
    idx_regs_to_regmap,
    unhandled_register_exit,
    unhandled_register_io,
)
from lib.logger import GscemuLogger

from .m3 import pend_external_irq, unpend_external_irq
from .timels import component_start_timer_debug, component_stop_timer_debug

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)


class CryptoAccelerator:
    def __init__(self, ctx: EmulatorContext):
        self.ctx = ctx

        self.opthread = None
        self.opqueue = queue.Queue()

        self.crypto_emulator = CryptoEngine()
        self.control = 0
        self.rand_stall_ctl = 0
        self.host_cmd = 0

    def crypto_worker(self) -> None:
        while True:
            try:
                op = self.opqueue.get()
                target_fn, args = op

                target_fn(*args)

                if self.control:
                    self.control_process()

                if self.host_cmd:
                    # start_time = time.perf_counter()
                    if GSCEMULATOR_DISABLE_CRYPTO_ENGINE:
                        time.sleep(0.01)
                        pend_external_irq(self.ctx.c_fast.m3, 4)
                        self.host_cmd = 0
                        continue

                    self.crypto_emulator.set_pc(self.host_cmd)

                    self.host_cmd = 0  # Clear HOST_CMD

                    try:
                        self.crypto_emulator.run_emulator()
                    except Exception:
                        traceback.print_exc()
                        prints.warning("CRYPTO engine died :(")

                    pend_external_irq(self.ctx.c_fast.m3, 4)
                    # print(time.perf_counter() - start_time)

                self.opqueue.task_done()

            except Exception as e:
                prints.fatal(e)

    def start_worker(self) -> None:
        if not self.opthread:
            self.opthread = threading.Thread(target=self.crypto_worker)
            self.opthread.daemon = True
            self.opthread.start()

    def queue_read_worker_op(self, size: int, target_fn) -> int:
        retqueue = queue.Queue()
        self.opqueue.put([target_fn, (size, retqueue)])
        self.opqueue.join()
        return retqueue.get_nowait()

    def queue_write_worker_op(self, size: int, value: int, target_fn) -> None:
        self.opqueue.put([target_fn, (size, value)])

    def control_process(self) -> None:
        if self.control & 1:  # RESET
            self.clear_emulator_object()

        elif self.control & 2:  # BREAK
            # Undefined behavior, just pass
            pass

        elif self.control & 4:  # RESUME
            # Undefined behavior, just pass
            pass

        # At this point, the writes should have been processed.
        self.control = 0

    def clear_emulator_object(self) -> None:
        self.crypto_emulator.reset_emulator_state()

    def read_control(self, size: int, queue: queue.Queue) -> None:
        # Should be zero everytime this is read anyways.
        queue.put(self.control)

    def write_control(self, size: int, value: int) -> None:
        val = value & 7

        # Check if more than 1 bit set.
        if val & (val - 1):
            # More than 1 bit set, ignore the write and return.
            return

        self.control = val

    def read_wipe_secrets(self, size: int, queue: queue.Queue) -> None:
        unhandled_register_io(prints, "READ", "CRYPTO", "WIPE_SECRETS")
        queue.put(0)

    def write_wipe_secrets(self, size: int, value: int) -> None:
        if value:
            self.clear_emulator_object()

    def read_imem(self, size: int, queue: queue.Queue, index: int) -> None:
        queue.put(self.crypto_emulator.get_imem(index))

    def write_imem(self, size: int, value: int, index: int) -> None:
        # Clear emulator state on IMEM write if emulator state has been
        # created?
        self.crypto_emulator.set_imem(index, value)

    def read_dmem(self, size: int, queue: queue.Queue, index: int) -> None:
        queue.put(self.crypto_emulator.get_dmem(index))

    def write_dmem(self, size: int, value: int, index: int) -> None:
        self.crypto_emulator.set_dmem(index, value)

    def read_int_state(self, size: int, queue: queue.Queue) -> None:
        # Doesn't matter
        queue.put(0)

    def write_int_state(self, size: int, value: int) -> None:
        if value & 0x2:
            unpend_external_irq(self.ctx.c_fast.m3, 4)

    def read_int_enable(self, size: int, queue: queue.Queue) -> None:
        # Doesn't matter
        queue.put(0)

    def write_int_enable(self, size: int, value: int) -> None:
        # Doesn't matter
        return

    def read_rand_stall_ctl(self, size: int, queue: queue.Queue) -> None:
        # Doesn't matter
        queue.put(self.rand_stall_ctl)

    def write_rand_stall_ctl(self, size: int, value: int) -> None:
        # Doesn't matter
        self.rand_stall_ctl = value

    def read_host_cmd(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.host_cmd)

    def write_host_cmd(self, size: int, value: int) -> None:
        self.host_cmd = value - 0x08000000


def init_CryptoAccelerator(
    ctx: EmulatorContext, regs: dict
) -> ComponentObjects:
    c_emu = CryptoAccelerator(ctx)
    c_emu.start_worker()

    reg_fn_map = {
        regs["CONTROL"]: [c_emu.read_control, c_emu.write_control],
        regs["WIPE_SECRETS"]: [
            c_emu.read_wipe_secrets,
            c_emu.write_wipe_secrets,
        ],
        regs["INT_ENABLE"]: [c_emu.read_int_enable, c_emu.write_int_enable],
        regs["INT_STATE"]: [c_emu.read_int_state, c_emu.write_int_state],
        regs["RAND_STALL_CTL"]: [
            c_emu.read_rand_stall_ctl,
            c_emu.write_rand_stall_ctl,
        ],
        regs["HOST_CMD"]: [c_emu.read_host_cmd, c_emu.write_host_cmd],
    }

    idx_regs_to_regmap(
        reg_fn_map, regs["IMEM_DUMMY"], c_emu.read_imem, c_emu.write_imem
    )

    idx_regs_to_regmap(
        reg_fn_map, regs["DMEM_DUMMY"], c_emu.read_dmem, c_emu.write_dmem
    )

    def component_read_handler(
        uc_unused: qemu.Uc, offset: int, size: int, user_data: typing.Any
    ) -> int | None:
        try:
            return c_emu.queue_read_worker_op(size, reg_fn_map[offset][0])
        except KeyError:
            unhandled_register_exit(ctx, prints, "CRYPTO", offset)

    def component_write_handler(
        uc_unused: qemu.Uc,
        offset: int,
        size: int,
        value: int,
        user_data: typing.Any,
    ) -> None:
        try:
            c_emu.queue_write_worker_op(size, value, reg_fn_map[offset][1])
        except KeyError:
            unhandled_register_exit(ctx, prints, "CRYPTO", offset)

    return ComponentObjects(
        c_emu, component_read_handler, component_write_handler
    )
