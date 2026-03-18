"""Diagnostic command — comprehensive system check for support and troubleshooting.

Runs a series of checks against the Cloud API and reports:
  - Library/Python version info
  - Connection + authentication test with timing
  - CloudFront edge details
  - Device info (model, firmware, phase config, solar, aPower units)
  - Operating mode + runtime state
  - Live power snapshot
  - Battery health
  - API metrics summary
  - Recent errors (if any)

Usage:
    franklinwh-cli diag               # rich text output
    franklinwh-cli diag --json        # machine-readable for support tickets
"""

import platform
import sys
import time

from franklinwh_cloud.cli_output import (
    print_header, print_section, print_kv, print_json_output,
    print_warning, print_success, print_error, c,
)


async def run(client, *, json_output: bool = False):
    """Execute the diagnostic command."""
    import franklinwh_cloud

    results = {}
    checks_passed = 0
    checks_failed = 0
    checks_warned = 0

    # ── 1. System Info ───────────────────────────────────────────────

    lib_version = getattr(franklinwh_cloud, "__version__", "unknown")
    sys_info = {
        "library": f"franklinwh-cloud-client {lib_version}",
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "platform": platform.platform(),
        "machine": platform.machine(),
    }
    results["system"] = sys_info

    if not json_output:
        print_header("FranklinWH Diagnostics")
        print_section("🖥️", "System")
        print_kv("Library", sys_info["library"])
        print_kv("Python", sys_info["python"])
        print_kv("Platform", sys_info["platform"])
        print_kv("Architecture", sys_info["machine"])

    # ── 2. Connection + Auth Test ────────────────────────────────────

    conn_info = {"authenticated": False, "gateway": client.gateway, "response_time_s": None}

    t0 = time.monotonic()
    try:
        gw_res = await client.get_home_gateway_list()
        elapsed = time.monotonic() - t0
        conn_info["authenticated"] = True
        conn_info["response_time_s"] = round(elapsed, 3)

        gateways = gw_res.get("result", [])
        conn_info["gateways_found"] = len(gateways)
        conn_info["gateway_sns"] = [g.get("id", "?") for g in gateways]
        checks_passed += 1
    except Exception as e:
        elapsed = time.monotonic() - t0
        conn_info["response_time_s"] = round(elapsed, 3)
        conn_info["error"] = str(e)
        checks_failed += 1

    results["connection"] = conn_info

    if not json_output:
        print_section("🔐", "Connection & Auth")
        if conn_info["authenticated"]:
            print_kv("Status", c("green", "✓ Authenticated"))
            print_kv("Response Time", f'{conn_info["response_time_s"]:.3f}s')
            print_kv("Gateway", conn_info["gateway"])
            print_kv("Gateways Found", conn_info["gateways_found"])
        else:
            print_kv("Status", c("red", f'✘ Failed: {conn_info.get("error", "unknown")}'))
            print_kv("Response Time", f'{conn_info["response_time_s"]:.3f}s')

    if not conn_info["authenticated"]:
        results["checks"] = {"passed": checks_passed, "failed": checks_failed, "warnings": checks_warned}
        if json_output:
            print_json_output(results)
        else:
            print()
            print_error("Cannot continue diagnostics without authentication.")
        return

    # ── 3. CloudFront Edge ───────────────────────────────────────────

    edge_info = {"available": False}
    if hasattr(client, 'edge_tracker') and client.edge_tracker and client.edge_tracker.total_requests > 0:
        et = client.edge_tracker.snapshot()
        edge_info = {
            "available": True,
            "current_pop": et.get("current_pop"),
            "total_requests": et.get("total_cf_requests", 0),
            "cache_hit_rate": et.get("cache_hit_rate", "—"),
            "distribution_ids": et.get("distribution_ids", []),
            "edge_transitions": et.get("edge_transitions", 0),
        }
        checks_passed += 1
    else:
        edge_info["note"] = "No CloudFront data yet (too few API calls)"
        checks_warned += 1

    results["cloudfront"] = edge_info

    if not json_output:
        print_section("☁️", "CloudFront Edge")
        if edge_info["available"]:
            print_kv("Edge PoP", edge_info["current_pop"] or "—")
            print_kv("Requests", edge_info["total_requests"])
            print_kv("Cache Rate", edge_info["cache_hit_rate"])
            if edge_info["distribution_ids"]:
                print_kv("Distribution", ", ".join(edge_info["distribution_ids"]))
            if edge_info["edge_transitions"] > 0:
                print_kv("⚠ Transitions", edge_info["edge_transitions"])
        else:
            print_kv("Status", c("dim", edge_info.get("note", "Not available")))

    # ── 4. Device Info ───────────────────────────────────────────────

    device_info = {}
    try:
        res = await client.get_device_info()
        result = res.get("result", {})

        apower_list = result.get("apowerList", [])
        batteries = []
        for ap in apower_list:
            batteries.append({
                "serial": ap.get("id", "?"),
                "rated_power_w": ap.get("ratedPwr", 0),
                "capacity_wh": ap.get("rateBatCap", 0),
            })

        device_info = {
            "device_time": result.get("deviceTime"),
            "solar_flag": result.get("solarFlag", 0),
            "off_grid": result.get("offGirdFlag", 0),
            "v2l_enabled": result.get("v2lModeEnable", 0),
            "mppt_enabled": result.get("mpptEnFlag", 0),
            "total_capacity_kwh": result.get("totalCap", 0),
            "battery_count": len(apower_list),
            "batteries": batteries,
        }
        checks_passed += 1
    except Exception as e:
        device_info["error"] = str(e)
        checks_failed += 1

    results["device"] = device_info

    if not json_output:
        print_section("📟", "Device")
        if "error" in device_info:
            print_kv("Status", c("red", f'✘ {device_info["error"]}'))
        else:
            print_kv("Batteries", f'{device_info["battery_count"]} × aPower ({device_info["total_capacity_kwh"]} kWh total)')
            flags = []
            if device_info.get("solar_flag"):
                flags.append("Solar")
            if device_info.get("mppt_enabled"):
                flags.append("MPPT")
            if device_info.get("v2l_enabled"):
                flags.append("V2L")
            if device_info.get("off_grid"):
                flags.append("Off-Grid")
            print_kv("Features", ", ".join(flags) if flags else "None detected")

            for bat in device_info.get("batteries", []):
                sn = bat["serial"]
                sn_short = sn[-6:] if len(str(sn)) > 6 else sn
                print_kv(f"aPower {sn_short}", f'{bat["rated_power_w"]}W / {bat["capacity_wh"]}Wh')

    # ── 5. Phase Config + Gateway Detail ─────────────────────────────

    gateway_info = {}
    try:
        res = await client.get_device_composite_info()
        data = res.get("result", {})
        solar_vo = data.get("solarHaveVo", {})

        is_three_phase = solar_vo.get("isThreePhaseInstall", False)
        if is_three_phase:
            phase = "Three Phase (L1/L2/L3)"
        else:
            phase = "Single Phase (L1)"

        gw_detail = {}
        for g in gateways:
            if g.get("id") == client.gateway:
                from franklinwh_cloud.const import FRANKLINWH_MODELS, COUNTRY_ID
                hw_ver = int(g.get("sysHdVersion", 0))
                model_info = FRANKLINWH_MODELS.get(hw_ver, {})
                gw_detail = {
                    "name": g.get("name", "?"),
                    "model": model_info.get("model", f"HW v{hw_ver}"),
                    "sku": model_info.get("sku", "?"),
                    "firmware": g.get("version", "?"),
                    "protocol": g.get("protocolVer", "?"),
                    "country": COUNTRY_ID.get(g.get("countryId", 0), "Unknown"),
                    "timezone": g.get("zoneInfo", "?"),
                    "address": g.get("address", "?"),
                }
                break

        gateway_info = {
            "phase": phase,
            "three_phase_flag": is_three_phase,
            **gw_detail,
        }

        from franklinwh_cloud.const import OPERATING_MODES, RUN_STATUS
        rt = data.get("runtimeData", {})
        work_mode = data.get("currentWorkMode", 0)
        run_status_code = rt.get("run_status", 0)

        gateway_info["operating_mode"] = OPERATING_MODES.get(work_mode, f"Unknown ({work_mode})")
        gateway_info["run_status"] = RUN_STATUS.get(int(run_status_code), f"Unknown ({run_status_code})")
        gateway_info["soc"] = rt.get("soc", 0)

        checks_passed += 1
    except Exception as e:
        gateway_info["error"] = str(e)
        checks_failed += 1

    results["gateway"] = gateway_info

    if not json_output:
        print_section("🏠", "Gateway")
        if "error" in gateway_info:
            print_kv("Status", c("red", f'✘ {gateway_info["error"]}'))
        else:
            if gateway_info.get("name"):
                print_kv("Name", gateway_info["name"])
            if gateway_info.get("model"):
                print_kv("Model", f'{gateway_info["model"]} ({gateway_info.get("sku", "?")})')
            if gateway_info.get("firmware"):
                print_kv("Firmware", gateway_info["firmware"])
            if gateway_info.get("country"):
                print_kv("Country", gateway_info["country"])
            if gateway_info.get("timezone"):
                print_kv("Timezone", gateway_info["timezone"])

            phase_color = "cyan" if gateway_info.get("three_phase_flag") else "dim"
            print_kv("Phase Config", c(phase_color, gateway_info.get("phase", "Unknown")))

    # ── 6. Power Snapshot ────────────────────────────────────────────

    power_info = {}
    t1 = time.monotonic()
    try:
        stats = await client.get_stats()
        api_time = round(time.monotonic() - t1, 3)
        cur = stats.current

        power_info = {
            "api_response_s": api_time,
            "solar_kw": cur.solar_production,
            "battery_kw": cur.battery_use,
            "battery_soc": cur.battery_soc,
            "grid_kw": cur.grid_use,
            "grid_status": cur.grid_status.name,
            "home_load_kw": cur.home_load,
            "operating_mode": cur.work_mode_desc,
            "run_status": cur.run_status_dec,
        }
        checks_passed += 1
    except Exception as e:
        api_time = round(time.monotonic() - t1, 3)
        power_info["error"] = str(e)
        power_info["api_response_s"] = api_time
        checks_failed += 1

    results["power"] = power_info

    if not json_output:
        print_section("⚡", "Live Power")
        if "error" in power_info:
            print_kv("Status", c("red", f'✘ {power_info["error"]}'))
        else:
            print_kv("API Response", f'{power_info["api_response_s"]:.3f}s')
            print_kv("Solar", f'{power_info["solar_kw"]:.1f} kW')
            print_kv("Battery", f'{power_info["battery_kw"]:.1f} kW  (SoC: {power_info["battery_soc"]:.0f}%)')
            grid_color = "green" if power_info["grid_status"] == "NORMAL" else "red"
            print_kv("Grid", f'{power_info["grid_kw"]:.1f} kW  ({c(grid_color, power_info["grid_status"])})')
            print_kv("Home", f'{power_info["home_load_kw"]:.1f} kW')
            print_kv("Mode", power_info["operating_mode"])
            print_kv("Run Status", power_info["run_status"])

    # ── 7. API Health ────────────────────────────────────────────────

    metrics = client.get_metrics()
    api_health = {
        "total_calls": metrics["total_api_calls"],
        "avg_response_s": metrics["avg_response_time_s"],
        "min_response_s": metrics["min_response_time_s"],
        "max_response_s": metrics["max_response_time_s"],
        "total_errors": metrics["total_errors"],
        "total_rate_limits": metrics["total_rate_limits"],
        "retry_count": metrics["retry_count"],
        "uptime_s": metrics["uptime_s"],
        "endpoints_hit": len(metrics["calls_by_endpoint"]),
    }

    if client.rate_limiter:
        rl = client.rate_limiter.snapshot()
        api_health["rate_limiter"] = {
            "calls_last_minute": rl["calls_last_minute"],
            "limit_per_minute": rl["limit_per_minute"],
            "calls_today": rl["calls_today"],
            "remaining_daily": rl["remaining_daily"],
            "is_throttled": rl["is_throttled"],
        }

    if metrics["total_errors"] > 0:
        checks_warned += 1
    else:
        checks_passed += 1

    results["api_health"] = api_health

    if not json_output:
        print_section("📈", "API Health")
        print_kv("Total Calls", api_health["total_calls"])
        print_kv("Avg / Min / Max",
                 f'{api_health["avg_response_s"]:.3f}s / '
                 f'{api_health["min_response_s"]:.3f}s / '
                 f'{api_health["max_response_s"]:.3f}s')
        print_kv("Endpoints Hit", api_health["endpoints_hit"])

        err_color = "green" if api_health["total_errors"] == 0 else "yellow"
        print_kv("Errors", c(err_color, str(api_health["total_errors"])))

        if api_health["total_rate_limits"] > 0:
            print_kv("⚠ Rate Limits", api_health["total_rate_limits"])
        if api_health["retry_count"] > 0:
            print_kv("Retries", api_health["retry_count"])

        if "rate_limiter" in api_health:
            rl = api_health["rate_limiter"]
            throttle = c("red", "⚠ THROTTLED") if rl["is_throttled"] else c("green", "OK")
            print_kv("Rate Limit", f'{rl["calls_last_minute"]}/{rl["limit_per_minute"]} per min  {throttle}')

    # ── 8. Summary ───────────────────────────────────────────────────

    results["checks"] = {
        "passed": checks_passed,
        "failed": checks_failed,
        "warnings": checks_warned,
    }

    if json_output:
        print_json_output(results)
    else:
        print_section("📋", "Summary")
        total = checks_passed + checks_failed + checks_warned
        print_kv("Checks", f"{total} total")
        print_kv("Passed", c("green", str(checks_passed)))
        if checks_failed > 0:
            print_kv("Failed", c("red", str(checks_failed)))
        if checks_warned > 0:
            print_kv("Warnings", c("yellow", str(checks_warned)))

        if checks_failed == 0:
            print()
            print_success("All diagnostic checks passed.")
        else:
            print()
            print_error(f"{checks_failed} check(s) failed — see details above.")
        print()
