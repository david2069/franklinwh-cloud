"""FEAT-JA12-CLI-SURFACE — JA12 compliance capacity in `schema --live`.

`query_compliance_capacity()` (California Title 24 JA12) existed in `TouMixin`
but was reachable from no CLI command. It is now fetched by `schema --live`,
**gated on the gateway advertising `ja12Entrance`** so a CA-specific request is
not sent from every gateway in every market.

AP-14 note: this endpoint has **zero captured responses** in the corpus, so its
response shape is unknown. It is rendered generically rather than against a
declared schema — inventing field names for a payload nobody has observed is
what the evidence standard exists to prevent.
"""

import contextlib
import io
import json

import pytest

from franklinwh_cloud.cli_commands import schema as sch


class _Ja12Client:
    def __init__(self, ja12_entrance=1, capacity=None, capacity_error=None):
        self._entrance = {"ja12Entrance": ja12_entrance}
        self._capacity = capacity if capacity is not None else {
            "complianceCapacity": 13.6, "cycleCount": 118,
        }
        self._capacity_error = capacity_error
        self.calls = []

    async def get_entrance_info(self):
        self.calls.append("entrance")
        return {"result": self._entrance}

    async def query_compliance_capacity(self):
        self.calls.append("capacity")
        if self._capacity_error:
            raise self._capacity_error
        return self._capacity

    # Everything else schema --live touches, failing harmlessly.
    def __getattr__(self, name):
        async def _fail(*a, **k):
            raise RuntimeError(f"not mocked: {name}")
        return _fail


async def _run(client, json_output=False, filter_group=None):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        await sch.run(client, json_output=json_output, show_live=True,
                      filter_group=filter_group)
    return buf.getvalue()


# ── the gate ─────────────────────────────────────────────────────────

async def test_capacity_is_requested_when_the_gateway_advertises_ja12():
    client = _Ja12Client(ja12_entrance=1)
    await _run(client)
    assert "capacity" in client.calls


async def test_capacity_is_not_requested_without_ja12_entrance():
    """A CA-only endpoint must not be called from every market."""
    client = _Ja12Client(ja12_entrance=0)
    await _run(client)
    assert "capacity" not in client.calls


async def test_section_is_absent_when_not_advertised():
    out = await _run(_Ja12Client(ja12_entrance=0))
    assert "JA12 Compliance Capacity" not in out


# ── rendering ────────────────────────────────────────────────────────

async def test_values_are_rendered():
    out = await _run(_Ja12Client())
    assert "JA12 Compliance Capacity" in out
    assert "complianceCapacity" in out
    assert "13.6" in out


async def test_render_states_that_the_shape_is_unobserved():
    """AP-14 — the reader must know these values carry no declared schema."""
    out = await _run(_Ja12Client())
    assert "not documented" in out
    assert "capture corpus" in out


async def test_no_units_are_invented():
    """No field here has ever been observed, so no unit may be claimed."""
    out = await _run(_Ja12Client(capacity={"complianceCapacity": 13.6}))
    section = out[out.index("JA12 Compliance Capacity"):]
    assert "kWh" not in section
    assert "%" not in section


async def test_a_failing_capacity_call_does_not_break_the_command():
    out = await _run(_Ja12Client(capacity_error=RuntimeError("403")))
    assert "Could not check JA12" in out


async def test_an_empty_payload_does_not_crash():
    out = await _run(_Ja12Client(capacity={}))
    assert "JA12 Compliance Capacity" not in out or "not documented" not in out


# ── json ─────────────────────────────────────────────────────────────

async def test_json_passes_the_payload_through_verbatim():
    payload = {"complianceCapacity": 13.6, "somethingUnknown": "x"}
    out = await _run(_Ja12Client(capacity=payload), json_output=True)
    parsed = json.loads(out)
    assert parsed["ja12_compliance_capacity"] == payload


async def test_json_omits_the_key_when_not_advertised():
    out = await _run(_Ja12Client(ja12_entrance=0), json_output=True)
    assert "ja12_compliance_capacity" not in json.loads(out)


# ── filtering ────────────────────────────────────────────────────────

async def test_filter_ja12_shows_the_section():
    out = await _run(_Ja12Client(), filter_group="ja12")
    assert "JA12 Compliance Capacity" in out


async def test_an_unrelated_filter_hides_it():
    out = await _run(_Ja12Client(), filter_group="battery")
    assert "JA12 Compliance Capacity" not in out
