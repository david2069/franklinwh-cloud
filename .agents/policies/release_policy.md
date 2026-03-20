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
| Constants changes (dispatch codes, modes, etc.) | ✅ Yes |
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
- **Security** — vulnerability fixes

---

## Traceability — Mandatory Rules

> **Every code change MUST be traceable from defect/feature request → commit → release → test evidence.**

### Defect and Feature IDs

| Item | ID Format | Example |
|------|-----------|---------|
| Defect | `DEF-<AREA>-<NAME>` | `DEF-MODE-SUPPRESS-TYPO` |
| Feature | `FEAT-<AREA>-<NAME>` | `FEAT-CONST-MODBUS-MODES` |
| GitHub Issue | `#<number>` | `#7` |

### Commit Messages
- Defect fixes: commit message MUST include `DEF-<ID>` (e.g., `fix(DEF-MODE-ALARMS): ...`)
- Feature implementations: commit message SHOULD include `FEAT-<ID>` if tracked
- Internal refactors: no ID required but CHANGELOG not required either

### CHANGELOG.md
- Each entry MUST list the `DEF-<ID>`, `FEAT-<ID>`, or `#<issue>` it addresses
- Test evidence MUST be noted (test count, test results)

### defect_list.md
- All known defects and feature requests are tracked in `defect_list.md`
- Updated at start and end of each session per AP-12 (Change Management Policy)
- Items are triaged by severity (S1–S4) and grouped by functional area

---

## API Safety Policy

> **Any change that writes to the aGate (TOU schedule, mode, power settings)
> must be documented in the TOU_SCHEDULE_GUIDE.md or API_CLIENT_GUIDE.md.**

| Rule | Detail |
|------|--------|
| **Document dispatch codes** | All valid dispatch codes must be listed in `const/tou.py` and `docs/TOU_SCHEDULE_GUIDE.md` |
| **Warn on destructive operations** | CLI commands that modify the aGate must print a confirmation or warning |
| **Log all write operations** | All `set_*` methods must log inputs and results via the `franklinwh_cloud` logger |
| **Validate before submit** | Schedule must be validated (JSON schema + 1440 min coverage) before API call |

---

## Release Process

1. Update `CHANGELOG.md` with version heading: `## [x.y.z] — YYYY-MM-DD`
2. Update version in `pyproject.toml` / `setup.cfg` (if applicable)
3. Commit: `vX.Y.Z — <summary>`
4. Tag: `git tag vX.Y.Z`
5. Push: `git push && git push --tags`

---

## PR Checklist

Before any commit:

- [ ] `CHANGELOG.md` updated (if user-facing change)
- [ ] All relevant defect/feature IDs referenced in commit message
- [ ] Syntax check passed on all modified files
- [ ] Test suite passes (all tests, not just new ones)
- [ ] No credentials in logs or output
- [ ] Documentation updated for new CLI arguments or API methods
- [ ] Regression risk stated
