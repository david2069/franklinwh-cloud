"""Gateway time and time-zone handling — docs/TIME_AND_TIMEZONES.md.

The gateway acts on its own clock. Every timestamp it returns is naive — no
offset, no zone — so a value read by a host in another zone is silently wrong
rather than an error. These tests pin the facts the guide rests on.
"""

import inspect
import re

import pytest


# ── the facts the guide asserts ──────────────────────────────────────

def test_the_pair_comes_from_one_endpoint():
    """deviceTime and zoneInfo arrive together from getDeviceInfoV2."""
    from franklinwh_cloud.mixins import devices

    src = inspect.getsource(devices.DevicesMixin.get_device_info)
    assert "getDeviceInfoV2" in src


def test_discover_reads_both_halves():
    from franklinwh_cloud.mixins import discover

    src = inspect.getsource(discover.DiscoverMixin)
    assert 'gw.get("deviceTime"' in src or '"deviceTime"' in src
    assert '"zoneInfo"' in src


def test_the_library_performs_no_timezone_conversion():
    """Documented explicitly: TOU HH:MM strings pass through untouched.

    If conversion is ever added, the guide's central warning stops being true
    and must be rewritten — this test is the tripwire.
    """
    import pathlib

    tou = pathlib.Path("franklinwh_cloud/mixins/tou.py").read_text()
    assert "astimezone" not in tou
    assert "ZoneInfo" not in tou


# ── the CLI gap that prompted the guide ──────────────────────────────

def _diag_src():
    from franklinwh_cloud.cli_commands import diag

    return inspect.getsource(diag)


def test_diag_renders_the_gateway_time_it_collects():
    """device_time was fetched and then silently discarded."""
    src = _diag_src()
    assert 'device_info.get("device_time")' in src
    assert "Gateway Time" in src


def test_diag_shows_the_zone_beside_the_time():
    """A naive wall clock without its zone is not interpretable remotely."""
    src = _diag_src()
    i = src.index("Gateway Time")
    window = src[i:i + 320]
    assert "timezone" in window


def test_diag_does_not_imply_a_zone_it_does_not_have():
    src = _diag_src()
    assert "zone unknown" in src


# ── the guide itself ─────────────────────────────────────────────────

def _guide():
    import pathlib

    return pathlib.Path("docs/TIME_AND_TIMEZONES.md").read_text()


def test_guide_exists_and_covers_the_multi_gateway_case():
    g = _guide()
    assert "Coordinating several gateways" in g
    assert "Compare in UTC, act in local" in g


def test_guide_flags_the_epoch_rendering_defect():
    """Readers must know the install/activation dates can be a day out."""
    g = _guide()
    assert "DEF-EPOCH-RENDERED-IN-CLIENT-TZ" in g


def test_guide_marks_the_numeric_offset_as_unverified():
    """AP-14 — 23 and 7 samples cannot establish DST behaviour."""
    g = _guide()
    i = g.index("timeZone")
    assert "ASSUMED" in g
    assert "Do not compute offsets from `timeZone`" in g


def test_guide_states_what_is_not_established():
    g = _guide()
    assert "Not established" in g


@pytest.mark.parametrize("claim", ["2,485", "2,505", "4,867", "19 characters"])
def test_guide_cites_counts_rather_than_adjectives(claim):
    """AP-14 — a citation is a number, not a word like "verified"."""
    assert claim in _guide()
