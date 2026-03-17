# Agent Release Policy

## Purpose

Ensures the changelog, version, and documentation stay in sync with every
code change. This policy applies to **all agents** working on this repository.

## CHANGELOG.md — Mandatory Update Rule

> **Every commit that adds, changes, or fixes user-facing behaviour MUST include
> a corresponding entry in `CHANGELOG.md` under the `[Unreleased]` section.**

### What Counts as User-Facing

| Change Type | Requires CHANGELOG Entry? |
|-------------|:------------------------:|
| New CLI command | ✅ Yes |
| New API method in `client.py` or mixins | ✅ Yes |
| Bug fix that changes output or behaviour | ✅ Yes |
| New/changed constants or enums | ✅ Yes |
| Dependency changes | ✅ Yes |
| Internal refactor (no output change) | ❌ No |
| Test-only changes | ❌ No |
| Agent policy/doc-only changes | ❌ No |

### CHANGELOG Format

Use [Keep a Changelog](https://keepachangelog.com) categories:

- **Added** — new features
- **Changed** — changes to existing functionality
- **Deprecated** — soon-to-be removed features
- **Removed** — removed features
- **Fixed** — bug fixes
- **Security** — vulnerability fixes

Reference GitHub Issue numbers where applicable: `(#1)`, `(#42)`.

### Example Entry

```markdown
## [Unreleased]

### Added
- `franklinwh-cli storm` — Storm Hedge settings display (#1)

### Fixed
- Monitor crash when cache_hit_rate is a string (#2)
```

## Release Process

When cutting a release:

1. Move `[Unreleased]` entries to a new version heading: `## [x.y.z] - YYYY-MM-DD`
2. Update version in `pyproject.toml`
3. Update the comparison links at the bottom of `CHANGELOG.md`
4. Commit: `release: vX.Y.Z`
5. Tag: `git tag vX.Y.Z`
6. Push: `git push && git push --tags`

## GitHub Issues

- Reference issue numbers in commit messages and CHANGELOG entries
- Close issues via commit message when appropriate: `Fixes #2`
- New bugs/features discovered during development → create a GitHub Issue immediately
- Do NOT track issues in markdown files — use GitHub Issues exclusively

## PR Checklist Enforcement

Before any commit is pushed, verify:

- [ ] `CHANGELOG.md` updated (if user-facing change)
- [ ] GitHub Issue referenced (if applicable)
- [ ] All tests pass
- [ ] No credentials in logs or output
