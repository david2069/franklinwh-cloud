# CLAUDE.md — Auto-onboarding for Claude Code / Anthropic

> **This file is auto-loaded by Claude Code at session start.**
> Canonical source: [AGENT.md](AGENT.md) — read it first, along with all policies in `.agents/policies/`.

## Critical Rules

1. **Read `AGENT.md` from the WORKSPACE ROOT** — never from open files in other projects. Verify the path starts with this repo's directory before reading.
2. **Read `.agents/policies/` before doing anything**
3. **Focus Discipline** — one fix at a time, full cycle (code → test → verify → commit)
4. **Syntax check is NON-NEGOTIABLE** before every commit:
   ```bash
   python3 -c "import ast; ast.parse(open('<file>').read()); print('OK')"
   ```
4. **No `ShouldAutoProceed: true`** on implementation plans — wait for user approval
5. **Save test results** to `tests/results/` for traceability
6. **API-affecting changes** (`set_tou_schedule`, `set_mode`, etc.) need user sign-off before commit

## Project Layout

| Path | Purpose |
|------|---------|
| `franklinwh_cloud/` | Library source — mixins, client, models |
| `franklinwh_cloud/cli.py` | CLI entry point |
| `franklinwh_cloud/cli_commands/` | CLI subcommands (11 modules) |
| `tests/` | pytest suite (125+ tests) |
| `docs/` | API reference, cookbook, guides |
| `.agents/policies/` | Governance policies |

## Key Commands

```bash
cd /Users/davidhona/dev/franklinwh-cloud
python -m pytest tests/ -v --tb=short
```

Live tests are **opt-in** — `pyproject.toml` sets `addopts = "-m 'not live'"`, so the
command above never touches the real cloud or aGate. To run them deliberately:

```bash
python -m pytest tests/ -m live -v          # authenticates for real; see AP-13
```

> ⚠️ `tests/test_live_mode.py::test_live_set_mode` issues real `set_mode()` writes that
> change the physical aGate's operating mode. Never run `-m live` unattended.
> The older `--ignore=tests/test_live.py` form was **not** a sufficient guard: it missed
> the live tests in `test_live_mode.py` and `test_integration.py`.

> Credentials live in `~/dev/franklinwh-cloud-test/franklinwh.ini`
