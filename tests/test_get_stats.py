"""Tests for get_stats — response parsing, conditional API calls, empty fallback.

Uses respx to mock httpx responses without hitting the real API.
"""

import json

import pytest
import respx
import httpx

from franklinwh_cloud.client import Client, Stats, Current, Totals
from franklinwh_cloud.metrics import ClientMetrics


# ── Sample Data ──────────────────────────────────────────────────────

SAMPLE_RUNTIME = {
    "p_sun": 5.23,
    "p_gen": 0.0,
    "p_fhp": -2.1,
    "p_uti": 0.5,
    "p_load": 3.63,
    "soc": 85.0,
    "genEn": 0,
    "genStat": 0,
    "run_status": 2,
    "mode": 10001,
    "name": "Solar Export",
    "offgridreason": 0,
    "offGridFlag": 0,
    "pro_load": [1, 0, 0],
    "v2lModeEnable": 0,
    "v2lRunState": 0,
    "fhpSn": ["AP2-001"],
    "fhpSoc": [85.0],
    "fhpPower": [-2.1],
    "bms_work": [2],
    "t_amb": 28.5,
    "signal": 75.0,
    "wifiSignal": -45.0,
    "connType": 1,
    "gridChBat": 0.0,
    "soOutGrid": 1.2,
    "soChBat": 0.8,
    "batOutGrid": 0.0,
    "apbox20Pv": 0.0,
    "remoteSolarEn": 0,
    "mpptSta": 0,
    "mpptAllPower": 0.0,
    "mpptActPower": 0.0,
    "mPanPv1Power": 0.0,
    "mPanPv2Power": 0.0,
    "remoteSolar1Power": 0.0,
    "remoteSolar2Power": 0.0,
    "kwh_fhp_chg": 10.5,
    "kwh_fhp_di": 8.2,
    "kwh_uti_in": 3.1,
    "kwh_uti_out": 5.4,
    "kwh_sun": 22.7,
    "kwh_gen": 0.0,
    "kwh_load": 18.3,
    "kwhSolarLoad": 12.1,
    "kwhGridLoad": 2.5,
    "kwhFhpLoad": 3.7,
    "kwhGenLoad": 0.0,
    "mpanPv1Wh": 0.0,
    "mpanPv2Wh": 0.0,
}

SAMPLE_SWITCH_DATA = {
    "SW1ExpPower": 0.45,
    "SW2ExpPower": 0.0,
    "CarSWPower": 0.0,
    "SW1ExpEnergy": 2.3,
    "SW2ExpEnergy": 0.0,
    "CarSWExpEnergy": 0.0,
    "CarSWImpEnergy": 0.0,
}


class TestGetStatsResponseParsing:
    """get_stats correctly parses API responses into Stats dataclass."""

    @pytest.fixture
    async def mock_client(self):
        """Create a Client with mocked httpx transport."""
        async with httpx.AsyncClient() as session:
            c = Client.__new__(Client)
            c.gateway = "TEST-GW-001"
            c.snno = 0
            c.url_base = "https://energy.franklinwh.com/"
            c.token = "test-token"
            c.session = session
            c.fetcher = None
            c.metrics = ClientMetrics()
            c.rate_limiter = None
            c.stale_cache = None
            c.edge_tracker = None
            yield c

    @respx.mock
    async def test_returns_stats_type(self, mock_client):
        """get_stats should return a Stats namedtuple."""
        respx.get(
            "https://energy.franklinwh.com/hes-gateway/terminal/getDeviceCompositeInfo"
        ).mock(return_value=httpx.Response(200, json={
            "code": 200,
            "result": {"currentWorkMode": 1, "runtimeData": SAMPLE_RUNTIME},
        }))
        # Mock switch usage (MQTT via POST)
        respx.post(
            "https://energy.franklinwh.com/hes-gateway/terminal/sendMqtt"
        ).mock(return_value=httpx.Response(200, json={
            "code": 200,
            "result": {"dataArea": json.dumps(SAMPLE_SWITCH_DATA)},
        }))

        stats = await mock_client.get_stats()
        assert isinstance(stats, Stats)
        assert isinstance(stats.current, Current)
        assert isinstance(stats.totals, Totals)

    @respx.mock
    async def test_parses_current_power(self, mock_client):
        """Current power values are correctly extracted."""
        respx.get(
            "https://energy.franklinwh.com/hes-gateway/terminal/getDeviceCompositeInfo"
        ).mock(return_value=httpx.Response(200, json={
            "code": 200,
            "result": {
                "currentWorkMode": 1,
                "runtimeData": {**SAMPLE_RUNTIME, "pro_load": [0, 0, 0]},
            },
        }))

        stats = await mock_client.get_stats()
        assert stats.current.solar_production == 5.23
        assert stats.current.battery_use == -2.1
        assert stats.current.grid_use == 0.5
        assert stats.current.home_load == 3.63
        assert stats.current.battery_soc == 85.0

    @respx.mock
    async def test_parses_totals(self, mock_client):
        """Daily totals are correctly extracted."""
        respx.get(
            "https://energy.franklinwh.com/hes-gateway/terminal/getDeviceCompositeInfo"
        ).mock(return_value=httpx.Response(200, json={
            "code": 200,
            "result": {
                "currentWorkMode": 1,
                "runtimeData": {**SAMPLE_RUNTIME, "pro_load": [0, 0, 0]},
            },
        }))

        stats = await mock_client.get_stats()
        assert stats.totals.battery_charge == 10.5
        assert stats.totals.battery_discharge == 8.2
        assert stats.totals.grid_import == 3.1
        assert stats.totals.grid_export == 5.4
        assert stats.totals.solar == 22.7
        assert stats.totals.home_use == 18.3

    @respx.mock
    async def test_empty_result_returns_empty_stats(self, mock_client):
        """Empty API result should return empty_stats() fallback."""
        from franklinwh_cloud.client import empty_stats

        respx.get(
            "https://energy.franklinwh.com/hes-gateway/terminal/getDeviceCompositeInfo"
        ).mock(return_value=httpx.Response(200, json={
            "code": 200,
            "result": None,
        }))

        stats = await mock_client.get_stats()
        expected = empty_stats()
        assert stats.current.solar_production == expected.current.solar_production


class TestGetStatsConditionalCalls:
    """get_stats conditionally fetches switch_usage and power_info."""

    @pytest.fixture
    async def mock_client(self):
        async with httpx.AsyncClient() as session:
            c = Client.__new__(Client)
            c.gateway = "TEST-GW-001"
            c.snno = 0
            c.url_base = "https://energy.franklinwh.com/"
            c.token = "test-token"
            c.session = session
            c.fetcher = None
            c.metrics = ClientMetrics()
            c.rate_limiter = None
            c.stale_cache = None
            c.edge_tracker = None
            yield c

    @respx.mock
    async def test_no_switch_call_when_inactive(self, mock_client):
        """When pro_load=[0,0,0], _switch_usage should NOT be called."""
        composite_route = respx.get(
            "https://energy.franklinwh.com/hes-gateway/terminal/getDeviceCompositeInfo"
        ).mock(return_value=httpx.Response(200, json={
            "code": 200,
            "result": {
                "currentWorkMode": 2,
                "runtimeData": {**SAMPLE_RUNTIME, "pro_load": [0, 0, 0]},
            },
        }))
        mqtt_route = respx.post(
            "https://energy.franklinwh.com/hes-gateway/terminal/sendMqtt"
        ).mock(return_value=httpx.Response(200, json={
            "code": 200,
            "result": {"dataArea": "{}"},
        }))

        await mock_client.get_stats()
        assert composite_route.called
        assert not mqtt_route.called  # No switch_usage call

    @respx.mock
    async def test_switch_call_when_active(self, mock_client):
        """When pro_load has active circuits, _switch_usage SHOULD be called."""
        respx.get(
            "https://energy.franklinwh.com/hes-gateway/terminal/getDeviceCompositeInfo"
        ).mock(return_value=httpx.Response(200, json={
            "code": 200,
            "result": {
                "currentWorkMode": 1,
                "runtimeData": {**SAMPLE_RUNTIME, "pro_load": [1, 0, 0]},
            },
        }))
        mqtt_route = respx.post(
            "https://energy.franklinwh.com/hes-gateway/terminal/sendMqtt"
        ).mock(return_value=httpx.Response(200, json={
            "code": 200,
            "result": {"dataArea": json.dumps(SAMPLE_SWITCH_DATA)},
        }))

        await mock_client.get_stats()
        assert mqtt_route.called
