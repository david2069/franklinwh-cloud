"""TOU command — Time-of-Use schedule inspection and control.

Shows tariff configuration, the actual dispatch schedule (matching FEM),
rate information, and charge power estimates. Supports multiple seasons,
day types (weekday/weekend/every day), and pricing tiers.

Usage:
    franklinwh-cli tou                # schedule overview with dispatch blocks
    franklinwh-cli tou --dispatch     # include raw dispatch metadata
    franklinwh-cli tou --next         # current/next dispatch with remaining time
    franklinwh-cli tou --json         # machine-readable

    franklinwh-cli tou --set GRID_CHARGE --start 11:30 --end 15:00
    franklinwh-cli tou --set GRID_CHARGE --start 11:30 --end 15:00 --default HOME
    franklinwh-cli tou --set SELF
    franklinwh-cli tou --set CUSTOM --file schedule.json
"""

import json
import re
from datetime import datetime, timedelta

from franklinwh_cloud.cli_output import (
    print_header, print_section, print_kv, print_json_output, print_warning,
    print_success, print_error, c,
)
from franklinwh_cloud.const import DISPATCH_CODES, WAVE_TYPES


async def run(client, *, json_output: bool = False, show_dispatch: bool = False,
              set_mode: str | None = None, start: str | None = None,
              end: str | None = None, default_mode: str = "SELF",
              schedule_file: str | None = None, rates_file: str | None = None,
              season_name: str | None = None, season_months: str | None = None,
              day_type_str: str | None = None, show_next: bool = False):
    """Execute the TOU command."""

    # ── tou --set ────────────────────────────────────────────────
    if set_mode:
        await _handle_set(client, set_mode, start, end, default_mode,
                          schedule_file, rates_file, season_name,
                          season_months, day_type_str, json_output)
        return

    # ── tou --next ───────────────────────────────────────────────
    if show_next:
        await _handle_next(client, json_output)
        return

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


def _validate_time(time_str: str) -> bool:
    """Validate HH:MM time format."""
    return bool(re.match(r'^([01]?\d|2[0-3]):[0-5]\d$', time_str) or time_str == "24:00")


def _dispatch_name(dispatch_id: int) -> str:
    """Resolve dispatch ID to human-readable name."""
    return DISPATCH_CODES.get(dispatch_id, f"Unknown ({dispatch_id})")


# ── tou --set handler ───────────────────────────────────────────────

_DAY_TYPE_MAP = {"everyday": 3, "weekday": 1, "weekend": 2}


def _load_rates_file(rates_file: str):
    """Load pricing rates from a JSON file."""
    try:
        with open(rates_file, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print_error(f"Rates file not found: {rates_file}")
        return None
    except json.JSONDecodeError as e:
        print_error(f"Invalid JSON in rates file {rates_file}: {e}")
        return None


def _build_extra_kwargs(rates_file, season_name, season_months, day_type_str, json_output):
    """Build keyword arguments for set_tou_schedule from CLI flags."""
    kwargs = {}

    # Rates
    if rates_file:
        rates = _load_rates_file(rates_file)
        if rates is None:
            return None  # signal error
        kwargs["rates"] = rates
        if not json_output:
            print(f"  Loading pricing rates from {rates_file}")

    # Seasons
    if season_name or season_months:
        name = season_name or "Season 1"
        months = season_months or "1,2,3,4,5,6,7,8,9,10,11,12"
        kwargs["seasons"] = [{"name": name, "months": months}]
        if not json_output:
            print(f"  Season: {name} (months: {months})")

    # Day type
    if day_type_str:
        kwargs["day_type"] = _DAY_TYPE_MAP.get(day_type_str, 3)
        if not json_output:
            print(f"  Day type: {day_type_str}")

    return kwargs


async def _handle_set(client, set_mode: str, start: str | None, end: str | None,
                      default_mode: str | None, schedule_file: str | None,
                      rates_file: str | None, season_name: str | None,
                      season_months: str | None, day_type_str: str | None,
                      json_output: bool):
    """Handle tou --set command."""
    from franklinwh_cloud.const import dispatchCodeType, WaveType
    from franklinwh_cloud.exceptions import InvalidTOUScheduleOption

    mode = set_mode.upper().replace("-", "_").replace(" ", "_")

    # Build extra kwargs from CLI flags
    extra_kwargs = _build_extra_kwargs(
        rates_file, season_name, season_months, day_type_str, json_output
    )
    if extra_kwargs is None:
        return  # error loading rates file

    # ── CUSTOM --file ────────────────────────────────────────────
    if mode == "CUSTOM" and schedule_file:
        try:
            with open(schedule_file, "r") as f:
                schedule = json.load(f)
        except FileNotFoundError:
            print_error(f"File not found: {schedule_file}")
            return
        except json.JSONDecodeError as e:
            print_error(f"Invalid JSON in {schedule_file}: {e}")
            return

        if not isinstance(schedule, list):
            print_error("Schedule file must contain a JSON array of time blocks.")
            return

        if not json_output:
            print(f"Loading schedule from {schedule_file} ({len(schedule)} blocks)...")

        try:
            result = await client.set_tou_schedule(
                touMode="CUSTOM",
                touSchedule=schedule,
                default_mode=default_mode.upper() if default_mode else "SELF",
                **extra_kwargs,
            )
            if await _print_set_result(result, json_output, client):
                return
        except (InvalidTOUScheduleOption, Exception) as e:
            _print_set_error(e, json_output)
        return

    # ── CUSTOM without --file ────────────────────────────────────
    if mode == "CUSTOM" and not schedule_file:
        print_error("CUSTOM mode requires --file schedule.json")
        return

    # ── Single-window mode (--start / --end) ─────────────────────
    if start and end:
        if not _validate_time(start):
            print_error(f"Invalid start time: {start} (expected HH:MM)")
            return
        if not _validate_time(end):
            print_error(f"Invalid end time: {end} (expected HH:MM)")
            return

        # --default: warn if not specified, default to SELF
        if not default_mode:
            default_mode = "SELF"
            if not json_output:
                print_warning(f"No --default specified — remaining times will use Self-Consumption (dispatchId=6).")
                print(f"  Tip: use --default MODE to change (SELF, HOME, STANDBY, SOLAR, GRID_CHARGE, GRID_EXPORT)")

        # Resolve dispatch ID
        dispatch_id = DISPATCH_CODES.get(mode)
        if dispatch_id is None:
            print_error(f"Unknown dispatch mode: {set_mode}")
            print(f"  Available: GRID_CHARGE, GRID_EXPORT, SELF, HOME, STANDBY, SOLAR")
            return

        # Validate default mode
        default_dispatch_id = DISPATCH_CODES.get(default_mode.upper())
        if default_dispatch_id is None:
            print_error(f"Unknown default mode: {default_mode}")
            print(f"  Available: SELF, HOME, STANDBY, SOLAR, GRID_CHARGE, GRID_EXPORT")
            return

        schedule = [{
            "name":          WAVE_TYPES.get(0, "Off-Peak"),
            "startHourTime": start,
            "endHourTime":   end,
            "waveType":      WaveType.OFF_PEAK.value,
            "dispatchId":    dispatch_id,
        }]

        if not json_output:
            default_name = DISPATCH_CODES.get(default_dispatch_id, "Unknown")
            print(f"Setting {_dispatch_name(dispatch_id)} from {start} to {end}")
            print(f"  Remaining times: {default_name} (dispatchId={default_dispatch_id})")

        try:
            result = await client.set_tou_schedule(
                touMode="CUSTOM",
                touSchedule=schedule,
                default_mode=default_mode.upper(),
                **extra_kwargs,
            )
            if await _print_set_result(result, json_output, client):
                return
        except (InvalidTOUScheduleOption, Exception) as e:
            _print_set_error(e, json_output)
        return

    # ── Full-day simple mode (no --start/--end) ──────────────────
    if not start and not end:
        dispatch_id = DISPATCH_CODES.get(mode)
        if dispatch_id is None:
            print_error(f"Unknown dispatch mode: {set_mode}")
            print(f"  Available: GRID_CHARGE, GRID_EXPORT, SELF, HOME, STANDBY, SOLAR")
            return

        if not json_output:
            print(f"Setting full-day {_dispatch_name(dispatch_id)}...")

        try:
            result = await client.set_tou_schedule(touMode=mode, **extra_kwargs)
            if await _print_set_result(result, json_output, client):
                return
        except (InvalidTOUScheduleOption, Exception) as e:
            _print_set_error(e, json_output)
        return

    # ── Partial args ─────────────────────────────────────────────
    print_error("Both --start and --end are required for a time window.")
    print(f"  Usage: franklinwh-cli tou --set {set_mode} --start HH:MM --end HH:MM")


async def _print_set_result(result: dict, json_output: bool, client=None):
    """Print the result of a set_tou_schedule call."""
    if json_output:
        print_json_output(result)
        return True

    if result.get("code") == 200:
        tou_id = result.get("result", {}).get("id", "?")
        print_success(f"Schedule submitted — touId={tou_id}")
        print(f"  {c('dim', 'The aGate will apply this within ~1 minute.')}")
        print()
        # Show the resulting schedule
        if client:
            await _handle_next(client, json_output=False)
        return True
    else:
        code = result.get("code", "?")
        msg = result.get("msg", result.get("message", "Unknown error"))
        print_error(f"API returned code={code}: {msg}")
        return False


def _print_set_error(error: Exception, json_output: bool):
    """Print a set_tou_schedule error."""
    if json_output:
        print_json_output({"error": str(error), "type": type(error).__name__})
    else:
        print_error(f"{type(error).__name__}: {error}")


# ── tou --next handler ──────────────────────────────────────────────

async def _handle_next(client, json_output: bool):
    """Handle tou --next: show current/next dispatch with remaining time."""

    res = await client.get_tou_dispatch_detail()
    result = res.get("result", {})
    strategies = result.get("strategyList", [])

    if not strategies:
        if json_output:
            print_json_output({"error": "No TOU schedule configured"})
        else:
            print_warning("No TOU schedule configured.")
        return

    # Build dispatch lookup from detailDefaultVo
    default_vo = result.get("detailDefaultVo", {})
    tou_dispatch_list = default_vo.get("touDispatchList", [])
    dispatch_lookup = {}
    for d in tou_dispatch_list:
        if d.get("id") is not None:
            dispatch_lookup[d["id"]] = d

    # Get blocks from first season, first day type
    day_types = strategies[0].get("dayTypeVoList", [])
    if not day_types:
        if json_output:
            print_json_output({"error": "No day types configured"})
        else:
            print_warning("No day types configured.")
        return

    blocks = day_types[0].get("detailVoList", [])
    if not blocks:
        if json_output:
            print_json_output({"error": "No time blocks configured"})
        else:
            print_warning("No time blocks configured.")
        return

    now = datetime.now()
    now_time = now.strftime("%H:%M")
    now_minutes = now.hour * 60 + now.minute

    current_block = None
    next_block = None
    current_remaining = None
    next_duration = None

    # Sort blocks by start time
    sorted_blocks = sorted(blocks, key=lambda b: b.get("startHourTime", "00:00"))

    for i, block in enumerate(sorted_blocks):
        start_str = block.get("startHourTime", "00:00")
        end_str = block.get("endHourTime", "24:00")

        start_mins = _time_to_minutes(start_str)
        end_mins = _time_to_minutes(end_str)

        if start_mins <= now_minutes < end_mins:
            current_block = block
            remaining_mins = end_mins - now_minutes
            current_remaining = _format_duration(remaining_mins * 60 - now.second)
            # Next block
            if i + 1 < len(sorted_blocks):
                next_block = sorted_blocks[i + 1]
            elif len(sorted_blocks) > 0:
                next_block = sorted_blocks[0]  # wraps to start of day

            if next_block:
                nb_start = _time_to_minutes(next_block.get("startHourTime", "00:00"))
                nb_end = _time_to_minutes(next_block.get("endHourTime", "24:00"))
                next_duration = _format_duration((nb_end - nb_start) * 60)
            break

    # JSON output
    if json_output:
        output = {"now": now.strftime("%H:%M:%S"), "blocks": []}
        for block in sorted_blocks:
            entry = {
                "start": block.get("startHourTime"),
                "end": block.get("endHourTime"),
                "dispatchId": block.get("dispatchId"),
                "dispatch": _resolve_dispatch_name(block.get("dispatchId"), dispatch_lookup),
                "waveType": block.get("waveType"),
                "active": block is current_block,
            }
            if block is current_block:
                entry["remaining"] = current_remaining
            output["blocks"].append(entry)
        if current_block:
            output["current"] = {
                "dispatch": _resolve_dispatch_name(current_block.get("dispatchId"), dispatch_lookup),
                "remaining": current_remaining,
            }
        if next_block:
            output["next"] = {
                "dispatch": _resolve_dispatch_name(next_block.get("dispatchId"), dispatch_lookup),
                "duration": next_duration,
                "start": next_block.get("startHourTime"),
            }
        print_json_output(output)
        return

    # Rich output
    print_header("TOU Schedule — Current & Next")

    print_section("📋", "Schedule")
    print(f"  {'':3}{'START':<10}{'END':<10}{'DISPATCH':<32}{'WAVE':<12}{'DURATION'}")
    print(f"  {'':3}{'─'*9} {'─'*9} {'─'*31} {'─'*11} {'─'*8}")

    for block in sorted_blocks:
        start_str = block.get("startHourTime", "00:00")
        end_str = block.get("endHourTime", "24:00")
        dispatch_id = block.get("dispatchId", 0)
        wave_type = block.get("waveType", 0)

        disp_name = _resolve_dispatch_name(dispatch_id, dispatch_lookup)
        wave_name = WAVE_TYPES.get(wave_type, f"Wave {wave_type}")
        disp_color = _dispatch_color(disp_name)

        s_mins = _time_to_minutes(start_str)
        e_mins = _time_to_minutes(end_str)
        dur = _format_duration_short((e_mins - s_mins) * 60)

        is_active = block is current_block
        marker = c("green", "▸ ") if is_active else "  "
        name_formatted = c("bold", c(disp_color, f"{disp_name:<32s}")) if is_active else c(disp_color, f"{disp_name:<32s}")

        print(f"  {marker}{start_str:<10}{end_str:<10}{name_formatted}{wave_name:<12}{dur}")

    print()

    # Current + Next summary
    print_section("⏱️ ", "Now")
    if current_block:
        cur_name = _resolve_dispatch_name(current_block.get("dispatchId"), dispatch_lookup)
        cur_color = _dispatch_color(cur_name)
        print_kv("Current", f"{c(cur_color, cur_name)}")
        print_kv("Remaining", f"{c('bold', current_remaining)}")
    else:
        print_kv("Current", c("dim", "Unknown (no matching block for current time)"))

    if next_block:
        next_name = _resolve_dispatch_name(next_block.get("dispatchId"), dispatch_lookup)
        next_color = _dispatch_color(next_name)
        print_kv("Next", f"{c(next_color, next_name)} at {next_block.get('startHourTime', '?')}")
        print_kv("Duration", next_duration)
    print()


def _resolve_dispatch_name(dispatch_id: int, dispatch_lookup: dict) -> str:
    """Resolve dispatch ID to human-readable name via lookup or fallback."""
    info = dispatch_lookup.get(dispatch_id, {})
    title = info.get("title", "")
    if title:
        return title
    return DISPATCH_CODES.get(dispatch_id, f"Dispatch {dispatch_id}")


def _time_to_minutes(time_str: str) -> int:
    """Convert HH:MM to minutes since midnight."""
    if time_str == "24:00":
        return 1440
    parts = time_str.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def _format_duration(total_seconds: int) -> str:
    """Format seconds as HH:MM:SS."""
    if total_seconds < 0:
        total_seconds = 0
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _format_duration_short(total_seconds: int) -> str:
    """Format seconds as Xh Ym."""
    if total_seconds < 0:
        total_seconds = 0
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m"
