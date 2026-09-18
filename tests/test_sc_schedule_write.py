"""FEAT-SC-SCHEDULE-WRITE — writing a Smart Circuit time schedule.

This was evidence-blocked for a long time: the four ``SwNTime`` slots carried
no obvious pairing and the date half was twice read wrongly. Live hardware
settled every part of it on 2026-09-18:

* four slots are **two start/end pairs**, ``SwNTimeSet = [1, 0, 1, 0]``, with
  the app confirming *"Only two time slots can be scheduled"*
* ``SwNTimeEn`` arms slots individually — the app's *Time Schedule* row read
  **Off** with the bits all zero and **On** with them all one
* ``SwNFreq`` is a cycle in **days**; ``0`` is *"Once only"*
* execution date is ``base + k x cycle`` — 2026-06-19 + 2x60 = 2026-10-17,
  matching the app exactly

So the writer mirrors an observed layout rather than inventing one.
"""

import pytest
from unittest.mock import AsyncMock

from franklinwh_cloud.mixins.devices import DevicesMixin

W = [{"start": "12:00", "end": "12:01"}, {"start": "13:03", "end": "14:03"}]

LIVE_311 = {
    "Sw1Time": ["2026-09-18 12:00", "2026-09-18 12:01",
                "2026-09-18 13:03", "2026-09-18 14:03"],
    "Sw1TimeEn": [0, 0, 0, 0],
    "Sw1TimeSet": [1, 0, 1, 0],
    "Sw1Freq": 0,
    "Sw1Mode": 1,
    "Sw1ProLoad": 1,
    "Sw2Time": ["2026-01-01 08:00", "2026-01-01 09:00",
                "2026-01-01 10:00", "2026-01-01 11:00"],
    "Sw3Time": ["2000-01-01 00:00"] * 4,
}


class _Client(DevicesMixin):
    gateway = "test-gw"
    url_base = "https://example.invalid/"

    def __init__(self, stores=True, readback_error=None, payload=None):
        self.updates = []
        self._stores = stores
        self._readback_error = readback_error
        self._payload = dict(payload if payload is not None else LIVE_311)
        self._reads = 0

    async def get_smart_circuits_info(self):
        self._reads += 1
        # The first read is the read-modify-write fetch; later ones are the
        # verify read-back.
        if self._reads > 1 and self._readback_error:
            raise self._readback_error
        state = dict(self._payload)
        if self._stores:
            for u in self.updates:
                state.update(u)
        return state

    async def _update_smart_circuit_config(self, circuit, updates):
        self.updates.append(dict(updates))
        return {"result": 0}

    @property
    def last(self):
        return self.updates[-1]


# ── guards ───────────────────────────────────────────────────────────

async def test_refuses_without_confirm():
    with pytest.raises(ValueError, match="confirm=True"):
        await _Client().set_smart_circuit_schedule(1, W)


async def test_rejects_a_bad_circuit():
    with pytest.raises(ValueError, match="Circuit must be"):
        await _Client().set_smart_circuit_schedule(4, W, confirm=True)


async def test_rejects_more_than_two_windows():
    three = W + [{"start": "20:00", "end": "21:00"}]
    with pytest.raises(ValueError, match="at most 2"):
        await _Client().set_smart_circuit_schedule(1, three, confirm=True)


async def test_rejects_a_window_spanning_midnight():
    with pytest.raises(ValueError, match="midnight"):
        await _Client().set_smart_circuit_schedule(
            1, [{"start": "23:00", "end": "01:00"}], confirm=True)


async def test_rejects_overlapping_windows():
    clash = [{"start": "12:00", "end": "14:00"}, {"start": "13:00", "end": "15:00"}]
    with pytest.raises(ValueError, match="overlap"):
        await _Client().set_smart_circuit_schedule(1, clash, confirm=True)


async def test_a_disabled_window_may_overlap():
    """Only armed windows can collide — a disarmed one is not running."""
    ok = [{"start": "12:00", "end": "14:00"},
          {"start": "13:00", "end": "15:00", "enabled": False}]
    res = await _Client().set_smart_circuit_schedule(1, ok, confirm=True)
    assert res["verified"] is True


@pytest.mark.parametrize("bad", ["9:00", "0900", "24:00", "12:60", None, 900])
async def test_rejects_malformed_times(bad):
    with pytest.raises(ValueError):
        await _Client().set_smart_circuit_schedule(
            1, [{"start": bad, "end": "23:00"}], confirm=True)


@pytest.mark.parametrize("bad", ["18-09-2026", "2026/09/18", "not-a-date", 20260918])
async def test_rejects_a_malformed_base_date(bad):
    with pytest.raises(ValueError, match="base_date"):
        await _Client().set_smart_circuit_schedule(1, W, base_date=bad, confirm=True)


@pytest.mark.parametrize("bad", [-1, 1.5, True, "60"])
async def test_rejects_a_bad_cycle(bad):
    with pytest.raises(ValueError, match="cycle_days"):
        await _Client().set_smart_circuit_schedule(1, W, cycle_days=bad, confirm=True)


# ── the observed layout ──────────────────────────────────────────────

async def test_writes_two_pairs_in_the_observed_order():
    c = _Client()
    await c.set_smart_circuit_schedule(1, W, confirm=True)
    assert c.last["Sw1Time"] == ["2026-09-18 12:00", "2026-09-18 12:01",
                                 "2026-09-18 13:03", "2026-09-18 14:03"]
    assert c.last["Sw1TimeEn"] == [1, 1, 1, 1]
    assert c.last["Sw1TimeSet"] == [1, 0, 1, 0], "pairing is open, close, open, close"


async def test_one_window_disarms_the_second_pair():
    c = _Client()
    await c.set_smart_circuit_schedule(1, W[:1], confirm=True)
    assert c.last["Sw1TimeEn"] == [1, 1, 0, 0]


async def test_an_empty_list_disarms_without_discarding_the_times():
    """Switching a schedule off is not the same as deleting it.

    Live hardware kept Sw1Time and Sw1TimeSet across a turn-off and moved only
    the enable bits, so this mirrors that rather than blanking the slots.
    """
    c = _Client()
    await c.set_smart_circuit_schedule(1, [], confirm=True)
    assert c.last["Sw1TimeEn"] == [0, 0, 0, 0]
    assert c.last["Sw1Time"] == LIVE_311["Sw1Time"], "the configured times survive"


async def test_the_switch_is_not_touched():
    """Arming a schedule must not flip the circuit.

    Mode/ProLoad are deliberately absent: the setters that write them disagree
    with hardware (DEF-SC-PROLOAD-WRITTEN-INVERTED), and a schedule write has
    no business changing the switch.
    """
    c = _Client()
    await c.set_smart_circuit_schedule(1, W, confirm=True)
    assert not [k for k in c.last if "Mode" in k or "ProLoad" in k]


async def test_other_circuits_are_not_touched():
    c = _Client()
    await c.set_smart_circuit_schedule(1, W, confirm=True)
    assert all(k.startswith("Sw1") for k in c.last)


# ── dates and cycle ──────────────────────────────────────────────────

async def test_the_existing_date_is_preserved_by_default():
    c = _Client()
    await c.set_smart_circuit_schedule(2, W, confirm=True)
    assert [s.split(" ")[0] for s in c.last["Sw2Time"]] == ["2026-01-01"] * 4


async def test_base_date_overrides_every_slot():
    c = _Client()
    await c.set_smart_circuit_schedule(1, W, base_date="2026-12-25", confirm=True)
    assert [s.split(" ")[0] for s in c.last["Sw1Time"]] == ["2026-12-25"] * 4


async def test_a_placeholder_date_demands_an_explicit_one():
    """No date is invented.

    With cycle_days=0 the base date IS the execution date, so guessing "today"
    from the client clock would write a schedule that silently never fires on a
    gateway in another time zone.
    """
    c = _Client()
    with pytest.raises(ValueError, match="base_date"):
        await c.set_smart_circuit_schedule(3, W, confirm=True)


async def test_a_placeholder_slot_is_fine_once_a_date_is_given():
    c = _Client()
    res = await c.set_smart_circuit_schedule(3, W, base_date="2026-10-01", confirm=True)
    assert res["verified"] is True
    assert c.last["Sw3Time"][0] == "2026-10-01 12:00"


async def test_cycle_days_is_written_only_when_asked():
    c = _Client()
    await c.set_smart_circuit_schedule(1, W, confirm=True)
    assert "Sw1Freq" not in c.last
    await c.set_smart_circuit_schedule(1, W, cycle_days=60, confirm=True)
    assert c.last["Sw1Freq"] == 60


async def test_cycle_zero_is_once_only_and_is_writable():
    """0 is a real value, not "unset" — it means Once only."""
    c = _Client()
    await c.set_smart_circuit_schedule(1, W, cycle_days=0, confirm=True)
    assert c.last["Sw1Freq"] == 0


# ── an ack is not a confirmation ─────────────────────────────────────

async def test_a_gateway_that_does_not_store_is_reported_unverified():
    c = _Client(stores=False)
    res = await c.set_smart_circuit_schedule(1, W, confirm=True)
    assert res["verified"] is False
    assert res["mismatches"], "a silent discard must be named, not swallowed"
    assert "NOT in effect" in res["note"]


async def test_a_failed_readback_is_unknown_not_success():
    c = _Client(readback_error=RuntimeError("gateway offline"))
    res = await c.set_smart_circuit_schedule(1, W, confirm=True)
    assert res["verified"] is None, "could not check is not the same as passed"
    assert "read-back failed" in res["note"]


async def test_verify_false_reports_unknown_rather_than_true():
    c = _Client()
    res = await c.set_smart_circuit_schedule(1, W, confirm=True, verify=False)
    assert res["verified"] is None
    assert "ack alone" in res["note"]


async def test_a_stored_write_verifies():
    c = _Client()
    res = await c.set_smart_circuit_schedule(1, W, confirm=True)
    assert res["verified"] is True and res["mismatches"] == []


# ── CLI surface ──────────────────────────────────────────────────────

def test_window_spec_parsing():
    from franklinwh_cloud.cli_commands.sc import _parse_sc_window
    assert _parse_sc_window("12:00-13:30") == {"start": "12:00", "end": "13:30"}
    assert _parse_sc_window(" 12:00 - 13:30 ") == {"start": "12:00", "end": "13:30"}
    # An en-dash is what a phone keyboard and a copy-paste from the app produce.
    assert _parse_sc_window("12:00–13:30") == {"start": "12:00", "end": "13:30"}


@pytest.mark.parametrize("bad", ["12:00 to 13:00", "1200 1300", ""])
def test_window_spec_rejects_junk(bad):
    from franklinwh_cloud.cli_commands.sc import _parse_sc_window
    with pytest.raises(ValueError, match="START-END"):
        _parse_sc_window(bad)


def test_the_doubtful_mode_flag_says_so():
    """`sc --schedule` writes SwNMode=2, which may not be a real value.

    A circuit with a schedule configured and armed reads Mode 0 or 1 and never
    2 (live, 2026-09-18), so the help must not present it as the way to set a
    schedule while --set-schedule exists.
    """
    import argparse
    from franklinwh_cloud import cli

    parser = cli.build_parser() if hasattr(cli, "build_parser") else None
    if parser is None:
        import inspect
        src = inspect.getsource(cli)
        i = src.index('"--schedule", type=int, metavar="CIRCUIT"')
        block = src[i:i + 500]
        assert "DOUBTFUL" in block
        assert "--set-schedule" in block
