# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

"""Main file that contains the Emulator object and all it's logic.

The emulator emulates the H1B3C chip, which is to say:
- H1 chip
- RevB ver 3
- Chromebook
"""

import unicorn as qemu
from .init_utils import *

class Emulator:
    """Emulator object for the haven chip.
    
    Attributes:
        uc:
            The unicorn engine object which runs the actual ARM instructions.
    """
    
    def __init__(self) -> None:
        """Initalizes the emulator.
        
        Initalizes all the components of the emulator like the unicorn engine,
        components, registers, etc.
        """

        # For the H1B3C, we're running a ARM Cortex-M3 chip, or at least that's
        # what's documented.
        self.uc = qemu.Uc(
            qemu.UC_ARCH_ARM,
            qemu.UC_MODE_THUMB,
            qemu.arm_const.UC_CPU_ARM_CORTEX_M3
        )

    def start_emulation(self) -> None:
        """Run the emulator."""
        pass
