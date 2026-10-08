"""Field dictionary for the energy history endpoints (FEAT-ENERGY-FIELD-DICT).

Maps each array returned by ``getFhpElectricData`` (``get_power_details``) and
``getFhpPowerByDay`` (``get_power_by_day``) to a readable column name, a
description, a unit and an evidence level.

Evidence levels (AP-14):
    CONFIRMED     settled by a controlled observation, or a corpus-wide
                  relationship with no exceptions
    CORROBORATED  adds up arithmetically with other fields (one site: 12 months
                  of kWh, one day of 5-minute power)
    INFERRED      from the field name only; never seen non-zero, so not checkable

Evidence: tests/results/2026-10-08_FEAT-ENERGY-FIELD-DICT_evidence.txt
Plan:     docs/ENERGY_FIELD_DICTIONARY_PLAN.md
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EnergyField:
    api: str            # key in the API response
    column: str         # output column name
    description: str
    unit: str
    evidence: str       # CONFIRMED | CORROBORATED | INFERRED
    default: bool = False   # shown without --all-fields
    note: str = ""


_C, _K, _I = "CONFIRMED", "CORROBORATED", "INFERRED"
_NEVER_NONZERO = "never non-zero in the hars/ corpus"
_INTEGRATES = "x 5/60 h sums to the day's kWh totals within 3%"

# ── getFhpElectricData — energy per bucket ───────────────────────────
ELECTRIC_FIELDS: tuple[EnergyField, ...] = (
    EnergyField("deviceTimeArray", "date", "Bucket label: YYYY-MM-DD, YYYY-MM or YYYY", "", _C, True,
                "live, every period"),
    EnergyField("kwhSuArray", "solar_kwh", "Solar produced", "kWh", _K, True,
                "= solar to home + battery + grid, 1-2.5% over"),
    EnergyField("kwhUtiInArray", "grid_import_kwh", "Bought from the grid", "kWh", _K, True,
                "= grid to home + battery, largest gap 4 kWh"),
    EnergyField("kwhUtiOutArray", "grid_export_kwh", "Sold to the grid", "kWh", _K, True,
                "= solar + battery to grid in 9/12 months"),
    EnergyField("kwhFhpChgArray", "battery_charge_kwh", "Into the battery", "kWh", _K, True,
                "= battery from solar + grid + generator, ~1.5%"),
    EnergyField("kwhFhpDiArray", "battery_discharge_kwh", "Out of the battery", "kWh", _K, True,
                "= battery to home + grid within 2.5% in 10/12 months"),
    EnergyField("kwhLoadArray", "home_kwh", "Home consumption", "kWh", _K, True,
                "= sum of home-from splits, ~2% over"),
    EnergyField("kwhGenArray", "generator_kwh", "Generator produced", "kWh", _I, True,
                "non-zero in 3/3067 responses"),
    EnergyField("kwhSolarLoadArray", "home_from_solar_kwh", "Home use supplied by solar", "kWh", _K),
    EnergyField("kwhGridLoadArray", "home_from_grid_kwh", "Home use supplied by the grid", "kWh", _K),
    EnergyField("kwhFhpLoadArray", "home_from_battery_kwh", "Home use supplied by the battery", "kWh", _K),
    EnergyField("kwhGenLoadArray", "home_from_generator_kwh", "Home use supplied by the generator", "kWh", _I),
    EnergyField("soChBatArray", "battery_from_solar_kwh", "Battery charged from solar", "kWh", _K),
    EnergyField("gridChBatArray", "battery_from_grid_kwh", "Battery charged from the grid", "kWh", _K),
    EnergyField("genChBatArray", "battery_from_generator_kwh", "Battery charged from the generator", "kWh", _I),
    EnergyField("soOutGridArray", "grid_export_from_solar_kwh", "Grid export that came from solar", "kWh", _K),
    EnergyField("batOutGridArray", "grid_export_from_battery_kwh", "Grid export that came from the battery", "kWh", _K),
    EnergyField("kwhV2lArray", "v2l_kwh", "Vehicle-to-load (V2L) total", "kWh", _I, note=_NEVER_NONZERO),
    EnergyField("kwhV2lToFhpArray", "v2l_to_battery_kwh", "V2L into the battery", "kWh", _I, note=_NEVER_NONZERO),
    EnergyField("kwhV2lToHomeArray", "v2l_to_home_kwh", "V2L to the home", "kWh", _I, note=_NEVER_NONZERO),
    EnergyField("proximalSolarWhArray", "pv_proximal_wh", "Proximal (aPower-connected) solar", "Wh?", _I,
                note=_NEVER_NONZERO),
    EnergyField("mpptWhArray", "pv_mppt_wh", "MPPT solar input", "Wh?", _I, note=_NEVER_NONZERO),
    EnergyField("mpptEngyArryArray", "pv_mppt_energy", "MPPT energy", "?", _I,
                note="not in the hars/ corpus; always null live"),
    EnergyField("remoteSolarWhTotalArray", "pv_remote_wh", "Remote solar", "Wh?", _I, note=_NEVER_NONZERO),
    EnergyField("meterkitPvWhArray", "pv_meterkit_wh", "Solar measured by a meter kit", "Wh?", _I,
                note=_NEVER_NONZERO),
    EnergyField("secondaryPvWhArray", "pv_secondary_wh", "Secondary solar", "Wh?", _I, note=_NEVER_NONZERO),
    EnergyField("mpanPv1Wh", "pv_mpan1_wh", "MPAN PV input 1", "Wh?", _I, note=_NEVER_NONZERO),
    EnergyField("mpanPv2Wh", "pv_mpan2_wh", "MPAN PV input 2", "Wh?", _I, note=_NEVER_NONZERO),
    EnergyField("apbox20PvWh", "pv_apbox20_wh", "aPbox 20 A PV input", "Wh?", _I, note=_NEVER_NONZERO),
)

# ── getFhpPowerByDay — 5-minute samples. "Gird" is the API's spelling. ──
POWER_FIELDS: tuple[EnergyField, ...] = (
    EnergyField("deviceTimeArray", "time", "Sample time, gateway-local", "", _C, True),
    EnergyField("socArray", "soc_pct", "Battery state of charge", "%", _C, True,
                "kwhTotalArray / socArray is constant per site"),
    EnergyField("runStatusArray", "run_status", "Battery state code (see run_status_label)", "", _C, True,
                "0 no flow 100%, 1 charging 95%, 2 discharging 98% of 12,962 samples"),
    EnergyField("kwhTotalArray", "battery_stored_kwh", "Energy stored across all aPowers", "kWh", _C, True,
                "= SoC x 1-4 x 13.6 kWh in 55,479/55,479 samples"),
    EnergyField("powerSolarHomeArray", "solar_to_home_kw", "Solar to home", "kW", _K, True, _INTEGRATES),
    EnergyField("powerSolarGirdArray", "solar_to_grid_kw", "Solar to grid", "kW", _K, True, _INTEGRATES),
    EnergyField("powerSolarFhpArray", "solar_to_battery_kw", "Solar to battery", "kW", _K, True, _INTEGRATES),
    EnergyField("powerGirdHomeArray", "grid_to_home_kw", "Grid to home", "kW", _K, True, _INTEGRATES),
    EnergyField("powerGirdFhpArray", "grid_to_battery_kw", "Grid to battery", "kW", _K, True, _INTEGRATES),
    EnergyField("powerFhpHomeArray", "battery_to_home_kw", "Battery to home", "kW", _K, True, _INTEGRATES),
    EnergyField("powerFhpGirdArray", "battery_to_grid_kw", "Battery to grid", "kW", _K, True, _INTEGRATES),
    EnergyField("powerGenHomeArray", "generator_to_home_kw", "Generator to home", "kW", _I, True),
    EnergyField("powerGenFhpArray", "generator_to_battery_kw", "Generator to battery", "kW", _I, True),
    EnergyField("powerV2lFhpArray", "v2l_to_battery_kw", "V2L to battery", "kW", _I),
    EnergyField("powerV2lHomeArray", "v2l_to_home_kw", "V2L to home", "kW", _I),
)

# Added next to run_status in the output; not an API field.
RUN_STATUS_LABEL_COLUMN = "run_status_label"
