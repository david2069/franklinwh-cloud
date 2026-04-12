# CLI Reference: `franklinwh-cli schema`

> **Purpose:** The `schema` command is the authoritative reference for the
> `franklinwh_cloud` data model. It prints every field in `stats.current`
> and `stats.totals` alongside the raw API JSON key, the MQTT cmdType source,
> units, and (optionally) the live value from your gateway.

---

## Why this exists

The FranklinWH Cloud API uses terse, undocumented field names (`p_sun`, `p_fhp`,
`p_uti`, `gridChBat`, etc.) that bear no obvious relationship to their physical
meaning. The library normalises these to readable Python attribute names on the
`Current` and `Totals` dataclasses.

Without a reference, there is no way to know that:
- `battery_use` ← raw field `p_fhp` (FHPower — pack power, kW)
- `grid_use` ← raw field `p_uti` (utility power, kW)
- `grid_line_voltage` ← raw field `gridLineVol` **÷ 10** (raw is tenths of a volt)
- `switch_1_load` comes from cmdType **311** (not 203)

`franklinwh-cli schema` answers all of these questions in one command.

---

## Usage

```bash
franklinwh-cli schema                           # full schema — no login required
franklinwh-cli schema --live                    # + live values from get_stats()
franklinwh-cli schema --filter 211              # only cmdType 211 electrical fields
franklinwh-cli schema --filter power            # only power flow fields
franklinwh-cli schema --filter relay            # only relay fields
franklinwh-cli schema --json                    # machine-readable JSON
franklinwh-cli schema --live --json             # JSON + live values
franklinwh-cli schema --live --filter power     # filtered JSON
```

---

## Output columns

| Column | Meaning |
|--------|---------|
| **Python Attribute** | The field name on `stats.current` or `stats.totals` |
| **Raw API Key** | The JSON key in the FranklinWH API response |
| **Source** | Which MQTT command provides this field |
| **Units** | Physical unit (kW, kWh, V, A, Hz, %, °C) |
| **Live Value** | (with `--live` only) current reading from the gateway |

### Source codes

| Source | Description |
|--------|-------------|
| `203/runtimeData` | `getDeviceCompositeInfo` (cmdType 203) → `result.runtimeData` — main telemetry call |
| `203/result` | `getDeviceCompositeInfo` → `result` (top-level, not nested in runtimeData) |
| `211/result` | `get_power_info` (cmdType 211) — **opt-in**, only with `get_stats(include_electrical=True)` |
| `311/sw_data` | `getSmartCircuitsInfo` (cmdType 311) — requires Smart Circuit accessory |
| `311/runtimeData` | `getSmartCircuitsInfo` → runtimeData inline |
| `get_tou_info` | Derived from TOU schedule lookup — not from the main MQTT call |
| `derived` | Computed by the library (no direct API field) |

### Relay encoding

All relay fields use firmware convention: **`1 = OPEN (disconnected)`, `0 = CLOSED (connected)`**
This is the inverse of what you might expect — the firmware reports relay coil state, not contact state.

---

## Examples

### Basic schema (no login)

```bash
$ franklinwh-cli schema
```

```
============================================================
  API Field Schema — Current & Totals
============================================================

📊 stats.current  (getDeviceCompositeInfo / cmdType 203)
Python Attribute                Raw API Key             Source                Units
-----------------------------------------------------------------------------------------

  ── Power Flow
  solar_production                p_sun                   203/runtimeData       kW
  generator_production            p_gen                   203/runtimeData       kW
  battery_use                     p_fhp                   203/runtimeData       kW
  grid_use                        p_uti                   203/runtimeData       kW
  home_load                       p_load                  203/runtimeData       kW
  battery_soc                     soc                     203/runtimeData       %
  switch_1_load                   pro_load_pwr[0]         311/sw_data           kW
  switch_2_load                   pro_load_pwr[1]         311/sw_data           kW
  v2l_use                         CarSWPower              311/sw_data           kW

  ── Grid State
  grid_connection_state           derived                 derived               enum

  ── Mode
  work_mode                       currentWorkMode         203/result            int
  work_mode_desc                  derived                 derived               str
  device_status                   deviceStatus            203/result            int
  tou_mode                        mode                    203/runtimeData       int
  tou_mode_desc                   name                    203/runtimeData       str
  run_status                      run_status              203/runtimeData       int
  run_status_desc                  derived                 derived               str

  ── Battery Packs
  apower_serial_numbers           fhpSn                   203/runtimeData       list
  apower_soc                      fhpSoc                  203/runtimeData       list
  apower_power                    fhpPower                203/runtimeData       list
  apower_bms_mode                 bms_work                203/runtimeData       list

  ── Environment
  agate_ambient_temparture        t_amb                   203/runtimeData       °C

  ── Relays
  grid_relay1                     main_sw[0]              203/runtimeData       relay
  generator_relay                 main_sw[1]              203/runtimeData       relay
  solar_relay1                    main_sw[2]              203/runtimeData       relay

  ── Connectivity
  mobile_signal                   signal                  203/runtimeData       dBm
  wifi_signal                     wifiSignal              203/runtimeData       %
  network_connection              connType                203/runtimeData       int

  ── V2L
  v2l_enabled                     v2lModeEnable           203/runtimeData       bool
  v2l_status                      v2lRunState             203/runtimeData       int

  ── Generator
  generator_enabled               genEn                   203/runtimeData       bool
  generator_status                genStat                 203/runtimeData       int

  ── Power Flow
  grid_charging_battery           gridChBat               203/runtimeData       kW
  solar_export_to_grid            soOutGrid               203/runtimeData       kW
  solar_charging_battery          soChBat                 203/runtimeData       kW
  battery_export_to_grid          batOutGrid              203/runtimeData       kW

  ── APbox/MPPT
  apbox_remote_solar              apbox20Pv               203/runtimeData       kW
  remote_solar_enabled            remoteSolarEn           203/runtimeData       bool
  mppt_status                     mpptSta                 203/runtimeData       int
  mppt_all_power                  mpptAllPower            203/runtimeData       kW
  mppt_active_power               mpptActPower            203/runtimeData       kW
  mpan_pv1_power                  mPanPv1Power            203/runtimeData       kW
  mpan_pv2_power                  mPanPv2Power            203/runtimeData       kW
  remote_solar_pv1                remoteSolar1Power       203/runtimeData       kW
  remote_solar_pv2                remoteSolar2Power       203/runtimeData       kW

  ── Alarms
  alarms_count                    currentAlarmVOList      203/result            count

  ── Extended Relays (211)
  grid_relay2                     gridRelayStat           211/result            relay
  black_start_relay               bFpVApboxRelay          211/result            relay
  pv_relay2                       pvRelay2                211/result            relay
  bfpv_apbox_relay                BFPVApboxRelay          211/result            relay

  ── Electrical (211)
  grid_voltage1                   gridVol1                211/result            V
  grid_voltage2                   gridVol2                211/result            V
  grid_current1                   gridCur1                211/result            A
  grid_current2                   gridCur2                211/result            A
  grid_frequency                  gridFreq                211/result            Hz
  grid_set_frequency              gridSetFreq             211/result            Hz
  grid_line_voltage               gridLineVol÷10          211/result            V
  generator_voltage               oilVol                  211/result            V

  ── TOU Window
  active_tou_name                 derived                 get_tou_info          str
  active_tou_dispatch             derived                 get_tou_info          str
  active_tou_start                derived                 get_tou_info          HH:MM
  active_tou_end                  derived                 get_tou_info          HH:MM
  active_tou_remaining            derived                 get_tou_info          str

  ── Smart Circuits
  switch_1_state                  pro_load[0]             311/runtimeData       0/1
  switch_2_state                  pro_load[1]             311/runtimeData       0/1
  switch_3_state                  pro_load[2]             311/runtimeData       0/1


📈 stats.totals  (getDeviceCompositeInfo / cmdType 203)
Python Attribute                Raw API Key             Source                Units
-----------------------------------------------------------------------------------------

  ── Battery
  battery_charge                  kwh_fhp_chg             203/runtimeData       kWh
  battery_discharge               kwh_fhp_di              203/runtimeData       kWh

  ── Grid
  grid_import                     kwh_uti_in              203/runtimeData       kWh
  grid_export                     kwh_uti_out             203/runtimeData       kWh

  ── Generation
  solar                           kwh_sun                 203/runtimeData       kWh
  generator                       kwh_gen                 203/runtimeData       kWh
  home_use                        kwh_load                203/runtimeData       kWh

  ── Smart Circuits
  switch_1_use                    SW1ExpEnergy            311/sw_data           kWh
  switch_2_use                    SW2ExpEnergy            311/sw_data           kWh

  ── V2L
  v2l_export                      CarSWExpEnergy          311/sw_data           kWh
  v2l_import                      CarSWImpEnergy          311/sw_data           kWh

  ── Load Breakdown
  solar_load_kwh                  kwhSolarLoad            203/runtimeData       kWh
  grid_load_kwh                   kwhGridLoad             203/runtimeData       kWh
  battery_load_kwh                kwhFhpLoad              203/runtimeData       kWh
  generator_load_kwh              kwhGenLoad              203/runtimeData       kWh

  ── APbox/MPPT
  mpan_pv1_wh                     mpanPv1Wh               203/runtimeData       Wh
  mpan_pv2_wh                     mpanPv2Wh               203/runtimeData       Wh

  Relay encoding: 1=OPEN (disconnected), 0=CLOSED (connected)
  cmdType 211 fields only populated when get_stats(include_electrical=True)
  cmdType 311 fields require Smart Circuit accessory installed
```

---

### Filter to cmdType 211 electrical fields only

```bash
$ franklinwh-cli schema --filter 211
```

```
  ── Extended Relays (211)
  grid_relay2                     gridRelayStat           211/result            relay
  black_start_relay               bFpVApboxRelay          211/result            relay
  pv_relay2                       pvRelay2                211/result            relay
  bfpv_apbox_relay                BFPVApboxRelay          211/result            relay

  ── Electrical (211)
  grid_voltage1                   gridVol1                211/result            V
  grid_voltage2                   gridVol2                211/result            V
  grid_current1                   gridCur1                211/result            A
  grid_current2                   gridCur2                211/result            A
  grid_frequency                  gridFreq                211/result            Hz
  grid_set_frequency              gridSetFreq             211/result            Hz
  grid_line_voltage               gridLineVol÷10          211/result            V
  generator_voltage               oilVol                  211/result            V
```

> [!NOTE]
> `grid_line_voltage` applies a `÷ 10` scaling factor. The raw API field `gridLineVol`
> is an integer in tenths of a volt (e.g. `2440` = `244.0 V`). The library divides by 10
> before storing the value. This is the only field with a non-obvious raw-to-display transform.

---

### JSON output (for integrators / scripts)

```bash
$ franklinwh-cli --json schema --filter power
```

```json
{
  "current": {
    "solar_production": {
      "api_key": "p_sun",
      "source": "203/runtimeData",
      "units": "kW",
      "group": "Power Flow"
    },
    "battery_use": {
      "api_key": "p_fhp",
      "source": "203/runtimeData",
      "units": "kW",
      "group": "Power Flow"
    },
    "grid_use": {
      "api_key": "p_uti",
      "source": "203/runtimeData",
      "units": "kW",
      "group": "Power Flow"
    },
    "home_load": {
      "api_key": "p_load",
      "source": "203/runtimeData",
      "units": "kW",
      "group": "Power Flow"
    },
    "battery_soc": {
      "api_key": "soc",
      "source": "203/runtimeData",
      "units": "%",
      "group": "Power Flow"
    }
  },
  "totals": {}
}
```

When `--live` is added, each entry gains a `"live_value"` key:

```json
{
  "current": {
    "solar_production": {
      "api_key": "p_sun",
      "source": "203/runtimeData",
      "units": "kW",
      "group": "Power Flow",
      "live_value": 4.82
    },
    "battery_soc": {
      "api_key": "soc",
      "source": "203/runtimeData",
      "units": "%",
      "group": "Power Flow",
      "live_value": 87.0
    }
  }
}
```

---

### With live values (`--live`)

```bash
$ franklinwh-cli schema --live --filter power
```

```
  ── Power Flow
  solar_production                p_sun                   203/runtimeData       kW       4.82
  generator_production            p_gen                   203/runtimeData       kW       0.00
  battery_use                     p_fhp                   203/runtimeData       kW       -1.20
  grid_use                        p_uti                   203/runtimeData       kW       0.00
  home_load                       p_load                  203/runtimeData       kW       3.62
  battery_soc                     soc                     203/runtimeData       %        87.00
  grid_charging_battery           gridChBat               203/runtimeData       kW       0.00
  solar_export_to_grid            soOutGrid               203/runtimeData       kW       0.00
  solar_charging_battery          soChBat                 203/runtimeData       kW       1.20
  battery_export_to_grid          batOutGrid              203/runtimeData       kW       0.00
```

> [!TIP]
> Negative `battery_use` = battery is **charging** (power flowing in).
> Negative `grid_use` = battery/solar is **exporting** to grid.

---

## FHAI / Integrator use

The JSON output is designed for downstream consumers that need to know what
each field represents. An integrator can query the schema once at startup
to build sensor metadata:

```python
import subprocess, json

result = subprocess.run(
    ["franklinwh-cli", "--json", "schema"],
    capture_output=True, text=True
)
schema = json.loads(result.stdout)

for field, meta in schema["current"].items():
    print(f"{field}: {meta['units']} from {meta['api_key']} ({meta['source']})")
```

Or simply reference it when mapping library fields to Home Assistant sensor
configuration — every `stats.current.<field>` value corresponds to exactly
one `api_key` in exactly one `source` cmdType.

---

## Implementation notes

- **No login required** for the base schema — the registry is static and local
- **One MQTT call** with `--live` (same as `franklinwh-cli status`)
- The schema registry is in `franklinwh_cloud/cli_commands/schema.py` (`CURRENT_SCHEMA`, `TOTALS_SCHEMA`)
- The same mapping is documented as inline comments in `franklinwh_cloud/models.py`
- `--filter` matches case-insensitively against the `group` field (e.g. `211`, `power`, `relay`, `battery`)
