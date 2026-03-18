# CLI Development Sandbox — Setup Guide

How to create an isolated sandbox for developing, testing, and validating the `franklinwh-cli` tool without polluting the main source repo.

## Architecture

```
~/dev/franklinwh-cloud/           ← Source repo (real work, branches, commits)
    ├── franklinwh_cloud/         ← Library source
    ├── tests/                    ← Unit tests (74+)
    ├── venv/                     ← Dev venv (pytest, respx, pytest-asyncio)
    └── .gitignore                ← venv/ ignored

~/dev/franklinwh-cloud-test/      ← Sandbox (CLI testing, credentials, scratch)
    ├── franklinwh.ini            ← API credentials (never committed)
    ├── venv/                     ← CLI venv (editable install of source repo)
    └── (scratch files)           ← Test JSON schedules, logs, etc.
```

---

## Step 1: Create the Sandbox Directory

```bash
mkdir -p ~/dev/franklinwh-cloud-test
cd ~/dev/franklinwh-cloud-test
```

## Step 2: Create a Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

## Step 3: Install the CLI (Editable Mode)

Editable mode (`-e`) means source changes in `franklinwh-cloud/` take effect immediately — no reinstall needed.

```bash
pip install -e ~/dev/franklinwh-cloud
```

Verify the CLI is available:

```bash
franklinwh-cli --help
```

Expected output: full help text with all subcommands (`status`, `monitor`, `tou`, `mode`, etc.)

## Step 4: Configure Credentials

Create `franklinwh.ini` in the sandbox directory:

```bash
cat > franklinwh.ini << 'EOF'
[franklinwh]
username = your_email@example.com
password = your_password
gateway = YOUR_GATEWAY_ID
EOF
```

> ⚠️ **Never commit `franklinwh.ini`** — it contains your Cloud API credentials. The main repo's `.gitignore` already excludes it.

To find your Gateway ID, log into the FranklinWH app or use:
```bash
franklinwh-cli discover
```

## Running the CLI — Three Ways

You can run the CLI from **either** the sandbox or the source repo:

```bash
# 1. Entry point (requires pip install -e in active venv)
franklinwh-cli status

# 2. Python module (works from source repo without install)
cd ~/dev/franklinwh-cloud
python -m franklinwh_cloud.cli status

# 3. Direct script (works anywhere with correct Python path)
~/dev/franklinwh-cloud/venv/bin/python -m franklinwh_cloud.cli status
```

> **Credentials:** All three methods look for `franklinwh.ini` in the **current working directory**. Either `cd` to where your `.ini` file is, or use `--config /path/to/franklinwh.ini`.

## Step 5: Validate the CLI

Run these commands in order to verify everything works:

```bash
cd ~/dev/franklinwh-cloud-test
source venv/bin/activate

# 1. Basic connectivity (read-only, safe)
franklinwh-cli status

# 2. TOU schedule inspection
franklinwh-cli tou

# 3. Current/next dispatch with remaining time
franklinwh-cli tou --next

# 4. Real-time monitor (Ctrl+C to stop)
franklinwh-cli monitor

# 5. JSON output mode
franklinwh-cli status --json
```

All commands should return data without errors. If you see `No credentials found`, check that `franklinwh.ini` exists in the current directory.

---

## Step 6: Set Up the Test Harness (Main Repo)

The unit tests use [**pytest**](https://docs.pytest.org/) — Python's most popular testing framework. If you're new to pytest, the key things to know are:

- Tests are plain Python files named `test_*.py`
- Each test is a function starting with `test_`
- Run with `pytest tests/` — it auto-discovers and runs all tests
- `-v` = verbose (show each test name), `--tb=short` = compact error output
- Docs: [docs.pytest.org](https://docs.pytest.org/en/stable/)

The test suite lives in the **source repo**, not the sandbox. Install test dependencies in the source repo's venv:

```bash
cd ~/dev/franklinwh-cloud
source venv/bin/activate

# Install the library itself
pip install -e .

# Install test dependencies
pip install pytest pytest-asyncio respx
```

### Run the Unit Tests

```bash
cd ~/dev/franklinwh-cloud
./venv/bin/python -m pytest tests/ -v --tb=short
```

Expected: **74+ tests passed**, 0 failures.

> **Note:** `test_live.py` requires credentials and hits the real API. Skip it for routine testing:
> ```bash
> ./venv/bin/python -m pytest tests/ -v --tb=short --ignore=tests/test_live.py
> ```

### Test Coverage by File

| Test File | Coverage |
|-----------|---------|
| `test_build_payload.py` | TOU payload construction, CRC, JSON structure |
| `test_const.py` | Dispatch codes, wave types, predefined schedules, schema |
| `test_get_stats.py` | Power/stats response parsing, conditional API calls |
| `test_grid_status.py` | Grid status enum, outage reason mapping |
| `test_metrics.py` | Call counting, response times, error tracking, edge PoP |
| `test_modes.py` | Mode constants, enum mappings, run status codes |
| `test_retry.py` | HTTP retry logic, 401 refresh, timeout handling |
| `test_set_mode.py` | Mode validation, SoC bounds, exception types |
| `test_token_fetcher.py` | Login flow, token caching, credential errors |
| `test_live.py` | Live API integration (requires credentials) |

---

## Day-to-Day Workflow

### Making and Testing a Code Change

```bash
# 1. Edit source in franklinwh-cloud/
cd ~/dev/franklinwh-cloud
# ... edit files ...

# 2. Syntax check
python3 -c "import ast; ast.parse(open('franklinwh_cloud/cli_commands/tou.py').read()); print('OK')"

# 3. Run unit tests
./venv/bin/python -m pytest tests/ -v --tb=short

# 4. Test the CLI (editable install = changes are live instantly)
cd ~/dev/franklinwh-cloud-test
source venv/bin/activate
franklinwh-cli tou --next

# 5. Commit (back in source repo)
cd ~/dev/franklinwh-cloud
git add -A && git commit -m "feat: description" && git push
```

### Running a Single Test File

```bash
./venv/bin/python -m pytest tests/test_const.py -v
```

### Running Tests Matching a Pattern

```bash
./venv/bin/python -m pytest tests/ -v -k "dispatch"
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `command not found: franklinwh-cli` | Activate the sandbox venv: `source ~/dev/franklinwh-cloud-test/venv/bin/activate` |
| `No credentials found` | Run from the sandbox dir (`cd ~/dev/franklinwh-cloud-test`) or use `--config path/to/franklinwh.ini` |
| `ModuleNotFoundError: respx` | Install test deps: `~/dev/franklinwh-cloud/venv/bin/pip install respx pytest-asyncio` |
| Code changes not reflected | Ensure editable install: `pip install -e ~/dev/franklinwh-cloud` |
| `Operation not permitted` on new files | macOS Tahoe provenance — `sudo rm file && recreate` |
| Tests hang | Use `--timeout=30`: `pip install pytest-timeout && pytest --timeout=30` |
