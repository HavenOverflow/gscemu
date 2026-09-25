# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer
"""
AI made this test to test the SPS driver. This allows for repeatable SPS
testing. I can't be bothered to write the host side code, it doesn't
really affect the emulator.
"""

import types
import typing
import unittest

from lib.pindevice import PinDevice, PinStatus
from src.haven.ap_emu import APEmulator
from src.haven.components.regdefs.registers import SPS_REGS
from src.haven.components.sps import (
    FIFO_CTRL_RXFIFO_EN,
    FIFO_CTRL_TXFIFO_EN,
    ISTATE_CS_ASSERT,
    ISTATE_CS_DEASSERT,
    ISTATE_RXFIFO_LVL,
    SPS_RX_FIFO_OFFSET,
    SPS_TX_FIFO_OFFSET,
    init_SPISlaveDevice,
)


class FakeInterruptController:
    def __init__(self) -> None:
        self.pending: set[int] = set()

    def pend_external_irq(self, irq: int) -> None:
        self.pending.add(irq)

    def unpend_external_irq(self, irq: int) -> None:
        self.pending.discard(irq)


def make_context() -> tuple[typing.Any, FakeInterruptController]:
    interrupt_controller = FakeInterruptController()
    m3 = types.SimpleNamespace(intr_op=interrupt_controller)
    context = types.SimpleNamespace(c_fast=types.SimpleNamespace(m3=m3))
    return context, interrupt_controller


class HavenSPSTest(unittest.TestCase):
    def setUp(self) -> None:
        self.context, self.interrupts = make_context()
        self.component = init_SPISlaveDevice(self.context, SPS_REGS)
        self.sps = self.component.object

    def read_register(self, name: str) -> int:
        return self.component.read_fn(None, SPS_REGS[name], 4, None)

    def write_register(self, name: str, value: int) -> None:
        self.component.write_fn(None, SPS_REGS[name], 4, value, None)

    def test_defaults_and_self_clearing_fifo_reset(self) -> None:
        self.assertEqual(self.read_register("CTRL"), 0x1)
        self.assertEqual(self.read_register("DUMMY_WORD"), 0xFF)
        self.assertEqual(self.read_register("ISTATE"), 0)

        self.write_register("FIFO_CTRL", 0x9)
        self.assertEqual(self.read_register("FIFO_CTRL"), 0)
        self.assertEqual(self.read_register("TXFIFO_RPTR"), 0)
        self.assertEqual(self.read_register("TXFIFO_WPTR"), 0)
        self.assertEqual(self.read_register("RXFIFO_RPTR"), 0)
        self.assertEqual(self.read_register("RXFIFO_WPTR"), 0)

    def test_full_duplex_fifo_transfer(self) -> None:
        self.component.write_fn(
            None, SPS_TX_FIFO_OFFSET, 4, 0x04030201, None
        )
        self.write_register("TXFIFO_WPTR", 4)
        self.write_register(
            "FIFO_CTRL", FIFO_CTRL_TXFIFO_EN | FIFO_CTRL_RXFIFO_EN
        )

        self.sps.set_chip_select(True)
        received = self.sps.transfer(b"abcd")
        self.sps.set_chip_select(False)

        self.assertEqual(received, b"\x01\x02\x03\x04")
        self.assertEqual(self.read_register("TXFIFO_RPTR"), 4)
        self.assertEqual(self.read_register("RXFIFO_WPTR"), 4)
        self.assertEqual(
            self.component.read_fn(None, SPS_RX_FIFO_OFFSET, 4, None),
            int.from_bytes(b"abcd", "little"),
        )

    def test_threshold_and_chip_select_interrupts(self) -> None:
        self.write_register("FIFO_CTRL", FIFO_CTRL_RXFIFO_EN)
        self.write_register("RXFIFO_THRESHOLD", 3)
        self.write_register(
            "ICTRL",
            ISTATE_CS_ASSERT | ISTATE_CS_DEASSERT | ISTATE_RXFIFO_LVL,
        )

        self.sps.set_chip_select(True)
        self.assertIn(129, self.interrupts.pending)

        self.sps.transfer(b"abcd")
        self.assertIn(138, self.interrupts.pending)

        self.sps.set_chip_select(False)
        self.assertIn(130, self.interrupts.pending)
        self.assertEqual(
            self.read_register("ISTATE")
            & (ISTATE_CS_ASSERT | ISTATE_CS_DEASSERT | ISTATE_RXFIFO_LVL),
            ISTATE_CS_ASSERT | ISTATE_CS_DEASSERT | ISTATE_RXFIFO_LVL,
        )

        self.write_register("RXFIFO_RPTR", 4)
        self.write_register(
            "ISTATE_CLR", ISTATE_CS_ASSERT | ISTATE_CS_DEASSERT
        )
        self.read_register("ISTATE")
        self.assertNotIn(129, self.interrupts.pending)
        self.assertNotIn(130, self.interrupts.pending)
        self.assertNotIn(138, self.interrupts.pending)


class HavenAPEmulatorTest(unittest.TestCase):
    def test_frame_buffer_and_tpm_reset(self) -> None:
        context, _ = make_context()
        component = init_SPISlaveDevice(context, SPS_REGS)
        pinmux: typing.Any = types.SimpleNamespace(
            diom=[PinDevice() for _ in range(5)],
            gpio0=[PinDevice() for _ in range(16)],
        )
        ap = APEmulator()
        ap.initialize_ap(component.object, pinmux)

        self.assertEqual(pinmux.diom[3].read_pdpu(), PinStatus.PULLUP)
        ap.set_tpm_reset(True)
        self.assertEqual(pinmux.diom[3].read_pdpu(), PinStatus.PULLDOWN)

        ap.write_data(b"abc")
        self.assertEqual(ap.read_data(), b"\xff\xff\xff")
        self.assertEqual(ap.read_data(), b"")


if __name__ == "__main__":
    unittest.main()
