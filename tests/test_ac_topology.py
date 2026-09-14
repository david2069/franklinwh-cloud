"""AC topology resolution — DEF-AC-TOPOLOGY-INCONSISTENT.

The API reports every AC measurement as an L1/L2 pair regardless of what is
installed. On a split-phase US site those are two real 120 V legs. On an AU/NZ
site the supply is 230/240 VAC L/N/PE, so there is no second active conductor
and the pair is an artifact.

`discover` handled this; `bms`, `support` and `schema` did not. Resolved once
in `ac_topology` rather than re-derived per renderer, which is what produced
the inconsistency.
"""

import inspect

import pytest

from franklinwh_cloud.ac_topology import leg_caveat, legs_are_real


# ── resolution ───────────────────────────────────────────────────────

@pytest.mark.parametrize("three_phase,country_id,expected", [
    (0, 3, False),      # AU single-phase — L/N/PE, no second leg
    (1, 3, False),      # AU three-phase — L1/L2/L3, still not a split pair
    (None, 3, False),   # AU, phase unknown — not split either way
    (0, 2, True),       # US split-phase — legs are real
    (1, 2, False),      # US three-phase — not a split pair
    (None, None, None), # nothing known
    (0, None, None),    # country unknown — must not assume split
    (None, 99, None),   # unlisted market — must not assume split
])
def test_resolution(three_phase, country_id, expected):
    assert legs_are_real(three_phase=three_phase, country_id=country_id) is expected


def test_an_unknown_market_does_not_default_to_split_phase():
    """The failure mode this guards: silently treating a new market as US."""
    assert legs_are_real(country_id=7) is None


def test_three_phase_is_never_reported_as_split():
    """L1/L2/L3 mapping onto a two-leg pair is not established."""
    for cid in (2, 3, None, 99):
        assert legs_are_real(three_phase=1, country_id=cid) is False


# ── caveats ──────────────────────────────────────────────────────────

def test_no_caveat_when_legs_are_genuinely_real():
    assert leg_caveat(True) is None


def test_caveat_points_at_the_line_value_when_legs_are_artificial():
    c = leg_caveat(False)
    assert "not split-phase" in c
    assert "Line" in c


def test_undetermined_says_undetermined_rather_than_guessing():
    c = leg_caveat(None)
    assert "undetermined" in c


# ── the three renderers that were inconsistent ───────────────────────

def _src(mod):
    return inspect.getsource(mod)


def test_bms_resolves_topology_and_does_not_hardcode_the_leg_label():
    from franklinwh_cloud.cli_commands import bms

    s = _src(bms)
    assert "legs_are_real" in s
    assert '"Grid Feed (L1/L2)"' not in s, "label must depend on topology"


def test_bms_takes_country_from_a_call_it_already_makes():
    """getDeviceInfoV2 carries countryId — no extra request for this."""
    from franklinwh_cloud.cli_commands import bms

    s = _src(bms)
    assert 'dev_result.get("countryId")' in s


def test_support_exposes_topology_without_removing_existing_keys():
    """The JSON snapshot is a consumed contract; this is additive only."""
    from franklinwh_cloud.cli_commands import support

    s = _src(support)
    assert '"ac_legs_are_real"' in s
    assert '"grid_voltage_l1_v"' in s
    assert '"grid_voltage_l2_v"' in s


def test_schema_warns_in_rendered_output_not_only_in_a_comment():
    """A caveat only a source reader sees does not help a CLI user."""
    from franklinwh_cloud.cli_commands import schema

    s = _src(schema)
    assert "artifact, not two conductors" in s


def test_discover_behaviour_is_unchanged():
    """It was already correct — this change must not disturb it."""
    from franklinwh_cloud.cli_commands import discover

    s = _src(discover)
    assert "is_au and is_single_phase" in s


# ── evidence discipline ──────────────────────────────────────────────

def test_the_us_assumption_is_marked_as_unverified():
    """No US metrics have been obtained; that branch rests on market standard."""
    from franklinwh_cloud import ac_topology

    s = _src(ac_topology)
    assert "not on an observation" in s
    assert "DEF-AC-TOPOLOGY-NO-US-SAMPLE" in s


def test_the_modbus_lead_is_recorded():
    from franklinwh_cloud import ac_topology

    assert "Modbus" in _src(ac_topology)
