"""Tests for ClientMetrics and instrumented_retry."""

import time
import pytest
import httpx

from franklinwh.metrics import ClientMetrics, instrumented_retry, extract_endpoint


# ---------------------------------------------------------------------------
# extract_endpoint
# ---------------------------------------------------------------------------

class TestExtractEndpoint:
    """URL → short endpoint name extraction."""

    def test_simple_url(self):
        assert extract_endpoint(
            "https://energy.franklinwh.com/hes-gateway/terminal/getDeviceCompositeInfo"
        ) == "getDeviceCompositeInfo"

    def test_url_with_query(self):
        assert extract_endpoint(
            "https://energy.franklinwh.com/hes-gateway/common/getAccessoryList?gatewayId=123"
        ) == "getAccessoryList"

    def test_trailing_slash(self):
        assert extract_endpoint("https://example.com/api/foo/") == "foo"


# ---------------------------------------------------------------------------
# ClientMetrics
# ---------------------------------------------------------------------------

class TestClientMetrics:
    """Direct counter and snapshot tests."""

    def test_initial_state(self):
        m = ClientMetrics()
        assert m.total_calls == 0
        assert m.total_errors == 0
        assert m.retry_count == 0
        assert m.token_refresh_count == 0
        assert m.login_count == 0

    def test_record_call(self):
        m = ClientMetrics()
        m.record_call("GET", "getStats", 0.5)
        assert m.total_calls == 1
        assert m.calls_by_method == {"GET": 1}
        assert m.calls_by_endpoint == {"getStats": 1}
        assert m.total_time_s == 0.5
        assert m.last_call_time_s == 0.5

    def test_record_multiple_calls(self):
        m = ClientMetrics()
        m.record_call("GET", "getStats", 0.3)
        m.record_call("POST", "sendMqtt", 0.7)
        m.record_call("GET", "getStats", 0.2)
        assert m.total_calls == 3
        assert m.calls_by_method == {"GET": 2, "POST": 1}
        assert m.calls_by_endpoint == {"getStats": 2, "sendMqtt": 1}
        assert m.min_call_time_s == 0.2
        assert m.max_call_time_s == 0.7

    def test_record_error(self):
        m = ClientMetrics()
        m.record_error("timeout")
        m.record_error("timeout")
        m.record_error("auth_401")
        assert m.total_errors == 3
        assert m.errors_by_type["timeout"] == 2
        assert m.errors_by_type["auth_401"] == 1

    def test_avg_call_time(self):
        m = ClientMetrics()
        assert m.avg_call_time_s == 0.0  # zero calls
        m.record_call("GET", "x", 1.0)
        m.record_call("GET", "x", 3.0)
        assert m.avg_call_time_s == 2.0

    def test_uptime(self):
        m = ClientMetrics()
        time.sleep(0.05)
        assert m.uptime_s >= 0.04

    def test_snapshot_format(self):
        m = ClientMetrics()
        m.record_call("GET", "getStats", 0.123)
        m.record_error("timeout")
        m.record_token_refresh()
        m.record_login()

        snap = m.snapshot()
        assert "uptime_s" in snap
        assert snap["total_api_calls"] == 1
        assert snap["calls_by_method"] == {"GET": 1}
        assert snap["calls_by_endpoint"] == {"getStats": 1}
        assert snap["total_errors"] == 1
        assert snap["retry_count"] == 0
        assert snap["token_refresh_count"] == 1
        assert snap["login_count"] == 1
        assert isinstance(snap["avg_response_time_s"], float)


# ---------------------------------------------------------------------------
# instrumented_retry
# ---------------------------------------------------------------------------

class TestInstrumentedRetry:
    """Tests for the instrumented_retry wrapper."""

    async def test_success_records_call(self):
        """Successful call records timing and count."""
        m = ClientMetrics()

        async def ok():
            return {"code": 200, "result": "ok"}

        result = await instrumented_retry(
            m, "testEndpoint", "GET",
            ok, lambda j: j["code"] != 401, lambda: None,
        )

        assert result["code"] == 200
        assert m.total_calls == 1
        assert m.calls_by_method == {"GET": 1}
        assert m.calls_by_endpoint == {"testEndpoint": 1}
        assert m.last_call_time_s > 0
        assert m.total_errors == 0

    async def test_401_records_retry_and_error(self):
        """401 response triggers retry count and auth error."""
        m = ClientMetrics()
        calls = []

        async def flaky():
            calls.append(1)
            if len(calls) == 1:
                return {"code": 401}
            return {"code": 200, "result": "ok"}

        refreshed = []
        async def mock_refresh():
            refreshed.append(1)

        result = await instrumented_retry(
            m, "flakyEndpoint", "POST",
            flaky, lambda j: j["code"] != 401, mock_refresh,
        )

        assert result["code"] == 200
        assert m.retry_count == 1
        assert m.errors_by_type["auth_401"] == 1
        assert len(refreshed) == 1
        # First call fails, second succeeds — both counted
        assert m.total_calls == 1  # only the successful one

    async def test_timeout_records_error(self):
        """Timeout exception is caught and recorded."""
        m = ClientMetrics()

        async def timeout_fn():
            raise httpx.TimeoutException("timed out")

        with pytest.raises(httpx.TimeoutException):
            await instrumented_retry(
                m, "slowEndpoint", "GET",
                timeout_fn, lambda j: True, lambda: None,
            )

        assert m.total_errors == 1
        assert m.errors_by_type["timeout"] == 1

    async def test_network_error_records(self):
        """Network error is caught and recorded."""
        m = ClientMetrics()

        async def network_fn():
            raise httpx.ConnectError("connection refused")

        with pytest.raises(httpx.ConnectError):
            await instrumented_retry(
                m, "deadEndpoint", "POST",
                network_fn, lambda j: True, lambda: None,
            )

        assert m.errors_by_type["network"] == 1
