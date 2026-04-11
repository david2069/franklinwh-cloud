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


class GridConnectionState(str, Enum):
    """Grid connection state — four unambiguous states covering all topologies.

    Confirmed live (2026-04-10):
      main_sw[0]=1 → relay CLOSED → CONNECTED
      main_sw[0]=0 → relay OPEN  → SIMULATED_OFF_GRID or OUTAGE
      offgridState=1 from selectOffgrid → SIMULATED_OFF_GRID
      gridFlag=False from get_entrance_info() → NOT_GRID_TIED (startup-cached)
    """
    CONNECTED          = "Connected"          # grid-tied, relay CLOSED
    OUTAGE             = "Outage"             # firmware-detected grid loss
    NOT_GRID_TIED      = "NotGridTied"        # permanent island (no utility service)
    SIMULATED_OFF_GRID = "SimulatedOffGrid"   # user-initiated; relay OPEN, offgridState=1


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
    """Current power flow and state snapshot for FranklinWH gateway.

    All fields sourced from getDeviceCompositeInfo (cmdType 203) → result.runtimeData
    unless noted. Field comments show the raw API key name.

    Power values are in kW (positive = producing/exporting, negative = consuming/importing).
    """

    # ── Power flow (kW) ──────────────────────────────────────────────────────
    solar_production: float          # runtimeData.p_sun
    generator_production: float      # runtimeData.p_gen
    battery_use: float               # runtimeData.p_fhp  (negative = charging)
    grid_use: float                  # runtimeData.p_uti  (negative = exporting to grid)
    home_load: float                 # runtimeData.p_load
    battery_soc: float               # runtimeData.soc  (%)
    switch_1_load: float             # cmdType 311 pro_load_pwr[0] or sw_data
    switch_2_load: float             # cmdType 311 pro_load_pwr[1]
    v2l_use: float                   # cmdType 311 CarSWPower (V2L / car charger)

    # ── Grid state ───────────────────────────────────────────────────────────
    grid_connection_state: GridConnectionState  # derived — see mixins/stats.py

    # ── Operating mode ───────────────────────────────────────────────────────
    work_mode: int                   # result.currentWorkMode  (1=TOU, 2=Self, 3=EmgBkp)
    work_mode_desc: str              # derived from OPERATING_MODES[work_mode]
    device_status: int               # result.deviceStatus
    tou_mode: int                    # runtimeData.mode  (TOU sub-mode)
    tou_mode_desc: str               # runtimeData.name
    run_status: int                  # runtimeData.run_status  (0=Normal, 1=OG-Standby, 2=OG-Chg, 3=OG-Dis)
    run_status_dec: str              # derived from RUN_STATUS[run_status]

    # ── Battery pack telemetry ───────────────────────────────────────────────
    apower_serial_numbers: str       # runtimeData.fhpSn  (list → str)
    apower_soc: str                  # runtimeData.fhpSoc  (per-pack SoC list)
    apower_power: str                # runtimeData.fhpPower  (per-pack power list)
    apower_bms_mode: str             # runtimeData.bms_work  (per-pack BMS state; use BMS_STATE[v])

    # ── Environment ──────────────────────────────────────────────────────────
    agate_ambient_temparture: float  # runtimeData.t_amb  (°C)  [sic — vendor typo]

    # ── Primary relays (main_sw[]) ───────────────────────────────────────────
    # FW encoding: 1=OPEN (disconnected), 0=CLOSED (connected)
    # Array order: main_sw[Grid=0, Generator=1, Solar=2]
    grid_relay1: int                 # runtimeData.main_sw[0]  (1=OPEN, 0=CLOSED)
    generator_relay: int             # runtimeData.main_sw[1]
    solar_relay1: int                # runtimeData.main_sw[2]

    # ── Connectivity ─────────────────────────────────────────────────────────
    mobile_signal: float             # runtimeData.signal  (RSSI dBm or %)
    wifi_signal: float               # runtimeData.wifiSignal
    network_connection: int          # runtimeData.connType  (0=4G, 1=WiFi, 2=Ethernet)

    # ── V2L / Vehicle-to-Load ────────────────────────────────────────────────
    v2l_enabled: int                 # runtimeData.v2lModeEnable
    v2l_status: int                  # runtimeData.v2lRunState

    # ── Generator ────────────────────────────────────────────────────────────
    generator_enabled: int           # runtimeData.genEn
    generator_status: int            # runtimeData.genStat

    # ── Power flow breakdown (kW) ────────────────────────────────────────────
    grid_charging_battery: float     # runtimeData.gridChBat
    solar_export_to_grid: float      # runtimeData.soOutGrid
    solar_charging_battery: float    # runtimeData.soChBat
    battery_export_to_grid: float    # runtimeData.batOutGrid

    # ── APbox / Remote Solar (MPPT) ──────────────────────────────────────────
    apbox_remote_solar: float        # runtimeData.apbox20Pv  (APbox 20A PV input kW)
    remote_solar_enabled: int        # runtimeData.remoteSolarEn
    mppt_status: int                 # runtimeData.mpptSta
    mppt_all_power: float            # runtimeData.mpptAllPower  (kW)
    mppt_active_power: float         # runtimeData.mpptActPower  (kW)
    mpan_pv1_power: float            # runtimeData.mPanPv1Power  (kW)
    mpan_pv2_power: float            # runtimeData.mPanPv2Power  (kW)
    remote_solar_pv1: float          # runtimeData.remoteSolar1Power  (kW)
    remote_solar_pv2: float          # runtimeData.remoteSolar2Power  (kW)

    # ── Alarms ───────────────────────────────────────────────────────────────
    alarms_count: int                # derived from result.currentAlarmVOList length

    # ── Extended relays (cmdType 211 / get_power_info) ───────────────────────
    # Only populated when get_stats(include_electrical=True) — extra MQTT call.
    # FW encoding: 1=OPEN, 0=CLOSED
    grid_relay2: int                 # cmdType 211 result.gridRelayStat  (second grid contactor)
    black_start_relay: int           # cmdType 211 result.bFpVApboxRelay  (black-start contactor)
    pv_relay2: int                   # cmdType 211 result.pvRelay2
    bfpv_apbox_relay: int            # cmdType 211 result.BFPVApboxRelay

    # ── Electrical measurements (cmdType 211 / get_power_info) ───────────────
    # Only populated when get_stats(include_electrical=True).
    grid_voltage1: float             # cmdType 211 result.gridVol1  (V)
    grid_voltage2: float             # cmdType 211 result.gridVol2  (V)
    grid_current1: float             # cmdType 211 result.gridCur1  (A)
    grid_current2: float             # cmdType 211 result.gridCur2  (A)
    grid_frequency: float            # cmdType 211 result.gridFreq  (Hz)
    grid_set_frequency: float        # cmdType 211 result.gridSetFreq  (Hz)
    grid_line_voltage: float         # cmdType 211 result.gridLineVol ÷ 10  (V, raw is tenths)
    generator_voltage: float         # cmdType 211 result.oilVol  (V)

    # ── Active TOU window (optional, from get_tou_info) ──────────────────────
    active_tou_name: str = ""        # derived from TOU schedule lookup
    active_tou_dispatch: str = ""    # dispatch mode name
    active_tou_start: str = ""       # HH:MM
    active_tou_end: str = ""         # HH:MM
    active_tou_remaining: str = ""   # "Xh Ym remaining"

    # ── Smart circuit switch states (cmdType 311) ────────────────────────────
    switch_1_state: int = 0          # runtimeData.pro_load[0]  (0=OFF, 1=ON)
    switch_2_state: int = 0          # runtimeData.pro_load[1]
    switch_3_state: int = 0          # runtimeData.pro_load[2]


@dataclass
class Totals:
    """Daily energy totals for FranklinWH gateway (kWh, reset at midnight local time).

    All fields sourced from getDeviceCompositeInfo (cmdType 203) → result.runtimeData
    unless noted. Field comments show the raw API key name.
    """

    # ── Battery (kWh) ────────────────────────────────────────────────────────
    battery_charge: float            # runtimeData.kwh_fhp_chg
    battery_discharge: float         # runtimeData.kwh_fhp_di

    # ── Grid (kWh) ───────────────────────────────────────────────────────────
    grid_import: float               # runtimeData.kwh_uti_in
    grid_export: float               # runtimeData.kwh_uti_out

    # ── Generation (kWh) ─────────────────────────────────────────────────────
    solar: float                     # runtimeData.kwh_sun
    generator: float                 # runtimeData.kwh_gen
    home_use: float                  # runtimeData.kwh_load

    # ── Smart switch energy (kWh, from cmdType 311 sw_data) ──────────────────
    switch_1_use: float              # sw_data.SW1ExpEnergy
    switch_2_use: float              # sw_data.SW2ExpEnergy
    v2l_export: float                # sw_data.CarSWExpEnergy  (V2L export)
    v2l_import: float                # sw_data.CarSWImpEnergy  (V2L import)

    # ── Load breakdown by source ──────────────────────────────────────────
    # NOTE: live observation shows values ~13442, 3933, 2632 — far above daily kWh.
    # Suspected to be cumulative lifetime Wh (not daily kWh). Treat with caution.
    solar_load_kwh: float            # runtimeData.kwhSolarLoad  (suspected cumulative Wh)
    grid_load_kwh: float             # runtimeData.kwhGridLoad   (suspected cumulative Wh)
    battery_load_kwh: float          # runtimeData.kwhFhpLoad    (suspected cumulative Wh)
    generator_load_kwh: float        # runtimeData.kwhGenLoad    (suspected cumulative Wh)

    # ── APbox / MPAN PV (kWh) ────────────────────────────────────────────────
    mpan_pv1_wh: float               # runtimeData.mpanPv1Wh  (note: field name is Wh not kWh)
    mpan_pv2_wh: float               # runtimeData.mpanPv2Wh


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
            GridConnectionState.CONNECTED,          # grid_connection_state
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
