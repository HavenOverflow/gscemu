# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer
"""Cr50 PINMUX component

This is a very complicated component, as it requires a lot of integration
with other components, such as UART, SPS, GPIO etc.
"""

import queue
import threading
import typing

import unicorn as qemu

from env import *
from lib.emulator_context import ComponentObjects, EmulatorContext
from lib.helpers import idx_regs_to_regmap, unhandled_register_exit
from lib.logger import GscemuLogger
from lib.pindevice import PinDevice, PinStatus

from .regdefs.pinmux_registers import *

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)


class Cr50Pinmux:
    def __init__(self, ctx: EmulatorContext):
        self.ctx = ctx

        self.opthread = None
        self.opqueue = queue.Queue()

        self.internal_pd = PinDevice()
        self.internal_pu = PinDevice()
        self.internal_pd.set_pininfo(PinStatus.PULLDOWN, 50000.0)
        self.internal_pu.set_pininfo(PinStatus.PULLUP, 50000.0)

        self.dioa: list[PinDevice] = []
        for _ in range(15):
            self.dioa.append(PinDevice())

        self.diob: list[PinDevice] = []
        for _ in range(8):
            self.diob.append(PinDevice())

        self.diom: list[PinDevice] = []
        for _ in range(5):
            self.diom.append(PinDevice())

        self.vio: list[PinDevice] = []
        for _ in range(2):
            self.vio.append(PinDevice())

        self.resetb: list[PinDevice] = []
        for _ in range(1):
            self.resetb.append(PinDevice())

        for register in ["GPIO0", "GPIO1"]:
            if register not in ctx.components:
                prints.fatal(
                    "PINMUX failed to initialize! "
                    + "GPIO not initialized properly."
                )

        self.gpio0: list[PinDevice] = ctx.components["GPIO0"].object.pindevices
        self.gpio1: list[PinDevice] = ctx.components["GPIO1"].object.pindevices

        self.sps: list[PinDevice] = ctx.components["SPS0"].object.pindevices

        # Stored values just for the sake of register readback, although never
        # used in the Cr50(maybe in the BootROM/RO for register verification?)
        self.sel_stored = {}
        self.ctl_stored = {}

        # Haven behavior tested with Crapple:
        # It seems that for items like SPS, they have hardcoded PinDevice
        # attachments with no SEL value. However, it's overridden when the SEL 
        # register changes from 0. Have to assume here that it works like a 
        # default, where if nothing is connected, the mux device defaults to a 
        # device.
        self.sel_default_overrides = {
            self.dioa[2]: self.sps[0],  # SPS_MOSI drives DIOA2
            self.dioa[6]: self.sps[1],  # SPS_CLK drives DIOA6
            self.sps[2]: self.dioa[10], # DIOA10 drives SPS_MISO
            self.dioa[12]: self.sps[3], # SPS_CS_L drives DIOA12
        }

        self.exiten0 = 0
        self.exitedge0 = 0
        self.exitinv0 = 0
        self.hold = 0

    def _convert_pinmux_ctl_reg_idx_to_pindevice(
        self, idx: int
    ) -> PinDevice | None:
        if idx < 5:
            return self.diom[idx]

        if idx < 20:
            return self.dioa[idx - 5]

        if idx < 28:
            return self.diob[idx - 20]

        if idx == 28:
            return self.resetb[0]

        if idx < 31:
            return self.vio[idx - 29]

        return None

    def _convert_pinmux_sel_reg_idx_to_pindevice(
        self, idx: int
    ) -> PinDevice | None:
        if 0 < idx < 5:
            return self.diom[idx]

        if idx < 20:
            return self.dioa[idx - 5]

        if idx < 28:
            return self.diob[idx - 20]

        if idx == 28:
            return self.resetb[0]

        if idx < 31:
            return self.vio[idx - 29]

        if idx < 47:
            return self.gpio0[idx - 31]

        if idx < 63:
            return self.gpio1[idx - 47]

        return None

    # DIOxx only accepts GPIOx_GPIOx or other components.
    def _convert_pinmux_sel_val_to_gpio_pindevice(
        self, val: int
    ) -> PinDevice | None:
        if not isinstance(val, int):
            return None

        if 0x1 <= val <= 0x10:
            return self.gpio0[val - 0x1]

        if 0x11 <= val <= 0x20:
            return self.gpio1[val - 0x11]

        return None

    # GPIOx_GPIOx only accepts DIOxx or VIOx or other components.
    def _convert_pinmux_sel_val_to_dio_pindevice(
        self, val: int
    ) -> PinDevice | None:
        if not isinstance(val, int):
            return None

        if val == 0:
            return None

        if 0x1A <= val <= 0x1E:
            return self.diom[0x1E - val]

        if 0xB <= val <= 0x19:
            return self.dioa[0x19 - val]

        if 0x3 <= val <= 0xA:
            return self.diob[0xA - val]

        if val == 0x2:
            return self.vio[0]

        if val == 0x1:
            return self.vio[1]

        return None

    def pinmux_worker(self) -> None:
        while True:
            try:
                op = self.opqueue.get()
                target_fn, args = op

                target_fn(*args)

                self.opqueue.task_done()

            except Exception as e:
                prints.fatal(e)

    def start_worker(self) -> None:
        if not self.opthread:
            self.opthread = threading.Thread(target=self.pinmux_worker)
            self.opthread.daemon = True
            self.opthread.start()

    def queue_read_worker_op(self, size: int, target_fn) -> int:
        retqueue = queue.Queue()
        self.opqueue.put([target_fn, (size, retqueue)])
        self.opqueue.join()
        return retqueue.get_nowait()

    def queue_write_worker_op(self, size: int, value: int, target_fn) -> None:
        self.opqueue.put([target_fn, (size, value)])
        self.opqueue.join()

    def read_sel(self, size: int, queue: queue.Queue, index: int) -> None:
        val = 0

        try:
            val = self.sel_stored[index]
        except KeyError:
            val = 0

        queue.put(val)

    def write_sel(self, size: int, value: int, index: int) -> None:
        # Index is ALWAYS valid, because of the regmap.

        drived_device = self._convert_pinmux_sel_reg_idx_to_pindevice(index)
        if not drived_device:
            # Ignore the device, because gscemu doesn't support it.
            return

        # Validate the value given to the SEL register
        if value > 0x63:
            print(f"SEL register {index} recieved invalid value.")
            drived_device.disconnect_driver()
            self.sel_stored[index] = 0
            return

        self.sel_stored[index] = value

        driver_device = None

        if value == 0:
            # Any override?
            def_ovrd = self.sel_default_overrides.get(drived_device)
            if def_ovrd:
                # Yes, set override.
                driver_device = def_ovrd
            else: 
                # No, so we disconnect and will return.
                drived_device.disconnect_driver()

        if index < 31:
            driver_device = self._convert_pinmux_sel_val_to_gpio_pindevice(
                value
            )
        else:
            driver_device = self._convert_pinmux_sel_val_to_dio_pindevice(value)

        if not driver_device:
            # Ignore the device, because gscemu doesn't support it.
            return

        drived_device.drive_by_component(driver=driver_device)

    def read_ctl(self, size: int, queue: queue.Queue, index: int) -> None:
        val = 0

        try:
            val = self.ctl_stored[index]
        except KeyError:
            val = 0

        queue.put(val)

    def write_ctl(self, size: int, value: int, index: int) -> None:
        # Index is ALWAYS valid, because of the regmap.

        self.ctl_stored[index] = value

        drived_device = self._convert_pinmux_ctl_reg_idx_to_pindevice(index)
        if not drived_device:
            prints.warning("Could not find drived_device for CTL!!")
            return

        if not (value & 0x18 == 0x18):
            if value & 0x8:  # PD_MASK
                drived_device.add_external_drive_by_component(
                    "PINMUX_CTL", self.internal_pd
                )
            elif value & 0x10:  # PU_MASK
                drived_device.add_external_drive_by_component(
                    "PINMUX_CTL", self.internal_pu
                )
            elif (value & 0x18) == 0:
                # PD/PU not set, disconnect external driver.
                drived_device.disconnect_external_driver("PINMUX_CTL")
        else:
            prints.warning("Conflicting SEL PD/PU in PINMUX!")

        # Should we enable input reading?
        if value & 0x4:  # IE_MASK
            # Enable input
            drived_device.mask_pininfo(False)
        else:
            # Disable input
            drived_device.mask_pininfo(True)

    # These registers are to wakeup the chip from deep sleep. We don't really
    # need to implement this, since no direct implementation depends on these
    # alone. For example, SPS is attached to GPIO. With our emulator model,
    # deep sleep has not been implemented, so we don't need to have a "wakeup
    # from sleep" mechanism.
    def read_exiten0(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.exiten0)

    def write_exiten0(self, size: int, value: int) -> None:
        self.exiten0 = value

    def read_exitedge0(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.exitedge0)

    def write_exitedge0(self, size: int, value: int) -> None:
        self.exitedge0 = value

    def read_exitinv0(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.exitinv0)

    def write_exitinv0(self, size: int, value: int) -> None:
        self.exitinv0 = value

    def read_hold(self, size: int, queue: queue.Queue) -> None:
        queue.put(self.hold)

    def write_hold(self, size: int, value: int) -> None:
        self.hold = value

    def initialize_default_overrides(self) -> None:
        for drived_device, driver_device in self.sel_default_overrides.items():
            drived_device.drive_by_component(driver = driver_device)

def init_Cr50Pinmux(ctx: EmulatorContext, regs: dict) -> ComponentObjects:
    c_emu = Cr50Pinmux(ctx)
    c_emu.initialize_default_overrides()
    c_emu.start_worker()

    reg_fn_map = {
        regs["EXITEN0"]: [c_emu.read_exiten0, c_emu.write_exiten0],
        regs["EXITEDGE0"]: [c_emu.read_exitedge0, c_emu.write_exitedge0],
        regs["EXITINV0"]: [c_emu.read_exitinv0, c_emu.write_exitinv0],
        regs["HOLD"]: [c_emu.read_hold, c_emu.write_hold],
    }

    idx_regs_to_regmap(
        reg_fn_map, PINMUX_SEL_REGS_LIST, c_emu.read_sel, c_emu.write_sel
    )

    idx_regs_to_regmap(
        reg_fn_map, PINMUX_CTL_REGS_LIST, c_emu.read_ctl, c_emu.write_ctl
    )

    def component_read_handler(
        uc: qemu.Uc, offset: int, size: int, user_data: typing.Any
    ) -> int | None:
        try:
            return c_emu.queue_read_worker_op(size, reg_fn_map[offset][0])
        except KeyError:
            unhandled_register_exit(ctx, prints, "PINMUX", offset)

    def component_write_handler(
        uc: qemu.Uc, offset: int, size: int, value: int, user_data: typing.Any
    ) -> None:
        try:
            c_emu.queue_write_worker_op(size, value, reg_fn_map[offset][1])
        except KeyError:
            unhandled_register_exit(ctx, prints, "PINMUX", offset)

    return ComponentObjects(
        c_emu, component_read_handler, component_write_handler
    )
