"""TOU command — Time-of-Use schedule inspection."""

import pprint

from franklinwh_cloud.cli_output import (
    print_header, print_section, print_kv, print_json_output, print_warning,
    c,
)


async def run(client, *, json_output: bool = False, show_dispatch: bool = False):
    """Execute the TOU command."""

    if json_output:
        output = {}
        output["tou_list"] = await client.get_gateway_tou_list()
        if show_dispatch:
            output["dispatch_detail"] = await client.get_tou_dispatch_detail()
        output["charge_power"] = await client.get_charge_power_details()
        print_json_output(output)
        return

    print_header("Time-of-Use Schedule")

    # ── TOU List ──────────────────────────────────────────────────
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

    # ── Dispatch Detail ───────────────────────────────────────────
    if show_dispatch:
        print_section("⚙️ ", "Dispatch Detail")
        try:
            res = await client.get_tou_dispatch_detail()
            result = res.get("result", {})
            template = result.get("template", {})

            print_kv("Template ID", template.get("templateId", "?"))
            print_kv("Name", template.get("name", "?"))
            print_kv("Utility", template.get("electricCompany", "?"))
            print_kv("DER Schedule", template.get("derSchdule", "?"))
            print_kv("Last Updated", template.get("updateTime", "?"))

            print_kv("PTO Date", result.get("ptoDate", "?"))
            print_kv("NEM Type", result.get("nemType", "?"))
            print_kv("Battery Savings", result.get("batterySavingsFlag", "?"))

            # Battery info
            print_kv("aPower Count", result.get("apowerCount", "?"))
            print_kv("Online Flag", result.get("onlineFlag", "?"))
            print_kv("Battery Capacity", f'{result.get("batteryRatedCapacity", "?")} kWh')

            # Strategy list
            strategies = result.get("strategyList", [])
            if strategies:
                print_section("📊", f"Strategies ({len(strategies)} schedules)")
                for i, strat in enumerate(strategies):
                    name = strat.get("name", f"Schedule {i+1}")
                    wave = strat.get("waveType", "?")
                    dispatch = strat.get("dispatchCode", "?")
                    start = strat.get("startTime", "?")
                    end = strat.get("endTime", "?")
                    print_kv(name, f"{start}–{end}  Wave: {wave}  Dispatch: {dispatch}")

        except Exception as e:
            print_warning(f"Could not retrieve dispatch detail: {e}")

    # ── Charge Power Details ──────────────────────────────────────
    print_section("🔌", "Charge Power")
    try:
        res = await client.get_charge_power_details()
        if isinstance(res, dict):
            result = res.get("result", res)
            if isinstance(result, dict):
                for key, val in result.items():
                    if not key.startswith("_"):
                        print_kv(key, val)
            else:
                print_kv("Details", str(result))
        else:
            print_kv("Details", str(res))
    except Exception as e:
        print_warning(f"Could not retrieve charge power details: {e}")

    print()
