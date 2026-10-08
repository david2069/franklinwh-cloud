"""DEF-DIAG-GATEWAY-NONE-GUARD — null-valued keys in composite info.

`diag` failed its Gateway section with "'NoneType' object has no attribute
'get'" on live hardware. Root cause: `.get(key, default)` returns the default
only when the key is ABSENT. The API returns several of these keys PRESENT
WITH A NULL VALUE, in which case .get() hands back None.

Knock-on: the exception aborted the block before operating_mode, run_status
and soc were assigned, which is why the same report showed a blank Mode and
Run Status and SoC 0%.
"""

import json

import pytest
from unittest.mock import AsyncMock

from franklinwh_cloud.cli_commands import diag


GATEWAY_SN = "test-gateway"

FULL_COMPOSITE = {
    "result": {
        "solarHaveVo": {"isThreePhaseInstall": False},
        "runtimeData": {"run_status": 1, "soc": 47},
        "currentWorkMode": 1,
    }
}


class _NullClient:
    """diag stand-in whose composite-info payload is caller-supplied."""

    gateway = GATEWAY_SN
    edge_tracker = None
    metrics = None
    rate_limiter = None

    def __init__(self, composite):
        self._composite = composite
        self.method_cache = None

    async def get_home_gateway_list(self):
        return {"result": [{"id": GATEWAY_SN, "name": "Home",
                            "sysHdVersion": 1, "version": "1.0",
                            "protocolVer": "V1", "countryId": 1,
                            "zoneInfo": "UTC", "address": "-"}]}

    async def get_device_composite_info(self):
        return self._composite

    async def get_connectivity_overview(self, deep_scan=False):
        return {"primary": {"id": 3, "name": "WiFi"}, "backups": [],
                "signals": {}}

    async def get_network_state(self, probe_local=False):
        return {"active": {"key": "wifi"}, "interfaces": [],
                "available_transports": ["wifi"]}

    def get_metrics(self):
        return {"total_api_calls": 0, "avg_response_time_s": 0.0,
                "min_response_time_s": 0.0, "max_response_time_s": 0.0,
                "total_errors": 0, "total_rate_limits": 0, "retry_count": 0,
                "uptime_s": 0.0, "calls_by_endpoint": {}}

    def __getattr__(self, name):
        return AsyncMock(side_effect=RuntimeError(f"not mocked: {name}"))


async def _gateway_section(composite):
    """Run diag with --json and return just the gateway block."""
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        await diag.run(_NullClient(composite), json_output=True)
    return json.loads(buf.getvalue())["gateway"]


# ── the reported defect ──────────────────────────────────────────────

async def test_null_solar_have_vo_no_longer_crashes():
    """The reported failure: key present, value null."""
    gw = await _gateway_section({"result": {"solarHaveVo": None,
                                            "runtimeData": {"run_status": 1,
                                                            "soc": 47},
                                            "currentWorkMode": 1}})
    assert "error" not in gw, gw.get("error")
    assert gw["phase"] == "Single Phase (L1)"


async def test_null_runtime_data_no_longer_crashes():
    gw = await _gateway_section({"result": {"solarHaveVo": {},
                                            "runtimeData": None,
                                            "currentWorkMode": 1}})
    assert "error" not in gw, gw.get("error")


async def test_null_result_no_longer_crashes():
    gw = await _gateway_section({"result": None})
    assert "error" not in gw, gw.get("error")


async def test_every_nested_key_null_at_once():
    gw = await _gateway_section({"result": {"solarHaveVo": None,
                                            "runtimeData": None,
                                            "currentWorkMode": None}})
    assert "error" not in gw, gw.get("error")


# ── the knock-on the crash caused ────────────────────────────────────

async def test_mode_and_run_status_survive_a_null_solar_block():
    """The abort blanked these three in the original report."""
    gw = await _gateway_section({"result": {"solarHaveVo": None,
                                            "runtimeData": {"run_status": 1,
                                                            "soc": 47},
                                            "currentWorkMode": 1}})
    assert gw["operating_mode"]
    assert gw["run_status"]
    assert gw["soc"] == 47


async def test_null_run_status_does_not_break_the_int_cast():
    """int(None) would raise; run_status must degrade to 0."""
    gw = await _gateway_section({"result": {"solarHaveVo": {},
                                            "runtimeData": {"run_status": None,
                                                            "soc": None},
                                            "currentWorkMode": 1}})
    assert "error" not in gw, gw.get("error")
    assert gw["soc"] == 0


async def test_null_hardware_version_does_not_break_the_int_cast():
    class _NullHw(_NullClient):
        async def get_home_gateway_list(self):
            return {"result": [{"id": GATEWAY_SN, "sysHdVersion": None}]}

    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        await diag.run(_NullHw(FULL_COMPOSITE), json_output=True)
    gw = json.loads(buf.getvalue())["gateway"]
    assert "error" not in gw, gw.get("error")


async def test_null_gateway_list_does_not_break_iteration():
    """gw_res['result'] present but null -> `for g in None` would raise."""
    class _NullList(_NullClient):
        async def get_home_gateway_list(self):
            return {"result": None}

    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        await diag.run(_NullList(FULL_COMPOSITE), json_output=True)
    payload = json.loads(buf.getvalue())
    assert payload["connection"]["gateways_found"] == 0


# ── no regression on well-formed payloads ────────────────────────────

async def test_full_payload_still_populates_everything():
    gw = await _gateway_section(FULL_COMPOSITE)
    assert "error" not in gw
    assert gw["soc"] == 47
    assert gw["three_phase_flag"] is False
    assert gw["name"] == "Home"


async def test_three_phase_flag_still_read_correctly():
    gw = await _gateway_section({"result": {
        "solarHaveVo": {"isThreePhaseInstall": True},
        "runtimeData": {"run_status": 1, "soc": 10},
        "currentWorkMode": 1}})
    assert gw["three_phase_flag"] is True
    assert gw["phase"] == "Three Phase (L1/L2/L3)"


async def test_a_real_error_is_still_reported():
    """The guard must not swallow genuine failures."""
    class _Broken(_NullClient):
        async def get_device_composite_info(self):
            raise RuntimeError("upstream exploded")

    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        await diag.run(_Broken(None), json_output=True)
    gw = json.loads(buf.getvalue())["gateway"]
    assert gw["error"] == "upstream exploded"
