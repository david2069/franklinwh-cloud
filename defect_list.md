# Defect & Feature Queue

Per AP-12 Change Management Policy — all items queued here before execution.

## Open

### S2 — High

| ID | Area | Description | Reported |
|----|------|-------------|----------|

### S3 — Medium

| ID | Area | Description | Reported |
|----|------|-------------|----------|
| FEAT-MODE-DYNAMIC-LIST | Mixins | `get_gateway_tou_list` returns gateway-specific modes (e.g. `peak` instead of `Time of Use`). Client should retrieve and use this dynamic list instead of hardcoded `OPERATING_MODES`. **⏸ ON HOLD — client impact assessment required.** | 2026-03-26 |
| FEAT-METRICS-PYTHON-METHOD-COUNTERS | Metrics / ClientMetrics | `calls_by_method` stores HTTP verbs (`GET`/`POST`), not Python wrapper names. FHAI Sankey/dual-table dashboard requires per-Python-method call counts (e.g. `get_stats_v2: 900`, `set_mode: 15`). **Proposed fix:** add `calls_by_python_method: dict` field to `ClientMetrics`; populate via a lightweight decorator (`@track_method_calls`) applied to public mixin methods at class definition time. `calls_by_method` (HTTP verbs) must remain unchanged — it is a stable public field. The new field is additive only. FHAI agent to update `api_metrics_tab_v2.js` Sankey + table to use `calls_by_python_method` once published. | 2026-04-13 |

> **Design Notes (FEAT-MODE-DYNAMIC-LIST — ON HOLD)**
>
> The mobile app pattern: on startup it fetches the gateway's active mode list dynamically via `get_gateway_tou_list`, then only presents modes that are supported by that specific hardware configuration (e.g. AU grid may not expose `peak`, commercial gateways may expose additional modes).
>
> **Breaking change risk:** Downstream clients (HA integrator, automations) that call `set_mode("peak")` or compare against hardcoded `OPERATING_MODES` keys will break silently if the gateway returns a different mode name than expected.
>
> **Open design questions before execution:**
> 1. **Graceful degradation**: If a client requests a mode not in the gateway's dynamic list, should we: (a) raise `InvalidModeException`, (b) silently no-op with a warning, or (c) attempt the set and let the API reject it?
> 2. **Mode name normalisation**: The gateway returns display strings (e.g. `"Time of Use"`, `"Self-Consumption"`). Do we expose these raw, or map them to the existing canonical slug keys (`tou`, `self_consumption`)?
> 3. **Caching**: The mode list rarely changes (hardware config). Should it be fetched once on `Client.__init__`, or lazily on first `get_mode()`/`set_mode()` call?
> 4. **Emulator support**: The emulator needs a `get_gateway_tou_list` synthetic endpoint before live testing can safely proceed.
> 5. **Documentation**: [COMPLETED] Downstream UI constraint handling and fallback states are now fully specified in `docs/OPERATING_MODES_GUIDE.md`.


### S4 — Low

| ID | Area | Description | Reported |
|----|------|-------------|----------|
| FEAT-AUTH-ABSTRACT | Client / API Core | Auth strategy pattern (PasswordAuth → OAuthAuth → ApiKeyAuth) — ready for OAuth-day when FranklinWH introduces token-based auth | 2026-03-21 |
| FEAT-DOCS-OPENAPI | Docs | Generate OpenAPI/Swagger spec from HAR capture of full app lifecycle | 2026-03-21 |

---

## Resolved

| ID | Area | Description | Fixed In | Commit |
|----|------|-------------|----------|--------|
| DEF-BMS-STATE-SWAP | Constants / CLI | Fixed inverted BMS Charging/Discharging states and enforced dict lookup. | Unreleased | `27cfaf4` |
| DEF-BLANK-STATS-PASSTHROUGH | Mixins / Models | Added `is_stale` caching to `get_stats()` to prevent API glitches sending zero-value payloads | Unreleased | `5b29114` |
| DEF-GRID-STATE-ENUM | Models / Mixins / CLI / FHAI | Replaced `grid_outage: bool` with `GridConnectionState` enum (four states: `CONNECTED`, `OUTAGE`, `SIMULATED_OFF_GRID`, `NOT_GRID_TIED`). Startup cache for `NOT_GRID_TIED` via `get_entrance_info()`. Dual-gate on `main_sw[0]==0` OR `offgridreason!=null` before calling `get_grid_status()` — handles firmware relay reporting lag (~5–10s after go-off-grid). Live-verified: `CONNECTED → SIMULATED_OFF_GRID → CONNECTED` cycle. Full docs in `API_COOKBOOK.md §Grid Connection State`. | Unreleased | `76debfb` |
| DEF-TOU-LOG-NOISE | Mixins | `get_tou_info()` emitted INFO-level logs on every poll cycle, flooding HA system logs | Unreleased | `pending` |
| DEF-RELAY-INV | CLI / Mixin | Relay states inverted in `diag` and `discover`: firmware encodes `1=OPEN`, code displayed `1` as CLOSED. Fixed `fmt_relay`, `main_sw` index comment, `bool(val)→not bool(val)` storage, `stats.grid_relay2` attr path, and `ON/OFF→OPEN/CLOSED` labels. | Unreleased | `pending` |
| DEF-GRID-PROFILE-DYNAMIC-ID | Mixins | `get_grid_profile_info(2)` hardcoded `systemId=0` returning empty payloads; CLI crashed with `UnboundLocalError` due to string `requestType` | Unreleased | `pending` |
| FEAT-TEST-INTEGRATION | Tests | Live gateway integration test suite (read-only endpoints) with JSON schema validation against `franklinwh_openapi.json` | Unreleased | `pending` |
| FEAT-TEST-API-PROXY | Tests | FastAPI-based local proxy emulator (`emulator/`) intercepting requests and returning synthetic responses for offline structural testing | Unreleased | `pending` |
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
| DEF-CLI-TOU-PRICE | CLI Commands | `franklinwh-cli tou` and `--price` do not display actual pricing rates; should default to zero if none | 2026-03-27 | |
