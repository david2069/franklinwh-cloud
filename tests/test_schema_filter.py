"""DEF-SCHEMA-TOTALS-POWER-FILTER — `--filter power` showed an empty section.

`schema --filter power` rendered the `stats.totals` header with zero rows.
Substring matching against group names: no TOTALS_SCHEMA group contains the
word "power". CURRENT_SCHEMA happens to have "Power Flow" and "Power
Measurements (211)", so the filter appeared to work while half its output
silently vanished.
"""

import pytest

from franklinwh_cloud.cli_commands.schema import (
    CURRENT_SCHEMA,
    TOTALS_SCHEMA,
    _totals_filtered_out,
)

TOTALS_GROUPS = sorted({v[3] for v in TOTALS_SCHEMA.values()})


def test_no_totals_group_contains_the_word_power():
    """The premise. If a group is ever renamed to contain it, revisit this."""
    assert not [g for g in TOTALS_GROUPS if "power" in g.lower()]


def test_current_schema_does_contain_it_which_is_why_it_looked_fine():
    groups = {v[3] for v in CURRENT_SCHEMA.values()}
    assert [g for g in groups if "power" in g.lower()]


@pytest.mark.parametrize("group", TOTALS_GROUPS)
def test_power_filter_keeps_every_totals_group(group):
    """Every totals group is cumulative energy, so all of them qualify."""
    assert _totals_filtered_out("power", group) is False


@pytest.mark.parametrize("group", TOTALS_GROUPS)
def test_energy_filter_keeps_every_totals_group(group):
    assert _totals_filtered_out("energy", group) is False


@pytest.mark.parametrize("group", TOTALS_GROUPS)
def test_no_filter_keeps_everything(group):
    assert _totals_filtered_out(None, group) is False
    assert _totals_filtered_out("", group) is False


def test_an_unrelated_filter_still_excludes():
    """The fix must not turn --filter into a no-op."""
    assert _totals_filtered_out("tou", "Battery") is True
    assert _totals_filtered_out("generator", "Grid") is True


def test_a_real_group_name_still_matches_normally():
    assert _totals_filtered_out("battery", "Battery") is False
    assert _totals_filtered_out("grid", "Grid") is False


def test_matching_is_case_insensitive():
    assert _totals_filtered_out("POWER", "Battery") is False
    assert _totals_filtered_out("BaTtErY", "Battery") is False


def test_substring_matching_is_preserved():
    """e.g. --filter load matches "Load Breakdown"."""
    assert _totals_filtered_out("load", "Load Breakdown") is False
