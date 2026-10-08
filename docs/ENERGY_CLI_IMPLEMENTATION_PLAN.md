# Energy CLI — Implementation Plan

**Ledger:** `DEF-ENERGY-PERIOD-PARAM`, `FEAT-CLI-ENERGY` (`defect_list.md`)
**Status:** Approved 2026-10-08 (incl. 5-minute power)
**Evidence:** `tests/results/2026-10-08_DEF-ENERGY-PERIOD-PARAM_live_probe.txt`, `hars/` corpus

Two items, done in this order and committed separately (AP-1).

---

## 1. `DEF-ENERGY-PERIOD-PARAM` — send the date under the right key

### What the evidence shows

`GET api-energy/electric/getFhpElectricData` reads the date from a different
query key depending on `type`:

| type | Period | Key the server honours | Date the server accepts | Evidence |
|---|---|---|---|---|
| 1 | Day | `dayTime` | that day | live probe; hars ×3011 |
| 2 | Week | `startDate` | **Monday only** — a Thursday returned empty | live probe; hars ×10 |
| 3 | Month | `startDate` | any day in the month (server snaps it to the 1st) | live probe; hars ×24 |
| 4 | Year | `startDate` | any day in the year (server snaps it to Jan 1) | live probe; hars ×15 |
| 5 | Lifetime | either | ignored | live probe; hars ×7 |

`get_power_details()` (`mixins/stats.py:379`) and `get_electric_data()`
(`mixins/account.py:430`) both send `dayTime` for every type, so **week, month
and year return empty arrays**. Nothing fails loudly, so nobody noticed.

### Change

- In both methods, send `dayTime` for type 1 and `startDate` for types 2–5.
  **Signatures don't change** — not a breaking change.
- Week dates are **not** snapped to Monday in the library. The server behaviour is
  documented in the docstring and handled in the CLI (§2). A library that rewrote
  the date the caller asked for would be guessing.
- Fix the `get_electric_data()` docstring (it says `1/2/3 = daily/monthly/yearly`; the
  corpus shows 1–5 = day/week/month/year/lifetime) and the week row in
  `docs/API_REFERENCE.md` ("end of week" → "the Monday it starts").

### Tests

- respx unit tests asserting the query key per type, for both methods.
  The existing `test_get_power_details_strict_url` (type 1 + `dayTime`) stays as is.

> ⚠️ Changes what the library sends to the API — **needs your sign-off before commit**
> (CLAUDE.md rule 6).

---

## 2. `FEAT-CLI-ENERGY` — new `energy` subcommand

### Usage

```
franklinwh-cli energy [--period day|week|month|year|ytd|lifetime]
                      [--date YYYY-MM-DD]
                      [--format table|json|csv]
                      [--output FILE]
                      [--all-fields]
                      [--interval 5min]      # --period day only
```

| Option | Default | Behaviour |
|---|---|---|
| `--period` | `day` | Which period to fetch |
| `--date` | today | Any date inside the period; the CLI snaps it to the period start (week → Monday, month → 1st, year → Jan 1) |
| `--format` | `table` | `table` (terminal), `json`, `csv`. The global `--json` means `--format json` |
| `--output` | stdout | Write to a file instead |
| `--interval 5min` | off | `--period day` only: 288 rows of power (kW) from `get_power_by_day()` instead of the daily kWh total — see below |
| `--all-fields` | off | Include every array the API returns (generator, V2L, source split, per-PV-input …) under its raw API name |

`ytd` = the type 4 (year) call for the current year, keeping only the months up to and
including this one. The current month is partial.

### Rows and columns

One row per bucket the API returns: one day (day), 7 days (week), each day (month),
each month (year/ytd), each year (lifetime). Plus a **total** row in table and JSON output.

| Column | API field | Meaning |
|---|---|---|
| `date` | `deviceTimeArray` | Bucket label as the API returns it (`YYYY-MM-DD`, `YYYY-MM` or `YYYY`) |
| `solar_kwh` | `kwhSuArray` | Solar produced |
| `grid_import_kwh` | `kwhUtiInArray` | Bought from the grid |
| `grid_export_kwh` | `kwhUtiOutArray` | Sold to the grid |
| `battery_charge_kwh` | `kwhFhpChgArray` | Into the battery |
| `battery_discharge_kwh` | `kwhFhpDiArray` | Out of the battery |
| `home_kwh` | `kwhLoadArray` | Home consumption |
| `generator_kwh` | `kwhGenArray` | Generator |

Field meanings are **INFERRED** from the names and from `docs/API_REFERENCE.md`'s
existing labels. They have not been checked against the app's display. To settle it,
compare one day's CSV with the app's Energy screen for the same day. The `--help`
text and docs will say so.

`null` values (future months in a year) become empty CSV cells and `null` in JSON,
never `0`, so "no data yet" stays distinct from "zero".

### 5-minute power (`--interval 5min`)

Source: `GET api-energy/power/getFhpPowerByDay?dayTime=…` (hars ×454; each sampled
response has 288 points). Columns use the API's own flow names, made readable:

| Column | API field |
|---|---|
| `time` | `deviceTimeArray` |
| `soc_pct` | `socArray` |
| `solar_to_home_kw` / `solar_to_grid_kw` / `solar_to_battery_kw` | `powerSolarHomeArray` / `powerSolarGirdArray` / `powerSolarFhpArray` |
| `grid_to_home_kw` / `grid_to_battery_kw` | `powerGirdHomeArray` / `powerGirdFhpArray` |
| `battery_to_home_kw` / `battery_to_grid_kw` | `powerFhpHomeArray` / `powerFhpGirdArray` |
| `generator_to_home_kw` / `generator_to_battery_kw` | `powerGenHomeArray` / `powerGenFhpArray` |

`--all-fields` adds `runStatusArray`, `kwhTotalArray` and the V2L arrays under their raw
names. Units (kW, %) are **INFERRED** from the field names; not checked against the app.
No total row: summing power isn't energy.

### Example

```bash
franklinwh-cli energy --period month --date 2026-09-01 --format csv --output sep.csv
franklinwh-cli energy --period ytd --format json
franklinwh-cli energy --period week --date 2026-09-10     # snapped to Mon 2026-09-07
```

### Files

| File | Change |
|---|---|
| `franklinwh_cloud/cli_commands/energy.py` | new — period resolution, fetch, table/json/csv rendering |
| `franklinwh_cloud/cli.py` | add `energy` subparser + dispatch case |
| `tests/test_cli_energy.py` | new — date snapping, ytd trimming, CSV/JSON shape, null handling (offline, respx) |
| `docs/cli-energy.md` | new — usage + column reference |
| `AGENT.md`, `CHANGELOG.md` | add the command |

No live tests are added. Verification is one manual read-only run per period.

---

## Out of scope (queue if wanted)

- Custom ranges (`--from … --to …`) spanning several periods
- `raw` rejecting too many positional arguments
- `fetch GET` not injecting `gatewayId` into query params (it returned 400 during the probe)
