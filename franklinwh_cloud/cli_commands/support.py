"""Support command — point-in-time system snapshot for troubleshooting.

Collects device, network, version, power, and connectivity data into a
signed JSON snapshot. Supports redaction for safe sharing and comparison
against previous snapshots for change tracking.

Usage:
    franklinwh-cli support                              # Full snapshot to stdout
    franklinwh-cli support --save                       # Save to timestamped file
    franklinwh-cli support --save --redact              # Redacted for sharing
    franklinwh-cli support --save --label "pre-setup"   # Tag the snapshot
    franklinwh-cli support --analyze                    # Connectivity health check
    franklinwh-cli support --compare FILE               # Diff against previous
    franklinwh-cli support --compare FILE --scope net   # Scoped diff
"""

import hashlib
import json
import logging
import os
import re
import socket
import sys
from datetime import datetime, timezone

from franklinwh_cloud.cli_output import (
    print_header, print_section, print_kv, print_json_output,
    print_warning, print_success, print_error, c,
)

logger = logging.getLogger("franklinwh_cloud")

SNAPSHOT_VERSION = 3

# FranklinWH mobile app identifiers
APPLE_TRACK_ID = 1562630432
GOOGLE_PACKAGE = "com.Franklinwh.FamilyEnergy"


# ── App Store version lookup ─────────────────────────────────────────

def _fetch_apple_app_version(timeout: float = 5.0) -> dict | None:
    """Fetch current FranklinWH iOS app version from Apple iTunes API.

    Uses the public iTunes Search API — no authentication needed.
    Returns {version, releaseDate, releaseNotes} or None on failure.
    """
    import urllib.request
    try:
        url = f"https://itunes.apple.com/lookup?id={APPLE_TRACK_ID}&country=us"
        # iTunes lookup sometimes returns empty for direct ID; use search
        url = f"https://itunes.apple.com/search?term=franklinwh&entity=software&limit=5&country=us"
        req = urllib.request.Request(url, headers={"User-Agent": "franklinwh-cloud-client"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        for result in (data.get("results") or []):
            if result.get("trackId") == APPLE_TRACK_ID:
                return {
                    "version": result.get("version"),
                    "releaseDate": result.get("currentVersionReleaseDate"),
                    "releaseNotes": result.get("releaseNotes"),
                    "bundleId": result.get("bundleId"),
                }
    except Exception as e:
        logger.debug(f"Apple App Store lookup failed: {e}")
    return None


def _fetch_google_play_version(timeout: float = 5.0) -> str | None:
    """Scrape current FranklinWH Android app version from Google Play.

    Google Play doesn't have a public API, so we scrape the page.
    Returns version string or None on failure.
    """
    import urllib.request
    try:
        url = f"https://play.google.com/store/apps/details?id={GOOGLE_PACKAGE}&hl=en"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        # Google Play embeds version in JSON-LD or AF_initDataCallback
        # Look for pattern like [["2.11.0"]] near version indicators
        match = re.search(r'\[\[\["(\d+\.\d+\.?\d*)"\]\]', html)
        if match:
            return match.group(1)
        # Alternative: search for version pattern near "Current Version"
        match = re.search(r'"(\d+\.\d+\.\d+)"', html)
        if match:
            return match.group(1)
    except Exception as e:
        logger.debug(f"Google Play version lookup failed: {e}")
    return None


def fetch_app_store_versions(timeout: float = 5.0) -> dict:
    """Fetch mobile app versions from both stores.

    Returns dict with ios/android version info.
    Non-blocking on failure — returns partial results.
    """
    result = {}
    apple = _fetch_apple_app_version(timeout)
    if apple:
        result["ios"] = apple.get("version")
        result["ios_release_date"] = apple.get("releaseDate")
        result["ios_release_notes"] = apple.get("releaseNotes")
    google = _fetch_google_play_version(timeout)
    if google:
        result["android"] = google
    return result


# ── API schema fingerprint ───────────────────────────────────────────

def _collect_keys(obj, prefix="") -> list[str]:
    """Recursively collect all keys from a nested dict/list structure."""
    keys = []
    if isinstance(obj, dict):
        for k, v in sorted(obj.items()):
            full_key = f"{prefix}.{k}" if prefix else k
            keys.append(full_key)
            keys.extend(_collect_keys(v, full_key))
    elif isinstance(obj, list) and obj:
        # Sample first element for structure
        keys.extend(_collect_keys(obj[0], f"{prefix}[]"))
    return keys


def compute_schema_fingerprint(snapshot: dict) -> dict:
    """Compute a fingerprint of all API response keys.

    Returns {fingerprint: sha256_hex, key_count: int, keys: sorted_key_list}
    The fingerprint changes when FranklinWH adds, removes, or renames
    any field in their API responses — useful for detecting upstream changes.
    """
    # Collect keys from all data sections (skip metadata)
    all_keys = []
    for section in ("identity", "versions", "network", "connectivity",
                    "wifi_config", "switches", "batteries", "power",
                    "totals", "relays", "electrical"):
        data = (snapshot.get(section) or {})
        if isinstance(data, dict) and "error" not in data:
            section_keys = _collect_keys(data, section)
            all_keys.extend(section_keys)

    all_keys.sort()
    key_str = "\n".join(all_keys)
    fingerprint = hashlib.sha256(key_str.encode("utf-8")).hexdigest()[:16]
    return {
        "fingerprint": fingerprint,
        "key_count": len(all_keys),
        "keys": all_keys,
    }


# ── Redaction engine ─────────────────────────────────────────────────

def _redact_email(email: str, mode: str = "partial") -> str:
    """Redact an email address."""
    if not email or "@" not in email:
        return email
    if mode == "full":
        return "[REDACTED]"
    local, domain = email.split("@", 1)
    parts = domain.split(".")
    return f"{local[0]}***@{parts[0][0]}***.{'.'.join(parts[1:])}"


def _redact_serial(serial: str, mode: str = "partial") -> str:
    """Redact a device serial number."""
    if not serial or len(serial) < 6:
        return serial
    if mode == "full":
        return "[REDACTED]"
    return f"{serial[:4]}***{serial[-4:]}"


def _redact_ip(ip: str, mode: str = "partial") -> str:
    """Redact an IP address."""
    if not ip or ip == "0.0.0.0":
        return ip
    if mode == "full":
        return "[REDACTED]"
    parts = ip.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.{parts[2]}.XXX"
    return ip


def _redact_mac(mac: str, mode: str = "partial") -> str:
    """Redact a MAC address."""
    if not mac:
        return mac
    if mode == "full":
        return "[REDACTED]"
    parts = mac.split(":")
    if len(parts) == 6:
        return f"{parts[0]}:{parts[1]}:{parts[2]}:XX:XX:XX"
    return mac


def _redact_ssid(ssid: str, mode: str = "partial") -> str:
    """Redact a WiFi SSID."""
    if not ssid:
        return ssid
    if mode == "full":
        return "[REDACTED]"
    return ssid  # SSID kept in partial mode (useful for troubleshooting)


def redact_snapshot(data: dict, mode: str = "partial") -> dict:
    """Apply redaction to a snapshot data dict.

    Parameters
    ----------
    data : dict
        Raw snapshot data.
    mode : str
        "partial" — mask sensitive parts, keep structure visible.
        "full" — replace all PII with [REDACTED].

    Returns
    -------
    dict
        Redacted copy of the data.
    """
    import copy
    d = copy.deepcopy(data)

    # Identity
    identity = (d.get("identity") or {})
    if "serial" in identity:
        identity["serial"] = _redact_serial(identity["serial"], mode)
    if "email" in identity:
        identity["email"] = _redact_email(identity["email"], mode)
    if "address" in identity:
        identity["address"] = "[REDACTED]" if identity["address"] else identity["address"]
    for gw in (identity.get("gateway_sns") or []):
        pass  # Already redacted via serial

    # Versions
    versions = (d.get("versions") or {})
    if "msaSn" in versions and versions["msaSn"]:
        versions["msaSn"] = _redact_serial(versions["msaSn"], mode)

    # Network
    net = (d.get("network") or {})
    for iface in ("wifi", "eth0", "eth1", "operator"):
        idata = (net.get(iface) or {})
        if "mac" in idata:
            idata["mac"] = _redact_mac(idata.get("mac", ""), mode)
        if "ip" in idata:
            idata["ip"] = _redact_ip(idata.get("ip", ""), mode)
        if "gateway" in idata:
            idata["gateway"] = _redact_ip(idata.get("gateway", ""), mode)

    # WiFi config
    wifi_cfg = (d.get("wifi_config") or {})
    if "wifi_ssid" in wifi_cfg:
        wifi_cfg["wifi_ssid"] = _redact_ssid(wifi_cfg.get("wifi_ssid", ""), mode)
    if "wifi_password" in wifi_cfg:
        wifi_cfg["wifi_password"] = "***"
    if "ap_ssid" in wifi_cfg:
        wifi_cfg["ap_ssid"] = _redact_ssid(wifi_cfg.get("ap_ssid", ""), mode)
    if "ap_password" in wifi_cfg:
        wifi_cfg["ap_password"] = "***"

    d["_redacted"] = mode
    return d


# ── Snapshot collector ───────────────────────────────────────────────

async def collect_snapshot(client) -> dict:
    """Collect all diagnostic data into a single snapshot dict."""
    import franklinwh_cloud

    snapshot = {
        "identity": {},
        "versions": {},
        "network": {},
        "connectivity": {},
        "wifi_config": {},
        "switches": {},
        "power": {},
        "totals": {},
        "batteries": {},
        "relays": {},
        "electrical": {},
        "warranty": {},
        "tou_status": {},
        "programmes": {},
        "api_health": {},
    }

    # ── Identity ─────────────────────────────────────────────────
    try:
        gw_res = await client.get_home_gateway_list()
        gateways = (gw_res.get("result") or [])
        gw = next((g for g in gateways if g.get("id") == client.gateway), {})
        from franklinwh_cloud.const import FRANKLINWH_MODELS, COUNTRY_ID
        hw_ver = int(gw.get("sysHdVersion", 0))
        model_info = (FRANKLINWH_MODELS.get(hw_ver) or {})
        # Convert epoch ms timestamps to ISO dates
        active_time = gw.get("activeTime")
        create_time = gw.get("createTime")
        install_time = gw.get("installTime")

        snapshot["identity"] = {
            "serial": client.gateway,
            "model": model_info.get("model", f"HW v{hw_ver}"),
            "sku": model_info.get("sku", "?"),
            "hardware": gw.get("realSysHdVersion", "?"),
            "country": COUNTRY_ID.get(gw.get("countryId", 0), "Unknown"),
            "countryId": gw.get("countryId", 0),
            "provinceId": gw.get("provinceId", 0),
            "timezone": gw.get("zoneInfo", "?"),
            "email": gw.get("account", "?"),
            "status": gw.get("status"),
            "activeStatus": gw.get("activeStatus"),
            "simCardStatus": gw.get("simCardStatus"),
            "connType": gw.get("connType"),
            "activatedDate": datetime.fromtimestamp(active_time / 1000.0).strftime("%Y-%m-%d") if active_time else None,
            "createdDate": datetime.fromtimestamp(create_time / 1000.0).strftime("%Y-%m-%d") if create_time else None,
            "installedDate": datetime.fromtimestamp(install_time / 1000.0).strftime("%Y-%m-%d") if install_time else None,
            "deviceTime": gw.get("deviceTime"),
        }
    except Exception as e:
        snapshot["identity"]["error"] = str(e)

    # ── Versions ─────────────────────────────────────────────────
    try:
        agate = await client.get_agate_info()
        result = (agate.get("result") or {})
        snapshot["versions"]["ibgVersion"] = result.get("ibgVersion")
        snapshot["versions"]["awsVersion"] = result.get("awsVersion")
        snapshot["versions"]["appVersion"] = result.get("appVersion")
        snapshot["versions"]["slVersion"] = result.get("slVersion")
        snapshot["versions"]["meterVersion"] = result.get("meterVersion")
        snapshot["versions"]["protocolVer"] = result.get("protocolVer")
        snapshot["versions"]["connType"] = result.get("connType")
        snapshot["versions"]["msaModel"] = result.get("msaModel")
        snapshot["versions"]["msaSn"] = result.get("msaSn")
        snapshot["versions"]["adModuleHdVer"] = result.get("adModuleHdVer")
        snapshot["versions"]["adModuleAppVer"] = result.get("adModuleAppVer")
    except Exception as e:
        snapshot["versions"]["error"] = str(e)

    try:
        site = await client.siteinfo()
        snapshot["versions"]["cloudApiVersion"] = site.get("version")
    except Exception:
        pass

    snapshot["versions"]["libraryVersion"] = getattr(franklinwh_cloud, "__version__", "?")

    # ── Network ──────────────────────────────────────────────────
    try:
        snapshot["network"] = await client.get_network_info()
    except Exception as e:
        snapshot["network"]["error"] = str(e)

    # ── Connectivity ─────────────────────────────────────────────
    try:
        snapshot["connectivity"] = await client.get_connection_status()
    except Exception as e:
        snapshot["connectivity"]["error"] = str(e)

    # ── WiFi config ──────────────────────────────────────────────
    try:
        snapshot["wifi_config"] = await client.get_wifi_config()
    except Exception as e:
        snapshot["wifi_config"]["error"] = str(e)

    # ── Network switches ─────────────────────────────────────────
    try:
        snapshot["switches"] = await client.get_network_switches()
    except Exception as e:
        snapshot["switches"]["error"] = str(e)

    # ── Batteries (aPower) ───────────────────────────────────────
    try:
        snapshot["batteries"] = await client.get_apower_info()
    except Exception as e:
        snapshot["batteries"]["error"] = str(e)

    # ── Power snapshot + Totals ───────────────────────────────────────
    try:
        stats = await client.get_stats()
        cur = stats.current
        tot = stats.totals
        snapshot["power"] = {
            # ─ Core flow
            "solar_kw":           cur.solar_production,
            "battery_kw":         cur.battery_use,
            "battery_soc":        cur.battery_soc,
            "grid_kw":            cur.grid_use,
            "grid_status":        cur.grid_connection_state.value,
            "home_load_kw":       cur.home_load,
            # ─ Mode
            "operating_mode":     cur.work_mode_desc,
            "effective_mode":     cur.effective_mode,
            "run_status":         cur.run_status_desc,
            "tou_mode_desc":      cur.tou_mode_desc,
            "alarms_count":       cur.alarms_count,
            "device_status":      cur.device_status,
            "ambient_temp_c":     cur.agate_ambient_temparture,
            # ─ Power flow breakdown
            "power_flow": {
                "grid_charging_battery_kw":  cur.grid_charging_battery,
                "solar_export_to_grid_kw":   cur.solar_export_to_grid,
                "solar_charging_battery_kw": cur.solar_charging_battery,
                "battery_export_to_grid_kw": cur.battery_export_to_grid,
            },
            # ─ Signal quality
            # runtimeData.signal is a 0-100 percentage, not dBm (verified over
            # 20,471 HAR samples: range 0-99, never negative). The misnamed
            # "mobile_signal_dbm" key is retained for backward compatibility and
            # will be dropped in a future major release — prefer _pct.
            "wifi_signal_pct":    cur.wifi_signal,
            "mobile_signal_pct":  cur.mobile_signal,
            "mobile_signal_dbm":  cur.mobile_signal,  # DEPRECATED alias — value is %, not dBm
            # ─ Per-pack aPower state
            "apower_serials":     cur.apower_serial_numbers,
            "apower_soc":         cur.apower_soc,
            "apower_power":       cur.apower_power,
            "apower_bms_mode":    cur.apower_bms_mode,
            # ─ Smart circuit states
            "switch_1_state":     cur.switch_1_state,
            "switch_2_state":     cur.switch_2_state,
            "switch_3_state":     cur.switch_3_state,
        }
        snapshot["totals"] = {
            "solar_kwh":              tot.solar,
            "grid_import_kwh":        tot.grid_import,
            "grid_export_kwh":        tot.grid_export,
            "battery_charge_kwh":     tot.battery_charge,
            "battery_discharge_kwh":  tot.battery_discharge,
            "home_use_kwh":           tot.home_use,
            "switch_1_kwh":           tot.switch_1_use,
            "switch_2_kwh":           tot.switch_2_use,
            "v2l_export_kwh":         tot.v2l_export,
            "v2l_import_kwh":         tot.v2l_import,
        }
    except Exception as e:
        snapshot["power"]["error"] = str(e)
        snapshot["totals"]["error"] = str(e)

    # ── Relays ───────────────────────────────────────────────────
    # Primary relays sourced from runtimeData.main_sw[] via get_device_composite_info().
    # Extended 211-relay fields (grid_relay2, pv_relay2, black_start_relay) require a
    # separate get_stats(include_electrical=True) call — omitted here to avoid an extra
    # MQTT round-trip. They are displayed by `franklinwh-cli diag` instead.
    _comp_result = None
    _rt = {}
    try:
        comp = await client.get_device_composite_info()
        _comp_result = (comp.get("result") or {})
        _rt = (_comp_result.get("runtimeData") or {})
        main_sw = (_rt.get("main_sw") or [])
        snapshot["relays"] = {
            "grid_relay":      main_sw[0] if len(main_sw) > 0 else None,
            "generator_relay": main_sw[1] if len(main_sw) > 1 else None,
            "solar_pv_relay":  main_sw[2] if len(main_sw) > 2 else None,
        }
    except Exception as e:
        snapshot["relays"]["error"] = str(e)

    # ── Accessories ──────────────────────────────────────────────
    # Independent try-block: accessories must not fail due to relay errors.
    try:
        rt = _rt  # reuse runtimeData from composite if available

        try:
            sc_info = await client.get_smart_circuits_info()
        except Exception:
            sc_info = {}

        try:
            raw_equip = await client.get_accessories(0)
            equip_list = (raw_equip.get("result") or []) if isinstance(raw_equip, dict) else []
        except Exception:
            equip_list = []

        snapshot["accessories"] = {
            "smart_circuits": {
                "Sw1Name":           sc_info.get("Sw1Name"),
                "Sw1Mode":           rt.get("Sw1Mode"),
                "Sw1ProLoad":        rt.get("Sw1ProLoad"),
                "Sw1AtuoEn":         sc_info.get("Sw1AtuoEn"),
                "Sw1SocLowSet":      sc_info.get("Sw1SocLowSet"),
                "Sw1LoadLimit":      sc_info.get("Sw1LoadLimit"),
                "Sw2Name":           sc_info.get("Sw2Name"),
                "Sw2Mode":           rt.get("Sw2Mode"),
                "Sw2AtuoEn":         sc_info.get("Sw2AtuoEn"),
                "Sw2SocLowSet":      sc_info.get("Sw2SocLowSet"),
                "Sw2LoadLimit":      sc_info.get("Sw2LoadLimit"),
                "Sw3Name":           sc_info.get("Sw3Name"),
                "Sw3Mode":           rt.get("Sw3Mode"),
                "SwMerge":           sc_info.get("SwMerge"),
                "CarSwConsSupEnable": sc_info.get("CarSwConsSupEnable"),
            },
            "generator": {
                "genStat": rt.get("genStat"),
            },
            "v2l": {
                "v2lRunState": rt.get("v2lRunState"),
            },
            "pcs": {
                "pe_stat": rt.get("pe_stat"),
            },
            "apbox": {
                "di":       rt.get("di"),
                "doStatus": rt.get("doStatus"),
            },
            "hardware_registry_dump": equip_list,
        }
    except Exception as e:
        snapshot["accessories"] = {"error": str(e)}

    # ── Electrical measurements (cmdType 211) ────────────────────────
    # One extra MQTT call (get_power_info). Best-effort: graceful on failure.
    try:
        pwr = await client.get_power_info()
        snapshot["electrical"] = {
            "grid_voltage_l1_v":   pwr.get("gridVol1"),
            "grid_voltage_l2_v":   pwr.get("gridVol2"),
            "grid_current_l1_a":   pwr.get("gridCurr1"),
            "grid_current_l2_a":   pwr.get("gridCurr2"),
            "load_current_l1_a":   pwr.get("loadCurr1"),
            "load_current_l2_a":   pwr.get("loadCurr2"),
            "grid_frequency_hz":   pwr.get("gridFreq"),
            "grid_set_freq_hz":    pwr.get("dspSetFreq"),
            "grid_line_voltage_v": (pwr.get("gridLineVol") or 0) / 10 if pwr.get("gridLineVol") is not None else None,
            "generator_voltage_v": pwr.get("genVoltage"),
            "dsp_run_status":      pwr.get("dspRunStatus"),
            "ibg_run_status":      pwr.get("ibgRunStatus"),
            "electricity_type":    pwr.get("electricity_type"),
        }
    except Exception as e:
        snapshot["electrical"] = {"error": str(e)}

    # ── Warranty ─────────────────────────────────────────────────
    try:
        from datetime import date as _date, datetime as _dt
        w_res = await client.get_warranty_info()
        w = (w_res.get("result") or {})
        today = _date.today()

        # ─ Rated / remaining throughput (API returns MWh, convert to kWh)
        tp_kwh  = (w.get("throughput", 0) or 0) * 1000   # total rated kWh
        rem_kwh = w.get("remainThroughput", 0) or 0       # remaining kWh
        used_kwh = max(tp_kwh - rem_kwh, 0)

        # ─ Parse reference dates (nullable; compute only what we can)
        def _parse_d(s):
            if not s:
                return None
            try:
                return _dt.strptime(str(s)[:10], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                return None

        expiry_date  = _parse_d(w.get("expirationTime"))
        install_date = _parse_d((snapshot.get("identity") or {}).get("installedDate"))
        # ptoDate lives in tou_status — fetch it directly here rather than relying
        # on tou_status being populated (execution order may vary).
        try:
            _tou_r = await client.get_tou_dispatch_detail()
            _pto_raw = (_tou_r.get("result") or {}).get("ptoDate")
        except Exception:
            _pto_raw = None
        pto_date = _parse_d(_pto_raw)

        days_to_expiry     = (expiry_date  - today).days if expiry_date  else None
        days_since_install = (today - install_date).days  if install_date else None
        days_since_pto     = (today - pto_date).days      if pto_date     else None

        # ─ Average daily kWh throughput (from install and from PTO)
        avg_per_day_install = round(used_kwh / days_since_install, 2) \
            if days_since_install and days_since_install > 0 else None
        avg_per_day_pto     = round(used_kwh / days_since_pto, 2) \
            if days_since_pto and days_since_pto > 0 else None

        # ─ Forecast: rated kWh/day over full warranty term (install → expiry)
        total_warranty_days = (expiry_date - install_date).days \
            if (expiry_date and install_date) else None
        daily_kwh_forecast  = round(tp_kwh / total_warranty_days, 2) \
            if (total_warranty_days and total_warranty_days > 0 and tp_kwh > 0) else None

        # ─ Pace needed to exhaust remaining budget by expiry date
        daily_rem_needed = round(rem_kwh / days_to_expiry, 2) \
            if (days_to_expiry and days_to_expiry > 0 and rem_kwh > 0) else None

        snapshot["warranty"] = {
            "expirationTime":          w.get("expirationTime"),
            "days_to_expiry":          days_to_expiry,
            "throughput_kWh":          tp_kwh,
            "remainThroughput_kWh":    rem_kwh,
            "used_kWh":                round(used_kwh, 1),
            "days_since_install":      days_since_install,
            "days_since_pto":          days_since_pto,
            "avg_kwh_per_day_install": avg_per_day_install,
            "avg_kwh_per_day_pto":     avg_per_day_pto,
            "total_warranty_days":     total_warranty_days,
            "daily_kwh_forecast":      daily_kwh_forecast,
            "daily_rem_needed":        daily_rem_needed,
        }
        devices = (w.get("deviceExpirationList") or [])
        if devices:
            snapshot["warranty"]["devices"] = [
                {"sn": d.get("sn"), "model": d.get("model"), "expires": d.get("expirationTime")}
                for d in devices
            ]
    except Exception as e:
        snapshot["warranty"]["error"] = str(e)

    # ── TOU / Grid status ────────────────────────────────────────
    try:
        tou_res = await client.get_tou_dispatch_detail()
        tou = (tou_res.get("result") or {})
        template = (tou.get("template") or {})
        snapshot["tou_status"] = {
            "ptoDate": tou.get("ptoDate"),
            "onlineFlag": tou.get("onlineFlag"),
            "tariffSettingFlag": tou.get("tariffSettingFlag"),
            "nemType": tou.get("nemType"),
            "batterySavingsFlag": tou.get("batterySavingsFlag"),
            "alertMessage": tou.get("alertMessage"),
            "sendStatus": tou.get("sendStatus"),
            "batteryRatedCapacity_kWh": tou.get("batteryRatedCapacity"),
            "apowerCount": tou.get("apowerCount"),
            # Template / tariff identifiers
            "tariffPlan":        template.get("name"),
            "electricCompany":   template.get("electricCompany") or template.get("eleCompanyFullName"),
            "electricCompanyId": template.get("eletricCompanyId"),   # -1 = no vendor ID / custom
            "templateId":        template.get("templateId"),          # 0 = user-defined
            "templateInstanceId": template.get("id"),                # DB row ID for this gateway's config
            "workMode":          template.get("workMode"),
            "electricityType":   template.get("electricityType"),
            "provinceEn":        template.get("provinceEn"),
            "provinceId":        template.get("provinceId"),
            "lastUpdated":       template.get("updateTime"),
        }
    except Exception as e:
        snapshot["tou_status"]["error"] = str(e)

    # ── Operating Modes availability ──────────────────────────────
    # Known work modes and their prerequisites:
    #   workMode 1 = Time-Of-Use       → requires tariff schedule configured
    #   workMode 2 = Self-Consumption  → requires solar connected (solarFlag)
    #   workMode 3 = Emergency Backup  → always available
    snapshot["operating_modes"] = {}
    try:
        _ml_res  = await client.get_gateway_tou_list()
        _ml      = (_ml_res.get("result") or {}) if isinstance(_ml_res, dict) else {}
        _ml_list = (_ml.get("list") or []) or []
        _configured_wm = {int(m.get("workMode", 0)): m for m in _ml_list if m.get("workMode") is not None}

        # Flags from programmes (already captured above, but re-read safely here)
        _solar_ok  = bool((snapshot.get("programmes") or {}).get("solar_connected", True))
        _tariff_ok = bool((snapshot.get("tou_status") or {}).get("tariffSettingFlag", False))

        KNOWN_MODES = [
            (1, "Time-Of-Use",      _tariff_ok,  "TOU schedule not configured (tariffSettingFlag=False)"),
            (2, "Self-Consumption", _solar_ok,   "Solar not connected to aGate ports (solarFlag=False)"),
            (3, "Emergency Backup", True,         None),   # always available
        ]
        _mode_summary = []
        for wm_id, wm_name, prereq, reason in KNOWN_MODES:
            configured = wm_id in _configured_wm
            available  = prereq and configured
            entry = {
                "workMode":   wm_id,
                "name":       wm_name,
                "configured": configured,
                "available":  available,
                "reason":     reason if not available else None,
            }
            if configured:
                m = _configured_wm[wm_id]
                entry["displayName"] = m.get("name", wm_name)   # e.g. "Ausgrid EA11 TOU"
                entry["soc"]         = m.get("soc")
                entry["minSoc"]      = m.get("minSoc")
                entry["maxSoc"]      = m.get("maxSoc")
            _mode_summary.append(entry)

        snapshot["operating_modes"] = {
            "modes": _mode_summary,
            "stop_mode": bool(_ml.get("stopMode")),
            "grid_charge_enabled": bool(_ml.get("gridChargeEn")),
            "backup_forever_flag": bool(_ml.get("backupForeverFlag")),
        }
    except Exception as e:
        snapshot["operating_modes"]["error"] = str(e)

    # ── Programmes, Schemes & VPP ────────────────────────────────
    # Sources: get_entrance_info() + get_programme_info() + get_grid_profile_info()
    # + vppSocVo / todayVppVo / nemType from tou_dispatch_detail (already fetched above).
    # Country-aware: NEM type is a US (country_id=2) / CA state concept only.
    try:
        _country_id = (snapshot.get("identity") or {}).get("countryId", 0)
        _is_us = (_country_id == 2)
        _is_au = (_country_id == 3)

        # ─ Grid compliance profile (actual API name)
        _grid_profile = None
        try:
            _gp = await client.get_grid_profile_info(requestType=1)
            if isinstance(_gp, dict):
                _profiles = (_gp.get("list") or [])
                _current_id = _gp.get("currentId", 0)
                for _p in _profiles:
                    if _p.get("id") == _current_id:
                        _grid_profile = _p.get("name", "")
                        break
        except Exception:
            pass

        # ─ Entrance info — scheme eligibility flags + grid limits
        _ent = {}
        try:
            _ent = await client.get_entrance_info() or {}
        except Exception:
            pass

        # ─ VPP programme enrollment
        _prog = {}
        try:
            _prog_raw = await client.get_programme_info()
            if isinstance(_prog_raw, dict):
                _prog = _prog_raw
            elif isinstance(_prog_raw, list) and _prog_raw:
                _prog = _prog_raw[0]  # some firmware returns list
        except Exception:
            pass

        # ─ VPP SoC window + NEM type + DER schedule from TOU dispatch (already fetched)
        _tou_disp = {}
        try:
            _td = await client.get_tou_dispatch_detail()
            _tou_disp = (_td.get("result") or {}) if isinstance(_td, dict) else {}
        except Exception:
            pass

        _template = (_tou_disp.get("template") or {}) or {}
        _vpp_soc_vo = (_tou_disp.get("vppSocVo") or {}) or {}
        _today_vpp = (_tou_disp.get("todayVppVo") or {}) or {}
        _nem_raw = _tou_disp.get("nemType", None)
        _der_schedule = _template.get("derSchdule", None)

        # NEM type is US-CA specific — only include for US gateways
        _nem_label = None
        if _is_us and _nem_raw is not None:
            _NEM_TYPES = {0: "None", 1: "NEM 1.0", 2: "NEM 2.0", 3: "NEM 3.0", 4: "NEM Aggregation"}
            _nem_label = _NEM_TYPES.get(int(_nem_raw), f"NEM type {_nem_raw}")

        # ─ Global grid power limits (authoritative source: get_power_control_settings)
        # Encoding: -1 = Unlimited, 0 = Not allowed/Disabled, >0 = kW cap
        _pcs_raw = {}
        try:
            _pcs_res = await client.get_power_control_settings()
            _pcs_raw = (_pcs_res.get("result") or {}) if isinstance(_pcs_res, dict) else {}
        except Exception:
            pass

        snapshot["programmes"] = {
            # Grid compliance
            "grid_profile":          _grid_profile,
            # Core operational flags (from entrance info)
            "solar_connected":        bool(_ent.get("solarFlag", True)),    # False = no solar on aGate ports
            "grid_connected":         bool(_ent.get("gridFlag", True)),     # False = off-grid; grid ops invalid
            "tariff_configured":      bool(_ent.get("tariffSettingFlag", False)),
            # Scheme eligibility
            "sgip":                  bool(_ent.get("sgipEntrance", 0)),
            "bb":                    bool(_ent.get("bbEntrance", 0)),
            "ja12":                  bool(_ent.get("ja12Entrance", 0)),
            "sdcp":                  bool(_ent.get("sdcpFlag", False)),
            "pcs_enabled":           bool(_ent.get("pcsEntrance", 0)),
            # Grid limits (authoritative: get_power_control_settings)
            # Encoding: -1 = Unlimited, 0 = Not allowed, >0.1 = kW cap
            "grid_limits_raw": _pcs_raw,
            # Hardware flags
            "ahub_detected":          bool(_ent.get("ahubAddressingFlag")),
            "charging_power_limited": bool(_ent.get("chargingPowerLimited", False)),
            "need_ct_test":           bool(_ent.get("needCtTest", False)),
            # VPP enrollment
            "vpp_enrolled":          bool(_prog.get("flag", 0)),
            "vpp_programme_name":    _prog.get("programName"),
            "vpp_partner_name":      _prog.get("partnerName"),
            # VPP SoC operating window
            "vpp_soc_pct":           _vpp_soc_vo.get("vppSoc"),
            "vpp_min_soc_pct":       _vpp_soc_vo.get("vppMinSoc"),
            "vpp_max_soc_pct":       _vpp_soc_vo.get("vppMaxSoc"),
            # VPP today status
            "vpp_active_today":      bool(_today_vpp.get("vppFlag", 0)) if _today_vpp else False,
            # NEM type (US-CA only)
            "nem_type":              _nem_label,
            # DER schedule
            "der_schedule":          _der_schedule,
            # Battery savings flag
            "battery_savings_flag":  bool(_tou_disp.get("batterySavingsFlag", 0)),
        }
    except Exception as e:
        snapshot["programmes"]["error"] = str(e)

    metrics = client.get_metrics()
    snapshot["api_health"] = {
        "total_calls": metrics["total_api_calls"],
        "avg_response_s": metrics["avg_response_time_s"],
        "total_errors": metrics["total_errors"],
    }

    if hasattr(client, 'edge_tracker') and client.edge_tracker and client.edge_tracker.total_requests > 0:
        et = client.edge_tracker.snapshot()
        snapshot["api_health"]["edge_pop"] = et.get("current_pop")
        snapshot["api_health"]["cache_hit_rate"] = et.get("cache_hit_rate")

    # ── Mobile app versions (Apple App Store + Google Play) ──────
    try:
        app_versions = fetch_app_store_versions(timeout=5.0)
        if app_versions:
            snapshot["versions"]["mobileApp"] = app_versions
    except Exception:
        pass

    # ── API schema fingerprint ───────────────────────────────────
    schema = compute_schema_fingerprint(snapshot)
    snapshot["schema_fingerprint"] = {
        "fingerprint": schema["fingerprint"],
        "key_count": schema["key_count"],
    }

    return snapshot


# ── Signing ──────────────────────────────────────────────────────────

def sign_snapshot(data: dict) -> str:
    """Generate SHA-256 checksum of the data section."""
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── Connectivity analysis ────────────────────────────────────────────

# DEF-SUPPORT-NETTYPE-ENUM. This was a local bitmask-style table
# (0=None, 1=WiFi, 2=Ethernet, 3=WiFi+Ethernet, ...) indexed with
# currentNetType, which is positional. All three call sites below read
# currentNetType — the variable and key names saying "connType" are a misnomer
# and are what disguised the defect. Index 3 had already been hand-patched from
# "WiFi+Ethernet" to "WiFi", fixing one symptom of the wrong table.
#
# For runtimeData.connType, which is a genuinely different encoding, use
# const.devices.CONN_TYPE_NAMES.
from franklinwh_cloud.const.devices import NETWORK_TYPES as NET_TYPES


def analyze_connectivity(snapshot: dict) -> list[dict]:
    """Run connectivity rules against snapshot data.

    Returns list of findings: {severity, check, detail}
    severity: "critical", "warning", "info", "ok"
    """
    findings = []
    net = (snapshot.get("network") or {})
    conn = (snapshot.get("connectivity") or {})
    switches = (snapshot.get("switches") or {})
    wifi_cfg = (snapshot.get("wifi_config") or {})

    # AWS cloud status
    # Cross-check: if other snapshot sections have real data, the cloud API
    # is clearly working.  The sendMqtt cmdType-339 status self-report from
    # the aGate can return all-zeros even when connectivity is fine.
    api_reachable = bool(
        (snapshot.get("versions") or {}).get("ibgVersion")
        or (snapshot.get("power") or {}).get("solar_kw") is not None
    )

    if "error" not in conn:
        aws = conn.get("awsStatus", 0)
        router = conn.get("routerStatus", 0)
        net_status = conn.get("netStatus", 0)

        all_zero = not aws and not router and not net_status

        if all_zero and api_reachable:
            # sendMqtt status is stale/unreliable — cloud API clearly works
            findings.append({"severity": "warning", "check": "Connection Status",
                             "detail": "aGate reports all-zero (sendMqtt cmdType 339 may be stale) — cloud API is reachable"})
        else:
            if aws:
                findings.append({"severity": "ok", "check": "AWS Cloud", "detail": "Connected"})
            else:
                sev = "warning" if api_reachable else "critical"
                findings.append({"severity": sev, "check": "AWS Cloud", "detail": "Disconnected (per aGate self-report)"})

            if router:
                findings.append({"severity": "ok", "check": "Router", "detail": "Reachable"})
            else:
                sev = "warning" if api_reachable else "critical"
                findings.append({"severity": sev, "check": "Router", "detail": "Unreachable (per aGate self-report)"})

            if net_status:
                findings.append({"severity": "ok", "check": "Internet", "detail": "Available"})
            else:
                sev = "warning" if api_reachable else "critical"
                findings.append({"severity": sev, "check": "Internet", "detail": "No internet (per aGate self-report)"})
    else:
        findings.append({"severity": "warning", "check": "Connectivity", "detail": f"Could not check: {conn['error']}"})

    # WiFi checks
    if "error" not in net:
        wifi = (net.get("wifi") or {})
        wifi_mac = wifi.get("mac", "")
        wifi_ip = wifi.get("ip", "")

        if wifi_mac and wifi_ip == "0.0.0.0":
            findings.append({"severity": "critical", "check": "WiFi DHCP",
                             "detail": f"MAC {wifi_mac} associated but IP 0.0.0.0 — no DHCP lease"})
        elif wifi_mac and wifi_ip and wifi_ip != "0.0.0.0":
            dhcp_text = "DHCP" if wifi.get("dhcp") else "Static"
            findings.append({"severity": "ok", "check": "WiFi",
                             "detail": f"IP {wifi_ip} via {dhcp_text}"})

        # Ethernet checks
        for iface, label in [("eth0", "Ethernet 0"), ("eth1", "Ethernet 1")]:
            idata = (net.get(iface) or {})
            eth_mac = idata.get("mac", "")
            eth_ip = idata.get("ip", "")
            if eth_mac and eth_ip in ("0.0.0.0", ""):
                findings.append({"severity": "warning", "check": label,
                                 "detail": f"MAC {eth_mac} present but IP {eth_ip or 'empty'} (not configured?)"})
            elif eth_mac and eth_ip and eth_ip != "0.0.0.0":
                findings.append({"severity": "ok", "check": label,
                                 "detail": f"IP {eth_ip}"})

        # Cellular
        op = (net.get("operator") or {})
        if op.get("mac"):
            # operatorRSSI is a 0-52 vendor scale, NOT dBm — gotcha G3.
            # DEF-SUPPORT-RSSI-DBM.
            rssi = op.get("rssi", "?")
            findings.append({"severity": "info", "check": "Cellular",
                             "detail": f"Available (RSSI: {rssi}/52 vendor scale) — backup ready"})

        # 4G fallback detection
        conn_type = net.get("currentNetType", 0)
        # Only 4 is cellular under this encoding; 5/6/13 were bitmask values
        # that can never occur here and were dead branches.
        if conn_type == 4 and wifi_mac:
            findings.append({"severity": "warning", "check": "4G Fallback",
                             "detail": f"Active (currentNetType {conn_type}: {NET_TYPES.get(conn_type, '?')}) — WiFi/Ethernet may have failed"})

        # DNS checks
        wifi_dns = wifi.get("dns", "")
        eth0_dns = (net.get("eth0") or {}).get("dns", "")
        if wifi_dns and eth0_dns and wifi_dns != eth0_dns and eth0_dns not in ("", "0.0.0.0"):
            findings.append({"severity": "info", "check": "DNS mismatch",
                             "detail": f"WiFi DNS {wifi_dns} ≠ Ethernet DNS {eth0_dns}"})

    # WiFi AP mode check
    if "error" not in wifi_cfg:
        ap_ssid = wifi_cfg.get("ap_ssid")
        if ap_ssid:
            findings.append({"severity": "info", "check": "AP Mode",
                             "detail": f"aGate AP broadcasting: {ap_ssid}"})

    # Interface switches
    if "error" not in switches:
        for key, label in [("wifiNetSwitch", "WiFi"), ("ethernet0NetSwitch", "Ethernet 0"),
                           ("ethernet1NetSwitch", "Ethernet 1"), ("4GNetSwitch", "4G")]:
            val = switches.get(key)
            if val == 0:
                findings.append({"severity": "warning", "check": f"{label} Switch",
                                 "detail": "Interface DISABLED"})

    # Optional: local Modbus TCP probe
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.0)
        # Try to find aGate IP from WiFi or Ethernet
        agate_ip = None
        if "error" not in net:
            for iface in ("wifi", "eth0", "eth1"):
                ip = (net.get(iface) or {}).get("ip", "")
                if ip and ip != "0.0.0.0":
                    # We can't know the aGate's LAN IP from the cloud API,
                    # but we can note we tried
                    break
        # Skip Modbus probe — would need aGate's LAN IP, not available from cloud
        s.close()
    except Exception:
        pass

    return findings


# ── Diff / compare ───────────────────────────────────────────────────

SCOPE_KEYS = {
    "all": None,  # Compare everything
    "network": ["network", "connectivity", "wifi_config", "switches"],
    "software": ["versions"],
    "power": ["power", "totals", "relays", "electrical"],
}


def compare_snapshots(old: dict, new: dict, scope: str = "all") -> list[dict]:
    """Compare two snapshot data sections.

    Returns list of changes: {section, key, old_val, new_val, changed}
    """
    changes = []
    scope_keys = SCOPE_KEYS.get(scope)

    old_data = old.get("data", old)
    new_data = new.get("data", new)

    sections = scope_keys or [k for k in new_data if k not in ("_redacted",)]

    for section in sections:
        old_section = (old_data.get(section) or {})
        new_section = (new_data.get(section) or {})

        if not isinstance(old_section, dict) or not isinstance(new_section, dict):
            if old_section != new_section:
                changes.append({"section": section, "key": "", "old": old_section, "new": new_section, "changed": True})
            continue

        all_keys = set(list(old_section.keys()) + list(new_section.keys()))
        for key in sorted(all_keys):
            if key in ("error",):
                continue
            old_val = old_section.get(key)
            new_val = new_section.get(key)
            # For nested dicts (wifi, eth0, etc.), flatten
            if isinstance(old_val, dict) and isinstance(new_val, dict):
                for sub_key in sorted(set(list(old_val.keys()) + list(new_val.keys()))):
                    ov = old_val.get(sub_key)
                    nv = new_val.get(sub_key)
                    changed = ov != nv
                    if changed:
                        changes.append({
                            "section": section, "key": f"{key}.{sub_key}",
                            "old": ov, "new": nv, "changed": True,
                        })
            else:
                changed = old_val != new_val
                if changed:
                    changes.append({
                        "section": section, "key": key,
                        "old": old_val, "new": new_val, "changed": True,
                    })

    return changes
# ── Network Test ─────────────────────────────────────────────────────

import time
import urllib.request
import urllib.error


def _test_dns(host: str = "energy.franklinwh.com") -> dict:
    """Test DNS resolution and measure time."""
    try:
        t0 = time.monotonic()
        results = socket.getaddrinfo(host, 443, socket.AF_INET)
        elapsed = (time.monotonic() - t0) * 1000
        ip = results[0][4][0] if results else "?"
        return {"hop": "DNS", "ok": True, "ms": round(elapsed, 1), "detail": f"{host} → {ip}"}
    except Exception as e:
        return {"hop": "DNS", "ok": False, "ms": None, "detail": str(e)}


async def _test_api(client) -> dict:
    """Test cloud API round-trip and get edge POP."""
    try:
        t0 = time.monotonic()
        await client.get_home_gateway_list()
        elapsed = (time.monotonic() - t0) * 1000
        edge = None
        if hasattr(client, 'edge_tracker') and client.edge_tracker:
            snap = client.edge_tracker.snapshot()
            edge = snap.get("current_pop")
        detail = f"HTTPS {elapsed:.0f}ms"
        if edge:
            detail += f" → {edge} (CloudFront)"
        return {"hop": "Cloud API", "ok": True, "ms": round(elapsed, 1), "detail": detail}
    except Exception as e:
        return {"hop": "Cloud API", "ok": False, "ms": None, "detail": str(e)}


async def _test_agate_rtt(client) -> dict:
    """Test round-trip to aGate via sendMqtt (cmdType 339)."""
    try:
        t0 = time.monotonic()
        r = await client.get_connection_status()
        elapsed = (time.monotonic() - t0) * 1000
        # get_connection_status returns flat dict: {routerStatus, netStatus, awsStatus}
        if isinstance(r, dict):
            router = r.get("routerStatus", 0)
            net = r.get("netStatus", 0)
            aws = r.get("awsStatus", 0)
        else:
            router = net = aws = "?"
        detail = f"RTT {elapsed:.0f}ms — router={router} net={net} aws={aws}"
        return {"hop": "aGate RTT", "ok": True, "ms": round(elapsed, 1), "detail": detail}
    except Exception as e:
        return {"hop": "aGate RTT", "ok": False, "ms": None, "detail": str(e)}


async def _test_device_data(client) -> dict:
    """Test device data retrieval — proves full API data path.

    Returns hop dict with extra 'apower_serial' key for BMS chaining.
    """
    try:
        t0 = time.monotonic()
        res = await client.get_device_composite_info()
        elapsed = (time.monotonic() - t0) * 1000
        result = (res.get("result") or {})
        # result is a dict with runtimeData, not a list
        ok = res.get("success", res.get("code") == 200)
        detail = f"{elapsed:.0f}ms"
        apower_serial = None
        if isinstance(result, dict) and result.get("runtimeData"):
            rd = result["runtimeData"]
            soc = rd.get("soc")
            if soc is not None:
                detail += f" — SoC {soc:.0f}%"
            fhp_sns = (rd.get("fhpSn") or [])
            if fhp_sns and isinstance(fhp_sns, list) and fhp_sns[0]:
                apower_serial = fhp_sns[0]
        hop = {"hop": "Device Data", "ok": bool(ok), "ms": round(elapsed, 1), "detail": detail}
        hop["_apower_serial"] = apower_serial  # internal, for BMS chaining
        return hop
    except Exception as e:
        hop = {"hop": "Device Data", "ok": False, "ms": None, "detail": str(e)}
        hop["_apower_serial"] = None
        return hop


async def _test_bms(client, apower_serial: str) -> dict:
    """Test BMS battery data — dual sendMqtt (cmdType 211 type 2 + type 3).

    This emulates the mobile app pattern where two requests are sent
    and sometimes one response is lost.
    """
    try:
        t0 = time.monotonic()
        bms = await client.get_bms_info(apower_serial)
        elapsed = (time.monotonic() - t0) * 1000
        # Extract key BMS fields as sanity check
        detail = f"{elapsed:.0f}ms"
        if isinstance(bms, dict):
            voltage = bms.get("batTotalVolt")
            temp = bms.get("devTemp")
            soc = bms.get("batSoc")
            if voltage is not None:
                detail += f" — {voltage}V"
            if temp is not None:
                detail += f" {temp}°C"
            if soc is not None:
                detail += f" SoC {soc}%"
        return {"hop": "BMS", "ok": True, "ms": round(elapsed, 1), "detail": detail}
    except Exception as e:
        return {"hop": "BMS", "ok": False, "ms": None, "detail": str(e)}


def _test_fem(fem_url: str) -> dict:
    """Test FEM health via /api/identity and /api/diagnostics/connectivity."""
    results = {"hop": "FEM", "ok": False, "detail": "not found", "sub_tests": {}}

    # Try identity
    try:
        req = urllib.request.Request(f"{fem_url}/api/identity", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            identity = json.loads(resp.read())
        results["ok"] = True
        results["detail"] = f"v{identity.get('version', '?')} — {identity.get('provider', '?')}"
        results["fem_version"] = identity.get("version")
        results["provider"] = identity.get("provider")
        results["uptime"] = identity.get("uptime_seconds")
    except Exception:
        return results

    # Try diagnostics
    try:
        req = urllib.request.Request(f"{fem_url}/api/diagnostics/connectivity", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            diag = json.loads(resp.read())
        tests = diag.get("tests", diag)
        if isinstance(tests, dict):
            for test_name, test_data in tests.items():
                if isinstance(test_data, dict):
                    results["sub_tests"][test_name] = {
                        "ok": test_data.get("ok", test_data.get("status") == "ok"),
                        "detail": test_data.get("detail", test_data.get("message", "")),
                        "ms": test_data.get("latency_ms"),
                    }
    except Exception:
        pass

    return results


async def _collect_nettest_config(client) -> dict:
    """Gather current network configuration for the test header."""
    config = {}
    try:
        # get_network_info returns flat dict: {currentNetType, wifi, eth0, eth1, operator}
        r = await client.get_network_info()
        if isinstance(r, dict) and "error" not in r:
            # Key names kept for snapshot-format compatibility, but the value
            # is currentNetType, not connType. Misnomer, not a bug.
            config["connType"] = r.get("currentNetType", 0)
            config["connTypeName"] = NET_TYPES.get(
                config["connType"], f"Unknown ({config['connType']})")

            wifi = (r.get("wifi") or {})
            if wifi.get("ip") and wifi["ip"] != "0.0.0.0":
                config["primary"] = f"WiFi (DHCP)  IP: {wifi['ip']}"
            eth0 = (r.get("eth0") or {})
            if eth0.get("ip") and eth0["ip"] != "0.0.0.0":
                config["primary"] = f"Ethernet (IP: {eth0['ip']})"

            op = (r.get("operator") or {})
            if op.get("mac"):
                config["backup"] = f"4G/LTE  RSSI: {op.get('rssi', '?')}/52 (vendor scale)"
    except Exception:
        pass

    try:
        # get_network_switches returns flat dict: {ethernet0NetSwitch, wifiNetSwitch, ...}
        sw_r = await client.get_network_switches()
        if isinstance(sw_r, dict):
            config["sim_active"] = sw_r.get("4GNetSwitch", 0) == 1
    except Exception:
        pass

    return config


async def run_nettest(client, *, json_output: bool = False,
                      interval: int = 0, duration: int = 0,
                      record_file: str | None = None,
                      fem_url: str | None = None,
                      include_bms: bool = False):
    """Run network connectivity test."""

    # Guardrails — good API citizenship
    MIN_INTERVAL = 5    # seconds
    MAX_SAMPLES = 500   # per run

    if interval > 0 and interval < MIN_INTERVAL:
        from franklinwh_cloud.cli_output import print_warning
        print_warning(f"Minimum interval is {MIN_INTERVAL}s (requested {interval}s) — adjusting")
        interval = MIN_INTERVAL

    # FEM auto-discovery
    fem_urls_to_try = []
    if fem_url:
        fem_urls_to_try = [fem_url]
    else:
        fem_urls_to_try = ["http://localhost:9090", "http://homeassistant.local:9090"]

    discovered_fem = None
    for url in fem_urls_to_try:
        try:
            req = urllib.request.Request(f"{url}/api/health", method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    discovered_fem = url
                    break
        except Exception:
            continue

    # Collect network config
    net_config = await _collect_nettest_config(client)

    if interval > 0:
        await _run_nettest_interval(client, net_config, discovered_fem,
                                    interval=interval, duration=duration,
                                    max_samples=MAX_SAMPLES,
                                    record_file=record_file, json_output=json_output,
                                    include_bms=include_bms)
    else:
        await _run_nettest_single(client, net_config, discovered_fem,
                                  record_file=record_file, json_output=json_output,
                                  include_bms=include_bms)


async def _run_nettest_single(client, net_config: dict, fem_url: str | None,
                              record_file: str | None = None,
                              json_output: bool = False,
                              include_bms: bool = False):
    """Single network test run."""
    import asyncio

    # Run tier 1 tests
    dns = _test_dns()
    api = await _test_api(client)
    mqtt = await _test_agate_rtt(client)
    device = await _test_device_data(client)

    hops = [dns, api, mqtt, device]

    # BMS test — opt-in only (extra sendMqtt load)
    if include_bms:
        apower_serial = device.get("_apower_serial")
        if apower_serial:
            bms = await _test_bms(client, apower_serial)
            hops.append(bms)

    # Run tier 2 if FEM available
    fem = None
    if fem_url:
        fem = _test_fem(fem_url)
        hops.append(fem)

    # Calculate summary (FEM is optional — exclude from pass/fail)
    core_hops = [h for h in hops if h["hop"] != "FEM"]
    total_ms = sum(h.get("ms", 0) or 0 for h in hops)
    all_ok = all(h["ok"] for h in core_hops)
    failures = [h for h in core_hops if not h["ok"]]

    import franklinwh_cloud
    local_tz = datetime.now().astimezone().tzname()

    result = {
        "_meta": {
            "command": "franklinwh-cli support --nettest",
            "library_version": getattr(franklinwh_cloud, "__version__", "?"),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "timestamp_local": datetime.now().astimezone().isoformat(),
            "timezone": local_tz,
        },
        "network_config": net_config,
        "fem_detected": fem_url,
        "hops": hops,
        "total_ms": round(total_ms, 1),
        "all_ok": all_ok,
    }
    if fem and fem.get("sub_tests"):
        result["fem_diagnostics"] = fem["sub_tests"]

    if json_output:
        print_json_output(result)
    else:
        print_header("FranklinWH Network Test")
        _display_nettest_config(net_config)
        _display_nettest_hops(hops, fem)
        _display_nettest_summary(total_ms, all_ok, failures)

    if record_file:
        with open(record_file, "w") as f:
            json.dump(result, f, indent=2, default=str)
        if not json_output:
            print_success(f"Results saved to {record_file}")
            print()


async def _run_nettest_interval(client, net_config: dict, fem_url: str | None,
                                interval: int, duration: int,
                                max_samples: int = 500,
                                record_file: str | None = None,
                                json_output: bool = False,
                                include_bms: bool = False):
    """Run network test at intervals."""
    import asyncio

    samples = []
    start_time = datetime.now(timezone.utc)
    elapsed = 0

    if not json_output:
        print_header(f"FranklinWH Network Monitor — {interval}s intervals")
        _display_nettest_config(net_config)
        if max_samples < 9999:
            print(f"  {c('dim', f'Max {max_samples} samples per run')}")
        print()
        # Table header — BMS column only when enabled
        fem_cols = "  FEM   " if fem_url else ""
        bms_col = f"{'BMS':>8}" if include_bms else ""
        print(f"  {'TIME':<10}{'DNS':>6}{'API':>8}{'aGate':>8}{'Data':>8}{bms_col}{fem_cols}  STATUS")
        print(f"  {'─'*9} {'─'*5} {'─'*7} {'─'*7} {'─'*7} {'─'*7 if include_bms else ''} {'─' * (6 if fem_url else 0)} {'─'*12}")

    try:
        while (duration == 0 or elapsed < duration) and len(samples) < max_samples:
            now = datetime.now()
            dns = _test_dns()
            api = await _test_api(client)
            mqtt = await _test_agate_rtt(client)
            device = await _test_device_data(client)

            # BMS — opt-in only
            bms = None
            if include_bms:
                apower_serial = device.get("_apower_serial")
                if apower_serial:
                    bms = await _test_bms(client, apower_serial)

            core = [dns, api, mqtt, device]
            if bms:
                core.append(bms)

            sample = {
                "time": now.strftime("%H:%M:%S"),
                "dns_ms": dns.get("ms"),
                "api_ms": api.get("ms"),
                "mqtt_ms": mqtt.get("ms"),
                "data_ms": device.get("ms"),
                "bms_ms": bms.get("ms") if bms else None,
                "ok": all(h["ok"] for h in core),
            }

            fem_status = ""
            if fem_url:
                fem = _test_fem(fem_url)
                sample["fem_ok"] = fem["ok"]
                fem_status = f"  {'✓' if fem['ok'] else '✗':>5} "

            samples.append(sample)

            if not json_output:
                dns_str = f"{dns['ms']:.0f}ms" if dns["ok"] else "✗"
                api_str = f"{api['ms']:.0f}ms" if api["ok"] else "✗"
                mqtt_str = f"{mqtt['ms']:.0f}ms" if mqtt["ok"] else "✗"
                data_str = f"{device['ms']:.0f}ms" if device["ok"] else "✗"
                bms_str = ""
                if include_bms:
                    bms_str = f"{bms['ms']:.0f}ms" if bms and bms["ok"] else ("✗" if bms else "—")
                    bms_str = f"{bms_str:>8}"
                status = c("green", "✓ All OK") if sample["ok"] else c("red", "⚠ FAIL")
                print(f"  {sample['time']:<10}{dns_str:>6}{api_str:>8}{mqtt_str:>8}{data_str:>8}{bms_str}{fem_status}  {status}")

            if duration > 0 and elapsed + interval >= duration:
                break
            if len(samples) >= max_samples:
                if not json_output:
                    print(f"\n  {c('yellow', f'Max {max_samples} samples reached — stopping')}")
                break
            await asyncio.sleep(interval)
            elapsed += interval
    except KeyboardInterrupt:
        if not json_output:
            print(f"\n  {c('dim', 'Stopped by user')}")

    # Summary
    if not json_output:
        print()
        total = len(samples)
        fails = sum(1 for s in samples if not s["ok"])
        avg_api = sum(s.get("api_ms", 0) or 0 for s in samples) / max(total, 1)
        # Each sample makes 4 requests (DNS, API, aGate, Config)
        total_requests = total * 4
        total_responses = sum(4 if s["ok"] else sum(1 for k in ["dns_ms", "api_ms", "mqtt_ms", "tou_ms"] if s.get(k)) for s in samples)
        print_kv("Samples", f"{total} ({fails} failures)")
        print_kv("Requests", f"{total_requests} sent, {total_responses} OK")
        print_kv("Avg API latency", f"{avg_api:.0f}ms")
        print()

    if record_file:
        import franklinwh_cloud
        local_tz = datetime.now().astimezone().tzname()
        output = {
            "_meta": {
                "command": f"franklinwh-cli support --nettest --interval {interval} --duration {duration}",
                "library_version": getattr(franklinwh_cloud, "__version__", "?"),
                "timezone": local_tz,
            },
            "start": start_time.isoformat(),
            "interval_s": interval,
            "duration_s": duration,
            "network_config": net_config,
            "fem_detected": fem_url,
            "samples": samples,
            "summary": {
                "total_samples": len(samples),
                "failures": sum(1 for s in samples if not s["ok"]),
                "avg_api_ms": round(sum(s.get("api_ms", 0) or 0 for s in samples) / max(len(samples), 1), 1),
            },
        }
        with open(record_file, "w") as f:
            json.dump(output, f, indent=2, default=str)
        if not json_output:
            print_success(f"Results saved to {record_file}")
            print()

    if json_output:
        print_json_output({
            "start": start_time.isoformat(),
            "samples": samples,
            "total": len(samples),
            "failures": sum(1 for s in samples if not s["ok"]),
        })


def _display_nettest_config(net_config: dict):
    """Display network configuration header."""
    print_section("🔌", "Active Configuration")
    primary = net_config.get("primary", "Unknown")
    print_kv("Primary", primary)
    backup = net_config.get("backup")
    if backup:
        sim = "SIM: Active" if net_config.get("sim_active") else ""
        print_kv("Backup", f"{backup}  {sim}")
    conn_name = net_config.get("connTypeName", "?")
    print_kv("currentNetType", f"{net_config.get('connType', '?')} ({conn_name})")
    # Source IP (this machine)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        src_ip = s.getsockname()[0]
        s.close()
        print_kv("Source IP", src_ip)
    except Exception:
        pass
    # Destination IP (API server)
    try:
        results = socket.getaddrinfo("energy.franklinwh.com", 443, socket.AF_INET)
        if results:
            print_kv("Dest IP", f"{results[0][4][0]} (energy.franklinwh.com)")
    except Exception:
        pass


def _display_nettest_hops(hops: list, fem: dict | None = None):
    """Display hop-by-hop results."""
    print_section("🏓", "Cloud Path")
    for i, hop in enumerate(hops):
        if hop["hop"] == "FEM":
            continue  # Display separately
        icon = c("green", "✓") if hop["ok"] else c("red", "✗")
        ms_str = f"{hop['ms']:.0f}ms" if hop.get("ms") else "—"
        print_kv(f"  {i+1}. {hop['hop']}", f"{icon}  {ms_str:<8} {hop.get('detail', '')}")

    if fem and fem["ok"]:
        print_section("🏠", f"FEM ({fem.get('detail', '')})")
        for name, test in (fem.get("sub_tests") or {}).items():
            icon = c("green", "✓") if test.get("ok") else c("red", "✗")
            ms_str = f"{test.get('ms', 0):.0f}ms" if test.get("ms") else ""
            detail = test.get("detail", "")
            print_kv(f"  {name}", f"{icon}  {ms_str:<8} {detail}")
    elif fem and not fem["ok"]:
        print_section("🏠", "FEM")
        print_kv("  Status", c("dim", "Not detected"))


def _display_nettest_summary(total_ms: float, all_ok: bool, failures: list):
    """Display test summary."""
    print_section("📊", "Summary")
    if all_ok:
        print_kv("End-to-end", c("green", f"✓ All hops passed ({total_ms:.0f}ms total)"))
    else:
        fail_names = ", ".join(f["hop"] for f in failures)
        print_kv("End-to-end", c("red", f"✗ Failed: {fail_names} ({total_ms:.0f}ms total)"))
    print()


# ── CLI entry point ──────────────────────────────────────────────────

# ── Account Info ─────────────────────────────────────────────────────


def mock_snapshot() -> dict:
    """Return a schema-valid v3 snapshot envelope populated with simulated data.

    Mirrors the real snapshot produced by collect_snapshot() + build_envelope().
    Safe to use in tests, CI, and --compare workflows without any API calls.
    All serial numbers, emails, and addresses are fictional.
    """
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat()
    return {
        "snapshot_version": 3,
        "timestamp": ts,
        "gateway": "10060006A0XXXXXX0001",
        "label": "mock",
        "checksum": "sha256:mock000000000000000000000000000000000000000000000000000000000000",
        "data": {
            "identity": {
                "serial": "10060006A0XXXXXX0001",
                "model": "aGate X-02-US",
                "sku": "AGT-R2V1-US",
                "hardware": "FranklinWH System1.2",
                "country": "United States",
                "countryId": 2,
                "provinceId": 5,
                "timezone": "America/Los_Angeles",
                "email": "john.doe@anymail.com",
                "status": 1,
                "activeStatus": 1,
                "simCardStatus": 2,
                "connType": 3,
                "activatedDate": "2024-04-01",
                "createdDate": "2024-01-15",
                "installedDate": None,
                "deviceTime": ts[:19].replace("T", " "),
            },
            "power": {
                "solar_kw": 7.6,
                "battery_kw": -2.5,
                "battery_soc": 85,
                "grid_kw": 0.0,
                "grid_state": "Connected",
                "home_load_kw": 5.1,
                "operating_mode": "Time-Of-Use",
                "tou_mode_desc": "PG&E Peak Day Pricing",
                "run_status": "Charging",
                "apower_serials": ["10050013A0AAAAAAA01", "10050013A0AAAAAAA02", "10050013A0AAAAAAS01"],
                "apower_soc": [85.0, 84.5, 85.5],
                "apower_bms_mode": [6, 6, 6],
                "ambient_temp_c": 22.5,
                "wifi_signal_pct": 78,
                "mobile_signal_pct": 45,
                "mobile_signal_dbm": 45,  # DEPRECATED alias — value is %, not dBm
                "grid_charging_battery_kw": 2.5,
                "solar_export_to_grid_kw": 0.0,
                "solar_charging_battery_kw": 5.1,
                "battery_export_to_grid_kw": 0.0,
            },
            "totals": {
                "battery_charge_kwh": 18540.2,
                "battery_discharge_kwh": 17820.1,
                "grid_import_kwh": 4210.5,
                "grid_export_kwh": 3150.8,
                "solar_kwh": 28750.3,
                "home_load_kwh": 21630.4,
            },
            "batteries": [
                {"type": "battery", "model": "aPower S", "serial": "10050013A0AAAAAAS01", "capacity_kwh": 15.0},
                {"type": "battery", "model": "aPower",   "serial": "10050013A0AAAAAAA01", "capacity_kwh": 13.6},
                {"type": "battery", "model": "aPower",   "serial": "10050013A0AAAAAAA02", "capacity_kwh": 13.6},
            ],
            "warranty": {
                "expirationTime": "2036-04-01",
                "throughput_kWh": 129000,
                "used_kWh": 18540,
                "remainThroughput_kWh": 110460,
                "days_to_expiry": 3998,
                "days_since_install": 387,
                "days_since_pto": 357,
                "avg_kwh_per_day_install": 47.9,
                "avg_kwh_per_day_pto": 51.9,
                "daily_kwh_forecast": 35.3,
                "daily_rem_needed": 27.6,
                "total_warranty_days": 4383,
                "devices": [
                    {"model": "aGate X-02-US", "expires": "2036-04-01"},
                    {"model": "aPower S",       "expires": "2036-04-01"},
                    {"model": "aPower",         "expires": "2036-04-01"},
                    {"model": "aPower",         "expires": "2036-04-01"},
                ],
            },
            "programmes": {
                "grid_profile": "IEEE 1547a (Default)",
                "solar_connected": True,
                "grid_connected": True,
                "tariff_configured": True,
                "sgip": True,
                "bb": False,
                "ja12": False,
                "sdcp": True,
                "pcs_enabled": True,
                "grid_limits_raw": {
                    "gridMax": -1.0,
                    "gridFeedMax": -1.0,
                    "globalGridChargeMax": -1.0,
                    "globalGridDischargeMax": -1.0,
                    "notControlExportSolar": False,
                    "peakDemandGridMax": None,
                    "sgipFlag": 1,
                    "itcFlag": 1,
                    "isNem3": 1,
                    "isCalifornia": 1,
                },
                "ahub_detected": True,
                "charging_power_limited": True,
                "need_ct_test": False,
                "vpp_enrolled": True,
                "vpp_programme_name": "Virtual Peakers",
                "vpp_partner_name": "Pacific Gas & Electric",
                "vpp_soc_pct": 30,
                "vpp_min_soc_pct": 10,
                "vpp_max_soc_pct": 100,
                "vpp_active_today": True,
                "nem_type": "NEM 3.0",
                "der_schedule": "SGIP",
                "battery_savings_flag": False,
            },
            "tou_status": {
                "ptoDate": "2024-05-01",
                "onlineFlag": True,
                "tariffSettingFlag": True,
                "nemType": 3,
                "batterySavingsFlag": False,
                "alertMessage": None,
                "sendStatus": None,
                "batteryRatedCapacity_kWh": 42.2,
                "apowerCount": 3,
                "tariffPlan": "PG&E Peak Day Pricing",
                "electricCompany": "Pacific Gas and Electric",
                "electricCompanyId": 12,
                "templateId": 1042,
                "templateInstanceId": 88001,
                "workMode": 1,
                "electricityType": 1,
                "provinceEn": "California",
                "provinceId": 5,
                "lastUpdated": "2026-01-15 08:00:00",
            },
            "versions": {
                "meterVersion": "1.0.0",
                "protocolVer": "1.0",
                "connType": "WIFI",
                "msaModel": "MAC-1",
                "msaSn": "mock-redacted-msa-sn",
                "adModuleHdVer": "V1.0",
                "adModuleAppVer": "V1.2.3",
            },
            "api_health": {
                "total_calls": 0,
                "avg_response_s": 0.0,
                "total_errors": 0,
            },
            "schema_fingerprint": {
                "fingerprint": "mock-fingerprint",
                "key_count": 0,
            },
        },
    }


def mock_diag_output(json_output: bool = False):
    """Print a simulated max-config support --info --diag output.

    With --json: emits a schema-valid v3 snapshot envelope (no real data).
    Without --json: prints the human-readable topology tree (no API calls).

    Shows every possible feature enabled on a fictional two-gateway grouped
    site. Useful for understanding output format and testing without API calls.
    No real account data is used or implied.
    """
    from franklinwh_cloud.cli_output import c

    if json_output:
        from franklinwh_cloud.cli_output import print_json_output
        print_json_output(mock_snapshot())
        return

    BANNER = "  ⚠  SIMULATED DATA — no real API calls made  ⚠"
    print(c("yellow", "─" * len(BANNER)))
    print(c("yellow", BANNER))
    print(c("yellow", "─" * len(BANNER)))
    print()

    # ── Account / Site header ──────────────────────────────────────────
    print(f"{c('cyan', 'john.doe@anymail.com')} (UserId: 99999)")
    print(f"└── {c('yellow', 'Smallsville (SiteId: 1203) — 123 Anywhere St, Sydney NSW 2000')}")

    gateways = [
        {
            "serial":  "10060006A0XXXXXX0001",
            "name":    "FHP1",
            "model":   "aGate X-02-US",
            "group":   "Main House",
            "grp_id":  "501",
            "last":    False,
        },
        {
            "serial":  "10060006A0XXXXXX0002",
            "name":    "FHP2",
            "model":   "aGate X-01-AU",
            "group":   "(ungrouped)",
            "grp_id":  None,
            "last":    True,
        },
    ]

    # Groups
    print(f"    ├── {c('magenta', 'Group: \"Main House\" (GroupId: 501)')}")
    print(f"    └── {c('magenta', 'Group: (ungrouped)')}")
    print()

    for gw in gateways:
        bar  = "    "
        grp_bar = "    "
        gw_pfx = "└──" if gw["last"] else "├──"
        indent = bar + grp_bar

        print(f"    {'└──' if gw['last'] else '├──'} {c('magenta', 'Group: ' + ('\"Main House\" (GroupId: 501)' if not gw['last'] else '(ungrouped)'))}")
        print(f"{indent}{gw_pfx} {c('green', gw['name'] + ' (' + gw['model'] + ': ' + gw['serial'] + ')')}")
        gw_bar = "    " if gw["last"] else "│   "

        # Tree items
        items = [
            "Status: Charging (Self-Consumption)",
            "Grid: Connected",
            "Solar PV: PV1 + PV2 + Proximal (7.6 kW live) + Remote (aPBox)",
            "CT: Split Grid ✓  (two utility services)",
            "CT: Split PV ✓  (multiple PV strings metered)",
            "aHub: Detected  (remote SC / solar / generator input)",
            "MAC-1 (MSA): Detected (Meter Socket Adaptor)",
            "aPBox: Detected, Remote Solar Enabled",
            "aPower S / DC MPPT: Enabled (1 unit(s))",
            "Smart Circuit: Living Room [Auto]",
            "Smart Circuit: Pool Pump [Schedule]",
            "Smart Circuit: Workshop [Manual]",
            "V2L: Enabled — Ready",
            "Generator: Honda EU7000iS (SN: GEN-XXXX001), Enabled — Running",
            "aPower S (Serial: 10050013A0AAAAAAS01)",
            "aPower (Serial: 10050013A0AAAAAAA01)",
            "aPower (Serial: 10050013A0AAAAAAA02)",
            "Derating: Charge limited to 8 kW",
            "Lifecycle: Created 2024-01-15 | Activated 2024-04-01 | Expires 2036-04-01 | PTO: 2024-05-01",
            "Grid Profile: IEEE 1547a (Default)",
            "✅ aGate: Normal",
            "✅ aPower: 3 unit(s), SoC 85.0%",
            "✅ PCS Control: Enabled",
            "✅ TOU Schedule: Configured",
        ]
        for i, item in enumerate(items):
            last = i == len(items) - 1
            print(f"{indent}{gw_bar}{'└──' if last else '├──'} {c('dim', item)}")

        # Feature flags
        pad = f"{indent}{gw_bar}    "
        print(f"{pad}{c('bold', '🏷️  Feature Flags')}")
        flags = [
            (True,  "Solar: PV1 + PV2 + Proximal (AC-coupled) + Remote (aPBox)"),
            (True,  "TOU/Tariff: Configured"),
            (True,  "PCS Power Control: Enabled"),
            (True,  "Grid-Tied: Connected"),
            (True,  "MPPT (DC-coupled): Enabled"),
            (True,  "Three Phase: Installed"),
            (True,  "CT Split — Grid: Installed"),
            (True,  "CT Split — PV: Installed"),
        ]
        for ok, lbl in flags:
            print(f"{pad}  {'✅' if ok else '❌'} {lbl}")

        # Smart circuits with V2L
        sc_ver = 2 if not gw["last"] else 1
        sc_names = "Living Room, Pool Pump, Workshop" if sc_ver == 2 else "Circuit 1, Circuit 2"
        sc_cnt = 3 if sc_ver == 2 else 2
        print(f"{pad}  ✅ Smart Circuits: V{sc_ver}, {sc_cnt} circuits ({sc_names})")
        if sc_ver == 2:
            print(f"{pad}      ✅ V2L: V2L built-in (V2 Smart Circuits)")
        else:
            print(f"{pad}      ✅ V2L: V2L via CarSW (V1 SC + Generator Module)")

        more_flags = [
            (True,  "Generator Module: Enabled"),
            (True,  "Remote Solar (aPBox): Connected"),
            (True,  "aHub: Detected"),
            (True,  "MAC-1 (MSA): Detected"),
            (True,  "VPP Programme: Enrolled"),
        ]
        for ok, lbl in more_flags:
            print(f"{pad}  {'✅' if ok else '❌'} {lbl}")

        # System Relays (all connected / closed)
        print(f"{pad}{c('bold', '🔧  System Relays')}")
        relays = [
            ("Grid Relay",        False, "OPEN"),
            ("Generator Relay",   True,  "CLOSED"),
            ("Solar PV Relay",    True,  "CLOSED"),
            ("Grid Relay 2",      True,  "CLOSED"),
            ("Black Start Relay", False, "OPEN"),
            ("Solar PV Relay 2",  True,  "CLOSED"),
            ("BFPV/aPBox Relay",  True,  "CLOSED"),
        ]
        label_w = max(len(r[0]) for r in relays)
        for lbl, closed, state in relays:
            icon = "●" if closed else "○"
            print(f"{pad}  {lbl:>{label_w}}: {icon} {state}")

        print()

    print(c("yellow", "─" * len(BANNER)))
    print(c("yellow", BANNER))
    print(c("yellow", "─" * len(BANNER)))


async def run_info(client, json_output: bool = False, diag: bool = False):
    """Implement franklinwh-cli support --info mapping the account taxonomy.

    Renders: user → site → [group →] aGate → full installation detail.
    Groups are shown only when at least one gateway has groupFlag=1 (multi-gateway
    accounts). Single-gateway accounts show the flat tree with no group tier.

    Installation detail per aGate:
      - Status (run + mode)
      - Grid connection type
      - Solar PV (ports + live kW or "None")
      - Split CTs (grid / PV) — only if installed
      - aHub / aPBox / MPPT — only if detected
      - Smart Circuits with serial + model
      - V2L state
      - Generator with serial + state
      - aPower batteries with model
      - Lifecycle dates
      - Grid profile
    """
    from franklinwh_cloud.cli_output import c, print_json_output
    from franklinwh_cloud.const import FRANKLINWH_MODELS

    email = getattr(client.fetcher, "email", "UnknownUser")
    user_id = getattr(client.fetcher, "user_id", "Unknown")

    try:
        site_info = await client.siteinfo()
        user_id = site_info.get("userId", user_id)
        email = site_info.get("email", email)
    except Exception:
        pass

    # ── Fetch account-level data ──────────────────────────────────────
    try:
        site_info_res = await client.get_site_and_device_info()
        sites_data = (site_info_res.get("result") or [])
    except Exception as e:
        print_error(f"Failed to fetch site list: {e}")
        return

    try:
        gw_res = await client.get_home_gateway_list()
        gw_meta_list = (gw_res.get("result") or [])
        # Keyed by gateway id for O(1) lookup
        gateways = {g.get("id"): g for g in gw_meta_list if g.get("id")}
    except Exception:
        gw_meta_list = []
        gateways = {}

    # ── Build output structure ────────────────────────────────────────
    topology = {"email": email, "userId": user_id, "sites": []}

    if not json_output:
        print(f"{c('cyan', email)} (UserId: {user_id})")

    for site_idx, site in enumerate(sites_data):
        is_last_site = site_idx == len(sites_data) - 1
        site_prefix = "└──" if is_last_site else "├──"
        site_bar    = "    " if is_last_site else "│   "

        site_name = site.get("siteName") or "Default Site"
        site_id   = site.get("siteId") or "Unknown"
        address   = site.get("completeAddress", "")

        site_node = {
            "siteName": site_name,
            "siteId": site_id,
            "completeAddress": address,
            "groups": [],
            "gateways": [],
        }
        topology["sites"].append(site_node)

        if not json_output:
            site_label = f"{site_name} (SiteId: {site_id})"
            if address:
                site_label += f" — {address}"
            print(f"{site_prefix} {c('yellow', site_label)}")

        # ── Group-aware gateway bucketing ─────────────────────────────
        gws = (site.get("basicDeviceInfoVOList") or [])

        # Check whether any gateway in this site belongs to a named group
        has_groups = any(
            (gateways.get(gw.get("gatewayId")) or {}).get("groupFlag") == 1
            for gw in gws
        )

        # Build ordered buckets: groupId (str) or None → [gw_dict, ...]
        group_buckets  = {}   # ordered by first appearance
        group_names    = {}   # groupId → display name

        for gw in gws:
            gid = gw.get("gatewayId", "?")
            meta = (gateways.get(gid) or {})
            grp  = meta.get("groupId") if meta.get("groupFlag") == 1 else None
            if grp not in group_buckets:
                group_buckets[grp] = []
            group_buckets[grp].append(gw)
            if grp and grp not in group_names:
                group_names[grp] = meta.get("groupName") or f"Group {grp}"

        # ── Iterate groups (or flat list if no groups) ─────────────────
        group_ids = list(group_buckets.keys())
        for grp_idx, grp_id in enumerate(group_ids):
            members = group_buckets[grp_id]
            is_last_grp = grp_idx == len(group_ids) - 1

            if has_groups:
                grp_prefix = "└──" if is_last_grp else "├──"
                grp_bar    = "    " if is_last_grp else "│   "
                grp_label  = group_names.get(grp_id, "(ungrouped)")
                grp_display = f"Group: \"{grp_label}\"" if grp_id else "Group: (ungrouped)"
                if grp_id:
                    grp_display += f" (GroupId: {grp_id})"
                if not json_output:
                    print(f"{site_bar}{grp_prefix} {c('magenta', grp_display)}")
                grp_node = {
                    "groupId": grp_id,
                    "groupName": grp_label if grp_id else None,
                    "gateways": [],
                }
                site_node["groups"].append(grp_node)
                gw_parent_list = grp_node["gateways"]
                indent = site_bar + grp_bar
            else:
                indent = site_bar
                gw_parent_list = site_node["gateways"]

            # ── Per-gateway rendering ──────────────────────────────────
            for gw_idx, gw in enumerate(members):
                is_last_gw = gw_idx == len(members) - 1
                gw_prefix  = "└──" if is_last_gw else "├──"
                gw_bar     = "    " if is_last_gw else "│   "

                gw_id   = gw.get("gatewayId", "?")
                gw_name = gw.get("gatewayName", "FHP")

                meta    = (gateways.get(gw_id) or {})
                hw_ver  = meta.get("sysHdVersion") or gw.get("sysHdVersion")
                try:
                    agate_model = (FRANKLINWH_MODELS.get(int(hw_ver)) or {}).get("model", "aGate") if hw_ver else "aGate"
                except (ValueError, TypeError):
                    agate_model = "aGate"

                gw_node = {
                    "gatewayId":   gw_id,
                    "gatewayName": gw_name,
                    "gatewayModel": agate_model,
                    "group":  {"id": grp_id, "name": group_names.get(grp_id)} if grp_id else None,
                    "status": "Unknown",
                    "grid":   {},
                    "solar":  {},
                    "ct_splits": {},
                    "ahub":   False,
                    "apbox":  {},
                    "mppt":   {},
                    "smart_circuits": [],
                    "v2l":    {},
                    "generator": {},
                    "batteries":  [],
                    "derating": {},
                    "lifecycle": {},
                }
                gw_parent_list.append(gw_node)

                if not json_output:
                    gw_label = f"{gw_name} ({agate_model}: {gw_id})"
                    print(f"{indent}{gw_prefix} {c('green', gw_label)}")

                # ── Per-gateway API calls ──────────────────────────────
                items = []   # line items for the tree display
                try:
                    old_gw = client.gateway
                    client.gateway = gw_id

                    # ── Status (run + mode) ──────────────────────────
                    try:
                        stats = await client.get_stats()
                        run_status = stats.current.run_status_desc or "Unknown"
                        work_mode  = stats.current.work_mode_desc  or "Unknown"
                        status_str = f"{run_status} ({work_mode})"
                        grid_conn  = stats.current.grid_connection_state.value
                        solar_live_kw = stats.current.solar_production
                    except Exception:
                        status_str    = "Unknown"
                        grid_conn     = None
                        solar_live_kw = None

                    # ── TOU sync flags ──────────────────────────────
                    try:
                        modes_res  = await client.get_gateway_tou_list()
                        m_res      = (modes_res.get("result") or {})
                        tou_send   = m_res.get("touSendStatus")
                        stop_mode  = m_res.get("stopMode")
                        alert_msg  = m_res.get("touAlertMessage")
                        if stop_mode:
                            status_str += " [STOP MODE!]"
                        if tou_send:
                            status_str += " [Sync Pending]"
                        if alert_msg:
                            status_str += f" [Alert: {alert_msg}]"
                        gw_node.update({"touSendStatus": tou_send, "stopMode": stop_mode,
                                        "touAlertMessage": alert_msg})
                    except Exception:
                        pass

                    gw_node["status"] = status_str
                    items.append(f"Status: {status_str}")

                    # ── runtimeData (composite) ─────────────────────
                    rt      = {}
                    solar_vo = {}
                    try:
                        comp    = await client.get_device_composite_info()
                        result  = (comp.get("result") or {})
                        rt      = (result.get("runtimeData") or {})
                        solar_vo = (result.get("solarHaveVo") or {}) or {}
                    except Exception:
                        pass

                    # ── Grid status ─────────────────────────────────
                    off_grid_permanent = bool(int(solar_vo.get("offGirdFlag", 0) or 0))
                    off_grid_live      = bool(int(solar_vo.get("offGridFlag", rt.get("offGridFlag", 0)) or 0))
                    if off_grid_permanent:
                        grid_label = "Not Grid-Tied"
                    elif off_grid_live:
                        grid_label = f"Off-Grid (Outage)"
                    elif grid_conn and grid_conn.lower() not in ("", "unknown"):
                        grid_label = grid_conn.replace("_", " ").title()
                    else:
                        grid_label = "Connected"
                    items.append(f"Grid: {grid_label}")
                    gw_node["grid"] = {"label": grid_label, "connected": not (off_grid_permanent or off_grid_live)}

                    # ── Solar PV ────────────────────────────────────
                    def _install(key, default="0"):
                        return rt.get(key, solar_vo.get(key, default))

                    pv1     = str(_install("installPv1Port")) == "1"
                    pv2     = str(_install("installPv2Port")) == "1"
                    proximal = str(_install("installProximalsolar")) == "1"
                    remote  = bool(int(solar_vo.get("remoteSolarEn", 0) or 0))

                    pv_parts = []
                    if pv1:      pv_parts.append("PV1")
                    if pv2:      pv_parts.append("PV2")
                    if proximal: pv_parts.append("Proximal")

                    if pv_parts or remote:
                        pv_detail = " + ".join(pv_parts) if pv_parts else ""
                        if remote:
                            pv_detail = (pv_detail + " + Remote (aPBox)").lstrip(" + ")
                        if solar_live_kw is not None and solar_live_kw > 0:
                            pv_detail += f" ({solar_live_kw:.1f} kW live)"
                        items.append(f"Solar PV: {pv_detail or 'Detected'}")
                        gw_node["solar"] = {
                            "installed": True, "pv1": pv1, "pv2": pv2,
                            "proximal": proximal, "remote": remote,
                            "live_kw": solar_live_kw,
                        }
                    else:
                        items.append("Solar PV: None")
                        gw_node["solar"] = {"installed": False}

                    # ── Split CTs ───────────────────────────────────
                    ct_grid = bool(int(_install("gridSplitCtEn", 0) or 0))
                    ct_pv   = bool(int(_install("pvSplitCtEn", 0) or 0))
                    gw_node["ct_splits"] = {"grid": ct_grid, "pv": ct_pv}
                    if ct_grid:
                        items.append("CT: Split Grid ✓  (two utility services)")
                    if ct_pv:
                        items.append("CT: Split PV ✓  (multiple PV strings metered)")

                    # ── Entrance info (aHub + MPPT flag) ───────────
                    entrance = {}
                    try:
                        entrance = await client.get_entrance_info()
                    except Exception:
                        pass

                    ahub = bool(entrance.get("ahubAddressingFlag"))
                    gw_node["ahub"] = ahub
                    if ahub:
                        items.append("aHub: Detected  (remote SC / solar / generator input)")

                    # ── aPBox ───────────────────────────────────────
                    di     = rt.get("di")
                    do_st  = rt.get("doStatus")
                    apbox_io    = (isinstance(di, list) and any(v != 0 for v in di)) or \
                                  (isinstance(do_st, list) and any(v != 0 for v in do_st))
                    apbox_solar = remote
                    apbox_detected = apbox_io or apbox_solar
                    gw_node["apbox"] = {"detected": apbox_detected, "remote_solar": apbox_solar}
                    if apbox_detected:
                        apbox_label = "aPBox: Detected"
                        if apbox_solar:
                            apbox_label += ", Remote Solar Enabled"
                        items.append(apbox_label)

                    # ── MPPT / aPower S ─────────────────────────────
                    mppt_en = bool(entrance.get("mpptEnFlag") or rt.get("mpptEnFlag") or
                                   solar_vo.get("mpptEnFlag"))
                    # Per-unit: aPower S has non-empty mpptAppVer in get_power_cap_config_list
                    try:
                        pcap_res      = await client.get_power_cap_config_list()
                        apower_configs = (pcap_res.get("result") or [])
                    except Exception:
                        apower_configs = []

                    apower_models = {}
                    derate_kw = None
                    for cfg in apower_configs:
                        sn  = cfg.get("peSn")
                        ver = cfg.get("peHwVersion") or (cfg.get("peHwVerList") or [None])[0]
                        if sn and ver:
                            try:
                                apower_models[sn] = (FRANKLINWH_MODELS.get(int(ver)) or {}).get("model", "aPower")
                            except (ValueError, TypeError):
                                apower_models[sn] = "aPower"
                        # Derating: maxChargingPower or chargingPowerLimited
                        if cfg.get("chargingPowerLimited") and cfg.get("maxChargingPower"):
                            derate_kw = cfg.get("maxChargingPower")

                    mppt_serials = [sn for sn, m in apower_models.items() if "S" in m]
                    gw_node["mppt"] = {"enabled": mppt_en, "units": mppt_serials}
                    if mppt_en:
                        items.append(f"aPower S / DC MPPT: Enabled ({len(mppt_serials)} unit(s))")
                    elif mppt_serials:
                        items.append(f"aPower S: Detected — MPPT Not Enabled")

                    # ── Smart Circuits + Generator (from accessories) ─
                    try:
                        acc_res     = await client.get_accessories(0)
                        accessories = (acc_res.get("result") or [])
                    except Exception:
                        accessories = []

                    sc_items  = []
                    gen_items = []
                    for a in accessories:
                        atype  = a.get("accessoryType", 0)
                        serial = a.get("snSerialNumber") or a.get("sn", "?")
                        acc_name = a.get("accessoryName", "")

                        if atype in (202, 204, 302):   # Smart Circuits
                            sc_items.append({"serial": serial, "type": atype, "name": acc_name})
                        elif atype in (201, 203, 301): # Generator
                            gen_items.append({"serial": serial, "type": atype, "name": acc_name})

                    # ── SC fallback: AU accounts don't return SCs via get_accessories()
                    # Use get_smart_circuits_info() (MQTT cmd 311) when accessories yields nothing
                    if not sc_items:
                        try:
                            sc_info = await client.get_smart_circuits_info()
                            if isinstance(sc_info, dict) and "Sw1Name" in sc_info:
                                from franklinwh_cloud.const.states import SMART_CIRCUIT_MODE
                                sw_merge = sc_info.get("SwMerge", 0) == 1
                                if sw_merge:
                                    slots = [("Sw1Name", "Sw1Mode"), ("Sw3Name", "Sw3Mode")]
                                else:
                                    slots = [("Sw1Name", "Sw1Mode"), ("Sw2Name", "Sw2Mode")]
                                    # Sw3 slot is always returned by firmware but is only
                                    # real hardware on US V2 SC (3 circuits). AU and US V1
                                    # are 2-circuit hardware — include Sw3 only when non-empty
                                    # AND this isn't a known 2-circuit region.
                                    is_au = (meta.get("countryId") or gw.get("countryId")) == 3
                                    if not is_au and sc_info.get("Sw3Name"):
                                        slots.append(("Sw3Name", "Sw3Mode"))
                                for name_key, mode_key in slots:
                                    sw_name = (sc_info.get(name_key) or "").strip()
                                    if sw_name:
                                        sc_items.append({
                                            "serial": None,
                                            "type": 302,   # AU type sentinel
                                            "name": sw_name,
                                            "mode": SMART_CIRCUIT_MODE.get(
                                                sc_info.get(mode_key, 0), str(sc_info.get(mode_key, 0))
                                            ),
                                        })
                        except Exception:
                            pass


                    for sc in sc_items:
                        sc_label = sc["name"] or "Smart Circuit"
                        mode_sfx = f" [{sc['mode']}]" if sc.get("mode") else ""
                        sn_sfx   = f" (SN: {sc['serial']})" if sc.get("serial") else ""
                        items.append(f"Smart Circuit: {sc_label}{mode_sfx}{sn_sfx}")
                    if sc_items:
                        gw_node["smart_circuits"] = sc_items


                    # ── V2L ─────────────────────────────────────────
                    v2l_state_raw = rt.get("v2lRunState")
                    v2l_en        = bool(entrance.get("v2lModeEnable") or rt.get("v2lModeEnable"))
                    if v2l_state_raw is not None or v2l_en:
                        from franklinwh_cloud.const.states import V2L_RUN_STATE
                        v2l_state_str = V2L_RUN_STATE.get(v2l_state_raw, str(v2l_state_raw)) if v2l_state_raw is not None else "Unknown"
                        v2l_label = f"V2L: {'Enabled' if v2l_en else 'Capable, Disabled'} — {v2l_state_str}"
                        items.append(v2l_label)
                        gw_node["v2l"] = {"enabled": v2l_en, "state": v2l_state_str}

                    # ── Generator detail ─────────────────────────────
                    gen_stat_raw = rt.get("genStat")
                    gen_en       = bool(entrance.get("genEn") or rt.get("genEn"))
                    for gen in gen_items:
                        gen_label = gen["name"] or "Generator"
                        state_sfx = ""
                        if gen_stat_raw is not None:
                            from franklinwh_cloud.const.states import GENERATOR_STATE
                            state_sfx = f" — {GENERATOR_STATE.get(gen_stat_raw, str(gen_stat_raw))}"
                        en_sfx = ", Enabled" if gen_en else ""
                        items.append(f"Generator: {gen_label} (SN: {gen['serial']}){en_sfx}{state_sfx}")
                    if gen_items:
                        gw_node["generator"] = {
                            "installed": True, "enabled": gen_en,
                            "state_code": gen_stat_raw, "units": gen_items,
                        }

                    # ── Derating ─────────────────────────────────────
                    if derate_kw:
                        items.append(f"Derating: Charge limited to {derate_kw} kW")
                        gw_node["derating"] = {"active": True, "max_charge_kw": derate_kw}

                    # ── aPower batteries ─────────────────────────────
                    apowers = (rt.get("fhpSn") or [])
                    for ap in apowers:
                        model_name = apower_models.get(ap, "aPower")
                        items.append(f"{model_name} (Serial: {ap})")
                        gw_node["batteries"].append({"type": "battery", "model": model_name, "serial": ap})

                    # ── Lifecycle ────────────────────────────────────
                    try:
                        tou_res = await client.get_tou_dispatch_detail()
                        pto     = (tou_res.get("result") or {}).get("ptoDate")
                    except Exception:
                        pto = None

                    try:
                        w_res   = await client.get_warranty_info()
                        expires = (w_res.get("result") or {}).get("expirationTime")
                    except Exception:
                        expires = None

                    from datetime import datetime
                    active_t  = meta.get("activeTime")
                    create_t  = meta.get("createTime")
                    active_str = datetime.fromtimestamp(active_t / 1000.0).strftime("%Y-%m-%d") if active_t else "N/A"
                    create_str = datetime.fromtimestamp(create_t / 1000.0).strftime("%Y-%m-%d") if create_t else "N/A"
                    pto_str    = pto if pto else "Pending"
                    exp_sfx    = f" | Expires {expires}" if expires else ""

                    gw_node["lifecycle"] = {
                        "createdOn": create_str, "activatedOn": active_str,
                        "expiresOn": expires,    "ptoDate": pto_str,
                    }
                    items.append(f"Lifecycle: Created {create_str} | Activated {active_str}{exp_sfx} | PTO: {pto_str}")

                    # ── Grid profile ─────────────────────────────────
                    try:
                        gp = await client.get_grid_profile_info()
                        grid_profile = "Unknown"
                        if isinstance(gp, dict):
                            for p in (gp.get("list") or []):
                                if p.get("id") == gp.get("currentId", -1):
                                    grid_profile = p.get("name", "Unknown")
                                    break
                    except Exception:
                        grid_profile = "Unknown"

                    if grid_profile != "Unknown":
                        items.append(f"Grid Profile: {grid_profile}")
                        gw_node["grid_profile"] = grid_profile

                    # ── System Readiness (always shown) ─────────────────
                    from franklinwh_cloud.const import AGATE_STATE
                    dev_status = 0
                    try:
                        dev_status = int((comp.get("result") or {}).get("deviceStatus", 0))
                    except Exception:
                        pass
                    agate_ok    = dev_status == 1   # 1=Normal, 0=uninitialised
                    agate_label = AGATE_STATE.get(dev_status, f"Unknown ({dev_status})")
                    items.append(f"{'✅' if agate_ok else '❌'} aGate: {agate_label}")

                    apower_count = len(apowers)
                    try:
                        soc_val = round(float(stats.current.battery_pct), 1)
                        soc_sfx = f", SoC {soc_val}%"
                    except Exception:
                        soc_sfx = ""
                    items.append(f"{'✅' if apower_count > 0 else '❌'} aPower: {apower_count} unit(s){soc_sfx}")

                    pcs_ok = bool(entrance.get("pcsEntrance"))
                    items.append(f"{'✅' if pcs_ok else '❌'} PCS Control: {'Enabled' if pcs_ok else 'Disabled'}")

                    tou_health_ok = not bool(stop_mode)
                    if stop_mode:
                        tou_health_label = "STOP MODE"
                    elif tou_send:
                        tou_health_label = "Sync Pending"
                    else:
                        tou_health_label = "Configured"
                    items.append(f"{'✅' if tou_health_ok else '❌'} TOU Schedule: {tou_health_label}")

                    gw_node["readiness"] = {
                        "agate": {"ok": agate_ok, "label": agate_label},
                        "apower": {"count": apower_count},
                        "pcs": {"enabled": pcs_ok},
                        "tou": {"ok": tou_health_ok, "label": tou_health_label},
                    }

                    client.gateway = old_gw

                except Exception as e:
                    gw_node["error"] = str(e)
                    if not json_output:
                        print(f"{indent}{gw_bar}└── {c('red', f'Error fetching details: {e}')}")
                    continue

                # ── Render tree items ─────────────────────────────────
                if not json_output:
                    for item_idx, item in enumerate(items):
                        is_last_item = item_idx == len(items) - 1 and not diag
                        item_prefix  = "└──" if is_last_item else "├──"
                        print(f"{indent}{gw_bar}{item_prefix} {c('dim', item)}")

                # ── Feature Flags (--diag only, after tree) ───────────
                if diag and not json_output:
                    client.gateway = gw_id   # re-scope for extra diag calls

                    vpp_enrolled = False
                    try:
                        prog = await client.get_programme_info()
                        vpp_enrolled = bool(prog.get("flag", 0)) if isinstance(prog, dict) else bool(prog)
                    except Exception:
                        pass

                    three_phase = str(_install("isThreePhaseInstall")) == "1"

                    try:
                        from franklinwh_cloud.mixins.discover import get_catalog
                        _cat = get_catalog()
                        hw_ver_int = int(meta.get("sysHdVersion") or gw.get("sysHdVersion") or 0)
                        sc_gen = ((_cat.get("agate_models") or {}).get(str(hw_ver_int)) or {}).get("generation", 1)
                    except Exception:
                        sc_gen = 1
                    sc_version = 2 if sc_gen == 2 else 1

                    country_id = int(meta.get("countryId") or gw.get("countryId") or 0)
                    has_gen = bool(gen_items) or bool(entrance.get("genEn"))
                    if not sc_items:
                        v2l_note, v2l_eligible = "No Smart Circuits installed", False
                    elif country_id == 3:
                        v2l_note, v2l_eligible = "AU Smart Circuits have no V2L port", False
                    elif sc_version == 2:
                        v2l_note, v2l_eligible = "V2L built-in (V2 Smart Circuits)", True
                    elif sc_version == 1 and has_gen:
                        v2l_note, v2l_eligible = "V2L via CarSW (V1 SC + Generator Module)", True
                    else:
                        v2l_note, v2l_eligible = "V1 Smart Circuits requires Generator Module for V2L", False

                    pad = f"{indent}{gw_bar}    "
                    print(f"{pad}{c('bold', '🏷️  Feature Flags')}")

                    def _flag(ok, label):
                        print(f"{pad}  {'✅' if ok else '❌'} {label}")

                    if pv_parts or remote:
                        solar_str = " + ".join(pv_parts)
                        if remote:
                            solar_str = (solar_str + " + Remote (aPBox)").lstrip(" + ")
                        if proximal:
                            solar_str = solar_str.replace("Proximal", "Proximal (AC-coupled)")
                        _flag(True, f"Solar: {solar_str}")
                    else:
                        _flag(False, "Solar: Not installed")

                    tariff_ok = bool(entrance.get("tariffSettingFlag"))
                    _flag(tariff_ok, f"TOU/Tariff: {'Configured' if tariff_ok else 'Not configured'}")
                    _flag(pcs_ok, f"PCS Power Control: {'Enabled' if pcs_ok else 'Disabled'}")
                    _flag(not (off_grid_permanent or off_grid_live), f"Grid-Tied: {grid_label}")
                    _flag(mppt_en, f"MPPT (DC-coupled): {'Enabled' if mppt_en else 'Not available'}")
                    _flag(three_phase, f"Three Phase: {'Installed' if three_phase else 'Single-phase'}")
                    _flag(ct_grid, f"CT Split — Grid: {'Installed' if ct_grid else 'Not installed'}")
                    _flag(ct_pv, f"CT Split — PV: {'Installed' if ct_pv else 'Not installed'}")

                    if sc_items:
                        sc_names = ", ".join(sc["name"] for sc in sc_items if sc.get("name"))
                        _flag(True, f"Smart Circuits: V{sc_version}, {len(sc_items)} circuits ({sc_names})")
                        print(f"{pad}      {'✅' if v2l_eligible else '❌'} V2L: {v2l_note}")
                    else:
                        _flag(False, "Smart Circuits: Not installed")

                    _flag(bool(gen_items), f"Generator Module: {'Enabled' if (gen_items and entrance.get('genEn')) else ('Installed' if gen_items else 'Not installed')}")
                    _flag(apbox_detected, f"Remote Solar (aPBox): {'Connected' if apbox_detected else 'Not connected'}")
                    _flag(ahub, f"aHub: {'Detected' if ahub else 'Not detected'}")
                    _flag(vpp_enrolled, f"VPP Programme: {'Enrolled' if vpp_enrolled else 'Not enrolled'}")

                    # ── System Relays ─────────────────────────────────
                    print(f"{pad}{c('bold', '🔧  System Relays')}")
                    RELAY_LABELS = [
                        ("grid_1",      "Grid Relay"),
                        ("generator",   "Generator Relay"),
                        ("solar_pv_1",  "Solar PV Relay"),
                        ("grid_2",      "Grid Relay 2"),
                        ("black_start", "Black Start Relay"),
                        ("solar_pv_2",  "Solar PV Relay 2"),
                        ("apbox",       "BFPV/aPBox Relay"),
                    ]
                    relay_vals = {}
                    main_sw = (rt.get("main_sw") or [])
                    for i, k in enumerate(["grid_1", "generator", "solar_pv_1"]):
                        if i < len(main_sw):
                            relay_vals[k] = not bool(main_sw[i])
                    try:
                        stats_ext = await client.get_stats(include_electrical=True)
                        if hasattr(stats_ext.current, "grid_relay2"):
                            relay_vals["grid_2"]      = not bool(stats_ext.current.grid_relay2)
                            relay_vals["black_start"] = not bool(stats_ext.current.black_start_relay)
                            relay_vals["solar_pv_2"]  = not bool(stats_ext.current.pv_relay2)
                            relay_vals["apbox"]       = not bool(stats_ext.current.bfpv_apbox_relay)
                    except Exception:
                        pass

                    label_w = max(len(lbl) for _, lbl in RELAY_LABELS)
                    for key, lbl in RELAY_LABELS:
                        if key in relay_vals:
                            closed = relay_vals[key]
                            print(f"{pad}  {lbl:>{label_w}}: {'●' if closed else '○'} {'CLOSED' if closed else 'OPEN'}")

                    gw_node["relays"] = relay_vals
                    client.gateway = old_gw   # restore after diag calls


    if json_output:
        print_json_output(topology)


# ── CLI entry point ──────────────────────────────────────────────────

async def run(client, *, json_output: bool = False, save: bool = False,
              redact: str | None = None, label: str | None = None,
              analyze: bool = False, compare_file: str | None = None,
              scope: str = "all", info: bool = False, diag: bool = False):
    """Execute the support command."""

    if info or diag:
        await run_info(client, json_output=json_output, diag=diag)
        return

    # Collect snapshot
    data = await collect_snapshot(client)

    # Apply redaction
    if redact:
        data = redact_snapshot(data, mode=redact)

    # Build envelope
    ts = datetime.now(timezone.utc).isoformat()
    checksum = sign_snapshot(data)
    envelope = {
        "snapshot_version": SNAPSHOT_VERSION,
        "timestamp": ts,
        "gateway": (data.get("identity") or {}).get("serial", "?"),
        "label": label,
        "checksum": f"sha256:{checksum}",
        "data": data,
    }

    # ── Compare mode ─────────────────────────────────────────────
    if compare_file:
        try:
            with open(compare_file, "r") as f:
                old = json.load(f)
        except Exception as e:
            print_error(f"Cannot read {compare_file}: {e}")
            return

        changes = compare_snapshots(old, envelope, scope=scope)
        old_ts = old.get("timestamp", "?")
        old_label = old.get("label", "")

        if json_output:
            print_json_output({"old_timestamp": old_ts, "scope": scope, "changes": changes})
            return

        print_header("FranklinWH Support — Snapshot Comparison")
        print_kv("Previous", f'{old_label or "snapshot"} @ {old_ts}')
        print_kv("Current", f'{label or "snapshot"} @ {ts}')
        print_kv("Scope", scope)
        print()

        if not changes:
            print_success(f"No changes detected (scope: {scope})")
        else:
            current_section = ""
            for ch in changes:
                if ch["section"] != current_section:
                    current_section = ch["section"]
                    print_section("📦" if current_section == "versions" else
                                 "📶" if current_section in ("network", "connectivity") else
                                 "⚡", current_section.title())
                key = ch["key"] or current_section
                old_v = ch["old"] if ch["old"] is not None else "—"
                new_v = ch["new"] if ch["new"] is not None else "—"
                print_kv(key, f'{old_v} → {c("cyan", str(new_v))}  ⬆ CHANGED')
            print()
            print_kv("Total changes", c("yellow", str(len(changes))))
        print()
        return

    # ── Analyze mode ─────────────────────────────────────────────
    if analyze and not json_output:
        print_header("FranklinWH Support — Connectivity Analysis")
        findings = analyze_connectivity(data)

        severity_icon = {"critical": "🔴", "warning": "🟡", "info": "ℹ️", "ok": "✓"}
        for f in findings:
            icon = severity_icon.get(f["severity"], "?")
            color = {"critical": "red", "warning": "yellow", "info": "dim", "ok": "green"}.get(f["severity"], "")
            print_kv(f["check"], c(color, f'{icon} {f["detail"]}'))

        criticals = sum(1 for f in findings if f["severity"] == "critical")
        warnings = sum(1 for f in findings if f["severity"] == "warning")
        print()
        if criticals:
            print_error(f"{criticals} critical issue(s) found")
        elif warnings:
            print_warning(f"{warnings} warning(s) — see above")
        else:
            print_success("All connectivity checks passed")
        print()

        # Still output snapshot if saving
        if not save:
            return

    # ── Save mode ────────────────────────────────────────────────
    if save:
        serial_short = ((data.get("identity") or {}).get("serial", "unknown"))[-8:]
        ts_file = datetime.now().strftime("%Y%m%d_%H%M%S")
        label_part = f"_{label}" if label else ""
        redact_part = "_redacted" if redact else ""
        filename = f"franklinwh_snapshot_{ts_file}_{serial_short}{label_part}{redact_part}.json"

        with open(filename, "w") as f:
            json.dump(envelope, f, indent=2, default=str)

        if not json_output:
            print_success(f"Snapshot saved: {filename}")
            print_kv("Checksum", envelope["checksum"])
            print_kv("Sections", str(len(data)))
            if redact:
                print_kv("Redaction", redact)
        return

    # ── Default: output to stdout ────────────────────────────────
    if json_output:
        print_json_output(envelope)
    else:
        print_header("FranklinWH Support — System Snapshot")
        print_kv("Timestamp", ts)
        print_kv("Gateway", envelope["gateway"])
        print_kv("Checksum", envelope["checksum"])
        if label:
            print_kv("Label", label)
        if redact:
            print_kv("Redaction", redact)

        # Identity
        identity = (data.get("identity") or {})
        if "error" not in identity:
            print_section("🏠", "Identity")
            print_kv("Model", f'{identity.get("model", "?")} ({identity.get("sku", "?")})')
            print_kv("Hardware", identity.get("hardware", "?"))
            print_kv("Country", identity.get("country", "?"))
            print_kv("Timezone", identity.get("timezone", "?"))
            # Lifecycle dates
            from franklinwh_cloud.const import AGATE_ACTIVE
            active_st = identity.get("activeStatus")
            if active_st is not None:
                print_kv("Status", AGATE_ACTIVE.get(active_st, f"Unknown ({active_st})"))
            for date_key, date_label in [("activatedDate", "Activated"), ("createdDate", "Created"), ("installedDate", "Installed")]:
                val = identity.get(date_key)
                if val:
                    print_kv(date_label, val)

        # Versions
        versions = (data.get("versions") or {})
        if "error" not in versions:
            print_section("📦", "Software Versions")
            for key in ("ibgVersion", "awsVersion", "appVersion", "slVersion",
                        "meterVersion", "protocolVer", "cloudApiVersion", "libraryVersion"):
                val = versions.get(key)
                if val:
                    print_kv(key, val)
            # Mobile app versions
            mobile = (versions.get("mobileApp") or {})
            if mobile:
                ios_ver = mobile.get("ios", "?")
                android_ver = mobile.get("android", "?")
                print_kv("Mobile App (iOS)", ios_ver)
                print_kv("Mobile App (Android)", android_ver)

        # Network summary
        net = (data.get("network") or {})
        if "error" not in net:
            conn_type = net.get("currentNetType", 0)
            print_section("📶", "Network")
            print_kv("Active", NET_TYPES.get(conn_type, f"Unknown ({conn_type})"))
            for iface, label_name in [("wifi", "WiFi"), ("eth0", "Eth0"), ("eth1", "Eth1")]:
                idata = (net.get(iface) or {})
                if idata.get("mac"):
                    dhcp = "DHCP" if idata.get("dhcp") else "Static"
                    print_kv(label_name, f'{idata["mac"]}  {dhcp}  IP: {idata.get("ip", "—")}')
            # Cellular/4G
            op = (net.get("operator") or {})
            if op.get("mac"):
                rssi = op.get("rssi", "?")
                rssi_label = f"RSSI: {rssi}/52 (vendor scale)" if rssi != "?" else ""
                print_kv("Cellular", f'{op["mac"]}  {rssi_label}')
            # SIM subscription status
            sim = (data.get("identity") or {}).get("simCardStatus")
            if sim is not None:
                sim_colors = {0: "dim", 1: "red", 2: "green", 3: "red"}
                from franklinwh_cloud.const import SIM_STATUS as SIM_MAP_NET
                sim_text = SIM_MAP_NET.get(sim, f"Unknown ({sim})")
                print_kv("SIM", c(sim_colors.get(sim, ""), sim_text))

        # Connectivity (from FranklinWH mobile app self-test)
        conn = (data.get("connectivity") or {})
        if "error" not in conn:
            print_section("🔗", "App Connectivity Test")
            # Detect stale all-zero from sendMqtt cmdType 339
            all_zero = all(conn.get(k, 0) == 0 for k in ("routerStatus", "netStatus", "awsStatus"))
            api_ok = (data.get("api_health") or {}).get("total_errors", 1) == 0
            if all_zero and api_ok:
                # API is working — connection status is stale
                print_kv("Router", c("yellow", "⚠ Stale (re-run from FranklinWH mobile app)"))
                print_kv("Internet", c("yellow", "⚠ Stale (re-run from FranklinWH mobile app)"))
                print_kv("AWS Cloud", c("green", "● Connected (API responding)"))
            else:
                for key, label_name in [("routerStatus", "Router"), ("netStatus", "Internet"), ("awsStatus", "AWS Cloud")]:
                    val = conn.get(key, 0)
                    status = c("green", "● Connected") if val else c("red", "○ Disconnected")
                    print_kv(label_name, status)

        # Power
        power = (data.get("power") or {})
        if "error" not in power:
            print_section("⚡", "Power")
            print_kv("Solar", f'{power.get("solar_kw", 0):.1f} kW')
            print_kv("Battery", f'{power.get("battery_kw", 0):.1f} kW')
            print_kv("Battery SoC", f'{power.get("battery_soc", 0):.0f}%')
            print_kv("Grid", f'{power.get("grid_kw", 0):.1f} kW  ({power.get("grid_status", "?")})')
            print_kv("Home", f'{power.get("home_load_kw", 0):.1f} kW')
            print_kv("Mode", power.get("operating_mode", "?"))   # work_mode_desc: Time-Of-Use / Self-Consumption etc.
            tou_desc = power.get("tou_mode_desc")
            if tou_desc:
                print_kv("TOU Programme", tou_desc)                # vendor schedule name: Ausgrid EA11 TOU etc.
            run_st = power.get("run_status")
            if run_st:
                print_kv("Run Status", run_st)                     # Standby / Charging / Discharging / VPP Mode
            alarms = power.get("alarms_count", 0)
            if alarms:
                print_kv("Alarms", c("red", str(alarms)))
            temp = power.get("ambient_temp_c")
            if temp is not None and temp != 0.0:
                print_kv("Ambient Temp", f"{temp:.1f} °C")
            # Power flow breakdown
            pf = (power.get("power_flow") or {})
            if pf and any(v for v in pf.values() if v):
                print_kv("→ Grid→Bat", f'{pf.get("grid_charging_battery_kw", 0):.2f} kW')
                print_kv("→ Sol→Grid", f'{pf.get("solar_export_to_grid_kw", 0):.2f} kW')
                print_kv("→ Sol→Bat", f'{pf.get("solar_charging_battery_kw", 0):.2f} kW')
                print_kv("→ Bat→Grid", f'{pf.get("battery_export_to_grid_kw", 0):.2f} kW')
            # Signals
            wifi = power.get("wifi_signal_pct")
            # Read the correctly-named key. mobile_signal_dbm is a DEPRECATED
            # alias carrying the same percentage, kept only for output
            # compatibility — consuming it here is what produced "4G 45 dBm"
            # for a value that is a percentage. DEF-SUPPORT-RSSI-DBM.
            mob = power.get("mobile_signal_pct", power.get("mobile_signal_dbm"))
            if wifi is not None or mob is not None:
                sig_parts = []
                if wifi is not None:
                    sig_parts.append(f"WiFi {wifi}%")
                if mob is not None:
                    sig_parts.append(f"4G {mob}%")
                print_kv("Signal", "  ".join(sig_parts))
            # Per-pack aPower state
            from franklinwh_cloud.const.states import BMS_STATE as _BMS_STATE
            _ap_serials = power.get("apower_serials")
            _ap_soc     = power.get("apower_soc")
            _ap_bms     = power.get("apower_bms_mode")
            # Normalise: model stores these as list or str repr of list
            def _as_list(v):
                if isinstance(v, list):
                    return v
                if isinstance(v, str):
                    import ast
                    try:
                        r = ast.literal_eval(v)
                        return r if isinstance(r, list) else [r]
                    except Exception:
                        return [v]
                return [v] if v is not None else []
            _serials = _as_list(_ap_serials)
            _socs    = _as_list(_ap_soc)
            _bmss    = _as_list(_ap_bms)
            if _serials or _socs or _bmss:
                # Header: aPower [SN1, SN2, ...]
                if _serials:
                    print_kv("aPower", f"[{', '.join(str(s) for s in _serials)}]")
                # SoC per pack
                if _socs:
                    soc_vals = ", ".join(f"{float(s):.1f}%" for s in _socs)
                    print_kv("  SoC", soc_vals)
                # BMS mode per pack, decoded
                if _bmss:
                    bms_vals = ", ".join(_BMS_STATE.get(int(b), f"mode {b}") for b in _bmss)
                    print_kv("  BMS", bms_vals)

        # Daily Totals
        totals = (data.get("totals") or {})
        if "error" not in totals and totals:
            print_section("📊", "Today's Totals")
            print_kv("Solar", f'{totals.get("solar_kwh", 0):.2f} kWh')
            grid_imp = totals.get("grid_import_kwh", 0)
            grid_exp = totals.get("grid_export_kwh", 0)
            print_kv("Grid Import", f'{grid_imp:.2f} kWh')
            print_kv("Grid Export", f'{grid_exp:.2f} kWh')
            print_kv("Battery Charge", f'{totals.get("battery_charge_kwh", 0):.2f} kWh')
            print_kv("Battery Discharge", f'{totals.get("battery_discharge_kwh", 0):.2f} kWh')
            print_kv("Home Use", f'{totals.get("home_use_kwh", 0):.2f} kWh')

        # Electrical (211)
        elec = (data.get("electrical") or {})
        if "error" not in elec and elec:
            print_section("🔌", "Electrical (211)")
            v1 = elec.get("grid_voltage_l1_v")
            v2 = elec.get("grid_voltage_l2_v")
            if v1 is not None:
                vstr = f"{v1:.0f} V"
                if v2 is not None and v2 != 0:
                    vstr += f" / {v2:.0f} V"
                print_kv("Grid Voltage", vstr)
            lv = elec.get("grid_line_voltage_v")
            if lv is not None and lv != 0:
                print_kv("Line Voltage", f"{lv:.0f} V")
            freq = elec.get("grid_frequency_hz")
            set_freq = elec.get("grid_set_freq_hz")
            if freq is not None:
                fstr = f"{freq:.2f} Hz"
                if set_freq is not None:
                    fstr += f"  (set: {set_freq:.2f} Hz)"
                print_kv("Frequency", fstr)
            i1 = elec.get("grid_current_l1_a")
            i2 = elec.get("grid_current_l2_a")
            if i1 is not None:
                istr = f"{i1:.2f} A"
                if i2 is not None:
                    istr += f" / {i2:.2f} A"
                print_kv("Grid Current", istr)
            dsp = elec.get("dsp_run_status")
            if dsp is not None:
                print_kv("DSP Run Status", str(dsp))

        # Run analysis inline
        findings = analyze_connectivity(data)
        criticals = [f for f in findings if f["severity"] == "critical"]
        warnings_list = [f for f in findings if f["severity"] == "warning"]
        if criticals or warnings_list:
            print_section("⚠️", "Issues Detected")
            for f in criticals:
                print_kv(f["check"], c("red", f'🔴 {f["detail"]}'))
            for f in warnings_list:
                print_kv(f["check"], c("yellow", f'🟡 {f["detail"]}'))

        # Warranty
        warranty = (data.get("warranty") or {})
        if "error" not in warranty and warranty.get("expirationTime"):
            print_section("📋", "Warranty")

            def _days_human(n):
                """Format a day count as 'X years, Y days (N days)'."""
                if n is None:
                    return None
                n = int(n)
                yrs, rem = divmod(abs(n), 365)
                if yrs:
                    return f"{yrs} year{'s' if yrs != 1 else ''}, {rem} day{'s' if rem != 1 else ''}  ({abs(n):,} days)"
                return f"{abs(n)} day{'s' if abs(n) != 1 else ''}"

            # ─ Expiry
            expires = warranty.get("expirationTime", "?")
            days_left = warranty.get("days_to_expiry")
            if days_left is not None:
                if days_left < 0:
                    expiry_color = "red"
                    expiry_tag = f"EXPIRED {_days_human(abs(days_left))} ago"
                elif days_left <= 90:
                    expiry_color, expiry_tag = "yellow", f"{_days_human(days_left)} remaining"
                else:
                    expiry_color, expiry_tag = "green", f"{_days_human(days_left)} remaining"
                print_kv("Expires", f"{expires}  {c(expiry_color, expiry_tag)}")
            else:
                print_kv("Expires", expires)

            # ─ Age since installation
            d_install = warranty.get("days_since_install")
            if d_install is not None:
                print_kv("Since Install", _days_human(d_install))

            # ─ Age since PTO
            d_pto = warranty.get("days_since_pto")
            if d_pto is not None:
                print_kv("Since PTO", _days_human(d_pto))

            # ─ Throughput
            tp   = warranty.get("throughput_kWh", 0)
            rem  = warranty.get("remainThroughput_kWh", 0)
            used = warranty.get("used_kWh", 0)
            if tp > 0:
                pct_used = round((used / tp) * 100, 1)
                pct_rem  = round((rem  / tp) * 100, 1)
                tp_color = "red" if pct_rem < 15 else "yellow" if pct_rem < 30 else "green"
                print_kv("Throughput", f"{tp:,.0f} kWh rated  | {used:,.0f} kWh used ({pct_used}%)  |  {c(tp_color, f'{rem:,.0f} kWh left ({pct_rem}%)')}")

            # ─ Average daily throughput
            avg_inst = warranty.get("avg_kwh_per_day_install")
            avg_pto  = warranty.get("avg_kwh_per_day_pto")
            if avg_inst is not None or avg_pto is not None:
                avg_parts = []
                if avg_inst is not None:
                    avg_parts.append(f"{avg_inst:.2f} kWh/day since install")
                if avg_pto is not None and avg_pto != avg_inst:
                    avg_parts.append(f"{avg_pto:.2f} kWh/day since PTO")
                print_kv("Avg Daily kWh", "  |  ".join(avg_parts))

            # ─ Budget/day = rated kWh ÷ total warranty term
            #   (what the warranty ALLOWS you to use each day on average)
            forecast = warranty.get("daily_kwh_forecast")
            total_wdays = warranty.get("total_warranty_days")
            if forecast is not None:
                tw_h = _days_human(total_wdays) if total_wdays else f"{total_wdays} days"
                print_kv("Budget/day", f"{forecast:.2f} kWh/day  ({tp:,.0f} kWh ÷ {tw_h} warranty term)")

            # ─ Remaining/day = remaining kWh ÷ days to expiry
            #   (the pace required from today to exhaust remaining budget by expiry)
            needed = warranty.get("daily_rem_needed")
            if needed is not None and days_left and days_left > 0:
                needed_color = "green" if (avg_inst or 0) <= needed else "yellow"
                print_kv("Remaining/day", c(needed_color, f"{needed:.2f} kWh/day  ({rem:,.0f} kWh remaining ÷ {_days_human(days_left)} to expiry)"))

            # ─ Per-device
            for dev in (warranty.get("devices") or []):
                print_kv(f"  {dev.get('model', '?')}", f"Expires: {dev.get('expires', '?')}")

        # Programmes, Schemes & VPP
        prog = (data.get("programmes") or {})
        if "error" not in prog and prog:
            print_section("🔌", "Grid & Schemes")

            # Grid compliance profile (from API — never hardcoded)
            gp = prog.get("grid_profile")
            if gp:
                print_kv("Grid Profile", gp)

            # ─ Operational validity flags — red warning when False
            solar_ok = prog.get("solar_connected", True)
            grid_ok  = prog.get("grid_connected", True)
            if not solar_ok:
                print_kv("Solar", c("red", "⚠️  Not connected to aGate ports — solar relay/MPPT/CT functions invalid"))
            if not grid_ok:
                print_kv("Grid", c("red", "⚠️  Off-grid configuration — grid charge/export operations not valid"))

            # aHub
            if prog.get("ahub_detected"):
                print_kv("aHub", c("green", "✅ Detected"))

            # CT calibration required
            if prog.get("need_ct_test"):
                print_kv("CT Test", c("yellow", "⚠️  CT calibration required"))

            # NEM type (US-CA only — omitted entirely for AU/other)
            nem = prog.get("nem_type")
            if nem and nem != "None":
                print_kv("NEM Type", nem)

            # DER schedule (relevant where SGIP/AS/DEMS applies)
            der = prog.get("der_schedule")
            if der and der not in ("", "Other", "None", None):
                print_kv("DER Schedule", der)

            # Scheme eligibility flags — only print those that are True
            _scheme_flags = [
                ("sgip",       "SGIP",          "Self-Generation Incentive Program (CA)"),
                ("bb",         "Backup Battery", "Backup Battery scheme"),
                ("ja12",       "JA12",           "JA12 grid compliance"),
                ("sdcp",       "SDCP",           "Smart Device Control Program"),
                ("pcs_enabled","PCS",            "Power Control System enabled"),
            ]
            active_schemes = [(label, desc) for key, label, desc in _scheme_flags if prog.get(key)]
            for label, desc in active_schemes:
                print_kv(label, c("green", f"✅ Enrolled  ({desc})"))

            # Grid limits (from get_power_control_settings)
            # -1 = Unlimited, 0 = Not allowed/Disabled, >0 = kW cap
            def _grid_limit_label(val, unlimited_txt="Unlimited", disabled_txt="Not allowed"):
                if val is None:
                    return c("dim", "—")
                val = float(val)
                if val < 0:           return c("green", unlimited_txt)
                if val == 0:          return c("yellow", disabled_txt)
                return f"{val:.1f} kW"

            _pcs = (prog.get("grid_limits_raw") or {}) or {}
            if _pcs:
                print_kv("Grid Import",    _grid_limit_label(_pcs.get("gridMax"),               "Unlimited import",  "Charge from grid not allowed"))
                print_kv("Grid Export",    _grid_limit_label(_pcs.get("gridFeedMax"),            "Unlimited export",  "Export not allowed"))
                print_kv("Global Charge",  _grid_limit_label(_pcs.get("globalGridChargeMax"),    "Unlimited",         "Disabled"))
                print_kv("Global Export",  _grid_limit_label(_pcs.get("globalGridDischargeMax"), "Unlimited",         "Disabled"))
                if _pcs.get("notControlExportSolar"):
                    print_kv("Solar Export", c("dim", "Not controlled (solar export unmetered)"))
                if _pcs.get("peakDemandGridMax") is not None:
                    print_kv("Peak Demand",  _grid_limit_label(_pcs.get("peakDemandGridMax")))

            # ─ Charge derating (aPower 2+)
            if prog.get("charging_power_limited"):
                print_kv("Charge Derating", c("yellow", "⚠️  Active — charge power limited to protect service breaker (aPower 2+)"))

            # Battery savings
            if prog.get("battery_savings_flag"):
                print_kv("Battery Savings", c("green", "✅ Active"))

            # VPP
            print_section("🏭", "VPP Programme")
            vpp_enrolled = prog.get("vpp_enrolled", False)
            if vpp_enrolled:
                prog_name    = prog.get("vpp_programme_name") or ""
                partner_name = prog.get("vpp_partner_name") or ""
                label = prog_name or "Enrolled"
                if partner_name:
                    label += f"  ({partner_name})"
                print_kv("Enrolled", c("green", f"✅ {label}"))
                soc     = prog.get("vpp_soc_pct")
                min_soc = prog.get("vpp_min_soc_pct")
                max_soc = prog.get("vpp_max_soc_pct")
                if soc is not None:
                    print_kv("VPP SoC", f"{soc}%  (range: {min_soc}% – {max_soc}%)")
                if prog.get("vpp_active_today"):
                    print_kv("Today", c("yellow", "⚡ VPP dispatch active today"))
            else:
                print_kv("Enrolled", c("dim", "Not enrolled"))
        # Operating Modes
        om = (data.get("operating_modes") or {})
        if "error" not in om and om.get("modes"):
            print_section("⚙️", "Operating Modes")

            if om.get("stop_mode"):
                print_kv("WARNING", c("red", "⚠️  STOP MODE active — gateway may be locked out"))

            for m in om["modes"]:
                wm_name = m.get("displayName") or m.get("name", "?")
                available = m.get("available", False)
                configured = m.get("configured", False)

                if available:
                    soc = m.get("soc")
                    min_soc = m.get("minSoc")
                    max_soc = m.get("maxSoc")
                    soc_str = f"  SoC: {soc}%" if soc is not None else ""
                    if min_soc is not None and max_soc is not None and (min_soc != 0 or max_soc != 100):
                        soc_str += f"  (range: {min_soc}–{max_soc}%)"
                    print_kv(f"✅ {wm_name}", c("green", f"Available{soc_str}"))
                elif not configured:
                    reason = m.get("reason") or "Not configured"
                    print_kv(f"❌ {m.get('name', '?')}", c("yellow", f"Not configured — {reason}"))
                else:
                    # Configured but prereq not met (shouldn't normally happen but handle gracefully)
                    reason = m.get("reason") or "Prerequisite not met"
                    print_kv(f"❌ {wm_name}", c("yellow", f"Not available — {reason}"))

            if om.get("grid_charge_enabled"):
                print_kv("Grid Charge", c("green", "✅ Enabled"))
            if om.get("backup_forever_flag"):
                print_kv("Backup Forever", c("dim", "Enabled"))

        # TOU / Grid status
        tou = (data.get("tou_status") or {})
        if "error" not in tou and tou:
            print_section("🏷️", "TOU / Grid")
            pto = tou.get("ptoDate")
            if pto:
                print_kv("PTO Date", pto)

            # Utility / tariff identity
            plan    = tou.get("tariffPlan")
            company = tou.get("electricCompany", "")
            co_id   = tou.get("electricCompanyId")
            if plan:
                print_kv("Tariff", plan)
            if company:
                co_str = company.strip()
                if co_id is not None and int(co_id) != -1:
                    co_str += f"  (ID: {co_id})"
                print_kv("Utility", co_str)

            # Template / schedule IDs (useful for support tickets and compare)
            tmpl_id  = tou.get("templateId")
            inst_id  = tou.get("templateInstanceId")
            province = tou.get("provinceEn")
            if tmpl_id is not None:
                id_str = f"Template {tmpl_id}" if int(tmpl_id) != 0 else "User-defined (templateId=0)"
                if inst_id:
                    id_str += f"  ·  Instance {inst_id}"
                print_kv("Schedule ID", id_str)
            if province:
                print_kv("Province", province)

            updated = tou.get("lastUpdated")
            if updated:
                print_kv("Last Updated", updated)

            tariff_set = tou.get("tariffSettingFlag")
            print_kv("Tariff Configured", c("green", "Yes") if tariff_set else c("red", "No"))
            online = tou.get("onlineFlag")
            if online is not None:
                print_kv("Online", c("green", "Yes") if online else c("red", "No"))
            alert = tou.get("alertMessage")
            if alert:
                print_kv("Alert", c("yellow", str(alert)))
            send = tou.get("sendStatus")
            if send:
                print_kv("Send Status", c("yellow", "Pending"))
            cap = tou.get("batteryRatedCapacity_kWh")
            if cap:
                print_kv("Battery Capacity", f"{cap} kWh ({tou.get('apowerCount', '?')} aPower)")

        # Schema fingerprint
        schema = (data.get("schema_fingerprint") or {})
        if schema:
            print_section("🔑", "API Schema")
            print_kv("Fingerprint", schema.get("fingerprint", "?"))
            print_kv("Total keys", str(schema.get("key_count", 0)))

        print()
        print_kv("Tip", c("dim", "Use --save to export, --redact for sharing, --compare to diff"))
        print()



