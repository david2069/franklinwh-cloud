"""Status command — live system overview with power, SOC, mode, weather, and metrics."""

from franklinwh_cloud.cli_output import (
    print_header, print_section, print_kv, print_json_output, print_warning,
    c,
)


async def run(client, *, json_output: bool = False):
    """Execute the status command."""
    stats = await client.get_stats()

    if json_output:
        import dataclasses
        output = {
            "current": dataclasses.asdict(stats.current),
            "totals": dataclasses.asdict(stats.totals),
        }

        # Add mode info
        try:
            mode = await client.get_mode()
            output["mode"] = mode
        except Exception:
            output["mode"] = None

        # Add weather
        try:
            weather = await client.get_weather()
            if weather and weather.get("result"):
                output["weather"] = weather["result"]
        except Exception:
            output["weather"] = None

        # Add metrics
        output["metrics"] = client.get_metrics()

        print_json_output(output)
        return

    # ── Rich text output ──────────────────────────────────────────

    print_header("FranklinWH System Status")

    cur = stats.current
    tot = stats.totals

    # Warn if runtime data was empty (API returned no power measurements)
    if cur.battery_soc == 0 and cur.solar_production == 0 and cur.home_load == 0:
        print_warning("Runtime data unavailable — API returned no power measurements.")
        print_warning("The aGate may not have reported yet. Try again in 30-60 seconds.")
        print()

    # Power flows
    print_section("📊", "Power Flow")
    print_kv("Solar", f"{cur.solar_production:>8.1f} kW")
    print_kv("Battery", f"{cur.battery_use:>8.1f} kW  (SoC: {c('bold', f'{cur.battery_soc:.0f}%')})")
    grid_color = "green" if cur.grid_status.name == "NORMAL" else "red"
    print_kv("Grid", f"{cur.grid_use:>8.1f} kW  ({c(grid_color, cur.grid_status.name)})")
    print_kv("Home Load", f"{cur.home_load:>8.1f} kW")
    if cur.generator_production:
        print_kv("Generator", f"{cur.generator_production:>8.1f} kW")

    # Smart circuits
    if cur.switch_1_load or cur.switch_2_load or cur.v2l_use:
        print_section("🔌", "Smart Circuits")
        if cur.switch_1_load:
            print_kv("Switch 1", f"{cur.switch_1_load:>8.1f} kW")
        if cur.switch_2_load:
            print_kv("Switch 2", f"{cur.switch_2_load:>8.1f} kW")
        if cur.v2l_use:
            print_kv("EV/V2L", f"{cur.v2l_use:>8.1f} kW")

    # Daily totals
    print_section("📅", "Daily Totals")
    print_kv("Solar", f"{tot.solar:>8.2f} kWh")
    print_kv("Grid Import", f"{tot.grid_import:>8.2f} kWh")
    print_kv("Grid Export", f"{tot.grid_export:>8.2f} kWh")
    print_kv("Home Use", f"{tot.home_use:>8.2f} kWh")
    print_kv("Battery Charge", f"{tot.battery_charge:>8.2f} kWh")
    print_kv("Battery Discharge", f"{tot.battery_discharge:>8.2f} kWh")
    if tot.generator:
        print_kv("Generator", f"{tot.generator:>8.2f} kWh")

    # Operating mode
    print_section("⚡", "Operating Mode")
    print_kv("Mode", cur.work_mode_desc)
    print_kv("Run Status", cur.run_status_dec)

    # aPower batteries
    if cur.apower_serial_numbers:
        print_section("🔋", "aPower Batteries")
        from franklinwh_cloud.const import RUN_STATUS
        sns = cur.apower_serial_numbers if isinstance(cur.apower_serial_numbers, list) else [cur.apower_serial_numbers]
        socs = cur.apower_soc if isinstance(cur.apower_soc, list) else [cur.apower_soc]
        pwrs = cur.apower_power if isinstance(cur.apower_power, list) else [cur.apower_power]
        bmss = cur.apower_bms_mode if isinstance(cur.apower_bms_mode, list) else [cur.apower_bms_mode]
        for i, sn in enumerate(sns):
            if not sn:
                continue
            soc = socs[i] if i < len(socs) else "?"
            pwr = pwrs[i] if i < len(pwrs) else "?"
            bms = bmss[i] if i < len(bmss) else 0
            bms_desc = RUN_STATUS.get(int(bms), "Unknown") if bms else ""
            sn_short = sn[-6:] if len(str(sn)) > 6 else sn
            print_kv(f"aPower {sn_short}", f"SoC: {soc}%  Power: {pwr}W  {bms_desc}")

    # Connectivity
    print_section("📡", "Connectivity")
    from franklinwh_cloud.const import NETWORK_TYPES
    conn_type = cur.network_connection or 0
    print_kv("Network", NETWORK_TYPES.get(conn_type, f"Type {conn_type}"))
    if cur.wifi_signal:
        print_kv("WiFi Signal", f"{cur.wifi_signal}")
    if cur.mobile_signal:
        print_kv("Cell Signal", f"{cur.mobile_signal}")

    # Weather
    try:
        weather = await client.get_weather()
        if weather and weather.get("result"):
            w = weather["result"]
            print_section("🌤️ ", "Weather")
            desc = w.get("description", "Unknown")
            is_day = "Day" if w.get("isDayTime") else "Night"
            print_kv("Conditions", f"{desc} ({is_day})")
    except Exception:
        pass

    # Grid status
    try:
        grid = await client.get_grid_status()
        if grid and grid.get("result"):
            r = grid["result"]
            offgrid_state = r.get("offgridState", 0)
            print_section("🔌", "Grid")
            status_text = c("red", "DISCONNECTED") if offgrid_state else c("green", "CONNECTED")
            print_kv("Grid Status", status_text)
    except Exception:
        pass

    # API Metrics
    metrics = client.get_metrics()
    print_section("📈", "API Metrics")
    print_kv("Total API Calls", metrics["total_api_calls"])
    print_kv("Avg Response", f'{metrics["avg_response_time_s"]:.3f}s')
    print_kv("Calls by Method", str(metrics["calls_by_method"]))
    print_kv("Endpoints Hit", len(metrics["calls_by_endpoint"]))
    print_kv("Errors", metrics["total_errors"])

    print()
