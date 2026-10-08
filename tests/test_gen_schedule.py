"""FEAT-GEN-CHARGE-SCHEDULE — writing the generator charge windows.

Unlike Smart Circuit schedules, this is not evidence-blocked: the fields are
plainly named and a real write is in the capture corpus::

    {"charge1En": 1, "charge1StartTime": "11:00", "charge1EndTime": "23:59",
     "charge2En": 0, "charge3En": 0, "opt": 1}

The implementation mirrors that shape rather than inventing one.
"""

import contextlib
import io

import pytest
from unittest.mock import AsyncMock

from franklinwh_cloud.mixins.devices import DevicesMixin

W = [{"start": "11:00", "end": "23:59"}]


class _Client(DevicesMixin):
    gateway = "test-gw"
    url_base = "https://example.invalid/"

    def __init__(self, stores=True, readback_error=None):
        self.sent = []
        self._stores = stores            # does the gateway keep what it accepts?
        self._readback_error = readback_error
        self._post = AsyncMock(side_effect=self._capture)

    async def _capture(self, url, params=None, payload=None):
        self.sent.append(payload)
        return {"result": {"ok": True}}

    async def get_generator_info(self):
        """Read-back. A rejecting gateway acks and stores nothing."""
        if self._readback_error:
            raise self._readback_error
        if not self.sent:
            return {}
        if not self._stores:
            return {"charge1En": 0, "charge2En": 0, "charge3En": 0}
        return dict(self.sent[-1])


# ── the guard ────────────────────────────────────────────────────────

async def test_refuses_without_confirm():
    c = _Client()
    with pytest.raises(ValueError, match="confirm=True"):
        await c.set_generator_charge_schedule(W)
    assert c.sent == []


# ── payload shape mirrors the capture ────────────────────────────────

async def test_payload_matches_the_captured_shape():
    c = _Client()
    await c.set_generator_charge_schedule(W, confirm=True)
    p = c.sent[0]
    assert p["charge1En"] == 1
    assert p["charge1StartTime"] == "11:00"
    assert p["charge1EndTime"] == "23:59"
    assert p["charge2En"] == 0 and p["charge3En"] == 0
    assert p["opt"] == 1


async def test_disabled_windows_carry_no_times():
    """The app sends only chargeNEn for a disabled window."""
    c = _Client()
    await c.set_generator_charge_schedule(W, confirm=True)
    p = c.sent[0]
    assert "charge2StartTime" not in p
    assert "charge3EndTime" not in p


async def test_all_three_windows_can_be_set():
    c = _Client()
    await c.set_generator_charge_schedule([
        {"start": "06:00", "end": "09:00"},
        {"start": "12:00", "end": "14:00"},
        {"start": "17:00", "end": "21:00"},
    ], confirm=True)
    p = c.sent[0]
    assert [p[f"charge{i}En"] for i in (1, 2, 3)] == [1, 1, 1]
    assert p["charge3StartTime"] == "17:00"


async def test_an_empty_list_disables_everything():
    c = _Client()
    await c.set_generator_charge_schedule([], confirm=True)
    p = c.sent[0]
    assert [p[f"charge{i}En"] for i in (1, 2, 3)] == [0, 0, 0]


async def test_an_explicitly_disabled_window_is_sent_off():
    c = _Client()
    await c.set_generator_charge_schedule(
        [{"start": "06:00", "end": "09:00", "enabled": False}], confirm=True)
    assert c.sent[0]["charge1En"] == 0
    assert "charge1StartTime" not in c.sent[0]


# ── validation the backend may not do ────────────────────────────────

async def test_overlapping_windows_are_rejected():
    """The app does not let a user enter these, so the backend may not check."""
    c = _Client()
    with pytest.raises(ValueError, match="overlap"):
        await c.set_generator_charge_schedule([
            {"start": "06:00", "end": "12:00"},
            {"start": "11:00", "end": "14:00"},
        ], confirm=True)
    assert c.sent == []


async def test_adjacent_windows_are_allowed():
    """Touching is not overlapping — 09:00 end, 09:00 start is fine."""
    c = _Client()
    await c.set_generator_charge_schedule([
        {"start": "06:00", "end": "09:00"},
        {"start": "09:00", "end": "12:00"},
    ], confirm=True)
    assert c.sent[0]["charge2En"] == 1


async def test_a_disabled_window_cannot_cause_an_overlap_error():
    c = _Client()
    await c.set_generator_charge_schedule([
        {"start": "06:00", "end": "12:00"},
        {"start": "11:00", "end": "14:00", "enabled": False},
    ], confirm=True)
    assert c.sent[0]["charge1En"] == 1


async def test_midnight_spanning_is_rejected_as_unverified():
    """No such window has been observed; behaviour is unknown."""
    c = _Client()
    with pytest.raises(ValueError, match="before end"):
        await c.set_generator_charge_schedule(
            [{"start": "22:00", "end": "02:00"}], confirm=True)


@pytest.mark.parametrize("bad", ["9:00", "0900", "25:00", "06:60", "", None, 600])
async def test_malformed_times_are_rejected(bad):
    c = _Client()
    with pytest.raises(ValueError):
        await c.set_generator_charge_schedule(
            [{"start": bad, "end": "09:00"}], confirm=True)
    assert c.sent == []


async def test_more_than_three_windows_is_rejected():
    c = _Client()
    with pytest.raises(ValueError, match="at most 3"):
        await c.set_generator_charge_schedule(
            [{"start": f"0{i}:00", "end": f"0{i}:30"} for i in range(1, 5)],
            confirm=True)


# ── the timezone hazard ──────────────────────────────────────────────

def test_the_docstring_says_times_are_gateway_local():
    """The likeliest way to get this wrong from another time zone."""
    import inspect

    src = inspect.getsource(DevicesMixin.set_generator_charge_schedule)
    assert "gateway-local" in src
    assert "Nothing is converted here" in src


# ── CLI ──────────────────────────────────────────────────────────────

async def _cli(client, **kw):
    from franklinwh_cloud.cli_commands import gen

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = await gen.run(client, **kw)
    return rc, buf.getvalue()


async def test_cli_writes_the_requested_window():
    c = _Client()
    rc, out = await _cli(c, json_output=True, schedule=["11:00-23:59"],
                         assume_yes=True)
    assert rc == 0
    assert c.sent[0]["charge1StartTime"] == "11:00"


async def test_cli_off_disables_all():
    c = _Client()
    await _cli(c, json_output=True, schedule=["off"], assume_yes=True)
    assert [c.sent[0][f"charge{i}En"] for i in (1, 2, 3)] == [0, 0, 0]


async def test_cli_warns_about_gateway_local_time():
    c = _Client()
    _, out = await _cli(c, json_output=False, schedule=["11:00-23:59"],
                        assume_yes=True)
    assert "GATEWAY's local wall clock" in out


async def test_cli_rejects_a_malformed_spec():
    c = _Client()
    with pytest.raises(ValueError, match="START-END"):
        await _cli(c, json_output=True, schedule=["1100 2359"], assume_yes=True)
    assert c.sent == []


def test_cli_flags_are_registered():
    from franklinwh_cloud.cli import build_parser

    ns = build_parser().parse_args(
        ["gen", "--schedule", "06:00-09:00", "--schedule", "17:00-21:00", "-y"])
    assert ns.schedule == ["06:00-09:00", "17:00-21:00"]
    assert ns.yes is True


# ── DEF-WRITES-NOT-VERIFIED: an ack is not a confirmation ────────────

async def test_a_stored_schedule_verifies():
    c = _Client(stores=True)
    r = await c.set_generator_charge_schedule(W, confirm=True)
    assert r["verified"] is True
    assert r["mismatches"] == []


async def test_a_silently_rejected_schedule_is_caught():
    """The gateway accepts the write and keeps nothing — the whole point."""
    c = _Client(stores=False)
    r = await c.set_generator_charge_schedule(W, confirm=True)
    assert r["verified"] is False
    assert any(m["field"] == "charge1En" for m in r["mismatches"])
    assert "NOT in effect" in r["note"]


async def test_the_ack_alone_is_never_reported_as_success():
    """Before this, the ack WAS the return value."""
    c = _Client(stores=False)
    r = await c.set_generator_charge_schedule(W, confirm=True)
    assert r["ack"], "the ack is still reported"
    assert r["verified"] is False, "but it is not what success means"


async def test_a_failed_read_back_is_unknown_not_verified():
    """"Could not check" must not read as "passed"."""
    c = _Client(readback_error=RuntimeError("timeout"))
    r = await c.set_generator_charge_schedule(W, confirm=True)
    assert r["verified"] is None
    assert "read-back failed" in r["note"]


async def test_verification_can_be_skipped_but_says_so():
    c = _Client(stores=True)
    r = await c.set_generator_charge_schedule(W, confirm=True, verify=False)
    assert r["verified"] is None
    assert "does not mean stored" in r["note"]


async def test_disabled_windows_are_not_compared_on_fields_never_sent():
    """Only En is sent for a disabled window, so times must not be diffed."""
    c = _Client(stores=True)
    r = await c.set_generator_charge_schedule(W, confirm=True)
    assert not any("charge2StartTime" in m["field"] for m in r["mismatches"])
