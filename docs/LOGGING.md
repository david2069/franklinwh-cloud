# Logging Strategy

How logging works in the `franklinwh-cloud` library and CLI.

## Logger Hierarchy

All library logging uses:

```
franklinwh_cloud          ← root library logger
franklinwh_cloud.mixins.* ← per-module (modes, tou, power, etc.)
```

Third-party:
```
httpx                     ← HTTP client (enabled at -vv)
```

## CLI Verbosity Flags

| Flag | Level | What you see |
|------|-------|--------------|
| *(none)* | WARNING | Only warnings and errors |
| `-v` | INFO | Mode switches, API milestones |
| `-vv` | DEBUG | Internal params, request URLs, response details |
| `-vvv` | DEBUG (all) | Everything including httpx wire-level |

### Selective Tracing

```bash
# Trace specific modules only
franklinwh-cli --trace modes,tou status

# Compact API call summaries
franklinwh-cli --api-trace status
```

Available modules: `stats`, `modes`, `tou`, `storm`, `power`, `devices`, `account`, `client`, `all`

## File Logging

```bash
franklinwh-cli --log-file debug.log -vv status
```

Uses `RotatingFileHandler`: **5 MB** max, **3 backups** (`debug.log`, `debug.log.1`, `debug.log.2`, `debug.log.3`).

## Log Level Guidelines

| Level | Use for |
|-------|---------|
| `logger.debug()` | Internal params, request/response details, API URLs, flow tracing |
| `logger.info()` | User-visible milestones (mode switch start/success, BMS data summary) |
| `logger.warning()` | Abnormal but recoverable (deviceStatus ≠ Normal, tariffSettingFlag, lost BMS response) |
| `logger.error()` | Operation failures (API errors, mode switch failures) |

**Rule of thumb**: If the user doesn't need to see it at `-v`, it's DEBUG.
