# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer

"""
The whole point of this file is to create a SPI slave driver to interface with
the SPI master which is the AP on real hardware.
This is necessary for TPM operations where we can expose the route to TPM
within gscemulator while keeping the logic accurate.

All standards based on:
https://chromium.googlesource.com/chromiumos/platform/ec/+/refs/heads/cr50_stab/chip/g/spp_tpm.c
https://chromium.googlesource.com/chromiumos/platform/ec/+/refs/heads/cr50_stab/chip/g/spp.c
https://chromium.googlesource.com/chromiumos/platform/ec/+/refs/heads/cr50_stab/common/tpm_registers.c
https://chromium.googlesource.com/chromiumos/platform/depthcharge/+/refs/heads/main/src/drivers/tpm/google/spi.c
"""

import queue
import threading
import typing

import unicorn as qemu

from env import *
from lib.emulator_context import ComponentObjects, EmulatorContext
from lib.helpers import unhandled_register_exit
from lib.logger import GscemuLogger
from lib.pindevice import PinDevice, PinStatus

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)


class SPISlaveDevice:
    def __init__(self, ctx: EmulatorContext):
        self.ctx = ctx

        self.opthread = None
        self.opqueue = queue.Queue()

        # Internal components, mapped with the pinmux.
        self.pindevices: list[PinDevice] = [0] * 4
        # 0 = MOSI, 1 = CLK, 2 = MISO, 3 = CS_L
        self.pindevices[0] = PinDevice() # MOSI
        self.pindevices[1] = PinDevice() # CLK
        self.pindevices[2] = PinDevice() # MISO
        self.pindevices[3] = PinDevice() # CS_L

        # Used when slave has nothing to put on MISO on a clock pulse.
        self.tx_dummy_word = 0

        # SPI settings CTRL register
        self.ctrl = 0
        # Used to control if we should trigger the interrupt.
        self.ictrl = 0
        # Which interrupts are currently pending?
        self.istate = 0
        # RX/TX CTRL register
        self.fifo_ctrl = 0
        # How many bytes before interrupting?
        self.rxfifo_threshold = 0

    def sps_worker(self) -> None:
        while True:
            try:
                op = self.opqueue.get()
                target_fn, args = op

                target_fn(*args)

                self.opqueue.task_done()

                if self.fifo_ctrl & 0x1:
                    # Reset the TX FIFO, then deassert _RST.
                    self.fifo_ctrl &= ~0x1

                if self.fifo_ctrl & 0x8:
                    # Reset the RX FIFO, then deassert _RST.
                    self.fifo_ctrl &= ~0x8

            except Exception as e:
                prints.fatal(e)

    def start_worker(self) -> None:
        if not self.opthread:
            self.opthread = threading.Thread(target=self.sps_worker)
            self.opthread.daemon = True
            self.opthread.start()

    def queue_read_worker_op(self, size: int, target_fn) -> None:
        retqueue = queue.Queue()
        self.opqueue.put([target_fn, (size, retqueue)])
        self.opqueue.join()
        return retqueue.get_nowait()

    def queue_write_worker_op(self, size: int, value: int, target_fn) -> None:
        self.opqueue.put([target_fn, (size, value)])

    def read_ctrl(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.ctrl)

    def write_ctrl(self, size: int, value: int) -> None:
        self.ctrl = value

    def read_dummy_word(self, size: int, queue: queue.Queue) -> None:
        # I don't think we can read from DUMMY_WORD, it's unclear.
        queue.put(0)

    def write_dummy_word(self, size: int, value: int) -> None:
        self.tx_dummy_word = value

    def read_ictrl(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.ictrl)

    def write_ictrl(self, size: int, value: int) -> None:
        self.ictrl = value

    def read_istate(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.istate)

    def write_istate(self, size: int, value: int) -> None:
        # Only the system can assert or deassert ISTATE unless by ISTATE_CLR
        return

    def read_istate_clr(self, size: int, queue: queue.Queue) -> None:
        queue.put(0)

    def write_istate_clr(self, size: int, value: int) -> None:
        for bit in range(32):
            bs = 1 << bit
            if not value & bs:
                continue

            if not self.istate & bs:
                continue

            # Clear the bit in ISTATE
            self.istate &= ~bs

    def read_fifo_ctrl(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.fifo_ctrl)

    def write_fifo_ctrl(self, size: int, value: int) -> None:
        self.fifo_ctrl = value

    def read_rxfifo_threshold(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.rxfifo_threshold)

    def write_rxfifo_threshold(self, size: int, value: int) -> None:
        self.rxfifo_threshold = value


def init_SPISlaveDevice(ctx: EmulatorContext, regs: dict) -> ComponentObjects:
    c_emu = SPISlaveDevice(ctx)
    c_emu.start_worker()

    reg_fn_map = {
        regs["CTRL"]: [c_emu.read_ctrl, c_emu.write_ctrl],
        regs["DUMMY_WORD"]: [c_emu.read_dummy_word, c_emu.write_dummy_word],
        regs["ICTRL"]: [c_emu.read_ictrl, c_emu.write_ictrl],
        regs["ISTATE"]: [c_emu.read_istate, c_emu.write_istate],
        regs["ISTATE_CLR"]: [c_emu.read_istate_clr, c_emu.write_istate_clr],
        regs["FIFO_CTRL"]: [c_emu.read_fifo_ctrl, c_emu.write_fifo_ctrl],
        regs["RXFIFO_THRESHOLD"]: [
            c_emu.read_rxfifo_threshold,
            c_emu.write_rxfifo_threshold,
        ],
    }

    def component_read_handler(
        uc: qemu.Uc, offset: int, size: int, user_data: typing.Any
    ) -> int | None:
        try:
            return c_emu.queue_read_worker_op(size, reg_fn_map[offset][0])
        except KeyError:
            unhandled_register_exit(ctx, prints, "SPS0", offset)

    def component_write_handler(
        uc: qemu.Uc, offset: int, size: int, value: int, user_data: typing.Any
    ) -> None:
        try:
            c_emu.queue_write_worker_op(size, value, reg_fn_map[offset][1])
        except KeyError:
            unhandled_register_exit(ctx, prints, "SPS0", offset)

    return ComponentObjects(
        c_emu, component_read_handler, component_write_handler
    )
