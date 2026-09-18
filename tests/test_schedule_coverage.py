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

def test_mode_is_on_off_not_an_operating_mode():
    """DEF-SC-MODE-ENUM-CONTRADICTS-SETTER — RESOLVED on live hardware.

    2026-09-18, circuit 1, one gateway:

        app "Turn On" off (11:57) -> Sw1Mode 0, switch_1_state 0
        app "Turn On" on  (12:00) -> Sw1Mode 1, switch_1_state 1

    SwXMode tracks the runtimeData switch state, so it is ON/OFF — which is what
    set_smart_switch_state() always wrote. The constant's old reading
    ({0: Manual, 1: Schedule, 2: Smart / Auto}) was unsourced and rendered an ON
    circuit as "Schedule". 2 is never observed; its label says so.
    """
    from franklinwh_cloud.const.states import SMART_CIRCUIT_MODE

    assert SMART_CIRCUIT_MODE[0] == "Off"
    assert SMART_CIRCUIT_MODE[1] == "On"
    assert "assumed" in SMART_CIRCUIT_MODE[2].lower(), (
        "2 has never been seen on the wire — the label must keep saying so"
    )


def test_proload_is_written_as_the_inverse_of_mode_which_hardware_contradicts():
    """DEF-SC-PROLOAD-WRITTEN-INVERTED — open, write-side, needs sign-off.

    Both live observations hold Mode and ProLoad EQUAL:

        off -> Sw1Mode 0, Sw1ProLoad 0
        on  -> Sw1Mode 1, Sw1ProLoad 1

    Every setter writes ``ProLoad = mode_val ^ 1``, a combination the gateway has
    not been observed holding in either state. Whatever ProLoad means, the
    inversion is contradicted.

    n=2, one circuit, one gateway, one hour apart — enough to refute the XOR, not
    enough to assert what ProLoad is for (AP-14). This test pins the CURRENT
    behaviour so the fix is deliberate; it fails when the setters change, which
    is the point.
    """
    import inspect

    from franklinwh_cloud.mixins.devices import DevicesMixin

    for fn in (DevicesMixin.set_smart_switch_state,
               DevicesMixin.set_smart_circuit_state):
        assert "mode_val ^ 1" in inspect.getsource(fn), (
            f"{fn.__name__} no longer inverts ProLoad — if that is the fix, update "
            "DEF-SC-PROLOAD-WRITTEN-INVERTED and delete this guard"
        )


def test_freq_zero_is_once_only():
    """DEF-SC-FREQ-UNIT — cycle interval is in DAYS, and 0 means "Once only".

    Live 2026-09-18: Sw1Freq 0 with the app showing "Cycle interval: Once only"
    and "Execution time: 18 Sept 2026", while Sw1Time carried 2026-09-18 slots.
    With zero cycles the base date IS the execution date, which is the degenerate
    case of the base + k x cycle derivation confirmed at Freq 60.
    """
    from franklinwh_cloud.mixins.discover import DiscoverMixin

    payload = {**SC_311, "Sw1Freq": 0,
               "Sw1Time": ["2026-09-18 12:00", "2026-09-18 12:01",
                           "2026-09-18 13:03", "2026-09-18 14:03"],
               "Sw1TimeEn": [1, 1, 1, 1], "Sw1TimeSet": [1, 0, 1, 0]}
    sched = DiscoverMixin._sc_schedules(payload, 1)[0]
    assert sched["base_date"] == "2026-09-18"
    assert sched["cycle_days"] == 0


# ── DEF-SC-EXECUTION-DATE-UNLOCATED — resolved ───────────────────────

def test_base_date_and_cycle_are_exposed():
    """The app's "Execution time" is derived from these, not stored."""
    payload = {**SC_311, "Sw1Freq": 60,
               "Sw1Time": ["2026-06-19 16:02", "2026-06-19 17:03",
                           "2026-06-19 17:04", "2026-06-19 17:05"]}
    out = DiscoverMixin._sc_schedules(payload, 1)
    assert out[0]["base_date"] == "2026-06-19"
    assert out[0]["cycle_days"] == 60


def test_the_derivation_reproduces_the_app_value():
    """Confirmed live: base 2026-06-19 + 2x60 days = 2026-10-17,
    which is exactly what the app displayed as Execution time."""
    from datetime import date, timedelta

    base, cycle = date(2026, 6, 19), 60
    occurrences = [base + timedelta(days=cycle * k) for k in range(3)]
    assert date(2026, 10, 17) in occurrences


def test_the_next_occurrence_is_not_computed_from_the_caller_clock():
    """It needs gateway-local "today"; the snapshot does not carry one."""
    import inspect

    src = inspect.getsource(DiscoverMixin._sc_schedules)
    assert "GATEWAY's time zone" in src
    assert "Not computed here" in src


def test_an_unset_schedule_has_no_base_date():
    payload = {**SC_311, "Sw1Time": ["2000-01-01 00:00"] * 4, "Sw1Freq": 0}
    out = DiscoverMixin._sc_schedules(payload, 1)
    assert out[0]["base_date"] is None
    assert out[0]["cycle_days"] == 0
