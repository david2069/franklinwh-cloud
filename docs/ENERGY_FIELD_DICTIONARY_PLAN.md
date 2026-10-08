# Energy Field Dictionary — Implementation Plan

**Ledger:** `FEAT-ENERGY-FIELD-DICT` (`defect_list.md`)
**Status:** Done 2026-10-08 — O1–O4 approved. The 5-minute balance check passed (within 3%), so the 7 solar/grid/battery kW flows are CORROBORATED
**Evidence:** `tests/results/2026-10-08_FEAT-ENERGY-FIELD-DICT_evidence.txt`
**Builds on:** `FEAT-CLI-ENERGY` (f7d7c72)

## Goal

Give every array `franklinwh-cli energy` can output a readable column name, a
description, a unit and an evidence level, kept in one place. Today the 7 main
columns have names, and everything `--all-fields` adds comes out under its raw
API key, with no description anywhere in the repo.

## Evidence levels

| Level | Means |
|---|---|
| **CONFIRMED** | Settled by a controlled observation, or a corpus-wide relationship with no exceptions |
| **CORROBORATED** | Adds up arithmetically with other fields; one site, 12 months |
| **INFERRED** | From the field name only; never seen non-zero, so not checkable here |

---

## The dictionary

New module `franklinwh_cloud/const/energy_fields.py`. It's in `const/` so library
users can import it too. Constant changes need approval (AGENT.md); this plan
asks for that.

```python
EnergyField(api="kwhSolarLoadArray", column="home_from_solar_kwh",
            description="Home consumption supplied by solar", unit="kWh",
            evidence="CORROBORATED")
```

### Energy history (`getFhpElectricData`), kWh per bucket

**Default columns — names unchanged:**

| API key | Column | Description | Evidence |
|---|---|---|---|
| `deviceTimeArray` | `date` | Bucket label: `YYYY-MM-DD`, `YYYY-MM` or `YYYY` | CONFIRMED (live, every period) |
| `kwhSuArray` | `solar_kwh` | Solar produced | CORROBORATED: equals solar→home + solar→battery + solar→grid, 1–2.5% over every month |
| `kwhUtiInArray` | `grid_import_kwh` | Bought from the grid | CORROBORATED: equals grid→home + grid→battery within ~6% (largest gap 4 kWh) |
| `kwhUtiOutArray` | `grid_export_kwh` | Sold to the grid | CORROBORATED: equals solar→grid + battery→grid in 9/12 months |
| `kwhFhpChgArray` | `battery_charge_kwh` | Into the battery | CORROBORATED: equals solar + grid + generator→battery within ~1.5% |
| `kwhFhpDiArray` | `battery_discharge_kwh` | Out of the battery | CORROBORATED: equals battery→home + battery→grid within 2.5% in 10/12 months (Apr 303 vs 263, Jun 341 vs 327) |
| `kwhLoadArray` | `home_kwh` | Home consumption | CORROBORATED: equals sum of the four home-from-X splits, ~2% over |
| `kwhGenArray` | `generator_kwh` | Generator produced | INFERRED: non-zero in 3/3067 responses |

**`--all-fields` columns — new readable names (currently raw API keys):**

| API key | Column | Description | Evidence |
|---|---|---|---|
| `kwhSolarLoadArray` | `home_from_solar_kwh` | Home use supplied by solar | CORROBORATED |
| `kwhGridLoadArray` | `home_from_grid_kwh` | Home use supplied by grid | CORROBORATED |
| `kwhFhpLoadArray` | `home_from_battery_kwh` | Home use supplied by battery | CORROBORATED |
| `kwhGenLoadArray` | `home_from_generator_kwh` | Home use supplied by generator | INFERRED |
| `soChBatArray` | `battery_from_solar_kwh` | Battery charged from solar | CORROBORATED |
| `gridChBatArray` | `battery_from_grid_kwh` | Battery charged from grid | CORROBORATED |
| `genChBatArray` | `battery_from_generator_kwh` | Battery charged from generator | INFERRED |
| `soOutGridArray` | `grid_export_from_solar_kwh` | Export that came from solar | CORROBORATED |
| `batOutGridArray` | `grid_export_from_battery_kwh` | Export that came from battery | CORROBORATED |
| `kwhV2lArray` | `v2l_kwh` | Vehicle-to-load total | INFERRED: never non-zero (0/1444) |
| `kwhV2lToFhpArray` | `v2l_to_battery_kwh` | V2L into the battery | INFERRED: never non-zero |
| `kwhV2lToHomeArray` | `v2l_to_home_kwh` | V2L to the home | INFERRED: never non-zero |
| `proximalSolarWhArray` | `pv_proximal_wh` | Proximal (aPower-connected) solar | INFERRED: never non-zero (0/3067) |
| `mpptWhArray` | `pv_mppt_wh` | MPPT solar input | INFERRED: never non-zero |
| `mpptEngyArryArray` | `pv_mppt_energy` | MPPT energy (unit unknown) | INFERRED: not in corpus; live always null |
| `remoteSolarWhTotalArray` | `pv_remote_wh` | Remote solar | INFERRED: never non-zero |
| `meterkitPvWhArray` | `pv_meterkit_wh` | Solar measured by a meter kit | INFERRED: never non-zero |
| `secondaryPvWhArray` | `pv_secondary_wh` | Secondary solar | INFERRED: never non-zero |
| `mpanPv1Wh` / `mpanPv2Wh` | `pv_mpan1_wh` / `pv_mpan2_wh` | MPAN PV inputs 1 and 2 | INFERRED: never non-zero |
| `apbox20PvWh` | `pv_apbox20_wh` | aPbox 20 A PV input | INFERRED: never non-zero |

The PV columns keep the API's own `Wh` naming, because the actual unit can't be
checked yet: every value seen is 0 or null. They are not converted to kWh.

### 5-minute power (`getFhpPowerByDay`)

The 10 existing columns keep their names. Two **confirmed** fields join the
**default** 5-minute columns. They're currently only reachable with `--all-fields`,
under raw names:

| API key | Column | Description | Evidence |
|---|---|---|---|
| `runStatusArray` | `run_status` + `run_status_label` | Battery state: code, plus its label from `const.RUN_STATUS` (0 Standby / 1 Charging / 2 Discharging) | CONFIRMED: 60 days, 12,962 samples; 1 = charging 95%, 2 = discharging 98%, 0 = no flow 100% |
| `kwhTotalArray` | `battery_stored_kwh` | Energy currently stored, all aPowers | CONFIRMED: equals SoC × 1–4 × 13.6 kWh in 55,479/55,479 samples |

The existing 5-minute columns are relabelled from INFERRED to CORROBORATED only
if the same balance check passes on the 5-minute data during implementation.
Otherwise they stay INFERRED.

V2L 5-minute arrays (`powerV2lFhpArray`, `powerV2lHomeArray`) → `v2l_to_battery_kw`,
`v2l_to_home_kw`, under `--all-fields` (INFERRED).

---

## Output changes — for your approval

| # | Change | Who's affected |
|---|---|---|
| **O1** | CSV/JSON/table: the `--all-fields` extra columns use the readable names above instead of raw API keys. A key the API adds that isn't in the dictionary still appears under its raw name | Anyone parsing `--all-fields` output by raw key. The command shipped today (f7d7c72) and has no known consumers |
| **O2** | 5-minute output gains `run_status`, `run_status_label` and `battery_stored_kwh` by default (column count 11 → 14) | Only scripts that rely on column *positions* in 5-minute CSV |
| **O3** | JSON gains a top-level `"fields"` object: `{column: {api, description, unit, evidence}}` for every column present. Purely additive; no existing key changes | None |
| **O4** | `--describe` flag: prints the dictionary as a table (or JSON with `--json`) and exits **without making an API call**. Handled before login | None (new flag) |

Not proposed: a description row inside the CSV itself, which would break
spreadsheet and pandas imports. Use `--describe` or the JSON `fields` block instead.

## Files

| File | Change |
|---|---|
| `franklinwh_cloud/const/energy_fields.py` | new — `EnergyField` dataclass, `ELECTRIC_FIELDS`, `POWER_FIELDS` |
| `franklinwh_cloud/cli_commands/energy.py` | use the dictionary for columns; `run_status_label`; `fields` block; `--describe` |
| `franklinwh_cloud/cli.py` | `--describe` flag; skip login for it |
| `tests/test_cli_energy.py` | dictionary covers every key seen in the corpus; O1–O4 behaviour |
| `docs/cli-energy.md` | replace the hand-written column tables with the dictionary (generated from it, so they can't drift) |
| `CHANGELOG.md`, `defect_list.md` | entries |

## Verification

Unit tests offline, then one read-only live run each of `--all-fields`
(year), 5-minute CSV and `--describe`.
