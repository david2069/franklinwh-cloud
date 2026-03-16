"""Live smoke tests — opt-in, requires real API credentials.

All tests in this file are marked with @pytest.mark.live and will be
SKIPPED by default. To run them:

    pytest -m live

Credentials are loaded from (in priority order):
  1. franklinwh.ini (same format as cli.py)
  2. Environment variables: FRANKLIN_USERNAME, FRANKLIN_PASSWORD
"""

import configparser
import os
import pytest

from franklinwh.client import Client, TokenFetcher, Stats


# Skip entire module if credentials not available
pytestmark = pytest.mark.live


def _load_credentials():
    """Load credentials from franklinwh.ini or environment variables."""
    # Try franklinwh.ini first (same config as cli.py)
    for ini_path in ["franklinwh.ini", "franklinwh/franklinwh.ini"]:
        if os.path.exists(ini_path):
            config = configparser.ConfigParser()
            config.read(ini_path)
            try:
                email = config.get("energy.franklinwh.com", "email")
                password = config.get("energy.franklinwh.com", "password")
                gateway = config.get("gateways.enabled", "serialno", fallback=None)
                return email, password, gateway
            except (configparser.NoSectionError, configparser.NoOptionError):
                # Try alternate section name from .ini.example
                try:
                    email = config.get("FranklinWH", "email")
                    password = config.get("FranklinWH", "password")
                    gateway = config.get("FranklinWH", "gateway", fallback=None)
                    return email, password, gateway
                except (configparser.NoSectionError, configparser.NoOptionError):
                    pass

    # Fall back to environment variables
    email = os.environ.get("FRANKLIN_USERNAME", "")
    password = os.environ.get("FRANKLIN_PASSWORD", "")
    gateway = os.environ.get("FRANKLIN_GATEWAY", None)
    return email, password, gateway


FRANKLIN_USERNAME, FRANKLIN_PASSWORD, FRANKLIN_GATEWAY = _load_credentials()


def credentials_available():
    return bool(FRANKLIN_USERNAME and FRANKLIN_PASSWORD)


@pytest.fixture
async def live_client():
    """Create a real Client connected to the FranklinWH API."""
    if not credentials_available():
        pytest.skip("No credentials — need franklinwh.ini or FRANKLIN_USERNAME/FRANKLIN_PASSWORD env vars")

    fetcher = TokenFetcher(FRANKLIN_USERNAME, FRANKLIN_PASSWORD)
    token = await fetcher.get_token()
    info = fetcher.info

    # Use gateway from config, or discover from account
    gateway_id = FRANKLIN_GATEWAY
    if not gateway_id:
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
        assert 0 <= stats.current.battery_soc <= 100


class TestLiveGetMode:
    """Verify get_mode returns valid mode data."""

    async def test_returns_valid_mode(self, live_client):
        result = await live_client.get_mode()
        assert result is not None


class TestLiveGatewayList:
    """Verify gateway list is accessible."""

    async def test_returns_gateways(self, live_client):
        response = await live_client.get_home_gateway_list()
        assert response is not None
        assert response.get("code") == 200
        gateways = response.get("result", [])
        assert isinstance(gateways, list)
        assert len(gateways) > 0
