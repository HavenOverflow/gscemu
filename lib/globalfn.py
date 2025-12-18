# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

"""Share objects across the entire codebase

Import where we share classes/objects/variables across the codebase.
"""

import inspect
import os
from termcolor import colored

class GscemuLoggerSettings:
    """Object to contain GscemuLogger print logger settings.

    Attributes:
        global_switch:
            Enable/disable ALL prints except FATAL prints. If disabled, this
            overrides all print options to disable them. If enabled, we follow
            the set print options.
        debug_prints:
            Enable/disable DEBUG prints.
        info_prints: 
            Enable/disable INFO prints.
        warning_prints:
            Enable/disable WARNING prints.
    """

    def __init__(
        self, 
        global_switch: bool, 
        debug_prints: bool, 
        info_prints: bool, 
        warning_prints: bool,
    ) -> None:
        self.global_switch = global_switch
        self.debug = debug_prints
        self.info = info_prints
        self.warning = warning_prints

class GscemuLogger:
    """Global logger that's used for debugging. 
    
    We use a class that can be used everywhere so that each file running in 
    gscemulator(for emulating hardware components) can have a unique print 
    message, such as "WARNING[gpio.py]: GPIO pulled up". This makes debug 
    messages more meaningful and more useful.

    Attributes:
        settings: 
            Contains a GscemuLoggerSettings object.
        caller:
            Contains a string containing the caller filename, for example, 
            "gpio.py".
    """

    def __init__(
            self,
            print_settings: GscemuLoggerSettings, 
            caller_override: str | None = None,
        ) -> None:
        """Initializes the GscemuLogger object.

        Args:
            settings: 
                Contains a GscemuLoggerSettings object.
            caller_override:
                Override the detected caller's filename.
        """
        self.settings = print_settings
        
        # Check if caller_override exists first. If it doesn't exist, then
        # auto-detect the caller's filename.
        # This feature is actually not really needed, we might remove it in the
        # future.
        if caller_override:
            self.caller = caller_override
        else:
            self.caller = os.path.basename(
                (inspect.currentframe().f_back) # Get the caller's frame
                .f_code.co_filename # Get the filename in the caller's frame
            )

    def debug(
            self, *args, **kwargs
        ) -> bool:
        """Print a string with "DEBUG[xxx.py]: {your_string}".

        Returns:
            Boolean of whether we printed the message. `True` if the setting was
            enabled, `False` if the setting was disabled.
        """

        if not self.settings:
            return False
        
        print(f"DEBUG[{self.caller}]:", *args, **kwargs)

        return True

    def warning(
            self, *args, **kwargs
        ) -> bool:
        """Print a string with "WARNING[xxx.py]: {your_string}".
        
        Returns:
            Boolean of whether we printed the message. `True` if the setting was
            enabled, `False` if the setting was disabled.
        """

        if not self.settings.warning:
            return False
        
        print(f"WARNING[{self.caller}]:", *args, **kwargs)

        return True
    
    def info(
            self, *args, **kwargs
        ) -> bool:
        """Print a string with "INFO[xxx.py]: {your_string}".
        
        Returns:
            Boolean of whether we printed the message. `True` if the setting was
            enabled, `False` if the setting was disabled.
        """

        if not self.settings.info:
            return False
        
        print(f"INFO[{self.caller}]:", *args, **kwargs)

        return True
    
    def fatal(
            self, *args, **kwargs
        ) -> bool:
        """Print a string with "FATAL[xxx.py]: {your_string}".
        
        Returns:
            Boolean of whether we printed the message. `True` if the setting was
            enabled, `False` if the setting was disabled.

            This is a fatal message, and it can NEVER be disabled. We will
            always return `True`. This is a special exception to this print
            logging function.
        """
        
        print(f"FATAL[{self.caller}]:", *args, **kwargs)
        return True
