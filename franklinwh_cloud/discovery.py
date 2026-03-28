"""Device discovery snapshot — structured result from client.discover().

Provides a DeviceSnapshot dataclass that any Python client can use.
The CLI discover command renders this; FEM and user scripts can also consume it.

Feature: FEAT-CLI-DISCOVER-VERBOSE
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class SiteInfo:
    """Site/location information."""
    site_id: int = 0
    site_name: str = ""
    gateway_name: str = ""
    address: str = ""
    country: str = ""
    country_id: int = 0
    province: str = ""
    province_id: int = 0
    city: str = ""
    postcode: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    timezone: str = ""
    utc_offset: float = 0.0
    dst_active: bool = False
    alpha_code: str = ""
    electric_company: str = ""
    tariff_name: str = ""
    der_schedule: str = ""       # NEM type from TOU template
    grid_profile: str = ""       # Grid compliance profile (e.g. AS4777 or User Defined)
    pto_date: str = ""           # Permission to Operate date


@dataclass
class AgateInfo:
    """aGate gateway identity and firmware."""
    serial: str = ""
    model: str = ""
    model_name: str = ""
    sku: str = ""
    hw_version: int = 0
    hw_version_str: str = ""     # e.g. "FranklinWH System1.2"
    generation: int = 0          # 1 or 2
    protocol_ver: str = ""
    firmware: str = ""           # IBG version
    status: int = 0
    active_status: int = 0
    device_time: str = ""
    device_date: str = ""
    conn_type: int = 0
    conn_type_name: str = ""
    sim_status: int = 0
    sim_status_name: str = ""
    wifi_signal: int = 0         # dBm
    mobile_signal: int = 0       # dBm
    # Firmware versions (Tier 3)
    ibg_version: str = ""
    sl_version: str = ""
    aws_version: str = ""
    app_version: str = ""
    meter_version: str = ""
    # MAC-1 / MSA detection
    msa_model: Optional[str] = None
    msa_serial: Optional[str] = None
    # Timestamps
    activated: Optional[str] = None
    installed: Optional[str] = None
    created: Optional[str] = None


@dataclass
class APowerUnit:
    """Per-aPower battery unit details."""
    serial: str = ""
    rated_power_kw: float = 0.0
    rated_capacity_kwh: float = 0.0
    remaining_kwh: float = 0.0
    soc: float = 0.0
    status: int = 0
    pe_hw_ver: str = ""
    # Firmware (Tier 2+)
    fpga_ver: str = ""
    dcdc_ver: str = ""
    inv_ver: str = ""
    bms_ver: str = ""
    bl_ver: str = ""             # bootloader
    th_ver: str = ""             # thermal
    mppt_app_ver: str = ""       # aPower S MPPT firmware


@dataclass
class BatteryInfo:
    """Battery inventory summary."""
    count: int = 0
    total_capacity_kwh: float = 0.0
    total_rated_power_kw: float = 0.0
    units: List[APowerUnit] = field(default_factory=list)


@dataclass
class AccessoryItem:
    """A single registered accessory."""
    serial: str = ""
    accessory_type: int = 0
    type_name: str = ""          # "smart_circuits", "generator", etc.
    name: str = ""
    create_time: str = ""


@dataclass
class SmartCircuitConfig:
    """Smart circuit configuration from MQTT cmd 311."""
    count: int = 0               # 2 or 3
    version: int = 0             # 1 or 2
    merged: bool = False         # SwMerge — SC1+SC2 merged
    names: List[str] = field(default_factory=list)
    v2l_port: bool = False       # V2L available on this SC
    v2l_enabled: bool = False    # V2L currently active


@dataclass
class AccessoriesInfo:
    """All accessories and their configuration."""
    items: List[AccessoryItem] = field(default_factory=list)
    has_smart_circuits: bool = False
    has_generator: bool = False
    has_apbox: bool = False
    has_ahub: bool = False
    has_mac1: bool = False
    smart_circuits: Optional[SmartCircuitConfig] = None
    # aPBox digital I/O
    apbox_di: List[int] = field(default_factory=list)
    apbox_do_status: List[int] = field(default_factory=list)


@dataclass
class FeatureFlags:
    """Feature flag analysis — ✅/❌ table."""
    solar: bool = False
    solar_detail: str = ""       # "PV1 + PV2", "PV1 only", etc.
    tariff_configured: bool = False
    pcs_enabled: bool = False
    off_grid: bool = False
    off_grid_simulated: bool = False  # get_grid_status offgridSet=1 (user opened contactor)
    off_grid_permanent: bool = False  # get_device_info offGirdFlag (no utility service)
    off_grid_reason: int = 0          # runtimeData offgridreason (detected outage)
    mppt_enabled: bool = False
    three_phase: bool = False
    ct_split_grid: bool = False
    ct_split_pv: bool = False
    v2l_enabled: bool = False
    v2l_eligible: bool = False
    v2l_note: str = ""           # "V1 SC needs Generator Module"
    generator_enabled: bool = False
    remote_solar: bool = False   # aPBox
    # Programmes
    sgip: bool = False
    bb: bool = False             # Hawaii Battery Bonus
    ja12: bool = False
    sdcp: bool = False
    vpp_enrolled: bool = False
    nem_type: str = ""           # "NEM 2.0", "NEM 3.0", "No NEM"
    ahub_detected: bool = False
    mac1_detected: bool = False
    charging_power_limited: bool = False
    need_ct_test: bool = False


@dataclass
class GridInfo:
    """Grid limits and entrance flags."""
    connected: bool = True
    pcs_entrance: bool = False
    global_discharge_max_kw: Optional[float] = None
    global_charge_max_kw: Optional[float] = None
    feed_max_kw: Optional[float] = None
    import_max_kw: Optional[float] = None
    peak_demand_max_kw: Optional[float] = None
    feed_max_flag: int = 0
    import_max_flag: int = 0
    bb_discharge_power: Optional[float] = None
    backup_solution: Optional[str] = None


@dataclass
class WarrantyDevice:
    """Per-device warranty detail."""
    serial: str = ""
    model: str = ""
    device_type: int = 0
    expiry: str = ""
    sub_module_expiry: Optional[str] = None


@dataclass
class WarrantyInfo:
    """Warranty and installer details."""
    expiry: str = ""
    throughput_mwh: float = 0.0
    remaining_kwh: float = 0.0
    installer_company: str = ""
    installer_phone: str = ""
    installer_email: str = ""
    support_phone: str = ""
    warranty_link: str = ""
    devices: List[WarrantyDevice] = field(default_factory=list)


@dataclass
class ElectricalInfo:
    """Live electrical measurements."""
    v_l1: Optional[float] = None
    v_l2: Optional[float] = None
    i_l1: Optional[float] = None
    i_l2: Optional[float] = None
    frequency: Optional[float] = None
    relays: Dict[str, bool] = field(default_factory=dict)
    operating_mode: int = 0
    operating_mode_name: str = ""
    run_status: int = 0
    run_status_name: str = ""
    device_status: int = 0
    soc: float = 0.0
    tou_status: int = 0              # TOU backend status (0 = ok)
    tou_dispatch_count: int = 0      # Number of active dispatches


@dataclass
class ProgrammeInfo:
    """VPP/utility programme enrollment."""
    enrolled: bool = False
    program_name: Optional[str] = None
    partner_name: Optional[str] = None
    vpp_soc: float = 20.0
    vpp_min_soc: float = 5.0
    vpp_max_soc: float = 100.0


@dataclass
class DeviceSnapshot:
    """Complete device discovery snapshot.

    Returned by client.discover(). Contains all static and semi-static
    device information organized by category.
    """
    tier: int = 1                # Tier that was requested
    timestamp: str = ""          # When this snapshot was taken

    site: SiteInfo = field(default_factory=SiteInfo)
    agate: AgateInfo = field(default_factory=AgateInfo)
    batteries: BatteryInfo = field(default_factory=BatteryInfo)
    flags: FeatureFlags = field(default_factory=FeatureFlags)
    accessories: AccessoriesInfo = field(default_factory=AccessoriesInfo)
    grid: GridInfo = field(default_factory=GridInfo)
    warranty: WarrantyInfo = field(default_factory=WarrantyInfo)
    electrical: ElectricalInfo = field(default_factory=ElectricalInfo)
    programmes: ProgrammeInfo = field(default_factory=ProgrammeInfo)
    region_quirks: dict = field(default_factory=dict)
    accessory_quirks: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to dict for JSON output."""
        from dataclasses import asdict
        return asdict(self)
