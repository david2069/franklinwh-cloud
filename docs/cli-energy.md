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
franklinwh-cli energy --describe                             # what every column means
```

| Option | Default | Meaning |
|---|---|---|
| `--period day\|week\|month\|year\|ytd\|lifetime` | `day` | Period to fetch |
| `--date YYYY-MM-DD` | today | Any date in the period. Snapped to the period start: week → Monday, month → 1st, year → Jan 1. Ignored for `ytd` and `lifetime` |
| `--format table\|json\|csv` | `table` | Output format. The global `--json` flag means `--format json` |
| `--output PATH`, `-o` | stdout | Write to a file |
| `--interval 5min` | — | `--period day` only: 288 five-minute power samples instead of the daily total |
| `--all-fields` | off | Also include the non-default columns below (source split, V2L, per-PV-input …) |
| `--describe` | — | Print the field dictionary and exit. Needs no login or API call |

Warnings go to stderr, so piping CSV or JSON stays clean. An empty period, such
as a future year, prints a warning and the header only, and exits 0. A bad
`--date`, or `--interval` used without `--period day`, exits 2.

## Field dictionary

Generated from `franklinwh_cloud/const/energy_fields.py`, and also printed by
`franklinwh-cli energy --describe` (no login needed). `tests/test_cli_energy.py`
fails if this section and the module disagree.

| Evidence | Means |
|---|---|
| **CONFIRMED** | Settled by a controlled observation, or a corpus-wide relationship with no exceptions |
| **CORROBORATED** | Adds up arithmetically with other fields (one site: 12 months of kWh, one day of 5-minute power) |
| **INFERRED** | From the field name only. Never seen non-zero, so it can't be checked here |

Evidence: `tests/results/2026-10-08_FEAT-ENERGY-FIELD-DICT_evidence.txt`.

Months that haven't happened yet come back as `null`, which CSV shows as an empty
cell, never `0`. The 5-minute output has no total row, because adding up power
samples doesn't give energy. The `pv_*_wh` columns keep the API's own `Wh` naming
(`Wh?`): every value seen is 0 or null, so the real unit is unknown.

JSON output includes a `fields` object with this information for each column it
contains. An array the API adds that isn't in the dictionary still appears under
its raw API key, with `description: null`.

<!-- BEGIN GENERATED: energy fields -->
### Energy history (kWh per bucket)

| Column | API key | Unit | Default | Evidence | Description |
|---|---|---|---|---|---|
| `date` | `deviceTimeArray` | — | yes | CONFIRMED | Bucket label: YYYY-MM-DD, YYYY-MM or YYYY — live, every period |
| `solar_kwh` | `kwhSuArray` | kWh | yes | CORROBORATED | Solar produced — = solar to home + battery + grid, 1-2.5% over |
| `grid_import_kwh` | `kwhUtiInArray` | kWh | yes | CORROBORATED | Bought from the grid — = grid to home + battery, largest gap 4 kWh |
| `grid_export_kwh` | `kwhUtiOutArray` | kWh | yes | CORROBORATED | Sold to the grid — = solar + battery to grid in 9/12 months |
| `battery_charge_kwh` | `kwhFhpChgArray` | kWh | yes | CORROBORATED | Into the battery — = battery from solar + grid + generator, ~1.5% |
| `battery_discharge_kwh` | `kwhFhpDiArray` | kWh | yes | CORROBORATED | Out of the battery — = battery to home + grid within 2.5% in 10/12 months |
| `home_kwh` | `kwhLoadArray` | kWh | yes | CORROBORATED | Home consumption — = sum of home-from splits, ~2% over |
| `generator_kwh` | `kwhGenArray` | kWh | yes | INFERRED | Generator produced — non-zero in 3/3067 responses |
| `home_from_solar_kwh` | `kwhSolarLoadArray` | kWh | `--all-fields` | CORROBORATED | Home use supplied by solar |
| `home_from_grid_kwh` | `kwhGridLoadArray` | kWh | `--all-fields` | CORROBORATED | Home use supplied by the grid |
| `home_from_battery_kwh` | `kwhFhpLoadArray` | kWh | `--all-fields` | CORROBORATED | Home use supplied by the battery |
| `home_from_generator_kwh` | `kwhGenLoadArray` | kWh | `--all-fields` | INFERRED | Home use supplied by the generator |
| `battery_from_solar_kwh` | `soChBatArray` | kWh | `--all-fields` | CORROBORATED | Battery charged from solar |
| `battery_from_grid_kwh` | `gridChBatArray` | kWh | `--all-fields` | CORROBORATED | Battery charged from the grid |
| `battery_from_generator_kwh` | `genChBatArray` | kWh | `--all-fields` | INFERRED | Battery charged from the generator |
| `grid_export_from_solar_kwh` | `soOutGridArray` | kWh | `--all-fields` | CORROBORATED | Grid export that came from solar |
| `grid_export_from_battery_kwh` | `batOutGridArray` | kWh | `--all-fields` | CORROBORATED | Grid export that came from the battery |
| `v2l_kwh` | `kwhV2lArray` | kWh | `--all-fields` | INFERRED | Vehicle-to-load (V2L) total — never non-zero in the hars/ corpus |
| `v2l_to_battery_kwh` | `kwhV2lToFhpArray` | kWh | `--all-fields` | INFERRED | V2L into the battery — never non-zero in the hars/ corpus |
| `v2l_to_home_kwh` | `kwhV2lToHomeArray` | kWh | `--all-fields` | INFERRED | V2L to the home — never non-zero in the hars/ corpus |
| `pv_proximal_wh` | `proximalSolarWhArray` | Wh? | `--all-fields` | INFERRED | Proximal (aPower-connected) solar — never non-zero in the hars/ corpus |
| `pv_mppt_wh` | `mpptWhArray` | Wh? | `--all-fields` | INFERRED | MPPT solar input — never non-zero in the hars/ corpus |
| `pv_mppt_energy` | `mpptEngyArryArray` | ? | `--all-fields` | INFERRED | MPPT energy — not in the hars/ corpus; always null live |
| `pv_remote_wh` | `remoteSolarWhTotalArray` | Wh? | `--all-fields` | INFERRED | Remote solar — never non-zero in the hars/ corpus |
| `pv_meterkit_wh` | `meterkitPvWhArray` | Wh? | `--all-fields` | INFERRED | Solar measured by a meter kit — never non-zero in the hars/ corpus |
| `pv_secondary_wh` | `secondaryPvWhArray` | Wh? | `--all-fields` | INFERRED | Secondary solar — never non-zero in the hars/ corpus |
| `pv_mpan1_wh` | `mpanPv1Wh` | Wh? | `--all-fields` | INFERRED | MPAN PV input 1 — never non-zero in the hars/ corpus |
| `pv_mpan2_wh` | `mpanPv2Wh` | Wh? | `--all-fields` | INFERRED | MPAN PV input 2 — never non-zero in the hars/ corpus |
| `pv_apbox20_wh` | `apbox20PvWh` | Wh? | `--all-fields` | INFERRED | aPbox 20 A PV input — never non-zero in the hars/ corpus |

### 5-minute power (`--interval 5min`)

| Column | API key | Unit | Default | Evidence | Description |
|---|---|---|---|---|---|
| `time` | `deviceTimeArray` | — | yes | CONFIRMED | Sample time, gateway-local |
| `soc_pct` | `socArray` | % | yes | CONFIRMED | Battery state of charge — kwhTotalArray / socArray is constant per site |
| `run_status` | `runStatusArray` | — | yes | CONFIRMED | Battery state code (see run_status_label) — 0 no flow 100%, 1 charging 95%, 2 discharging 98% of 12,962 samples |
| `run_status_label` | — | — | yes | CONFIRMED | run_status as text, from `const.RUN_STATUS` |
| `battery_stored_kwh` | `kwhTotalArray` | kWh | yes | CONFIRMED | Energy stored across all aPowers — = SoC x 1-4 x 13.6 kWh in 55,479/55,479 samples |
| `solar_to_home_kw` | `powerSolarHomeArray` | kW | yes | CORROBORATED | Solar to home — x 5/60 h sums to the day's kWh totals within 3% |
| `solar_to_grid_kw` | `powerSolarGirdArray` | kW | yes | CORROBORATED | Solar to grid — x 5/60 h sums to the day's kWh totals within 3% |
| `solar_to_battery_kw` | `powerSolarFhpArray` | kW | yes | CORROBORATED | Solar to battery — x 5/60 h sums to the day's kWh totals within 3% |
| `grid_to_home_kw` | `powerGirdHomeArray` | kW | yes | CORROBORATED | Grid to home — x 5/60 h sums to the day's kWh totals within 3% |
| `grid_to_battery_kw` | `powerGirdFhpArray` | kW | yes | CORROBORATED | Grid to battery — x 5/60 h sums to the day's kWh totals within 3% |
| `battery_to_home_kw` | `powerFhpHomeArray` | kW | yes | CORROBORATED | Battery to home — x 5/60 h sums to the day's kWh totals within 3% |
| `battery_to_grid_kw` | `powerFhpGirdArray` | kW | yes | CORROBORATED | Battery to grid — x 5/60 h sums to the day's kWh totals within 3% |
| `generator_to_home_kw` | `powerGenHomeArray` | kW | yes | INFERRED | Generator to home |
| `generator_to_battery_kw` | `powerGenFhpArray` | kW | yes | INFERRED | Generator to battery |
| `v2l_to_battery_kw` | `powerV2lFhpArray` | kW | `--all-fields` | INFERRED | V2L to battery |
| `v2l_to_home_kw` | `powerV2lHomeArray` | kW | `--all-fields` | INFERRED | V2L to home |
<!-- END GENERATED: energy fields -->

## Library equivalents

```python
await client.get_power_details(3, "2026-09-01")   # month; 1=day 2=week 3=month 4=year 5=lifetime
await client.get_power_by_day("2026-10-07")       # 5-minute power
```
