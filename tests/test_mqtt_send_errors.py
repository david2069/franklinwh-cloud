"""Tests for _mqtt_send error handling.

Regression cover for a defect where client._mqtt_send referenced
FranklinWHError without that class existing in franklinwh_cloud.exceptions.
Every sendMqtt rejection outside codes 200/102/136 therefore raised ImportError
and discarded the backend's actual code and message.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from franklinwh_cloud.exceptions import (
    DeviceTimeoutException,
    FranklinWHError,
    GatewayOfflineException,
)


def _client(response):
    from franklinwh_cloud.client import Client

    c = MagicMock(spec=Client)
    c.url_base = "https://example.invalid/"
    c._post = AsyncMock(return_value=response)
    c._mqtt_send = Client._mqtt_send.__get__(c)
    return c


class TestMqttSendErrors:

    @pytest.mark.asyncio
    async def test_success_returns_response(self):
        payload = {"code": 200, "message": "Query success!", "result": {"dataArea": "{}"}}
        c = _client(payload)
        assert await c._mqtt_send("wire") is payload

    @pytest.mark.asyncio
    async def test_102_raises_device_timeout(self):
        c = _client({"code": 102, "message": "device timeout"})
        with pytest.raises(DeviceTimeoutException, match="device timeout"):
            await c._mqtt_send("wire")

    @pytest.mark.asyncio
    async def test_136_raises_gateway_offline(self):
        c = _client({"code": 136, "message": "gateway offline"})
        with pytest.raises(GatewayOfflineException, match="gateway offline"):
            await c._mqtt_send("wire")

    @pytest.mark.asyncio
    async def test_400_raises_franklinwh_error_not_import_error(self):
        """Real backend rejection observed live when the gateway id is unresolvable."""
        c = _client({"code": 400, "message": "No vpn gateway vpn!", "success": False})

        with pytest.raises(FranklinWHError) as exc:
            await c._mqtt_send("wire")

        assert exc.value.code == 400
        # The backend's own message must survive — it is the only diagnostic.
        assert "No vpn gateway vpn!" in str(exc.value)

    @pytest.mark.asyncio
    async def test_missing_code_key_does_not_raise_keyerror(self):
        """A malformed response must surface as FranklinWHError, not KeyError."""
        c = _client({"message": "malformed"})

        with pytest.raises(FranklinWHError) as exc:
            await c._mqtt_send("wire")
        assert exc.value.code is None

    @pytest.mark.asyncio
    async def test_error_is_catchable_as_exception(self):
        """Must derive from Exception, not BaseException — callers use `except Exception`."""
        assert issubclass(FranklinWHError, Exception)
        c = _client({"code": 500, "message": "boom"})
        try:
            await c._mqtt_send("wire")
        except Exception as e:
            assert isinstance(e, FranklinWHError)
        else:
            pytest.fail("expected FranklinWHError")
