# Project History — franklinwh-cloud

> **From a 6-method fork to an independent 60+ method Cloud API library with CLI, TOU scheduling, and power control.**

---

## Timeline

### Origins — richo/franklinwh-python

The FranklinWH aGate battery system had no public API library. [richo](https://github.com/richo/franklinwh-python) created the first Python client by reverse-engineering the FranklinWH Cloud API, providing:

- Session authentication with cookie persistence
- 6 core API methods (`get_mode`, `set_mode`, `get_stats`, etc.)
- Basic `asyncio`/`httpx` HTTP transport
- Zero tests, zero CLI, minimal error handling

This was the starting point — a solid proof-of-concept that proved the API was accessible.

### Fork & Rapid Evolution — david2069/franklinwh-python

Forked in early 2026 to support the **FranklinWH Energy Manager** (FEM) — a Home Assistant add-on for battery dispatch control. What was needed far exceeded the original scope:

| Milestone | What Changed |
|-----------|-------------|
| **CLI utility** | `franklinwh-cli` with `status`, `discover`, `mode`, `tou`, `raw`, `metrics` commands |
| **60+ API methods** | TOU schedule management, power control, PCS settings, smart circuits, storm hedge, device info, alarms, notifications |
| **TOU scheduling engine** | Custom/predefined schedules, gap-filling, 24-hour validation, JSON schema validation |
| **Power control** | Grid import/export, PCS battery settings, grid compliance, off-grid detection |
| **CloudFront observability** | Edge PoP tracking, cache hit rates, CDN distribution IDs, latency metrics |
| **ClientMetrics** | API call counting, response time tracking, error rate monitoring |
| **Test infrastructure** | 106+ tests, CI pipeline, AP-11 traceability policy |
| **7-module mixin architecture** | Refactored monolithic `client.py` into: `modes`, `tou`, `power`, `stats`, `devices`, `account`, `storm` |
| **Real-time CLI monitor** | Full dashboard, compact, and JSON streaming modes with API response time |

### The Divergence Point

As the fork grew, a structural problem emerged:

- The **repo name** `franklinwh-python` implied we were richo's library
- The **PyPI package** was `franklinwh-cloud-client` with `from franklinwh_cloud import ...`
- The **`franklinwh/` directory** (richo's original code) was dead weight, confusing AI agents
- **Upstream PRs** required richo's approval — a dependency we couldn't control

The codebase had evolved from a 6-method client into a comprehensive energy management platform. The name no longer fit.

### Independence — david2069/franklinwh-cloud

On **17 March 2026**, the project migrated to its own identity:

```
Repository:    david2069/franklinwh-cloud
PyPI package:  franklinwh-cloud-client
Import path:   from franklinwh_cloud import Client
```

**What was preserved:**
- Full git history (164 commits) via `git filter-repo`
- All tags (`v0.2.0`, `archive/pre-migration-final`)
- All documentation, tests, and CI configuration

**What was removed:**
- `franklinwh/` directory (richo's original code)
- `upstream` git remote
- `upstream-pr/add-tests` branch (kept in archived repo)

**What was archived:**
- `david2069/franklinwh-python` → made private with "ARCHIVED" description
- The upstream PR branch with 26 tests for richo's code remains there

---

## Upstream Relationship

> We moved forward independently, but the door remains open.

The original `richo/franklinwh-python` library is acknowledged as the foundation. We are always willing to contribute back — particularly the test infrastructure and bug fixes. The archived `franklinwh-python` repo retains the `upstream-pr/add-tests` branch with 26 passing tests written against richo's original API surface.

If richo engages in future, we can cherry-pick fixes from `franklinwh-cloud` into PR-friendly format against his codebase.

---

## Architecture Today

```
franklinwh-cloud/
├── franklinwh_cloud/
│   ├── __init__.py              # Package root
│   ├── client.py                # Client class (composes all mixins)
│   ├── api.py                   # HTTP transport, auth, session management
│   ├── cli.py                   # CLI entry point
│   ├── cli_output.py            # Terminal rendering utilities
│   ├── exceptions.py            # Custom exception hierarchy
│   ├── const/                   # Constants, enums, TOU fixtures
│   ├── mixins/
│   │   ├── modes.py             # set_mode, get_mode, update_soc
│   │   ├── tou.py               # TOU schedule CRUD + dispatch
│   │   ├── power.py             # Grid control, PCS settings
│   │   ├── stats.py             # Runtime data, power history
│   │   ├── devices.py           # Accessories, smart circuits, LED
│   │   ├── account.py           # Site info, notifications, alarms
│   │   └── storm.py             # Storm hedge, weather
│   └── cli_commands/
│       ├── status.py            # Status dashboard
│       ├── discover.py          # Device discovery
│       └── monitor.py           # Real-time monitoring
├── tests/                       # 106+ unit and integration tests
├── pyproject.toml               # franklinwh-cloud-client
└── README.md
```

---

## Acknowledgements

- **[richo](https://github.com/richo/franklinwh-python)** — Original library foundation and API reverse-engineering
- **[jkt628](https://github.com/jkt628)** — Early tester and contributor
- **[FranklinWH](https://www.franklinwh.com/)** — The hardware that makes it all worthwhile
