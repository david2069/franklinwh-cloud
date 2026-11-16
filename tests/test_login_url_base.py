"""#39 — login follows url_base, so a client pointed elsewhere never logs in to the real cloud."""

import httpx
import respx

from franklinwh_cloud.auth import PasswordAuth
from franklinwh_cloud.client import Client

EMU = "http://127.0.0.1:8503/"
PATH = "hes-gateway/terminal/initialize/appUserOrInstallerLogin"
OK = {"code": 200, "success": True, "result": {"token": "tok-emu"}}


@respx.mock
async def test_password_auth_logs_in_at_its_url_base():
    route = respx.post(EMU + PATH).mock(return_value=httpx.Response(200, json=OK))
    assert await PasswordAuth("nobody@example.invalid", "x", url_base=EMU).get_token() == "tok-emu"
    assert route.called


@respx.mock
async def test_client_relogin_goes_to_client_url_base():
    route = respx.post(EMU + PATH).mock(return_value=httpx.Response(200, json=OK))
    c = Client(PasswordAuth("nobody@example.invalid", "x"), "gw", url_base=EMU)
    await c.refresh_token()
    assert route.called and c.token == "tok-emu"


def test_default_client_keeps_fetcher_url_base():
    auth = PasswordAuth("nobody@example.invalid", "x", url_base=EMU)
    Client(auth, "gw")
    assert auth.url_base == EMU
