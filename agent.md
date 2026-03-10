# AI Agent Development Guide — franklinwh-python

> **Project**: `/Users/davidhona/dev/franklinwh-python/`
> **Package**: `franklinwh` (Cloud API client, `pip install franklinwh`)
> **Sister project**: `/Users/davidhona/dev/modbus/` (Modbus TCP library, `pip install franklinwh-modbus`)

---

## 📖 Essential Reading

| Priority | File | Why |
|----------|------|-----|
| 1 | [`README.md`](./README.md) | Project overview, Cloud API usage |
| 2 | [`franklinwh/cli.py`](./franklinwh/cli.py) | CLI entry point |
| 3 | [`franklinwh/client.py`](./franklinwh/client.py) | Core async Cloud API client |
| 4 | [`franklinwh/const/`](./franklinwh/const/) | Constants, modes, TOU schedules |

## ⚠️ Important Notes

- **Package name**: `franklinwh` (NOT `franklinwh-modbus` — that's the sister project)
- **Install**: `cd ~/dev/franklinwh-python && pip install -e .`
- **Cloud API** requires FranklinWH account credentials (email/password)
- **Known lints**: Many `Coroutine` indexing errors in `client.py` — pre-existing, not critical
- **`tou_predefined_builtin`** was recently exported from `const/__init__.py` (was missing)

## Current State (2026-03-10)

- ✅ `pyproject.toml` added — editable install works
- ✅ `const/__init__.py` — fixed missing export
- ⚠️ Pre-existing lint errors in `client.py` — not yet addressed

---

*Last Updated: 2026-03-10*
