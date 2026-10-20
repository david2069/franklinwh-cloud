"""FEAT-CLIENT-ACLOSE and FEAT-RESOLVE-GATEWAY."""

import httpx
import pytest
import respx

from franklinwh_cloud import (
    Client, GatewaySelectionError, list_gateway_serials, resolve_gateway,
)
from franklinwh_cloud.auth import TokenAuth

GW_LIST_URL = "https://energy.franklinwh.com/hes-gateway/terminal/getHomeGatewayList"
SN_A = "99900000000000000001"
SN_B = "99900000000000000002"


def _gateways(*serials):
    respx.get(GW_LIST_URL).mock(return_value=httpx.Response(200, json={
        "code": 200, "success": True,
        "result": [{"id": s, "name": f"GW{i}", "groupId": None, "groupFlag": 0}
                   for i, s in enumerate(serials)],
    }))


class TestClientAclose:
    async def test_aclose_closes_session_and_is_idempotent(self):
        c = Client(TokenAuth("t"), SN_A, heartbeat=False)
        assert not c.session.is_closed
        await c.aclose()
        assert c.session.is_closed
        await c.aclose()  # second call is a no-op

    async def test_async_with_closes_session(self):
        async with Client(TokenAuth("t"), SN_A, heartbeat=False) as c:
            assert not c.session.is_closed
        assert c.session.is_closed

    async def test_auth_survives_for_next_client(self):
        auth = TokenAuth("t")
        async with Client(auth, SN_A, heartbeat=False):
            pass
        assert await auth.get_token() == "t"


class TestResolveGateway:
    @respx.mock
    async def test_single_gateway_is_returned(self):
        _gateways(SN_A)
        assert await resolve_gateway(TokenAuth("t")) == SN_A

    @respx.mock
    async def test_several_without_serial_refuses_and_lists_them(self):
        _gateways(SN_A, SN_B)
        with pytest.raises(GatewaySelectionError) as ei:
            await resolve_gateway(TokenAuth("t"))
        assert ei.value.serials == [SN_A, SN_B]

    @respx.mock
    async def test_none_refuses(self):
        _gateways()
        with pytest.raises(GatewaySelectionError) as ei:
            await resolve_gateway(TokenAuth("t"))
        assert ei.value.serials == []

    @respx.mock
    async def test_given_serial_on_account_is_returned(self):
        _gateways(SN_A, SN_B)
        assert await resolve_gateway(TokenAuth("t"), SN_B) == SN_B

    @respx.mock
    async def test_given_serial_matches_case_insensitively(self):
        _gateways("99900000AB0CD0000042")
        assert await resolve_gateway(TokenAuth("t"), "99900000ab0cd0000042") == "99900000AB0CD0000042"

    @respx.mock
    async def test_given_serial_not_on_account_refuses(self):
        _gateways(SN_A)
        with pytest.raises(GatewaySelectionError):
            await resolve_gateway(TokenAuth("t"), SN_B)

    @respx.mock
    async def test_list_gateway_serials_keeps_api_order(self):
        _gateways(SN_B, SN_A)
        assert await list_gateway_serials(TokenAuth("t")) == [SN_B, SN_A]
