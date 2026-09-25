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

from .m3 import pend_external_irq, unpend_external_irq

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

SPS_FIFO_SIZE = 0x400
SPS_FIFO_MASK = SPS_FIFO_SIZE - 1
SPS_FIFO_PTR_MASK = (SPS_FIFO_MASK << 1) | 1

SPS_TX_FIFO_OFFSET = 0x1000
SPS_RX_FIFO_OFFSET = SPS_TX_FIFO_OFFSET + SPS_FIFO_SIZE
SPS_DATA_END = SPS_RX_FIFO_OFFSET + SPS_FIFO_SIZE

FIFO_CTRL_TXFIFO_RST = 1 << 0
FIFO_CTRL_TXFIFO_EN = 1 << 1
FIFO_CTRL_RXFIFO_RST = 1 << 3
FIFO_CTRL_RXFIFO_EN = 1 << 4
FIFO_CTRL_MASK = 0x3F

ISTATE_CS_ASSERT = 1 << 8
ISTATE_CS_DEASSERT = 1 << 9
ISTATE_RXFIFO_OVERFLOW = 1 << 10
ISTATE_TXFIFO_EMPTY = 1 << 11
ISTATE_TXFIFO_FULL = 1 << 12
ISTATE_TXFIFO_LVL = 1 << 13
ISTATE_RXFIFO_LVL = 1 << 14
ISTATE_LATCHED_MASK = (1 << 11) - 1
ISTATE_MASK = (1 << 15) - 1

SPS_IRQS = {
    ISTATE_CS_ASSERT: 129,
    ISTATE_CS_DEASSERT: 130,
    ISTATE_RXFIFO_OVERFLOW: 139,
    ISTATE_TXFIFO_EMPTY: 148,
    ISTATE_TXFIFO_FULL: 149,
    ISTATE_TXFIFO_LVL: 150,
    ISTATE_RXFIFO_LVL: 138,
}


class SPISlaveDevice:
    def __init__(self, ctx: EmulatorContext) -> None:
        self.ctx = ctx

        self.opthread = None
        self.opqueue = queue.Queue()

        self.pindevices: list[PinDevice] = [PinDevice() for _ in range(4)]

        self.ctrl = 0x1
        self.tx_dummy_word = 0xFF
        self.ictrl = 0
        # Which interrupts are currently pending?
        self.istate = 0
        # RX/TX CTRL register
        self.fifo_ctrl = 0
        # How many bytes before interrupting?
        self.txfifo_threshold = 0
        self.rxfifo_threshold = 0

        self.txfifo = bytearray(SPS_FIFO_SIZE)
        self.rxfifo = bytearray(SPS_FIFO_SIZE)
        self.txfifo_rptr = 0
        self.txfifo_wptr = 0
        self.rxfifo_rptr = 0
        self.rxfifo_wptr = 0

        self.chip_select_asserted = False

    def sps_worker(self) -> None:
        while True:
            target_fn, args = self.opqueue.get()
            try:
                target_fn(*args)
            except Exception as e:
                if args and isinstance(args[-1], queue.Queue):
                    args[-1].put(e)
                else:
                    prints.fatal(e)
            finally:
                self.opqueue.task_done()

    def start_worker(self) -> None:
        if not self.opthread:
            self.opthread = threading.Thread(target=self.sps_worker)
            self.opthread.daemon = True
            self.opthread.start()

    def _get_worker_result(self, retqueue: queue.Queue) -> typing.Any:
        result = retqueue.get_nowait()
        if isinstance(result, Exception):
            raise result
        return result

    def queue_read_worker_op(self, size: int, target_fn) -> int:
        retqueue = queue.Queue()
        self.opqueue.put([target_fn, (size, retqueue)])
        self.opqueue.join()
        return self._get_worker_result(retqueue)

    def queue_write_worker_op(self, size: int, value: int, target_fn) -> None:
        self.opqueue.put([target_fn, (size, value)])

    def queue_read_fifo_worker_op(self, offset: int, size: int) -> int:
        retqueue = queue.Queue()

        self.opqueue.put(
            [
                self.read_fifo_data, 
                (offset, size, retqueue)
            ]
        )
        self.opqueue.join()
    
        return self._get_worker_result(retqueue)

    def queue_write_fifo_worker_op(
        self, offset: int, size: int, value: int
    ) -> None:
        self.opqueue.put(
            [
                self.write_fifo_data, 
                (offset, size, value)
            ]
        )

    def queue_chip_select_worker_op(self, asserted: bool) -> None:
        retqueue = queue.Queue()
        self.opqueue.put([self._set_chip_select, (asserted, retqueue)])
        self.opqueue.join()
        self._get_worker_result(retqueue)

    def queue_transfer_byte_worker_op(self, value: int) -> int:
        retqueue = queue.Queue()
        self.opqueue.put([self._transfer_byte, (value, retqueue)])
        self.opqueue.join()
        return self._get_worker_result(retqueue)

    def _m3(self) -> typing.Any:
        fast_lookup = getattr(self.ctx, "c_fast", None)
        return getattr(fast_lookup, "m3", None)

    def _set_irq_pending(self, state_bit: int, pending: bool) -> None:
        m3 = self._m3()
        if m3 is None:
            return

        irq = SPS_IRQS[state_bit]
        if pending:
            pend_external_irq(m3, irq)
        else:
            unpend_external_irq(m3, irq)

    def _txfifo_size(self) -> int:
        return (self.txfifo_wptr - self.txfifo_rptr) & SPS_FIFO_PTR_MASK

    def _rxfifo_size(self) -> int:
        return (self.rxfifo_wptr - self.rxfifo_rptr) & SPS_FIFO_PTR_MASK

    def _fifo_level_state(self) -> int:
        tx_size = self._txfifo_size()
        rx_size = self._rxfifo_size()
        state = 0

        if self.fifo_ctrl & FIFO_CTRL_TXFIFO_EN:
            if tx_size == 0:
                state |= ISTATE_TXFIFO_EMPTY
            if tx_size >= SPS_FIFO_SIZE:
                state |= ISTATE_TXFIFO_FULL
            if tx_size <= self.txfifo_threshold:
                state |= ISTATE_TXFIFO_LVL
        if (
            self.fifo_ctrl & FIFO_CTRL_RXFIFO_EN
            and rx_size > self.rxfifo_threshold
        ):
            state |= ISTATE_RXFIFO_LVL

        return state

    def referesh_sps_interrupts(self) -> None:
        level_state = self._fifo_level_state()
        for state_bit in (
            ISTATE_TXFIFO_EMPTY,
            ISTATE_TXFIFO_FULL,
            ISTATE_TXFIFO_LVL,
            ISTATE_RXFIFO_LVL,
        ):
            pending = bool(level_state & self.ictrl & state_bit)
            self._set_irq_pending(state_bit, pending)

    def _raise_latched_interrupt(self, state_bit: int) -> None:
        self.istate |= state_bit
        if self.ictrl & state_bit:
            self._set_irq_pending(state_bit, True)

    def _sync_latched_interrupts(self) -> None:
        for state_bit in (
            ISTATE_CS_ASSERT,
            ISTATE_CS_DEASSERT,
            ISTATE_RXFIFO_OVERFLOW,
        ):
            pending = bool(self.istate & self.ictrl & state_bit)
            self._set_irq_pending(state_bit, pending)

    def set_sps_pinstate(self, pin: PinDevice, high: bool) -> None:
        if high:
            level = PinStatus.PULLUP
        else:
            level = PinStatus.PULLDOWN

        pin.set_pininfo(level, 10.0)

    def _set_chip_select(
        self, asserted: bool, retqueue: queue.Queue
    ) -> None:
        if asserted == self.chip_select_asserted:
            retqueue.put(None)
            return

        self.chip_select_asserted = asserted
        self.set_sps_pinstate(self.pindevices[3], not asserted)
        if asserted:
            self._raise_latched_interrupt(ISTATE_CS_ASSERT)
        else:
            self._raise_latched_interrupt(ISTATE_CS_DEASSERT)

        retqueue.put(None)

    def set_chip_select(self, asserted: bool) -> None:
        # deassert or assert the CS line
        self.queue_chip_select_worker_op(asserted)

    def _transfer_byte(self, value: int, retqueue: queue.Queue) -> None:
        if not self.chip_select_asserted:
            raise RuntimeError("SPS transfer attempted while CS_L is high")

        output = self.tx_dummy_word & 0xFF
        if (self.fifo_ctrl & FIFO_CTRL_TXFIFO_EN) and self._txfifo_size():
            output = self.txfifo[self.txfifo_rptr & SPS_FIFO_MASK]
            self.txfifo_rptr = (self.txfifo_rptr + 1) & SPS_FIFO_PTR_MASK

        if self.fifo_ctrl & FIFO_CTRL_RXFIFO_EN:
            if self._rxfifo_size() < SPS_FIFO_SIZE:
                self.rxfifo[self.rxfifo_wptr & SPS_FIFO_MASK] = value
                self.rxfifo_wptr = (self.rxfifo_wptr + 1) & SPS_FIFO_PTR_MASK
            else:
                self._raise_latched_interrupt(ISTATE_RXFIFO_OVERFLOW)

        # We need to set the SPS pinstate for the GSC to read through
        # PINMUX.
        self.set_sps_pinstate(self.pindevices[0], bool(value & 1))
        self.set_sps_pinstate(self.pindevices[2], bool(output & 1))
        self.referesh_sps_interrupts()
        retqueue.put(output)

    def transfer(self, data: bytes) -> bytes:
        # While CS is asserted, clock bytes through SPS
        output = bytearray()

        for value in data:
            output.append(self.queue_transfer_byte_worker_op(value))

        return bytes(output)

    def read_ctrl(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.ctrl)

    def write_ctrl(self, size: int, value: int) -> None:
        self.ctrl = value

    def read_dummy_word(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.tx_dummy_word)

    def write_dummy_word(self, size: int, value: int) -> None:
        self.tx_dummy_word = value

    def read_fifo_ctrl(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.fifo_ctrl)

    def write_fifo_ctrl(self, size: int, value: int) -> None:
        self.fifo_ctrl = value & FIFO_CTRL_MASK

        if self.fifo_ctrl & FIFO_CTRL_TXFIFO_RST:
            self.txfifo_rptr = 0
            self.txfifo_wptr = 0
            self.txfifo[:] = bytes(SPS_FIFO_SIZE)
            self.fifo_ctrl &= ~FIFO_CTRL_TXFIFO_RST

        if self.fifo_ctrl & FIFO_CTRL_RXFIFO_RST:
            self.rxfifo_rptr = 0
            self.rxfifo_wptr = 0
            self.rxfifo[:] = bytes(SPS_FIFO_SIZE)
            self.fifo_ctrl &= ~FIFO_CTRL_RXFIFO_RST

        self.referesh_sps_interrupts()

    def read_txfifo_size(self, size: int, queue: queue.Queue) -> None:
        queue.put(self._txfifo_size())

    def write_txfifo_size(self, size: int, value: int) -> None:
        return

    def read_txfifo_rptr(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.txfifo_rptr)

    def write_txfifo_rptr(self, size: int, value: int) -> None:
        return

    def read_txfifo_wptr(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.txfifo_wptr)

    def write_txfifo_wptr(self, size: int, value: int) -> None:
        self.txfifo_wptr = value & SPS_FIFO_PTR_MASK
        self.referesh_sps_interrupts()

    def read_txfifo_threshold(
        self, size: int, queue: queue.Queue
    ) -> None:
        queue.put(self.txfifo_threshold)

    def write_txfifo_threshold(self, size: int, value: int) -> None:
        self.txfifo_threshold = value & SPS_FIFO_MASK
        self.referesh_sps_interrupts()

    def read_rxfifo_size(self, size: int, queue: queue.Queue) -> None:
        queue.put(self._rxfifo_size())

    def write_rxfifo_size(self, size: int, value: int) -> None:
        return

    def read_rxfifo_rptr(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.rxfifo_rptr)

    def write_rxfifo_rptr(self, size: int, value: int) -> None:
        self.rxfifo_rptr = value & SPS_FIFO_PTR_MASK
        self.referesh_sps_interrupts()

    def read_rxfifo_wptr(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.rxfifo_wptr)

    def write_rxfifo_wptr(self, size: int, value: int) -> None:
        return

    def read_rxfifo_threshold(
        self, size: int, queue: queue.Queue
    ) -> None:
        queue.put(self.rxfifo_threshold)

    def write_rxfifo_threshold(self, size: int, value: int) -> None:
        self.rxfifo_threshold = value & SPS_FIFO_MASK
        self.referesh_sps_interrupts()

    def read_val(self, size: int, queue: queue.Queue) -> None:
        value = 0
        for bit, pin in enumerate((2, 0, 3, 1)):
            pdpu_read = self.pindevices[pin].read_pdpu()

            if pdpu_read == PinStatus.PULLUP:
                value |= 1 << bit

        queue.put(value)

    def write_val(self, size: int, value: int) -> None:
        return

    def read_istate(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.istate | self._fifo_level_state())

    def write_istate(self, size: int, value: int) -> None:
        # Only the system can assert or deassert ISTATE unless by ISTATE_CLR
        return

    def read_istate_clr(self, size: int, queue: queue.Queue) -> None:
        queue.put(0)

    def write_istate_clr(self, size: int, value: int) -> None:
        clear = value & ISTATE_LATCHED_MASK
        self.istate &= ~clear
        self._sync_latched_interrupts()

    def read_ictrl(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.ictrl)

    def write_ictrl(self, size: int, value: int) -> None:
        self.ictrl = value & ISTATE_MASK
        self._sync_latched_interrupts()
        self.referesh_sps_interrupts()

    def read_fifo_data(
        self, offset: int, size: int, queue: queue.Queue
    ) -> None:
        if SPS_TX_FIFO_OFFSET <= offset < SPS_RX_FIFO_OFFSET:
            fifo = self.txfifo
            index = offset - SPS_TX_FIFO_OFFSET
        else:
            fifo = self.rxfifo
            index = offset - SPS_RX_FIFO_OFFSET

        fifo_bytes_ret = fifo[index : index + size]
        queue.put(
            int.from_bytes(fifo_bytes_ret, "little")
        )

    def write_fifo_data(self, offset: int, size: int, value: int) -> None:
        if not SPS_TX_FIFO_OFFSET <= offset < SPS_RX_FIFO_OFFSET:
            return

        index = offset - SPS_TX_FIFO_OFFSET
        mask = (1 << (size * 8)) - 1
        self.txfifo[index : index + size] = (value & mask).to_bytes(
            size, "little"
        )


def init_SPISlaveDevice(ctx: EmulatorContext, regs: dict) -> ComponentObjects:
    c_emu = SPISlaveDevice(ctx)
    c_emu.start_worker()

    reg_fn_map = {
        regs["CTRL"]: [c_emu.read_ctrl, c_emu.write_ctrl],
        regs["DUMMY_WORD"]: [
            c_emu.read_dummy_word,
            c_emu.write_dummy_word,
        ],
        regs["FIFO_CTRL"]: [c_emu.read_fifo_ctrl, c_emu.write_fifo_ctrl],
        regs["TXFIFO_SIZE"]: [
            c_emu.read_txfifo_size,
            c_emu.write_txfifo_size,
        ],
        regs["TXFIFO_RPTR"]: [
            c_emu.read_txfifo_rptr,
            c_emu.write_txfifo_rptr,
        ],
        regs["TXFIFO_WPTR"]: [
            c_emu.read_txfifo_wptr,
            c_emu.write_txfifo_wptr,
        ],
        regs["TXFIFO_THRESHOLD"]: [
            c_emu.read_txfifo_threshold,
            c_emu.write_txfifo_threshold,
        ],
        regs["RXFIFO_SIZE"]: [
            c_emu.read_rxfifo_size,
            c_emu.write_rxfifo_size,
        ],
        regs["RXFIFO_RPTR"]: [
            c_emu.read_rxfifo_rptr,
            c_emu.write_rxfifo_rptr,
        ],
        regs["RXFIFO_WPTR"]: [
            c_emu.read_rxfifo_wptr,
            c_emu.write_rxfifo_wptr,
        ],
        regs["RXFIFO_THRESHOLD"]: [
            c_emu.read_rxfifo_threshold,
            c_emu.write_rxfifo_threshold,
        ],
        regs["VAL"]: [c_emu.read_val, c_emu.write_val],
        regs["ISTATE"]: [c_emu.read_istate, c_emu.write_istate],
        regs["ISTATE_CLR"]: [
            c_emu.read_istate_clr,
            c_emu.write_istate_clr,
        ],
        regs["ICTRL"]: [c_emu.read_ictrl, c_emu.write_ictrl],
    }

    def is_fifo_data_access(offset: int, size: int) -> bool:
        return (
            SPS_TX_FIFO_OFFSET <= offset
            and offset + size <= SPS_RX_FIFO_OFFSET
        ) or (
            SPS_RX_FIFO_OFFSET <= offset
            and offset + size <= SPS_DATA_END
        )

    def component_read_handler(
        uc: qemu.Uc, offset: int, size: int, user_data: typing.Any
    ) -> int | None:
        try:
            if is_fifo_data_access(offset, size):
                return c_emu.queue_read_fifo_worker_op(offset, size)
            return c_emu.queue_read_worker_op(size, reg_fn_map[offset][0])
        except KeyError:
            unhandled_register_exit(ctx, prints, "SPS0", offset)

    def component_write_handler(
        uc: qemu.Uc, offset: int, size: int, value: int, user_data: typing.Any
    ) -> None:
        try:
            if is_fifo_data_access(offset, size):
                c_emu.queue_write_fifo_worker_op(offset, size, value)
                return
            c_emu.queue_write_worker_op(size, value, reg_fn_map[offset][1])
        except KeyError:
            unhandled_register_exit(ctx, prints, "SPS0", offset)

    return ComponentObjects(
        c_emu, component_read_handler, component_write_handler
    )
