# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

"""Wrapper file to interact with the gscemu emulator object. 

Of course, this project is already modular so others can integrate it into their
other projects, if needed. But this wrapper file allows a developer to start an
instance of gscemulator independently, for testing or fuzzing, so that they need
not to take the effort to create code to interact with the emulator object.

This main.py file was built for the haven Emulator object, but we will add more
support in the future.
"""

from lib.logger import GscemuLogger
from env import *
from src.emulators.haven import Emulator as havnEmulator

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

def main():
    chipemu = havnEmulator()
    chipemu.start_emulation()

main()