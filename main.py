# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

"""Wrapper file to interact with the gscemu emulator object. 

Of course, this project is already modular so others can integrate it into their
other projects, if needed. But this wrapper file allows a developer to start an
instance of gscemulator independently, for testing or fuzzing, so that they need
not to take the effort to create code to interact with the emulator object.
"""

from lib.globalfn import *
from env import *

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)

def main():
    prints.debug("test")

main()