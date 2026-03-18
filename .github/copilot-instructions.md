# GitHub Copilot Instructions — FranklinWH Cloud

> **Read `AGENT.md` and all policies in `.agents/policies/` before making any changes.**

## Critical Rules

1. **Focus Discipline** — one fix at a time, full cycle: code → test → verify → commit
2. **Syntax check before every commit** (non-negotiable):
   ```bash
   python3 -c "import ast; ast.parse(open('<file>').read()); print('OK')"
   ```
3. **Run tests**: `python -m pytest tests/ -v --tb=short --ignore=tests/test_live.py`
4. **Save test results** to `tests/results/` for traceability
5. **No auto-proceed** on implementation plans — wait for explicit user approval
6. **API-affecting changes** (`set_tou_schedule`, `set_mode`, PCS settings) require user sign-off before commit
7. **Read-only CLI commands** (`status`, `tou`, `monitor`, `--next`) are safe after syntax check

## Project Structure

- `franklinwh_cloud/` — library source (7 mixin modules, client, models)
- `franklinwh_cloud/cli_commands/` — CLI subcommands (11 modules)
- `tests/` — pytest suite (125+ tests)
- `docs/` — API reference, cookbook, TOU guide
- `.agents/policies/` — governance policies

## Key Paths

- Credentials: `~/dev/franklinwh-cloud-test/franklinwh.ini`
- Test sandbox: `~/dev/franklinwh-cloud-test/`
- Source: `~/dev/franklinwh-cloud/`
