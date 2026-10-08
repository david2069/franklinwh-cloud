"""DEF-DISCOVER-TOU-WRONG-ENDPOINT — TOU fields read from the wrong endpoint.

Reported by the FWHAI agent as "pto_date is always empty". Confirmed, and it
was one symptom of a larger fault: `discover()` read five fields from
`get_gateway_tou_list()`, but the two TOU endpoints carry **disjoint** field
sets. Measured over the HAR corpus:

    getGatewayTouListV2   n=1271   vppSocVo 98%, todayVppVo 100%
                                   ptoDate / nemType / template  0%
    getTouDispatchDetail  n=672    ptoDate 72%, nemType 100%, template 100%
                                   vppSocVo / todayVppVo  0%

So pto_date, electric_company, tariff_name, der_schedule and nem_type could
never populate — while the two VPP fields worked. Swapping wholesale to the
detail endpoint, as originally proposed, would have inverted the bug.
"""

import pytest

from franklinwh_cloud.mixins.discover import DiscoverMixin


class _TouClient:
    """Serves each endpoint its own payload, as the real API does."""

    def __init__(self, list_result=None, detail_result=None,
                 list_error=None, detail_error=None):
        self._list = list_result if list_result is not None else {}
        self._detail = detail_result if detail_result is not None else {}
        self._list_error = list_error
        self._detail_error = detail_error
        self.calls = []

    async def get_gateway_tou_list(self):
        self.calls.append("list")
        if self._list_error:
            raise self._list_error
        return {"result": self._list}

    async def get_tou_dispatch_detail(self):
        self.calls.append("detail")
        if self._detail_error:
            raise self._detail_error
        return {"result": self._detail}


# Shapes taken from the corpus, not invented.
LIST_PAYLOAD = {
    "vppSocVo": {"vppSoc": 30.0, "vppMinSoc": 10.0, "vppMaxSoc": 95.0},
    "todayVppVo": {"vppFlag": 1},
}
DETAIL_PAYLOAD = {
    "ptoDate": "2022-07-06",
    "nemType": 2,
    "template": {
        "electricCompany": "Ausgrid",
        "name": "EA11 TOU",
        "derSchdule": "AS4777",
        # Present and NULL in every captured sample.
        "ptoDate": None,
    },
}


class _DiscoverClient(DiscoverMixin):
    """Drives the REAL discover() tier-3 path.

    Only the two TOU endpoints return data; every other call raises and is
    swallowed by discover()'s per-section try/except. Deliberately exercising
    production code rather than a copy of it — a test that re-implements the
    logic passes even when the implementation is deleted.
    """

    gateway = "test-gateway"

    def __init__(self, list_result=None, detail_result=None,
                 list_error=None, detail_error=None):
        self._list = list_result if list_result is not None else {}
        self._detail = detail_result if detail_result is not None else {}
        self._list_error = list_error
        self._detail_error = detail_error
        self.calls = []

    async def get_gateway_tou_list(self):
        self.calls.append("list")
        if self._list_error:
            raise self._list_error
        return {"result": self._list}

    async def get_tou_dispatch_detail(self):
        self.calls.append("detail")
        if self._detail_error:
            raise self._detail_error
        return {"result": self._detail}

    def __getattr__(self, name):
        async def _fail(*a, **k):
            raise RuntimeError(f"not mocked: {name}")
        return _fail


async def _run(client):
    return await client.discover(tier=3)


# ── the reported defect ──────────────────────────────────────────────

async def test_pto_date_populates_from_the_detail_endpoint():
    snap = await _run(_DiscoverClient(LIST_PAYLOAD, DETAIL_PAYLOAD))
    assert snap.site.pto_date == "2022-07-06"


async def test_pto_date_is_empty_if_only_the_list_endpoint_is_consulted():
    """The original bug: the list endpoint has never carried ptoDate."""
    snap = await _run(_DiscoverClient(LIST_PAYLOAD, {}))
    assert snap.site.pto_date == ""


# ── the three fields the report did not mention ──────────────────────

async def test_tariff_fields_populate():
    snap = await _run(_DiscoverClient(LIST_PAYLOAD, DETAIL_PAYLOAD))
    assert snap.site.electric_company == "Ausgrid"
    assert snap.site.tariff_name == "EA11 TOU"
    assert snap.site.der_schedule == "AS4777"


async def test_nem_label_is_not_asserted_outside_the_us():
    """NEM is a US scheme; 0 must not render as "NEM 2.0" on an AU system.

    Raised by the FWHAI agent. Corpus: 661 samples of nemType=0 on a gateway
    whose country is Australia and whose retailer is Amber. Whether 0 is a
    genuine NEM 2.0 or an unset sentinel is still open, but either way the
    label is wrong here — so assert nothing and keep the raw value.
    """
    client = _DiscoverClient(LIST_PAYLOAD, DETAIL_PAYLOAD)
    snap = await _run(client)

    assert snap.flags.nem_type == "", "no scheme may be claimed outside the US"
    assert snap.flags.nem_type_raw == 2, "the wire value must survive"


async def test_the_raw_value_is_kept_even_when_unlabelled():
    """The open question needs the number, so blanking must not discard it."""
    snap = await _run(_DiscoverClient(LIST_PAYLOAD, {"nemType": 0}))
    assert snap.flags.nem_type == ""
    assert snap.flags.nem_type_raw == 0


async def test_absent_nem_type_leaves_the_flag_alone():
    """With nemType missing, nothing is claimed and nothing is invented."""
    snap = await _run(_DiscoverClient(LIST_PAYLOAD, {"template": {}}))
    assert snap.flags.nem_type == ""
    assert snap.flags.nem_type_raw is None


# ── the regression the proposed fix would have caused ────────────────

async def test_vpp_fields_still_come_from_the_list_endpoint():
    """Swapping wholesale to the detail endpoint would have broken these."""
    snap = await _run(_DiscoverClient(LIST_PAYLOAD, DETAIL_PAYLOAD))
    assert snap.flags.vpp_enrolled is True
    assert snap.programmes.vpp_soc == 30.0
    assert snap.programmes.vpp_max_soc == 95.0


async def test_detail_only_would_lose_vpp():
    """Proves the two sets are disjoint, so one call cannot serve both."""
    snap = await _run(_DiscoverClient({}, DETAIL_PAYLOAD))
    assert snap.site.pto_date == "2022-07-06"
    assert snap.flags.vpp_enrolled is False


# ── independence and resilience ──────────────────────────────────────

async def test_both_endpoints_are_called():
    """The list endpoint is consulted elsewhere in discover() too, so assert
    membership rather than an exact sequence."""
    client = _DiscoverClient(LIST_PAYLOAD, DETAIL_PAYLOAD)
    await _run(client)
    assert "list" in client.calls
    assert "detail" in client.calls


async def test_a_failing_list_call_does_not_cost_the_tariff_fields():
    snap = await _run(_DiscoverClient(list_error=RuntimeError("boom"),
                                 detail_result=DETAIL_PAYLOAD))
    assert snap.site.pto_date == "2022-07-06"
    assert snap.flags.vpp_enrolled is False


async def test_a_failing_detail_call_does_not_cost_vpp():
    snap = await _run(_DiscoverClient(list_result=LIST_PAYLOAD,
                                 detail_error=RuntimeError("boom")))
    assert snap.flags.vpp_enrolled is True
    assert snap.site.pto_date == ""


async def test_null_template_pto_date_does_not_crash_the_fallback():
    """template.ptoDate is present-and-null in every captured sample."""
    snap = await _run(_DiscoverClient(LIST_PAYLOAD,
                                 {"template": {"ptoDate": None}}))
    assert snap.site.pto_date == ""


async def test_discover_calls_the_detail_endpoint():
    """Guard against the call site regressing to the list endpoint."""
    import inspect

    from franklinwh_cloud.mixins.discover import DiscoverMixin

    src = inspect.getsource(DiscoverMixin)
    assert "get_tou_dispatch_detail()" in src
