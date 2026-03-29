# Payload Extraction Strategies: `discover` vs `support`

The `franklinwh-cloud` library provides two complementary but structurally opposite methods for extracting a payload from the aGate hardware. 

It is **critical** for all downstream integrators and autonomous coding agents to understand the operational differences between these two methodologies. Choosing the wrong payload extraction strategy will result in either massive technical debt or scrubbed troubleshooting data.

---

## 1. The `discover` Command (Human-Readable UI Binding)
**CLI Command**: `franklinwh-cli discover --json -vv`
**Python API**: `snap = await client.discover(tier=3)`

### Use Case
The `discover` module is the **definitive guide for UI interactions**. Whenever you are building a dashboard, logging metrics to Home Assistant, or presenting data to a homeowner, you MUST utilize the `DeviceSnapshot` returned by this command.

### What it Does
It acts as a translation layer. It automatically combs through the raw aGate hardware payload and maps opaque integer identifiers into fully localized human-readable English strings based on the library's internal constant maps.

**Example Translation**:
* Raw Hardware: `Sw1Mode = 2`
* `discover` Output: `"Smart_Circuit_1": "Generator"`

### 🛑 Anti-Pattern Warning for Agents
Do **not** take the "easy path" of querying `client.get_device_composite_info()` directly to build your UI. If you do, you will be forced to reinvent the integer-to-string dictionary mappings manually. Always consume the pre-parsed `DeviceSnapshot` hierarchy.

---

## 2. The `support` Command (Raw Diagnostic Troubleshooting)
**CLI Command**: `franklinwh-cli support --json`
**Python API**: `snap = await collect_snapshot(client)`

### Use Case
The `support` command is strictly intended for **debugging, firmware tracing, and issuing bug reports**. Whenever an aGate behaves unexpectedly or a new hardware module (like an `aHub` networking bridge) is installed, you MUST utilize this command to dump the raw system state.

### What it Does
It intentionally bypasses the string-translation layer. It recursively dumps the literal, unparsed integer states directly from the RS485 bus and cloud API. It natively aggregates all undocumented parameters into arrays like `accessories.hardware_registry_dump`.

**Example Output**:
* Raw Hardware: `Sw1Mode = 2`
* `support` Output: `"Sw1Mode": 2`

### 🛑 Anti-Pattern Warning for Agents
Do **not** use the `support` payload to power Home Assistant sensors or user interfaces. The payload is heavily fragmented, retains raw integers (which users cannot interpret), and is explicitly designed to isolate low-level networking and hardware failures. 

---

## Summary Matrix

| Requirement | You Should Use |
|-------------|----------------|
| Displaying the active TOU schedule to a user | `discover` |
| Presenting boolean relay states (Grid, Solar) | `discover` |
| Sending a bug report to FranklinWH | `support` |
| Tracking down an undocumented `aHub` MAC address | `support` |
| Counting how many aPower units are connected | `discover` |

---

## 3. Execution Best Practices: Initialization vs Runtime

Context and timing are critical. The `DeviceSnapshot` returned by `discover()` is deliberately heavy because it guarantees **atomicity** (point-in-time accuracy) and cross-references hardware integers across 15+ API endpoints. 

### The Initialization Phase (Call `discover()`)
Because physical hardware topography (number of batteries, Smart Circuit allocations) and system firmware versions **do not change during runtime**, integrations like Home Assistant plugins should strictly call `client.discover(tier=3)` **once** during their startup/initialization phase. 

This single authoritative call avoids 429 HTTP Rate Limits while safely mapping the static hardware entities.

### The Runtime Phase (Call `get_stats()`)
During active runtime monitoring loops (e.g., ticking every 15 seconds to update a dashboard), **do not** call `discover()`. 

Instead, polling loops should drastically reduce context and rely purely on lightweight, localized endpoints like `await client.get_stats()` or `await client.get_power_info()` to update continuous variables like battery SoC and grid import metrics.
