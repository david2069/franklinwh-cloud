# Defect & Feature Queue

Per AP-12 Change Management Policy — all items queued here before execution.

## Open

### S2 — High

| ID | Area | Description | Reported |
|----|------|-------------|----------|
| DEF-MODE-GETMODE | Mixins | `get_mode()` chains 3 API calls without error handling; fragile to any single failure | 2026-03-20 |

### S3 — Medium

*No items*

### S4 — Low

| ID | Area | Description | Reported |
|----|------|-------------|----------|
| DEF-CLIENT-TIMEOUT | Client / API Core | `_post()` has `timeout=30` but no graceful recovery on timeout | 2026-03-20 |

---

## Resolved

| ID | Area | Description | Fixed In | Commit |
|----|------|-------------|----------|--------|
| DEF-MODE-SUPPRESS | Mixins | `suppress_params` typo — `get_unread_count()` and `set_mode()` silently ignored flag | 2026-03-20 | `9dc7f52` |
| DEF-MODE-ALARMS | Mixins | `currentAlarmVOList` stringified then iterated over characters | 2026-03-20 | `9dc7f52` |
| DEF-MODE-CRASH | CLI Commands | `franklinwh-cli mode` crashes with NoneType when `get_mode()` fails | 2026-03-20 | `7dd2702` |
| DEF-MODE-NAME | CLI Commands | `mode` command displays `self_consumption` instead of `Self-Consumption` | 2026-03-20 | `76d341e` |
