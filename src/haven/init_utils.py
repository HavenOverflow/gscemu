# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer

"""Contains all the emulator's initialization utilities."""

# Note: Redundancy checks should be applied here as much as possible. This is
# only the initialization phase of the emulator, and therefore runtime does not
# matter as much in this part of the code. We will try to increase debugability
# as much as possible and not consider extra initialization time as wasted time.

import traceback

from env import *
from lib.emulator_context import EmulatorContext
from lib.logger import GscemuLogger

from .components.regdefs import REG_DEFS
from .endorsement_cert import PROD_ENDORSEMENT_SEED, PROD_RO_CERT_REGION

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)


def map_memory(
    ctx: EmulatorContext, qemu_mem_map_list: dict, mmio_mem_map_list: dict
) -> bool:
    """Helper function to map memory in the emulator.

    This is required or we will encounter issues within the emulator where the
    memory is not mapped.
    It is good practice to manually map regions in the memory, not to just map
    everything at once(0x0 to 0xFFFFFFFF).
    """

    # Map QEMU managed memory.
    try:
        for i in qemu_mem_map_list.items():
            prints.debug(
                f"Mapping {i[0]} with "
                + f"addr=0x{i[1]['base_addr']:x}"
                + f",size=0x{i[1]['size']:x}"
            )
            ctx.uc.mem_map(i[1]["base_addr"], i[1]["size"])
    except Exception:
        # We failed to map the memory, possibly because the base_addr or size
        # was invalid. This is a dev issue and even so, we should handle it
        # properly, to accomodate for forks of this repository.
        traceback.print_exc()
        return False

    # Map ComponentHandler managed memory.
    try:
        for i in mmio_mem_map_list.items():
            prints.debug(
                f"Mapping {i[0]} with "
                + f"addr=0x{i[1]['base_addr']:x}"
                + f",size=0x{i[1]['size']:x}"
            )
            ctx.uc.mmio_map(
                i[1]["base_addr"],
                i[1]["size"],
                ctx.components[i[0]].read_fn,
                None,
                ctx.components[i[0]].write_fn,
                None,
            )
    except Exception:
        # We failed to map the memory, possibly because the base_addr or size
        # was invalid. This is a dev issue and even so, we should handle it
        # properly, to accomodate for forks of this repository.
        traceback.print_exc()
        return False

    return True


def prepare_flash_space(ctx: EmulatorContext) -> None:
    """We need to fill the entire flash space with 0xFF every initialization."""
    for flash_regions in ["FLASH_PROG", "INFO0", "INFO1"]:
        ctx.uc.mem_write(
            REG_DEFS[flash_regions]["base_addr"],
            (b"\xff" * REG_DEFS[flash_regions]["size"]),
        )

def load_firmware(
    ctx: EmulatorContext,
    mem_map_list: dict,
    fw_paths: dict,
    strict_file_size_checks: bool | None = True,
) -> bool:
    """Load firmware into the FLASH_BROM + FLASH_PROG region.

    Args:
        mem_map_list:
            List containing all mapped register definitions. This is so we know
            where FLASH_BROM and FLASH_PROG is located.
        fw_paths:
            Dictionary that contains the path to the firwmare to load.
            BootROM and firmware paths are compulsory!

            {
                "bootrom": "{path}",
                "firmware": "{path}",
                "saved_state": "{path}",
            }
        strict_file_size_checks:
            Boolean to enable or disable strict file size checking. This
            defaults to True if we do.
    """
    # TODO(appleflyer): add saved_state support in the future.

    # Check that BootROM and firmware paths were specified!
    try:
        if not fw_paths["bootrom"]:
            return False
        if not fw_paths["firmware"]:
            return False
    except Exception:
        prints.debug("One or more paths were not specified in fw_paths dict!")
        return False

    # Load BootROM into a temp var for size calculation.
    with open(fw_paths["bootrom"], "rb") as f:
        rom_data = f.read()

    # Check that the BootROM file given has the correct size to load into
    # memory. If rom_data is too short and we aren't strict, add 0s until it
    # reaches the desired length. Too long a data string will be managed.
    if strict_file_size_checks:
        # Subtract 0x20 from the BootROM size!!
        if not (len(rom_data) == (mem_map_list["FLASH_BROM"]["size"] - 0x20)):
            prints.debug("BootROM did not meet size requirements!")
            return False

    # Load RO+RW into a temp var for size calculation.
    with open(fw_paths["firmware"], "rb") as f:
        fw_data = f.read()

    # Check that the firmware file given has the correct size to load into
    # memory. If fw_data is too short and we aren't strict, add 0s until it
    # reaches the desired length. Too long a data string will be managed.
    if strict_file_size_checks:
        if not (len(fw_data) == (mem_map_list["FLASH_PROG"]["size"])):
            return False

    # Load BootROM into FLASH_BROM
    ctx.uc.mem_write(
        mem_map_list["FLASH_BROM"]["base_addr"],
        rom_data[: (mem_map_list["FLASH_BROM"]["size"] - 0x20)],
    )

    # Load firmware into FLASH_PROG
    ctx.uc.mem_write(
        mem_map_list["FLASH_PROG"]["base_addr"],
        fw_data[: mem_map_list["FLASH_PROG"]["size"]],
    )

    return True


def install_tpm_endorsement_certs(ctx: EmulatorContext) -> None:
    # Write the EPS into INFO1
    ctx.uc.mem_write(0x28000 + 0x600, PROD_ENDORSEMENT_SEED)

    # Write the cerificates into the RO_A region
    ctx.uc.mem_write(0x43800, PROD_RO_CERT_REGION)
