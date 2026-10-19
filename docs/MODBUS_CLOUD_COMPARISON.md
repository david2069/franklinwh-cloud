# Cloud API vs Modbus TCP — Metrics Comparison

The same aGate can be read two ways:

- **Cloud API** — this library, `get_stats()` over the FranklinWH cloud
  (`getDeviceCompositeInfo`, cmdType 203, `result.runtimeData`).
- **Modbus TCP Server (aGate :502)** — read locally by a Modbus client such as
  [franklinwh-modbus](https://github.com/david2069/franklinwh-modbus).

This page maps each metric across the two. franklinwh-modbus keeps its own copy of
this table, linked to its own examples; the two are maintained separately on purpose.
Code examples for every cloud field are in the [API Cookbook](API_COOKBOOK.md#power-flow-status).

> [!NOTE]
> **Evidence (AP-14).** Cloud names, units and signs are from this library's code
> (`models.py`, `mixins/stats.py`, `const/modes.py`). Modbus names are from franklinwh-modbus
> `develop` (`controller.py`). A mapping marked **INFERRED** or **ASSUMED** has not been
> confirmed by a side-by-side capture. One site's data is a candidate, not a rule.

## Units and signs

| | Cloud API | Modbus client |
|---|---|---|
| Power | kW | W |
| Energy | kWh, **daily** (resets at local midnight — ASSUMED site-local) | Wh, **lifetime** counters |
| Grid sign | `+` import, `−` export | `+` import (per franklinwh-modbus docs; unconfirmed on device) |
| Battery sign | `−` charging, `+` discharging | `−` charging |

Grid sign on the cloud side was observed live on 2026-10-17: `grid_use` = −2.7 kW while
exporting (solar 2.9 kW, home 0.2 kW).

## Power and state

| Metric | Cloud (`stats.current.…`) | Cloud raw key | Modbus (franklinwh-modbus) | Modbus source | Notes |
|---|---|---|---|---|---|
| Solar power | `solar_production` (kW) | `p_sun` | `read_solar_status()['total_solar_w']`, else `['ac_power_w']` (W) | Extension total, else M502 `OutPw` | |
| Generator power | `generator_production` (kW) | `p_gen` | — | — | Not over Modbus |
| Battery power | `battery_use` (kW) | `p_fhp` | `read_battery_status()['battery_power_w']` (W) | M714 `DCW`, summed over ports | Modbus is DC side; whether `p_fhp` is AC or DC is unknown — **INFERRED** equivalent |
| Grid power | `grid_use` (kW) | `p_uti` | `read_grid_status()['grid_power_w']` (W) | M701 `W` | Same sign convention (see above) |
| Home load | `home_load` (kW) | `p_load` | `read_solar_status()['extension']['home_load_ext']` (W) | Extension 16000 (~1 W), else 15506 (~100 W steps) | 16000 is undocumented |
| Battery SoC | `battery_soc` (%) | `soc` | `read_battery_status()['soc']` (%) | M713 `SoC` | |
| Smart circuit / V2L power | `switch_1_load`, `switch_2_load`, `v2l_use` (kW) | cmdType 311 (not composite) | — | — | Cloud only; extra MQTT call |
| Operating mode | `work_mode` / `work_mode_desc` | `result.currentWorkMode` (1 TOU, 2 Self-Consumption, 3 Emergency Backup) | `read_native_mode()['mode_name']` | Extension 15507 | Does **not** change during a remote dispatch — see VPP row |
| Active programme | `tou_mode` / `tou_mode_desc` | `runtimeData.mode` / `.name` | — | — | A programme ID, **not** a run status |
| Run status | `run_status` / `run_status_desc` | `runtimeData.run_status` | No direct register | Nearest: `DCW` sign + deadband → charge / discharge / standby | **INFERRED** mapping. Codes in [RUN_STATUS](API_COOKBOOK.md#run_status-value-table-keyed-by-runtimedatarun_status-not-runtimedatamode) |
| External control (VPP) | `tou_mode == 9`, `effective_mode == "VPP mode"` | `runtimeData.mode` = 9 | Remote-control state | See franklinwh-modbus `VPP_MODE_REFERENCE.md` | Cloud showed `mode` 9 within a minute of a Modbus force discharge (one site, 2026-10-14) — [VPP Mode](API_COOKBOOK.md#vpp-mode-virtual-power-plant) |
| Grid connection | `grid_connection_state` (4 states) | Derived — see below | `read_grid_status()['connection_state']` (3 states) | M701 `ConnSt` | Closest raw cloud field: `main_sw[0]` |

### Grid connection — 4 cloud states vs 3 Modbus states

The cloud value is **derived**, not read from one field
([Grid Connection State](API_COOKBOOK.md#grid-connection-state)):

| Cloud state | How the library decides | Modbus `ConnSt` |
|---|---|---|
| `CONNECTED` | `main_sw[0] == 1` (grid relay closed) | Connected |
| `OUTAGE` | `offGridFlag` set, or relay open and `offgridState == 0` | Disconnected — **INFERRED** |
| `SIMULATED_OFF_GRID` | relay open (or `offgridreason` set) and `selectOffgrid` → `offgridState == 1` | Disconnected — **INFERRED** |
| `NOT_GRID_TIED` | Site configured with no grid (startup flag) | — |

Modbus cannot tell a user-simulated island from a real outage; the cloud needs the extra
`selectOffgrid` call to do it. Modbus `Fault` has no cloud counterpart identified.

## Energy

| Metric | Cloud (`stats.totals.…`, daily kWh) | Cloud raw key | Modbus (lifetime Wh) | Modbus source | Notes |
|---|---|---|---|---|---|
| Solar | `solar` | `kwh_sun` | — | — | Not over Modbus |
| Generator | `generator` | `kwh_gen` | — | — | Not over Modbus |
| Grid import | `grid_import` | `kwh_uti_in` | `read_grid_status()['grid_import_wh']` | M701 `TotWhAbs` | Modbus daily = difference of two readings |
| Grid export | `grid_export` | `kwh_uti_out` | `read_grid_status()['grid_export_wh']` | M701 `TotWhInj` | As above |
| Battery charge | `battery_charge` | `kwh_fhp_chg` | Not read by franklinwh-modbus yet | M714 `DCWhAbs` | Device has it |
| Battery discharge | `battery_discharge` | `kwh_fhp_di` | Not read by franklinwh-modbus yet | M714 `DCWhInj` | Device has it |
| Home | `home_use` | `kwh_load` | — | — | Not over Modbus |

For a **lifetime** figure to compare with Modbus counters, use
`get_power_details(type=5, …)` — see [Historical Energy Data](API_COOKBOOK.md#historical-energy-data).
Whether the cloud lifetime total and the Modbus counter agree has not been checked.

## Modbus-only data

- Battery: SoH, capacity (`wh_rating`, `wh_available`), DC current and temperature,
  per-battery breakdown.
- Grid: voltage, frequency, VA, VAR, power factor, temperatures. (The cloud has some of
  these via `get_stats(include_electrical=True)` — cmdType 211, an extra MQTT call.)
- Reserves: extension 15508 and 15509 (15509 repeats 15508 on current firmware).
- Remote-control state and a `partial` read-quality flag.

## Choosing a source

| | Cloud API | Modbus TCP Server (aGate :502) |
|---|---|---|
| Network | Internet + FranklinWH cloud | Local LAN only |
| Rate limits | Yes — shared per account ([Rate Limiting](RATE_LIMITING.md)) | None known |
| Daily totals, solar/home energy, programme name | Yes | No |
| Electrical detail, per-battery data | Partial | Yes |
| Tells simulated off-grid from outage | Yes | No |
