# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **Published to PyPI** — `pip install franklinwh-cloud` ([pypi.org/project/franklinwh-cloud](https://pypi.org/project/franklinwh-cloud))
- **Automated publish pipeline** — GitHub Actions Trusted Publisher (OIDC) workflow triggers on version tags
- **GitHub issue templates** — structured bug report and feature request forms with FranklinWH-specific fields (region, aGate model, component, redacted log sections)
- **Troubleshooting Guide** (`docs/TROUBLESHOOTING.md`) — 7 sections: login/auth, network connectivity, device config, inaccurate metrics, CLI inspection, collecting diagnostics, masking vs redacting PII
- **About & Disclaimer** — added to `docs/index.md` and `README.md` explaining unofficial nature, intended API users, educational-only purpose, and AS-IS no-fitness-warranty
- **`calculate_expected_earnings`** registered in raw CLI (`franklinwh-cli raw calculate_expected_earnings`)

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
