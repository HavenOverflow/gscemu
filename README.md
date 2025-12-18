# gscemulator public release

## gscemu(lator), an emulator for the GSC(Google Security Chip(s))
powered by unicorn and python, gscemulator runs a copy of the public firmware.

fun fact, this was written 100% without AI by appleflyer <3

## support
- cr50
- ti50(TBC)

## how to run
`pip3 install -r requirements.txt && python3 main.py`

## standard for devs
The python code written mostly follows the google style guide, with some 
exceptions or changes here and there.
    - 80 char ruler for python files
    - functions use a standardized comment system
    - all types and return values of functions should be already defined with 
        `->` or `:`

This is not every standard that is used, but are the main standards that we 
should use to write code.