# `get_entrance_info()` Field Coverage Analysis

> Analysis date: 2026-05-02  
> Source: live AU gateway (`franklinwh-cli raw get_entrance_info`)  
> Scope: `support` snapshot, `support --info`, `support --info --diag`, `schema` CLI

---

## Live field values (AU gateway, 2026-05-02)

```json
{
  "sgipEntrance":          0,
  "bbEntrance":            0,
  "pcsEntrance":           1,
  "ja12Entrance":          0,
  "tariffSettingFlag":     true,
  "sdcpFlag":              false,
  "solarFlag":             true,
  "gridFlag":              true,
  "globalGridDischargeMax": -1.0,
  "globalGridChargeMax":   -1.0,
  "slSettingFlag":         1,
  "needCtTest":            false,
  "gridFeedMaxFlag":       2,
  "gridMaxFlag":           2,
  "backupSolution":        null,
  "gridFeedMax":           null,
  "gridMax":               null,
  "peakDemandGridMax":     null,
  "bbDischargePower":      null,
  "bonusEnable":           null,
  "ahubAddressingFlag":    null,
  "chargingPowerLimited":  false
}
```

> [!IMPORTANT]
> **`gridFeedMax` and `gridMax` are `null` in `get_entrance_info()` on this AU gateway.**
> The authoritative values come from `get_power_control_settings()` (`gridFeedMax: 10.0`,
> `gridMax: -1.0`). This confirms the decision to source grid limits from
> `get_power_control_settings()` rather than `get_entrance_info()`.

---

## Field-by-Field Coverage Map

| Field | Meaning | `support` snapshot | `support --info` | `support --info --diag` | `schema` |
|-------|---------|:-:|:-:|:-:|:-:|
| `sgipEntrance` | SGIP scheme eligibility (US/CA) | ✅ `programmes.sgip` | ✅ flags | ✅ Feature Flags | ❌ |
| `bbEntrance` | Backup Battery scheme eligibility | ✅ `programmes.bb` | ✅ flags | ✅ Feature Flags | ❌ |
| `pcsEntrance` | PCS power control enabled | ✅ `programmes.pcs_enabled` | ✅ readiness | ✅ Feature Flags | ❌ |
| `ja12Entrance` | JA12 grid compliance | ✅ `programmes.ja12` | ✅ flags | ✅ Feature Flags | ❌ |
| `sdcpFlag` | Smart Device Control Program | ✅ `programmes.sdcp` | ✅ flags | ✅ Feature Flags | ❌ |
| `tariffSettingFlag` | TOU schedule configured | ⚠️ via `tou_status` only | ✅ readiness check | ✅ Feature Flags | ❌ |
| `solarFlag` | Solar PV connected to aGate ports | ❌ not in snapshot | ✅ flags.solar | ✅ Solar flag | ❌ |
| `gridFlag` | Grid connected / operations valid | ❌ not in snapshot | ✅ `gl.connected` | ✅ Grid-Tied flag | ❌ |
| `globalGridDischargeMax` | Global export power cap | ⚠️ superseded by `pcs` | ⚠️ partial | ❌ | ❌ |
| `globalGridChargeMax` | Global charge power cap | ⚠️ superseded by `pcs` | ⚠️ partial | ❌ | ❌ |
| `slSettingFlag` | Smart Load setting flag | ❌ | ❌ | ❌ | ❌ |
| `needCtTest` | CT calibration required | ❌ (captured, not displayed) | ❌ | ❌ | ❌ |
| `gridFeedMaxFlag` | Feed-in limit type/mode flag | ❌ | ⚠️ in `gl.feed_max_flag` | ❌ | ⚠️ `gridFeedMaxFlag` in `GRID_LIMITS_SCHEMA` |
| `gridMaxFlag` | Import limit type/mode flag | ❌ | ⚠️ in `gl.import_max_flag` | ❌ | ⚠️ `gridMaxFlag` in `GRID_LIMITS_SCHEMA` |
| `backupSolution` | Backup solution type | ❌ | ⚠️ in `gl.backup_solution` | ❌ | ❌ |
| `gridFeedMax` | Export max kW (⚠️ null AU) | ❌ (use `get_power_control_settings`) | ⚠️ in `gl.feed_max_kw` | ❌ | ✅ via `pcs` |
| `gridMax` | Import max kW (⚠️ null AU) | ❌ (use `get_power_control_settings`) | ⚠️ in `gl.import_max_kw` | ❌ | ✅ via `pcs` |
| `peakDemandGridMax` | Peak demand grid cap | ❌ | ⚠️ in `gl.peak_demand_max_kw` | ❌ | ✅ via `pcs` |
| `bbDischargePower` | Backup Battery discharge power | ❌ | ⚠️ in `gl.bb_discharge_power` | ❌ | ✅ via `pcs` |
| `bonusEnable` | Bonus/incentive programme flag | ❌ | ❌ | ❌ | ❌ |
| `ahubAddressingFlag` | aHub connected | ❌ not in snapshot | ✅ `flags.ahub_detected` | ✅ aHub flag | ❌ |
| `chargingPowerLimited` | aPower 2+ charge derating active | ❌ **gap** | ❌ **gap** | ❌ **gap** | ❌ |

**Key:**  
✅ = captured and displayed  ⚠️ = captured but not displayed / partial  ❌ = not present

---

## Gap Summary

### 🔴 Critical Gaps (actionable, have clear meaning)

| Field | Gap | Why it matters |
|-------|-----|---------------|
| **`chargingPowerLimited`** | Not in any CLI output | aPower 2+ feature: derate charging power to prevent tripping the utility service breaker. The `support --info --diag` derating block checks `chargingPowerLimited` from `get_power_cap_config_list()` (per-device), not this flag from `get_entrance_info()`. This field is the **gateway-level** derating enable flag and is never surfaced in any CLI output. |
| **`solarFlag`** | Not in `support` snapshot | If `False`, solar PV is not connected to the aGate ports — directly-connected solar functions (relays, MPPT, split-CT) are invalid. The flag is only read in the discover mixin (`flags.solar`) for `--info` tree building; it is absent from the `support` snapshot `programmes` block. |
| **`gridFlag`** | Not in `support` snapshot | If `False`, grid battery operations (grid charge, grid export) cannot be performed. Captured in discover mixin as `gl.connected` but absent from the `support` snapshot entirely. |
| **`tariffSettingFlag`** | Not in `programmes` | Currently only surfaced via `tou_status.tariffSettingFlag` (from `get_gateway_tou_list()`). It also appears in `get_entrance_info()` and is used in `--info` readiness checks, but is absent from the `support` snapshot `programmes` block. Having it in two places is fine; missing from `programmes` means `--compare` can't show it alongside scheme flags. |

### 🟡 Minor Gaps (captured but silent)

| Field | Where captured | Where missing |
|-------|----------------|---------------|
| `needCtTest` | `discover.py` → `snap.flags.need_ct_test` | Not displayed anywhere. A `True` value indicates CT calibration is required — field engineering relevance. |
| `ahubAddressingFlag` | `discover.py` → `snap.flags.ahub_detected` | In `--info --diag` Feature Flags, but **absent from `support` snapshot** `programmes` block. |
| `slSettingFlag` | Not captured anywhere | Smart Load setting mode; unclear semantics, likely internal. Low priority. |
| `bonusEnable` | Not captured anywhere | Incentive/bonus programme. Only relevant in markets with active bonus schemes. |
| `backupSolution` | `discover.py` → `gl.backup_solution` | Captured in discover model, never displayed. |
| `gridFeedMaxFlag` / `gridMaxFlag` | In discover model (`gl.feed_max_flag`, `gl.import_max_flag`) and `GRID_LIMITS_SCHEMA` | Limit mode type flag (2 = ?). Not decoded/documented. |

### ✅ Correctly Handled

| Field | Decision | Rationale |
|-------|----------|-----------|
| `gridFeedMax` / `gridMax` | Sourced from `get_power_control_settings()` | Returns `null` from `get_entrance_info()` on AU gateways; `get_power_control_settings()` is authoritative and always populated. |
| `globalGridChargeMax` / `globalGridDischargeMax` | Sourced from `get_power_control_settings()` | Both APIs return the same values; `pcs` is the authoritative source. |
| `peakDemandGridMax` / `bbDischargePower` | In `GRID_LIMITS_SCHEMA` via `pcs` | Better source than entrance info. |

---

## Field Semantic Notes

### `solarFlag`
```
"solarFlag": true
```
`True` = solar PV is connected to aGate's physical PV ports (i.e., "directly connected" topology).  
`False` = no solar on aGate ports — functions like MPPT, solar relay state, and solar-side CT are invalid.  
This is **not** the same as "solar is generating" — it is a **hardware topology flag** set at installation.

### `gridFlag`
```
"gridFlag": true
```
`True` = gateway is grid-tied and grid battery operations (charge from grid, export to grid) are valid.  
`False` = off-grid configuration — grid charge/export commands should not be sent.  
This flag gating is critical before issuing TOU dispatch commands to avoid hardware errors.

### `chargingPowerLimited` ← **Most Important Gap**
```
"chargingPowerLimited": false
```
aPower 2 and higher models support a firmware-enforced charge power derating mechanism.  
When `True`, the system limits AC charging power to prevent the aggregate draw from  
exceeding the utility service panel amperage rating (preventing breaker trips).  
The actual limit comes from the per-device `maxChargingPower` in `get_power_cap_config_list()`.  
This feature does **not exist** on original aPower / aPower X hardware.

The `support --info --diag` code already checks `cfg.get("chargingPowerLimited")` on
a per-device basis from the derating config, but the **gateway-level entrance flag**  
(`get_entrance_info().chargingPowerLimited`) is never surfaced anywhere in CLI output.

### `tariffSettingFlag`
```
"tariffSettingFlag": true
```
Appears in **both** `get_entrance_info()` and `get_gateway_tou_list()`.  
Currently only consumed from the TOU list in the `support` snapshot (`tou_status.tariffSettingFlag`).  
This is fine functionally, but creates a minor inconsistency:  
the `programmes` snapshot block (sourced from entrance info) is missing it, while `tou_status` has it.

### `slSettingFlag`
```
"slSettingFlag": 1
```
Unknown semantics. Present in entrance info but never documented or used in the library.  
Likely related to Smart Load settings. Low priority until confirmed.

### `gridFeedMaxFlag` / `gridMaxFlag`
```
"gridFeedMaxFlag": 2,
"gridMaxFlag": 2
```
These appear to be mode/type indicators for the corresponding limit fields.  
Value `2` is present on this AU gateway but no enum mapping has been documented.  
Both are in `GRID_LIMITS_SCHEMA` but the integer is displayed raw — no label decode.

---

## Recommended Actions

| Priority | Action |
|----------|--------|
| 🔴 **High** | Add `chargingPowerLimited` to `support` snapshot `programmes` block + display in Grid & Schemes section |
| 🔴 **High** | Add `solarFlag` and `gridFlag` to `support` snapshot `programmes` block — these are prerequisites for validating dispatch commands |
| 🟡 **Medium** | Add `ahubAddressingFlag` to `support` snapshot `programmes` block (already in discover; should be in snapshot for `--compare` parity) |
| 🟡 **Medium** | Add `tariffSettingFlag` to `programmes` snapshot block (supplement, not replace, `tou_status` copy) |
| 🟡 **Medium** | Add `needCtTest` to `support` snapshot + display as a warning when `True` |
| 🟢 **Low** | Decode `gridFeedMaxFlag` / `gridMaxFlag` enum values once semantics are confirmed |
| 🟢 **Low** | Investigate `slSettingFlag` semantics |
| 🟢 **Low** | Add `bonusEnable` if bonus/incentive markets become active |

---

## Related Files

| File | Role |
|------|------|
| `franklinwh_cloud/mixins/account.py` | Defines `get_entrance_info()` REST call |
| `franklinwh_cloud/mixins/discover.py` | Consumes entrance info in Tier 1 discovery → `snap.flags` + `snap.grid_limits` |
| `franklinwh_cloud/discovery.py` | `DeviceFlags` dataclass — defines `charging_power_limited`, `need_ct_test`, `ahub_detected`, `solar`, `tariff_configured` |
| `franklinwh_cloud/cli_commands/support.py` | `programmes` snapshot block (lines ~688-720) — consumes subset of entrance info |
| `franklinwh_cloud/cli_commands/support.py` | `run_info()` — consumes entrance info for `--info --diag` Feature Flags display |
| `franklinwh_cloud/cli_commands/schema.py` | `GRID_LIMITS_SCHEMA` — covers `get_power_control_settings()` fields (not entrance info directly) |
