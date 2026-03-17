"""TOU command — Time-of-Use schedule inspection.

Shows tariff configuration, the actual dispatch schedule (matching FEM),
rate information, and charge power estimates.

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
        output["schedule_blocks"] = await client.get_tou_info(2)
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

    # ── Tariff Plan ──────────────────────────────────────────────
    dispatch_result = None
    try:
        res = await client.get_tou_dispatch_detail()
        dispatch_result = res.get("result", {})
        template = dispatch_result.get("template", {})

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

        # Rates from strategyList
        strategies = dispatch_result.get("strategyList", [])
        if strategies:
            for season in strategies:
                day_types = season.get("dayTypeVoList", [])
                for day_type in day_types:
                    rates = _extract_rates(day_type)
                    if rates:
                        for rate_name, buy, sell in rates:
                            if buy is not None:
                                sell_str = f"  Sell: ${sell:.2f}" if sell is not None else ""
                                print_kv(f"  {rate_name}", f"Buy: ${buy:.2f}{sell_str}")

    except Exception as e:
        print_warning(f"Could not retrieve dispatch template: {e}")

    # ── Active Schedule (from get_tou_info option=2) ─────────────
    print_section("📅", "Dispatch Schedule")
    try:
        detail_list = await client.get_tou_info(2)

        if detail_list:
            # Build dispatch lookup from detailDefaultVo
            dispatch_lookup = {}
            if dispatch_result:
                default_vo = dispatch_result.get("detailDefaultVo", {})
                tou_dispatch_list = default_vo.get("touDispatchList", [])
                for d in tou_dispatch_list:
                    if d.get("id") is not None:
                        dispatch_lookup[d["id"]] = d

            # Header
            print(f"  {'START':<12}{'END':<12}{'NAME':<14}{'DISPATCH':<22}{'WAVE':<12}{'MAX SoC':<10}{'MIN SoC':<10}{'SOLAR CO'}")
            print(f"  {'─'*11}  {'─'*11}  {'─'*13} {'─'*21} {'─'*11} {'─'*9} {'─'*9} {'─'*8}")

            for block in detail_list:
                start = block.get("startHourTime", "?")
                end = block.get("endHourTime", "?")
                name = block.get("name", "?")
                dispatch_id = block.get("dispatchId", 0)
                wave_type = block.get("waveType", 0)
                max_soc = block.get("maxChargeSoc")
                min_soc = block.get("minDischargeSoc")
                solar_cutoff = block.get("solarCutoff", 0)

                # Look up dispatch name
                dispatch_info = dispatch_lookup.get(dispatch_id, {})
                dispatch_title = dispatch_info.get("title", "")
                dispatch_code = dispatch_info.get("dispatchCode", "")
                if dispatch_title:
                    disp_display = f"{dispatch_title}"
                elif dispatch_code:
                    disp_display = DISPATCH_CODES.get(dispatch_code, dispatch_code)
                else:
                    disp_display = f"ID {dispatch_id}"

                wave_name = WAVE_TYPES.get(wave_type, f"Wave {wave_type}")

                # Color code dispatch
                if "Charge" in disp_display or "charge" in str(dispatch_code):
                    disp_color = "cyan"
                elif "Export" in disp_display or "export" in str(dispatch_code):
                    disp_color = "yellow"
                elif "Self" in disp_display or "self" in str(dispatch_code).lower():
                    disp_color = "green"
                elif "Standby" in disp_display:
                    disp_color = "dim"
                else:
                    disp_color = "dim"

                max_str = f"{max_soc}%" if max_soc else "—"
                min_str = f"{min_soc}%" if min_soc else "—"
                solar_str = str(solar_cutoff) if solar_cutoff else "0"

                print(f"  {start:<12}{end:<12}{name:<14}{c(disp_color, f'{disp_display:<22s}')}{wave_name:<12}{max_str:<10}{min_str:<10}{solar_str}")

            print()
            print_kv("Blocks", f"{len(detail_list)} time blocks configured")
        else:
            print_warning("No schedule blocks found.")

    except Exception as e:
        print_warning(f"Could not retrieve schedule blocks: {e}")

    # ── Raw Dispatch Detail ──────────────────────────────────────
    if show_dispatch and dispatch_result:
        print_section("⚙️", "Raw Dispatch Detail")
        default_vo = dispatch_result.get("detailDefaultVo", {})
        tou_dispatch_list = default_vo.get("touDispatchList", [])

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
        if buy is not None and buy != 0:
            rates.append((name, buy, sell))
    return rates
