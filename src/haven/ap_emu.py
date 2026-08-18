# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer

'''
We need to emulate the AP to interact with the SPS driver on Haven. 

We recieve info from INT_AP_L and the 4 SPS lines, however the Cr50 only uses 1
to interact with us. The other 3 lines are controlled by the SPS driver directly
which we can abstract to Python code.
We control TPM_RST_L(aka PLT_RST_L) to tell the Cr50 we're online.

TPM_RST_L(to DIOM3) drives GPIO1,0 and GPIO1,4 (rising edge, falling edge)

All standards based on:
https://chromium.googlesource.com/chromiumos/platform/ec/+/refs/heads/cr50_stab/chip/g/spp_tpm.c
https://chromium.googlesource.com/chromiumos/platform/ec/+/refs/heads/cr50_stab/chip/g/spp.c
https://chromium.googlesource.com/chromiumos/platform/ec/+/refs/heads/cr50_stab/common/tpm_registers.c
https://chromium.googlesource.com/chromiumos/platform/depthcharge/+/refs/heads/main/src/drivers/tpm/google/spi.c
'''

import components

class APEmulator:
    def __init__(self):

        # TODO(appleflyer): Do we need to remove these?
        # We need to transmit data to SPS
        self.sps = None
        # We need to interact with some PINMUX pins.
        self.pinmux = None

    def initialize_ap(
        self,
        sps_object: components.sps.SPISlaveDevice,
        pinmux_object: components.pinmux.Cr50Pinmux,
    ):
        self.sps = sps_object
        self.pinmux = pinmux_object

    # Emulator exposes these functions to the user
    # We handle the underlying SPI logic and register writes.
    def write_data(input: bytes) -> None:
        pass

    def read_data() -> bytes:
        return b''