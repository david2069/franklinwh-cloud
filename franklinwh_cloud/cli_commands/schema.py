"""schema command — display the Current/Totals dataclass field schema.

Shows every field in franklinwh_cloud.models.Current and Totals with:
  - Python attribute name
  - Raw API JSON key (from runtimeData / cmdType 203 / 311 / 211)
  - Source (which cmdType / endpoint provides this field)
  - Units (kW, kWh, V, A, Hz, %, °C, etc.)
  - Live value (optional, with --live flag requiring login)

Usage:
    franklinwh-cli schema                  # show field schema (no login needed)
    franklinwh-cli schema --live           # schema + live values (calls get_stats(include_electrical=True))
    franklinwh-cli schema --live --json    # JSON output
    franklinwh-cli schema --filter power   # filter to power-flow fields only
"""

import dataclasses
import inspect
import re

from franklinwh_cloud.cli_output import (
    print_header, print_section, print_kv, print_json_output,
)
from franklinwh_cloud.models import Current, Totals, GridConnectionState

# ── Field registry ─────────────────────────────────────────────────────────────
# Manually maintained in sync with models.py inline comments.
# Format: field_name -> (raw_api_key, source, units, group)
#   source: "203" = cmdType 203 runtimeData, "211" = cmdType 211 (electrical, opt-in),
#           "311" = cmdType 311 (smart circuits), "derived" = computed by library
#   group:  display section label

# ── Network inventory ──────────────────────────────────────────────────────────
# Capabilities and settings exposed by get_network_state(), which composes
# cmdType 317 (interface config), 339 (reachability) and 341 (enable switches)
# plus a REST lookup for SIM state.
#
# Deliberately separate from CURRENT_SCHEMA: these are not Current dataclass
# fields, and the per-interface records are a repeating shape rather than flat
# attributes.

NETWORK_SCHEMA = {
    # Active transport — what the aGate has selected for ITSELF (see below)
    "active.id":              ("currentNetType",          "317/commSetPara", "int",  "Network Active"),
    "active.label":           ("NETWORK_TYPES[id]",       "derived",         "str",  "Network Active"),
    "active.ip":              ("<iface>StaticIP",         "317/commSetPara", "ipv4", "Network Active"),
    "active.gateway":         ("<iface>GateWay",          "317/commSetPara", "ipv4", "Network Active"),
    "active.dns":             ("<iface>DNS",              "317/commSetPara", "ipv4", "Network Active"),
    "active.selection":       ("always 'device-managed'", "derived",         "str",  "Network Active"),

    # Per-interface record — repeated for eth0, eth1, wifi, 4g
    "interfaces[].enabled":   ("<x>NetSwitch",            "341",             "bool", "Network Interfaces"),
    "interfaces[].link":      ("<x>ConnectRouterStatus",  "339 (extended)",  "bool", "Network Interfaces"),
    "interfaces[].ip":        ("<x>StaticIP",             "317/commSetPara", "ipv4", "Network Interfaces"),
    "interfaces[].dhcp":      ("<x>DHCP",                 "317/commSetPara", "bool", "Network Interfaces"),
    "interfaces[].mac":       ("<x>MAC",                  "317/commSetPara", "str",  "Network Interfaces"),
    "interfaces[].is_active": ("id == currentNetType",    "derived",         "bool", "Network Interfaces"),
    "interfaces[].available": ("see availability rule",   "derived",         "bool", "Network Interfaces"),

    # Signal — note the two scales are NOT the same unit
    "interfaces[wifi].signal_pct":     ("WifiSignalStrength", "339 (extended)",  "%",   "Network Signal"),
    "interfaces[4g].signal_raw":       ("operatorRSSI",       "317/commSetPara", "0-52", "Network Signal"),
    "interfaces[4g].sim_status":       ("simCardStatus",      "getHomeGatewayList", "int", "Network Signal"),
    "interfaces[4g].sim_status_name":  ("SIM_STATUS[status]", "derived",         "str",  "Network Signal"),

    # Cloud reachability
    "cloud.aws_connected":    ("awsStatus == 1",          "339",             "bool", "Network Cloud"),
    "cloud.internet":         ("netStatus == 1",          "339",             "bool", "Network Cloud"),
    "cloud.router_status_raw":("routerStatus",            "339",             "code", "Network Cloud"),

    # Derived roll-ups used for write safety
    "linked_transports":      ("derived",                 "derived",         "list", "Network Summary"),
    "available_transports":   ("derived",                 "derived",         "list", "Network Summary"),
    "redundant":              ("len(available) > 1",      "derived",         "bool", "Network Summary"),
    "source.extended_339":    ("derived",                 "derived",         "bool", "Network Summary"),
}

# Availability rule, printed alongside the inventory so the semantics travel
# with the data. See docs/NETWORK_CONNECTIVITY_DESIGN.md section 3.
NETWORK_NOTES = [
    "active is the transport the aGate selected for ITSELF, not a configured",
    "  primary — it re-selects autonomously and returns to the preferred link.",
    "available = would this carry traffic if the one in use stopped?",
    "  4G       : enabled + SIM Active + reception (holds no IP while idle)",
    "  WiFi/Eth : enabled + linked + holding an address (static or DHCP)",
    "signal_pct (WiFi) is 0-100%; signal_raw (4G) is a 0-52 vendor scale.",
    "routerStatus is NOT a boolean — 0, 1 and 4 all observed. Shown raw.",
]


CURRENT_SCHEMA = {
    # Power flow
    "solar_production":         ("p_sun",              "203/runtimeData",  "kW",    "Power Flow"),
    "generator_production":     ("p_gen",              "203/runtimeData",  "kW",    "Power Flow"),
    "battery_use":              ("p_fhp",              "203/runtimeData",  "kW",    "Power Flow"),
    "grid_use":                 ("p_uti",              "203/runtimeData",  "kW",    "Power Flow"),
    "home_load":                ("p_load",             "203/runtimeData",  "kW",    "Power Flow"),
    "battery_soc":              ("soc",                "203/runtimeData",  "%",     "Power Flow"),
    "switch_1_load":            ("pro_load_pwr[0]",    "311/sw_data",      "kW",    "Power Flow"),
    "switch_2_load":            ("pro_load_pwr[1]",    "311/sw_data",      "kW",    "Power Flow"),
    "v2l_use":                  ("CarSWPower",         "311/sw_data",      "kW",    "Power Flow"),
    # Grid state
    "grid_connection_state":    ("derived",            "derived",          "enum",  "Grid State"),
    # Operating mode
    "work_mode":                ("currentWorkMode",    "203/result",       "int",   "Mode"),
    "work_mode_desc":           ("derived",            "derived",          "str",   "Mode"),
    "device_status":            ("deviceStatus",       "203/result",       "int",   "Mode"),
    "tou_mode":                 ("mode",               "203/runtimeData",  "int",   "Mode"),
    "tou_mode_desc":            ("name",               "203/runtimeData",  "str",   "Mode"),
    "run_status":               ("run_status",         "203/runtimeData",  "int",   "Mode"),
    "run_status_desc":          ("RUN_STATUS[run_status]", "derived",      "str",   "Mode"),  # runtimeData.run_status — NOT runtimeData.mode
    "effective_mode":           ("derived",            "derived",          "str",   "Mode"),
    # Battery pack telemetry
    "apower_serial_numbers":    ("fhpSn",              "203/runtimeData",  "list",  "Battery Packs"),
    "apower_soc":               ("fhpSoc",             "203/runtimeData",  "list",  "Battery Packs"),
    "apower_power":             ("fhpPower",           "203/runtimeData",  "list",  "Battery Packs"),
    "apower_bms_mode":          ("bms_work",           "203/runtimeData",  "list",  "Battery Packs"),
    # Environment
    "agate_ambient_temparture": ("t_amb",              "203/runtimeData",  "°C",   "Environment"),
    # Primary relays
    "grid_relay1":              ("main_sw[0]",         "203/runtimeData",  "relay", "Relays"),
    "generator_relay":          ("main_sw[1]",         "203/runtimeData",  "relay", "Relays"),
    "solar_relay1":             ("main_sw[2]",         "203/runtimeData",  "relay", "Relays"),
    # Connectivity
    "mobile_signal":            ("signal",             "203/runtimeData",  "%",     "Connectivity"),
    "wifi_signal":              ("wifiSignal",         "203/runtimeData",  "%",     "Connectivity"),
    "network_connection":       ("connType",           "203/runtimeData",  "int",   "Connectivity"),
    # V2L
    "v2l_enabled":              ("v2lModeEnable",       "203/runtimeData",  "bool",  "V2L"),  # US only, off-grid only
    "v2l_status":               ("v2lRunState",         "203/runtimeData",  "int",   "V2L"),
    # Generator
    "generator_enabled":        ("genEn",               "203/runtimeData",  "bool",  "Generator"),  # off-grid only
    "generator_status":         ("genStat",             "203/runtimeData",  "int",   "Generator"),
    # Power flow breakdown
    "grid_charging_battery":    ("gridChBat",          "203/runtimeData",  "kW",    "Power Flow"),
    "solar_export_to_grid":     ("soOutGrid",          "203/runtimeData",  "kW",    "Power Flow"),
    "solar_charging_battery":   ("soChBat",            "203/runtimeData",  "kW",    "Power Flow"),
    "battery_export_to_grid":   ("batOutGrid",         "203/runtimeData",  "kW",    "Power Flow"),
    # APbox / MPPT
    "apbox_remote_solar":       ("apbox20Pv",          "203/runtimeData",  "kW",    "APbox/MPPT"),
    "remote_solar_enabled":     ("remoteSolarEn",       "203/runtimeData",  "bool",  "APbox/MPPT"),
    "remote_solar_mode":        ("remoteSolarMode",     "solarHaveVo",      "int",   "APbox/MPPT"),
    "mppt_status":              ("mpptSta",             "203/runtimeData",  "int",   "APbox/MPPT"),
    "mppt_all_power":           ("mpptAllPower",        "203/runtimeData",  "kW",    "APbox/MPPT"),
    "mppt_active_power":        ("mpptActPower",        "203/runtimeData",  "kW",    "APbox/MPPT"),
    "mpan_pv1_power":           ("mPanPv1Power",        "203/runtimeData",  "kW",    "APbox/MPPT"),
    "mpan_pv2_power":           ("mPanPv2Power",        "203/runtimeData",  "kW",    "APbox/MPPT"),
    "remote_solar_pv1":         ("remoteSolar1Power",  "203/runtimeData",  "kW",    "APbox/MPPT"),
    "remote_solar_pv2":         ("remoteSolar2Power",  "203/runtimeData",  "kW",    "APbox/MPPT"),
    # APbox / MPPT config flags (NOT relays — firmware enable booleans)
    "mppt_en_flag":             ("mpptEnFlag",          "203/runtimeData",  "bool",  "APbox/MPPT Flags"),
    "mppt_export_en":           ("mpptExportEn",        "203/runtimeData",  "bool",  "APbox/MPPT Flags"),
    "install_pv1_port":         ("installPv1Port",      "203/runtimeData",  "0/1",   "APbox/MPPT Flags"),
    "install_pv2_port":         ("installPv2Port",      "203/runtimeData",  "0/1",   "APbox/MPPT Flags"),
    # Hardware install config (static site topology — set at install, rarely changes)
    "pv_split_ct_en":           ("pvSplitCtEn",         "203/runtimeData",  "0/1",   "Hardware Config"),
    "grid_split_ct_en":         ("gridSplitCtEn",       "203/runtimeData",  "0/1",   "Hardware Config"),
    "install_proximal_solar":   ("installProximalsolar","203/runtimeData",  "0/1",   "Hardware Config"),
    "is_three_phase_install":   ("isThreePhaseInstall", "203/runtimeData",  "0/1",   "Hardware Config"),
    # Alarms
    "alarms_count":             ("currentAlarmVOList", "203/result",       "count", "Alarms"),
    # Extended relays (cmdType 211 — opt-in)
    "grid_relay2":              ("gridRelayStat",      "211/result",       "relay", "Extended Relays (211)"),
    "black_start_relay":        ("bFpVApboxRelay",     "211/result",       "relay", "Extended Relays (211)"),
    "pv_relay2":                ("pvRelay2",           "211/result",       "relay", "Extended Relays (211)"),
    "bfpv_apbox_relay":         ("BFPVApboxRelay",     "211/result",       "relay", "Extended Relays (211)"),
    # Load & EV relays (cmdType 211 — opt-in) — APBox smart-circuit / V2L contactors
    "load_relay1":              ("loadRelay1Stat",     "211/result",       "relay", "Load & V2L Relays (211)"),
    "load_relay2":              ("loadRelay2Stat",     "211/result",       "relay", "Load & V2L Relays (211)"),
    "v2l_relay":                 ("evRelayStat",        "211/result",       "relay", "Load & V2L Relays (211)"),  # V2L contactor only u2014 NOT EVSE
    "load_solar_relay1":        ("loadSolarRelay1Stat","211/result",       "relay", "Load & V2L Relays (211)"),
    "load_solar_relay2":        ("loadSolarRelay2Stat","211/result",       "relay", "Load & V2L Relays (211)"),
    # Electrical measurements (cmdType 211 — opt-in) — matches --filter power
    "grid_voltage1":            ("gridVol1",           "211/result",       "V",     "Power Measurements (211)"),
    "grid_voltage2":            ("gridVol2",           "211/result",       "V",     "Power Measurements (211)"),
    "grid_current1":            ("gridCurr1",          "211/result",       "A",     "Power Measurements (211)"),
    "grid_current2":            ("gridCurr2",          "211/result",       "A",     "Power Measurements (211)"),
    "load_current1":            ("loadCurr1",          "211/result",       "A",     "Power Measurements (211)"),
    "load_current2":            ("loadCurr2",          "211/result",       "A",     "Power Measurements (211)"),
    "grid_frequency":           ("gridFreq",           "211/result",       "Hz",    "Power Measurements (211)"),
    "grid_set_frequency":       ("dspSetFreq",         "211/result",       "Hz",    "Power Measurements (211)"),
    "grid_line_voltage":        ("gridLineVol÷10",     "211/result",       "V",     "Power Measurements (211)"),
    "generator_voltage":        ("genVoltage",         "211/result",       "V",     "Power Measurements (211)"),
    "dsp_run_status":           ("dspRunStatus",       "211/result",       "int",   "Power Measurements (211)"),
    "ibg_run_status":           ("ibgRunStatus",       "211/result",       "int",   "Power Measurements (211)"),
    "electricity_type":         ("electricity_type",   "211/result",       "int",   "Power Measurements (211)"),
    # TOU window (derived from get_tou_info)
    "active_tou_name":          ("derived",            "get_tou_info",     "str",   "TOU Window"),
    "active_tou_dispatch":      ("derived",            "get_tou_info",     "str",   "TOU Window"),
    "active_tou_dispatch_id":   ("derived",            "get_tou_info",     "int",   "TOU Window"),
    "active_tou_wave_type":     ("derived",            "get_tou_info",     "int",   "TOU Window"),
    "active_tou_wave_type_desc":("derived",            "get_tou_info",     "str",   "TOU Window"),
    "active_tou_start":         ("derived",            "get_tou_info",     "HH:MM", "TOU Window"),
    "active_tou_end":           ("derived",            "get_tou_info",     "HH:MM", "TOU Window"),
    "active_tou_remaining":     ("derived",            "get_tou_info",     "str",   "TOU Window"),
    # Smart circuits (cmdType 311)
    "switch_1_state":           ("pro_load[0]",        "311/runtimeData",  "0/1",   "Smart Circuits"),
    "switch_2_state":           ("pro_load[1]",        "311/runtimeData",  "0/1",   "Smart Circuits"),
    "switch_3_state":           ("pro_load[2]",        "311/runtimeData",  "0/1",   "Smart Circuits"),
}

TOTALS_SCHEMA = {
    "battery_charge":       ("kwh_fhp_chg",      "203/runtimeData",  "kWh",  "Battery"),
    "battery_discharge":    ("kwh_fhp_di",        "203/runtimeData",  "kWh",  "Battery"),
    "grid_import":          ("kwh_uti_in",         "203/runtimeData",  "kWh",  "Grid"),
    "grid_export":          ("kwh_uti_out",        "203/runtimeData",  "kWh",  "Grid"),
    "solar":                ("kwh_sun",            "203/runtimeData",  "kWh",  "Generation"),
    "generator":            ("kwh_gen",            "203/runtimeData",  "kWh",  "Generation"),
    "home_use":             ("kwh_load",           "203/runtimeData",  "kWh",  "Generation"),
    "switch_1_use":         ("SW1ExpEnergy",       "311/sw_data",      "kWh",  "Smart Circuits"),
    "switch_2_use":         ("SW2ExpEnergy",       "311/sw_data",      "kWh",  "Smart Circuits"),
    "v2l_export":           ("CarSWExpEnergy",     "311/sw_data",      "kWh",  "V2L"),
    "v2l_import":           ("CarSWImpEnergy",     "311/sw_data",      "kWh",  "V2L"),
    "solar_load_kwh":       ("kwhSolarLoad",       "203/runtimeData",  "kWh",  "Load Breakdown"),
    "grid_load_kwh":        ("kwhGridLoad",        "203/runtimeData",  "kWh",  "Load Breakdown"),
    "battery_load_kwh":     ("kwhFhpLoad",         "203/runtimeData",  "kWh",  "Load Breakdown"),
    "generator_load_kwh":   ("kwhGenLoad",         "203/runtimeData",  "kWh",  "Load Breakdown"),
    "mpan_pv1_wh":          ("mpanPv1Wh",          "203/runtimeData",  "Wh",   "APbox/MPPT"),
    "mpan_pv2_wh":          ("mpanPv2Wh",          "203/runtimeData",  "Wh",   "APbox/MPPT"),
}

# ── Grid Power Control Settings ─────────────────────────────────────────────
# Source: get_power_control_settings()  (REST — not MQTT/cmdType)
# Encoding: -1 = Unlimited, 0 = Not allowed/Disabled, >0 = kW power cap
GRID_LIMITS_SCHEMA = {
    "globalGridChargeMax":      ("globalGridChargeMax",      "get_power_control_settings", "kW / -1", "Global Limits"),
    "globalGridDischargeMax":   ("globalGridDischargeMax",   "get_power_control_settings", "kW / -1", "Global Limits"),
    "globalSettingStatus":      ("globalSettingStatus",      "get_power_control_settings", "int",     "Global Limits"),
    "gridFeedMax":              ("gridFeedMax",              "get_power_control_settings", "kW / -1", "Feed-In (Export)"),
    "gridFeedMaxFlag":          ("gridFeedMaxFlag",          "get_power_control_settings", "int",     "Feed-In (Export)"),
    "gridMax":                  ("gridMax",                  "get_power_control_settings", "kW / -1", "Import"),
    "gridMaxFlag":              ("gridMaxFlag",              "get_power_control_settings", "int",     "Import"),
    "gridFlag":                 ("gridFlag",                 "get_power_control_settings", "bool",    "Grid Connection"),
    "solarFlag":                ("solarFlag",                "get_power_control_settings", "bool",    "Grid Connection"),
    "notControlExportSolar":    ("notControlExportSolar",    "get_power_control_settings", "bool",    "Feed-In (Export)"),
    "peakDemandGridMax":        ("peakDemandGridMax",        "get_power_control_settings", "kW / -1", "Peak Demand"),
    "bbDischargePower":         ("bbDischargePower",         "get_power_control_settings", "kW",      "Backup Battery"),
    "sgipFlag":                 ("sgipFlag",                 "get_power_control_settings", "0/1",     "Programmes"),
    "itcFlag":                  ("itcFlag",                  "get_power_control_settings", "0/1",     "Programmes"),
    "isNem3":                   ("isNem3",                   "get_power_control_settings", "0/1",     "Programmes"),
    "isCalifornia":             ("isCalifornia",             "get_power_control_settings", "0/1",     "Programmes"),
}

TOU_SCHEMA = {
    "startHourTime":        ("startHourTime",      "setTouSchedule",   "HH:MM", "Time Block"),
    "endHourTime":          ("endHourTime",        "setTouSchedule",   "HH:MM", "Time Block"),
    "name":                 ("name",               "getTouList",       "str",   "Configuration"),
    "dispatchId":           ("dispatchId",         "setTouSchedule",   "int",   "Configuration"),
    "waveType":             ("waveType",           "setTouSchedule",   "int",   "Tariff/Pricing"),
    "targetSoc":            ("targetSoc",          "setTouSchedule",   "int",   "Configuration"),
}

MODE_SCHEMA = {
    "soc":                  ("soc",                "getTouList",       "float", "SOC Limits"),
    "maxSoc":               ("maxSoc",             "getTouList",       "float", "SOC Limits"),
    "minSoc":               ("minSoc",             "getTouList",       "float", "SOC Limits"),
    "dischargeDepthSoc":    ("dischargeDepthSoc",  "getTouList",       "float", "SOC Limits"),
    "complianceSoc":        ("complianceSoc",      "getTouList",       "float", "SOC Limits"),
}


def _fmt_value(val) -> str:
    """Format a live value for display."""
    if val is None:
        return "—"
    if isinstance(val, GridConnectionState):
        return val.value
    if isinstance(val, float):
        return f"{val:.2f}"
    if isinstance(val, (list, tuple)):
        return str(val)
    return str(val)


def network_health(state):
    """Derive connectivity findings from a get_network_state() snapshot.

    The API exposes no connection-attempt history — selectDeviceRunLogList is a
    static alarm-code dictionary, not an event log — so health has to be derived
    from current state. Continuous history requires client-side polling; see
    ``tools/network_probe.py observe``.

    Returns a list of ``{level, code, detail}`` dicts, most severe first.
    """
    findings = []
    ifaces = {i["key"]: i for i in (state.get("interfaces") or [])}
    available = (state.get("available_transports") or [])

    wifi = (ifaces.get("wifi") or {})
    if wifi.get("enabled") and wifi.get("signal_pct") and not wifi.get("ip"):
        findings.append({
            "level": "WARN", "code": "wifi_no_lease",
            "detail": f"WiFi associated at {wifi['signal_pct']}% but holding no address "
                      f"— no DHCP lease. This is the 2026-03-21 failure mode.",
        })

    cell = (ifaces.get("4g") or {})
    if cell.get("enabled") and cell.get("sim_status") not in (None, 2):
        findings.append({
            "level": "WARN", "code": "sim_not_active",
            "detail": f"SIM reports {cell.get('sim_status_name')!r} — cellular is not a "
                      f"usable fallback even with reception.",
        })
    if cell.get("enabled") and not cell.get("signal_raw"):
        findings.append({
            "level": "WARN", "code": "no_cellular_reception",
            "detail": "4G enabled but reception is 0 — the out-of-the-box fallback is unavailable.",
        })
    if not cell.get("enabled"):
        findings.append({
            "level": "WARN", "code": "cellular_disabled",
            "detail": "4GNetSwitch is off. The aGate cannot fall back to cellular, so a "
                      "failed network change would need on-site recovery.",
        })

    if not state.get("redundant"):
        findings.append({
            "level": "WARN", "code": "no_redundancy",
            "detail": f"Only {available or 'nothing'} can carry traffic. Any network write "
                      f"targeting it risks stranding the gateway.",
        })

    # DEF-ETH-LINK-SHARED-FLAG: firmware reports ONE Ethernet link status for
    # both ports, so these two findings are not independent observations. Say
    # so, and lean on the per-port address, which the firmware does report
    # separately.
    for key in ("eth0", "eth1"):
        e = (ifaces.get(key) or {})
        if e.get("enabled") and not e.get("link") and not e.get("ip"):
            shared = " The Ethernet link flag is shared by both ports (firmware " \
                     "reports one status for the pair), so this rests on the " \
                     "per-port address." if e.get("link_shared") else ""
            findings.append({
                "level": "INFO", "code": f"{key}_no_link",
                "detail": f"{key} is enabled but has no link and no address — cable "
                          f"likely unplugged. Not counted as a fallback.{shared}",
            })

    cloud = (state.get("cloud") or {})
    if not cloud.get("aws_connected"):
        # Surface the disagreement between the two self-reports rather than
        # just the one. DEF-AWS-STATUS-SOURCE.
        raw_339 = cloud.get("aws_status_339_raw")
        raw_317 = cloud.get("aws_status_317_raw")
        detail = (
            f"cmdType 339 reports awsStatus={raw_339}, yet this data arrived through "
            f"the cloud. These flags have been observed contradicting reality — do "
            f"not gate anything on them."
        )
        if raw_317 is not None and raw_317 != raw_339:
            detail += (
                f" cmdType 317 reports awsStatus={raw_317} for the same gateway at "
                f"the same moment, and it is the one matching observable reality. "
                f"Use round-trip success, not either flag."
            )
        findings.append({
            "level": "INFO", "code": "cloud_flags_unreliable", "detail": detail,
        })

    order = {"WARN": 0, "INFO": 1}
    findings.sort(key=lambda f: order.get(f["level"], 9))
    return findings


async def run(client, json_output: bool = False, show_live: bool = False,
              filter_group: str | None = None):
    """Display the Current/Totals field schema, optionally with live values."""

    live_current = None
    live_totals = None

    if show_live:
        try:
            stats = await client.get_stats(include_electrical=True)
            live_current = dataclasses.asdict(stats.current)
            # Enum values aren't serialisable by asdict — convert manually
            live_current["grid_connection_state"] = stats.current.grid_connection_state.value
            
            # Formally populate active_tou fields on-the-fly for schema validation
            if True:  # Only if in TOU mode
                try:
                    tou = await client.get_tou_info(1)  # Fetch current/next
                    if tou:
                        live_current["active_tou_name"] = tou.get("activeTOUname", "")
                        live_current["active_tou_dispatch"] = tou.get("activeTOUtitle", "")
                        live_current["active_tou_dispatch_id"] = tou.get("activeTOUdispatchId")
                        wt = tou.get("activeWaveType")
                        live_current["active_tou_wave_type"] = wt
                        from franklinwh_cloud.const.tou import WAVE_TYPES
                        live_current["active_tou_wave_type_desc"] = WAVE_TYPES.get(wt, "")
                        live_current["active_tou_start"] = tou.get("activeStartTime", "")
                        live_current["active_tou_end"] = tou.get("activeEndTime", "")
                        rem = tou.get("activeRemainingTime", "")
                        if rem and ":" in rem:
                            h, m = rem.split(":")
                            live_current["active_tou_remaining"] = f"{int(h)}h {int(m)}m"
                except Exception:
                    pass

            live_totals = dataclasses.asdict(stats.totals)
        except Exception as e:
            if not json_output:
                print(f"⚠ Could not fetch live data: {e}")

    # Grid limits — fetched independently (REST, not MQTT)
    live_grid_limits = None
    if show_live:
        try:
            pcs_res = await client.get_power_control_settings()
            live_grid_limits = (pcs_res.get("result") or {}) if isinstance(pcs_res, dict) else {}
        except Exception as e:
            if not json_output:
                print(f"⚠ Could not fetch grid limits: {e}")

    # Network inventory — composed from cmdType 317/339/341 plus a REST SIM lookup,
    # so it is fetched separately from the 203-based Current snapshot.
    live_network = None
    if show_live:
        try:
            live_network = await client.get_network_state()
        except Exception as e:
            if not json_output:
                print(f"⚠ Could not fetch network state: {e}")

    if json_output:
        _json_output(live_current, live_totals, live_grid_limits, filter_group,
                     live_network)
        return

    _terminal_output(live_current, live_totals, live_grid_limits, filter_group,
                     live_network)


def _json_output(live_current, live_totals, live_grid_limits, filter_group,
                 live_network=None):
    """Emit JSON schema output."""
    result = {"current": {}, "totals": {}, "grid_limits": {}}

    for field, (api_key, source, units, group) in CURRENT_SCHEMA.items():
        if filter_group and filter_group.lower() not in group.lower():
            continue
        entry = {"api_key": api_key, "source": source, "units": units, "group": group}
        if live_current is not None:
            entry["live_value"] = live_current.get(field)
        result["current"][field] = entry

    for field, (api_key, source, units, group) in TOTALS_SCHEMA.items():
        if filter_group and filter_group.lower() not in group.lower():
            continue
        entry = {"api_key": api_key, "source": source, "units": units, "group": group}
        if live_totals is not None:
            entry["live_value"] = live_totals.get(field)
        result["totals"][field] = entry

    for field, (api_key, source, units, group) in GRID_LIMITS_SCHEMA.items():
        if filter_group and filter_group.lower() not in group.lower() and (filter_group.lower() not in "grid"):
            continue
        entry = {"api_key": api_key, "source": source, "units": units, "group": group}
        if live_grid_limits is not None:
            entry["live_value"] = live_grid_limits.get(api_key)
        result["grid_limits"][field] = entry

    result["tou"] = {}
    for field, (api_key, source, units, group) in TOU_SCHEMA.items():
        if filter_group and filter_group.lower() not in group.lower() and filter_group.lower() != "tou":
            continue
        entry = {"api_key": api_key, "source": source, "units": units, "group": group}
        if live_current is not None:
            val = None
            if field == "startHourTime": val = live_current.get("active_tou_start")
            elif field == "endHourTime": val = live_current.get("active_tou_end")
            elif field == "name": val = live_current.get("active_tou_name")
            elif field == "dispatchId": val = live_current.get("active_tou_dispatch_id")
            elif field == "waveType": val = live_current.get("active_tou_wave_type")
            entry["live_value"] = val
        result["tou"][field] = entry

    result["mode"] = {}
    for field, (api_key, source, units, group) in MODE_SCHEMA.items():
        if filter_group and filter_group.lower() not in group.lower() and filter_group.lower() != "mode":
            continue
        entry = {"api_key": api_key, "source": source, "units": units, "group": group}
        result["mode"][field] = entry

    result["network"] = {}
    for field, (api_key, source, units, group) in NETWORK_SCHEMA.items():
        if filter_group and filter_group.lower() not in group.lower() \
                and filter_group.lower() != "network":
            continue
        result["network"][field] = {
            "api_key": api_key, "source": source, "units": units, "group": group,
        }
    if result["network"]:
        result["network_notes"] = NETWORK_NOTES
    if live_network is not None:
        result["network_state"] = live_network
        result["network_health"] = network_health(live_network)

    print_json_output(result)


def _terminal_output(live_current, live_totals, live_grid_limits, filter_group,
                     live_network=None):
    """Emit human-readable schema table."""
    print_header("API Field Schema — Current & Totals")

    col_field  = 30
    col_key    = 22
    col_src    = 20
    col_units  = 7

    def _header_row():
        h = (f"{'Python Attribute':<{col_field}}  "
             f"{'Raw API Key':<{col_key}}  "
             f"{'Source':<{col_src}}  "
             f"{'Units':<{col_units}}")
        if live_current is not None or live_totals is not None:
            h += "  Live Value"
        return h

    def _divider():
        return "-" * (col_field + col_key + col_src + col_units + 10 +
                      (20 if live_current is not None else 0))

    # ── Current ───────────────────────────────────────────────────────
    print_section("📊", "stats.current  (getDeviceCompositeInfo / cmdType 203)")
    print(_header_row())
    print(_divider())

    current_group = None
    for field, (api_key, source, units, group) in CURRENT_SCHEMA.items():
        if filter_group and filter_group.lower() not in group.lower():
            continue
        if group != current_group:
            print(f"\n  ── {group}")
            current_group = group
        row = (f"  {field:<{col_field}}  "
               f"{api_key:<{col_key}}  "
               f"{source:<{col_src}}  "
               f"{units:<{col_units}}")
        if live_current is not None:
            val = live_current.get(field)
            row += f"  {_fmt_value(val)}"
        print(row)

    # ── Totals ────────────────────────────────────────────────────────
    print()
    print_section("📈", "stats.totals  (getDeviceCompositeInfo / cmdType 203)")
    print(_header_row())
    print(_divider())

    totals_group = None
    for field, (api_key, source, units, group) in TOTALS_SCHEMA.items():
        if filter_group and filter_group.lower() not in group.lower():
            continue
        if group != totals_group:
            print(f"\n  ── {group}")
            totals_group = group
        row = (f"  {field:<{col_field}}  "
               f"{api_key:<{col_key}}  "
               f"{source:<{col_src}}  "
               f"{units:<{col_units}}")
        if live_totals is not None:
            val = live_totals.get(field)
            row += f"  {_fmt_value(val)}"
        print(row)

    # ── Modes ─────────────────────────────────────────────────────────
    mode_filtered = False
    
    # Check if MODE_SCHEMA has any matches for the filter
    for field, (api_key, source, units, group) in MODE_SCHEMA.items():
        if not filter_group or filter_group.lower() in group.lower() or filter_group.lower() == "mode" or filter_group.lower() in "soc":
            mode_filtered = True
            break
            
    if mode_filtered:
        print()
        print_section("⚙️", "Operating Mode Config  (getGatewayTouListV2)")
        print(_header_row())
        print(_divider())

        mode_group = None
        for field, (api_key, source, units, group) in MODE_SCHEMA.items():
            if filter_group and filter_group.lower() not in group.lower() and filter_group.lower() != "mode" and filter_group.lower() not in "soc":
                continue
            if group != mode_group:
                print(f"\n  ── {group}")
                mode_group = group
            row = (f"  {field:<{col_field}}  "
                   f"{api_key:<{col_key}}  "
                   f"{source:<{col_src}}  "
                   f"{units:<{col_units}}")
            # Mode schemas don't currently have a 'live' equivalent from get_stats
            if live_totals is not None:
                row += f"  {_fmt_value(None)}"
            print(row)

    # ── TOU ───────────────────────────────────────────────────────────
    tou_filtered = False
    
    # Check if TOU_SCHEMA has any matches for the filter
    for field, (api_key, source, units, group) in TOU_SCHEMA.items():
        if not filter_group or filter_group.lower() in group.lower() or filter_group.lower() == "tou" or filter_group.lower() in "dispatch":
            tou_filtered = True
            break
            
    if tou_filtered:
        print()
        print_section("📅", "TOU Schedule Blocks  (detailVoList)")
        print(_header_row())
        print(_divider())

        tou_group = None
        for field, (api_key, source, units, group) in TOU_SCHEMA.items():
            if filter_group and filter_group.lower() not in group.lower() and filter_group.lower() != "tou" and filter_group.lower() not in "dispatch":
                continue
            if group != tou_group:
                print(f"\n  ── {group}")
                tou_group = group
            row = (f"  {field:<{col_field}}  "
                   f"{api_key:<{col_key}}  "
                   f"{source:<{col_src}}  "
                   f"{units:<{col_units}}")
            # TOU schemas don't currently have a 'live' equivalent from get_stats
            # We map the active block values extrapolated into live_current
            if live_totals is not None:
                val = None
                if live_current is not None:
                    if field == "startHourTime": val = live_current.get("active_tou_start")
                    elif field == "endHourTime": val = live_current.get("active_tou_end")
                    elif field == "name": val = live_current.get("active_tou_name")
                    elif field == "dispatchId": val = live_current.get("active_tou_dispatch_id")
                    elif field == "waveType": val = live_current.get("active_tou_wave_type")
                row += f"  {_fmt_value(val)}"
            print(row)

    print()
    print("  Relay encoding: 1=OPEN (connected), 0=CLOSED (disconnected)  — all relays")
    print("  cmdType 211 fields only populated when get_stats(include_electrical=True)")
    print("  cmdType 311 fields require Smart Circuit accessory installed")
    print("  kwhSolarLoad / kwhGridLoad / kwhFhpLoad values may be cumulative Wh (not daily kWh)")

    # ── Grid Power Control Limits ─────────────────────────────────────────
    grid_filtered = (
        not filter_group
        or filter_group.lower() in "grid"
        or any(filter_group.lower() in g.lower()
               for _, (_, _, _, g) in GRID_LIMITS_SCHEMA.items())
    )
    if grid_filtered:
        print()
        print_section("⚡", "Grid Power Control Limits  (get_power_control_settings)")
        print("  -1 = Unlimited,  0 = Not allowed/Disabled,  >0 = kW power cap")
        print()
        print(_header_row())
        print(_divider())

        def _decode_limit(val):
            if val is None: return "—"
            try:
                v = float(val)
                if v < 0:  return "Unlimited (-1)"
                if v == 0: return "Not allowed (0)"
                return f"{v:.1f} kW"
            except (TypeError, ValueError):
                return str(val)

        grid_group = None
        for field, (api_key, source, units, group) in GRID_LIMITS_SCHEMA.items():
            if filter_group and filter_group.lower() not in group.lower() and filter_group.lower() not in "grid":
                continue
            if group != grid_group:
                print(f"\n  ── {group}")
                grid_group = group
            row = (f"  {field:<30}  "
                   f"{api_key:<22}  "
                   f"{source:<20}  "
                   f"{units:<7}")
            if live_grid_limits is not None:
                raw = live_grid_limits.get(api_key)
                # Decode kW limit fields; show others as-is
                if "kW" in units:
                    row += f"  {_decode_limit(raw)}"
                else:
                    row += f"  {_fmt_value(raw)}"
            print(row)

    # ── Network inventory ──────────────────────────────────────────────────
    show_network = (not filter_group) or filter_group.lower() == "network" \
        or any(filter_group.lower() in g.lower() for _, _, _, g in NETWORK_SCHEMA.values())

    if show_network:
        print_section("🌐", "Network Capabilities & Settings")
        net_group = None
        for field, (api_key, source, units, group) in NETWORK_SCHEMA.items():
            if filter_group and filter_group.lower() not in group.lower() \
                    and filter_group.lower() != "network":
                continue
            if group != net_group:
                print(f"\n  ── {group}")
                net_group = group
            print(f"  {field:<32}  {api_key:<26}  {source:<20}  {units}")

        print("\n  Semantics:")
        for line in NETWORK_NOTES:
            print(f"    {line}")

        if live_network is not None:
            print_section("📶", "Network — Current State")
            act = (live_network.get("active") or {})
            print(f"  ACTIVE   {act.get('label')}   {act.get('ip') or '—'}"
                  f"   gw {act.get('gateway') or '—'}   ({act.get('selection')})")
            print()
            print(f"  {'iface':<6} {'enabled':<8} {'link':<6} {'active':<7} "
                  f"{'available':<10} {'address':<16} {'addr src':<9} "
                  f"{'signal':<10} note")
            for i in (live_network.get("interfaces") or []):
                sig = ""
                note = ""
                if i["key"] == "wifi" and i.get("signal_pct") is not None:
                    sig = f"{i['signal_pct']}%"
                elif i["key"] == "4g":
                    sig = f"{i.get('signal_raw')}/52" if i.get("signal_raw") else "—"
                    note = f"SIM {i.get('sim_status_name') or 'unknown'}"
                # DEF-SCHEMA-DHCP-NOT-RENDERED. The capability inventory above
                # advertises interfaces[].dhcp, so show it. It reports whether
                # the aGate is a DHCP CLIENT — it says nothing about whether
                # the router holds a reservation for it, which no FranklinWH
                # endpoint exposes. Hence "addr src", not "reserved".
                dhcp = i.get("dhcp")
                addr_src = "—" if dhcp is None else ("dhcp" if dhcp else "static")
                print(f"  {i['key']:<6} {str(i['enabled']):<8} {str(i['link']):<6} "
                      f"{str(i['is_active']):<7} {str(i['available']):<10} "
                      f"{str(i.get('ip') or '—'):<16} {addr_src:<9} "
                      f"{sig:<10} {note}")

            cloud = (live_network.get("cloud") or {})
            print(f"\n  carrying traffic : {live_network.get('linked_transports')}")
            print(f"  available        : {live_network.get('available_transports')}"
                  f"   redundant={live_network.get('redundant')}")
            print(f"  cloud            : aws={cloud.get('aws_connected')} "
                  f"internet={cloud.get('internet')} "
                  f"routerStatus={cloud.get('router_status_raw')} (raw code)")
            print(f"  extended 339     : {(live_network.get('source') or {}).get('extended_339')}")

            findings = network_health(live_network)
            print_section("🩺", "Network — Health Check")
            if not findings:
                print("  ✓ no findings")
            for f in findings:
                mark = "⚠" if f["level"] == "WARN" else "·"
                print(f"  {mark} [{f['level']}] {f['code']}")
                print(f"      {f['detail']}")
            print("\n  Note: the API exposes no connection-attempt history — "
                  "selectDeviceRunLogList\n        is a static alarm-code dictionary, not an "
                  "event log. For continuous\n        history, poll with "
                  "`tools/network_probe.py observe`.")

    if live_current is None:
        print("\n  Tip: run with --live to show current values alongside the schema")
