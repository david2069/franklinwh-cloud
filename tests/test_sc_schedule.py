"""Smart Circuit schedules — DEF-SC-SCHEDULE-NOT-RENDERED.

`SmartCircuitDetail` parses the V2 schedule arrays (`SwNTime`, `SwNTimeEn`,
`SwNTimeSet`) and `sc --json` emits them, but the terminal renderer only handled
the legacy V1 `open_time`/`close_time` integers. The firmware in the capture
corpus sends **only** the V2 arrays — no `SwNOpenTime` field exists in its
cmdType 311 payload — so `franklinwh-cli sc` displayed no schedule at all.
"""

import contextlib
import inspect
import io
import json

import pytest

from franklinwh_cloud.models import SmartCircuitDetail


# Shape taken from the corpus, not invented.
V2_PAYLOAD = {
    "Sw1Mode": 1, "Sw1Name": "Circuit 1", "Sw1ProLoad": 1,
    "Sw1SocLowSet": 20, "Sw1MsgType": 0,
    "Sw1Time": ["2000-01-01 06:30", "2000-01-01 09:00",
                "2000-01-01 17:00", "2000-01-01 21:30"],
    "Sw1TimeEn": [1, 1, 0, 0],
    "Sw1TimeSet": [1, 0, 1, 0],
}


def test_the_model_parses_the_v2_arrays():
    d = SmartCircuitDetail.from_api_payload(V2_PAYLOAD, 1)
    assert d.time_schedules == V2_PAYLOAD["Sw1Time"]
    assert d.time_enabled == [1, 1, 0, 0]
    assert d.time_set == [1, 0, 1, 0]


def test_the_corpus_firmware_sends_no_legacy_fields():
    """Which is why rendering only V1 showed nothing."""
    d = SmartCircuitDetail.from_api_payload(V2_PAYLOAD, 1)
    assert d.open_time is None
    assert d.close_time is None


# ── rendering ────────────────────────────────────────────────────────

class _ScClient:
    async def get_smart_circuits(self):
        return {1: SmartCircuitDetail.from_api_payload(V2_PAYLOAD, 1)}

    def __getattr__(self, name):
        async def _fail(*a, **k):
            raise RuntimeError(f"not mocked: {name}")
        return _fail


async def _render(json_output=False):
    from franklinwh_cloud.cli_commands import sc

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        await sc.run(_ScClient(), json_output=json_output)
    return buf.getvalue()


async def test_schedule_times_are_now_visible():
    out = await _render()
    assert "06:30" in out
    assert "21:30" in out


async def test_enabled_state_is_shown_per_slot():
    out = await _render()
    assert "(on)" in out
    assert "(off)" in out


async def test_the_placeholder_date_is_not_shown():
    """Every sample carries '2000-01-01'; only the wall clock is meaningful."""
    out = await _render()
    assert "2000-01-01" not in out


async def test_the_pairing_is_not_asserted():
    """AP-14 — whether four entries are two windows has never been confirmed."""
    out = await _render()
    assert "pairing unverified" in out
    assert "→" not in out.split("Schedule slots")[-1].split("\n")[0], (
        "must not render slots as start → end windows"
    )


async def test_an_all_disabled_schedule_says_so():
    """The corpus default: times present, every flag 0."""
    from franklinwh_cloud.cli_commands import sc

    payload = {**V2_PAYLOAD, "Sw1TimeEn": [0, 0, 0, 0]}

    class _C(_ScClient):
        async def get_smart_circuits(self):
            return {1: SmartCircuitDetail.from_api_payload(payload, 1)}

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        await sc.run(_C(), json_output=False)
    assert "schedule inactive" in buf.getvalue()


async def test_json_still_carries_the_raw_arrays():
    out = await _render(json_output=True)
    parsed = json.loads(out)
    assert parsed["1"]["time_schedules"] == V2_PAYLOAD["Sw1Time"]


# ── the write gap ────────────────────────────────────────────────────

def test_no_schedule_setter_exists_yet():
    """Documents the gap: mode can be set to SCHEDULE, the windows cannot.

    Update this test when FEAT-SC-SCHEDULE-SETTER lands.
    """
    from franklinwh_cloud.client import Client

    assert hasattr(Client, "set_smart_switch_state")
    setters = [n for n in dir(Client)
               if n.startswith("set_smart") and "time" in n.lower()]
    assert setters == [], f"a schedule setter appeared: {setters}"
