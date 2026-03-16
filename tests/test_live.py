"""Live smoke tests — opt-in, requires real API credentials.

All tests in this file are marked with @pytest.mark.live and will be
SKIPPED by default. To run them:

    pytest -m live

Requires a .env file in the project root with:
    FRANKLIN_USERNAME=your_email@example.com
    FRANKLIN_PASSWORD=your_password
"""

import os
import pytest

from franklinwh.client import Client, TokenFetcher, Stats


# Skip entire module if credentials not available
pytestmark = pytest.mark.live

FRANKLIN_USERNAME = os.environ.get("FRANKLIN_USERNAME", "")
FRANKLIN_PASSWORD = os.environ.get("FRANKLIN_PASSWORD", "")


def credentials_available():
    return bool(FRANKLIN_USERNAME and FRANKLIN_PASSWORD)


@pytest.fixture
async def live_client():
    """Create a real Client connected to the FranklinWH API."""
    if not credentials_available():
        pytest.skip("FRANKLIN_USERNAME/FRANKLIN_PASSWORD not set")

    fetcher = TokenFetcher(FRANKLIN_USERNAME, FRANKLIN_PASSWORD)
    token = await fetcher.get_token()
    info = fetcher.info

    # Need at least one gateway
    gateway_list = info.get("gatewayList", [])
    if not gateway_list:
        pytest.skip("No gateways found for this account")

    gateway_id = gateway_list[0].get("sn", "")
    client = Client(fetcher, gateway_id)
    yield client


class TestLiveLogin:
    """Verify login works with real credentials."""

    async def test_login_returns_token(self):
        if not credentials_available():
            pytest.skip("No credentials")

        fetcher = TokenFetcher(FRANKLIN_USERNAME, FRANKLIN_PASSWORD)
        token = await fetcher.get_token()
        assert token is not None
        assert len(token) > 0


class TestLiveGetStats:
    """Verify get_stats returns valid data from a real aGate."""

    async def test_returns_stats(self, live_client):
        stats = await live_client.get_stats()
        assert isinstance(stats, Stats)

    async def test_soc_in_range(self, live_client):
        stats = await live_client.get_stats()
        assert 0 <= stats.current.state_of_charge <= 100


class TestLiveGetMode:
    """Verify get_mode returns valid mode data."""

    async def test_returns_valid_mode(self, live_client):
        result = await live_client.get_mode()
        assert result is not None


class TestLiveGatewayList:
    """Verify gateway list is accessible."""

    async def test_returns_gateways(self, live_client):
        gateways = await live_client.get_home_gateway_list()
        assert isinstance(gateways, list)
        assert len(gateways) > 0
