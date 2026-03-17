"""TOU command — Time-of-Use schedule inspection.

Shows tariff configuration, schedule periods with rates,
dispatch modes, and charge power estimates.

Usage:
    franklinwh-cli tou                # schedule overview
    franklinwh-cli tou --dispatch     # include raw dispatch detail
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
            print_kv("Send Status", "Active")

        alert = result.get("touAlertMessage")
        if alert:
            print_kv("Alert", c("yellow", str(alert)))

    except Exception as e:
        print_warning(f"Could not retrieve TOU list: {e}")

    # ── Schedule (always shown) ──────────────────────────────────
    try:
        res = await client.get_tou_dispatch_detail()
        result = res.get("result", {})
        template = result.get("template", {})
        strategies = result.get("strategyList", [])

        # Template info
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

        nem_type = result.get("nemType", 0)
        nem_names = {0: "NEM 2.0", 1: "NEM 3.0 (Net Billing)", 2: "No NEM"}
        print_kv("NEM Type", nem_names.get(nem_type, f"Unknown ({nem_type})"))

        # Battery info from dispatch
        bat_cap = result.get("batteryRatedCapacity")
        if bat_cap:
            print_kv("Battery Capacity", f"{bat_cap} kWh")

        # Schedule periods
        if strategies:
            for season in strategies:
                season_name = season.get("seasonName", "Schedule")
                months = season.get("month", "")
                month_display = _format_months(months)

                print_section("📅", f"{season_name} ({month_display})")

                day_types = season.get("dayTypeVoList", [])
                for day_type in day_types:
                    day_name = day_type.get("dayName", "?")
                    day_label = _day_type_label(day_type.get("dayType", 0), day_name)

                    # Rates
                    rates = _extract_rates(day_type)
                    if rates:
                        print_kv("Day", day_label)
                        for rate_name, buy, sell in rates:
                            if buy is not None:
                                sell_str = f"  Sell: ${sell:.2f}" if sell is not None else ""
                                print_kv(f"  {rate_name}", f"Buy: ${buy:.2f}{sell_str}")

                    # Periods
                    periods = day_type.get("detailVoList", [])
                    if periods:
                        print()
                        print_kv("  Time", "Period                Dispatch")
                        print_kv("  ────", "──────────────────    ────────")
                        for period in periods:
                            start = period.get("startHourTime", "?")
                            end = period.get("endHourTime", "?")
                            wave = period.get("waveType", 0)
                            name = period.get("name", "?")
                            dispatch_id = period.get("dispatchId", 0)

                            wave_name = WAVE_TYPES.get(wave, f"Wave {wave}")
                            dispatch_name = DISPATCH_CODES.get(dispatch_id, f"Code {dispatch_id}")

                            # Color code by wave type
                            if wave in (1, 5):  # sharp/super-off-peak
                                time_color = "red" if wave == 1 else "cyan"
                            elif wave == 2:  # peak
                                time_color = "yellow"
                            elif wave == 3:  # shoulder
                                time_color = "dim"
                            elif wave == 4:  # off-peak
                                time_color = "green"
                            else:
                                time_color = "dim"

                            time_range = f"{start}–{end}"
                            period_str = f"{name} ({wave_name})"
                            print_kv(f"  {c(time_color, time_range)}", f"{period_str:<22s}{dispatch_name}")
                        print()
        else:
            print_warning("No TOU schedules configured.")

        # Raw dispatch detail (extra info with --dispatch)
        if show_dispatch:
            print_section("⚙️", "Raw Dispatch Detail")
            print_kv("PTO Date", result.get("ptoDate", "—"))
            print_kv("Battery Savings", result.get("batterySavingsFlag", "—"))
            print_kv("aPower Count", result.get("apowerCount", "—"))
            print_kv("Online Flag", result.get("onlineFlag", "—"))
            print_kv("Cover Content", result.get("coverContentFlag", "—"))

    except Exception as e:
        print_warning(f"Could not retrieve dispatch detail: {e}")

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

                # Time estimates
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
    """Convert '1,2,3,4,5,6,7,8,9,10,11,12' to 'All Year' or 'Jan-Mar'."""
    if not months_str:
        return "?"
    months = [int(m) for m in months_str.split(",") if m.strip()]
    if months == list(range(1, 13)):
        return "All Year"

    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    if len(months) <= 3:
        return ", ".join(month_names[m - 1] for m in months)
    return f"{month_names[months[0] - 1]}–{month_names[months[-1] - 1]}"


def _day_type_label(day_type: int, day_name: str) -> str:
    """Convert day type code to readable label."""
    labels = {1: "Weekdays", 2: "Weekends", 3: "Every Day", 4: "Custom"}
    return labels.get(day_type, day_name)


def _extract_rates(day_type: dict) -> list:
    """Extract rate tiers from day type data."""
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
        if buy is not None:
            rates.append((name, buy, sell))
    return rates
