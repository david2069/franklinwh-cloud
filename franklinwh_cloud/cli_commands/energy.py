"""Energy command — export energy (kWh) and power (kW) history.

Energy totals come from getFhpElectricData via ``get_power_details()``; the
5-minute power series comes from getFhpPowerByDay via ``get_power_by_day()``.

Usage:
    franklinwh-cli energy                                   # today, table
    franklinwh-cli energy --period month --date 2026-09-01 --format csv
    franklinwh-cli energy --period ytd --format json --output ytd.json
    franklinwh-cli energy --period day --interval 5min --format csv
    franklinwh-cli energy --describe                        # field dictionary, no API call

Column names, descriptions, units and evidence levels come from
franklinwh_cloud.const.energy_fields (FEAT-ENERGY-FIELD-DICT).
See docs/ENERGY_CLI_IMPLEMENTATION_PLAN.md (FEAT-CLI-ENERGY).
"""

import csv
import io
import sys
from datetime import date, timedelta
from itertools import zip_longest

from franklinwh_cloud.cli_output import c, print_error, print_success, print_json_output
from franklinwh_cloud.const.energy_fields import (
    ELECTRIC_FIELDS, POWER_FIELDS, RUN_STATUS_LABEL_COLUMN, EnergyField,
)
from franklinwh_cloud.const.modes import RUN_STATUS

PERIODS = ("day", "week", "month", "year", "ytd", "lifetime")
FORMATS = ("table", "json", "csv")

# getFhpElectricData type codes (hars corpus; DEF-ENERGY-PERIOD-PARAM)
_PERIOD_TYPE = {"day": 1, "week": 2, "month": 3, "year": 4, "ytd": 4, "lifetime": 5}


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


def build_rows(result: dict, fields: tuple[EnergyField, ...], *,
               all_fields: bool = False) -> tuple[list[str], list[dict], dict]:
    """Turn the API's parallel arrays into one dict per bucket.

    ``fields[0]`` is the time column. Missing or ``null`` values stay ``None``
    — "no data" is not zero. With ``all_fields``, non-default dictionary fields
    are added, then any array the dictionary doesn't know, under its raw API key.

    Returns (column names, rows, {column: EnergyField or None}).
    """
    result = result or {}
    selected = [f for f in fields if f.default or all_fields]
    if all_fields:
        known = {f.api for f in fields}
        selected += [EnergyField(k, k, "", "", "") for k, v in result.items()
                     if isinstance(v, list) and k not in known]
    arrays = [result.get(f.api) or [] for f in selected]
    names = [f.column for f in selected]
    rows = [dict(zip(names, values)) for values in zip_longest(*arrays)]
    meta = {f.column: (f if f.evidence else None) for f in selected}

    if "run_status" in names:
        i = names.index("run_status") + 1
        names.insert(i, RUN_STATUS_LABEL_COLUMN)
        for r in rows:
            code = r.get("run_status")
            r[RUN_STATUS_LABEL_COLUMN] = None if code is None else RUN_STATUS.get(code, f"Unknown {code}")
        meta[RUN_STATUS_LABEL_COLUMN] = None
    return names, rows, meta


def field_info(names: list[str], meta: dict) -> dict:
    """The JSON ``fields`` block: column → {api, description, unit, evidence, note}."""
    out = {}
    for n in names:
        f = meta.get(n)
        if n == RUN_STATUS_LABEL_COLUMN:
            out[n] = {"api": None, "description": "run_status as text, from const.RUN_STATUS",
                      "unit": "", "evidence": "CONFIRMED", "note": ""}
        elif f is None:
            out[n] = {"api": n, "description": None, "unit": None, "evidence": None,
                      "note": "not in the field dictionary"}
        else:
            out[n] = {"api": f.api, "description": f.description, "unit": f.unit,
                      "evidence": f.evidence, "note": f.note}
    return out


def describe_markdown() -> str:
    """The field dictionary as Markdown tables, embedded in docs/cli-energy.md."""
    out = []
    for title, fs in (("Energy history (kWh per bucket)", ELECTRIC_FIELDS),
                      ("5-minute power (`--interval 5min`)", POWER_FIELDS)):
        out += [f"### {title}", "",
                "| Column | API key | Unit | Default | Evidence | Description |",
                "|---|---|---|---|---|---|"]
        for f in fs:
            desc = f.description + (f" — {f.note}" if f.note else "")
            out.append(f"| `{f.column}` | `{f.api}` | {f.unit or '—'} | "
                       f"{'yes' if f.default else '`--all-fields`'} | {f.evidence} | {desc} |")
            if f.column == "run_status":
                out.append(f"| `{RUN_STATUS_LABEL_COLUMN}` | — | — | yes | CONFIRMED | "
                           "run_status as text, from `const.RUN_STATUS` |")
        out.append("")
    return "\n".join(out)


def describe(json_output: bool = False) -> int:
    """Print the field dictionary. Makes no API call."""
    groups = {"energy": ELECTRIC_FIELDS, "power_5min": POWER_FIELDS}
    if json_output:
        print_json_output({g: [{"column": f.column, "api": f.api, "description": f.description,
                                "unit": f.unit, "evidence": f.evidence, "default": f.default,
                                "note": f.note} for f in fs] for g, fs in groups.items()})
        return 0
    titles = {"energy": "Energy history (kWh per bucket)", "power_5min": "5-minute power (--interval 5min)"}
    for g, fs in groups.items():
        rows = [(f.column + ("" if f.default else " +"), f.api, f.unit, f.evidence, f.description)
                for f in fs]
        widths = [max(len(r[i]) for r in rows) for i in range(4)]
        print(c("bold", titles[g]))
        for r in rows:
            print("  " + "  ".join(r[i].ljust(widths[i]) for i in range(4)) + "  " + r[4])
        print()
    print(c("dim", "+ = only with --all-fields.  Wh? = unit named by the API, unverified."))
    return 0


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
    if getattr(args, "describe", False):
        return describe(json_output=fmt == "json")
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
        names, rows, meta = build_rows(result, POWER_FIELDS, all_fields=args.all_fields)
        total, unit = None, "kW"
        data_type, query_date = None, on
    else:
        data_type, query_date = resolve_period(period, on, today)
        result = await client.get_power_details(data_type, query_date.isoformat())
        names, rows, meta = build_rows(result, ELECTRIC_FIELDS, all_fields=args.all_fields)
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
            "fields": field_info(names, meta),
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
