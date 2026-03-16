"""Tests for retry() — token refresh, retry logic, error propagation."""

import pytest
import respx
import httpx

from franklinwh.client import (
    retry,
    DeviceTimeoutException,
    GatewayOfflineException,
)


class TestRetryLogic:
    """Retry function behaviour on success and failure."""

    async def test_success_no_retry(self):
        """Successful call (code != 401) should not retry."""
        call_count = 0

        async def func():
            nonlocal call_count
            call_count += 1
            return {"code": 200, "result": "ok"}

        async def refresh():
            pass

        result = await retry(func, lambda j: j["code"] != 401, refresh)
        assert result["code"] == 200
        assert call_count == 1

    async def test_401_triggers_refresh_and_retry(self):
        """401 response should trigger token refresh and retry."""
        call_count = 0
        refresh_count = 0

        async def func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"code": 401, "message": "Token expired"}
            return {"code": 200, "result": "ok"}

        async def refresh():
            nonlocal refresh_count
            refresh_count += 1

        result = await retry(func, lambda j: j["code"] != 401, refresh)
        assert result["code"] == 200
        assert call_count == 2
        assert refresh_count == 1

    async def test_persistent_401_exhausts_retries(self):
        """Persistent 401 should eventually stop retrying."""
        call_count = 0

        async def func():
            nonlocal call_count
            call_count += 1
            return {"code": 401, "message": "Always expired"}

        async def refresh():
            pass

        result = await retry(func, lambda j: j["code"] != 401, refresh)
        # Should have retried and eventually returned the 401
        assert result["code"] == 401
        assert call_count > 1  # At least one retry
