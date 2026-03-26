# FranklinWH Cloud: Backward Compatibility Analysis (`v0.4.x`)
**Date:** March 27, 2026
**Subject:** `franklinwh-cloud` Refactor vs Legacy `richo/franklinwh-python` Implementations

## Executive Summary
The structural refactoring of `client.py` into distinct functional classes (`mixins/modes.py`, `mixins/tou.py`, etc.) introduced **strict type checking** and **constrained string enums** to prevent invalid HTTP payloads. However, this architectural shift silently broke backward compatibility for downstream developers (e.g., Home Assistant integrators) who relied on the legacy library’s forgiving type coercions. 

We have identified three critical vectors of backward incompatibility, their upstream impact, and the remediations performed to restore legacy alignments.

---

## 1. Operating Mode Casting (`set_mode`)
### Legacy Behaviour (`client.py`)
The original `set_mode(mode)` function accepted extremely loose identifiers. A developer could pass `1`, `"1"`, `"TIME_OF_USE"`, or `"time_of_use"`, and the library would dynamically map it to the underlying Modbus Integer (`1`).

### Refactored Behaviour (`mixins/modes.py` prior to `v0.4.1`)
The refactor introduced physical `match case` structural blocks that completely removed `int` and semantic string equivalencies.
* `client.set_mode(1)` ❌ raising `InvalidOperatingModeOption`
* `client.set_mode("time_of_use")` ❌ raising `InvalidOperatingModeOption`

### Resolution (Restored in `v0.4.1`)
The `validate_mode` block was retrofitted. We mapped string normalization (`validate_mode.lower()`) across extensive `OR` cases implicitly binding legacy types:
```python
case "1" | "time_of_use" | "timeofuse" | "tou":
    requestedOperatingMode = TIME_OF_USE
```
**Status: ✅ 100% Backward Compatible Restored.**

---

## 2. Dispatch Identification Strings (`set_tou_schedule`)
### Legacy Behaviour (`client.py`)
When developers pushed new scheduling modes, the `touMode` parameter freely supported both string aliases (`"CUSTOM"`) and Dispatch IDs (`8` or `"8"` for `charge_from_grid`). 

### Refactored Behaviour (`mixins/tou.py` prior to `v0.4.1`)
The library attempted to sanitize user input using `DISPATCH_CODES.get(touMode)`. Because `DISPATCH_CODES` relies on **integer keys**, passing `"8"` caused standard dictionary lookups to fail, ejecting a traceback exception to the user.

### Resolution (Restored in `v0.4.1`)
The validator has been patched to cleanly intercept and test `int()` castability prior to dictionary lookup, explicitly checking `DISPATCH_CODES.get(int(touMode))` when natural dict matching fails. Integrators can now pass `"8"` without causing a crash.
**Status: ✅ 100% Backward Compatible Restored.**

---

## 3. The `updateTouModeV2` Blackhole Constraints
### Legacy Behaviour (`client.py`)
The legacy library relied exclusively on `/hes-gateway/terminal/tou/updateTouModeV2` to perform fast mode changes. Null payload variables (e.g. absent `soc` or `enableStorm` values) were silently ignored by the V1 server APIs.

### The Spring Boot Cloud Migration
Unbeknownst to the legacy developers, FranklinWH updated the Cloud Java Spring Boot environment:
1. **`@NotNull` Constraints**: V2 APIs actively crash with `400 Bad Request` if ANY parameter is omitted or passed as literally `"None"`.
2. **V2 aGate Deprecation**: V2 gateways simply *reject* `updateTouModeV2` HTTP transitions into `TIME_OF_USE`. They demand fully-formed schedule payload replacements via `set_tou_schedule()`.

### Resolution (Handled in `v0.4.1`)
We could not revert to the legacy API here because the Cloud server literally rejects it now. Instead, we:
* Overhauled `modes.py` to assertively strip all optional nulls before posting the HTTP URL string.
* Defaulted missing dependencies (Storm mode inherits `1`, basic electricity targets inherit default variables instead of dumping blanks). 
* FAH integrations are being updated to utilise `set_tou_schedule()` to transition V2 aGates safely.
**Status: ✅ Sever-side compatibility patched.**

---

**Conclusion**: The core library routing constraints have been relaxed to accept legacy type signatures natively, while the downstream payload generators have been heavily tightened to dodge the undocumented Java `@NotNull` server regressions that brought down the upstream automations.
