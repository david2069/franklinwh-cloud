"""Live smoke tests — opt-in, requires real API credentials.

All tests in this file are marked with @pytest.mark.live and will be
SKIPPED by default. To run them:

    pytest -m live

Credentials are loaded from (in priority order):
  1. franklinwh.ini (same format as cli.py)
  2. Environment variables: FRANKLIN_USERNAME, FRANKLIN_PASSWORD

NOTE: All tests are READ-ONLY — no set_mode, set_tou, or other
state-changing calls are made. Safe to run against a live system.

⚠️ URGENT POLICY: NO NEGATIVE AUTHENTICATION WITH REAL ACCOUNTS
This suite is governed by `.agents/policies/live_test_protocol.md`.
Under NO circumstances should tests artificially supply invalid passwords 
to a REAL email address to trigger an `InvalidCredentialsException`. 
FranklinWH employs strict brute-force lockouts.

Negative authentication paths (HTTP 401/Locked) against the live API 
MUST strictly utilize dummy emails (e.g. `test-invalid@example.com`) 
to safely absorb rate-limit bans without locking your gateway automation.
"""

import configparser
import os
import pytest

from franklinwh_cloud.client import Client, Stats
from franklinwh_cloud.auth import PasswordAuth
from franklinwh_cloud.models import GridStatus


# Skip entire module if credentials not available
pytestmark = pytest.mark.live


def _load_credentials():
    """Load credentials from franklinwh_cloud.ini or environment variables."""
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

    fetcher = PasswordAuth(FRANKLIN_USERNAME, FRANKLIN_PASSWORD)
    token = await fetcher.get_token()
    info = fetcher.info

    # Use gateway from config, or discover from account
    gateway_id = FRANKLIN_GATEWAY
    if not gateway_id:
        temp = Client(fetcher, "placeholder")
        gw_raw = await temp.get_home_gateway_list()
        gw_list = gw_raw.get("result", []) if isinstance(gw_raw, dict) else gw_raw
        if not gw_list:
            pytest.skip("No gateways found for this account")
        gateway_id = gw_list[0].get("id", "")

    client = Client(fetcher, gateway_id)
    yield client


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TestLiveLogin:
    """Verify login works with real credentials."""

    async def test_login_returns_token(self):
        if not credentials_available():
            pytest.skip("No credentials")

        fetcher = PasswordAuth(FRANKLIN_USERNAME, FRANKLIN_PASSWORD)
        token = await fetcher.get_token()
        assert token is not None
        assert len(token) > 0

    async def test_login_returns_info(self):
        if not credentials_available():
            pytest.skip("No credentials")

        fetcher = PasswordAuth(FRANKLIN_USERNAME, FRANKLIN_PASSWORD)
        await fetcher.get_token()
        assert fetcher.info is not None
        assert isinstance(fetcher.info, dict)


# ---------------------------------------------------------------------------
# Stats Mixin
# ---------------------------------------------------------------------------

class TestLiveStats:
    """Verify stats methods return valid data from a real aGate."""

    async def test_returns_stats(self, live_client):
        stats = await live_client.get_stats()
        assert isinstance(stats, Stats)

    async def test_soc_in_range(self, live_client):
        stats = await live_client.get_stats()
        assert 0 <= stats.current.battery_soc <= 100

    async def test_stats_has_totals(self, live_client):
        stats = await live_client.get_stats()
        assert stats.totals is not None
        # Total solar should be >= 0
        assert stats.totals.solar >= 0

    async def test_stats_grid_status(self, live_client):
        stats = await live_client.get_stats()
        assert isinstance(stats.current.grid_status, GridStatus)

    async def test_runtime_data(self, live_client):
        result = await live_client.get_runtime_data()
        assert result is not None

    async def test_power_by_day(self, live_client):
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        result = await live_client.get_power_by_day(today)
        assert result is not None

    async def test_power_details(self, live_client):
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        result = await live_client.get_power_details(type=1, timeperiod=today)
        assert result is not None


# ---------------------------------------------------------------------------
# Modes Mixin
# ---------------------------------------------------------------------------

class TestLiveModes:
    """Verify mode methods return valid mode data (read-only)."""

    async def test_get_mode(self, live_client):
        result = await live_client.get_mode()
        assert result is not None

    async def test_get_mode_info(self, live_client):
        result = await live_client.get_mode_info()
        assert result is not None


# ---------------------------------------------------------------------------
# Storm Mixin
# ---------------------------------------------------------------------------

class TestLiveStorm:
    """Verify storm/weather methods (read-only)."""

    async def test_get_weather(self, live_client):
        result = await live_client.get_weather()
        assert result is not None

    async def test_get_storm_settings(self, live_client):
        result = await live_client.get_storm_settings()
        assert result is not None

    async def test_get_storm_list(self, live_client):
        result = await live_client.get_storm_list()
        assert result is not None


# ---------------------------------------------------------------------------
# Power Mixin
# ---------------------------------------------------------------------------

class TestLivePower:
    """Verify power/grid methods (read-only)."""

    async def test_get_grid_status(self, live_client):
        result = await live_client.get_grid_status()
        assert result is not None

    async def test_get_power_control_settings(self, live_client):
        result = await live_client.get_power_control_settings()
        assert result is not None


# ---------------------------------------------------------------------------
# Devices Mixin
# ---------------------------------------------------------------------------

class TestLiveDevices:
    """Verify device/accessory methods (read-only)."""

    async def test_get_device_composite_info(self, live_client):
        result = await live_client.get_device_composite_info()
        assert result is not None

    async def test_get_agate_info(self, live_client):
        result = await live_client.get_agate_info()
        assert result is not None

    async def test_get_device_info(self, live_client):
        result = await live_client.get_device_info()
        assert result is not None

    async def test_get_power_info(self, live_client):
        result = await live_client.get_power_info()
        assert result is not None

    async def test_get_smart_circuits_info(self, live_client):
        result = await live_client.get_smart_circuits_info()
        assert result is not None

    async def test_get_bms_info(self, live_client):
        # Get an aPower serial number from device composite info first
        info = await live_client.get_device_composite_info()
        apower_list = info.get("result", {}).get("apboxList", [])
        if not apower_list:
            pytest.skip("No aPower units found")
        serial = apower_list[0].get("sn", "")
        result = await live_client.get_bms_info(serial)
        assert result is not None


# ---------------------------------------------------------------------------
# Account Mixin
# ---------------------------------------------------------------------------

class TestLiveAccount:
    """Verify account/site methods (read-only)."""

    async def test_get_home_gateway_list(self, live_client):
        response = await live_client.get_home_gateway_list()
        assert response is not None
        assert response.get("code") == 200
        gateways = response.get("result", [])
        assert isinstance(gateways, list)
        assert len(gateways) > 0

    async def test_siteinfo(self, live_client):
        result = await live_client.siteinfo()
        assert result is not None

    async def test_get_entrance_info(self, live_client):
        result = await live_client.get_entrance_info()
        assert result is not None

    async def test_get_unread_count(self, live_client):
        result = await live_client.get_unread_count()
        assert result is not None

    async def test_get_notification_settings(self, live_client):
        result = await live_client.get_notification_settings()
        assert result is not None

    async def test_get_warranty_info(self, live_client):
        result = await live_client.get_warranty_info()
        assert result is not None

    async def test_get_alarm_codes_list(self, live_client):
        result = await live_client.get_alarm_codes_list()
        assert result is not None


# ---------------------------------------------------------------------------
# TOU Mixin
# ---------------------------------------------------------------------------

class TestLiveTOU:
    """Verify TOU schedule methods (read-only)."""

    async def test_get_gateway_tou_list(self, live_client):
        result = await live_client.get_gateway_tou_list()
        assert result is not None

    async def test_get_charge_power_details(self, live_client):
        result = await live_client.get_charge_power_details()
        assert result is not None

    async def test_get_tou_dispatch_detail(self, live_client):
        result = await live_client.get_tou_dispatch_detail()
        assert result is not None


# ---------------------------------------------------------------------------
# Metrics (verify instrumentation works on real calls)
# ---------------------------------------------------------------------------

class TestLiveMetrics:
    """Verify metrics are recorded on live API calls."""

    async def test_metrics_after_calls(self, live_client):
        """Metrics should show calls after exercising the API."""
        await live_client.get_stats()
        await live_client.get_mode()

        metrics = live_client.get_metrics()
        assert metrics["total_api_calls"] >= 2
        assert metrics["uptime_s"] > 0
        assert metrics["total_errors"] == 0

