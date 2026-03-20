# Defect & Feature Queue

Per AP-12 Change Management Policy — all items queued here before execution.

## Open

### S2 — High

*No items*

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
| DEF-CLIENT-URL-BASE | Client / API Core | 34 methods used hardcoded `DEFAULT_URL_BASE` instead of `self.url_base`; base URL not configurable | 2026-03-21 | `2b55919` |
| DEF-AUTH-LOGIN-TYPE | Client / API Core | `_login()` hardcoded `type: 1` (installer) — should be `type: 0` (user) for homeowner accounts | 2026-03-21 | `cba2b6d` |
| DEF-MODE-GETMODE | Mixins | `get_mode()` chained 3 API calls without error handling; refactored with try/except, separate variables, proper error returns | 2026-03-20 | `b86cdc6` |
| DEF-MODE-SUPPRESS | Mixins | `suppress_params` typo — `get_unread_count()` and `set_mode()` silently ignored flag | 2026-03-20 | `9dc7f52` |
| DEF-MODE-ALARMS | Mixins | `currentAlarmVOList` stringified then iterated over characters | 2026-03-20 | `9dc7f52` |
| DEF-MODE-CRASH | CLI Commands | `franklinwh-cli mode` crashes with NoneType when `get_mode()` fails | 2026-03-20 | `7dd2702` |
| DEF-MODE-NAME | CLI Commands | `mode` command displays `self_consumption` instead of `Self-Consumption` | 2026-03-20 | `76d341e` |
