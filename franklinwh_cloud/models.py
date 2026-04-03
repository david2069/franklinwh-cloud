"""Shared data models for FranklinWH client.

Contains dataclasses and enums used across the client and mixin modules.
"""

from dataclasses import dataclass
from enum import Enum, IntEnum


class MqttCmd(IntEnum):
    """Legacy Gateway MQTT Relay codes (cmdType).
    
    Used exclusively by the `sendMqtt` REST endpoints to tunnel 
    hardware-specific commands to the aGate.
    """
    STATUS = 203                # cmdType 203: High-level device component polling
    POWER_AND_RELAYS = 211      # cmdType 211: Electrical voltage/freq/relays (type 1) or BMS (type 2,3)
    SMART_CIRCUIT_TOGGLE = 310  # cmdType 310: Toggle smart circuits, auto-shed limits
    SMART_CIRCUIT_INFO = 311    # cmdType 311: Smart circuit names & statuses
    NETWORK_INTERFACES = 317    # cmdType 317: Verbose eth/wifi interface IP and DHCP
    AESTHETICS = 327            # cmdType 327: aPower RGB LEDs
    WIFI_SCAN = 335             # cmdType 335: Trigger active 2.4/5GHz AP discovery
    WIFI_CONFIG = 337           # cmdType 337: Connected SSID & local AP limits
    CLOUD_CONNECTIVITY = 339    # cmdType 339: AWS Cloud/Internet reachability 
    NETWORK_SWITCHES = 341      # cmdType 341: Boolean toggles for eth0/eth1/4G/wifi
    ACCESSORY_LOADS = 353       # cmdType 353: SC/V2L/Generator current draw


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
    OFF_GRID = 2  # Alias for OFF — fixes GridStatus.OFF_GRID references in downstream consumers



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
    switch_1_state: int = 0
    switch_2_state: int = 0
    switch_3_state: int = 0


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
    """Return a Stats object with all values set to zero.

    Returns
    -------
    Stats
        A Stats object with zeroed Current and Totals values,
        suitable as a fallback when API calls fail.
    """
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

@dataclass
class SmartCircuitDetail:
    """Represents a single Smart Circuit condition.
    
    Bridging V1 (integer minute intervals / explicit load limits)
    and V2 (datetime strings array / discrete SwTimeEn) gateway firmwares.
    """
    id: int
    name: str
    mode: int
    is_on: bool
    soc_cutoff_enabled: bool
    soc_cutoff_limit: int
    pro_load_type: int
    
    # Optional V1 scheduling formats (Legacy)
    open_time: int | None = None
    close_time: int | None = None
    open_time_2: int | None = None
    close_time_2: int | None = None
    load_limit: int | None = None

    # Optional V2 scheduling formats (Modern)
    time_enabled: list[int] | None = None
    time_schedules: list[str] | None = None
    time_set: list[int] | None = None

    @classmethod
    def from_api_payload(cls, payload: dict, circuit_id: int) -> "SmartCircuitDetail":
        """Safely extract variables from the hardware JSON blob regardless of firmware edition."""
        cid = circuit_id
        return cls(
            id=cid,
            name=payload.get(f"Sw{cid}Name", ""),
            mode=payload.get(f"Sw{cid}Mode", 0),
            is_on=payload.get(f"Sw{cid}Mode", 0) == 1,
            soc_cutoff_enabled=payload.get(f"Sw{cid}AtuoEn", 0) == 1,
            soc_cutoff_limit=payload.get(f"Sw{cid}SocLowSet", 0),
            pro_load_type=payload.get(f"Sw{cid}ProLoad", 0),
            
            open_time=payload.get(f"Sw{cid}OpenTime"),
            close_time=payload.get(f"Sw{cid}CloseTime"),
            open_time_2=payload.get(f"Sw{cid}OpenTime2"),
            close_time_2=payload.get(f"Sw{cid}CloseTime2"),
            load_limit=payload.get(f"Sw{cid}LoadLimit"),
            
            time_enabled=payload.get(f"Sw{cid}TimeEn"),
            time_schedules=payload.get(f"Sw{cid}Time"),
            time_set=payload.get(f"Sw{cid}TimeSet"),
        )
