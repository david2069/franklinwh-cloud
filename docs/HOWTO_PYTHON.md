# Python Environment Setup

This library requires Python. The setup you need depends on what you're doing:

| What you need | Setup Required |
|:--------------|:---------------|
| **Use** scripts or CLI | Python + a virtual environment |
| **Develop** the library/tests | Python + virtual environment + dev dependencies |
| **Run TUI** monitor | Same as develop |

---

## 1. Get Python

### What version?
- **Minimum:** Python 3.8
- **Recommended:** Python 3.12 (used in CI and tested extensively)
- **Avoid:** Python 3.7 and below — native `f-strings` and `dataclasses` features are used throughout the library

Check your current version:
```bash
python3 --version
```

---

## 2. Platform Setup

### macOS (Recommended)
Recommended: install Python via [Homebrew](https://brew.sh).
Homebrew manages Python cleanly, avoids conflicts with the macOS system Python, and makes upgrades easy.

**Step 1 — Install Homebrew (if you don't have it):**
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

**Step 2 — Install Python:**
```bash
brew install python
```
This installs the latest stable Python and makes `python3` and `pip3` available on your PATH.

**Step 3 — Verify:**
```bash
python3 --version
which python3
# Should be /opt/homebrew/bin/python3 (Apple Silicon) or /usr/local/bin/python3 (Intel)
```

> **Don't use the native system Python:** macOS ships with `/usr/bin/python3` (typically 3.9). It's managed by the OS — never install packages into it. Always use Homebrew Python with a venv.

### Linux / Ubuntu
**Ubuntu 24.04+**
Python 3.12 is in the standard repos — just install it directly:
```bash
sudo apt install python3.12 python3.12-venv
```

**Older Ubuntu Versions (e.g. 22.04, 20.04)**
Python 3.12 may not be in the default APT repos natively. Use the `deadsnakes` PPA:
```bash
sudo apt update
sudo apt install software-properties-common -y
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install python3.12 python3.12-venv python3.12-dev -y
```

**Verify:**
```bash
python3.12 --version
```

### Windows
**Option A — Microsoft Store (easiest):**
Open the Microsoft Store and search for Python 3.12. Install directly.

**Option B — python.org installer:**
1. Download from [python.org/downloads](https://www.python.org/downloads/)
2. Run the installer — **check "Add Python to PATH" before clicking Install**

**Option C — winget:**
```powershell
winget install Python.Python.3.12
```

**Verify (in a new terminal):**
```powershell
python --version   # Windows uses `python`, not `python3`
python -m pip --version
```

> **Use PowerShell or Windows Terminal:** Avoid `cmd.exe` — PowerShell handles paths and venvs much more reliably.

---

## 3. Virtual Environments

### Why use a virtual environment?
A virtual environment (`venv`) creates an isolated Python installation for your project. This means:
- Package versions for `franklinwh-cloud` don't conflict with other projects
- You can `pip install` freely without affecting the system Python
- Easy to delete and recreate if something goes wrong
- Resolves conflicts with other dependency-heavy libraries (like httpx, respx, pydantic)

> **Never install packages with `pip install` globally** — always use a venv.

### Create and activate

**macOS / Linux:**
```bash
# Create the venv (do this once, inside your project folder)
python3 -m venv venv

# Activate it (do this every time you open a new terminal)
source venv/bin/activate

# Your prompt will show (venv) when active:
# (venv) user@Mac franklinwh-cloud %
```

Deactivate when done:
```bash
deactivate
```

**Windows (PowerShell):**
```powershell
# Create the venv
python -m venv venv

# Activate it
venv\Scripts\Activate.ps1

# If you get a permission error, run once:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Deactivate when done:
```powershell
deactivate
```

---

## 4. Install the Library

### Run only (no development)
Install from PyPI into your active venv:
```bash
pip install franklinwh-cloud
```

To install the full CLI suite (which includes tools like `rich` for the monitor UI):
```bash
pip install "franklinwh-cloud[cli]"
```

### Develop (editable install)
Clone the repo and install in editable (`-e`) mode with dev dependencies attached:
```bash
git clone https://github.com/davidhona/franklinwh-cloud.git
cd franklinwh-cloud
python3 -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

The `-e` flag means changes you make to the source code files in the directory are immediately reflected in Python — no reinstall needed.

Verify the install:
```bash
python3 -c "import franklinwh_cloud; print(franklinwh_cloud.__version__)"
```

---

## 5. Best Practices & Housekeeping

### Always work in the venv
Before running any scripts or CLI commands, check your prompt shows `(venv)`. If not, run `source venv/bin/activate`.

### Keep dependencies up to date
```bash
pip install --upgrade franklinwh-cloud   # if installed from PyPI
pip install --upgrade httpx rich         # individual packages
```

### Check what's installed
```bash
pip list                    # all packages in the venv
pip show franklinwh-cloud   # just this library
```

### Recreate a broken venv
Venvs are disposable — if something goes wrong with package versions, just delete and recreate the folder entirely:
```bash
deactivate
rm -rf venv/                     # macOS/Linux
# rmdir /s venv                  # Windows

python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

### Don't commit the venv
The `venv/` directory is already tracked in `.gitignore`. **Never commit it** — each developer creates their own local environment tied to their exact OS platform logic.

### IDEs (VS Code, PyCharm)
Point your IDE to the venv interpreter so it successfully indexes and finds all packages without showing red wavy syntax errors:
- **VS Code:** `Cmd+Shift+P` → **Python: Select Interpreter** → choose `./venv/bin/python`
- **PyCharm:** **Settings** → **Project** → **Python Interpreter** → Add Local → Existing Environment → `venv/bin/python`
