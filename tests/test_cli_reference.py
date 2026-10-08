"""docs/CLI_COMMAND_REFERENCE.md must match the CLI's own definitions."""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_cli_reference_is_current():
    r = subprocess.run([sys.executable, "scripts/gen_cli_reference.py", "--check"],
                       cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
