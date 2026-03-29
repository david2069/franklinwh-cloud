"""Tests for Client's automatic 401 token refresh capability."""

import pytest
import respx
import httpx

from franklinwh_cloud.client import Client
from franklinwh_cloud.auth import PasswordAuth
from franklinwh_cloud.exceptions import TokenExpiredException

LOGIN_URL = "https://energy.franklinwh.com/hes-gateway/terminal/initialize/appUserOrInstallerLogin"
DATA_URL = "https://energy.franklinwh.com/hes-gateway/terminal/getDeviceCompositeInfo"

class TestClientAuthRetry:
    """Validate that Client._get/_post correctly intercept 401s and trigger token refreshes."""

    @respx.mock
    async def test_client_get_handles_401_recovery(self):
        """Simulate a 401 response and verify the client successfully refreshes the token and retries the request."""
        
        # 1. Mock the login endpoint to track refresh calls
        login_calls = []
        def login_response(request):
            call_num = len(login_calls)
            login_calls.append(call_num)
            token = f"token-version-{call_num}"
            return httpx.Response(200, json={
                "code": 200,
                "result": {"token": token, "userId": "user1"},
                "success": True,
            })
        
        respx.post(LOGIN_URL).mock(side_effect=login_response)
        
        # 2. Mock the data endpoint to return 401 first, then 200 OK
        data_calls = []
        def data_response(request):
            data_calls.append(request)
            if len(data_calls) == 1:
                # First attempt: token is implicitly invalid
                return httpx.Response(200, json={"code": 401, "message": "Token expired"})
            # Second attempt: we expect the new token in the headers
            assert request.headers.get("loginToken") == "token-version-1"
            return httpx.Response(200, json={
                "code": 200, 
                "result": {"runtimeData": {"battery": 100}, "deviceStatus": 1}, 
                "success": True
            })
            
        respx.get(DATA_URL).mock(side_effect=data_response)
        
        auth = PasswordAuth("test@a", "password")
        client = Client(auth, "10060006AXXXXXXXXX")
        client.token = await auth.get_token()
        
        res = await client.get_device_composite_info()
        
        assert len(login_calls) == 2, "Login should have been called twice (initial + refresh)"
        assert len(data_calls) == 2, "Data endpoint should have been hit twice (401 + 200)"
        
        # The final result must be the successful payload, stripped of any exceptions.
        assert res["code"] == 200
        assert res["result"]["deviceStatus"] == 1

    @respx.mock
    async def test_client_get_persistent_401_raises(self):
        """If the token refresh fails to resolve the 401 (e.g. account revoked), verify it raises TokenExpiredException."""
        
        respx.post(LOGIN_URL).mock(return_value=httpx.Response(200, json={
            "code": 200,
            "result": {"token": "dummy-token", "userId": "user1"},
            "success": True,
        }))
        
        # Endpoint always returns 401
        respx.get(DATA_URL).mock(return_value=httpx.Response(200, json={
            "code": 401,
            "message": "Token permanently expired or invalid"
        }))
        
        auth = PasswordAuth("test@a", "password")
        client = Client(auth, "10060006AXXXXXXXXX")
        client.token = await auth.get_token()
        
        # The client should retry once, then ultimately surface the TokenExpiredException
        with pytest.raises(TokenExpiredException) as exc:
            await client.get_device_composite_info()
            
        assert "Token expired or completely invalid: Code 401" in str(exc.value)
