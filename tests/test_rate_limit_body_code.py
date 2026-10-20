"""DEF-429-BODY-CODE — a 429 carried in the JSON body, and 429s on POST.

FWHAI logged "getDeviceCompositeInfo: 429: Too Many Requests" built from the
response body (2026-10-16). Whether that came with HTTP 200 is not captured;
these bodies are synthetic.
"""

import httpx
import respx

from franklinwh_cloud import Client
from franklinwh_cloud.auth import TokenAuth
from franklinwh_cloud.metrics import RateLimiter

GET_URL = "https://energy.franklinwh.com/hes-gateway/terminal/getDeviceCompositeInfo"
POST_URL = "https://energy.franklinwh.com/hes-gateway/terminal/sendMqtt"
BODY_429 = {"code": 429, "message": "Too Many Requests", "result": None, "success": False}


def _client(**kw):
    return Client(TokenAuth("t"), "99900000000000000001", heartbeat=False, **kw)


@respx.mock
async def test_get_body_code_429_is_explicit_and_backs_off():
    respx.get(GET_URL).mock(return_value=httpx.Response(200, json=BODY_429))
    rl = RateLimiter(calls_per_minute=0, calls_per_hour=0)
    async with _client(rate_limiter=rl) as c:
        res = await c._get(GET_URL)
        assert res == {"code": 429, "message": "Too Many Requests",
                       "result": None, "retry_after": 30}
        assert c.metrics.total_rate_limits == 1
    assert rl.is_rate_limited


@respx.mock
async def test_get_stats_on_body_429_is_stale_rate_limited():
    respx.get(GET_URL).mock(return_value=httpx.Response(200, json=BODY_429))
    async with _client() as c:
        stats = await c.get_stats()
    assert stats.is_stale is True
    assert stats.stale_reason == "rate_limited"


@respx.mock
async def test_post_http_429_is_explicit():
    respx.post(POST_URL).mock(return_value=httpx.Response(
        429, headers={"Retry-After": "7"}, text="<html>Too Many Requests</html>"))
    async with _client() as c:
        res = await c._post(POST_URL, {"cmdType": 203})
        assert res["code"] == 429 and res["retry_after"] == 7
        assert c.metrics.total_rate_limits == 1


@respx.mock
async def test_post_body_code_429_is_explicit():
    respx.post(POST_URL).mock(return_value=httpx.Response(200, json=BODY_429))
    async with _client() as c:
        res = await c._post(POST_URL, {"cmdType": 203})
        assert res["code"] == 429 and res["message"] == "Too Many Requests"
        assert c.metrics.total_rate_limits == 1


@respx.mock
async def test_429_is_not_stored_as_last_good_data():
    good = {"code": 200, "result": {"runtimeData": {"soc": 50}}, "success": True}
    route = respx.get(GET_URL)
    route.side_effect = [httpx.Response(200, json=good), httpx.Response(200, json=BODY_429)]
    async with _client(tolerate_stale_data=True) as c:
        await c._get(GET_URL)
        await c._get(GET_URL)
        cached = c.stale_cache.get("getDeviceCompositeInfo")
    assert cached is not None and cached["code"] == 200
