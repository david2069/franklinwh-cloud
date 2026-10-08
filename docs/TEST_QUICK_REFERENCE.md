# Test Quick Reference

How to run this project's checks, and which ones touch real hardware.

## ⚡ Before every commit

```bash
cd ~/dev/franklinwh-cloud
source venv/bin/activate

python -m pytest tests/ -m "not live" -q        # offline suite: no network, no credentials
python3 scripts/check_pii.py --scan             # repository hygiene scan
python scripts/gen_cli_reference.py --check     # CLI reference matches the CLI
```

All three must pass. The pre-push hook runs the scan again
(`git config core.hooksPath scripts/hooks`, once per clone).

## 🧪 Offline tests

| Command | What it runs |
|---|---|
| `python -m pytest tests/ -q` | Offline suite. `pyproject.toml` sets `addopts = "-m 'not live'"` |
| `python -m pytest tests/test_cli_energy.py -v` | One file |
| `python -m pytest tests/ -k energy -v` | Tests whose name matches |

These use mocks only: no cloud calls, no credentials needed.

## 🔒 Live tests (real cloud and aGate)

> ⚠️ **Live tests act on your real system.** `-m live` authenticates against the real
> cloud, and `tests/test_live_mode.py` sends real `set_mode()` writes that change the
> aGate's operating mode. **Never run them unattended.** Rules:
> [live_test_protocol.md](https://github.com/david2069/franklinwh-cloud/blob/main/.agents/policies/live_test_protocol.md).

```bash
python -m pytest tests/ -m live -v
```

- Credentials come from `franklinwh.ini` in the repo root (gitignored) or the
  `FRANKLIN_USERNAME` / `FRANKLIN_PASSWORD` environment variables. Without them, live
  tests are skipped, not failed.
- Never test failed logins against a real account: repeated failures can lock it.
  Negative-path tests use a dummy address only.

## ✅ Read-only CLI checks

These read from the live system without changing it, so they're a safe smoke test:

```bash
franklinwh-cli status
franklinwh-cli energy --period week
franklinwh-cli network status
franklinwh-cli discover
```

## 📊 Recording results

```bash
./tests/run_and_record.sh DEF-EXAMPLE-ID          # offline suite
./tests/run_and_record.sh DEF-EXAMPLE-ID --live   # live suite (see warning above)
```

Results are saved to `tests/results/YYYY-MM-DD_<ID>_<result>.txt`, with your home
directory replaced by `~`. Cite the file in the commit message.

## 🌐 Docs site

```bash
python -m mkdocs build --strict      # must finish with no warnings
python -m mkdocs serve               # preview at http://127.0.0.1:8000
```

The site redeploys when `docs/` or `mkdocs.yml` change on `main`. It only accepts
links inside `docs/`, so link to anything else by its GitHub URL.
