# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer
"""The component handler for the M3 component

The Cr50 runs an Arm SC300 CortexM3 armv7m CPU.
Since this is the CPU, it is tightly integrated with the Uc engine. Therefore,
this will not be threaded/queued. Instead, we will have one mutex.
"""

import unicorn as qemu
import queue

from lib.globalvars import *
from env import *
from lib.logger import GscemuLogger
from lib.threadutils import FifoLock
from src.emulators.haven.registers import REG_DEFS, M3_REGS
from lib.helpers import unhandled_register_io, unhandled_register_exit

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

_REG_BASE_ADDR = REG_DEFS["M3"]["base_addr"]

class ArmSC300:
    def __init__(self):
        self.mutex = FifoLock()
        self.demcr = 0
        self.itcmcr = 0
        self.dwt_ctrl = 0
        self.cpuid = 0x410fc331 # Known CPUID for the ArmSC300

    def read_demcr(self, addr: int) -> None:
        with self.mutex:
            ucmutex().mem_write(
                addr, 
                (self.demcr).to_bytes(4, 'little')
            )

    def write_demcr(self, val: int) -> None:
        with self.mutex:
            self.demcr = val

    def read_itcmcr(self, addr: int) -> None:
        with self.mutex:
            ucmutex().mem_write(
                addr,
                (self.itcmcr).to_bytes(4, "little")
            )

    def write_itcmcr(self, val: int) -> None:
        with self.mutex:
            self.itcmcr = val & 0x3


    def read_dwt_ctrl(self, addr: int) -> None:
        with self.mutex:
            ucmutex().mem_write(
                addr, 
                (self.dwt_ctrl).to_bytes(4, 'little')
            )

    def write_dwt_ctrl(self, val: int) -> None:
        with self.mutex:
            self.dwt_ctrl = val

    def read_cpuid(self, addr: int) -> None:
        with self.mutex:
            ucmutex().mem_write(
                addr, 
                (self.cpuid).to_bytes(4, 'little')
            )

    def write_cpuid(self, val: int) -> None:
        unhandled_register_io(prints, "WRITE", "M3", "CPUID")

c_emu = ArmSC300()

_REG_FUNC_MAP = {
    M3_REGS["DEMCR"]: [c_emu.read_demcr, c_emu.write_demcr],
    M3_REGS["DWT_CTRL"]: [c_emu.read_dwt_ctrl, c_emu.write_dwt_ctrl],
    M3_REGS["CPUID"]: [c_emu.read_cpuid, c_emu.write_cpuid],
    M3_REGS["ITCMCR"]:   [c_emu.read_itcmcr,   c_emu.write_itcmcr],
}

def component_handler(uc: qemu.Uc,
                      access,
                      address: int,
                      size: int,
                      value: int,
                      user_data
                      ) -> bool:
    """Main component handler for M3"""

    reg_offset = address - _REG_BASE_ADDR

    try:
        if access == qemu.UC_MEM_READ:
            _REG_FUNC_MAP[reg_offset][0](address)
        elif access == qemu.UC_MEM_WRITE:
            _REG_FUNC_MAP[reg_offset][1](value)

    except KeyError:
        unhandled_register_exit(prints, "M3", address)