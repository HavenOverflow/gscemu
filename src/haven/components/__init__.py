# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer

from lib.emulator_context import ComponentObjects, EmulatorContext

# Manual import of the component handlers. Refactor in the future?
# Probably not.
from . import (
    crypto,
    flash,
    fuse,
    globalsec,
    gpio,
    keymgr,
    m3,
    pinmux,
    pmu,
    regdefs,
    sps,
    swdp,
    timels,
    trng,
    uart,
    usb,
)


class ComponentFastLookup:
    """
    Helper "pointers" for components.
    These are typically tied to a component.
    Will deprecate eventually when there's better ways to fix this?
    (M3 interrupts, TIMERLS debug start/stops)
    """

    def __init__(self):
        self.timels = None
        self.m3 = None
        self.uart0 = None

        # PINMUX and GPIO not necessary, only increases setup time, not runtime.


def blank_read_handler(*args, **kwargs) -> int:
    return 0


def blank_write_handler(*args, **kwargs) -> None:
    return


blank_component = ComponentObjects(
    None, blank_read_handler, blank_write_handler
)


def initialize_components(ctx: EmulatorContext) -> None:
    ctx.components["M3"] = m3.init_ArmSC300(ctx, regdefs.M3_REGS)
    ctx.c_fast.m3 = ctx.components["M3"].object

    # TIMELS comes after M3
    ctx.components["TIMELS0"] = timels.init_LowSpeedTimer(
        ctx, regdefs.TIMELS_REGS
    )
    ctx.c_fast.timels = ctx.components["TIMELS0"].object

    # UART comes after M3
    ctx.components["UART0"] = uart.init_UartController(ctx, regdefs.UART_REGS)
    ctx.c_fast.uart0 = ctx.components["UART0"].object

    ctx.components["UART1"] = blank_component
    ctx.components["UART2"] = blank_component

    # CRYPTO comes after M3 and TIMELS
    ctx.components["CRYPTO0"] = crypto.init_CryptoAccelerator(
        ctx, regdefs.CRYPTO_REGS
    )

    # GPIO comes before PINMUX, we need to setup the PinDevice.
    ctx.components["GPIO0"] = gpio.init_GpioController(
        ctx, regdefs.GPIO_REGS, 0
    )
    ctx.components["GPIO1"] = gpio.init_GpioController(
        ctx, regdefs.GPIO_REGS, 1
    )

    # SPS comes before PINMUX, we need to setup the PinDevice.
    ctx.components["SPS0"] = sps.init_SPISlaveDevice(ctx, regdefs.SPS_REGS)

    # PINMUX comes after GPIO0, GPIO1, SPS
    ctx.components["PINMUX"] = pinmux.init_Cr50Pinmux(ctx, regdefs.PINMUX_REGS)

    # Order of these below don't matter.
    ctx.components["GLOBALSEC"] = globalsec.init_HavenGlobalsec(
        ctx, regdefs.GLOBALSEC_REGS
    )
    ctx.components["FLASH0"] = flash.init_FlashController(
        ctx, regdefs.FLASH_REGS
    )
    ctx.components["FUSE0"] = fuse.init_eFuses(
        ctx, regdefs.fuse_registers.FUSE_DEFAULTS
    )
    ctx.components["SWDP0"] = swdp.init_ARMSoftwareDebugPort(
        ctx, regdefs.SWDP_REGS
    )
    ctx.components["PMU"] = pmu.init_PowerManagementUnit(ctx, regdefs.PMU_REGS)

    ctx.components["KEYMGR0"] = keymgr.init_KeymgrController(
        ctx, regdefs.KEYMGR_REGS
    )

    ctx.components["TRNG0"] = trng.init_TRNGEngine(ctx, regdefs.TRNG_REGS)

    ctx.components["USB0"] = usb.init_UsbController(ctx, regdefs.USB_REGS)
