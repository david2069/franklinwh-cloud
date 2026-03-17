"""TOU command — Time-of-Use schedule inspection.

Shows tariff configuration, the actual dispatch schedule (matching FEM),
rate information, and charge power estimates. Supports multiple seasons,
day types (weekday/weekend/every day), and pricing tiers.

Usage:
    franklinwh-cli tou                # schedule overview with dispatch blocks
    franklinwh-cli tou --dispatch     # include raw dispatch metadata
    franklinwh-cli tou --json         # machine-readable
"""

from franklinwh_cloud.cli_output import (
    print_header, print_section, print_kv, print_json_output, print_warning,
    c,
)
from franklinwh_cloud.const import DISPATCH_CODES, WAVE_TYPES


async def run(client, *, json_output: bool = False, show_dispatch: bool = False):
    """Execute the TOU command."""

    if json_output:
        output = {}
        output["tou_list"] = await client.get_gateway_tou_list()
        output["dispatch_detail"] = await client.get_tou_dispatch_detail()
        output["charge_power"] = await client.get_charge_power_details()
        print_json_output(output)
        return

    print_header("Time-of-Use Schedule")

    # ── TOU Status ───────────────────────────────────────────────
    print_section("📋", "TOU Configuration")
    try:
        res = await client.get_gateway_tou_list()
        result = res.get("result", {})

        tariff = result.get("tariffSettingFlag", False)
        status_text = c("green", "CONFIGURED") if tariff else c("yellow", "NOT CONFIGURED")
        print_kv("Tariff", status_text)

        stop_mode = result.get("stopMode")
        if stop_mode:
            print_kv("Stop Mode", c("red", "ACTIVE"))

        send_status = result.get("touSendStatus")
        if send_status:
            print_kv("Send Status", c("yellow", "Pending"))

        alert = result.get("touAlertMessage")
        if alert:
            print_kv("Alert", c("yellow", str(alert)))

    except Exception as e:
        print_warning(f"Could not retrieve TOU list: {e}")

    # ── Full Schedule (all seasons, day types, periods) ──────────
    dispatch_result = None
    try:
        res = await client.get_tou_dispatch_detail()
        dispatch_result = res.get("result", {})
        template = dispatch_result.get("template", {})
        strategies = dispatch_result.get("strategyList", [])

        # Build dispatch lookup from detailDefaultVo
        dispatch_lookup = {}
        default_vo = dispatch_result.get("detailDefaultVo", {})
        tou_dispatch_list = default_vo.get("touDispatchList", [])
        for d in tou_dispatch_list:
            if d.get("id") is not None:
                dispatch_lookup[d["id"]] = d

        # ── Tariff Plan ──────────────────────────────────────────
        print_section("🏷️", "Tariff Plan")
        plan_name = template.get("name", template.get("tariffName", "?"))
        print_kv("Plan", plan_name)
        print_kv("Utility", template.get("electricCompany", "?"))
        print_kv("Country", template.get("countryEn", "?"))
        der = template.get("derSchdule")
        if der:
            print_kv("DER Schedule", der)
        work_mode = template.get("workMode", 0)
        mode_names = {1: "Time of Use", 2: "Self Consumption", 3: "Emergency Backup"}
        print_kv("Work Mode", mode_names.get(work_mode, f"Unknown ({work_mode})"))

        nem_type = dispatch_result.get("nemType", 0)
        nem_names = {0: "NEM 2.0", 1: "NEM 3.0 (Net Billing)", 2: "No NEM"}
        print_kv("NEM Type", nem_names.get(nem_type, f"Unknown ({nem_type})"))

        bat_cap = dispatch_result.get("batteryRatedCapacity")
        if bat_cap:
            print_kv("Battery Capacity", f"{bat_cap} kWh")

        # ── Iterate seasons ──────────────────────────────────────
        if not strategies:
            print_warning("No TOU schedules configured.")
        else:
            total_blocks = 0
            for season_idx, season in enumerate(strategies):
                season_name = season.get("seasonName", f"Season {season_idx + 1}")
                months = season.get("month", "")
                month_display = _format_months(months)

                print_section("📅", f"{season_name} — {month_display}")

                day_types = season.get("dayTypeVoList", [])
                if not day_types:
                    print_warning("No day types configured for this season.")
                    continue

                # ── Iterate day types ────────────────────────────
                for dt_idx, day_type in enumerate(day_types):
                    day_name = day_type.get("dayName", "?")
                    dt_code = day_type.get("dayType", 0)
                    day_label = _day_type_label(dt_code, day_name)

                    # Show day type header if multiple
                    if len(day_types) > 1:
                        print(f"\n  {c('bold', f'▸ {day_label}')}")

                    # ── Rates for this day type ──────────────────
                    rates = _extract_rates(day_type)
                    if rates:
                        print()
                        for rate_name, buy, sell in rates:
                            sell_str = f"  Sell: ${sell:.4f}" if sell is not None else ""
                            print_kv(f"  💰 {rate_name}", f"Buy: ${buy:.4f}{sell_str}")
                        print()

                    # ── Dispatch periods ─────────────────────────
                    periods = day_type.get("detailVoList", [])
                    if periods:
                        # Table header
                        print(f"  {'START':<10}{'END':<10}{'NAME':<14}{'DISPATCH':<24}{'WAVE':<12}{'MAX SoC':<9}{'MIN SoC':<9}{'SOL CO'}")
                        print(f"  {'─'*9} {'─'*9} {'─'*13} {'─'*23} {'─'*11} {'─'*8} {'─'*8} {'─'*6}")

                        for block in periods:
                            start = block.get("startHourTime", "?")
                            end = block.get("endHourTime", "?")
                            name = block.get("name", "?")
                            dispatch_id = block.get("dispatchId", 0)
                            wave_type = block.get("waveType", 0)
                            max_soc = block.get("maxChargeSoc")
                            min_soc = block.get("minDischargeSoc")
                            solar_cutoff = block.get("solarCutoff", 0)

                            # Resolve dispatch name
                            disp_display = _resolve_dispatch(dispatch_id, dispatch_lookup)
                            # Truncate long names
                            if len(disp_display) > 22:
                                disp_display = disp_display[:20] + "…"

                            wave_name = WAVE_TYPES.get(wave_type, f"Wave {wave_type}")
                            disp_color = _dispatch_color(disp_display)

                            max_str = f"{max_soc}%" if max_soc else "—"
                            min_str = f"{min_soc}%" if min_soc else "—"
                            solar_str = str(solar_cutoff) if solar_cutoff else "0"

                            print(f"  {start:<10}{end:<10}{name:<14}{c(disp_color, f'{disp_display:<24s}')}{wave_name:<12}{max_str:<9}{min_str:<9}{solar_str}")

                        total_blocks += len(periods)
                        print()
                    else:
                        print_warning("  No dispatch periods configured for this day type.")

            print_kv("Total", f"{total_blocks} time blocks across {len(strategies)} season(s)")

    except Exception as e:
        print_warning(f"Could not retrieve dispatch detail: {e}")

    # ── Raw Dispatch Detail ──────────────────────────────────────
    if show_dispatch and dispatch_result:
        print_section("⚙️", "Raw Dispatch Detail")
        print_kv("PTO Date", dispatch_result.get("ptoDate", "—"))
        print_kv("Battery Savings", dispatch_result.get("batterySavingsFlag", "—"))
        print_kv("aPower Count", dispatch_result.get("apowerCount", "—"))
        print_kv("Battery Capacity", f'{dispatch_result.get("batteryRatedCapacity", "?")} kWh')

        if tou_dispatch_list:
            print_section("📊", "Available Dispatch Codes")
            for d in tou_dispatch_list:
                if d.get("id") is not None:
                    title = d.get("title", "?")
                    code = d.get("dispatchCode", "?")
                    desc = d.get("content", "")
                    print_kv(f"  [{d['id']}] {title}", f"Code: {code}")
                    if desc:
                        print(f"         {c('dim', desc[:80])}")

    # ── Charge Power Details ─────────────────────────────────────
    print_section("🔌", "Charge Power")
    try:
        res = await client.get_charge_power_details()
        if isinstance(res, dict):
            result = res.get("result", res)
            if isinstance(result, dict):
                soc = result.get("batterySoc")
                if soc is not None:
                    soc_color = "green" if float(soc) > 20 else ("yellow" if float(soc) > 10 else "red")
                    print_kv("Battery SoC", c(soc_color, f"{soc}%"))

                min_soc = result.get("touMinSoc")
                if min_soc is not None:
                    print_kv("TOU Min SoC", f"{min_soc}%")

                duration = result.get("currentStateDuration")
                if duration is not None:
                    hrs = int(float(duration))
                    mins = int((float(duration) - hrs) * 60)
                    print_kv("Current Duration", f"{hrs}h {mins}m")

                high = result.get("highEnergyConsumption")
                if high is not None:
                    print_kv("High Consumption", f"{high} kW")

                avg = result.get("averageEnergyConsumption")
                if avg is not None:
                    print_kv("Avg Consumption", f"{avg} kW")

                cur_time = result.get("currentTime")
                if cur_time:
                    print_kv("Est. Runtime (now)", cur_time)
                high_time = result.get("highEnergyTime")
                if high_time:
                    print_kv("Est. Runtime (high)", high_time)
                avg_time = result.get("averageTime")
                if avg_time:
                    print_kv("Est. Runtime (avg)", avg_time)
            else:
                print_kv("Details", str(result))
        else:
            print_kv("Details", str(res))
    except Exception as e:
        print_warning(f"Could not retrieve charge power details: {e}")

    print()


# ── Helpers ──────────────────────────────────────────────────────

def _format_months(months_str: str) -> str:
    """Convert '1,2,3,...,12' to human-readable month range."""
    if not months_str:
        return "?"
    months = sorted(int(m) for m in months_str.split(",") if m.strip())
    if months == list(range(1, 13)):
        return "All Year"

    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    if len(months) == 1:
        return month_names[months[0] - 1]
    if len(months) <= 3:
        return ", ".join(month_names[m - 1] for m in months)

    # Check for contiguous range
    if months == list(range(months[0], months[-1] + 1)):
        return f"{month_names[months[0] - 1]}–{month_names[months[-1] - 1]}"

    return ", ".join(month_names[m - 1] for m in months)


def _day_type_label(day_type: int, day_name: str) -> str:
    """Convert day type code to readable label."""
    labels = {1: "Weekdays (Mon–Fri)", 2: "Weekends (Sat–Sun)", 3: "Every Day", 4: "Custom"}
    return labels.get(day_type, day_name)


def _extract_rates(day_type: dict) -> list:
    """Extract non-zero rate tiers from day type data."""
    rates = []
    tiers = [
        ("On-Peak", "eleticRatePeak", "eleticSellPeak"),
        ("Sharp Peak", "eleticRateSharp", "eleticSellSharp"),
        ("Shoulder", "eleticRateShoulder", "eleticSellShoulder"),
        ("Off-Peak", "eleticRateValley", "eleticSellValley"),
        ("Super Off-Peak", "eleticRateSuperOffPeak", "eleticSellSuperOffPeak"),
    ]
    for name, buy_key, sell_key in tiers:
        buy = day_type.get(buy_key)
        sell = day_type.get(sell_key)
        if buy is not None and buy != 0:
            rates.append((name, buy, sell))
    return rates


def _resolve_dispatch(dispatch_id: int, dispatch_lookup: dict) -> str:
    """Resolve dispatch ID to display name using lookup table."""
    info = dispatch_lookup.get(dispatch_id, {})
    title = info.get("title", "")
    code = info.get("dispatchCode", "")
    if title:
        return title
    if code:
        return DISPATCH_CODES.get(code, code)
    return f"ID {dispatch_id}"


def _dispatch_color(name: str) -> str:
    """Pick ANSI color based on dispatch mode name."""
    lower = name.lower()
    if "charge" in lower or "grid" in lower:
        return "cyan"
    if "export" in lower:
        return "yellow"
    if "self" in lower:
        return "green"
    if "standby" in lower or "idle" in lower:
        return "dim"
    if "home" in lower:
        return "magenta"
    return "dim"
