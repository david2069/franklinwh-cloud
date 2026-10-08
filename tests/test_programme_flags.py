"""Programme enrolment flags — DEF-PROGRAMME-ENTRANCE-OVERCLAIM and
DEF-ISJOINJA12-NEVER-READ.

`discover` rendered SGIP, Battery Bonus and JA12 as "Enrolled" whenever the
corresponding `*Entrance` field was 1. The field name suggests an entry point
being offered, and nothing in the corpus establishes that it means joined — so
the label asserted more than the data supports, the same class of error as
`nemType: 0` rendering "NEM 2.0".

The asymmetry is what decides the wording: 0 safely implies not enrolled,
while 1 does not safely imply enrolled.
"""

import pytest

from franklinwh_cloud.discovery import DeviceSnapshot, FeatureFlags


# ── the flag the corpus said was never read ──────────────────────────

def test_ja12_joined_defaults_to_unknown_not_false():
    """None means the firmware did not report it; False means it said no."""
    assert FeatureFlags().ja12_joined is None


def test_ja12_joined_is_distinct_from_ja12():
    """Two fields from two endpoints, deliberately not merged."""
    f = FeatureFlags()
    assert hasattr(f, "ja12") and hasattr(f, "ja12_joined")


def test_ja12_joined_survives_serialisation():
    snap = DeviceSnapshot()
    snap.flags.ja12_joined = False
    assert snap.to_dict()["flags"]["ja12_joined"] is False


async def test_is_join_ja12_is_read_from_the_gateway_list():
    """It is present on the gateway object discover() already walks."""
    import inspect

    from franklinwh_cloud.mixins.discover import DiscoverMixin

    src = inspect.getsource(DiscoverMixin)
    assert 'isJoinJA12' in src
    assert 'ja12_joined' in src


def test_absent_is_join_ja12_leaves_the_flag_unknown():
    """Most firmware does not report it — 9 corpus samples in total."""
    import inspect

    from franklinwh_cloud.mixins.discover import DiscoverMixin

    src = inspect.getsource(DiscoverMixin)
    # Guarded on presence, so a missing key cannot become False.
    assert 'if "isJoinJA12" in gw' in src


# ── the label ────────────────────────────────────────────────────────

@pytest.mark.parametrize("attr,api_key", [
    ("sgip", "sgipEntrance"),
    ("bb", "bbEntrance"),
])
def test_entrance_flags_do_not_claim_enrolment(attr, api_key):
    """An *Entrance field set to 1 must not be reported as "Enrolled"."""
    import inspect

    from franklinwh_cloud.cli_commands import discover as dcmd

    src = inspect.getsource(dcmd)
    # The shared helper is the only thing that may label these two.
    assert "_entrance(f." + attr in src


def test_the_entrance_helper_is_honest_in_both_directions():
    import inspect
    import re

    from franklinwh_cloud.cli_commands import discover as dcmd

    src = inspect.getsource(dcmd)
    m = re.search(r'def _entrance\(flag\):\s*\n\s*return (.+?)\n', src)
    assert m, "helper not found"
    body = m.group(1)
    assert "Available or enrolled" in body, "1 must not assert enrolment"
    assert "Not enrolled" in body, "0 safely implies not enrolled"


def test_ja12_prefers_the_join_field_when_the_gateway_reports_it():
    """A direct answer outranks an inference from the entrance flag."""
    import inspect

    from franklinwh_cloud.cli_commands import discover as dcmd

    src = inspect.getsource(dcmd)
    assert "f.ja12_joined is not None" in src
    assert "Available, not joined" in src, (
        "the informative case — offered but not taken up — must be sayable"
    )


# ── AP-14 applied to the support scheme block ────────────────────────

def _support_src():
    import inspect

    from franklinwh_cloud.cli_commands import support

    return inspect.getsource(support)


def test_support_does_not_print_enrolled_for_scheme_flags():
    """It printed "✅ Enrolled" directly beneath a comment calling the same
    values "eligibility flags". Both readings cannot be right."""
    src = _support_src()
    assert "✅ Enrolled" not in src
    assert "✅ Flag set" in src


def test_support_calls_bb_battery_bonus_not_backup_battery():
    """Same mislabel as DEF-BB-GROUP-MISLABEL, in a second renderer."""
    src = _support_src()
    assert "Backup Battery scheme" not in src
    assert "Battery Bonus" in src


def test_sdcp_expansion_is_not_asserted():
    """AP-14: the acronym has no vendor citation, so claim neither candidate."""
    src = _support_src()
    assert "Smart Device Control Program" not in src, (
        "unsourced expansion must not be presented as fact"
    )
    assert "expansion unverified" in src
