# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer

"""File that contains all emulator hooks.

After some contemplation, I felt that a seperate file was needed to store the
hook functions, since they shouldn't be a part of the class that is exposed
to the user. We could make a seperate class in the future instead?
"""

import typing

import unicorn as qemu

from env import *
from lib.emulator_context import EmulatorContext
from lib.logger import GscemuLogger

from .components.m3 import (
    exc_return_handler,
    handle_externally_pended_interrupts,
    handle_primask_faultmask_update,
    pend_svcall_interrupt,
    unsafe_pend_sysintr,
    wait_for_interrupt,
)

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)


def mem_invalid_access(
    uc: qemu.Uc,
    access,
    address: int,
    size: int,
    value: int,
    user_data: EmulatorContext,
) -> bool:
    kind = {
        qemu.UC_MEM_READ_UNMAPPED: "READ",
        qemu.UC_MEM_WRITE_UNMAPPED: "WRITE",
        qemu.UC_MEM_FETCH_UNMAPPED: "FETCH",
    }

    prints.warning(
        f"Bad memory access {kind[access]} at 0x{address:x} on "
        + f"pc=0x{uc.reg_read(qemu.arm_const.UC_ARM_REG_PC):x}."
        + "Emulator will crash soon..."
    )
    if access == qemu.UC_MEM_WRITE_UNMAPPED:
        prints.warning(f"value written = 0x{value:x}")

    unsafe_pend_sysintr(user_data.c_fast.m3, 5)  # BusFault

    # When we return from a UC_MEM_x_UNMAPPED hook, we need to map the memory.
    # Unicorn will try to re-access the memory and crash the emulator.
    # There is no way around this issue as of now, and there's also no
    # UC_ERR_MAP hook to capture this issue.
    page_addr = address & ~0xFFF
    try:
        uc.mem_map(page_addr, 0x1000)
    except qemu.UcError:
        # Mapping already overlaps something else! But honestly this
        # shouldn't even happen.
        pass

    return True


def intr_hook(uc: qemu.Uc, intno: int, user_data: EmulatorContext) -> bool:
    ctx = user_data

    if intno == 2:
        # EXCP_SWI
        pend_svcall_interrupt(ctx.c_fast.m3)
    elif intno == 8:  # EXCP_EXCEPTION_EXIT
        exc_return_handler(ctx.c_fast.m3)
    else:
        prints.fatal(
            f"unhandled intr={intno}, "
            + f"pc=0x{ctx.ucmutex.reg_read(qemu.arm_const.UC_ARM_REG_PC):x}"
        )

    return True


def handle_wfi_instruction(uc: qemu.Uc, user_data: EmulatorContext) -> bool:
    ctx = user_data

    # Wait until an interrupt is externally pended from an external source.
    wait_for_interrupt(ctx.c_fast.m3)

    # Increment past the wfi instruction
    ctx.ucmutex.reg_write(
        qemu.arm_const.UC_ARM_REG_PC,
        (ctx.ucmutex.reg_read(qemu.arm_const.UC_ARM_REG_PC) + 2) | 1,
    )

    # We are still in safe hook context. Let's check if we are allowed to
    # service any interrupts right now.
    handle_externally_pended_interrupts(ctx.c_fast.m3)

    return True


def m3_interrupt_safe_point(
    uc: qemu.Uc, user_data: EmulatorContext
) -> bool:
    ctx = user_data
    handle_externally_pended_interrupts(ctx.c_fast.m3)
    return True


def m3_faultmask_primask_update(
    uc: qemu.Uc, 
    regid: int, 
    old_value: int, 
    new_value: int, 
    user_data: EmulatorContext
) -> bool:
    handle_primask_faultmask_update(user_data.c_fast.m3)
    return True


def pc_logger(
    uc: qemu.Uc, address: int, size: int, user_data: typing.TextIO
) -> bool:
    user_data.write(f"{hex(address)}\n")
    user_data.flush()
    return True

def mmio_logger_read_pc(
    uc: qemu.Uc, access: int, address: int, 
    size: int, value: int, user_data: typing.TextIO,
) -> None:
    user_data.write(
        f"r - {hex(address)}: {hex(value)}, "
        f"pc={hex(uc.reg_read(qemu.arm_const.UC_ARM_REG_PC))}\n"
    )
    user_data.flush()
    return

def mmio_logger_write_pc(
    uc: qemu.Uc, access: int, address: int, 
    size: int, value: int, user_data: typing.TextIO,
) -> None:
    user_data.write(
        f"w - {hex(address)}: {hex(value)}, "
        f"pc={hex(uc.reg_read(qemu.arm_const.UC_ARM_REG_PC))}\n"
    )
    user_data.flush()
    return

def mmio_logger_read(
    uc: qemu.Uc, access: int, address: int, 
    size: int, value: int, user_data: typing.TextIO,
) -> None:
    user_data.write(f"r - {hex(address)}: {hex(value)}\n")
    user_data.flush()
    return

def mmio_logger_write(
    uc: qemu.Uc, access: int, address: int, 
    size: int, value: int, user_data: typing.TextIO,
) -> None:
    user_data.write(f"w - {hex(address)}: {hex(value)}\n")
    user_data.flush()
    return

def blank_tick_hook(
    uc: qemu.Uc, address: int, size: int, user_data: typing.TextIO
) -> bool:
    return True
