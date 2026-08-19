# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

from pathlib import Path

from lib.logger import GscemuLoggerSettings

GSCEMULATOR_LOGGER_SETTINGS = GscemuLoggerSettings(
    global_switch=False,
    debug_prints=True,
    info_prints=True,
    warning_prints=True,
)

GSCEMULATOR_FW_STRICT_SIZE_CHECKING = False

GSCEMULATOR_PC_LOGGING_SETTINGS = {
    "enabled": False, 
    "file_path": "./pc.txt"
}
GSCEMULATOR_MMIO_TRACE = {
    "enabled": False, 
    "file_path": "./mmio-trace.txt",
    "pc_log": False
}

# -- gscemu debug flags --
# These flags change how the emulator works internally during runtime, and
# may cause unintended effects when any are set. For a prod run, these flags
# should be disabled!

# Always force SB_COMP_STATUS to True within GLOBALSEC. This allows garbage
# values to be passed into SB_BL_SIG and execution will still be unlocked.
# Decreases BootROM/RO bootup time by at least 20%.
GSCEMULATOR_FORCE_SB_COMP_STATUS = True

# Disable the CRYPTO engine and just claim the CRYPTO engine has finished
# op. This speeds up the emulator as the CRYPTO engine has large speed overhead,
# but the CRYPTO engine will be unusable.
GSCEMULATOR_DISABLE_CRYPTO_ENGINE = False

# Pull the DIOB4 pad to 5k PU to enable spiflash in the ROM.
GSCEMULATOR_ASSERT_SPIFLASH_PIN = False
