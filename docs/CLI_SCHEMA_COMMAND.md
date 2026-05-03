# CLI Reference: `franklinwh-cli schema`

> **Purpose:** The `schema` command is the authoritative reference for the
> `franklinwh_cloud` data model. It prints every field in `stats.current`,
> `stats.totals`, and the grid power control settings alongside the raw API JSON
> key, the MQTT cmdType source, units, and (optionally) the live value from your
> gateway.

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
- `gridFeedMax = -1` means **unlimited export**, not a bug

`franklinwh-cli schema` answers all of these questions in one command.

---

## Usage

```bash
franklinwh-cli schema                           # full schema — no login required
franklinwh-cli schema --live                    # + live values from get_stats() + get_power_control_settings()
franklinwh-cli schema --filter 211              # only cmdType 211 electrical fields
franklinwh-cli schema --filter power            # only power flow fields
franklinwh-cli schema --filter mode             # only global Operating Mode configurations (SOC limiters)
franklinwh-cli schema --filter tou              # only TOU schedule blocks
franklinwh-cli schema --filter relay            # only relay fields
franklinwh-cli schema --filter grid             # only Grid Power Control Limits section
franklinwh-cli schema --json                    # machine-readable JSON
franklinwh-cli schema --live --json             # JSON + live values
franklinwh-cli schema --live --filter power     # filtered with live values
```

---

## Output sections

| Section | Header | Source | Login required? |
|---------|--------|--------|-----------------|
| `stats.current` | `📊 stats.current` | `getDeviceCompositeInfo` / cmdType 203, 211, 311 | No (static) / Yes (live) |
| `stats.totals` | `📈 stats.totals` | `getDeviceCompositeInfo` / cmdType 203, 311 | No (static) / Yes (live) |
| Operating Mode Config | `⚙️` | `getGatewayTouListV2` | No (static) |
| TOU Schedule Blocks | `📅` | `setTouSchedule` / `getTouList` | No (static) |
| Grid Power Control Limits | `⚡` | `get_power_control_settings` (REST) | Yes (live only) |

---

## Output columns

| Column | Meaning |
|--------|---------|
| **Python Attribute** | The field name on `stats.current` or `stats.totals` |
| **Raw API Key** | The JSON key in the FranklinWH API response |
| **Source** | Which API endpoint or transport provides this field |
| **Units** | Physical unit (kW, kWh, V, A, Hz, %, °C, `kW / -1`) |
| **Live Value** | (with `--live` only) current reading from the gateway |

### Source prefix notation

> [!IMPORTANT]
> **`203/` is a REST GET — not a `sendMqtt` call.** The prefix notation describes *which API
> response* a field comes from, not the transport mechanism used to retrieve it. Specifically:
> `getDeviceCompositeInfo` is a plain `HTTPS GET` that the cloud server assembles server-side.
> The `sendMqtt + cmdType 203` path (`_status()`) is a legacy private method not used by
> `get_stats()`. See [Transport Architecture](API_COOKBOOK.md#-transport-architecture-rest-get-vs-mqtt-relay)
> for the full breakdown.

| Source | Transport | Cost | When it fires |
|--------|-----------|------|---------------|
| `203/runtimeData` | **REST GET** → `getDeviceCompositeInfo` | **Cheapest** — CloudFront-cached | Every `get_stats()` call |
| `203/result` | **REST GET** → `getDeviceCompositeInfo` (top-level) | **Cheapest** — same call | Every `get_stats()` call |
| `211/result` | **MQTT Relay** → `get_power_info()` (sendMqtt cmdType 211) | Higher — aGate round-trip | Only when `include_electrical=True` |
| `311/runtimeData` | **MQTT Relay** → `get_smart_circuits_info()` (cmdType 311) | Higher — aGate round-trip | Only if smart circuits accessory present |
| `311/sw_data` | **MQTT Relay** → `_switch_usage()` (cmdType 353, not 311) | Higher — aGate round-trip | Only if smart circuits active in `pro_load[]` |
| `get_tou_info` | **REST GET** → TOU schedule endpoint | Low-medium | Only in TOU mode, opt-in |
| `get_power_control_settings` | **REST GET** | Low — cached | `--live` only |
| `derived` | Local computation | **Free** — no API call | Always |

### Relay encoding

All relay fields use firmware convention: **`1 = OPEN (disconnected)`, `0 = CLOSED (connected)`**
This is the inverse of what you might expect — the firmware reports relay coil state, not contact state.

### Grid limit encoding (`kW / -1` units)

Fields sourced from `get_power_control_settings` use a three-state encoding:

| Raw value | Meaning | Display |
|-----------|---------|---------|
| `-1` | Unlimited | `Unlimited (-1)` |
| `0` | Not allowed / Disabled | `Not allowed (0)` |
| `> 0` | kW power cap | `{value:.1f} kW` |

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

  ── Mode
  work_mode                       currentWorkMode         203/result            int
  work_mode_desc                  derived                 derived               str
  tou_mode                        mode                    203/runtimeData       int
  tou_mode_desc                   name                    203/runtimeData       str
  run_status                      run_status              203/runtimeData       int
  run_status_desc                 RUN_STATUS[run_status]  derived               str
  effective_mode                  derived                 derived               str

  ── Battery Packs
  apower_serial_numbers           fhpSn                   203/runtimeData       list
  apower_soc                      fhpSoc                  203/runtimeData       list
  apower_power                    fhpPower                203/runtimeData       list
  apower_bms_mode                 bms_work                203/runtimeData       list
  ...

⚡ Grid Power Control Limits  (get_power_control_settings)
  -1 = Unlimited,  0 = Not allowed/Disabled,  >0 = kW power cap

  ── Global Limits
  globalGridChargeMax             globalGridChargeMax     get_power_control_settings  kW / -1
  globalGridDischargeMax          globalGridDischargeMax  get_power_control_settings  kW / -1
  globalSettingStatus             globalSettingStatus     get_power_control_settings  int

  ── Feed-In (Export)
  gridFeedMax                     gridFeedMax             get_power_control_settings  kW / -1
  notControlExportSolar           notControlExportSolar   get_power_control_settings  bool

  ── Import
  gridMax                         gridMax                 get_power_control_settings  kW / -1

  ── Programmes
  sgipFlag                        sgipFlag                get_power_control_settings  0/1
  itcFlag                         itcFlag                 get_power_control_settings  0/1
  isNem3                          isNem3                  get_power_control_settings  0/1
  isCalifornia                    isCalifornia            get_power_control_settings  0/1
```

---

### Grid Power Control Limits (with live values)

```bash
$ franklinwh-cli schema --live --filter grid
```

```
⚡ Grid Power Control Limits  (get_power_control_settings)
  -1 = Unlimited,  0 = Not allowed/Disabled,  >0 = kW power cap

  ── Global Limits
  globalGridChargeMax             globalGridChargeMax     ...  kW / -1   Unlimited (-1)
  globalGridDischargeMax          globalGridDischargeMax  ...  kW / -1   Unlimited (-1)
  globalSettingStatus             globalSettingStatus     ...  int       0

  ── Feed-In (Export)
  gridFeedMax                     gridFeedMax             ...  kW / -1   10.0 kW
  gridFeedMaxFlag                 gridFeedMaxFlag         ...  int       2
  notControlExportSolar           notControlExportSolar   ...  bool      True

  ── Import
  gridMax                         gridMax                 ...  kW / -1   Unlimited (-1)
  gridMaxFlag                     gridMaxFlag             ...  int       2
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

  ── Power Measurements (211)
  grid_voltage1                   gridVol1                211/result            V
  grid_voltage2                   gridVol2                211/result            V
  grid_current1                   gridCurr1               211/result            A
  grid_current2                   gridCurr2               211/result            A
  grid_frequency                  gridFreq                211/result            Hz
  grid_set_frequency              dspSetFreq              211/result            Hz
  grid_line_voltage               gridLineVol÷10          211/result            V
  generator_voltage               genVoltage              211/result            V
  dsp_run_status                  dspRunStatus            211/result            int
  ibg_run_status                  ibgRunStatus            211/result            int
```

> [!NOTE]
> `grid_line_voltage` applies a `÷ 10` scaling factor. The raw API field `gridLineVol`
> is an integer in tenths of a volt (e.g. `2440` = `244.0 V`). The library divides by 10
> before storing the value. This is the only field with a non-obvious raw-to-display transform.

---

### Operating Mode & TOU Blocks

```bash
$ franklinwh-cli schema --filter mode
```

```
  ── SOC Limits
  soc                             soc                     getTouList            float
  maxSoc                          maxSoc                  getTouList            float
  minSoc                          minSoc                  getTouList            float
  dischargeDepthSoc               dischargeDepthSoc       getTouList            float
  complianceSoc                   complianceSoc           getTouList            float
```

```bash
$ franklinwh-cli schema --filter tou
```

```
  ── Time Block
  startHourTime                   startHourTime           setTouSchedule        HH:MM
  endHourTime                     endHourTime             setTouSchedule        HH:MM

  ── Configuration
  name                            name                    getTouList            str
  dispatchId                      dispatchId              setTouSchedule        int    [1=Home, 2=Standby, 3=SolarCharge, 6=SelfCons, 7=Export, 8=GridCharge]
  targetSoc                       targetSoc               setTouSchedule        int

  ── Tariff/Pricing
  waveType                        waveType                setTouSchedule        int    [0=OffPeak, 1=MidPeak, 2=Peak, 4=SuperOff]
```

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
    "battery_soc": {
      "api_key": "soc",
      "source": "203/runtimeData",
      "units": "%",
      "group": "Power Flow"
    }
  },
  "totals": {},
  "grid_limits": {}
}
```

When `--live` is added, each entry gains a `"live_value"` key. The `grid_limits`
object is populated from `get_power_control_settings`:

```json
{
  "grid_limits": {
    "gridFeedMax": {
      "api_key": "gridFeedMax",
      "source": "get_power_control_settings",
      "units": "kW / -1",
      "group": "Feed-In (Export)",
      "live_value": 10.0
    },
    "gridMax": {
      "api_key": "gridMax",
      "source": "get_power_control_settings",
      "units": "kW / -1",
      "group": "Import",
      "live_value": -1.0
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
  solar_production                p_sun                   203/runtimeData       kW       1.20
  battery_use                     p_fhp                   203/runtimeData       kW       -0.70
  grid_use                        p_uti                   203/runtimeData       kW       0.00
  home_load                       p_load                  203/runtimeData       kW       0.50
  battery_soc                     soc                     203/runtimeData       %        96.00
  grid_charging_battery           gridChBat               203/runtimeData       kW       0.21
  solar_export_to_grid            soOutGrid               203/runtimeData       kW       0.23
  solar_charging_battery          soChBat                 203/runtimeData       kW       8.85
  battery_export_to_grid          batOutGrid              203/runtimeData       kW       0.04
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

# Grid limits
for field, meta in schema["grid_limits"].items():
    print(f"{field}: {meta['units']} → {meta.get('live_value')}")
```

---

## Implementation notes

- **No login required** for the base schema — the registry is static and local
- **`--live`** makes two calls: `get_stats(include_electrical=True)` (MQTT+REST) + `get_power_control_settings()` (REST)
- The schema registries are in `franklinwh_cloud/cli_commands/schema.py`:
  - `CURRENT_SCHEMA` — `stats.current` fields
  - `TOTALS_SCHEMA` — `stats.totals` fields
  - `GRID_LIMITS_SCHEMA` — `get_power_control_settings` fields (added v3)
- The same mapping is documented as inline comments in `franklinwh_cloud/models.py`
- `--filter` matches case-insensitively against the `group` field (e.g. `211`, `power`, `relay`, `battery`, `grid`)
