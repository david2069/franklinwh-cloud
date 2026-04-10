# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **Emulator Foundation (`FEAT-TEST-API-PROXY`)** — Created top-level `emulator/` directory with a fully decoupled FastAPI proxy server (`emulator/main.py`) that intercepts `franklinwh-cloud` library requests and returns synthetic responses. Includes request-logging middleware simulating `@NotNull` Java Spring Boot constraints. Documented in `emulator/README.md` with instructions for routing `franklinwh-cli` against `localhost:8080` for offline structural failure experiments.
- **`emulator` dependency group** — Added `fastapi[standard]>=0.110.0` and `uvicorn` as an isolated optional dependency group in `pyproject.toml` (`pip install -e ".[emulator]"`), keeping emulator deps fully decoupled from the core library and test suite.
- **Live JSON schema validation (`FEAT-TEST-INTEGRATION`)** — Added `_assert_live_schema(path, method, payload)` helper to `tests/test_live.py`. Dynamically loads `docs/franklinwh_openapi.json` and validates live API payloads against the formal spec using `jsonschema`, providing automatic detection of undocumented upstream API mutations.

### Fixed
- **`DEF-GRID-PROFILE-DYNAMIC-ID`** — `get_grid_profile_info(requestType=2)` was hardcoding `systemId=0`, returning empty `{}` payloads from the API. The method now auto-fetches the active profile `currentId` from `requestType=1` when `systemId` is not supplied. Also fixed `UnboundLocalError` caused by the CLI passing `requestType` as a string — now cast to `int` before branching logic.
- **`DEF-TOU-LOG-NOISE`** — `get_tou_info()` was emitting two `logger.info()` calls on every poll cycle (`option = {option}` and `returning current=..., next=...`). Both downgraded to `logger.debug()` to eliminate INFO-level spam in Home Assistant system logs.
- **`DEF-DYNAMIC-MODE-REVERT`** — Reverted unauthorised `FEAT-MODE-DYNAMIC-LIST` partial implementation. `get_operating_mode_name()` was silently calling `get_gateway_tou_list()` on every `get_stats()` poll and returning dealer-customised strings (e.g. `"peak"`) which broke downstream clients comparing against canonical mode names like `"Time of Use"`. Reverted to stable `OPERATING_MODES` dict lookup. `FEAT-MODE-DYNAMIC-LIST` remains ON HOLD pending approved design — see `defect_list.md`.
- **`DEF-RELAY-INV`** — Relay states in `diag` and `discover` were inverted: the firmware encodes `1=OPEN, 0=CLOSED` but `fmt_relay` displayed `1` as `● CLOSED`. Fixed in `diag.py` (corrected comment + swapped display strings), `mixins/discover.py` (primary relay `main_sw` index comment corrected to `[Grid, Gen, Solar]`; storage changed from `bool(val)` to `not bool(val)` for both primary and extended relays; `stats.grid_relay2` attr path corrected to `stats.current.grid_relay2`), and `cli_commands/discover.py` (relay display changed from `ON/OFF` to `● CLOSED / ○ OPEN`). Verified live against `main_sw=[1,0,1]` (Grid=OPEN, Gen=CLOSED, Solar=OPEN) and cmdType 211 extended relay fields.
- **`DEF-BMS-STATE-SWAP`** — `BMS_STATE` in `states.py` had `6` mapped to `"Discharging"` and `7` to `"Charging"`, inverting the firmware ground truth (`V10R01B04D00`, captured 2026-02-23). Fixed to `6="Charging"`, `7="Discharging"` per the invariant `bms_work = run_status + 5`. Added `BMS_WORK_OFFSET = 5` constant and `DCDC_STATE` map (mirrors `bms_work`, standby at `4`) to prevent consumers using `RUN_STATUS` as a wrong-dict lookup for `bms_work` values. Both exported from `franklinwh_cloud.const`.
- **`DEF-ELECTRICAL-METRICS-LAYER`** — `get_stats()` now accepts `include_electrical: bool = False`. When `True`, calls `get_power_info()` (cmdType 211) internally and populates `grid_voltage1/2`, `grid_current1/2`, `grid_frequency`, `grid_set_frequency`, `grid_line_voltage` (correctly ÷10 scaled from raw integer), `generator_voltage`, and extended relays (`grid_relay2`, `black_start_relay`, `pv_relay2`, `bfpv_apbox_relay`) on `Current`. Scaling logic lives in the library — consumers call `get_stats(include_electrical=True)` on their slow cadence and read pre-scaled fields.
- **`DEF-GRID-STATUS-SEMANTIC`** *(superseded by DEF-GRID-STATE-ENUM below)* — `Current.grid_status: GridStatus` replaced with `grid_outage: bool`. `GridStatus.NORMAL` was semantically wrong for permanently-islanded systems (`offgridreason=0` means "no outage detected", not "grid is present"). `grid_outage=True` only when firmware reports an active grid loss (`offGridFlag` or `offgridreason > 0`). `GridStatus` enum retained for `set_grid_status()` command path only. All CLI consumers updated: `Connected` / `Outage` labels replace `NORMAL` / `DOWN` / `OFF`.
- **`DEF-GRID-STATE-ENUM`** — `grid_outage: bool` removed and replaced with `grid_connection_state: GridConnectionState` (four-state enum). The bool model conflated `Not-Grid-Tied` and `Simulated-Off-Grid` into `False`, making it impossible to distinguish deliberately-islanded systems from grid-tied ones. The enum provides unambiguous state for all topologies:

  | State | `.value` | Condition |
  |-------|----------|-----------|
  | `CONNECTED` | `"Connected"` | `main_sw[0]==1` (relay CLOSED) |
  | `OUTAGE` | `"Outage"` | `offGridFlag==1` (firmware-authoritative) |
  | `SIMULATED_OFF_GRID` | `"SimulatedOffGrid"` | `main_sw[0]==0` AND `offgridState==1` |
  | `NOT_GRID_TIED` | `"NotGridTied"` | `gridFlag==False` from `get_entrance_info()` |

  **Detection strategy:** `NOT_GRID_TIED` cached once at startup via `get_entrance_info()` (never re-polled). `get_grid_status()` called only when `main_sw[0]==0` OR `offgridreason!=null` — zero overhead on connected systems. Dual-gate handles firmware API reporting lag (~5–10s) where `offgridreason` is set before `main_sw` updates (mechanical relay settling — expected vendor behaviour).

  **Live-verified** (2026-04-10): Full `CONNECTED → SIMULATED_OFF_GRID → CONNECTED` cycle via `TestLiveGridConnectionState`. `offgridState=1`, `main_sw[0]=0`, and `GridConnectionState.SIMULATED_OFF_GRID` all confirmed.

  **Breaking change:** `Current.grid_outage: bool` removed. Consumers migrate to `stats.current.grid_connection_state` (enum) or `.value` (str). See `docs/API_COOKBOOK.md §Grid Connection State` for full annotated examples.

  **Files changed:** `models.py`, `mixins/stats.py`, `client.py`, `cli_commands/status.py`, `cli_commands/monitor.py`, `cli_commands/diag.py`, `cli_commands/support.py`, `__init__.py`, `tests/test_live.py`.




## [0.4.6] - 2026-03-31

### Fixed
- **Facade Envelope Unwrap Defect** — Fixed a `KeyError: 0` in `FranklinWHCloud.select_gateway()`. The facade's internal `get_home_gateway_list()` auto-discovery proxy was failing to unwrap the `dict` API envelope before attempting to extract the `["result"]` gateway array list.

## [0.4.5] - 2026-03-31

### Added
- **Urgent Testing Policy (AP-13)** — Adopted the AP-13 `live_test_protocol.md` policy. The strict ban on Negative Authentication Testing against live APIs now natively permits failure traces *only if* strictly routed through explicitly declared `DUMMY_EMAIL` payloads to preserve real user connectivity while allowing rigorous 401/403 header integration tests.

### Fixed
- **Facade Auto-Discovery Defect** — Fixed a fatal `ValueError` in `FranklinWHCloud.select_gateway()` where the wrapper hallucinated that the login `info` payload natively bundled a `gatewayList`. The facade now cleanly instantiates a temporary API proxy to explicitly call `get_home_gateway_list()` to establish its binding. Associated test mocked fixtures were also scrubbed of hallucinated gateway lists to restore parity with reality.

## [0.4.4] - 2026-03-30

### Added
- **AI Onboarding Workflow** — Created `onboard.md` slash-command to establish a formal Zero-Trust initialization sequence for all AI Agents, enforcing the reading of policies and inflight defects before code execution.
- **Incident Reporting** — Authored `INCIDENT_001_AUTH_BREAKAGE.md` systematically documenting the downstream fragmentation caused by undocumented AI refactoring, and enforcing the `"explicit declaration of break change"` authorization policy in `CONTRIBUTING.md` and `AGENT.md`.
- **Legacy Authentication Facade** — Introduced `FranklinWHCloud(email, password)` wrapper backwards-compatibility layer orchestrating `TokenFetcher` and `Client` bindings natively, preventing the need to rewrite basic automation scripts.
- **Dual Architecture Documentation** — Formalised `README.md` and `docs/getting-started.md` structurally designating the Legacy Facade as the "preferred" quick-start method, while reserving the decoupled Token architecture for Future-Proof OAuth integrations.

## [0.4.3] - 2026-03-28

### Added
- **Telemetry Opt-In Engine** — Formalized tracking privacy policy in `TELEMETRY.md` and injected robust Scarf Edge PoP integration in `README.md`. Shipped an optional asynchronous HTTP PostHog dispatcher in `telemetry.py` running gracefully on a background daemon to capture zero-friction client executions.
- **Strict Headers Customization** — Officially documented HTTP identity injection rules inside `API_COOKBOOK.md` to safely permit Home Assistant API integrations.
- **Unified Accessory Translations** — Refactored deeply-nested proprietary hardware binary schemas natively into english output maps. Arrays mapping directly resolved in `discover -v`: Generator (`genStat`), V2L (`v2lRunState`), Power Control Systems (`pe_stat`), BMS (`bms_work`), Smart Circuits (`Sw1Mode`), and Remote Sensors (`doStatus` / `di`).
- **API Mapping Documentation** — Generated `API_ENDPOINTS_MAPPING.md` via AST to fully document mapping of library methods to Cloud Endpoints. Added to MkDocs Wiki explicitly.
- **Hardware Diagnostics** — Added `get_power_cap_config_list` (nameplate capacity/models) and `get_device_run_log_list` (alarm/error logs) natively to the codebase pipeline.
- **CLI TOU Filtering** — `franklinwh-cli tou --current` strictly filters output table string representations to actively display only the currently active season blocks.
- **Hardware Detection** — `franklinwh-cli accessories` dynamically queries `peHwVersion` per-serial from the cloud hardware dictionary to correctly print precise aPower model names (e.g. 'aPower X') implicitly.
- **`FEAT-SUPPORT-PAYLOAD`** — Unified the `franklinwh-cli support --json` payload exporter to natively append the raw integer strings for `v2lRunState`, `genStat`, and Smart Circuit parameters (`SwMerge`, `CarSwConsSupEnable`, `Sw1Name`), along with a full mapping of `hardware_registry_dump` capturing auxiliary devices like `aHub`.
- **Payload Architecture Documentation** — Authored `docs/DISCOVER_VS_SUPPORT.md` mapping out the rigid use-case boundaries between human-readable bindings (`discover`) versus raw firmware troubleshooting dumps (`support`), preventing UI integration anti-patterns.

### Fixed
- **`DEF-CLI-TOU-SCOPE`** — Patched execution crash preventing the run of `tou --current` by successfully passing the unpacked `show_current` parameter downstream into the `tou.py` scope mapping.
- **`DEF-TEST-FIXTURE`** — Fixed `test_live_mode.py` violently crashing PyTest by defining the missing `live_credentials` fixture in `conftest.py`. Unauthenticated suites correctly SKIP the integration testing suite safely now.
- **`DEF-CLI-TOU-PRICE`** — `franklinwh-cli tou --price` now renders the active pricing tier by default, explicit $0.00 for empty rates, and supports `--all` flag.
- **`DEF-STATS-DOUBLE-SLASH`** — fixed double-slash URL 404 error when calling `get_power_details` and `get_power_by_day`

## [0.4.2] — 2026-03-27

### Added
- **`TEST-BACKWARD-COMPAT`** — Formalized and restored the original `richo/franklinwh` Python type mappings inside API setters. Methods like `set_mode` and `set_tou_schedule` now universally accept un-typed semantic string aliases (e.g. `'time_of_use'`) and raw integer casts, preventing downstream 400 errors across existing Integrations. See `docs/BACKWARD_COMPATIBILITY.md` for the executive impact analysis.

### Fixed
- **`DEF-SET-MODE-NULLID`** — Intercepted a secondary Java `@NotNull` crash where an un-customized aGate natively returns `touId: null`. The query string parser now explicitly injects a default `0` (`currendId=0`) rather than completely dropping the parameter key to satisfy upstream Spring Boot validators.

## [0.4.1] — 2026-03-27

### Added
- **`TEST-TRACEABILITY`** — Created `tests/test_live_mode.py` and `tests/test_cli_mode.py` pushing the `mode` subsystem branch coverage above 96%, strictly enforced by `run_and_record.sh` local gates prior to upstream deployment. Results permanently archived in `tests/results/`.

### Fixed
- **`DEF-SET-MODE-NULL`** — Fixed critical `400 Bad Request` server-side HTTP rejection caused by Python injecting literal string `"None"` values into the `/hes-gateway/terminal/tou/updateTouModeV2` query string (e.g. `stromEn=None`). Optional backend parameters are now gracefully stripped before dispatch.
- **`DEF-CLI-MODE-STRING`** — Fixed `franklinwh-cli mode --set` crashing with an `TypeError` when dictionary integer keys (`1`, `2`, `3`) were passed into a native string list `.join()`.
- **`FEAT-HOTFIX-401`** — Downstream `AssertionError` collision natively trapped: HTTP API wrappers `_post` and `_get` now accurately intercept unresolvable `{ "code": 401 }` and `{ "code": 10009 }` authentication limits out of `instrumented_retry()`. Instead of crashing downstream loops, the core dynamically raises a trappable `TokenExpiredException`.

## [0.4.0] — 2026-03-26

### Added
- **Published to PyPI** — `pip install franklinwh-cloud` ([pypi.org/project/franklinwh-cloud](https://pypi.org/project/franklinwh-cloud))
- **Automated publish pipeline** — GitHub Actions Trusted Publisher (OIDC) workflow triggers on version tags
- **GitHub issue templates** — structured bug report and feature request forms with FranklinWH-specific fields (region, aGate model, component, redacted log sections)
- **Troubleshooting Guide** (`docs/TROUBLESHOOTING.md`) — 7 sections: login/auth, network connectivity, device config, inaccurate metrics, CLI inspection, collecting diagnostics, masking vs redacting PII
- **About & Disclaimer** — added to `docs/index.md` and `README.md` explaining unofficial nature, intended API users, educational-only purpose, and AS-IS no-fitness-warranty
- **`calculate_expected_earnings`** registered in raw CLI (`franklinwh-cli raw calculate_expected_earnings`)
- **`FEAT-AUTH-CLI-OPTION`** — `franklinwh-cli --installer` flag sets `LOGIN_TYPE_INSTALLER` for certified installer accounts; default remains homeowner (`LOGIN_TYPE_USER`)
- **`FEAT-REGION-QUIRKS`** — `device_catalog.json` v1.1.0: `region_quirks` (AU/US grid standard, V2L, NEM, max export, known API null fields) + `accessory_quirks` (aHub, aPBox, MAC-1, Split-CT, Generator, Smart Circuits: API exposes vs opaque, detection, known firmware). `franklinwh-cli discover -v` now shows ⚠ API opaque hints per accessory. `docs/REGION_QUIRKS.md` living document added.
- **`FEAT-TOU-MULTISEASON`** — `set_tou_schedule_multi(strategy_list)` — accepts per-season/per-day-type schedules matching the HAR fixture format, validates all 12 months covered. CLI: `franklinwh-cli tou --multi-season seasons.json` (accepts `{strategyList: [...]}` or bare array).
- **`FEAT-TOU-CURRENT-PRICE`** — `get_current_tou_price()` — matches current month → season, weekday/weekend → day type, HH:MM → active block; returns `buy_rate`, `sell_rate`. Supports `option=1` for isolated dictionary output. CLI: `franklinwh-cli tou --price` w/ `--active-only` JSON flag.
- **`FEAT-CLIENT-TIMEOUT`** — Catch global `httpx.TimeoutException` instances and cast as predictable `FranklinWHTimeoutError` to elegantly prevent CLI stack-trace vomit during poor connectivity events / outage failovers.
- **`FEAT-AUTH-ABSTRACT`** — Auth strategy pattern extracting rigidly coupled TokenFetcher loops into polymorphic `BaseAuth`, `PasswordAuth`, and `TokenAuth` (raw JWT injection) schemas. (Retains `TokenFetcher` alias for downstream backwards compatibility).
- **`FEAT-SMART-CIRCUITS`** — Deep Hardware Integration bridging physical `SwTimeEn` arrays (V2 firmwares) against string explicit minute mappings (V1 firmwares) natively inside the `SmartCircuitDetail` Python dataclass. Includes `set_smart_circuit_load_limit` API setter, gracefully intercepting blank properties without polluting standard `franklinwh-cli sc` execution loops.
- **Environment Bootstrapping** — Added `docs/HOWTO_PYTHON.md` exhaustively documenting `deadsnakes`, OSX `Homebrew` strategies, and OS-agnostic Pip environments matching `franklinwh-modbus` architectures.

### Fixed
- **`tWaveTypeId` → `waveType`** in API Cookbook — corrected 3 instances to match the actual field name used by `set_tou_schedule`
- **`DEF-SITE-DETAIL`** — `get_site_detail()` passed `siteId=''` because `fetcher.info` does not contain `siteId`; now resolves via `get_home_gateway_list()` matched on gateway serial number

## [0.3.0] — 2026-03-23

### Added
- **Enhanced `franklinwh-cli discover` with 3 verbosity tiers** `FEAT-CLI-DISCOVER-VERBOSE`
  - `discover` (Tier 1): site identity, aGate model/firmware, battery summary, 20 feature flags (✅/❌), operating state, diagnostics (~6 API calls)
  - `discover -v` (Tier 2): + per-aPower firmware (FPGA/DCDC/INV/BMS/bootloader/thermal), SC config (version/count/names/V2L), warranty (expiry/throughput/installer), grid profile, programmes, relays (~12 calls)
  - `discover -vv` (Tier 3): + full aGate firmware (IBG/SL/AWS/App/Meter), NEM type, PTO date, site detail (~20 calls)
  - `discover --json`: full JSON output for scripting and diffing (always Tier 3)
- **Two-layer architecture**: `client.discover(tier=N) → DeviceSnapshot` — Python API + CLI renderer `FEAT-CLI-DISCOVER-VERBOSE`
- **`DeviceSnapshot` dataclass** with 10 categories: site, agate, batteries, flags, accessories, grid, warranty, electrical, programmes `FEAT-CLI-DISCOVER-VERBOSE`
- **`const/device_catalog.json`** — Hybrid A+B JSON hardware catalog with model registry, compatibility matrix, V2L rules, programme definitions `FEAT-CLI-DISCOVER-VERBOSE`
- **V2L eligibility logic**: V1 SC + Gen = eligible; V2 SC = built-in; AU = no V2L `FEAT-CLI-DISCOVER-VERBOSE`
- **55 new API fields surfaced** from 13 static APIs (see `docs/API_FIELD_REGISTRY.md`) `FEAT-CLI-DISCOVER-VERBOSE`
- `docs/DISCOVER_IMPLEMENTATION_PLAN.md` — implementation plan
- `docs/DEVICE_CATALOG_DESIGN.md` — Hybrid A+B design decision
- `docs/API_FIELD_REGISTRY.md` — complete field registry (120 fields, 13 APIs)
- `franklinwh-cli mode` — now shows reserve SoC for active mode and SoC summary for all modes
- `franklinwh-cli status` — reserve SoC displayed in Operating Mode section
- `get_all_mode_soc()` — new API method returning reserve SoC, min/max, and active flag for all modes
- `get_mode()` — now includes `soc`, `minSoc`, `maxSoc` in return dict
- `MODBUS_TIME_OF_USE`, `MODBUS_SELF_CONSUMPTION`, `MODBUS_EMERGENCY_BACKUP` — Modbus TCP work mode constants (oldIndex mapping) `FEAT-CONST-MODBUS-MODES`
- `modbusWorkMode` enum and `CLOUD_TO_MODBUS_MODE`/`MODBUS_TO_CLOUD_MODE` bidirectional conversion dicts `FEAT-CONST-MODBUS-MODES`
- `franklinwh-cli bms` — Battery Management System inspection (cell voltages, temperatures, SoC/SoH)
- `franklinwh-cli diag` — System diagnostics report
- `franklinwh-cli tou` — Full dispatch schedule with seasons, day types, pricing tiers
- `franklinwh-cli tou --set` — Set TOU dispatch: single window, full-day, or custom JSON file
- `franklinwh-cli tou --next` — Show current/next dispatch with remaining time (HH:MM:SS)
- `franklinwh-cli metrics` — now does a probe call so it shows real data including CloudFront edge
- `docs/TOU_SCHEDULE_GUIDE.md` — TOU API reference with mermaid diagrams and code examples
- GitHub Issues for public issue tracking (#1–#6)
- AP-12 Change Management Policy and enhanced Release Policy with traceability rules
- `LOGIN_TYPE_USER` (0) and `LOGIN_TYPE_INSTALLER` (1) constants for `appUserOrInstallerLogin` endpoint `FEAT-AUTH-INSTALLER`
- `login_type` parameter on `TokenFetcher`, `login()`, and `_login()` — supports both homeowner and installer accounts `FEAT-AUTH-INSTALLER`
- `franklinwh-cli support` — point-in-time system snapshot for troubleshooting with save, redact, analyze, compare, and scoped diff `FEAT-SUPPORT-SNAPSHOT`
- `franklinwh-cli support --analyze` — connectivity and WiFi health analysis engine detecting DHCP failures, 4G fallback, disabled interfaces `FEAT-SUPPORT-ANALYZE`
- `franklinwh-cli support --compare FILE --scope` — diff previous snapshot (scopes: all, network, software, power) `FEAT-SUPPORT-COMPARE`
- `get_apower_info` added to `franklinwh-cli raw` method list `FEAT-RAW-APOWER`
- **20 new API endpoints from HAR capture** — tariff management, billing/savings, device/site `FEAT-HAR-ENDPOINTS`
  - TOU: `get_utility_companies`, `get_tariff_list`, `get_tariff_detail`, `get_tou_detail_by_id`, `get_custom_dispatch_list`, `get_bonus_info`, `get_vpp_tip`, `get_recommend_dispatch_list`, `calculate_expected_earnings`, `apply_tariff_template`
  - Billing: `get_electric_data`, `get_charge_history`, fixed `get_benefit_info` URL and params
  - Device: `get_site_detail`, `get_device_detail`, `get_device_overall_info`, `get_personal_info`
- `franklinwh-cli raw` — stdin JSON pipe for methods needing structured payloads `FEAT-RAW-STDIN`
- **MkDocs Material docs site** — auto-deployed to GitHub Pages on push `FEAT-DOCS-SITE`
- `docs/SCHEDULING.md` — platform-specific scheduling HOWTO (launchd, cron, systemd, Docker)
- `docs/LOGGING.md` — logging strategy (verbosity flags, tracing, rotation, level guidelines)
- `docs/TOU_SCHEDULE_GUIDE.md` — TOU entrance flags prerequisite section
- **System Readiness panel** in `discover` — at-a-glance ✅/⚠ status for aGate, aPower, PCS, TOU, Grid, Solar `FEAT-CLI-DISCOVER-VERBOSE`
- **3-state off-grid detection** — simulated (`get_grid_status` offgridSet), permanent (`offGirdFlag`), detected outage (`offgridreason`) `FEAT-CLI-DISCOVER-VERBOSE`
- **Extended relays** in Tier 2 — Grid 2, Black Start, Solar PV 2, aPBox (from `get_stats` powerInfo) `FEAT-CLI-DISCOVER-VERBOSE`
- **TOU dispatch status** in Tier 2 — `tou_status` and `tou_dispatch_count` for backend health monitoring `FEAT-CLI-DISCOVER-VERBOSE`
- **Region-filtered flags** — MAC-1/MSA, NEM, SGIP, BB, JA12 only shown for US systems `FEAT-CLI-DISCOVER-VERBOSE`
- **Accessory model/SKU** from catalog lookup in accessories section `FEAT-CLI-DISCOVER-VERBOSE`
- **TOU Setup Workflows** — two mermaid diagrams in `docs/TOU_SCHEDULE_GUIDE.md`: template-based (7-step app wizard) and direct dispatch (5-step CLI) `FEAT-TOU-WORKFLOWS`
- **10 TOU tariff management endpoints** added to `API_REFERENCE.md` with HTTP methods and WRITE warnings `FEAT-TOU-WORKFLOWS`
- **Architecture diagrams** — two distinct transport paths: Cloud API (sendMqtt format) and Modbus TCP (`franklinwh_modbus`, SunSpec/Raw, LAN port 502) `FEAT-DOCS`
- **Thank You page** — `docs/thank-you.md` acknowledging Richo's `franklinwh-python` and `homeassistant-franklinwh` with contributor links `FEAT-DOCS`
- **Device Discovery** section in mkdocs nav — implementation plan, catalog design, field registry `FEAT-DOCS`
- **API method count** updated to 70 (from 59) across all documentation `FEAT-DOCS`

### Fixed
- **AU Smart Circuits reported 3 circuits** — now uses catalog hardware truth (AU model 302 = 2 circuits) `DEF-DISCOVER-AU-SC`
- **Relay labels inconsistent** — standardised to Grid Relay 1, Generator Relay, Solar PV Relay 1 `DEF-DISCOVER-RELAYS`
- **AU single-phase aGates showed split-phase L2** — suppressed L2 voltage/current for AU/NZ, labelled L1 as just "Voltage"/"Current" `DEF-DISCOVER-AU-PHASE`
- **MAC-1 detection too late** — now detected in Tier 1 from `get_device_info` `msaInstallStartDetectTime` field `DEF-DISCOVER-MAC1`
- **Login type was wrong** — hardcoded `type: 1` (installer) instead of `type: 0` (user); now defaults to `LOGIN_TYPE_USER` (0) `DEF-AUTH-LOGIN-TYPE`
- **`url_base` inconsistency** — 34 methods used hardcoded `DEFAULT_URL_BASE` instead of configurable `self.url_base`; now all methods respect the `url_base` parameter passed to `Client()` `DEF-CLIENT-URL-BASE`
- `franklinwh-cli mode` — resilient to `get_mode()` API failures; falls back to `get_all_mode_soc()` for SoC summary `DEF-MODE-CRASH`
- `franklinwh-cli mode` — displays proper mode name (`Self-Consumption`) instead of snake_case (`self_consumption`) `DEF-MODE-NAME`
- `suppress_params`/`suppress_gateway` — standardised kwarg spelling across `_get()`, `_post()`, and all callers; `get_unread_count()` and `set_mode()` were silently ignoring the flag due to typo mismatch `DEF-MODE-SUPPRESS`
- `currentAlarmVOList` in `get_mode()` — was stringified then iterated over characters; now operates on the original list `DEF-MODE-ALARMS`
- `get_mode()` refactored — was fragile (3 chained API calls, `res` reuse, scope leaks, set-not-dict error return); now uses separate variables per API call, try/except, optional unread count, proper error dicts `DEF-MODE-GETMODE`
- **All CLI commands display wrong power units** — API returns kW but monitor/status/discover/diag displayed as W (#7)
- Monitor power bar and direction thresholds used watt-scale values (±50) instead of kW-scale (±0.05)
- Monitor CDN line now shows distribution count instead of overwhelming hash list
- Monitor crash when edge tracker `cache_hit_rate` returns string instead of float (#2)
- Status command now warns when runtimeData is empty instead of silently showing zeros
- **Broken logger in `get_stats()`** — missing f-prefix meant offGridFlag/offGridReason variables were never interpolated `DEF-STATS-LOGGER`

### Removed
- Dead methods `_post2()`, `_get2()`, `_post_form()` — zero callers
- `UnknownMethodsClient` class — never imported or used
- Unused `import pprint` in `client.py`
- HA-specific `configuration.yaml` comment and stale inline comments
- Commented-out code lines and dead docstring example block
- 28 consecutive blank lines in `client.py`
- Built-in scheduler (`--schedule`) — removed ~390 lines; see `docs/SCHEDULING.md` for platform-native alternatives

### Changed
- 12 debug-noise `logger.info()` calls → `logger.debug()` in `client.py`, `stats.py`, `storm.py`
- HA-specific import comments → generic descriptions in `client.py`, `__init__.py`
- `--log-file` now uses `RotatingFileHandler` (5MB max, 3 backups) instead of unbounded `FileHandler`
- 7 internal log calls downgraded from `INFO` → `DEBUG` in `power.py` and `account.py`

---

## [0.2.0] - 2026-03-17

### Added
- Independent repository — migrated from `franklinwh-python` fork
- CloudFront edge PoP tracking with cache hit rate and transition detection
- `franklinwh-cli monitor` — real-time battery dashboard (full, compact, JSON modes)
- `franklinwh-cli metrics` — API call stats, response times, edge tracker data
- `franklinwh-cli discover` — device discovery with SIM/connectivity info
- `franklinwh-cli status` — power flow, battery, grid, and mode info
- `franklinwh-cli mode` — get/set operating mode
- `franklinwh-cli raw` — raw API method calls for debugging
- `ClientMetrics` — API call counting, response time tracking, error rate monitoring
- 7-module mixin architecture (`modes`, `tou`, `power`, `stats`, `devices`, `account`, `storm`)
- 60+ API methods covering TOU scheduling, power control, PCS settings, smart circuits, storm hedge
- `cli_output.py` — shared terminal rendering with colour, alignment, and JSON output
- Test infrastructure with 106+ tests
- Public repo with MIT license, CONTRIBUTING.md, issue templates

### Changed
- Repository name: `franklinwh-python` → `franklinwh-cloud`
- Removed `franklinwh/` directory (original upstream code)
- Removed `upstream` git remote

---

## [0.1.0] - 2026-02-01

### Added
- Initial fork from [richo/franklinwh-python](https://github.com/richo/franklinwh-python)
- Session authentication with cookie persistence
- TOU schedule management (`set_tou_schedule`, `get_tou_info`)
- Power control basics (`set_mode`, `get_mode`)
- Basic `asyncio`/`httpx` HTTP transport

[Unreleased]: https://github.com/david2069/franklinwh-cloud/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/david2069/franklinwh-cloud/releases/tag/v0.2.0
[0.1.0]: https://github.com/david2069/franklinwh-cloud/releases/tag/v0.1.0
