"""Generator settings and Smart Circuit schedules in schema and discover.

Both surfaces carried runtime *state* but neither carried *settings* or
*schedules*. The circuit schedule was the sharper gap: `discover()` already
fetched the cmdType 311 payload and parsed straight past the arrays — the same
shape as DEF-SC-SCHEDULE-NOT-RENDERED, where data was fetched and discarded.
"""

import pytest

from franklinwh_cloud.discovery import (
    DeviceSnapshot, GeneratorConfig, SmartCircuitConfig,
)
from franklinwh_cloud.mixins.discover import DiscoverMixin

SC_311 = {
    "SwMerge": 0,
    "Sw1Name": "Fridge", "Sw1Mode": 1,
    "Sw1Time": ["2000-01-01 06:30", "2000-01-01 09:00",
                "2000-01-01 17:00", "2000-01-01 21:30"],
    "Sw1TimeEn": [1, 1, 0, 0], "Sw1TimeSet": [1, 0, 1, 0],
    "Sw2Name": "Pool", "Sw2Mode": 0,
    "Sw2Time": ["2000-01-01 00:00", "2000-01-01 23:59",
                "2000-01-01 00:00", "2000-01-01 23:59"],
    "Sw2TimeEn": [0, 0, 0, 0], "Sw2TimeSet": [1, 0, 1, 0],
}


# ── circuit schedules (free — 311 already fetched) ───────────────────

def test_schedules_are_extracted_from_the_payload_already_in_hand():
    out = DiscoverMixin._sc_schedules(SC_311, 2)
    assert [s["circuit"] for s in out] == [1, 2]
    assert out[0]["slots"][0]["at"] == "06:30"


def test_the_placeholder_date_is_stripped():
    """'2000-01-01' is a placeholder in every observed sample."""
    out = DiscoverMixin._sc_schedules(SC_311, 2)
    assert all("2000" not in (s["at"] or "") for s in out[0]["slots"])


def test_enabled_state_is_per_slot():
    out = DiscoverMixin._sc_schedules(SC_311, 2)
    assert [s["enabled"] for s in out[0]["slots"]] == [True, True, False, False]


def test_an_all_disabled_schedule_is_flagged():
    out = DiscoverMixin._sc_schedules(SC_311, 2)
    assert out[0]["any_enabled"] is True
    assert out[1]["any_enabled"] is False


def test_time_set_is_passed_through_undeciphered():
    out = DiscoverMixin._sc_schedules(SC_311, 2)
    assert out[0]["raw_time_set"] == [1, 0, 1, 0]


def test_the_pairing_is_now_confirmed_as_two_ranges():
    """Settled 2026-09-18 by the app's own limit message.

    The Timing Supply screen refuses a third range with "Only two time slots
    can be scheduled", and shows each as a start-end pair. So the four SwNTime
    entries are two ranges: (0,1) and (2,3).
    """
    out = DiscoverMixin._sc_schedules(SC_311, 2)
    assert out[0]["pairing"] == "two ranges of start/end"
    roles = [s["role"] for s in out[0]["slots"]]
    assert roles == ["start", "end", "start", "end"]
    assert [s["range"] for s in out[0]["slots"]] == [1, 1, 2, 2]


def test_the_date_is_kept_but_not_called_the_execution_date():
    """Verified live 2026-09-18 against a schedule set in the app.

    The app showed "Execution time: 17 Oct 2026" while Sw1Time carried
    2026-06-19 on range 1 and 2026-09-18 on range 2 — so the date in SwNTime
    is NOT the execution date. It is surfaced as `date_raw` for that reason.
    '2000-01-01' is the unset sentinel.
    """
    payload = {**SC_311, "Sw1Time": ["2026-06-19 16:02", "2026-06-19 17:03",
                                     "2000-01-01 00:00", "2000-01-01 23:59"]}
    out = DiscoverMixin._sc_schedules(payload, 1)
    slots = out[0]["slots"]
    assert slots[0]["date_raw"] == "2026-06-19"
    assert slots[0]["at"] == "16:02"
    assert slots[2]["date_raw"] is None, "the unset sentinel must read as None"
    assert "date" not in slots[0], "must not imply it is the execution date"


def test_a_circuit_with_no_schedule_is_omitted():
    out = DiscoverMixin._sc_schedules({"Sw1Time": ["2000-01-01 06:00"]}, 3)
    assert [s["circuit"] for s in out] == [1]


def test_schedules_reach_the_snapshot():
    snap = DeviceSnapshot()
    snap.accessories.smart_circuits = SmartCircuitConfig(
        schedules=DiscoverMixin._sc_schedules(SC_311, 2))
    assert snap.to_dict()["accessories"]["smart_circuits"]["schedules"][0]["circuit"] == 1


# ── generator settings (tier 3 — one REST call) ──────────────────────

def test_generator_config_uses_the_real_soc_field_names():
    """genStartElec / genCloseElec — genStartSoc/genStopSoc do not exist."""
    import dataclasses

    names = {f.name for f in dataclasses.fields(GeneratorConfig)}
    assert {"start_below_soc", "stop_above_soc"} <= names


def test_generator_config_keeps_mode_and_manual_switch_apart():
    """They are different controls — DEF-GEN-MODE-WRITES-MANUSW."""
    import dataclasses

    names = {f.name for f in dataclasses.fields(GeneratorConfig)}
    assert "mode" in names and "manual_switch" in names


def test_generator_is_only_fetched_when_one_was_detected():
    """A site without a generator must not pay for the extra REST call."""
    import inspect

    src = inspect.getsource(DiscoverMixin._discover_tier3)
    assert "if snap.accessories.has_generator:" in src


def test_generator_is_tier_three_only():
    import inspect

    t3 = inspect.getsource(DiscoverMixin._discover_tier3)
    t1 = inspect.getsource(DiscoverMixin._discover_tier1)
    assert "get_generator_info" in t3
    assert "get_generator_info" not in t1


# ── schema ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("field", [
    "genStartElec", "genCloseElec", "mode", "manuSw",
    "charge1En", "charge1StartTime", "charge3EndTime",
])
def test_schema_documents_generator_settings(field):
    from franklinwh_cloud.cli_commands.schema import GENERATOR_SCHEMA

    assert field in GENERATOR_SCHEMA


@pytest.mark.parametrize("field", ["SwNTime", "SwNTimeEn", "SwNTimeSet", "SwMerge"])
def test_schema_documents_the_circuit_schedule_fields(field):
    from franklinwh_cloud.cli_commands.schema import SMART_CIRCUIT_SCHEDULE_SCHEMA

    assert field in SMART_CIRCUIT_SCHEDULE_SCHEMA


def test_schema_marks_charge_windows_as_gateway_local():
    """The likeliest way to get a multi-timezone schedule wrong."""
    import inspect

    from franklinwh_cloud.cli_commands import schema

    assert "GATEWAY-LOCAL wall clock" in inspect.getsource(schema)


def test_schema_records_that_sc_schedules_have_no_setter():
    import inspect

    from franklinwh_cloud.cli_commands import schema

    src = inspect.getsource(schema)
    assert "there is no" in src and "DEF-SC-TIMESET-UNDECIPHERED" in src


# ── vendor-confirmed semantics (franklinwh.com Smart Circuits overview) ──

def test_soc_cutoff_is_documented_as_off_grid_only():
    """It sheds circuits during a grid outage; it does nothing grid-tied.

    A threshold configured on a healthy grid looks inert, so a reader seeing
    only "Enabled" would reasonably expect action that will not come.
    """
    import inspect

    from franklinwh_cloud import models

    src = " ".join(inspect.getsource(models).split())
    assert "OFF-GRID ONLY" in src
    assert "during a grid outage" in src


def test_the_cli_says_off_grid_only_where_it_renders_the_threshold():
    import inspect

    from franklinwh_cloud.cli_commands import sc

    src = inspect.getsource(sc)
    assert "off-grid only" in src


def test_merge_matches_the_vendor_description():
    """SC1+SC2 merge when they share a 2-pole switch — confirmed by vendor."""
    import inspect

    from franklinwh_cloud.mixins import discover

    src = inspect.getsource(discover)
    assert "SC1+SC2" in src


# ── DEF-SC-MODE-ENUM-CONTRADICTS-SETTER ──────────────────────────────

def test_the_two_mode_mappings_are_known_to_disagree():
    """Guard, not an assertion of which is right.

    set_smart_switch_state() writes 0=OFF, 1=ON, 2=SCHEDULE.
    SMART_CIRCUIT_MODE reads 0=Manual, 1=Schedule, 2=Smart/Auto.

    They disagree on every value and cannot both be correct. This test fails
    once either is changed, forcing whoever resolves it to do so deliberately
    and to update the other.
    """
    import inspect

    from franklinwh_cloud.const.states import SMART_CIRCUIT_MODE
    from franklinwh_cloud.mixins.devices import DevicesMixin

    assert SMART_CIRCUIT_MODE == {0: "Manual", 1: "Schedule", 2: "Smart / Auto"}

    src = inspect.getsource(DevicesMixin.set_smart_switch_state)
    assert 'state_up == "SCHEDULE"' in src and "mode_val = 2" in src, (
        "the setter still maps SCHEDULE to 2, which the constant calls "
        "Smart / Auto — see DEF-SC-MODE-ENUM-CONTRADICTS-SETTER"
    )
