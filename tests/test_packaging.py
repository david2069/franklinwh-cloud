"""Every non-Python file the package needs at runtime must be declared as package data.

Without [tool.setuptools.package-data], setuptools leaves data files out of the wheel,
so they exist in a source checkout but not in a normal install (DEF-PACKAGE-DEVICE-CATALOG:
discover() raised FileNotFoundError on every pip install of v0.4.9–v0.5.0).
"""

import fnmatch
import subprocess
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# Tracked files that are deliberately NOT shipped
NOT_SHIPPED = {"franklinwh_cloud/franklinwh.ini.example"}


def _package_data_patterns():
    cfg = tomllib.loads((REPO / "pyproject.toml").read_text())
    return cfg.get("tool", {}).get("setuptools", {}).get("package-data", {}).get("franklinwh_cloud", [])


def test_device_catalog_is_declared_package_data():
    patterns = _package_data_patterns()
    assert any(fnmatch.fnmatch("const/device_catalog.json", p) for p in patterns), patterns


def test_every_tracked_data_file_is_shipped():
    tracked = subprocess.run(["git", "ls-files", "franklinwh_cloud"], cwd=REPO,
                             capture_output=True, text=True, check=True).stdout.split()
    data = [f for f in tracked if not f.endswith(".py") and f not in NOT_SHIPPED]
    patterns = _package_data_patterns()
    missing = [f for f in data
               if not any(fnmatch.fnmatch(f.removeprefix("franklinwh_cloud/"), p) for p in patterns)]
    assert not missing, f"not declared in [tool.setuptools.package-data]: {missing}"
