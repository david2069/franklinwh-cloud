"""Secrets in request payloads must never reach the debug log."""

import json
import logging

import pytest

from franklinwh_cloud.client import Client, _redact_secrets

SECRET = "hunter2-not-real"


def test_redacts_top_level_and_nested_json_string():
    payload = {
        "cmdType": 337,
        "dataArea": json.dumps({"opt": 1, "wifi_SSID": "MyNet", "wifi_Pw": SECRET,
                                "ap_SSID": "AP", "ap_Pw": SECRET}),
        "password": SECRET,
        "nested": [{"token": SECRET, "ok": "visible"}],
    }
    out = json.dumps(_redact_secrets(payload))
    assert SECRET not in out
    assert "MyNet" in out and "visible" in out      # non-secrets kept


def test_empty_secret_values_are_left_alone():
    assert _redact_secrets({"wifi_Pw": ""}) == {"wifi_Pw": ""}
    assert _redact_secrets("plain text") == "plain text"


async def test_post_debug_log_does_not_contain_wifi_password(caplog):
    c = Client.__new__(Client)

    async def fake_post_impl(*a, **k):      # stop after the log line
        raise RuntimeError("stop")

    class _Session:
        post = fake_post_impl

    c.session = _Session()
    payload = {"dataArea": json.dumps({"wifi_SSID": "MyNet", "wifi_Pw": SECRET})}
    with caplog.at_level(logging.DEBUG, logger="franklinwh_cloud"):
        with pytest.raises(Exception):
            await c._post("https://example.invalid/x", payload)
    assert "_post:" in caplog.text
    assert SECRET not in caplog.text


# --- issue #25: DEBUG request/response hooks must not log the token or the serial ---

import httpx

from franklinwh_cloud.client import _mask_serial, _redact_url

TOKEN = "tok-abcdef0123456789-not-real"
SERIAL = "99900000000000009999"        # mock serial (PII policy)


def test_redact_url_masks_serial_and_token_in_query():
    out = _redact_url(f"https://example.invalid/hes-gateway/x?gatewayId={SERIAL}&lang=en_US&token={TOKEN}")
    assert SERIAL not in out and TOKEN not in out
    assert "gatewayId=***9999" in out and "lang=en_US" in out


def test_mask_serial_keeps_last_four():
    assert _mask_serial(SERIAL) == "***9999"
    assert _mask_serial("123") == "***"


async def test_debug_hooks_log_no_token_or_serial(caplog):
    def handler(request):
        return httpx.Response(200, json={"code": 200, "result": {"gatewayId": SERIAL, "token": TOKEN,
                                                                "note": f"gw {SERIAL}"}})

    with caplog.at_level(logging.DEBUG, logger="franklinwh_cloud"):
        c = Client.__new__(Client)
        Client.__init__(c, _TokenFetcher(), SERIAL)
        hooks = c.session.event_hooks
        c.session = httpx.AsyncClient(transport=httpx.MockTransport(handler), event_hooks=hooks)
        await c.session.get(f"https://example.invalid/x?gatewayId={SERIAL}",
                            headers={"loginToken": TOKEN})
        await c.session.post("https://example.invalid/y", headers={"loginToken": TOKEN},
                             json={"equipNo": SERIAL, "password": TOKEN})
    assert "Request:" in caplog.text and "Response:" in caplog.text
    assert TOKEN not in caplog.text
    assert SERIAL not in caplog.text
    assert "***9999" in caplog.text


def test_debug_mode_keeps_edge_tracker_hook(caplog):
    with caplog.at_level(logging.DEBUG, logger="franklinwh_cloud"):
        c = Client(_TokenFetcher(), SERIAL)
    assert len(c.session.event_hooks["response"]) == 2   # edge tracker + debug
    assert len(c.session.event_hooks["request"]) == 1


class _TokenFetcher:
    info = {}

    async def get_token(self):
        return TOKEN
