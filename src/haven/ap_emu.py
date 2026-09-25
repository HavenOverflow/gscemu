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

import threading

from lib.pindevice import PinDevice, PinStatus

from .components.pinmux import Cr50Pinmux
from .components.sps import SPISlaveDevice

class APEmulator:
    def __init__(self) -> None:
        self.sps: SPISlaveDevice | None = None
        self.pinmux: Cr50Pinmux | None = None

        self.tpm_rst_l = PinDevice()
        self.read_buffer = bytearray()
        self.transaction_lock = threading.Lock()

    def initialize_ap(
        self,
        sps_object: SPISlaveDevice,
        pinmux_object: Cr50Pinmux,
    ) -> None:
        self.sps = sps_object
        self.pinmux = pinmux_object

        # Poppy routes PLT_RST_L to DIOM3. The AP starts out of reset.
        pinmux_object.diom[3].add_external_drive_by_component(
            "AP_EMU_TPM_RST_L", self.tpm_rst_l
        )

        self.set_tpm_reset(False)

    def is_initialized_sps(self) -> SPISlaveDevice:
        # Just in case the user calls it very early when Cr50 isn't set up
        # yet. Quite impossible for this to happen.
        if self.sps is None:
            raise RuntimeError("AP emulator has not been initialized")
        
        return self.sps

    def set_tpm_reset(self, asserted: bool) -> None:

        if asserted:
            level = PinStatus.PULLDOWN
        else:
            level = PinStatus.PULLUP

        self.tpm_rst_l.set_pininfo(level, 10.0)

        if self.pinmux is not None:
            reset_pad = self.pinmux.diom[3]
            reset_pad.pininfo_sync_device_pininfo()
            reset_pad.pininfo_sync()

    def write_data(self, input: bytes) -> None:
        sps = self.is_initialized_sps()
        data = bytes(input)

        with self.transaction_lock:
            sps.set_chip_select(True)
            try:
                received = sps.transfer(data)
            finally:
                sps.set_chip_select(False)
            self.read_buffer.extend(received)

    def read_data(self) -> bytes:
        with self.transaction_lock:
            output = bytes(self.read_buffer)
            self.read_buffer.clear()
            return output