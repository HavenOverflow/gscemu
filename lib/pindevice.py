# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 HavenOverflow/appleflyer
from __future__ import annotations

import enum
import typing

from env import *
from lib.logger import GscemuLogger
from lib.threadutils import FifoLock

prints = GscemuLogger(GSCEMULATOR_LOGGER_SETTINGS)


def _normalize_resistance(resistance_ohms: float) -> float:
    # pd/pu without resistance? Just normalize it to 50k for now.
    if resistance_ohms <= 0:
        prints.warning("_normalize_resistance 50k triggered, invalid val!")
        return 50000.0

    return resistance_ohms


def _parallel_ohms(res_list: list[float]) -> float:
    # Follow the 1/R law to calculate resistance in parallel.
    inv = 0.0
    for r in res_list:
        inv += 1.0 / r

    if inv:
        # Round to 2dp, we don't need to be that accurate anyways.
        return round(1.0 / inv, 2)
    else:
        return 0.0


class PinStatus(enum.Enum):
    PULLDOWN = enum.auto()
    FLOATING = enum.auto()
    PULLUP = enum.auto()


class PinInfo:
    def __init__(self, pinstate=PinStatus.FLOATING, resistance_ohms=0.0):
        self.pinstate: PinStatus = pinstate
        self.resistance_ohms: float = resistance_ohms


EMPTY_PININFO = PinInfo()


class PinDevice:
    """
    This class is used to make pinmux devices, such as for GPIO pins,
    PINMUX pads, SPS connections, etc.
    """

    def __init__(
        self,
        interrupt_fn: typing.Callable[
            [PinStatus, PinStatus, typing.Any], None
        ] | None = None,
        interrupt_fn_userdata: typing.Any | None = None,
    ):
        self.lock = FifoLock()

        # The devices that are driving this pin. On the software side, a pin
        # can only have 1 driver.
        self.driving_me = None

        # The devices that we have been assigned to drive
        self.driving_components = set()

        # The PinInfo that this device exerts onto components that it drives and
        # on itself.
        self.device_pininfo: PinInfo = PinInfo()

        # List of external PinDevices driving us.
        self.device_pindevice_external: dict[str, PinDevice] = dict()

        # The combined PinInfo of external PinDevices' PinInfos that are driving
        # us and our own PinInfo
        self.combined_device_pininfo: PinInfo = PinInfo()

        # Factor in the device_pininfo PinInfo from the component driving us
        # too.
        self.balanced_pininfo: PinInfo = PinInfo()

        # Convenience variable, allows us to disable output on a single pin
        # to mask it to FLOATING, 0.0, without losing state when we re-enable
        # the pin.
        self.mask_device_pininfo = False

        # Optionally, a device might want a signal on FALLING_EDGE/RISING_EDGE.
        # This is needed for GPIO anyways.
        self.interrupt_signal = interrupt_fn
        self.user_data = interrupt_fn_userdata

    def _update_balanced_pininfo(
        self, new_pinstate: PinStatus, resistance: float | int
    ) -> None:
        # THIS SHOULD NOT BE CALLED WITHOUT A LOCK!!
        current_pinstate = self.balanced_pininfo.pinstate
        if current_pinstate != new_pinstate:
            self.balanced_pininfo.pinstate = new_pinstate

            if self.interrupt_signal:
                # Caller should handle this interrupt signal properly,
                # else they might get stale data.
                self.interrupt_signal(
                    current_pinstate, new_pinstate, self.user_data
                )

        self.balanced_pininfo.resistance_ohms = float(resistance)

    def _update_combined_device_pininfo(
        self, new_pinstate: PinStatus, resistance: float | int
    ) -> None:
        self.combined_device_pininfo.pinstate = new_pinstate
        self.combined_device_pininfo.resistance_ohms = float(resistance)

    # This function is used for the internal muxer to connect this device
    # to other components.
    def drive_by_component(self, driver: PinDevice) -> None:
        # Someone will drive us.
        with self.lock:
            if self.driving_me:
                with self.driving_me.lock:
                    # We should not KeyError, it is impossible.
                    # If it happens then we should catch it!
                    self.driving_me.driving_components.remove(self)

            self.driving_me = driver
            with self.driving_me.lock:
                driver.driving_components.add(self)

        self.pininfo_sync()

    def disconnect_driver(self) -> None:
        with self.lock:
            if self.driving_me:
                with self.driving_me.lock:
                    # We should not KeyError, it is impossible.
                    # If it happens then we should catch it!
                    self.driving_me.driving_components.remove(self)

                self.driving_me = None

        self.pininfo_sync()

    # This, so far, has only been used for the PINMUX internal pd/pu driving.
    # When using this function, the driver exerts a pd/pu, but the drived device
    # cannot exert a pd/pu on the driver. For bi-directionality,
    # drive_by_component needs to be used.
    # (to be refactored? iiwiw) 
    def add_external_drive_by_component(
        self, tag: str, driver: PinDevice
    ) -> None:
        with self.lock:
            if self.device_pindevice_external.get(tag):
                with self.device_pindevice_external[tag].lock:
                    # We should not KeyError, it is impossible.
                    # If it happens then we should catch it!
                    self.device_pindevice_external[tag].driving_components.remove(
                        self
                    )

            self.device_pindevice_external[tag] = driver
            with self.device_pindevice_external[tag].lock:
                driver.driving_components.add(self)

        self.pininfo_sync_device_pininfo()
        self.pininfo_sync()

    def disconnect_external_driver(self, tag: str) -> None:
        with self.lock:
            if self.device_pindevice_external.get(tag):
                with self.device_pindevice_external[tag].lock:
                    # We should not KeyError, it is impossible.
                    # If it happens then we should catch it!
                    self.device_pindevice_external[tag].driving_components.remove(
                        self
                    )

                self.device_pindevice_external.pop(tag)

        self.pininfo_sync_device_pininfo()
        self.pininfo_sync()

    def balance_pininfo(
        self, pininfos: list[PinInfo], update_fn: typing.Callable
    ) -> None:
        # THIS SHOULD NOT BE CALLED WITHOUT A LOCK!!
        pullups = []
        pulldowns = []

        for info in pininfos:
            if info.pinstate == PinStatus.PULLUP:
                pullups.append(_normalize_resistance(info.resistance_ohms))
            elif info.pinstate == PinStatus.PULLDOWN:
                pulldowns.append(_normalize_resistance(info.resistance_ohms))

        if not pullups and not pulldowns:
            update_fn(PinStatus.FLOATING, 0.0)
            return

        if pullups and not pulldowns:
            update_fn(PinStatus.PULLUP, _parallel_ohms(pullups))
            return

        if pulldowns and not pullups:
            update_fn(PinStatus.PULLDOWN, _parallel_ohms(pulldowns))
            return

        ru = _parallel_ohms(pullups)
        rd = _parallel_ohms(pulldowns)

        # Based on Cr50, it seems the chip's behavior to settle pin contention
        # is to follow the dominant puller.
        if (ru < 100) and (rd < 100):
            # This shouldn't happen. 100ohm vs 100ohm pin contention is
            # basically a short.
            prints.warning(
                "extremely strong pin contention occured!! undefined behavior."
            )
            update_fn(PinStatus.FLOATING, 0.0)
        elif ru < rd:
            update_fn(PinStatus.PULLUP, ru)
        elif rd < ru:
            update_fn(PinStatus.PULLDOWN, rd)
        else:
            prints.warning("ru == rd!! PinStatus set to FLOATING!!")
            update_fn(PinStatus.FLOATING, 0.0)

    def set_pininfo(self, pdpu: PinStatus, resistance: int | float) -> None:
        # This function is used to update the pd/pu on the pin
        # itself. If other components are driving us, then the updated value
        # would be in self.balanced_pininfo. But we need the device_pininfo
        # to track the pd/pu exerted on the chip, not influenced by the
        # balanced_pininfo.

        with self.lock:
            self.device_pininfo.pinstate = pdpu
            self.device_pininfo.resistance_ohms = round(float(resistance), 2)

        self.pininfo_sync_device_pininfo()
        self.pininfo_sync()

    def mask_pininfo(self, en: bool) -> None:
        # A convenience function to mask the pininfo value. This is needed when
        # e.g. GPIO needs to disable a pin's output.
        with self.lock:
            self.mask_device_pininfo = en

        self.pininfo_sync()

    def read_pdpu(self) -> PinStatus:
        with self.lock:
            return self.balanced_pininfo.pinstate

    def read_resistance(self) -> float:
        with self.lock:
            return self.balanced_pininfo.resistance_ohms

    def pininfo_sync_device_pininfo(self) -> None:
        with self.lock:
            pininfos = []
            pininfos.append(self.device_pininfo)
            for v in self.device_pindevice_external.values():
                pininfos.append(v.combined_device_pininfo)

            self.balance_pininfo(pininfos, self._update_combined_device_pininfo)

    def pininfo_sync(self, visited: set | None = None) -> None:
        if visited is None:
            visited = set()
        if self in visited:
            return
        visited.add(self)

        with self.lock:
            # First, balance our own PinInfo with others that are driving us.
            pininfos = []

            if self.driving_me:
                with self.driving_me.lock:
                    if not self.driving_me.mask_device_pininfo:
                        pininfos.append(self.driving_me.combined_device_pininfo)
                    else:
                        pininfos.append(EMPTY_PININFO)

            # Second, append our own PinInfo
            if not self.mask_device_pininfo:
                pininfos.append(self.combined_device_pininfo)
            else:
                pininfos.append(EMPTY_PININFO)

            self.balance_pininfo(pininfos, self._update_balanced_pininfo)

            # Snapshot driver targets so we can call them without the lock, else
            # we might deadlock.
            driving_components = list(self.driving_components)

        # Next, sync other pin's PinInfos.
        for driving_component in driving_components:
            driving_component.pininfo_sync(visited)
