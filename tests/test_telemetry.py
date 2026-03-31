import pytest
from unittest.mock import patch, MagicMock
import urllib.error
import urllib.request
import logging

from franklinwh_cloud.telemetry import _send_telemetry_sync, dispatch_cli_event

@patch("urllib.request.urlopen")
def test_telemetry_happy_path(mock_urlopen, caplog):
    # Mock a successful 200 OK response from PostHog
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    with caplog.at_level(logging.WARNING):
        _send_telemetry_sync("test_event", "fake_uuid", {"command": "status"}, api_key="valid_key")

    # Should NOT have logged any warnings
    mock_urlopen.assert_called_once()
    assert "Telemetry failed" not in caplog.text

@patch("urllib.request.urlopen")
def test_telemetry_unhappy_path_http_401(mock_urlopen, caplog):
    # Mock PostHog returning 401 Unauthorized (e.g. invalid API key)
    mock_resp = MagicMock()
    mock_resp.status = 401
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    with caplog.at_level(logging.WARNING):
        _send_telemetry_sync("test_event", "fake_uuid", {"command": "status"}, api_key="invalid_key")

    # Should have explicitly logged a warning about HTTP 401
    mock_urlopen.assert_called_once()
    assert "Telemetry failed to dispatch (HTTP 401)" in caplog.text
    assert "Check your PostHog API Key" in caplog.text

@patch("urllib.request.urlopen")
def test_telemetry_unhappy_path_network_timeout(mock_urlopen, caplog):
    # Mock a network failure (timeout or DNS resolution error)
    mock_urlopen.side_effect = urllib.error.URLError("Network is unreachable")

    with caplog.at_level(logging.WARNING):
        _send_telemetry_sync("test_event", "fake_uuid", {"command": "status"}, api_key="valid_key")

    # Must catch and swallow the exception, but log it as a warning!
    mock_urlopen.assert_called_once()
    assert "Telemetry dispatch swallowed exception" in caplog.text
    assert "Check your network or API Key" in caplog.text

@patch("threading.Thread")
def test_dispatch_cli_event_opt_out_aborts(mock_thread):
    # Ensure that if is_opted_in=False, we don't even instantiate the daemon thread
    dispatch_cli_event("status", is_opted_in=False, execution_uuid="fake", api_key="key")
    mock_thread.assert_not_called()

@patch("threading.Thread")
def test_dispatch_cli_event_opt_in_fires(mock_thread):
    # If explicitly opted-in, the thread should start
    dispatch_cli_event("status", is_opted_in=True, execution_uuid="fake", api_key="key")
    mock_thread.assert_called_once()
    mock_thread.return_value.start.assert_called_once()
