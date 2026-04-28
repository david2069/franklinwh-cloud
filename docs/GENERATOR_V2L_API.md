# Generator & V2L API Reference

> **Scope:** `franklinwh_cloud` mixin methods for the Generator Module and
> Vehicle-to-Load (V2L) accessories.
> Generator APIs are **confirmed** from live traffic.
> V2L control is **speculative** — see the clearly marked section below.

---

## Generator Module

FranklinWH's Generator Module connects a standby petrol/diesel generator to
the aGate system, enabling automatic start during grid outages or as a
supplemental power source during off-grid operation.

**Supported hardware:**

| Accessory Type | SKU | Notes |
|---|---|---|
| 201 | `ACCY-GENV1-US` | V1 — enables V2L CarSW port on V1 Smart Circuits |
| 203 | `ACCY-GENV2-US` | V2 — no V2L port (V2L built-in on V2 Smart Circuits) |
| 301 | `ACCY-GENV1-AU` | AU V1 — no V2L capability on AU hardware |

### ✅ `get_generator_info()` — Confirmed

```python
gen = await client.get_generator_info()
```

**Endpoint:** `GET hes-gateway/terminal/selectIotGenerator`

**Returns:** raw JSON dict from the aGate. Key fields observed:

| Field | Type | Description |
|---|---|---|
| `status` | int | Current running state (mirrors `genStat`) |
| `manuSw` | int | Operating mode: `1` = Auto-schedule, `2` = Manual |
| `opt` | int | Option flag |

**Example:**
```python
gen = await client.get_generator_info()
print(gen)
# {'status': 0, 'manuSw': 2, 'opt': 1}
```

**Note:** Only call this if the generator module is installed. Check first:
```python
snap = await client.discover()
if not snap.accessories.has_generator:
    print("No generator module installed")
```

Or via the accessories CLI:
```bash
franklinwh-cli accessories
```

---

### ✅ `set_generator_mode(mode)` — Confirmed

```python
result = await client.set_generator_mode(mode=1)
```

**Endpoint:** `POST hes-gateway/terminal/updateIotGenerator`

**Parameters:**

| `mode` | Behaviour |
|---|---|
| `1` | Auto-schedule (generator starts automatically on outage/threshold) |
| `2` | Manual (generator only runs when explicitly started) |

**Payload sent:**
```json
{"gatewayId": "10060006A0XXXXXXXXXX", "manuSw": 1, "opt": 1}
```

**Important:** This only toggles between Auto and Manual. Starting/stopping
the generator physically and configuring auto-start thresholds is done in
the FranklinWH app. There is no confirmed `startGenerator` / `stopGenerator`
API endpoint in captured traffic.

---

### ✅ Generator Telemetry — `get_stats()` fields

All available without extra API calls, included in the standard stats poll:

```python
stats = await client.get_stats()
cur = stats.current

print(cur.generator_production)  # float kW — live output
print(cur.generator_enabled)     # int — genEn flag (0/1)
print(cur.generator_status)      # int — genStat raw code

from franklinwh_cloud.const import GENERATOR_STATE
print(GENERATOR_STATE[cur.generator_status])
# "Standby / OFF" | "Running / ON" | "Cooldown" | "Fault"
```

**Daily energy totals:**
```python
print(stats.totals.generator)          # float kWh — daily generator output
print(stats.totals.generator_load_kwh) # float — load served by generator
```

---

### ✅ `get_accessories_power_info(option=3)` — Generator Live Power

```python
gen_pwr = await client.get_accessories_power_info(option=3)
# → {"generator": {"power": 3.5, "voltage": 240.1, "current": 14.6, "frequency": 60.0}}
```

**Source:** MQTT cmdType 353 (`CarSW` + generator power data).

---

## V2L — Vehicle-to-Load

V2L allows the aGate to power AC loads (e.g. tools, appliances, EV charging)
directly from the battery, through the CarSW port on the Smart Circuit module.

**Hardware compatibility:**

| Configuration | V2L Capable? | Notes |
|---|---|---|
| US V1 Smart Circuits (202) + Generator Module (201) | ✅ Yes | Via CarSW port on SC, enabled by Gen Module |
| US V2 Smart Circuits (204) | ✅ Yes | V2L built-in, no Generator Module needed |
| AU V1 Smart Circuits (302) | ❌ No | AU hardware has no V2L port |
| US V1 Smart Circuits only (no Gen Module) | ❌ No | CarSW port not available without Gen Module |

**Check eligibility in code:**
```python
snap = await client.discover()
print(snap.flags.v2l_eligible)  # bool
print(snap.flags.v2l_note)      # human-readable reason
```

---

### ✅ V2L Telemetry — All Confirmed

#### Real-time state

```python
stats = await client.get_stats()
cur = stats.current

print(cur.v2l_enabled)   # int — runtimeData.v2lModeEnable (feature licence flag)
print(cur.v2l_status)    # int — runtimeData.v2lRunState
print(cur.v2l_use)       # float kW — CarSWPower (live output power)
print(cur.v2l_relay)     # int — cmdType 211 evRelayStat (contactor state)

from franklinwh_cloud.const import V2L_RUN_STATE
print(V2L_RUN_STATE[cur.v2l_status])
# 0 = "Disabled"
# 1 = "Standby"
# 2 = "Discharging / Active"
# 3 = "Fault"
```

#### Daily energy

```python
print(stats.totals.v2l_export)   # float kWh — energy discharged through CarSW
print(stats.totals.v2l_import)   # float kWh — energy returned through CarSW
```

#### Live current/voltage (MQTT cmdType 353)

```python
v2l = await client.get_accessories_power_info(option=2)
# → {
#     "v2l": {
#       "current":    12.3,   # A
#       "power":       2.8,   # kW
#       "imp_energy":  0.0,   # kWh
#       "exp_energy": 14.2    # kWh
#     }
#   }
```

#### Relay state (requires `include_electrical=True`)

```python
stats = await client.get_stats(include_electrical=True)
print(stats.current.v2l_relay)
# cmdType 211 evRelayStat: 1=OPEN (contactor closed/active), 0=CLOSED
```

---

### ⚠️ `set_v2l_mode(enable)` — SPECULATIVE PLACEHOLDER

> **Status: SPECULATIVE — not verified on live V2L hardware.**
>
> This method is a placeholder based on analysis of the cmdType 311
> Smart Circuit payload structure. It may or may not work.
> **Do not use in production without live verification.**

```python
# ⚠️ SPECULATIVE — verify before production use
result = await client.set_v2l_mode(enable=True)   # Start V2L
result = await client.set_v2l_mode(enable=False)  # Stop V2L
```

#### Hypothesis

The CarSW port is **Sw3** in the cmdType 311 Smart Circuit payload — the same
mechanism used to control Smart Circuit 1 and 2. On a US V1 system with the
Generator Module, `modeChoose=3` in the 311 response indicates a 3-circuit
configuration (Sw1 + Sw2 + Sw3/CarSW).

Expected 311 payload on a V2L-capable system:
```json
{
  "Sw1Name": "Circuit 1",  "Sw1Mode": 1,
  "Sw2Name": "Circuit 2",  "Sw2Mode": 0,
  "Sw3Name": "V2L / Car",  "Sw3Mode": 1,  ← CarSW port
  "modeChoose": 3,                          ← 3-circuit (Sw1+Sw2+Sw3/CarSW)
  "v2lModeEnable": 1,                       ← system V2L licence flag
  "v2lRunState": 2                          ← 0=Disabled 1=Standby 2=Active 3=Fault
}
```

The speculative control write:
```json
{
  "opt": 1,
  "Sw3Mode": 1,       ← 1=ON (V2L active), 0=OFF
  "Sw3ProLoad": 0,    ← inverse of Sw3Mode (ProLoad is the "protected load" flag)
  "Sw3MsgType": 1     ← required write flag for circuit 3
}
```

#### Implementation

`set_v2l_mode()` calls `_update_smart_circuit_config(circuit=3, ...)` which:
1. Reads the current 311 state via `get_smart_circuits_info()`
2. Patches `Sw3Mode` and `Sw3ProLoad`
3. Writes back via `_mqtt_send(cmdType=311, opt=1)`

A `WARNING` level log is emitted at runtime to flag the speculative status.

#### Alternative hypothesis

A dedicated V2L endpoint (e.g. `updateV2l` or `selectV2lMode`) may exist
that accepts `v2lModeEnable` directly, similar to how `updateIotGenerator`
is separate from the Smart Circuit 311 path. This has **not** been observed
in any captured mobile app traffic.

#### How to verify

If you have a US V1 aGate + Generator Module + Smart Circuits with V2L:

1. Set up Charles Proxy or mitmproxy on your phone
2. Open the FranklinWH app and navigate to the V2L / CarSW control
3. Toggle V2L on and off
4. Capture the raw POST payloads and compare against this hypothesis
5. Open a GitHub issue with the captured payload: [david2069/franklinwh-cloud](https://github.com/david2069/franklinwh-cloud/issues)

**Fields to look for in the capture:**
- `cmdType` value (is it 311, or something new like 355/357?)
- Presence of `Sw3Mode` vs a dedicated `v2lModeEnable` flag
- Presence of `modeChoose` and its value
- Any separate REST endpoint (not `sendMqtt`)

#### Prerequisites before calling

```python
# 1. Hardware check
snap = await client.discover()
assert snap.flags.v2l_eligible, f"Not V2L capable: {snap.flags.v2l_note}"

# 2. Feature licence check
stats = await client.get_stats()
assert stats.current.v2l_enabled, "v2lModeEnable=0 — V2L not licensed on this gateway"

# 3. Off-grid check (V2L only works off-grid)
assert stats.current.grid_connection_state.value != "Connected", \
    "V2L requires off-grid mode (grid relay open)"
```

---

## Field Reference — All V2L & Generator Stats Fields

| `stats.current.*` | Raw API field | Source | Type | Notes |
|---|---|---|---|---|
| `generator_production` | `p_gen` | `203/runtimeData` | kW | Live generator output |
| `generator_enabled` | `genEn` | `203/runtimeData` | int | Feature enable flag |
| `generator_status` | `genStat` | `203/runtimeData` | int | Use `GENERATOR_STATE` lookup |
| `generator_relay` | `main_sw[1]` | `203/runtimeData` | int | 1=OPEN (connected) |
| `v2l_enabled` | `v2lModeEnable` | `203/runtimeData` | int | System licence flag |
| `v2l_status` | `v2lRunState` | `203/runtimeData` | int | Use `V2L_RUN_STATE` lookup |
| `v2l_use` | `CarSWPower` | `311/sw_data` | kW | Live V2L output power |
| `v2l_relay` | `evRelayStat` | `211/result` | int | V2L contactor state |
| `v2l_export` | `CarSWExpEnergy` | `311/sw_data` | kWh | Daily V2L energy exported |
| `v2l_import` | `CarSWImpEnergy` | `311/sw_data` | kWh | Daily V2L energy imported |

| `stats.totals.*` | Raw API field | Source | Notes |
|---|---|---|---|
| `generator` | `kwh_gen` | `203/runtimeData` | Daily kWh |
| `generator_load_kwh` | `kwhGenLoad` | `203/runtimeData` | Load served |
| `v2l_export` | `CarSWExpEnergy` | `311/sw_data` | |
| `v2l_import` | `CarSWImpEnergy` | `311/sw_data` | |

---

## Related Documentation

- [API Cookbook](API_COOKBOOK.md) — copy-paste recipes for common tasks
- [REGION_QUIRKS.md](REGION_QUIRKS.md) — AU vs US accessory differences
- [CLI_SUPPORT_INFO.md](CLI_SUPPORT_INFO.md) — `--diag` flag shows V2L and Generator in Feature Flags
- [MQTT Command Catalog](MQTT_CMD_CATALOG.md) — cmdType 311 (SC/V2L), 353 (Accessory Loads)
