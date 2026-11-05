"""README badges must point at things that exist."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text()


def test_build_badges_point_at_existing_workflows():
    names = set(re.findall(r"actions/workflow/status/[^/]+/[^/]+/([\w.-]+\.yml)", README))
    assert names, "no build badges"
    for name in names:
        assert (ROOT / ".github" / "workflows" / name).is_file(), name


def test_python_badge_matches_requires_python():
    floor = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["requires-python"]
    m = re.search(r"badge/python-([\d.]+)%2B", README)
    assert m and floor == f">={m.group(1)}"
