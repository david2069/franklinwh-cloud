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

SNAPSHOT_VERSION = 2

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
        for result in data.get("results", []):
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
                    "wifi_config", "switches", "batteries", "power", "relays"):
        data = snapshot.get(section, {})
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
    identity = d.get("identity", {})
    if "serial" in identity:
        identity["serial"] = _redact_serial(identity["serial"], mode)
    if "email" in identity:
        identity["email"] = _redact_email(identity["email"], mode)
    if "address" in identity:
        identity["address"] = "[REDACTED]" if identity["address"] else identity["address"]
    for gw in identity.get("gateway_sns", []):
        pass  # Already redacted via serial

    # Network
    net = d.get("network", {})
    for iface in ("wifi", "eth0", "eth1", "operator"):
        idata = net.get(iface, {})
        if "mac" in idata:
            idata["mac"] = _redact_mac(idata.get("mac", ""), mode)
        if "ip" in idata:
            idata["ip"] = _redact_ip(idata.get("ip", ""), mode)
        if "gateway" in idata:
            idata["gateway"] = _redact_ip(idata.get("gateway", ""), mode)

    # WiFi config
    wifi_cfg = d.get("wifi_config", {})
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
        "batteries": {},
        "relays": {},
        "warranty": {},
        "tou_status": {},
        "api_health": {},
    }

    # ── Identity ─────────────────────────────────────────────────
    try:
        gw_res = await client.get_home_gateway_list()
        gateways = gw_res.get("result", [])
        gw = next((g for g in gateways if g.get("id") == client.gateway), {})
        from franklinwh_cloud.const import FRANKLINWH_MODELS, COUNTRY_ID
        hw_ver = int(gw.get("sysHdVersion", 0))
        model_info = FRANKLINWH_MODELS.get(hw_ver, {})
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
        result = agate.get("result", {})
        snapshot["versions"]["ibgVersion"] = result.get("ibgVersion")
        snapshot["versions"]["awsVersion"] = result.get("awsVersion")
        snapshot["versions"]["appVersion"] = result.get("appVersion")
        snapshot["versions"]["slVersion"] = result.get("slVersion")
        snapshot["versions"]["meterVersion"] = result.get("meterVersion")
        snapshot["versions"]["protocolVer"] = result.get("protocolVer")
        snapshot["versions"]["connType"] = result.get("connType")
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

    # ── Power snapshot ───────────────────────────────────────────
    try:
        stats = await client.get_stats()
        cur = stats.current
        snapshot["power"] = {
            "solar_kw": cur.solar_production,
            "battery_kw": cur.battery_use,
            "battery_soc": cur.battery_soc,
            "grid_kw": cur.grid_use,
            "grid_status": "Outage" if cur.grid_outage else "Connected",
            "home_load_kw": cur.home_load,
            "operating_mode": cur.work_mode_desc,
            "run_status": cur.run_status_dec,
        }
    except Exception as e:
        snapshot["power"]["error"] = str(e)

    # ── Relays ───────────────────────────────────────────────────
    try:
        comp = await client.get_device_composite_info()
        rt = comp.get("result", {}).get("runtimeData", {})
        main_sw = rt.get("main_sw", [])
        snapshot["relays"] = {
            "grid_relay": main_sw[0] if len(main_sw) > 0 else None,
            "generator_relay": main_sw[1] if len(main_sw) > 1 else None,
            "solar_pv_relay": main_sw[2] if len(main_sw) > 2 else None,
            "grid_relay2": stats.grid_relay2 if 'stats' in locals() else None,
            "solar_pv_relay2": stats.pv_relay2 if 'stats' in locals() else None,
            "black_start": stats.black_start if 'stats' in locals() else None,
        }

        # Extrapolate custom names and pure equipment listings
        try:
            sc_info = await client.get_smart_circuits_info()
        except Exception:
            sc_info = {}

        try:
            raw_equip = await client.get_accessories(0)
            equip_list = raw_equip.get("result", []) if isinstance(raw_equip, dict) else []
        except Exception:
            equip_list = []

        snapshot["accessories"] = {
            "smart_circuits": {
                "Sw1Name": sc_info.get("Sw1Name"),
                "Sw1Mode": rt.get("Sw1Mode"),
                "Sw1ProLoad": rt.get("Sw1ProLoad"),
                "Sw1MsgType": rt.get("Sw1MsgType"),
                "Sw2Name": sc_info.get("Sw2Name"),
                "Sw2Mode": rt.get("Sw2Mode"),
                "Sw3Name": sc_info.get("Sw3Name"),
                "Sw3Mode": rt.get("Sw3Mode"),
                "SwMerge": sc_info.get("SwMerge"),
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
                "di": rt.get("di"),
                "doStatus": rt.get("doStatus"),
            },
            "hardware_registry_dump": equip_list,
        }
    except Exception as e:
        snapshot["relays"]["error"] = str(e)
        snapshot["accessories"] = {"error": str(e)}

    # ── Warranty ─────────────────────────────────────────────────
    try:
        w_res = await client.get_warranty_info()
        w = w_res.get("result", {})
        snapshot["warranty"] = {
            "expirationTime": w.get("expirationTime"),
            "throughput_kWh": (w.get("throughput", 0) or 0) * 1000,
            "remainThroughput_kWh": w.get("remainThroughput", 0) or 0,
        }
        devices = w.get("deviceExpirationList", [])
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
        tou = tou_res.get("result", {})
        template = tou.get("template", {})
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
            "tariffPlan": template.get("name"),
            "electricCompany": template.get("electricCompany"),
            "workMode": template.get("workMode"),
            "lastUpdated": template.get("updateTime"),
        }
    except Exception as e:
        snapshot["tou_status"]["error"] = str(e)

    # ── API health ───────────────────────────────────────────────
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

NET_TYPES = {
    0: "None", 1: "WiFi", 2: "Ethernet", 3: "WiFi",
    4: "4G/LTE", 5: "WiFi+4G", 6: "Ethernet+4G",
    13: "WiFi+Ethernet+4G",
}


def analyze_connectivity(snapshot: dict) -> list[dict]:
    """Run connectivity rules against snapshot data.

    Returns list of findings: {severity, check, detail}
    severity: "critical", "warning", "info", "ok"
    """
    findings = []
    net = snapshot.get("network", {})
    conn = snapshot.get("connectivity", {})
    switches = snapshot.get("switches", {})
    wifi_cfg = snapshot.get("wifi_config", {})

    # AWS cloud status
    # Cross-check: if other snapshot sections have real data, the cloud API
    # is clearly working.  The sendMqtt cmdType-339 status self-report from
    # the aGate can return all-zeros even when connectivity is fine.
    api_reachable = bool(
        snapshot.get("versions", {}).get("ibgVersion")
        or snapshot.get("power", {}).get("solar_kw") is not None
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
        wifi = net.get("wifi", {})
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
            idata = net.get(iface, {})
            eth_mac = idata.get("mac", "")
            eth_ip = idata.get("ip", "")
            if eth_mac and eth_ip in ("0.0.0.0", ""):
                findings.append({"severity": "warning", "check": label,
                                 "detail": f"MAC {eth_mac} present but IP {eth_ip or 'empty'} (not configured?)"})
            elif eth_mac and eth_ip and eth_ip != "0.0.0.0":
                findings.append({"severity": "ok", "check": label,
                                 "detail": f"IP {eth_ip}"})

        # Cellular
        op = net.get("operator", {})
        if op.get("mac"):
            rssi = op.get("rssi", "?")
            findings.append({"severity": "info", "check": "Cellular",
                             "detail": f"Available (RSSI: {rssi} dBm) — backup ready"})

        # 4G fallback detection
        conn_type = net.get("currentNetType", 0)
        if conn_type in (4, 5, 6, 13) and wifi_mac:
            findings.append({"severity": "warning", "check": "4G Fallback",
                             "detail": f"Active (connType {conn_type}: {NET_TYPES.get(conn_type, '?')}) — WiFi/Ethernet may have failed"})

        # DNS checks
        wifi_dns = wifi.get("dns", "")
        eth0_dns = net.get("eth0", {}).get("dns", "")
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
                ip = net.get(iface, {}).get("ip", "")
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
    "power": ["power", "relays"],
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
        old_section = old_data.get(section, {})
        new_section = new_data.get(section, {})

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
        result = res.get("result", {})
        # result is a dict with runtimeData, not a list
        ok = res.get("success", res.get("code") == 200)
        detail = f"{elapsed:.0f}ms"
        apower_serial = None
        if isinstance(result, dict) and result.get("runtimeData"):
            rd = result["runtimeData"]
            soc = rd.get("soc")
            if soc is not None:
                detail += f" — SoC {soc:.0f}%"
            fhp_sns = rd.get("fhpSn", [])
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
            config["connType"] = r.get("currentNetType", 0)
            config["connTypeName"] = NET_TYPES.get(config["connType"], f"Type {config['connType']}")

            wifi = r.get("wifi", {})
            if wifi.get("ip") and wifi["ip"] != "0.0.0.0":
                config["primary"] = f"WiFi (DHCP)  IP: {wifi['ip']}"
            eth0 = r.get("eth0", {})
            if eth0.get("ip") and eth0["ip"] != "0.0.0.0":
                config["primary"] = f"Ethernet (IP: {eth0['ip']})"

            op = r.get("operator", {})
            if op.get("mac"):
                config["backup"] = f"4G/LTE  RSSI: {op.get('rssi', '?')} dBm"
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
    print_kv("connType", f"{net_config.get('connType', '?')} ({conn_name})")
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
        for name, test in fem.get("sub_tests", {}).items():
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

async def run_info(client, json_output: bool = False):
    """Implement franklinwh-cli support --info mapping the account taxonomy."""
    from franklinwh_cloud.cli_output import c, print_json_output
    import json
    
    email = getattr(client.fetcher, "email", "UnknownUser")
    user_id = getattr(client.fetcher, "user_id", "Unknown")
    
    try:
        site = await client.siteinfo()
        user_id = site.get("userId", user_id)
        email = site.get("email", email)
    except Exception:
        pass

    try:
        site_info_res = await client.get_site_and_device_info()
        sites_data = site_info_res.get("result", [])
        
        # Parallel fetch gateways for lifecycle dates
        try:
            gw_res = await client.get_home_gateway_list()
            gateways = {g.get("id"): g for g in gw_res.get("result", []) if g.get("id")}
        except Exception:
            gateways = {}
            
    except Exception as e:
        print_error(f"Failed to fetch site list: {e}")
        return

    # We will build a unified output dictionary so JSON clients get everything
    topology = {"email": email, "userId": user_id, "sites": []}
    
    if not json_output:
        print(f"{c('cyan', email)} (UserId: {user_id})")
    
    for site_idx, site in enumerate(sites_data):
        is_last_site = site_idx == len(sites_data) - 1
        site_prefix = "└──" if is_last_site else "├──"
        site_bar = "    " if is_last_site else "│   "
        
        site_name = site.get("siteName") or "Default Site"
        site_id = site.get("siteId") or "Unknown"
        address = site.get("completeAddress", "")
        
        site_node = {
            "siteName": site_name,
            "siteId": site_id,
            "completeAddress": address,
            "gateways": []
        }
        topology["sites"].append(site_node)
        
        if not json_output:
            site_label = f"{site_name} (SiteId: {site_id})"
            if address:
                site_label += f" — {address}"
            print(f"{site_prefix} {c('yellow', site_label)}")
        
        gws = site.get("basicDeviceInfoVOList", [])
        for gw_idx, gw in enumerate(gws):
            is_last_gw = gw_idx == len(gws) - 1
            gw_prefix = "└──" if is_last_gw else "├──"
            gw_bar = "    " if is_last_gw else "│   "
            
            gw_id = gw.get("gatewayId", "?")
            gw_name = gw.get("gatewayName", "FHP")
            gw_addr = gw.get("completeAddress", "")
            
            from franklinwh_cloud.const import FRANKLINWH_MODELS
            hw_ver = gw.get("sysHdVersion")
            agate_model = FRANKLINWH_MODELS.get(int(hw_ver), {}).get("model", "aGate") if hw_ver else "aGate"
            
            gw_node = {
                "gatewayId": gw_id,
                "gatewayName": gw_name,
                "gatewayModel": agate_model,
                "completeAddress": gw_addr,
                "status": "Unknown",
                "lifecycle": {},
                "devices": []
            }
            site_node["gateways"].append(gw_node)
            
            if not json_output:
                gw_label = f"{gw_name} ({agate_model}: {gw_id})"
                if gw_addr and gw_addr != address:
                    gw_label += f" — {gw_addr}"
                print(f"{site_bar}{gw_prefix} {c('green', gw_label)}")
            
            try:
                old_gw = client.gateway
                client.gateway = gw_id
                
                comp = await client.get_device_composite_info()
                rt = comp.get("result", {}).get("runtimeData", {})
                
                apowers = rt.get("fhpSn", [])
                solar = rt.get("solarVo", [])
                
                from datetime import datetime
                
                try:
                    stats = await client.get_stats()
                    run_status = stats.current.run_status_dec
                    work_mode = stats.current.work_mode_desc
                    status_str = f"{run_status} ({work_mode})"
                except Exception:
                    status_str = "Unknown"
                    
                sync_flags = {}
                try:
                    modes_res = await client.get_gateway_tou_list()
                    m_res = modes_res.get("result", {})
                    tou_send = m_res.get("touSendStatus")
                    stop_mode = m_res.get("stopMode")
                    alert_msg = m_res.get("touAlertMessage")
                    
                    if stop_mode:
                        status_str += " [STOP MODE!]"
                    if tou_send:
                        status_str += f" [Sync Pending]"
                    if alert_msg:
                        status_str += f" [Alert: {alert_msg}]"
                        
                    sync_flags = {
                        "touSendStatus": tou_send,
                        "stopMode": stop_mode,
                        "touAlertMessage": alert_msg
                    }
                except Exception:
                    pass
                
                gw_node["status"] = status_str
                gw_node.update(sync_flags)
                    
                try:
                    tou_res = await client.get_tou_dispatch_detail()
                    pto = tou_res.get("result", {}).get("ptoDate")
                except Exception:
                    pto = None
                    
                try:
                    w_res = await client.get_warranty_info()
                    expires = w_res.get("result", {}).get("expirationTime")
                except Exception:
                    expires = None
                
                gw_meta = gateways.get(gw_id, {})
                active_t = gw_meta.get("activeTime")
                create_t = gw_meta.get("createTime")
                
                active_str = datetime.fromtimestamp(active_t / 1000.0).strftime("%Y-%m-%d") if active_t else "N/A"
                create_str = datetime.fromtimestamp(create_t / 1000.0).strftime("%Y-%m-%d") if create_t else "N/A"
                pto_str = pto if pto else "Pending"
                exp_str = f" | Expires {expires}" if expires else ""
                
                gw_node["lifecycle"] = {
                    "createdOn": create_str,
                    "activatedOn": active_str,
                    "expiresOn": expires,
                    "ptoDate": pto_str
                }
                
                try:
                    gp = await client.get_grid_profile_info()
                    grid_profile = "Unknown"
                    if isinstance(gp, dict):
                        for p in gp.get("list", []):
                            if p.get("id") == gp.get("currentId", -1):
                                grid_profile = p.get("name", "Unknown")
                                break
                except Exception:
                    grid_profile = "Unknown"
                if grid_profile != "Unknown":
                    gw_node["grid_profile"] = grid_profile
                
                items = [
                    f"Status: {status_str}",
                    f"Lifecycle: Created {create_str} | Activated {active_str}{exp_str} | PTO: {pto_str}"
                ]
                if grid_profile != "Unknown":
                    items.append(f"Grid Profile: {grid_profile}")
                
                try:
                    pcap_res = await client.get_power_cap_config_list()
                    apower_configs = pcap_res.get("result", [])
                except Exception:
                    apower_configs = []

                apower_models = {}
                for cfg in apower_configs:
                    sn = cfg.get("peSn")
                    ver = cfg.get("peHwVersion") or (cfg.get("peHwVerList") or [None])[0]
                    if sn and ver:
                        try:
                            model_dict = FRANKLINWH_MODELS.get(int(ver), {})
                            apower_models[sn] = model_dict.get("model", "aPower")
                        except (ValueError, TypeError):
                            pass
                            
                for i, ap in enumerate(apowers):
                    model_name = apower_models.get(ap, "aPower")
                    items.append(f"{model_name} (Serial: {ap})")
                    gw_node["devices"].append({"type": "battery", "model": model_name, "serial": ap})
                
                if solar:
                    items.append(f"Solar PV: {len(solar)} strings")
                    gw_node["devices"].append({"type": "solar", "count": len(solar)})
                
                try:
                    acc_res = await client.get_accessories(0)
                    accessories = acc_res.get("result", [])
                except Exception:
                    accessories = []
                
                if accessories:
                    sc_cnt = sum(1 for a in accessories if a.get("accessoryType") in (202, 204, 302))
                    gen_cnt = sum(1 for a in accessories if a.get("accessoryType") in (201, 203, 301))
                    
                    if sc_cnt:
                        items.append(f"Smart Circuit × {sc_cnt}")
                        gw_node["devices"].append({"type": "smart_circuit", "count": sc_cnt})
                    if gen_cnt:
                        items.append(f"Generator × {gen_cnt}")
                        gw_node["devices"].append({"type": "generator", "count": gen_cnt})
                
                if not json_output:
                    for item_idx, item in enumerate(items):
                        is_last_item = item_idx == len(items) - 1
                        item_prefix = "└──" if is_last_item else "├──"
                        print(f"{site_bar}{gw_bar}{item_prefix} {c('dim', item)}")
                    
                client.gateway = old_gw
            except Exception as e:
                gw_node["error"] = str(e)
                if not json_output:
                    print(f"{site_bar}{gw_bar}└── Error fetching devices: {e}")

    if json_output:
        print_json_output(topology)

# ── CLI entry point ──────────────────────────────────────────────────

async def run(client, *, json_output: bool = False, save: bool = False,
              redact: str | None = None, label: str | None = None,
              analyze: bool = False, compare_file: str | None = None,
              scope: str = "all", info: bool = False):
    """Execute the support command."""

    if info:
        await run_info(client, json_output=json_output)
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
        "gateway": data.get("identity", {}).get("serial", "?"),
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
        serial_short = (data.get("identity", {}).get("serial", "unknown"))[-8:]
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
        identity = data.get("identity", {})
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
        versions = data.get("versions", {})
        if "error" not in versions:
            print_section("📦", "Software Versions")
            for key in ("ibgVersion", "awsVersion", "appVersion", "slVersion",
                        "meterVersion", "protocolVer", "cloudApiVersion", "libraryVersion"):
                val = versions.get(key)
                if val:
                    print_kv(key, val)
            # Mobile app versions
            mobile = versions.get("mobileApp", {})
            if mobile:
                ios_ver = mobile.get("ios", "?")
                android_ver = mobile.get("android", "?")
                print_kv("Mobile App (iOS)", ios_ver)
                print_kv("Mobile App (Android)", android_ver)

        # Network summary
        net = data.get("network", {})
        if "error" not in net:
            conn_type = net.get("currentNetType", 0)
            print_section("📶", "Network")
            print_kv("Active", NET_TYPES.get(conn_type, f"Type {conn_type}"))
            for iface, label_name in [("wifi", "WiFi"), ("eth0", "Eth0"), ("eth1", "Eth1")]:
                idata = net.get(iface, {})
                if idata.get("mac"):
                    dhcp = "DHCP" if idata.get("dhcp") else "Static"
                    print_kv(label_name, f'{idata["mac"]}  {dhcp}  IP: {idata.get("ip", "—")}')
            # Cellular/4G
            op = net.get("operator", {})
            if op.get("mac"):
                rssi = op.get("rssi", "?")
                rssi_label = f"RSSI: {rssi} dBm" if rssi != "?" else ""
                print_kv("Cellular", f'{op["mac"]}  {rssi_label}')
            # SIM subscription status
            sim = data.get("identity", {}).get("simCardStatus")
            if sim is not None:
                sim_colors = {0: "dim", 1: "red", 2: "green", 3: "red"}
                from franklinwh_cloud.const import SIM_STATUS as SIM_MAP_NET
                sim_text = SIM_MAP_NET.get(sim, f"Unknown ({sim})")
                print_kv("SIM", c(sim_colors.get(sim, ""), sim_text))

        # Connectivity (from FranklinWH mobile app self-test)
        conn = data.get("connectivity", {})
        if "error" not in conn:
            print_section("🔗", "App Connectivity Test")
            # Detect stale all-zero from sendMqtt cmdType 339
            all_zero = all(conn.get(k, 0) == 0 for k in ("routerStatus", "netStatus", "awsStatus"))
            api_ok = data.get("api_health", {}).get("total_errors", 1) == 0
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
        power = data.get("power", {})
        if "error" not in power:
            print_section("⚡", "Power")
            print_kv("Solar", f'{power.get("solar_kw", 0):.1f} kW')
            print_kv("Battery", f'{power.get("battery_kw", 0):.1f} kW  (SoC: {power.get("battery_soc", 0):.0f}%)')
            print_kv("Grid", f'{power.get("grid_kw", 0):.1f} kW  ({power.get("grid_status", "?")})')
            print_kv("Home", f'{power.get("home_load_kw", 0):.1f} kW')
            print_kv("Mode", power.get("operating_mode", "?"))

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
        warranty = data.get("warranty", {})
        if "error" not in warranty and warranty.get("expirationTime"):
            print_section("📋", "Warranty")
            print_kv("Expires", warranty.get("expirationTime", "?"))
            tp = warranty.get("throughput_kWh", 0)
            rem = warranty.get("remainThroughput_kWh", 0)
            if tp > 0:
                used = tp - rem
                pct = round((used / tp) * 100)
                print_kv("Throughput", f"{tp:.0f} kWh ({pct}% used)")
            for dev in warranty.get("devices", []):
                print_kv(f"  {dev.get('model', '?')}", f"Expires: {dev.get('expires', '?')}")

        # TOU / Grid status
        tou = data.get("tou_status", {})
        if "error" not in tou and tou:
            print_section("🏷️", "TOU / Grid")
            pto = tou.get("ptoDate")
            if pto:
                print_kv("PTO Date", pto)
            plan = tou.get("tariffPlan")
            if plan:
                company = tou.get("electricCompany", "")
                print_kv("Tariff", f"{plan} ({company})" if company else plan)
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
        schema = data.get("schema_fingerprint", {})
        if schema:
            print_section("🔑", "API Schema")
            print_kv("Fingerprint", schema.get("fingerprint", "?"))
            print_kv("Total keys", str(schema.get("key_count", 0)))

        print()
        print_kv("Tip", c("dim", "Use --save to export, --redact for sharing, --compare to diff"))
        print()



