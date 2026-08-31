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
    SYSTEM_CONTROL = 315        # cmdType 315: aGate reboot / alarm clear / factory reset
    NETWORK_INTERFACES = 317    # cmdType 317: Verbose eth/wifi interface IP and DHCP
    AESTHETICS = 327            # cmdType 327: aPower RGB LEDs
    # Discovery spans both bands, but the aGate can only JOIN 2.4 GHz
    # (FranklinWH System Installation Guide p.59, Method 2). A 5 GHz SSID
    # can therefore be scanned, ranked and written, and will simply never
    # associate. See scan_wifi_networks_ranked().
    WIFI_SCAN = 335             # cmdType 335: active AP discovery, both bands
    WIFI_CONFIG = 337           # cmdType 337: Connected SSID & local AP limits
    CLOUD_CONNECTIVITY = 339    # cmdType 339: AWS Cloud/Internet reachability
    NETWORK_SWITCHES = 341      # cmdType 341: Boolean toggles for eth0/eth1/4G/wifi
    ACCESSORY_LOADS = 353       # cmdType 353: SC/V2L/Generator current draw


class MqttResponse(IntEnum):
    """Response cmdType observed for each request in :class:`MqttCmd`.

    Useful for asserting that a response belongs to the command that was issued.

    The gateway answers request cmdType N with response N+1 — **except STATUS,
    where 203 answers with 201.** Do not assume N+1; use this mapping.

    Every value below is confirmed by matched request/response pairs in the HAR
    corpus (counts as of the 44-capture survey):

        203 -> 201  (780x)   211 -> 212  (137x)   311 -> 312  (283x)
        315 -> 316    (2x)   317 -> 318  (484x)   327 -> 328  (418x)
        335 -> 336   (39x)   337 -> 338  (388x)   339 -> 340   (67x)
        341 -> 342   (38x)   353 -> 354 (1267x)

    ``MqttCmd.SMART_CIRCUIT_TOGGLE`` (310) is deliberately absent: it has never
    been observed as a request in any capture, so its response code is unknown.
    """
    STATUS = 201                # NOT 204 — the one exception to the N+1 rule
    POWER_AND_RELAYS = 212
    SMART_CIRCUIT_INFO = 312
    SYSTEM_CONTROL = 316
    NETWORK_INTERFACES = 318
    AESTHETICS = 328
    WIFI_SCAN = 336
    WIFI_CONFIG = 338
    CLOUD_CONNECTIVITY = 340
    NETWORK_SWITCHES = 342
    ACCESSORY_LOADS = 354


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
    run_status: int                  # runtimeData.run_status  — RUN_STATUS key (0=Standby,1=Chg,2=Dis,9=VPP)
    run_status_desc: str             # derived: RUN_STATUS[runtimeData.run_status]  (NOT runtimeData.mode — different field!)
    # NOTE: runtimeData.mode is a programme/schedule ID (any int, e.g. 9=VPP, 29287=Ausgrid EA11 TOU).
    # runtimeData.run_status is the RUN_STATUS key. FranklinWH naming is intentionally confusing.

    @property
    def run_status_dec(self) -> str:
        """DEPRECATED (typo alias): Use run_status_desc."""
        return self.run_status_desc

    # ── Battery pack telemetry ───────────────────────────────────────────────
    apower_serial_numbers: str       # runtimeData.fhpSn  (list → str)
    apower_soc: str                  # runtimeData.fhpSoc  (per-pack SoC list)
    apower_power: str                # runtimeData.fhpPower  (per-pack power list)
    apower_bms_mode: str             # runtimeData.bms_work  (per-pack BMS state; use BMS_STATE[v])

    # ── Environment ──────────────────────────────────────────────────────────
    agate_ambient_temparture: float  # runtimeData.t_amb  (°C)  [sic — vendor typo]

    # ── Primary relays (main_sw[]) ───────────────────────────────────────────
    # FW encoding: 1=OPEN (connected), 0=CLOSED (disconnected)  — same for all relays
    # Array order: main_sw[Grid=0, Generator=1, Solar=2]
    grid_relay1: int                 # runtimeData.main_sw[0]  (1=OPEN, 0=CLOSED)
    generator_relay: int             # runtimeData.main_sw[1]
    solar_relay1: int                # runtimeData.main_sw[2]

    # ── Connectivity ─────────────────────────────────────────────────────────
    mobile_signal: float             # runtimeData.signal  (RSSI dBm or %)
    wifi_signal: float               # runtimeData.wifiSignal
    # Same encoding as NETWORK_TYPES / currentNetType: 1=Eth0, 2=Eth1, 3=WiFi,
    # 4=4G. The previous annotation here said 0=4G, 1=WiFi, 2=Ethernet; that was
    # unsourced and is contradicted by 20,471 corpus samples, in which connType
    # is only ever {2, 3, 4}. DEF-CONNTYPE-ENCODING-WRONG.
    network_connection: int          # runtimeData.connType — see NETWORK_TYPES

    # ── V2L / Vehicle-to-Load ────────────────────────────────────────────────
    # US hardware only. Only operational when off-grid (relay OPEN).
    v2l_enabled: int                 # runtimeData.v2lModeEnable  (None if not installed)
    v2l_status: int                  # runtimeData.v2lRunState

    # ── Generator ────────────────────────────────────────────────────────────
    # Only operational when off-grid.
    generator_enabled: int           # runtimeData.genEn   (None if not installed)
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
    # FW encoding: 1=OPEN (connected), 0=CLOSED (disconnected)  — same as primary relays.
    grid_relay2: int                 # cmdType 211 result.gridRelayStat  (second grid contactor)
    black_start_relay: int           # cmdType 211 result.bFpVApboxRelay  (black-start contactor)
    pv_relay2: int                   # cmdType 211 result.pvRelay2
    bfpv_apbox_relay: int            # cmdType 211 result.BFPVApboxRelay

    # ── Electrical measurements (cmdType 211 / get_power_info) ───────────────────
    # Only populated when get_stats(include_electrical=True).
    grid_voltage1: float             # cmdType 211 result.gridVol1   (V)
    grid_voltage2: float             # cmdType 211 result.gridVol2   (V)
    grid_current1: float             # cmdType 211 result.gridCurr1  (A) [double-r in raw]
    grid_current2: float             # cmdType 211 result.gridCurr2  (A) [double-r in raw]
    grid_frequency: float            # cmdType 211 result.gridFreq   (Hz)
    grid_set_frequency: float        # cmdType 211 result.dspSetFreq (Hz) [raw key is dspSetFreq not gridSetFreq]
    grid_line_voltage: float         # cmdType 211 result.gridLineVol ÷ 10  (V, raw is tenths)
    generator_voltage: float         # cmdType 211 result.genVoltage (V)  [raw key is genVoltage not oilVol]
    load_current1: float = 0.0       # cmdType 211 result.loadCurr1  (A, load side current L1)
    load_current2: float = 0.0       # cmdType 211 result.loadCurr2  (A, load side current L2)
    dsp_run_status: int = 0          # cmdType 211 result.dspRunStatus
    ibg_run_status: int = 0          # cmdType 211 result.ibgRunStatus
    electricity_type: int = 0        # cmdType 211 result.electricity_type

    # ── Active TOU window (optional, from get_tou_info) ──────────────────────
    active_tou_name: str = ""        # derived from TOU schedule lookup
    active_tou_dispatch: str = ""    # dispatch mode name
    active_tou_dispatch_id: int | None = None # dispatchId integer from schedule block
    active_tou_wave_type: int | None = None   # waveType integer from schedule block
    active_tou_wave_type_desc: str = ""       # string representation of waveType
    active_tou_start: str = ""       # HH:MM
    active_tou_end: str = ""         # HH:MM
    active_tou_remaining: str = ""   # "Xh Ym remaining"

    # ── Smart circuit switch states (cmdType 311) ────────────────────────────
    switch_1_state: int = 0          # runtimeData.pro_load[0]  (0=OFF, 1=ON)
    switch_2_state: int = 0          # runtimeData.pro_load[1]
    switch_3_state: int = 0          # runtimeData.pro_load[2]

    # ── Effective/display mode (derived) ─────────────────────────────────────
    # Mirrors what the FranklinWH mobile app shows as the primary mode label:
    # - run_status==9 (VPP) → tou_mode_desc (e.g. "VPP Mode")
    # - all other run_status → work_mode_desc (e.g. "Time-Of-Use")
    effective_mode: str = ""         # derived in get_stats()

    # ── APbox / MPPT config flags ─────────────────────────────────────────────
    # Enable flags — these are NOT relays; they are firmware feature-enable booleans.
    mppt_en_flag: bool = False        # runtimeData.mpptEnFlag     (aPower S only — DC Solar Inverter enabled)
    mppt_export_en: int = 0           # runtimeData.mpptExportEn   (aPower S — export enable)
    install_pv1_port: int = 0         # runtimeData.installPv1Port (PV port 1 installed: 1=yes)
    install_pv2_port: int = 0         # runtimeData.installPv2Port (PV port 2 installed: 1=yes)
    remote_solar_mode: int = 0        # solarHaveVo.remoteSolarMode (aPBox remote solar mode)

    # ── Hardware install config ───────────────────────────────────────────────
    # Static site topology flags — set at install time, rarely change.
    pv_split_ct_en: int = 0           # runtimeData.pvSplitCtEn        (solar PV CT / split-phase CT enabled)
    grid_split_ct_en: int = 0         # runtimeData.gridSplitCtEn      (split grid CT2 enabled)
    install_proximal_solar: int = 0   # runtimeData.installProximalsolar (proximal/roof solar installed: 1=yes)
    is_three_phase_install: int = 0   # runtimeData.isThreePhaseInstall  (3-phase site: 1=yes, 0=split-phase)

    # ── Load & EV relays (cmdType 211 / get_power_info — include_electrical=True) ────────
    # Relay encoding: 1=OPEN (connected), 0=CLOSED (disconnected) — same as all relays.
    load_relay1: int = 0              # cmdType 211 result.loadRelay1Stat      (smart circuit / load relay 1)
    load_relay2: int = 0              # cmdType 211 result.loadRelay2Stat      (smart circuit / load relay 2)
    v2l_relay: int = 0                # cmdType 211 result.evRelayStat  (V2L contactor — NOT EVSE/EV charger)
    load_solar_relay1: int = 0        # cmdType 211 result.loadSolarRelay1Stat (APBox solar relay 1)
    load_solar_relay2: int = 0        # cmdType 211 result.loadSolarRelay2Stat (APBox solar relay 2)


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
    is_stale: bool = False           # True if telemetry is a last-known-good cache hit


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


@dataclass(frozen=True)
class ResolvedCapabilities:
    """Compiled capabilities for a gateway, taking regional quirks into account."""
    # Identity
    country_id: int            # 1=CN, 2=US, 3=AU (site location)
    agate_generation: int      # 1=Gen 1, 2=Gen 2 (derived from sysHdVersion)
    gateway_id: str            # Gateway serial number
    
    # Solar Capabilities
    solar_installed: bool      # Sourced from solarFlag / pv1Port / pv2Port
    pv1_installed: bool
    pv2_installed: bool
    has_mppt: bool             # Sourced from mpptEnFlag (aPower S support)
    has_apbox: bool            # Sourced from apbox20Num > 0
    
    # Accessories
    has_smart_circuits: bool   # Sourced from get_accessories() type=4
    circuit_count: int         # Sourced from country_id rules (3 for US, 2 for AU)
    has_generator: bool        # Sourced from get_accessories() type=3 / genEn
    has_v2l: bool              # Sourced from v2lModeEnable (forced False in AU)
    
    # Grid
    grid_connected: bool       # Sourced from gridFlag / offGridFlag
    three_phase: bool          # Sourced from isThreePhaseInstall
    
    # Pricing & VPP
    vpp_eligible: bool         # Sourced from checkUserVppEligibility() (forced False offgrid)
    tariff_configured: bool    # Sourced from tariffSettingFlag

    def to_dict(self) -> dict:
        """Convert capabilities to a plain dictionary for API/CLI serialization."""
        from dataclasses import asdict
        return asdict(self)

