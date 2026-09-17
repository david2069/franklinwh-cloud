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


def test_the_pairing_is_declared_unverified():
    """Four entries may be two windows or four slots — unestablished."""
    out = DiscoverMixin._sc_schedules(SC_311, 2)
    assert out[0]["pairing"] == "unverified"


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
