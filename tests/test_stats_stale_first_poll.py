"""DEF-STATS-FIRST-POLL-ZERO: placeholder zeros must be flagged stale, and a 429 named."""

import httpx
import pytest
import respx

from franklinwh_cloud.client import Client
from franklinwh_cloud.metrics import ClientMetrics, RateLimiter

URL = "https://energy.franklinwh.com/hes-gateway/terminal/getDeviceCompositeInfo"


@pytest.fixture
async def client():
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
        c._not_grid_tied = False
        from franklinwh_cloud.heartbeat import GatewayHeartbeat
        c._heartbeat = GatewayHeartbeat("test-gateway", None)
        yield c


@respx.mock
async def test_first_poll_empty_payload_is_flagged_stale(client):
    respx.get(URL).mock(return_value=httpx.Response(200, json={"code": 200, "result": None}))
    stats = await client.get_stats()
    assert stats.current.battery_soc == 0.0
    assert stats.is_stale is True
    assert stats.stale_reason == "empty_payload"


@respx.mock
async def test_first_poll_429_is_flagged_rate_limited(client):
    client.rate_limiter = RateLimiter()
    respx.get(URL).mock(return_value=httpx.Response(429, headers={"Retry-After": "12"},
                                                    text="<html>Too Many Requests</html>"))
    stats = await client.get_stats()
    assert stats.is_stale is True
    assert stats.stale_reason == "rate_limited"
    assert client.metrics.total_rate_limits == 1
    assert client.rate_limiter._retry_after_until > 0


@respx.mock
async def test_get_returns_explicit_429_instead_of_raising_on_html(client):
    respx.get(URL).mock(return_value=httpx.Response(429, text="<html>Too Many Requests</html>"))
    res = await client._get(URL)
    assert res["code"] == 429 and res["result"] is None and res["retry_after"] == 30


@respx.mock
async def test_fallback_to_last_known_carries_reason(client):
    from franklinwh_cloud.models import empty_stats
    last = empty_stats(); last.current.battery_soc = 55.0
    client._last_known_stats = last
    respx.get(URL).mock(return_value=httpx.Response(200, json={"code": 200, "result": None}))
    stats = await client.get_stats()
    assert stats.current.battery_soc == 55.0
    assert stats.is_stale is True and stats.stale_reason == "empty_payload"
