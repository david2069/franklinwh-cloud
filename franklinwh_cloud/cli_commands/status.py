"""Status command — live system overview with power, SOC, mode, weather, and metrics."""

from franklinwh_cloud.cli_output import (
    print_header, print_section, print_kv, print_json_output, print_warning,
    c,
)
from franklinwh_cloud.models import GridConnectionState
from franklinwh_cloud.const.states import GENERATOR_STATE

import logging

logger = logging.getLogger(__name__)



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
    _grid_state = cur.grid_connection_state
    _gcolor = {
        GridConnectionState.CONNECTED: "green",
        GridConnectionState.OUTAGE: "red",
        GridConnectionState.SIMULATED_OFF_GRID: "yellow",
        GridConnectionState.NOT_GRID_TIED: "cyan",
    }.get(_grid_state, "white")
    print_kv("Grid", f"{cur.grid_use:>8.1f} kW  ({c(_gcolor, _grid_state.value)})")
    print_kv("Home Load", f"{cur.home_load:>8.1f} kW")
    if cur.generator_production:
        print_kv("Generator", f"{cur.generator_production:>8.1f} kW")

    # Smart circuits.
    #
    # This used to render only when a circuit was drawing power, so a circuit
    # that was ON but idle did not appear at all — indistinguishable from one
    # that was off, or from having no circuits. Zero watts is not zero state:
    # a switched-on circuit with nothing plugged in reads 0.00 kW (observed
    # 2026-09-18, Sw1Mode 1 with switch_1_load 0). State comes from 311 now,
    # and the power reading sits alongside it.
    sc_info = None
    try:
        sc_info = await client.get_smart_circuits_info()
    except Exception as e:
        logger.debug(f"status: smart circuit config unavailable: {e}")

    if sc_info or cur.switch_1_load or cur.switch_2_load or cur.v2l_use:
        print_section("🔌", "Smart Circuits")
        loads = {1: cur.switch_1_load, 2: cur.switch_2_load}
        for i in (1, 2, 3):
            mode = (sc_info or {}).get(f"Sw{i}Mode")
            name = (sc_info or {}).get(f"Sw{i}Name") or f"Switch {i}"
            load = loads.get(i)
            if mode is None and not load:
                continue          # no config and no load — nothing to report
            bits = []
            if mode is not None:
                bits.append("on" if mode == 1 else "off")
            if load is not None:
                bits.append(f"{load:.1f} kW")
            armed = [e for e in ((sc_info or {}).get(f"Sw{i}TimeEn") or []) if e]
            if armed:
                freq = (sc_info or {}).get(f"Sw{i}Freq")
                when = "once only" if freq == 0 else (
                    f"every {freq}d" if freq else "scheduled")
                bits.append(f"schedule {when}")
            elif (sc_info or {}).get(f"Sw{i}TimeEn"):
                bits.append("schedule off")
            # A circuit whose every slot still holds the firmware's
            # never-written date is almost certainly not installed — this AU
            # gateway has two and reports three. Labelled, not hidden: a real
            # circuit nobody has scheduled looks identical from the payload,
            # so absence of configuration is not proof of absent hardware.
            slots = (sc_info or {}).get(f"Sw{i}Time") or []
            if slots and all(isinstance(s, str) and s.startswith(("2000-01-01", "1970-01-01"))
                             for s in slots) and not load:
                print_kv(name, "never configured — may not be installed")
                continue
            cutoff = (sc_info or {}).get(f"Sw{i}SocLowSet")
            if cutoff:
                # AtuoEn does not track this value and may not be its enable —
                # DEF-SC-ATUOEN-MAY-NOT-BE-THE-SOC-ENABLE. Report the threshold
                # without claiming it is active.
                bits.append(f"SoC cut-off {cutoff}%")
            print_kv(name, "  ·  ".join(bits))
        if cur.v2l_use:
            print_kv("EV/V2L", f"{cur.v2l_use:>8.1f} kW")

    # Generator. Only shown when one is actually configured — genEn 0 with no
    # schedule means the module is absent, and an empty section reads as a
    # fault rather than an absence.
    gen_info = None
    try:
        gen_info = await client.get_generator_info()
    except Exception as e:
        logger.debug(f"status: generator config unavailable: {e}")

    if gen_info and (gen_info.get("genEn") or gen_info.get("genStat")
                     or any(gen_info.get(f"charge{i}En") for i in (1, 2, 3))):
        print_section("⛽", "Generator")
        print_kv("Enabled", "yes" if gen_info.get("genEn") else "no")
        stat = gen_info.get("genStat")
        if stat is not None:
            print_kv("State", GENERATOR_STATE.get(stat, f"Unknown ({stat})"))
        start, stop = gen_info.get("genStartElec"), gen_info.get("genCloseElec")
        if start is not None and stop is not None:
            print_kv("SoC window", f"start {start}%  ·  stop {stop}%")
        windows = []
        for i in (1, 2, 3):
            if gen_info.get(f"charge{i}En"):
                windows.append(f"{gen_info.get(f'charge{i}StartTime')}"
                               f"–{gen_info.get(f'charge{i}EndTime')}")
        # Gateway-local wall clock, not the caller's — TIME_AND_TIMEZONES.md.
        print_kv("Charge windows",
                 "  ·  ".join(windows) + "  (gateway-local)" if windows else "none")

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
    print_kv("Mode", cur.effective_mode)
    # Show reserve SoC for active mode
    try:
        mode_info = await client.get_mode_info(cur.work_mode or 2)
        if mode_info and isinstance(mode_info, list) and mode_info[0]:
            active_soc = mode_info[0].get("soc")
            if active_soc is not None:
                print_kv("Reserve SoC", f"{active_soc}%")
    except Exception:
        pass
    print_kv("Run Status", cur.run_status_desc)

    # aPower batteries
    if cur.apower_serial_numbers:
        print_section("🔋", "aPower Batteries")
        from franklinwh_cloud.const.states import BMS_STATE
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
            bms_desc = BMS_STATE.get(int(bms), "Unknown") if bms else ""
            sn_short = sn[-6:] if len(str(sn)) > 6 else sn
            print_kv(f"aPower {sn_short}", f"SoC: {soc}%  Power: {pwr}W  {bms_desc}")

    # Connectivity
    print_section("📡", "Connectivity")
    # runtimeData.connType uses the SAME encoding as currentNetType. Verified
    # against 20,471 samples in the HAR corpus: observed values are {2, 3, 4}
    # with 3 (WiFi) at 19,797 — matching this gateway living on WiFi. Values 0
    # and 1 never occur. See DEF-CONNTYPE-ENCODING-WRONG.
    from franklinwh_cloud.const import NETWORK_TYPES
    conn_type = cur.network_connection or 0
    print_kv("Network", NETWORK_TYPES.get(conn_type, f"Unknown ({conn_type})"))
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
