# Agent Onboarding — FranklinWH Cloud API Library

> **Read this first.** This document tells you where everything is so you don't have to ask the user.

## 🤖 Auto-Onboarding

| File | AI Tool | Auto-reads? |
|------|---------|-------------|
| `CLAUDE.md` | Claude Code / Anthropic | ✅ Auto |
| `.cursor/rules/project.mdc` | Cursor | ✅ Auto |
| `.github/copilot-instructions.md` | GitHub Copilot | ✅ Auto |
| `AGENT.md` | All (convention) | Manual first use |

> All auto-onboarding files point here as the **canonical source**. Edit policies here, not in the tool-specific files.

## 🚨 Workspace Scope Rule (CRITICAL)

> **NEVER read `AGENT.md` from an open file in another project.** Always resolve `AGENT.md` from the **workspace root** — the directory defined by the user's active workspace URI.

| Rule | Detail |
|------|--------|
| **Use workspace path** | `AGENT.md` lives at the root of **this** repository. Read `<workspace_root>/AGENT.md`, not a file that happens to be open in the editor from a different repo. |
| **Ignore cross-project open files** | The editor may show files from multiple projects. Open files from other repos are **never** authoritative for this project's policies. |
| **Verify the path** | Before reading `AGENT.md`, confirm the path starts with the active workspace URI (e.g. `/Users/davidhona/dev/franklinwh-cloud/`). |

> ⚠️ **Incident (2026-03-21):** An agent read `franklinwh-energy-manager/AGENT.md` (open in editor) instead of `franklinwh-cloud/AGENT.md` (workspace root), applying the wrong project's policies for an entire session. This rule prevents that.

## ⚡ Focus Discipline Protocol (AP-1)

> **Re-affirm at session start.** The formal AP-1 `Queue → Plan → Execute` protocol is located at:
> ↳ `.agents/policies/change_management.md`
> 
> You MUST explicitly follow this workflow constraint: **One fix at a time.** Complete the full cycle (code → test → verify → commit) before addressing secondary issues raised by the user.

---

## 🚫 ZERO-TOLERANCE: API Breaking Changes

> **CRITICAL POLICY:** No agent is authorized to make arbitrary changes that directly break existing usage via deprecation or fundamental structural alterations.

Any modification that alters existing public-facing API signatures (e.g., changing class `__init__` arguments, modifying expected method signatures, or deleting legacy structs) is **strictly forbidden** unless the user explicitly grants the authorization phrase:
`"explicit declaration of break change"`

If a change requires a downstream user to rewrite their integration code, you must:
1. Stop immediately.
2. Outline the exact breaking change in an Implementation Plan.
3. Wait for the user to explicitly reply with the authorization phrase.
4. Without the phrase, you must find a backward-compatible wrapper or fallback architecturally.

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

All verification logic (Syntax checks, live testing limits, and offline logs) must rigorously adhere to the AP-1 Verification Cycle documented in `.agents/policies/change_management.md`.

> ⚠️ **The syntax check is NON-NEGOTIABLE.** Always run it before committing.
> ```bash
> python3 -c "import ast; ast.parse(open('<modified_file>').read()); print('OK')"
> ```

### 🚫 STRICT BOUNDARY: No Negative Credential Testing with Real Accounts (AP-13)
> Under no circumstances may an AI Agent test negative authentication handling (e.g. intentionally using invalid passwords) against the **live API** using a REAL email address. Doing so triggers severe anti-bruteforce lockouts and bricks the user's connection.
> **Exception:** You MAY perform live negative authentication testing (e.g. simulating `InvalidCredentialsException`) ONLY IF you explicitly route the test through a **dummy fallback email** (e.g. `nobody@doesnotexist.invalid`). See `.agents/policies/live_test_protocol.md` for full constraints.

### 🚫 STRICT BOUNDARY: No PII Exposure (AP-3)
> **Never commit real user details.** Any captured JSON payloads, API outputs, or documentation examples must be rigorously scrubbed of all Personally Identifiable Information before being written to disk or `.md` files.
> You must strictly adhere to `.agents/policies/pii_policy.md`. Replace real emails with `user@example.com` and real serials with `10060006AXXXXXXXXX`.

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
