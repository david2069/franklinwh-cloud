"""Energy command — export energy (kWh) and power (kW) history.

Energy totals come from getFhpElectricData via ``get_power_details()``; the
5-minute power series comes from getFhpPowerByDay via ``get_power_by_day()``.

Usage:
    franklinwh-cli energy                                   # today, table
    franklinwh-cli energy --period month --date 2026-09-01 --format csv
    franklinwh-cli energy --period ytd --format json --output ytd.json
    franklinwh-cli energy --period day --interval 5min --format csv

Field meanings below are INFERRED from the API field names and the labels in
docs/API_REFERENCE.md; they have not been checked against the app's display.
See docs/ENERGY_CLI_IMPLEMENTATION_PLAN.md (FEAT-CLI-ENERGY).
"""

import csv
import io
import sys
from datetime import date, timedelta
from itertools import zip_longest

from franklinwh_cloud.cli_output import c, print_error, print_success, print_json_output

PERIODS = ("day", "week", "month", "year", "ytd", "lifetime")
FORMATS = ("table", "json", "csv")

# getFhpElectricData type codes (hars corpus; DEF-ENERGY-PERIOD-PARAM)
_PERIOD_TYPE = {"day": 1, "week": 2, "month": 3, "year": 4, "ytd": 4, "lifetime": 5}

# (output column, API field) — kWh per bucket
ENERGY_COLUMNS = [
    ("solar_kwh", "kwhSuArray"),
    ("grid_import_kwh", "kwhUtiInArray"),
    ("grid_export_kwh", "kwhUtiOutArray"),
    ("battery_charge_kwh", "kwhFhpChgArray"),
    ("battery_discharge_kwh", "kwhFhpDiArray"),
    ("home_kwh", "kwhLoadArray"),
    ("generator_kwh", "kwhGenArray"),
]

# (output column, API field) — 5-minute samples. "Gird" is the API's spelling.
POWER_COLUMNS = [
    ("soc_pct", "socArray"),
    ("solar_to_home_kw", "powerSolarHomeArray"),
    ("solar_to_grid_kw", "powerSolarGirdArray"),
    ("solar_to_battery_kw", "powerSolarFhpArray"),
    ("grid_to_home_kw", "powerGirdHomeArray"),
    ("grid_to_battery_kw", "powerGirdFhpArray"),
    ("battery_to_home_kw", "powerFhpHomeArray"),
    ("battery_to_grid_kw", "powerFhpGirdArray"),
    ("generator_to_home_kw", "powerGenHomeArray"),
    ("generator_to_battery_kw", "powerGenFhpArray"),
]

_TIME_FIELD = "deviceTimeArray"


def resolve_period(period: str, on: date, today: date) -> tuple[int, date]:
    """Return (getFhpElectricData type, date to query) for a period.

    The date is snapped to the period start. Only the week snap is required
    (the server returns nothing for a non-Monday); month and year are snapped
    so the reported query date matches what the server returns.
    """
    if period == "day":
        start = on
    elif period == "week":
        start = on - timedelta(days=on.weekday())
    elif period == "month":
        start = on.replace(day=1)
    elif period == "year":
        start = on.replace(month=1, day=1)
    elif period == "ytd":
        start = today.replace(month=1, day=1)
    elif period == "lifetime":
        start = today
    else:
        raise ValueError(f"unknown period: {period}")
    return _PERIOD_TYPE[period], start


def build_rows(result: dict, columns: list[tuple[str, str]], *,
               time_column: str = "date", all_fields: bool = False) -> tuple[list[str], list[dict]]:
    """Turn the API's parallel arrays into one dict per bucket.

    Missing or ``null`` values stay ``None`` — "no data" is not zero.
    With ``all_fields``, every other array in the response is appended under
    its raw API name.
    """
    result = result or {}
    selected = list(columns)
    if all_fields:
        known = {api for _, api in columns} | {_TIME_FIELD}
        selected += [(k, k) for k, v in result.items()
                     if isinstance(v, list) and k not in known]
    names = [time_column] + [name for name, _ in selected]
    arrays = [result.get(_TIME_FIELD) or []] + [result.get(api) or [] for _, api in selected]
    rows = [dict(zip(names, values)) for values in zip_longest(*arrays)]
    return names, rows


def trim_ytd(rows: list[dict], today: date, time_column: str = "date") -> list[dict]:
    """Keep year rows up to and including the current month ('YYYY-MM' labels)."""
    cutoff = f"{today.year:04d}-{today.month:02d}"
    return [r for r in rows if str(r.get(time_column) or "") <= cutoff]


def totals(rows: list[dict], names: list[str]) -> dict:
    """Sum each numeric column, ignoring None. A column with no values totals None."""
    out = {}
    for name in names[1:]:
        values = [r[name] for r in rows if isinstance(r.get(name), (int, float))]
        out[name] = round(sum(values), 3) if values else None
    return out


def render_csv(names: list[str], rows: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(names)
    for r in rows:
        writer.writerow(["" if r.get(n) is None else r.get(n) for n in names])
    return buf.getvalue()


def render_table(names: list[str], rows: list[dict], total: dict | None, title: str) -> str:
    def fmt(v):
        if v is None:
            return "—"
        return f"{v:.2f}" if isinstance(v, float) else str(v)

    headers = [names[0]] + [n.removesuffix("_kwh").removesuffix("_kw") for n in names[1:]]
    body = [[fmt(r.get(n)) for n in names] for r in rows]
    if total is not None:
        body.append(["total"] + [fmt(total.get(n)) for n in names[1:]])
    widths = [max(len(h), *(len(line[i]) for line in body)) if body else len(h)
              for i, h in enumerate(headers)]

    def line(cells):
        return "  ".join(cells[0].ljust(widths[0]) if i == 0 else cells[i].rjust(widths[i])
                         for i in range(len(cells)))

    out = [c("bold", title), c("bold", line(headers)), c("dim", line(["─" * w for w in widths]))]
    for i, cells in enumerate(body):
        text = line(cells)
        out.append(c("bold", text) if total is not None and i == len(body) - 1 else text)
    return "\n".join(out)


def _warn(msg: str):
    # stderr, so stdout stays clean CSV/JSON
    print(f"{c('yellow', '⚠')} {msg}", file=sys.stderr)


async def run(client, args) -> int:
    """Execute the energy command. Returns a process exit code."""
    period = args.period
    interval = getattr(args, "interval", None)
    fmt = "json" if getattr(args, "json", False) else args.format
    today = date.today()

    try:
        on = date.fromisoformat(args.date) if args.date else today
    except ValueError:
        print_error(f"--date must be YYYY-MM-DD, got {args.date!r}")
        return 2

    if interval and period != "day":
        print_error("--interval 5min only works with --period day")
        return 2

    if interval:
        result = await client.get_power_by_day(on.isoformat())
        names, rows = build_rows(result, POWER_COLUMNS, time_column="time",
                                 all_fields=args.all_fields)
        total, unit = None, "kW"
        data_type, query_date = None, on
    else:
        data_type, query_date = resolve_period(period, on, today)
        result = await client.get_power_details(data_type, query_date.isoformat())
        names, rows = build_rows(result, ENERGY_COLUMNS, all_fields=args.all_fields)
        if period == "ytd":
            rows = trim_ytd(rows, today)
        total, unit = totals(rows, names), "kWh"

    label = f"{period} {query_date.isoformat()}" if period not in ("ytd", "lifetime") else period
    if period == "ytd":
        label = f"ytd {today.year}"
    if not rows:
        _warn(f"No data returned for {label}")

    if fmt == "csv":
        text = render_csv(names, rows)
    elif fmt == "json":
        payload = {
            "period": period,
            "interval": interval or None,
            "type": data_type,
            "requested_date": on.isoformat(),
            "query_date": query_date.isoformat(),
            "unit": unit,
            "columns": names,
            "rows": rows,
        }
        if total is not None:
            payload["totals"] = total
        if args.output:
            import json
            text = json.dumps(payload, indent=2, default=str) + "\n"
        else:
            print_json_output(payload)
            return 0
    else:
        title = f"Energy — {label}" + (" (5-minute power, kW)" if interval else " (kWh)")
        text = render_table(names, rows, total, title) + "\n"

    if args.output:
        with open(args.output, "w", newline="") as fh:
            fh.write(text)
        print_success(f"Wrote {len(rows)} rows to {args.output}")
    else:
        sys.stdout.write(text)
    return 0
