# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
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

### Fixed
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

### Changed
- 12 debug-noise `logger.info()` calls → `logger.debug()` in `client.py`, `stats.py`, `storm.py`
- HA-specific import comments → generic descriptions in `client.py`, `__init__.py`

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
