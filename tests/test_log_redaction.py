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
