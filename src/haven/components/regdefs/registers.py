# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer
# fmt: off

"""
All register values derived from
https://chromium.googlesource.com/chromiumos/platform/ec/+/a766634/chip/g/hw_regdefs.h
"""

from lib.helpers import pattern_list_gen as reg_list

DEFAULT_REG_WIDTH = 0x10000

REG_DEFS = {
    # Although this is FLASH, this region is immutable. On real silicon,
    # we would not be able to write to the BootROM from userspace.
    "FLASH_BROM": {  # No handler necessary
        "base_addr": 0x0,
        "size": 0x2000,
    },
    "FLASH_PROG": {  # No handler necessary
        "base_addr": 0x40000,
        "size": 0x80000,
    },
    "SRAM": {  # No handler necessary
        "base_addr": 0x10000,
        "size": 0x10000,
    },
    # INFO0 mapping determined from tock-on-titan repo. found by kxtzownsu.
    # google/tock-on-titan/kernel/h1/src/hil/flash/h1_hw.rs#L30
    "INFO0": {  # No handler necessary
        "base_addr": 0x20000,
        "size": 0x800,
    },
    "INFO1": {  # No handler necessary
        "base_addr": 0x28000,
        "size": 0x800,
    },
    "RTC0": {  # Unimplemented
        "base_addr": 0x400A0000,
        "size": DEFAULT_REG_WIDTH,
    },
    "XO0": {  # Unimplemented
        "base_addr": 0x400B0000,
        "size": DEFAULT_REG_WIDTH,
    },
    "RDD0": {  # Unimplemented
        "base_addr": 0x40440000,
        "size": DEFAULT_REG_WIDTH,
    },
    "WATCHDOG0": {  # Unimplemented
        "base_addr": 0x40500000,
        "size": DEFAULT_REG_WIDTH,
    },
    "I2CS0": {
        "base_addr": 0x40530000,
        "size": DEFAULT_REG_WIDTH,
    },
    "RBOX0": {
        "base_addr": 0x40550000,
        "size": DEFAULT_REG_WIDTH,
    },
    "I2C0": {
        "base_addr": 0x40630000,
        "size": DEFAULT_REG_WIDTH,
    },
    "SPI0": {  # Unimplemented
        "base_addr": 0x40700000,
        "size": DEFAULT_REG_WIDTH,
    },
}

MMIO_REG_DEFS = {
    "PMU": {
        "base_addr": 0x40000000,
        "size": DEFAULT_REG_WIDTH * 2,  # PMU has an unusually long reg width.
    },
    "GLOBALSEC": {
        "base_addr": 0x40090000,
        "size": DEFAULT_REG_WIDTH,
    },
    "GPIO0": {
        "base_addr": 0x40200000,
        "size": DEFAULT_REG_WIDTH,
    },
    "GPIO1": {
        "base_addr": 0x40210000,
        "size": DEFAULT_REG_WIDTH,
    },
    "USB0": {
        "base_addr": 0x40300000,
        "size": DEFAULT_REG_WIDTH,
    },
    "TRNG0": {
        "base_addr": 0x40410000,
        "size": DEFAULT_REG_WIDTH,
    },
    "CRYPTO0": {
        "base_addr": 0x40420000,
        "size": DEFAULT_REG_WIDTH,
    },
    "FUSE0": {
        "base_addr": 0x40450000,
        "size": DEFAULT_REG_WIDTH,
    },
    "SPS0": {
        "base_addr": 0x40510000,
        "size": DEFAULT_REG_WIDTH,
    },
    "SWDP0": {
        "base_addr": 0x40520000,
        "size": DEFAULT_REG_WIDTH,
    },
    "TIMELS0": {
        "base_addr": 0x40540000,
        "size": DEFAULT_REG_WIDTH,
    },
    "PINMUX": {
        "base_addr": 0x40060000,
        "size": DEFAULT_REG_WIDTH,
    },
    "KEYMGR0": {
        "base_addr": 0x40570000,
        "size": DEFAULT_REG_WIDTH,
    },
    "UART0": {"base_addr": 0x40600000, "size": DEFAULT_REG_WIDTH},
    "UART1": {"base_addr": 0x40610000, "size": DEFAULT_REG_WIDTH},
    "UART2": {"base_addr": 0x40620000, "size": DEFAULT_REG_WIDTH},
    "FLASH0": {"base_addr": 0x40720000, "size": DEFAULT_REG_WIDTH},
    "M3": {
        "base_addr": 0xE0000000,
        "size": DEFAULT_REG_WIDTH,
    },
}

UART_REGS = {
    "NCO": 0x8,
    "FIFO": 0x24,
    "CTRL": 0xC,
    "STATE": 0x14,
    "WDATA": 0x4,
    "RDATA": 0x0,
    "ICTRL": 0x10,
    "ISTATECLR": 0x20,
}

GLOBALSEC_REGS = {
    "CPU0_S_PERMISSION": 0x2D0,
    "CPU0_S_DAP_PERMISSION": 0x2D4,
    "DDMA0_PERMISSION": 0x2D8,
    "SOFTWARE_LVL": 0x2DC,
    "DBG_CONTROL": 0xA6D0,
    "DUMMYKEY": [0x9598, 0xAF04, 0xB2AC],
    "SB_COMP_STATUS": 0x1000,
    "SB_BL_SIG": reg_list(0x1004, 8),
    "SIG_UNLOCK": 0x1024,
    "HIDE_ROM": 0x40D0,
    "OBFS_SW_EN": 0x40B8,
    "ALERT": {
        "CFG_LOCK": 0x102C,
        "FW_TRIGGER": 0x4000,
        "CONTROL": 0x405C,
        "INTR_STS": reg_list(0x4004, 2),
        "NMI_EN": reg_list(0x400C, 2),
        "DLYCTR": [
            {
                "BASE": 0x4060,
                "LEN": 0x406C,
                "EN": reg_list(0x402C, 2),
                "SHUTDOWN_EN": 0x4078,
                "CLEAR": 0x4084,
            },
            {
                "BASE": 0x4064,
                "LEN": 0x4070,
                "EN": reg_list(0x4034, 2),
                "SHUTDOWN_EN": 0x407C,
                "CLEAR": 0x4088,
            },
            {
                "BASE": 0x4068,
                "LEN": 0x4074,
                "EN": reg_list(0x403C, 2),
                "SHUTDOWN_EN": 0x4080,
                "CLEAR": 0x408C,
            },
        ],
        "GROUP": [
            {
                "EN": reg_list(0x4014, 2),
                "CTR": 0x4044,
                "THRESHOLD": 0x4050,
            },
            {
                "EN": reg_list(0x401C, 2),
                "CTR": 0x4048,
                "THRESHOLD": 0x4054,
            },
            {
                "EN": reg_list(0x4024, 2),
                "CTR": 0x404C,
                "THRESHOLD": 0x4058,
            },
        ],
    },
    # For the REGION registers, hardcode it. Don't use reg_list. It
    # overcomplicates things.
    "REGION": {
        "CTRL": {
            "CPU0_D": [0x0, 0x4, 0x8, 0xC, 0x10, 0x14, 0x18, 0x1C],
            "CPU0_D_DAP": [0x40, 0x44, 0x48, 0x4C],
            "CPU0_I": [0x60, 0x64, 0x68, 0x6C, 0x70, 0x74, 0x78, 0x7C],
            "DDMA0": [0x80, 0x84, 0x88, 0x8C],
            "DSPS0": [0xA0, 0xA4, 0xA8, 0xAC],
            "DUSB0": [0xC0, 0xC4, 0xC8, 0xCC],
            "FLASH": [0xE0, 0xE4, 0xE8, 0xEC, 0xF0, 0xF4, 0xF8, 0xFC],
            "FLASH0_BULKERASE": [0x124],
            "FLASH1_BULKERASE": [0x12C],
            "CPU0_I_STAGING": [
                0x270,
                0x27C,
                0x288,
                0x294,
                0x2A0,
                0x2AC,
                0x2B8,
                0x2C4,
            ],
        },
        "CTRL_CFG_EN": {
            "CPU0_D": [0x20, 0x24, 0x28, 0x2C, 0x30, 0x34, 0x38, 0x3C],
            "CPU0_D_DAP": [0x50, 0x54, 0x58, 0x5C],
            "DDMA0": [0x90, 0x94, 0x98, 0x9C],
            "DSPS0": [0xB0, 0xB4, 0xB8, 0xBC],
            "DUSB0": [0xD0, 0xD4, 0xD8, 0xDC],
            "FLASH": [0x100, 0x104, 0x108, 0x10C, 0x110, 0x114, 0x118, 0x11C],
            "FLASH0_BULKERASE": [0x120],
            "FLASH1_BULKERASE": [0x128],
        },
        "BASE_ADDR": {
            "CPU0_D": [0x130, 0x138, 0x140, 0x148, 0x150, 0x158, 0x160, 0x168],
            "CPU0_D_DAP": [0x170, 0x178, 0x180, 0x188],
            "CPU0_I": [0x190, 0x198, 0x1A0, 0x1A8, 0x1B0, 0x1B8, 0x1C0, 0x1C8],
            "DDMA0": [0x1D0, 0x1D8, 0x1E0, 0x1E8],
            "DSPS0": [0x1F0, 0x1F8, 0x200, 0x208],
            "DUSB0": [0x210, 0x218, 0x220, 0x228],
            "FLASH": [0x230, 0x238, 0x240, 0x248, 0x250, 0x258, 0x260, 0x268],
            "CPU0_I_STAGING": [
                0x274,
                0x280,
                0x28C,
                0x298,
                0x2A4,
                0x2B0,
                0x2BC,
                0x2C8,
            ],
        },
        "SIZE": {
            "CPU0_D": [0x134, 0x13C, 0x144, 0x14C, 0x154, 0x15C, 0x164, 0x16C],
            "CPU0_D_DAP": [0x174, 0x17C, 0x184, 0x18C],
            "CPU0_I": [0x194, 0x19C, 0x1A4, 0x1AC, 0x1B4, 0x1BC, 0x1C4, 0x1CC],
            "DDMA0": [0x1D4, 0x1DC, 0x1E4, 0x1EC],
            "DSPS0": [0x1F4, 0x1FC, 0x204, 0x20C],
            "DUSB0": [0x214, 0x21C, 0x224, 0x22C],
            "FLASH": [0x234, 0x23C, 0x244, 0x24C, 0x254, 0x25C, 0x264, 0x26C],
            "CPU0_I_STAGING": [
                0x278,
                0x284,
                0x290,
                0x29C,
                0x2A8,
                0x2B4,
                0x2C0,
                0x2CC,
            ],
        },
    },
}

M3_REGS = {
    "VTOR": 0xED08,
    "DWT_CTRL": 0x1000,
    "DEMCR": 0xEDFC,
    "CPUID": 0xED00,
    "ITCMCR": 0xEF90,
    "DWT_CYCCNT": 0x1004,
    "CCR": 0xED14,
    "SHSCR": 0xED24,
    "MMFS": 0xED28,
    "BFAR": 0xED38,
    "MFAR": 0xED34,
    "HFSR": 0xED2C,
    "DFSR": 0xED30,
    "NVIC_ISER": reg_list(0xE100, 8),
    "NVIC_ICER": reg_list(0xE180, 8),
    "NVIC_ICPR": reg_list(0xE280, 8),
    "NVIC_IPR": reg_list(0xE400, 64),
    "NVIC_STIR": 0xEF00,
}

KEYMGR_REGS = {
    "HKEY_RWR": reg_list(0x3000, 8),
    "HKEY_FWR": reg_list(0x3100, 8),
    "HKEY_FRR": reg_list(0x3300, 8),
    "FW_MAJOR_VERSION": 0x3124,
    "FWR_VLD": 0x3120,
    "FWR_LOCK": 0x3128,
    "RWR_VLD": 0x3020,
    "RWR_LOCK": 0x3024,
    "CERT_REVOKE_CTRL": reg_list(0x4A8, 3),
    "HKEY_ERR_FLAGS": 0x3324,
    "SHA": {
        "CFG": {
            "MSGLEN_LO": 0x400,
            "MSGLEN_HI": 0x404,
            "EN": 0x408,
            "WR_EN": 0x40C,
        },
        "TRIG": 0x410,
        "INPUT_FIFO": 0x440,
        "STS_H": reg_list(0x444, 8),
        "KEY_W": reg_list(0x464, 8),
        "ITOP": 0x48C,
        "USE_HIDDEN_KEY": 0x490,  # Unimplemented, handled
        "USE_CERT": 0x494,  # Unimplemented
        "CERT_OVERRIDE": 0x498,  # Unimplemented
        "RAND_STALL_CTL": 0x49C,  # Unimplemented, handled
        "STS": 0x484,  # Unused, unimplemented
        "ITCR": 0x488,  # Unused, unimplemented
        "EXECUTE_COUNT_STATE": 0x4A0,  # Unused, unimplemented
        "EXECUTE_COUNT_MAX": 0x4A4,  # Unused, unimplemented
    },
    "AES": {
        "CTRL": 0x0,
        "WFIFO_DATA": 0x8,
        "RFIFO_DATA": 0xC,
        "KEY": reg_list(0x2C, 8),
        "KEY_START": 0x4C,
        "CTR": reg_list(0x50, 4),
        "RAND_STALL_CTL": 0x60,
        "WFIFO_LEVEL": 0x64,
        "WFIFO_FULL": 0x68,
        "RFIFO_LEVEL": 0x6C,
        "RFIFO_EMPTY": 0x70,
        "GCM_DO_ACC": 0x7C,
        "GCM_H": reg_list(0x80, 4),
        "GCM_MAC": reg_list(0x90, 4),
        "GCM_HASH_IN": reg_list(0xA0, 4),
        "WIPE_SECRETS": 0xB0,
        "USE_HIDDEN_KEY": 0xC0,
    },
}

FLASH_REGS = {
    "PE_CONTROL0": 0x0,
    "PE_CONTROL1": 0x4,
    "PE_EN": 0xC8,
    "TRANS": 0x8,
    "WR_DATA": reg_list(0x48, 32),
    "ERROR": 0xD4,
    "PROTECT_INFO1_ERASE": 0xC,
    "DOUT_VAL0": 0x3C,
    "DOUT_VAL1": 0x40,
    "PROG_SMART_ALGO": 0x104,
    "ERASE_SMART_ALGO": 0x134,
    "BULKERASE_SMART_ALGO": 0x154,
}

TIMELS_REGS = {
    "TIMER": {
        "CONTROL": 0x0,
        "STATUS": 0x4,
        "LOAD": 0x8,
        "RELOADVAL": 0xC,
        "VALUE": 0x10,
        "STEP": 0x14,
        "IER": 0x18,
        "ISR": 0x1C,
        "IPR": 0x20,
        "IAR": 0x24,
        "WAKEUP_ACK": 0x28,
    },
    "TIMER0_BASE": 0x0,
    "TIMER1_BASE": 0x40,
}

CRYPTO_REGS = {
    "CONTROL": 0x4,
    "INT_ENABLE": 0x14,
    "INT_STATE": 0x18,
    "HOST_CMD": 0x20,
    "RAND_STALL_CTL": 0x30,
    "WIPE_SECRETS": 0x50,
    "DMEM_DUMMY": reg_list(0x4000, 1024),
    "IMEM_DUMMY": reg_list(0x8000, 1024),
}

USB_REGS = {
    "GRSTCTL": 0x10,
}

GPIO_REGS = {
    "DATAIN": 0x0,
    "DATAOUT": 0x4,
    "SETDOUTEN": 0x10,
    "CLRDOUTEN": 0x14,
    "SETINTEN": 0x20,
    "CLRINTEN": 0x24,
    "SETINTTYPE": 0x28,
    "CLRINTTYPE": 0x2C,
    "SETINTPOL": 0x30,
    "CLRINTPOL": 0x34,
    "CLRINTSTAT": 0x38,
    "MASKLOWBYTE": reg_list(0x400, 256),
    "MASKHIGHBYTE": reg_list(0x800, 256),
}

TRNG_REGS = {
    "SECURE_POST_PROCESSING_CTRL": 0x10,
    "POST_PROCESSING_CTRL": 0x14,
    "LDO_CTRL": 0x48,
    "ANALOG_CTRL": 0x64,
    "ALLOWED_VALUES": 0x30,
    "SLICE_MAX_UPPER_LIMIT": 0x38,
    "SLICE_MIN_LOWER_LIMIT": 0x3C,
    "POWER_DOWN_B": 0x4C,
    "GO_EVENT": 0x18,
    "STOP_WORK": 0x28,
    "READ_DATA": 0x70,
    "EMPTY": 0x7C,
    "TIMEOUT_COUNTER": 0x1C,
    "TIMEOUT_MAX_TRY_NUM": 0x20,
    "FSM_STATE": 0x2C,
    "OUTPUT_TIME_COUNTER": 0x24,
}

SWDP_REGS = {
    "BUILD_DATE": 0x30,
    "BUILD_TIME": 0x34,
    "P4_LAST_SYNC": 0x2C,
}

PMU_REGS = {
    "RESET": 0x0,
    "CLRRST": 0x8,
    "RSTSRC": 0xC,
    "GLOBAL_RESET": 0x10,
    "LOW_POWER_DIS": 0x14,  # low power cfg reg
    "EXITPD_MASK": 0x4C,  # exit low power src cfg
    "PERICLKSET0": 0x64,  # enable periph clock
    "PERICLKCLR0": 0x68,  # disable periph clock
    "PERICLKSET1": 0x6C,  # enable periph clock
    "PERICLKCLR1": 0x70,  # disable periph clock
    "RST_WR_EN": reg_list(0x90, 2, 8),
    "RST": reg_list(0x94, 2, 8),
    "SW_PDB": 0x34,  # only used in the BootROM
    "PWRDN_SCRATCH": reg_list(0xA0, 32),
    "PWRDN_SCRATCH_LOCK": reg_list(0x120, 2),
    "LONG_LIFE_SCRATCH": reg_list(0x12C, 4),
    "LONG_LIFE_SCRATCH_WR_EN": 0x128,  # write-enable
    "INT_ENABLE": 0x13C,  # interrupt enable
    "CHIP_ID": 0x1FFF8,
}

SPS_REGS = {
    "CTRL": 0x0,  # SPS main control reg
    "DUMMY_WORD": 0x4,
    "FIFO_CTRL": 0x28,
    "RXFIFO_THRESHOLD": 0x48,
    "ISTATE": 0x54,  # Interrupt Status register
    "ISTATE_CLR": 0x58,  # Interrupt Status Clear register
    "ICTRL": 0x64,  # Interrupt Control register
}
