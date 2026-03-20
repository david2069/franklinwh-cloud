"""Shared data models for FranklinWH client.

Contains dataclasses and enums used across the client and mixin modules.
"""

from dataclasses import dataclass
from enum import Enum


class GridStatus(Enum):
    """Represents the status of the grid connection for the FranklinWH gateway.

    Attributes:
        NORMAL (int): Grid connection is normal / up.
        DOWN (int): Grid connection is abnormal / down.
        OFF (int): Grid connection is turned off at the gateway.

    OFF is set by software, specifically Settings / Go Off-Grid in the app.
    DOWN is external to the gateway.
    NORMAL indicates normal operation.
    """

    NORMAL = 0
    DOWN = 1
    OFF = 2


@dataclass
class Current:
    """Current statistics for FranklinWH gateway."""

    solar_production: float
    generator_production: float
    battery_use: float
    grid_use: float
    home_load: float
    battery_soc: float
    switch_1_load: float
    switch_2_load: float
    v2l_use: float
    grid_status: GridStatus
    work_mode: int
    work_mode_desc: str
    device_status: int
    tou_mode: int
    tou_mode_desc: str
    run_status: int
    run_status_dec: str
    apower_serial_numbers: str
    apower_soc: str
    apower_power: str
    apower_bms_mode: str
    agate_ambient_temparture: float
    grid_relay1: int
    generator_relay: int
    solar_relay1: int
    mobile_signal: float
    wifi_signal: float
    network_connection: int
    v2l_enabled: int
    v2l_status: int
    generator_enabled: int
    generator_status: int
    grid_charging_battery: float
    solar_export_to_grid: float
    solar_charging_battery: float
    battery_export_to_grid: float
    apbox_remote_solar: float
    remote_solar_enabled: int
    mppt_status: int
    mppt_all_power: float
    mppt_active_power: float
    mpan_pv1_power: float
    mpan_pv2_power: float
    remote_solar_pv1: float
    remote_solar_pv2: float
    alarms_count: int
    grid_relay2: int
    black_start_relay: int
    pv_relay2: int
    bfpv_apbox_relay: int
    grid_voltage1: float
    grid_voltage2: float
    grid_current1: float
    grid_current2: float
    grid_frequency: float
    grid_set_frequency: float
    grid_line_voltage: float
    generator_voltage: float
    active_tou_name: str = ""
    active_tou_dispatch: str = ""
    active_tou_start: str = ""
    active_tou_end: str = ""
    active_tou_remaining: str = ""


@dataclass
class Totals:
    """Total energy statistics for FranklinWH gateway."""

    battery_charge: float
    battery_discharge: float
    grid_import: float
    grid_export: float
    solar: float
    generator: float
    home_use: float
    switch_1_use: float
    switch_2_use: float
    v2l_export: float
    v2l_import: float
    solar_load_kwh: float
    grid_load_kwh: float
    battery_load_kwh: float
    generator_load_kwh: float
    mpan_pv1_wh: float
    mpan_pv2_wh: float


@dataclass
class Stats:
    """Statistics for FranklinWH gateway."""

    current: Current
    totals: Totals


def empty_stats() -> Stats:
    """Return a Stats object with all values set to zero."""
    return Stats(
        Current(
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0,   # solar, generator, battery, grid, home, soc
            0.0, 0.0, 0.0,                     # sw1, sw2, v2l
            GridStatus.NORMAL,                  # grid_status
            0, "", 0, 0, "", 0, "",             # work_mode through run_status_dec
            "", "", "", "",                     # apower fields
            0.0,                                # agate_ambient_temparture
            0, 0, 0,                            # relays
            0.0, 0.0, 0,                        # signals
            0, 0, 0, 0,                         # v2l/generator enable/status
            0.0, 0.0, 0.0, 0.0, 0.0,           # grid/solar/battery flows
            0, 0, 0.0, 0.0,                     # remote solar, mppt
            0.0, 0.0, 0.0, 0.0,                # pv powers
            0,                                  # alarms_count
            0, 0, 0, 0,                         # relay2, black_start, pv_relay2, bfpv
            0.0, 0.0, 0.0, 0.0,                # grid voltages/currents
            0.0, 0.0, 0.0, 0.0,                # grid freq, line vol, gen vol
        ),
        Totals(
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,  # battery through home
            0.0, 0.0, 0.0, 0.0,                   # switch/v2l
            0.0, 0.0, 0.0, 0.0,                   # load kwh
            0.0, 0.0,                              # mpan pv
        ),
    )
