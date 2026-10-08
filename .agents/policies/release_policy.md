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

## Branch Model

One repository, one copy of the source. Versions are chosen by what you install,
never by keeping a second copy of the code.

| Branch / ref | Purpose | Rules |
|---|---|---|
| `main` | Released and releasable code | Every release tag is on `main`. Don't push unfinished work to it |
| `feat/*`, `fix/*`, `docs/*` | Development | Branch from `main`; merge back through a reviewed merge or PR |
| `release/x.y.z` | A fix-only release cut from the last tag (Path B) | Short-lived; merged into `main` once tagged |
| `vX.Y.Z` tags | Releases | Annotated, on `main`, with a GitHub Release |

**Never clone the repo a second time** (e.g. into `~/dev/franklinwh-cloud-test`).
A second copy drifts, and plain `python` started inside it imports its stale
`franklinwh_cloud/` instead of the installed package. The sandbox holds credentials,
venvs and scratch output only — see `docs/SANDBOX_SETUP.md`.

---

## Versioning

[Semantic Versioning](https://semver.org), `0.y.z` while pre-1.0:

| Change | Bump |
|---|---|
| Bug fixes only, no new public methods or CLI arguments | patch (`0.4.9` → `0.4.10`) |
| New features, new public methods or CLI commands | minor (`0.4.x` → `0.5.0`) |
| Breaking change (needs `"explicit declaration of break change"` — AGENT.md) | minor while `0.y`; major from 1.0 |

The version lives in **two** places and both must change together:
`pyproject.toml` (`version`) and `franklinwh_cloud/__init__.py` (`__version__`).

---

## Release Process

Choose the path by **what is on `main` that has not been released**, not by what
you want to ship. A tag ships everything reachable from it.

### Path A — Feature release (from `main`)

Use when everything unreleased on `main` is meant to ship.

1. Merge the feature branch into `main` (all tests passing on the merged result).
2. In `CHANGELOG.md`, rename `## [Unreleased]` entries into `## [x.y.z] - YYYY-MM-DD`
   and leave an empty `## [Unreleased]` above it.
3. Bump the version in both files (see Versioning).
4. Commit `vX.Y.Z — <summary>`, then `git tag -a vX.Y.Z -m "vX.Y.Z — <summary>"`.
5. Push: `git push origin main vX.Y.Z`.
6. Steps 7–9 below.

### Path B — Fix-only release (from the last tag)

Use when a fix is needed downstream **now**, but `main` or the feature branch also
contains unreleased work that should not ship with it. First used for v0.4.10.

1. `git worktree add -b release/x.y.z <dir> vLAST` — branch from the **last tag**,
   not from `main`.
2. `git cherry-pick <fix commit>` — only the fix and its tests. Resolve
   `CHANGELOG.md` / `defect_list.md` conflicts by hand.
3. Add `## [x.y.z] - YYYY-MM-DD` with only the fix; bump the version in both files.
4. Run the full suite on the release branch; save results to `tests/results/`.
5. Commit `vX.Y.Z — <summary>`; `git tag -a vX.Y.Z`.
6. Merge `release/x.y.z` into `main` (keep `main`'s `[Unreleased]` entries above the
   new section); run the suite on the merged `main`; push `main`, the release
   branch and the tag.
7. Steps 7–9 below.

### Both paths — after tagging

7. **Verify the tag installs.** In a fresh venv, run **outside any checkout**:
   ```bash
   pip install "franklinwh-cloud @ git+https://github.com/david2069/franklinwh-cloud.git@vX.Y.Z"
   python -c "import franklinwh_cloud; print(franklinwh_cloud.__file__, franklinwh_cloud.__version__)"
   ```
   The path must be in `site-packages` and the version must match the tag.
8. **Create the GitHub Release** from the changelog section, not the one-line tag
   message:
   `gh release create vX.Y.Z --verify-tag --title "vX.Y.Z — <summary>" --notes-file <notes.md>`.
   Notes = the `[x.y.z]` changelog section, an *Upgrading* section, and the compare link.
9. **Merge back.** Merge `main` into every active `feat/*` branch. Delete any
   changelog entry from the branch's `[Unreleased]` that has now shipped, so each
   change is listed exactly once.

### Live testing gates

| When | Against | How |
|---|---|---|
| Before merging a branch that changes API calls | the branch | Sandbox venv with an editable install of the working copy. Read-only commands unless the change is a write and the user has approved it |
| After tagging | the tag | Step 7, plus a read-only CLI smoke test |

Live tests follow `live_test_protocol.md`. `pytest -m live` includes real
`set_mode()` writes — never run it unattended.

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
