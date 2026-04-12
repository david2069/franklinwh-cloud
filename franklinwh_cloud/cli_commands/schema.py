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
    "run_status_desc":          ("derived",            "derived",          "str",   "Mode"),
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
    "mobile_signal":            ("signal",             "203/runtimeData",  "dBm",   "Connectivity"),
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

    if json_output:
        _json_output(live_current, live_totals, filter_group)
        return

    _terminal_output(live_current, live_totals, filter_group)


def _json_output(live_current, live_totals, filter_group):
    """Emit JSON schema output."""
    result = {"current": {}, "totals": {}}

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

    print_json_output(result)


def _terminal_output(live_current, live_totals, filter_group):
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
    if live_current is None:
        print("\n  Tip: run with --live to show current values alongside the schema")
