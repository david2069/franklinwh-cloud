# Region Quirks & Accessory Behaviour

> **Living Document** — Update this file as new regional attributes, API behaviour differences, or accessory details are discovered. No code changes required to add new entries; only `device_catalog.json` changes are needed.

---

## Why This Exists

The FranklinWH Cloud API was designed for the **US market** (split-phase 120/240V, NEM 2.0/3.0, SGIP/BB incentive programmes). Australian deployments use the same backend but with a different hardware configuration and grid standard. This causes:

- Several API fields to return `null` for AU systems — **this is expected, not a bug**
- US-specific feature flags to appear in API responses but be meaningless for AU
- Accessory details that are API-opaque regardless of region

---

## Region Reference

| Attribute | 🇺🇸 United States (country_id: 2) | 🇦🇺 Australia (country_id: 3) |
|-----------|----------------------------------|------------------------------|
| Grid Standard | UL9540 / IEEE 1547 | AS4777 / Clean Energy Council |
| Voltage | 120/240V split-phase | 230V single-phase / 415V 3-phase |
| Max Export | No federal limit (state/utility varies) | ~10 kW (CEC guideline; DNSP/state may differ) |
| V2L Capable | ✅ (Gen 1+Gen Module, or Gen 2 built-in) | ❌ (AU hardware has no V2L port) |
| NEM Type | ✅ NEM 2.0 / NEM 3.0 applicable | ❌ Not applicable (different FiT model) |
| SGIP / BB / JA12 | ✅ California / Hawaii incentive programmes | ❌ (returns `null` — expected) |

---

## AU-Specific API Null Fields

These fields are returned by the API but are always `null` or `false` for Australian systems. They are **not errors** — they are US-programme fields not applicable to AU:

| Field | US Meaning | AU Behaviour |
|-------|-----------|--------------|
| `sgipEntrance` | SGIP enrollment (CA) | Always `false` |
| `bbEntrance` | Battery Bonus (HI) | Always `false` |
| `ja12Entrance` | JA12 code compliance (CA) | Always `false` |
| `isJoinJA12` | JA12 enrolled | Always `false` |
| `sdcpFlag` | Sustainable development (CA) | Always `false` |
| `nemType` | NEM 2.0 or 3.0 | Always `null` |
| `programmeList` | VPP/incentive list | Always `null` or `[]` |

> The `franklinwh-cli discover` command suppresses these for AU users — they will not appear in CLI output.

---

## Accessory Quirks — What the API Can and Cannot Tell You

Many accessory details are **not exposed by the Cloud API**. This table documents what's available and what requires alternative methods.

### aHub

| Attribute | API Available? | Notes |
|-----------|---------------|-------|
| Presence | ✅ `ahubAddressingFlag` | Boolean flag in feature flags |
| Count | ✅ `scCount` / accessory list | |
| Firmware version | ❌ | Not in any Cloud API response |
| Serial number | ❌ | Not returned |
| Individual port status | ❌ | |

**Known firmware versions:** `1.0.3`, `1.1.0`  
**Workaround:** aHub firmware is accessible via Modbus registers (15xxx range) if on local network.

---

### aPBox Digital I/O

| Attribute | API Available? | Notes |
|-----------|---------------|-------|
| Presence | ✅ accessoryList type 251 | |
| Digital input states | ✅ `getApBoxStatus` MQTT | |
| Digital output states | ✅ `getApBoxStatus` MQTT | |
| Firmware version | ❌ | Not returned |
| Serial number | ❌ | Not returned |

---

### Smart Circuits

| Attribute | API Available? | Notes |
|-----------|---------------|-------|
| Version (V1/V2) | ✅ `scVersion` | |
| Count | ✅ `scCount` | |
| Circuit names | ✅ | |
| V2L port present | ✅ | V1 AU: always false |
| Merged mode (240V) | ✅ | |
| Firmware version | ❌ | Not in Cloud API |
| Individual circuit current | ❌ | Use Modbus or FranklinWH app |
| Thermal status | ❌ | |

**AU note:** AU Smart Circuits V1 has no V2L port. V2L is a US-only feature.

---

### Meter Adapter Controller (MAC-1 / MSA)

| Attribute | API Available? | Notes |
|-----------|---------------|-------|
| Model | ✅ `msa_model` via `get_site_software_info` | |
| Serial number | ✅ `msa_serial` | |
| Firmware version | ❌ | Not returned |
| RSD switch state | ❌ | Physical inspection required |
| Meter readings | ❌ | |

**Note:** aPower S only. Has a Rapid Shutdown (RSD) switch not exposed by the Cloud API.

---

### Split-CT (200A)

| Attribute | API Available? | Notes |
|-----------|---------------|-------|
| Grid CT installed | ✅ `ct_split_grid` flag | |
| PV CT installed | ✅ `ct_split_pv` flag | |
| Calibration needed | ✅ `needCtTest` flag | |
| Firmware version | ❌ | |
| Serial number | ❌ | |
| Calibration values | ❌ | |

---

### Generator Module

| Attribute | API Available? | Notes |
|-----------|---------------|-------|
| Presence | ✅ accessoryList type 3 | |
| Version (V1/V2) | ✅ | |
| Brand / model | ❌ | Not in Cloud API |
| kW rating | ❌ | Set at install time |
| Runtime hours | ❌ | |

---

## Contributing New Quirks

All region and accessory data lives in [`franklinwh_cloud/const/device_catalog.json`](../franklinwh_cloud/const/device_catalog.json) under `region_quirks` and `accessory_quirks` keys.

To add a new finding:
1. Edit the JSON directly — no Python code changes needed
2. Add your discovery to the relevant section in this document
3. Submit a PR with both the JSON and doc changes

Please include:
- What the field is named in the API response
- What value it returns (null, false, specific value)
- What region/model you observed it on
- Your aGate model and country_id if relevant
