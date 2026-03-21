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
import re
import socket
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
            "grid_status": cur.grid_status.name,
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
        }
    except Exception as e:
        snapshot["relays"]["error"] = str(e)

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
    0: "None", 1: "WiFi", 2: "Ethernet", 3: "WiFi+Ethernet",
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


# ── CLI entry point ──────────────────────────────────────────────────

async def run(client, *, json_output: bool = False, save: bool = False,
              redact: str | None = None, label: str | None = None,
              analyze: bool = False, compare_file: str | None = None,
              scope: str = "all"):
    """Execute the support command."""

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

        # Connectivity
        conn = data.get("connectivity", {})
        if "error" not in conn:
            print_section("🔗", "Connectivity")
            # Detect stale all-zero from sendMqtt cmdType 339
            all_zero = all(conn.get(k, 0) == 0 for k in ("routerStatus", "netStatus", "awsStatus"))
            api_ok = data.get("api_health", {}).get("total_errors", 1) == 0
            if all_zero and api_ok:
                # API is working — connection status is stale
                print_kv("Router", c("yellow", "⚠ Reported offline (stale — API reachable)"))
                print_kv("Internet", c("yellow", "⚠ Reported offline (stale — API reachable)"))
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
