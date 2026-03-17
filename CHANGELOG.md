# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `franklinwh-cli bms` — Battery Management System inspection (cell voltages, temperatures, SoC/SoH)
- `franklinwh-cli diag` — System diagnostics report
- `franklinwh-cli tou` — Full dispatch schedule with seasons, day types, pricing tiers
- `franklinwh-cli metrics` — now does a probe call so it shows real data including CloudFront edge
- GitHub Issues for public issue tracking (#1–#6)

### Fixed
- Monitor crash when edge tracker `cache_hit_rate` returns string instead of float (#2)
- Status command now warns when runtimeData is empty instead of silently showing zeros

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
