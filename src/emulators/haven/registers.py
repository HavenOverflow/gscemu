# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

from lib.globalvars import *

# Yes/No/NA
# No meaning that a handler can be defined, but we haven't done it
# Yes meaning that a handler exists for that component
# NA meaning that a handler is not needed for that component.
REG_DEFS = {
    # Although this is FLASH, this region is immutable. On real silicon,
    # we would not be able to write to the BootROM from userspace.
    "FLASH_BROM": { # NA
        "base_addr": 0x0,
        "size": 0x2000,
    },

    "FLASH_PROG": { # NA
        "base_addr": 0x40000,
        "size": 0x80000,
    },

    "SRAM": { # NA
        "base_addr": 0x10000,
        "size": 0x10000,
    },

    "PMU": { # No
        "base_addr": 0x40000000,
        "size": DEFAULT_REG_WITDH,
    },

    "GLOBALSEC": { # Yes
        "base_addr": 0x40090000,
        "size": DEFAULT_REG_WITDH,
    },

    "FUSE0": { # Yes
        "base_addr": 0x40450000,
        "size": DEFAULT_REG_WITDH,
    },

    "UART0": { # Yes
        "base_addr": 0x40600000,
        "size": DEFAULT_REG_WITDH
    },

    "UART1": { # Yes
        "base_addr": 0x40610000,
        "size": DEFAULT_REG_WITDH
    },

    "UART2": { # Yes
        "base_addr": 0x40620000,
        "size": DEFAULT_REG_WITDH
    },

    "RTC0": { # No
        "base_addr": 0x400a0000,
        "size": DEFAULT_REG_WITDH,
    },

    "M3": { # No
        "base_addr": 0xe0000000,
        "size": DEFAULT_REG_WITDH,
    }
}

UART_REGS = {
    "NCO": 0x8,
    "NCO_WIDTH": 16,
    "OVERSAMPLE_RATE": 16,
    "ADDR_BASE_SEP": 0x10000,
    "PCLK_FREQ": 24 * 1000 * 1000,
    "FIFO": 0x24,
    "CTRL": 0xc,
    "STATE": 0x14,
    "WDATA": 0x4,
    "RDATA": 0x0,
    "ICTRL": 0x10,
    "ISTATECLR": 0x20,
}

GLOBALSEC_REGS = {
    "ALERT_CONTROL": 0x405c,
}

M3_REGS = {
    "DWT_CTRL": 0x1000,
    "DEMCR": 0xedfc,
    "ITCMCR": 0xef90,
    "CPUID": 0xed00,

    "UNKNOWN_REG1": 0xef90,
}