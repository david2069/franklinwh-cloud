"""DEF-AUTH-LOGIN-NULL-RESULT — typed login errors instead of TypeError.

The 400 warning text is from one live sample (2026-10-17); the other bodies
are synthetic, since no capture of them exists.
"""

import httpx
import pytest
import respx

from franklinwh_cloud.auth import PasswordAuth
from franklinwh_cloud.exceptions import (
    AccountLockedException,
    FranklinWHError,
    InvalidCredentialsException,
    LoginError,
    RateLimitedError,
)

LOGIN_URL = "https://energy.franklinwh.com/hes-gateway/terminal/initialize/appUserOrInstallerLogin"


def _mock(status=200, **body):
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(status, json=body))


@respx.mock
async def test_null_result_raises_login_error_with_code_and_message():
    _mock(code=10086, message="Account does not exist", result=None, success=False)
    with pytest.raises(LoginError) as ei:
        await PasswordAuth._login("nobody@example.com", "x")
    assert ei.value.code == 10086
    assert ei.value.message == "Account does not exist"
    assert not isinstance(ei.value, InvalidCredentialsException)


@respx.mock
async def test_missing_result_key_raises_login_error():
    _mock(code=500)
    with pytest.raises(LoginError) as ei:
        await PasswordAuth._login("a@example.com", "x")
    assert ei.value.code == 500
    assert str(ei.value) == "Login failed (code=500)"


@respx.mock
async def test_non_json_body_raises_login_error():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(200, text="<html>oops</html>"))
    with pytest.raises(LoginError):
        await PasswordAuth._login("a@example.com", "x")


@respx.mock
async def test_401_is_invalid_credentials_and_a_login_error():
    _mock(code=401, message="Invalid credentials", success=False)
    with pytest.raises(InvalidCredentialsException) as ei:
        await PasswordAuth._login("a@example.com", "x")
    assert isinstance(ei.value, LoginError)
    assert isinstance(ei.value, FranklinWHError)
    assert ei.value.code == 401
    assert str(ei.value) == "Invalid credentials"


@respx.mock
async def test_400_pre_lockout_warning_exposes_attempts_left():
    # Live sample, 2026-10-17: wrong password, code 400.
    _mock(code=400, message="Incorrect password, you still have 2 chances to enter.",
          success=False)
    with pytest.raises(AccountLockedException) as ei:
        await PasswordAuth._login("a@example.com", "wrong")
    assert ei.value.attempts_left == 2
    assert ei.value.code == 400
    assert isinstance(ei.value, LoginError)


@respx.mock
async def test_400_without_count_has_attempts_left_none():
    _mock(code=400, message="Account locked", success=False)
    with pytest.raises(AccountLockedException) as ei:
        await PasswordAuth._login("a@example.com", "x")
    assert ei.value.attempts_left is None


def test_attempts_left_singular_chance():
    e = AccountLockedException("Incorrect password, you still have 1 chance to enter.")
    assert e.attempts_left == 1


@respx.mock
async def test_http_429_on_login_raises_rate_limited_not_login_error():
    respx.post(LOGIN_URL).mock(return_value=httpx.Response(
        429, headers={"Retry-After": "12"}, text="Too Many Requests"))
    with pytest.raises(RateLimitedError) as ei:
        await PasswordAuth._login("a@example.com", "x")
    assert ei.value.retry_after == 12
    assert not isinstance(ei.value, LoginError)


@respx.mock
async def test_body_code_429_on_login_raises_rate_limited():
    _mock(code=429, message="Too Many Requests", result=None)
    with pytest.raises(RateLimitedError) as ei:
        await PasswordAuth._login("a@example.com", "x")
    assert ei.value.retry_after == 30
    assert ei.value.message == "Too Many Requests"


@respx.mock
async def test_get_token_propagates_login_error():
    _mock(code=10086, message="Account does not exist", result=None)
    with pytest.raises(LoginError):
        await PasswordAuth("nobody@example.com", "x").get_token()


def test_legacy_single_arg_construction_still_works():
    e = InvalidCredentialsException("Login failed: No token returned in response")
    assert str(e) == "Login failed: No token returned in response"
    assert e.code is None
