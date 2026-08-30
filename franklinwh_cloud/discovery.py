"""Device discovery snapshot — structured result from client.discover().

Provides a DeviceSnapshot dataclass that any Python client can use.
The CLI discover command renders this; FEM and user scripts can also consume it.

Feature: FEAT-CLI-DISCOVER-VERBOSE
"""

# Lazy annotations (PEP 563): `get_resolved_capabilities` is annotated `-> ResolvedCapabilities`
# but imports that name inside its body — on Python < 3.14 (e.g. the bridge's 3.12 container)
# eager annotation evaluation raised NameError at import. Strings-only annotations fix it.
from __future__ import annotations

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
    # Both are 0-100 quality percentages, NOT dBm. Verified over 20,471 samples
    # in the HAR corpus: runtimeData.wifiSignal spans 0-100 (always even),
    # runtimeData.signal spans 0-99. Neither is ever negative.
    # NOTE: commSetPara.operatorRSSI (317) and 4GSignalStrength (339) are a
    # DIFFERENT, narrower vendor scale (observed 0-52) — do not mix them in.
    wifi_signal: int = 0         # 0-100 %
    mobile_signal: int = 0       # 0-100 %
    # Firmware versions (Tier 3)
    ibg_version: str = ""
    sl_version: str = ""
    aws_version: str = ""
    app_version: str = ""
    meter_version: str = ""
    # MAC-1 / MSA detection
    msa_model: Optional[str] = None
    msa_serial: Optional[str] = None
    ad_module_hd_ver: Optional[str] = None
    ad_module_app_ver: Optional[str] = None
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
    # Operational states
    bms_state: str = ""
    pcs_state: str = ""


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
    version: int = 1             # 1 or 2
    merged: bool = False         # SwMerge — SC1+SC2 merged
    names: List[str] = field(default_factory=list)
    modes: List[str] = field(default_factory=list)
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
    apbox_di: List[str] = field(default_factory=list)
    apbox_do_status: List[str] = field(default_factory=list)
    generator_state: str = ""
    v2l_state: str = ""


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
    # From getGatewayTouListV2 showType=1 — only supported modes returned
    # Each entry: {id, name, workMode, soc, minSoc, maxSoc, editSocFlag,
    #   socExceedTimerEndTime, complianceSoc, delayMinutes, energyIncentivesType}
    supported_modes: List[dict] = field(default_factory=list)


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


def get_catalog() -> dict:
    """Load device catalog JSON (cached at module level)."""
    from importlib.resources import files as pkg_files
    import json
    catalog_path = pkg_files("franklinwh_cloud.const").joinpath("device_catalog.json")
    with open(str(catalog_path), "r", encoding="utf-8") as f:
        return json.load(f)


def compile_capabilities(
    entrance_data: dict,
    device_data: dict,
    accessories_data: dict,
    vpp_data: dict | None = None
) -> ResolvedCapabilities:
    """Resolve and compile gateway capabilities, applying regional overrides."""
    from .models import ResolvedCapabilities

    ent_res = entrance_data.get("result", entrance_data) if isinstance(entrance_data, dict) else {}
    dev_res = device_data.get("result", device_data) if isinstance(device_data, dict) else {}
    acc_res = accessories_data.get("result", accessories_data) if isinstance(accessories_data, dict) else []
    if not isinstance(acc_res, list):
        acc_res = []

    vpp_res = vpp_data.get("result", vpp_data) if isinstance(vpp_data, dict) else {}

    # Identity
    country_id = dev_res.get("countryId") or ent_res.get("countryId") or 0
    gateway_id = dev_res.get("gatewayId") or dev_res.get("fhpSn") or ""
    
    # Resolve Agate Generation
    hw_ver = str(dev_res.get("sysHdVersion", "100"))
    try:
        catalog = get_catalog()
        model_info = ((catalog.get("agate_models") or {}).get(hw_ver) or {})
        agate_generation = model_info.get("generation", 1)
    except Exception:
        agate_generation = 1

    # Solar
    pv1_installed = (str(dev_res.get("installPv1Port")) == "1" or str(ent_res.get("pv1Port")) == "1")
    pv2_installed = (str(dev_res.get("installPv2Port")) == "1" or str(ent_res.get("pv2Port")) == "1")
    solar_installed = bool(ent_res.get("solarFlag", False)) or pv1_installed or pv2_installed
    has_mppt = bool(dev_res.get("mpptEnFlag", False))
    has_apbox = int(dev_res.get("apbox20Num", 0)) > 0

    # Accessories
    has_smart_circuits = any(item.get("accessoryType") == 4 for item in acc_res)
    has_generator = any(item.get("accessoryType") == 3 for item in acc_res) or bool(dev_res.get("genEn", 0))

    # Grid
    grid_connected = bool(ent_res.get("gridFlag", True)) and not bool(dev_res.get("offGirdFlag", False))
    three_phase = str(dev_res.get("isThreePhaseInstall")) == "1"

    # Pricing & VPP
    tariff_configured = bool(ent_res.get("tariffSettingFlag", False))

    # Apply Regional Quirks & Locks
    if country_id == 3:  # Australia (AU)
        has_v2l = False
        circuit_count = 2
    else:  # US/Other
        has_v2l = bool(dev_res.get("v2lModeEnable", False))
        circuit_count = 2 if agate_generation == 1 else 3

    if not grid_connected:
        vpp_eligible = False
    else:
        vpp_eligible = bool(vpp_res.get("isVppEligible", False))

    return ResolvedCapabilities(
        country_id=country_id,
        agate_generation=agate_generation,
        gateway_id=gateway_id,
        solar_installed=solar_installed,
        pv1_installed=pv1_installed,
        pv2_installed=pv2_installed,
        has_mppt=has_mppt,
        has_apbox=has_apbox,
        has_smart_circuits=has_smart_circuits,
        circuit_count=circuit_count,
        has_generator=has_generator,
        has_v2l=has_v2l,
        grid_connected=grid_connected,
        three_phase=three_phase,
        vpp_eligible=vpp_eligible,
        tariff_configured=tariff_configured,
    )

