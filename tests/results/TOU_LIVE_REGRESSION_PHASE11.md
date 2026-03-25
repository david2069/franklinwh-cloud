# TOU Live Regression Testing Results (Session 11)

**Objective**: Safely execute a live configuration mutation against the FranklinWH Cloud to verify the legacy `set_tou_schedule` and modern `set_tou_schedule_multi` logic.

## Summary of Execution
The `tmp_live_tou.py` regression suite connected to the live aGate and successfully performed the following sequence:
1. Backed up the original live schedule via `get_tou_dispatch_detail`.
2. Applied a multi-season configuration via `set_tou_schedule_multi`.
3. Applied the legacy configuration via `set_tou_schedule` (CUSTOM fallback).
4. Restored the original schedule by injecting the V1 snapshot backup payload into `saveTouDispatch`.

## Core Findings & Bug Fixes
During testing, the SDK crashed on the live system. Analysis revealed two hidden API restrictions which silently rejected mutations, both of which have now been mitigated:

1. **Gateway Serial Case-Sensitivity (`181 Operation without permission`)**
   The FranklinWH API aggressively enforces uppercase string matching on the Gateway ID (e.g. `A02F` vs `a02f`). Supplying a lowercase serial fails validation upstream, returning `181` instead of a 404. 
   **Fix**: The core `Client` instantiation `__init__` was patched to strictly enforce `.upper()` on all Gateway Serials.

2. **Spring Framework `@NotBlank` Exceptions (`400 must not be blank`)**
   The V2 template extraction occasionally generates empty strings `""` for metadata such as `electricCompany` or `countryEn`. The Cloud API drops these connections with a `400` validation error as opposed to tolerating `null`.
   **Fix**: The template dispatch stubs (`save_template` parameters) were updated to coerce empty fields to explicitly fallback (e.g., `template.get("name") or "Custom"`).

## Verification Outcomes

| Test Phase | Validated Endpoint | Target Result | Outcome |
|:---|:---|:---|:---|
| Baseline Backup | `getTouDispatchDetail` | Successfully snapshotted the config | ✅ PASS |
| Multi-Season Test | `set_tou_schedule_multi` | Delivered multi-season JSON array | ✅ PASS |
| Legacy Generic Test | `set_tou_schedule` | Handled backwards compatibility wrapper | ✅ PASS |
| Configuration Restore | `saveTouDispatch` | Original configuration fully reinstated | ✅ PASS |

The live execution successfully completed end-to-end and left the gateway in its original working configuration.
