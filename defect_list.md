# Defect & Feature Queue

Per AP-12 Change Management Policy — all items queued here before execution.

## Open

### S2 — High

| ID | Area | Description | Reported |
|----|------|-------------|----------|

### S3 — Medium

| ID | Area | Description | Reported |
|----|------|-------------|----------|
| FEAT-MODE-DYNAMIC-LIST | Mixins | `get_gateway_tou_list` returns gateway-specific modes (e.g. `peak` instead of `Time of Use`). Client should retrieve and use this dynamic list instead of hardcoded `OPERATING_MODES`. | 2026-03-26 |

### S4 — Low

| ID | Area | Description | Reported |
|----|------|-------------|----------|
| FEAT-AUTH-ABSTRACT | Client / API Core | Auth strategy pattern (PasswordAuth → OAuthAuth → ApiKeyAuth) — ready for OAuth-day when FranklinWH introduces token-based auth | 2026-03-21 |
| FEAT-DOCS-OPENAPI | Docs | Generate OpenAPI/Swagger spec from HAR capture of full app lifecycle | 2026-03-21 |

---

## Resolved

| ID | Area | Description | Fixed In | Commit |
|----|------|-------------|----------|--------|
| DEF-STATS-DOUBLE-SLASH | Mixins | `get_power_details` and `get_power_by_day` prepend `/hes-gateway/` to `self.url_base` causing 404 from CloudFront due to double slash `//` | 2026-03-26 | `pending` |
| DEF-CLIENT-URL-BASE | Client / API Core | 34 methods used hardcoded `DEFAULT_URL_BASE` instead of `self.url_base`; base URL not configurable | 2026-03-21 | `2b55919` |
| DEF-AUTH-LOGIN-TYPE | Client / API Core | `_login()` hardcoded `type: 1` (installer) — should be `type: 0` (user) for homeowner accounts | 2026-03-21 | `cba2b6d` |
| DEF-MODE-GETMODE | Mixins | `get_mode()` chained 3 API calls without error handling; refactored with try/except, separate variables, proper error returns | 2026-03-20 | `b86cdc6` |
| DEF-MODE-SUPPRESS | Mixins | `suppress_params` typo — `get_unread_count()` and `set_mode()` silently ignored flag | 2026-03-20 | `9dc7f52` |
| DEF-MODE-ALARMS | Mixins | `currentAlarmVOList` stringified then iterated over characters | 2026-03-20 | `9dc7f52` |
| DEF-MODE-CRASH | CLI Commands | `franklinwh-cli mode` crashes with NoneType when `get_mode()` fails | 2026-03-20 | `7dd2702` |
| DEF-MODE-NAME | CLI Commands | `mode` command displays `self_consumption` instead of `Self-Consumption` | 2026-03-20 | `76d341e` |
| DEF-SITE-DETAIL | Mixins | `get_site_detail()` sent `siteId=''` — `siteId` not in `fetcher.info`; fixed to resolve via `get_home_gateway_list()` + gateway serial match | 2026-03-25 | `09e1fdd` |
| FEAT-CLI-DISCOVER-VERBOSE | CLI Commands | Enhanced `discover` with 3 verbosity tiers, feature flags, Hybrid A+B JSON catalog | 2026-03-23 | `multiple` |
| DEF-CLIENT-TIMEOUT | Client / API Core | `httpx.TimeoutException` propagated raw; now caught in `__post`/`__get` → `ApiTimeoutError` with friendly CLI message | 2026-03-25 | `f38d456` |
| FEAT-AUTH-CLI-OPTION | CLI Commands | `franklinwh-cli --installer` flag passes `LOGIN_TYPE_INSTALLER` to `TokenFetcher` | 2026-03-25 | `f38d456` |
