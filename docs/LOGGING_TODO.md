# Logging TODO

> Best practices for disk hygiene, log levels, and rotation.

---

## Priority Overview

| # | Item | Priority | Type | Effort |
|---|------|----------|------|--------|
| 1 | Scheduler `stderr.log` rotation | 🔴 P1 | Quick win | 5 min |
| 2 | Downgrade `modes.py` chatty INFO → DEBUG | 🔴 P1 | Quick win | 5 min |
| 3 | Scheduler JSON log auto-prune | 🟠 P2 | Quick win | 10 min |
| 4 | `--log-file` RotatingFileHandler | 🟡 P3 | Long-term | 15 min |
| 5 | Downgrade remaining chatty INFO → DEBUG | 🟡 P3 | Cleanup | 15 min |
| 6 | Logging strategy docs | 🟢 P4 | Documentation | 20 min |

---

## 🔴 P1 — Quick Wins (Do Now)

### 1. Scheduler `stderr.log` — single file, grows forever

**Problem**: Every hourly run appends to one `stderr.log`. No rotation, no size limit.
At hourly with BMS delta logging, this grows ~5KB/hour = ~120KB/day = ~44MB/year.

**Quick fix**: Rotate by date — one stderr per day:
```bash
# In nettest-runner.sh, redirect to dated log:
exec 2>> "$LOG_DIR/stderr-$(date +%Y-%m-%d).log"
```

**Long-term**: Auto-prune stderr logs older than 30 days.

---

### 2. `modes.py` — 20+ INFO lines per mode switch

**Problem**: `set_mode` has ~20 `logger.info()` calls tracing every internal step.
These are **debug-level** statements, not user-facing info.

**Heavy hitters** (should be `logger.debug`):
```
modes.py:88   set_mode: Requested Operating Mode...
modes.py:97   set_mode: Validating requested...
modes.py:139  set_mode: Validated requested...
modes.py:140  set_mode: calling get_device_composite_info...
modes.py:141  set_mode: lookup MODE_MAP...
modes.py:146  set_mode: getDeviceCompositeInfo successful
modes.py:150  set_mode: currentWorkMode=...
modes.py:153  set_mode: deviceStatus=...
modes.py:161  set_mode: getGatewayTouListV2 successful
modes.py:164  set_mode: search for requestedOperatingMode...
modes.py:166  set_mode: Found target mode...
modes.py:169  set_mode: touId=...
modes.py:178  set_mode: Retrieved operating mode details...
modes.py:199  set_mode: Preparing to switch...
```

**Keep as INFO** (user-facing milestones only):
```
modes.py:232  "switching operating work mode to '...' for aGate ..."
modes.py:238  "Successfully switched operating mode to '...'"
```

**Keep as ERROR:**
```
modes.py:240  "failed switched operating mode..."
modes.py:266  "get_device_composite_info failed..."
modes.py:307  "get_gateway_tou_list failed..."
```

---

## 🟠 P2 — Soon

### 3. Scheduler JSON log auto-prune

**Problem**: `nettest-*.json` files accumulate. Hourly = 24/day = 720/month.

**Fix**: Add `--max-logs N` option (default 500) and prune on each run:
```python
# In nettest-runner.sh or _schedule_create:
# Delete logs older than 30 days
find "$LOG_DIR" -name "nettest-*.json" -mtime +30 -delete
```

Warning already shows at 100+ files — make it actionable.

---

## 🟡 P3 — When Time Permits

### 4. `--log-file` uses `FileHandler` — no rotation

**Problem**: `cli_output.py:159` — `FileHandler` appends forever.

**Fix**: Use `RotatingFileHandler` with sensible defaults:
```python
from logging.handlers import RotatingFileHandler
file_handler = RotatingFileHandler(
    log_file, maxBytes=5_000_000, backupCount=3  # 5MB × 3
)
```

---

### 5. Other chatty INFO → DEBUG candidates

| File | Lines | Current | Should be |
|------|-------|---------|-----------|
| `power.py` | 65, 80, 82, 97, 105 | INFO | DEBUG (internal params) |
| `account.py` | 125, 128 | INFO | DEBUG (session details) |
| `storm.py` | 104, 114, 128 | INFO | INFO ✓ (user actions) |
| `devices.py` (BMS) | new delta logs | INFO | INFO ✓ (investigation data) |

---

## 🟢 P4 — Documentation

### 6. Logging strategy doc

Document in `docs/LOGGING.md`:
- Logger name: `franklinwh_cloud`
- Verbosity mapping: `-v` = INFO, `-vv` = DEBUG, `-vvv` = all
- `--trace` selective module tracing
- `--api-trace` compact API call summaries
- `--log-file` file output
- Scheduler log locations and rotation
- Log level guidelines: when to use INFO vs DEBUG vs WARNING
