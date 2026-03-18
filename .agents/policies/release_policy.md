# Agent Release Policy

## Purpose

Ensures the changelog, version, and documentation stay in sync with every
code change. This policy applies to **all agents** working on this repository.

## CHANGELOG.md — Mandatory Update Rule

> **Every commit that adds, changes, or fixes user-facing behaviour MUST include
> a corresponding entry in `CHANGELOG.md` under the current version section.**

### What Counts as User-Facing

| Change Type | Requires CHANGELOG Entry? |
|-------------|:------------------------:|
| New CLI command or subcommand | ✅ Yes |
| New CLI argument | ✅ Yes |
| Bug fix that changes output or behaviour | ✅ Yes |
| New/changed API method in mixins | ✅ Yes |
| Constants changes (dispatch codes, etc.) | ✅ Yes |
| Dependency changes | ✅ Yes |
| Version bump | ✅ Yes |
| Internal refactor (no output change) | ❌ No |
| Test-only changes | ❌ No |
| Agent policy/doc-only changes | ❌ No |

### CHANGELOG Format

Use [Keep a Changelog](https://keepachangelog.com) categories:

- **Added** — new features
- **Changed** — changes to existing functionality
- **Fixed** — bug fixes

## API Safety Policy

> **Any change that writes to the aGate (TOU schedule, mode, power settings)
> must be documented in the TOU_SCHEDULE_GUIDE.md or API_CLIENT_GUIDE.md.**

| Rule | Detail |
|------|--------|
| **Document dispatch codes** | All valid dispatch codes must be listed in `const/tou.py` and `docs/TOU_SCHEDULE_GUIDE.md` |
| **Warn on destructive operations** | CLI commands that modify the aGate must print a confirmation or warning |
| **Log all write operations** | All `set_*` methods must log inputs and results via the `franklinwh_cloud` logger |
| **Validate before submit** | Schedule must be validated (JSON schema + 1440 min coverage) before API call |

## PR Checklist

Before any commit:

- [ ] `CHANGELOG.md` updated (if user-facing change)
- [ ] Syntax check passed on all modified files
- [ ] No credentials in logs or output
- [ ] Documentation updated for new CLI arguments or API methods
