# FEAT-CLI-DISCOVER-VERBOSE — Implementation Plan

> **Feature ID:** `FEAT-CLI-DISCOVER-VERBOSE`
> **Date:** 2026-03-23
> **Status:** Planning — awaiting approval
> **Related:** `docs/DEVICE_CATALOG_DESIGN.md`, `docs/API_FIELD_REGISTRY.md`

---

## Goal

Enhance `franklinwh-cli discover` with a two-layer architecture:
1. **Library API** — `client.discover()` returns a structured `DeviceSnapshot` by category
2. **CLI renderer** — `discover.py` formats the snapshot at 3 verbosity tiers

## Architecture

```
┌────────────────────────────────────────────────────┐
│  Python Library API                                │
│                                                    │
│  snapshot = await client.discover(tier=2)           │
│  snapshot.flags          → feature flag analysis    │
│  snapshot.site           → location / geo / tz      │
│  snapshot.batteries      → aPower inventory         │
│  snapshot.accessories    → SC / Gen / aPBox         │
│  snapshot.grid           → limits / entrance flags  │
│  snapshot.firmware       → aGate + aPower versions  │
│  snapshot.warranty       → expiry / throughput      │
│  snapshot.programmes     → VPP / BB / SGIP / NEM    │
│  snapshot.to_dict()      → full JSON serialization  │
└───────────────┬────────────────────────────────────┘
                │
   ┌────────────┼────────────────┐
   ▼            ▼                ▼
CLI render   FEM import     User scripts
(discover.py) (DeviceDiscovery) (custom)
```

## Components

### 1. DeviceSnapshot dataclass — `franklinwh_cloud/models/discovery.py` [NEW]

Structured result from `client.discover()`. Mirrors FEM's `DeviceCapabilities` but
Cloud-API-native. Categories:

| Category | Fields | Source APIs |
|----------|--------|------------|
| `site` | name, address, country, province, lat/lon, timezone, PTO date | `get_equipment_location`, `get_site_and_device_info` |
| `agate` | model, SN, firmware, hw version, protocol, device time, activated date | `get_home_gateway_list`, `get_agate_info` |
| `batteries` | count, total kWh, per-unit: SN, capacity, SoC, firmware (FPGA/DCDC/INV/BMS) | `get_device_info`, `get_apower_info` |
| `flags` | ✅/❌ table: solar, TOU, PCS, V2L, MPPT, 3-phase, off-grid, CT split (grid/PV) | `get_entrance_info`, `get_device_composite_info` |
| `accessories` | SC (x2/x3, version, names, merge, V2L port), generator, aPBox, aHub, MAC-1 | `get_accessories`, `get_smart_circuits_info`, `get_agate_info` |
| `grid` | PCS limits, import/export, feed-in, peak demand, off-grid state + reason | `get_entrance_info`, `get_device_info` |
| `programmes` | BB (HI), SGIP/JA12 (CA), SDCP, VPP, NEM type | `get_entrance_info`, `get_programme_info`, TOU template |
| `warranty` | expiry, throughput, installer company/phone/email, per-device warranty | `get_warranty_info` |
| `firmware` | IBG, SL, AWS, App, Meter, MSA model/SN, per-aPower BMS/bootloader/thermal | `get_agate_info`, `get_apower_info` |
| `network` | WiFi/Eth/4G IPs, SSID, AWS status | `get_network_info`, `get_connection_status` |
| `electrical` | L1/L2 voltage, current, frequency, relays | `get_device_composite_info` |

### 2. Device catalog JSON — `franklinwh_cloud/const/device_catalog.json` [NEW]

See `docs/DEVICE_CATALOG_DESIGN.md` for the Hybrid A+B decision. Contains:
- Model registry (aGate, aPower, accessories) with metadata
- Compatibility matrix
- Programme/flag definitions with display names

### 3. Discover mixin — `franklinwh_cloud/mixins/discover.py` [NEW]

```python
class DiscoverMixin:
    async def discover(self, tier: int = 1, category: str = None) -> DeviceSnapshot:
        """Full device discovery — returns structured DeviceSnapshot."""

    async def discover_flags(self) -> dict:
        """Quick feature flags only (~2 API calls)."""
```

### 4. CLI renderer — `franklinwh_cloud/cli_commands/discover.py` [MODIFY]

Refactored to render `DeviceSnapshot`:
- `run()` calls `client.discover(tier=verbosity)`
- `_render_tier1(snapshot)` — site + flags + mode
- `_render_tier2(snapshot)` — + batteries + accessories + warranty
- `_render_tier3(snapshot)` — + network + firmware + TOU + all flags
- `_render_flags_table(snapshot.flags)` — ✅/❌ table with V2L eligibility logic
- `_render_whats_missing(snapshot)` — ⚠/ⓘ diagnostics

### 5. CLI argument — `franklinwh_cloud/cli_commands/main.py` [MODIFY]

```
franklinwh-cli discover          # Tier 1 (default)
franklinwh-cli discover -v       # Tier 2
franklinwh-cli discover -vv      # Tier 3
franklinwh-cli discover --json   # Full JSON (always tier 3)
```

## V2L Eligibility Logic (Python)

```python
def is_v2l_eligible(country_id, sc_version, has_generator):
    if country_id == 3:       # AU
        return False          # AU SC (302) has no V2L port
    if sc_version == 2:       # SC V2 (204)
        return True           # V2L built-in
    if sc_version == 1 and has_generator:  # SC V1 (202) + Gen (201)
        return True           # V2L via CarSW port
    return False
```

## Feature Flags Table

```
┌──────────────────────┬──────┬────────────────────────────────┐
│ Feature              │ Flag │ Status                         │
├──────────────────────┼──────┼────────────────────────────────┤
│ Solar                │  ✅  │ PV1 + PV2                      │
│ TOU/Tariff           │  ✅  │ Configured                     │
│ PCS Power Control    │  ✅  │ Enabled                        │
│ Off-Grid             │  ❌  │ Grid-connected                 │
│ MPPT (DC-coupled)    │  ❌  │ aPower X — no MPPT             │
│ Three Phase          │  ❌  │ Single phase                   │
│ CT Split — Grid      │  ✅  │ Installed                      │
│ CT Split — PV        │  ❌  │ Not installed                  │
│ Smart Circuits       │  ✅  │ V1, 2 circuits                 │
│ V2L                  │  ❌  │ V1 SC needs Generator Module   │
│ Generator Module     │  ❌  │ Not installed                  │
│ Remote Solar (aPBox) │  ❌  │ Not connected                  │
│ aHub                 │  ❌  │ Not detected                   │
│ MAC-1 (MSA)          │  ❌  │ Not detected                   │
│ NEM Type             │  —   │ NEM 2.0                        │
│ SGIP (CA)            │  ❌  │ Not enrolled                   │
│ BB (HI)              │  ❌  │ Not enrolled                   │
│ VPP                  │  ❌  │ Not enrolled                   │
└──────────────────────┴──────┴────────────────────────────────┘
```

## Verification Plan

### Automated
```bash
cd /Users/davidhona/dev/franklinwh-cloud
python -m pytest tests/ -v --tb=short
```

### Manual
```bash
franklinwh-cli discover              # Tier 1
franklinwh-cli discover -v           # Tier 2
franklinwh-cli discover -vv          # Tier 3
franklinwh-cli discover --json       # Full JSON
```

### Programmatic
```python
from franklinwh_cloud import Client
snapshot = await client.discover(tier=2)
print(snapshot.flags)
print(snapshot.to_dict())
```
