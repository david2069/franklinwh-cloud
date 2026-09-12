"""DEF-TOU-NEXT-WAVE-OVERFLOW — WAVE column too narrow for its own labels.

`tou --next` used a 12-wide WAVE column while `WAVE_TYPES` contains
"Super Off-Peak" at 14 characters, so that value ran straight into the
DURATION column with no separator: "Super Off-Peak10h 00m".
"""

import inspect
import re

import pytest

from franklinwh_cloud.cli_commands import tou
from franklinwh_cloud.const import WAVE_TYPES


def _label_widths():
    return [len(v) for v in WAVE_TYPES.values() if isinstance(v, str)]


def test_the_longest_label_is_what_the_column_must_fit():
    assert max(_label_widths()) == 14  # "Super Off-Peak"


@pytest.mark.parametrize("width_spec", ["{wave_name:<15}", "{'WAVE':<15}"])
def test_next_view_uses_a_wide_enough_wave_column(width_spec):
    src = inspect.getsource(tou)
    assert width_spec.replace("{", "").replace("}", "") in src.replace("{", "").replace("}", "")


def test_no_wave_column_is_narrower_than_the_longest_label():
    """Guard every WAVE format spec in the module, not just the one fixed."""
    src = inspect.getsource(tou)
    widths = [int(w) for w in re.findall(r"(?:'WAVE'|wave_name):<(\d+)", src)]
    assert widths, "expected to find WAVE column format specs"
    longest = max(_label_widths())
    too_narrow = [w for w in widths if w <= longest]
    assert too_narrow == [], (
        f"WAVE columns of width {too_narrow} cannot fit a {longest}-char label "
        f"and will run into the next column"
    )


def test_header_and_row_widths_agree():
    """A header wider than its rows misaligns just as badly."""
    src = inspect.getsource(tou)
    header = {int(w) for w in re.findall(r"'WAVE':<(\d+)", src)}
    rows = {int(w) for w in re.findall(r"wave_name:<(\d+)", src)}
    assert header == rows, f"header widths {header} != row widths {rows}"
