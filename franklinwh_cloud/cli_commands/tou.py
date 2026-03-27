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
import asyncio
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
              day_type_str: str | None = None, wait_confirm: bool = False,
              show_next: bool = False, show_price: bool = False,
              active_only: bool = False, multi_season_file: str | None = None,
              show_all_rates: bool = False, extended: bool = False):
    """Execute the TOU command."""

    # ── tou --price ───────────────────────────────────────────────
    if show_price:
        await _handle_price(client, json_output, active_only, show_all_rates)
        return

    # ── tou --multi-season ────────────────────────────────────────
    if multi_season_file:
        await _handle_multi_season(client, multi_season_file, json_output)
        return

    # ── tou --set ────────────────────────────────────────────────
    if set_mode:
        await _handle_set(client, set_mode, start, end, default_mode,
                          schedule_file, rates_file, season_name,
                          season_months, day_type_str, wait_confirm,
                          json_output)
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
            from datetime import datetime
            current_month = str(datetime.now().month)
            total_blocks = 0
            
            for season_idx, season in enumerate(strategies):
                months = season.get("month", "")
                
                # Check --current flag constraint
                if getattr(args, "show_current", False):
                    active_months = [m.strip() for m in months.split(",") if m.strip()]
                    if current_month not in active_months:
                        continue
                        
                season_name = season.get("seasonName", f"Season {season_idx + 1}")
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
                            sell_str = f"  Sell: ${sell:.2f}"
                            print_kv(f"  💰 {rate_name}", f"Buy: ${buy:.2f}{sell_str}")
                        print()

                    # ── Dispatch periods ─────────────────────────
                    periods = day_type.get("detailVoList", [])
                    if periods:
                        has_soc = extended or any(b.get("maxChargeSoc") is not None or b.get("minDischargeSoc") is not None for b in periods)

                        # Table header
                        if has_soc:
                            print(f"  {'START':<10}{'END':<10}{'NAME':<14}{'DISPATCH':<24}{'WAVE':<12}{'MAX SoC':<9}{'MIN SoC':<9}{'BUY':<7}{'SELL'}")
                            print(f"  {'─'*9} {'─'*9} {'─'*13} {'─'*23} {'─'*11} {'─'*8} {'─'*8} {'─'*6} {'─'*6}")
                        else:
                            print(f"  {'START':<10}{'END':<10}{'NAME':<14}{'DISPATCH':<24}{'WAVE':<12}{'BUY':<7}{'SELL'}")
                            print(f"  {'─'*9} {'─'*9} {'─'*13} {'─'*23} {'─'*11} {'─'*6} {'─'*6}")

                        for block in periods:
                            start = block.get("startHourTime", "?")
                            end = block.get("endHourTime", "?")
                            name = block.get("name", "?")
                            dispatch_id = block.get("dispatchId", 0)
                            wave_type = block.get("waveType", 0)
                            max_soc = block.get("maxChargeSoc")
                            min_soc = block.get("minDischargeSoc")

                            # Resolve dispatch name
                            disp_display = _resolve_dispatch(dispatch_id, dispatch_lookup)
                            # Truncate long names
                            if len(disp_display) > 22:
                                disp_display = disp_display[:20] + "…"

                            wave_name = WAVE_TYPES.get(wave_type, f"Wave {wave_type}")
                            disp_color = _dispatch_color(disp_display)

                            max_str = f"{max_soc}%" if max_soc else "—"
                            min_str = f"{min_soc}%" if min_soc else "—"
                            soc_cols = f"{max_str:<9}{min_str:<9}" if has_soc else ""
                            
                            w_buy, w_sell = 0.0, 0.0
                            if wave_type == 0:
                                w_buy, w_sell = day_type.get("eleticRateValley"), day_type.get("eleticSellValley")
                            elif wave_type == 1:
                                w_buy, w_sell = day_type.get("eleticRateShoulder"), day_type.get("eleticSellShoulder")
                            elif wave_type == 2:
                                w_buy, w_sell = day_type.get("eleticRatePeak"), day_type.get("eleticSellPeak")
                            elif wave_type == 3:
                                w_buy, w_sell = day_type.get("eleticRateSharp"), day_type.get("eleticSellSharp")
                            elif wave_type == 4:
                                w_buy, w_sell = day_type.get("eleticRateSuperOffPeak"), day_type.get("eleticSellSuperOffPeak")

                            buy_str = f"${w_buy or 0.0:.2f}"
                            sell_str = f"${w_sell or 0.0:.2f}"

                            print(f"  {start:<10}{end:<10}{name:<14}{c(disp_color, f'{disp_display:<24s}')}{wave_name:<12}{soc_cols}{buy_str:<7}{sell_str}")

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
    """Extract rate tiers from day type data, defaulting to zero if not set."""
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
            data = json.load(f)
    except FileNotFoundError:
        print_error(f"Rates file not found: {rates_file}")
        return None
    except json.JSONDecodeError as e:
        print_error(f"Invalid JSON in rates file {rates_file}: {e}")
        return None

    # Validate the loaded rates
    errors = validate_rates(data)
    if errors:
        for err in errors:
            print_error(f"Rates validation: {err}")
        return None
    return data


# Valid rate keys (matches TouMixin.RATE_FIELD_MAP)
_VALID_RATE_KEYS = {
    "peak", "sharp", "shoulder", "off_peak", "super_off_peak",
    "sell_peak", "sell_sharp", "sell_shoulder", "sell_off_peak",
    "sell_super_off_peak", "grid_fee",
}


def validate_rates(rates: dict) -> list[str]:
    """Validate a rates dict. Returns list of error strings (empty = valid).

    Checks:
    - Must be a dict (not list, string, etc.)
    - No unknown keys (typo protection)
    - All values must be numeric (int or float)
    - No negative values
    - No unreasonably high values (> 100 $/kWh as sanity cap)
    - No duplicate keys (JSON spec allows but we reject)
    """
    errors = []

    if not isinstance(rates, dict):
        return [f"Expected a JSON object/dict, got {type(rates).__name__}"]

    if not rates:
        return ["Rates dict is empty — provide at least one rate key"]

    for key, value in rates.items():
        if key not in _VALID_RATE_KEYS:
            errors.append(f"Unknown rate key '{key}'. Valid: {', '.join(sorted(_VALID_RATE_KEYS))}")
        if not isinstance(value, (int, float)):
            errors.append(f"Rate '{key}' must be numeric, got {type(value).__name__}: {value!r}")
        elif value < 0:
            errors.append(f"Rate '{key}' cannot be negative: {value}")
        elif value > 100:
            errors.append(f"Rate '{key}' = {value} seems unreasonably high (> $100/kWh)")

    return errors


def validate_season_months(season_months: str) -> list[str]:
    """Validate a comma-separated months string. Returns list of errors.

    Checks:
    - All values must be integers 1-12
    - No duplicates within the same season
    - No empty values
    """
    errors = []
    if not season_months:
        return []

    parts = [p.strip() for p in season_months.split(",")]
    seen = set()
    for part in parts:
        if not part:
            errors.append("Empty month value in months list")
            continue
        try:
            m = int(part)
        except ValueError:
            errors.append(f"Invalid month '{part}' — must be an integer 1-12")
            continue
        if m < 1 or m > 12:
            errors.append(f"Month {m} out of range — must be 1-12")
        elif m in seen:
            errors.append(f"Duplicate month {m} in season")
        seen.add(m)

    return errors


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
        # Validate months
        month_errors = validate_season_months(months)
        if month_errors:
            for err in month_errors:
                print_error(f"Season validation: {err}")
            return None
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
                      wait_confirm: bool, json_output: bool):
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
            if await _print_set_result(result, json_output, client, wait_confirm):
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
            if await _print_set_result(result, json_output, client, wait_confirm):
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
            if await _print_set_result(result, json_output, client, wait_confirm):
                return
        except (InvalidTOUScheduleOption, Exception) as e:
            _print_set_error(e, json_output)
        return

    # ── Partial args ─────────────────────────────────────────────
    print_error("Both --start and --end are required for a time window.")
    print(f"  Usage: franklinwh-cli tou --set {set_mode} --start HH:MM --end HH:MM")


async def _print_set_result(result: dict, json_output: bool, client=None,
                            wait_confirm: bool = False):
    """Print the result of a set_tou_schedule call."""
    if json_output:
        output = dict(result)
        if wait_confirm and client and result.get("code") == 200:
            wait_result = await _wait_for_dispatch(client)
            output["wait_result"] = wait_result
        print_json_output(output)
        return True

    if result.get("code") == 200:
        tou_id = result.get("result", {}).get("id", "?")
        print_success(f"Schedule submitted — touId={tou_id}")

        if wait_confirm and client:
            await _wait_for_dispatch(client, verbose=True)
        else:
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


async def _wait_for_dispatch(client, *, verbose: bool = False,
                             timeout: int = 90, interval: int = 5):
    """Poll touSendStatus until dispatch is confirmed applied.

    The aGate sets touSendStatus=1 when a schedule is pending.
    When applied, it clears to 0. We also check the work mode
    changed to TOU (workMode=1).

    Returns dict with confirmation status for JSON output.
    """
    if verbose:
        print(f"  {c('dim', 'Waiting for dispatch confirmation (up to {timeout}s)...')}")

    elapsed = 0
    confirmed = False
    tou_active = False
    last_status = None

    while elapsed < timeout:
        try:
            res = await client.get_gateway_tou_list()
            result = res.get("result", {})
            send_status = result.get("touSendStatus", None)
            work_mode = result.get("workMode", None)

            # touSendStatus: 0 = applied, 1 = pending
            if send_status == 0 or send_status is None:
                confirmed = True
            # workMode: 1 = TOU
            tou_active = (work_mode == 1)
            last_status = {
                "touSendStatus": send_status,
                "workMode": work_mode,
            }

            if confirmed:
                if verbose:
                    if tou_active:
                        print_success(f"Dispatch confirmed — TOU mode active (took {elapsed}s)")
                    else:
                        print_warning(f"Dispatch sent but workMode={work_mode} (expected 1=TOU) after {elapsed}s")
                return {"confirmed": True, "tou_active": tou_active,
                        "elapsed_seconds": elapsed, **last_status}

            if verbose and elapsed % 15 == 0 and elapsed > 0:
                print(f"  {c('dim', f'Still pending... touSendStatus={send_status} ({elapsed}s)')}")

        except Exception as e:
            if verbose:
                print(f"  {c('dim', f'Poll error: {e}')}")

        await asyncio.sleep(interval)
        elapsed += interval

    # Timeout
    if verbose:
        print_warning(f"Timed out after {timeout}s — touSendStatus may still be pending")
    return {"confirmed": False, "tou_active": tou_active,
            "elapsed_seconds": elapsed, "timeout": True,
            **(last_status or {})}


def _print_set_error(error: Exception, json_output: bool):
    """Print a set_tou_schedule error."""
    if json_output:
        print_json_output({"error": str(error), "type": type(error).__name__})
    else:
        print_error(f"{type(error).__name__}: {error}")


# ── tou --next handler ──────────────────────────────────────────────

async def _handle_next(client, json_output: bool):
    """Handle tou --next: show current/next dispatch with remaining time.

    Uses get_tou_info(1) for current/next identification and
    get_tou_info(2) for the full schedule table display.
    """
    # Get current/next block info from the API mixin (single source of truth)
    tou_info = await client.get_tou_info(1)

    if not tou_info:
        if json_output:
            print_json_output({"error": "No TOU schedule configured or no matching season"})
        else:
            print_warning("No TOU schedule configured or no matching season for current month.")
        return

    # Get full schedule for table display
    all_blocks = await client.get_tou_info(2)
    if not all_blocks:
        if json_output:
            print_json_output({"error": "No time blocks configured"})
        else:
            print_warning("No time blocks configured.")
        return

    # Build dispatch lookup for display names
    res = await client.get_tou_dispatch_detail()
    result = res.get("result", {})
    default_vo = result.get("detailDefaultVo", {})
    tou_dispatch_list = default_vo.get("touDispatchList", [])
    dispatch_lookup = {}
    for d in tou_dispatch_list:
        if d.get("id") is not None:
            dispatch_lookup[d["id"]] = d

    now = datetime.now()
    now_minutes = now.hour * 60 + now.minute

    # Sort blocks for display
    sorted_blocks = sorted(all_blocks, key=lambda b: _time_to_minutes(b.get("startHourTime", "00:00")))

    # Identify active block from tou_info
    active_start = tou_info.get("activeStartTime")
    active_end = tou_info.get("activeEndTime")
    active_remaining = tou_info.get("activeRemainingTime")

    # Next block info from tou_info
    next_start = tou_info.get("nextStartTime")
    next_end = tou_info.get("nextEndTime")
    next_dispatch_title = tou_info.get("nextTOUtitle", "")

    # JSON output
    if json_output:
        output = {"now": now.strftime("%H:%M:%S"), "blocks": []}
        for block in sorted_blocks:
            b_start = block.get("startHourTime", "")
            b_end = block.get("endHourTime", "")
            is_active = (b_start == active_start and b_end == active_end)
            entry = {
                "start": b_start,
                "end": b_end,
                "dispatchId": block.get("dispatchId"),
                "dispatch": _resolve_dispatch_name(block.get("dispatchId"), dispatch_lookup),
                "waveType": block.get("waveType"),
                "active": is_active,
            }
            if is_active and active_remaining:
                entry["remaining"] = active_remaining
            output["blocks"].append(entry)
        if active_start:
            output["current"] = {
                "dispatch": tou_info.get("activeTOUtitle", ""),
                "remaining": active_remaining,
            }
        if next_start:
            output["next"] = {
                "dispatch": next_dispatch_title,
                "start": next_start,
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

        is_active = (start_str == active_start and end_str == active_end)
        marker = c("green", "▸ ") if is_active else "  "
        name_formatted = c("bold", c(disp_color, f"{disp_name:<32s}")) if is_active else c(disp_color, f"{disp_name:<32s}")

        print(f"  {marker}{start_str:<10}{end_str:<10}{name_formatted}{wave_name:<12}{dur}")

    print()

    # Current + Next summary
    print_section("⏱️ ", "Now")
    if active_start:
        cur_title = tou_info.get("activeTOUtitle", "Unknown")
        cur_color = _dispatch_color(cur_title)
        print_kv("Current", f"{c(cur_color, cur_title)}")
        print_kv("Remaining", f"{c('bold', active_remaining or '?')}")
    else:
        print_kv("Current", c("dim", "Unknown (no matching block for current time)"))

    if next_start:
        next_title = tou_info.get("nextTOUtitle", "Unknown")
        next_color = _dispatch_color(next_title)
        print_kv("Next", f"{c(next_color, next_title)} at {next_start}")
        if next_end:
            nb_start = _time_to_minutes(next_start)
            nb_end = _time_to_minutes(next_end)
            print_kv("Duration", _format_duration((nb_end - nb_start) * 60))
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


# ── tou --price handler ─────────────────────────────────────────────

async def _handle_price(client, json_output: bool, active_only: bool = False, show_all_rates: bool = False):
    """Handle tou --price: show the current TOU pricing tier and rates."""
    price = await client.get_current_tou_price(option=1 if active_only else 0)

    if not price:
        if json_output:
            print_json_output({"error": "No TOU schedule configured or no block for current time."})
        else:
            print_warning("No TOU schedule configured or no active block for current time.")
        return

    if json_output:
        print_json_output(price)
        return

    # If --active-only is set natively, do exactly what it says on the tin.
    if active_only:
        b = price.get("buy_rate") or 0.0
        s = price.get("sell_rate") or 0.0
        print(f"Buy: {b:.2f} | Sell: {s:.2f}")
        return

    print_header("Current TOU Pricing Tier")

    now_str = datetime.now().strftime("%H:%M")
    print_section("⏱", f"Now: {now_str}")

    # Tier badge
    wave_name = price.get("wave_type_name", "Unknown")
    wave_type = price.get("wave_type", 0)
    wave_color = {0: "green", 1: "yellow", 2: "red", 3: "red", 4: "green"}.get(wave_type, "dim")
    print_kv("Pricing Tier", c(wave_color, wave_name))
    print_kv("Season", price.get("season_name", "?"))
    print_kv("Day Type", price.get("day_type_name", "?"))
    print_kv("Block", f"{price.get('block_name', '?')}  ({price.get('block_start')} → {price.get('block_end')})")

    mins = price.get("minutes_remaining", 0)
    h, m = divmod(mins, 60)
    remaining_str = f"{h}h {m:02d}m" if h > 0 else f"{m}m"
    remaining_color = "green" if mins > 30 else "yellow" if mins > 10 else "red"
    print_kv("Time Remaining", c(remaining_color, remaining_str))

    dispatch_id = price.get("dispatch_id")
    if dispatch_id:
        print_kv("Dispatch Strategy", f"ID {dispatch_id}")

    # Rates
    if not show_all_rates:
        b = price.get("buy_rate") or 0.0
        s = price.get("sell_rate") or 0.0
        sell_str = f"   Sell: ${s:.2f}"
        print()
        print_kv("  💰 Current Rate", f"Buy: ${b:.2f}{sell_str}")
        print()
    else:
        buy = price.get("buy_rates", {})
        sell = price.get("sell_rates", {})
        rate_labels = [
            ("On-Peak", "peak"), ("Shoulder", "shoulder"), ("Off-Peak", "valley"),
            ("Sharp", "sharp"), ("Super Off-Peak", "super_off_peak"),
        ]
        print()
        for label, key in rate_labels:
            b = buy.get(key) or 0.0
            s = sell.get(key) or 0.0
            sell_str = f"   Sell: ${s:.2f}"
            print_kv(f"  💰 {label}", f"Buy: ${b:.2f}{sell_str}")

        print()


# ── tou --multi-season handler ──────────────────────────────────────

async def _handle_multi_season(client, multi_season_file: str, json_output: bool):
    """Handle tou --multi-season FILE: load and apply a multi-season strategy file.

    The FILE must be a JSON file with a 'strategyList' array (matching the
    HAR fixture format in tests/fixtures/tou_save_multi_season.json), OR it
    can be a bare strategyList array itself.
    """
    from franklinwh_cloud.exceptions import InvalidTOUScheduleOption

    try:
        with open(multi_season_file, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        if json_output:
            print_json_output({"error": f"File not found: {multi_season_file}"})
        else:
            print_error(f"File not found: {multi_season_file}")
        return
    except json.JSONDecodeError as e:
        if json_output:
            print_json_output({"error": f"Invalid JSON: {e}"})
        else:
            print_error(f"Invalid JSON in {multi_season_file}: {e}")
        return

    # Accept either {"strategyList": [...]} or bare [...]
    if isinstance(data, dict):
        strategy_list = data.get("strategyList", data.get("strategy_list"))
    elif isinstance(data, list):
        strategy_list = data
    else:
        if json_output:
            print_json_output({"error": "File must contain a JSON array or an object with 'strategyList'"})
        else:
            print_error("File must contain a JSON array or an object with 'strategyList'.")
        return

    if not strategy_list:
        if json_output:
            print_json_output({"error": "strategyList is empty"})
        else:
            print_error("strategyList is empty.")
        return

    if not json_output:
        print(f"Loading {len(strategy_list)} season(s) from {multi_season_file}...")

    try:
        result = await client.set_tou_schedule_multi(strategy_list)
        if json_output:
            print_json_output(result)
        elif result.get("code") == 200:
            tou_id = result.get("result", {}).get("id", "?")
            print_success(f"Multi-season schedule submitted — touId={tou_id}")
            print(f"  {c('dim', 'The aGate will apply this within ~1 minute.')}")
            print()
            await _handle_next(client, json_output=False)
        else:
            code = result.get("code", "?")
            msg = result.get("msg", result.get("message", "Unknown error"))
            print_error(f"API returned code={code}: {msg}")
    except InvalidTOUScheduleOption as e:
        if json_output:
            print_json_output({"error": str(e), "type": "InvalidTOUScheduleOption"})
        else:
            print_error(f"Validation error: {e}")
    except Exception as e:
        if json_output:
            print_json_output({"error": str(e), "type": type(e).__name__})
        else:
            print_error(f"{type(e).__name__}: {e}")
