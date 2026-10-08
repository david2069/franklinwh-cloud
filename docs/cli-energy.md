# CLI — Energy History

`franklinwh-cli energy` exports energy totals (kWh) for a day, week, month,
year, year-to-date or lifetime. It can also export one day's 5-minute power
samples (kW). Output is a terminal table, JSON or CSV.

## Usage

```bash
franklinwh-cli energy                                        # today, table
franklinwh-cli energy --period week --date 2026-09-10        # snapped to Mon 2026-09-07
franklinwh-cli energy --period month --date 2026-09-01 --format csv -o sep.csv
franklinwh-cli energy --period year --date 2025-01-01 --format json
franklinwh-cli energy --period ytd                           # Jan → this month, plus total
franklinwh-cli energy --period lifetime                      # one row per year
franklinwh-cli energy --period day --date 2026-10-07 --interval 5min --format csv
```

| Option | Default | Meaning |
|---|---|---|
| `--period day\|week\|month\|year\|ytd\|lifetime` | `day` | Period to fetch |
| `--date YYYY-MM-DD` | today | Any date in the period. Snapped to the period start: week → Monday, month → 1st, year → Jan 1. Ignored for `ytd` and `lifetime` |
| `--format table\|json\|csv` | `table` | Output format. The global `--json` flag means `--format json` |
| `--output PATH`, `-o` | stdout | Write to a file |
| `--interval 5min` | — | `--period day` only: 288 five-minute power samples instead of the daily total |
| `--all-fields` | off | Also include every other array the API returns (source split, V2L, per-PV-input …) under its raw API name |

Warnings go to stderr, so piping CSV or JSON stays clean. An empty period, such
as a future year, prints a warning and the header only, and exits 0. A bad
`--date`, or `--interval` used without `--period day`, exits 2.

## Energy columns (kWh)

One row per bucket: the day (day), 7 days (week), each day (month), each month
(year/ytd), each year (lifetime). Table and JSON output add a total.

| Column | API field |
|---|---|
| `date` | `deviceTimeArray` (`YYYY-MM-DD`, `YYYY-MM` or `YYYY`) |
| `solar_kwh` | `kwhSuArray` |
| `grid_import_kwh` | `kwhUtiInArray` |
| `grid_export_kwh` | `kwhUtiOutArray` |
| `battery_charge_kwh` | `kwhFhpChgArray` |
| `battery_discharge_kwh` | `kwhFhpDiArray` |
| `home_kwh` | `kwhLoadArray` |
| `generator_kwh` | `kwhGenArray` |

Months that haven't happened yet come back as `null`. CSV shows them as empty
cells, never `0`.

## 5-minute power columns (`--interval 5min`)

| Column | API field |
|---|---|
| `time` | `deviceTimeArray` |
| `soc_pct` | `socArray` |
| `solar_to_home_kw`, `solar_to_grid_kw`, `solar_to_battery_kw` | `powerSolarHomeArray`, `powerSolarGirdArray`, `powerSolarFhpArray` |
| `grid_to_home_kw`, `grid_to_battery_kw` | `powerGirdHomeArray`, `powerGirdFhpArray` |
| `battery_to_home_kw`, `battery_to_grid_kw` | `powerFhpHomeArray`, `powerFhpGirdArray` |
| `generator_to_home_kw`, `generator_to_battery_kw` | `powerGenHomeArray`, `powerGenFhpArray` |

There is no total row, because adding up power samples doesn't give energy.

> **Evidence (AP-14).** Column meanings and units are **INFERRED** from the API field
> names. They have not been checked against the app's Energy screen; compare one
> day's output with the app to settle it. The period codes and date rules are
> **CONFIRMED**: see `DEF-ENERGY-PERIOD-PARAM` and
> `tests/results/2026-10-08_DEF-ENERGY-PERIOD-PARAM_live_probe.txt`.

## Library equivalents

```python
await client.get_power_details(3, "2026-09-01")   # month; 1=day 2=week 3=month 4=year 5=lifetime
await client.get_power_by_day("2026-10-07")       # 5-minute power
```
