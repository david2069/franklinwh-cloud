"""Tests for TokenFetcher — login, token management, error handling."""

import pytest
import respx
import httpx

from franklinwh.client import (
    TokenFetcher,
    AccountLockedException,
    InvalidCredentialsException,
)

LOGIN_URL = "https://energy.franklinwh.com/hes-gateway/terminal/initialize/appUserOrInstallerLogin"


class TestTokenFetcherLogin:
    """Static _login method and error handling."""

    @respx.mock
    async def test_successful_login(self):
        """Successful login returns result dict with token."""
        respx.post(LOGIN_URL).mock(
            return_value=httpx.Response(200, json={
                "code": 200,
                "result": {
                    "token": "fresh-token-123",
                    "userId": "12345",
                    "gatewayList": [],
                },
                "success": True,
            })
        )

        result = await TokenFetcher._login("test@example.com", "password123")
        # _login returns js["result"], not the full response
        assert result["token"] == "fresh-token-123"
        assert result["userId"] == "12345"

    @respx.mock
    async def test_login_invalid_credentials_raises(self):
        """Login with code 401 raises InvalidCredentialsException."""
        respx.post(LOGIN_URL).mock(
            return_value=httpx.Response(200, json={
                "code": 401,
                "message": "Invalid credentials",
                "success": False,
            })
        )

        with pytest.raises(InvalidCredentialsException):
            await TokenFetcher._login("test@example.com", "wrong")

    @respx.mock
    async def test_login_account_locked_raises(self):
        """Login with code 400 raises AccountLockedException."""
        respx.post(LOGIN_URL).mock(
            return_value=httpx.Response(200, json={
                "code": 400,
                "message": "Account locked",
                "success": False,
            })
        )

        with pytest.raises(AccountLockedException):
            await TokenFetcher._login("test@example.com", "locked")


class TestTokenFetcherGetToken:
    """Token caching and refresh behaviour."""

    @respx.mock
    async def test_get_token_caches(self):
        """Second get_token call should return cached token."""
        route = respx.post(LOGIN_URL).mock(
            return_value=httpx.Response(200, json={
                "code": 200,
                "result": {
                    "token": "cached-token-xyz",
                    "userId": "12345",
                    "gatewayList": [],
                },
                "success": True,
            })
        )

        fetcher = TokenFetcher("test@example.com", "password123")
        token1 = await fetcher.get_token()
        token2 = await fetcher.get_token()

        assert token1 == "cached-token-xyz"
        assert token1 == token2
        # Should only have called login once (cached)
        assert route.call_count == 1

    @respx.mock
    async def test_force_refresh_calls_login_again(self):
        """force_refresh=True should bypass cache."""
        calls = []

        def make_response(request):
            calls.append(1)
            n = len(calls)
            return httpx.Response(200, json={
                "code": 200,
                "result": {
                    "token": f"token-{n}",
                    "userId": "12345",
                    "gatewayList": [],
                },
                "success": True,
            })

        respx.post(LOGIN_URL).mock(side_effect=make_response)

        fetcher = TokenFetcher("test@example.com", "password123")
        token1 = await fetcher.get_token()
        token2 = await fetcher.get_token(force_refresh=True)

        assert token1 == "token-1"
        assert token2 == "token-2"
        assert len(calls) == 2
