# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 HavenOverflow/appleflyer

'''Share objects across the entire codebase

Import where we share classes/objects/variables across the codebase.
'''

from termcolor import colored

class GscemuLoggerSettings:
    '''Object to contain GscemuLogger print logger settings.

    Attributes:
        global_switch:
            Enable/disable ALL prints except FATAL prints.
        debug_prints:
            Enable/disable DEBUG prints.
        info_prints: 
            Enable/disable INFO prints.
        warning_prints:
            Enable/disable WARNING prints.
    '''

    def __init__(
        self, global_switch, debug_prints, info_prints, warning_prints
    ) -> None:
        self.global_switch = global_switch
        self.debug = debug_prints
        self.info = info_prints
        self.warning = warning_prints

class GscemuLogger:
    '''Global logger that's used for debugging. 
    
    We use a class that can be used everywhere so that each file running in 
    gscemulator(for emulating hardware components) can have a unique print 
    message, such as "WARNING[gpio.py]: GPIO pulled up". This makes debug 
    messages more meaningful and more useful.

    Attributes:
        settings: 
            Contains a GscemuLoggerSettings object.
        caller:
            String containing the caller filename, for example, "gpio.py".
    '''

    def __init__(
            self,
            print_settings: GscemuLoggerSettings, 
            caller: str,
        ) -> None:
        '''Initializes the GscemuLogger object.

        Args:
            settings: 
                Contains a GscemuLoggerSettings object.
            caller:
                String containing the caller filename, for example, "gpio.py".
        '''
        self.settings = print_settings
        self.caller = caller