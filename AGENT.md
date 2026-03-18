# Agent Onboarding — FranklinWH Cloud API Library

> **Read this first.** This document tells you where everything is so you don't have to ask the user.

## ⚡ Focus Discipline Protocol

> **Re-affirm at session start.** When beginning a session, briefly acknowledge this protocol:
> *"I've read the focus discipline guidelines — I'll stay on-task and queue any side issues."*

### Rules for the Agent

| Situation | Action |
|-----------|--------|
| User reports a new issue **during** an active fix | **Acknowledge and queue:** "Noted — I'll address that after completing the current fix." Do NOT context-switch. |
| User provides context/observations mid-fix | **Absorb silently** — use the information but stay on the current task. |
| Multiple issues reported at once | **Triage and sequence:** fix one completely (code → test → verify → commit) before starting the next. |
| Fix introduces a new error | **Stop and fix immediately** — this IS the current task. |

### Rules for Both Parties

1. **One fix at a time.** Complete the full cycle: code → test → verify → commit. Then move to the next issue.
2. **No parallel debugging threads.** If a second issue is spotted, it goes on the queue — not into the current code change.

---

## 🚫 Approval Requirements

> **No auto-proceed without explicit user approval for plan documents.**

| Rule | Detail |
|------|--------|
| **Implementation plans require explicit LGTM** | Do NOT set `ShouldAutoProceed: true` on plans. Wait for user approval. |
| **API-affecting changes need approval** | Any change to `set_tou_schedule`, `save_tou_dispatch`, or mode-setting APIs requires user sign-off before commit |
| **CLI argument changes need approval** | Adding/removing/renaming CLI arguments or subcommands must be described in a plan first |
| **Constant changes need approval** | Changes to dispatch codes, wave types, or TOU schema in `const/` require approval |

---

## Mandatory Verification After Every Code Change

1. **Syntax check:**
   ```bash
   python3 -c "import ast; ast.parse(open('<modified_file>').read()); print('OK')"
   ```

2. **Test suite (if accessible):**
   ```bash
   cd /Users/davidhona/dev/franklinwh-cloud
   python -m pytest tests/ -v --tb=short
   ```

3. **Static verification for unit changes:**
   ```bash
   # Confirm no stale labels/keys remain
   grep -rn '<old_pattern>' franklinwh_cloud/cli_commands/
   ```

4. **Do not commit until user has tested** (if changes affect live aGate):
   - `--set` commands modify the live TOU schedule
   - `mode --set` changes the operating mode
   - Read-only commands (`--next`, `tou`, `status`, `monitor`) are safe to commit after syntax check

> ⚠️ **The syntax check is NON-NEGOTIABLE.** Always run it before committing.

---

## Quick Start

```bash
cd /Users/davidhona/dev/franklinwh-cloud
```

- **Tests**: `python -m pytest tests/ -v --tb=short`
- **CLI**: Run from `~/dev/franklinwh-cloud-test/` (where `franklinwh.ini` lives)
- **Install**: `pip install -e .` (editable — source changes take effect immediately)

> ⚠️ **Credentials live in `franklinwh-cloud-test/franklinwh.ini`** — the CLI must be run from that directory or with `--config` pointing to it.

---

## Project Overview

FranklinWH Cloud API client library — Python package for battery monitoring, mode control, TOU scheduling, and diagnostics via the FranklinWH Cloud API.

### Architecture — Key Files

| Purpose | File |
|---------|------|
| HTTP client + auth | `franklinwh_cloud/client.py` |
| CLI entrypoint + arg parser | `franklinwh_cloud/cli.py` |
| CLI commands | `franklinwh_cloud/cli_commands/` |
| CLI output formatting | `franklinwh_cloud/cli_output.py` |
| TOU scheduling mixin | `franklinwh_cloud/mixins/tou.py` |
| Mode management mixin | `franklinwh_cloud/mixins/modes.py` |
| Power/stats mixin | `franklinwh_cloud/mixins/power.py`, `stats.py` |
| Device/account mixin | `franklinwh_cloud/mixins/devices.py`, `account.py` |
| Constants (dispatch codes, wave types) | `franklinwh_cloud/const/tou.py` |
| Test fixtures (predefined schedules) | `franklinwh_cloud/const/test_fixtures.py` |

### CLI Commands

| Command | Purpose |
|---------|---------|
| `status` | Power flow, battery SoC, mode, weather |
| `monitor` | Real-time dashboard (auto-refresh) |
| `tou` | TOU schedule inspection + `--set` + `--next` |
| `mode` | Get/set operating mode |
| `discover` | Device enumeration |
| `diag` | Diagnostic report |
| `bms` | Battery cell telemetry |
| `metrics` | API call stats + CloudFront edge |
| `raw` | Direct API method calls |
| `fetch` | Arbitrary endpoint GET/POST |

---

## Documentation Index

| Doc | What's in it |
|-----|-------------|
| [API_CLIENT_GUIDE.md](API_CLIENT_GUIDE.md) | CLI usage guide, examples, metrics |
| [docs/TOU_SCHEDULE_GUIDE.md](docs/TOU_SCHEDULE_GUIDE.md) | TOU API reference — dispatch codes, diagrams, code examples |
| [CHANGELOG.md](CHANGELOG.md) | Release history |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution guidelines |
| [README.md](README.md) | Project overview and installation |

---

## Related Repositories

| Repo | Purpose |
|------|---------|
| [`franklinwh-energy-manager`](https://github.com/david2069/franklinwh-energy-manager) | FEM — Flask dashboard + MQTT bridge (private) |
| `franklinwh-modbus` | Standalone Modbus CLI tool |
| [`franklinwh-addon`](https://github.com/david2069/franklinwh-addon) | HA Add-on distribution (public) |

> ⚠️ **This library is vendored into FEM** at `vendor/cloud/`. Changes here may need to be synced via `sync.sh` in the add-on repo.
