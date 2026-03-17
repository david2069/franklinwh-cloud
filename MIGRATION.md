# franklinwh-cloud Refactoring — FEM Agent Handoff

> **Purpose**: Summary of all changes to the `franklinwh-cloud` library that may impact the `franklinwh-energy-manager` (FEM) project. Includes what changed, what's backward compatible, and what needs attention.

## TL;DR — Impact Summary

| Area | Breaking? | FEM Action Required? |
|------|-----------|---------------------|
| `from franklinwh import Client, TokenFetcher` | ✅ No change | None |
| `from franklinwh import Stats, Current, Totals, GridStatus` | ✅ No change | None |
| `from franklinwh import *Exceptions` | ✅ No change | None |
| `from franklinwh.const import ...` | ✅ No change | None |
| `from franklinwh.client import Client, TokenFetcher` | ✅ No change | None |
| All `client.*` API methods | ✅ No change | None |
| `client.get_metrics()` | 🆕 New method | Optional — can add monitoring |
| `franklinwh/cli.py` | ⚠️ Rewritten | FEM has stale copy in `lib/` |
| `franklinwh/models.py` | 🆕 New file | Already re-exported via `__init__` |
| `franklinwh/exceptions.py` | 🆕 New file | Already re-exported via `__init__` |
| `franklinwh/metrics.py` | 🆕 New file | Optional new feature |
| `franklinwh/mixins/*` | 🆕 New (internal) | Transparent — Client inherits all |

> [!IMPORTANT]
> **No breaking changes for FEM.** All existing imports work unchanged. The `Client` class has the same API surface — methods were just moved to mixin classes that it inherits from.

---

## What Changed (Commits)

```
c0d50cd  feat: rewrite CLI — subcommands, debug tracing, metrics
8aaad4f  test: expand live API tests to 33, fix 4 pre-existing bugs
9ff2d56  test: improve live tests — franklinwh.ini support
065f9f3  refactor: modularize client.py into 7 domain-specific mixins
f9f7308  feat: add ClientMetrics instrumentation
```

---

## 1. client.py Modularization (Non-Breaking)

`client.py` was reduced from **3,610 → 690 lines** by extracting methods into 7 mixin classes:

```
franklinwh/mixins/
├── stats.py      ← get_stats, get_runtime_data, get_power_by_day, ...
├── modes.py      ← get_mode, set_mode, get_mode_info, ...
├── tou.py        ← get_tou_info, set_tou, get_gateway_tou_list, ...
├── storm.py      ← get_weather, get_storm_settings, ...
├── power.py      ← get_grid_status, get_power_control_settings, ...
├── devices.py    ← get_device_info, get_bms_info, ...
└── account.py    ← siteinfo, get_warranty_info, get_alarm_codes_list, ...
```

**How it works**: `Client` inherits from all mixins:
```python
class Client(StatsMixin, ModesMixin, TOUMixin, StormMixin, 
             PowerMixin, DevicesMixin, AccountMixin):
```

**FEM impact**: **None.** `Client` still has every method as before. Example:
```python
# This still works exactly the same:
from franklinwh import Client, TokenFetcher
client = Client(fetcher, gateway)
stats = await client.get_stats()       # → StatsMixin
mode = await client.get_mode()         # → ModesMixin
tou = await client.get_tou_info(2)     # → TOUMixin
```

---

## 2. New Files (Non-Breaking)

| File | Purpose | FEM Import Needed? |
|------|---------|-------------------|
| `franklinwh/models.py` | `Stats`, `Current`, `Totals`, `GridStatus`, `empty_stats` | No — already re-exported from `franklinwh/__init__.py` |
| `franklinwh/exceptions.py` | 9 exception classes | No — already re-exported |
| `franklinwh/metrics.py` | `ClientMetrics` class | Optional |
| `franklinwh/cli_output.py` | CLI formatting utilities | No |
| `franklinwh/cli_commands/*.py` | CLI subcommand modules | No |

---

## 3. API Metrics (New Feature)

`Client` now tracks API call metrics automatically:

```python
metrics = client.get_metrics()
# Returns dict with:
# {
#   "total_api_calls": 42,
#   "avg_response_time_s": 0.85,
#   "calls_by_method": {"GET": 35, "POST": 7},
#   "calls_by_endpoint": {"hes-gateway/terminal/...": 5, ...},
#   "total_errors": 0,
#   "total_retries": 1,
#   "uptime_s": 3600.0,
# }
```

**FEM opportunity**: Could expose metrics via MQTT or the admin API for monitoring FranklinWH Cloud API health.

---

## 4. Bug Fixes Found During Live Testing

| Bug | Location | Fix |
|-----|----------|-----|
| `_pos_get` → `_get` typo | `account.py:get_notification_settings` | Fixed — was crashing with `AttributeError` |
| `gatewayOd` → `gatewayId` typo | `stats.py:get_power_details` | Fixed — was sending wrong param name |
| `data['result']` crashes | `stats.py`, `account.py` (3 methods) | Changed to `data.get('result', data)` |

> [!WARNING]
> If FEM has its own copy of these methods (e.g., in `lib/franklinwh/`), it should resync to pick up these fixes.

---

## 5. CLI Rewrite (FEM has stale copy)

The FEM project has a stale copy at `lib/franklinwh/cli.py` (the old 728-line version).

**Old CLI** (728 lines):
- Monolithic `main()` with nested functions
- `--email`/`--password`/`--gateway` all required
- `--command discover|mode|...` dispatch

**New CLI** (230 lines + 5 command modules):
```bash
franklinwh-cli status              # live system overview
franklinwh-cli discover            # device enumeration  
franklinwh-cli mode                # get/set mode
franklinwh-cli tou --dispatch      # TOU schedules
franklinwh-cli raw <method>        # 33 API methods
franklinwh-cli metrics             # API metrics

# Debug tracing
franklinwh-cli status -v           # INFO level
franklinwh-cli status -vvv         # full DEBUG
franklinwh-cli status --trace tou  # only TOU mixin debug
```

**FEM action**: The stale `lib/franklinwh/cli.py` should be **deleted** — it references the old import structure and has broken code paths. The new CLI is installed as `franklinwh-cli` via `pyproject.toml` console_scripts entry.

---

## 6. FEM Files Importing from franklinwh

Verified these FEM files — **all imports are backward compatible**:

| FEM File | Imports | Status |
|----------|---------|--------|
| `lib/franklinwh/endpoints.py` | `Client, TokenFetcher` | ✅ Works |
| `src/services/cloud_bypass.py` | `TokenFetcher, Client, GridStatus` | ✅ Works |
| `src/services/mqtt_registry.py` | `franklinwh.const.devices` | ✅ Works |
| `src/services/mqtt_publisher.py` | `franklinwh.const.modes.RUN_STATUS` | ✅ Works |
| `src/services/modbus_control.py` | `franklinwh.types.BatteryCommand` | ✅ Works |
| `src/services/stats_mapper.py` | Uses `Stats` object from `get_stats()` | ✅ Works |
| `lib/franklinwh/cli.py` | Old copy — 728-line version | ⚠️ Stale, delete |
| `lib/franklinwh/const/test_fixtures.py` | TOU test schedules | ✅ Works |

---

## 7. Resync Instructions

```bash
cd /path/to/franklinwh-energy-manager

# Update the library
pip install -e /path/to/franklinwh-cloud

# Delete stale CLI copy  
rm lib/franklinwh/cli.py

# Verify imports still work
python -c "from franklinwh import Client, TokenFetcher, Stats, GridStatus; print('OK')"

# Optional: add metrics to FEM
# In your cloud polling loop:
#   metrics = client.get_metrics()
#   logger.info(f"API metrics: {metrics}")
```

---

## 8. Test Coverage

| Suite | Count | Status |
|-------|------:|--------|
| Unit tests (mocked) | 74 | ✅ All pass |
| Live API tests | 33 | ✅ 32 pass, 1 skipped |
| Metrics tests | 14 | ✅ All pass |
| **Total** | **107** | ✅ |
