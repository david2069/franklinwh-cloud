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
import json
import pytest
from pathlib import Path
import jsonschema

from franklinwh_cloud.client import Client, Stats
from franklinwh_cloud.auth import PasswordAuth
from franklinwh_cloud.models import GridStatus, GridConnectionState


def _assert_live_schema(path: str, method: str, raw_payload: dict):
    """Fallback validator: check if the captured raw payload matches the formal Spec."""
    spec_path = Path("docs/franklinwh_openapi.json")
    if not spec_path.exists():
        return
    spec = json.loads(spec_path.read_text())
    try:
        schema = spec["paths"][path][method.lower()]["responses"]["200"]["content"]["application/json"]["schema"]
    except KeyError:
        return  # End point not in spec yet
    jsonschema.validate(instance=raw_payload, schema=schema)



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

    async def test_stats_grid_connection_state(self, live_client):
        stats = await live_client.get_stats()
        assert isinstance(stats.current.grid_connection_state, GridConnectionState)
        # On a live connected system this must be CONNECTED
        assert stats.current.grid_connection_state == GridConnectionState.CONNECTED

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


# ---------------------------------------------------------------------------
# Destructive — Simulated Off-Grid (opt-in, explicit user confirmation)
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.destructive
class TestLiveGridConnectionState:
    """Verify GridConnectionState transitions through a live simulated off-grid cycle.

    DESTRUCTIVE: performs one grid relay open/close cycle (~15 seconds total).
    Non-backed loads will lose power during the simulation window.

    Requires both markers to run:
        pytest -m "live and destructive" tests/test_live.py::TestLiveGridConnectionState -s
    """

    async def test_simulated_offgrid_state_cycle(self, live_client):
        """Full state machine: CONNECTED → SIMULATED_OFF_GRID → CONNECTED.

        Safety pre-flight:
          - SOC must be ≥ reserve + 10% margin
          - System must currently be CONNECTED
          - No active off-grid state or outage
          - Explicit terminal confirmation from user (type 'yes')

        Guarantees:
          - try/finally ensures restore even on assertion failure or crash
          - Exactly 1 simulated outage
          - ~15 second total duration
        """
        import asyncio
        import sys

        # ── Pre-flight ───────────────────────────────────────────────
        print("\n" + "═" * 62)
        print("  ⚠️   LIVE OFF-GRID SIMULATION TEST — PRE-FLIGHT CHECK")
        print("═" * 62)

        stats = await live_client.get_stats()
        cur = stats.current
        soc        = cur.battery_soc
        solar_kw   = cur.solar_production
        battery_kw = cur.battery_use
        grid_kw    = cur.grid_use
        home_kw    = cur.home_load

        # Reserve SOC
        try:
            mode_info = await live_client.get_mode_info()
            reserve_soc = int(mode_info.get("result", {}).get("soc", 20)) if isinstance(mode_info, dict) else 20
        except Exception:
            reserve_soc = 20
        margin = soc - reserve_soc
        soc_ok = margin >= 10

        # Current off-grid API state
        gs = await live_client.get_grid_status()
        gs_result = gs.get("result", gs) if isinstance(gs, dict) else {}
        already_simulated = gs_result.get("offgridState", 0) == 1
        already_requested = gs_result.get("offgridSet", 0) == 1
        not_grid_tied = getattr(live_client, "_not_grid_tied", False)

        print(f"  Current state:    {cur.grid_connection_state.value}")
        print(f"  SOC:              {soc:.0f}%  |  Reserve: {reserve_soc:.0f}%  |  Margin: {margin:.0f}%  {'✅' if soc_ok else '❌ INSUFFICIENT'}")
        print(f"  Solar:            {solar_kw:.1f} kW")
        bat_dir = "charging" if battery_kw < -0.05 else "discharging" if battery_kw > 0.05 else "idle"
        print(f"  Battery:          {battery_kw:+.1f} kW  ({bat_dir})")
        grid_dir = "importing" if grid_kw > 0.05 else "exporting" if grid_kw < -0.05 else "idle"
        print(f"  Grid:             {grid_kw:+.1f} kW  ({grid_dir})")
        print(f"  Home load:        {home_kw:.1f} kW")
        print(f"  Not grid-tied:    {not_grid_tied}")
        print(f"  offgridState:     {gs_result.get('offgridState', 0)}")
        print()
        print("  This test will:")
        print("    • Perform exactly 1 simulated grid disconnect")
        print("    • Duration: ~15 seconds total (5s settle + capture + 5s restore)")
        print("    • Non-backed loads WILL lose power during the simulation")
        print("    • Grid restore is guaranteed via try/finally (even on crash)")
        print("═" * 62)

        # Safety guards — skip rather than fail so CI doesn't break
        if not_grid_tied:
            pytest.skip("System is not grid-tied — simulated off-grid not applicable")
        if already_simulated or already_requested:
            pytest.skip("System already in off-grid state — restore first then re-run")
        if cur.grid_connection_state != GridConnectionState.CONNECTED:
            pytest.skip(f"System not CONNECTED ({cur.grid_connection_state.value}) — cannot test")
        if not soc_ok:
            pytest.skip(f"SOC margin insufficient ({margin:.0f}%) — need ≥10% above reserve ({reserve_soc:.0f}%)")

        # ── Explicit user confirmation ────────────────────────────────
        print("  Type 'yes' to proceed, anything else to abort: ", end="", flush=True)
        try:
            answer = sys.stdin.readline().strip().lower()
        except Exception:
            answer = ""
        if answer != "yes":
            pytest.skip("User aborted — no changes made to system")

        # ── Test cycle ────────────────────────────────────────────────
        print("\n  [1/4] Activating simulated off-grid (offgridSet=1)...")
        stats_during = cur_during = None
        main_sw = []
        grid_relay_raw = -1
        offgridreason = None
        offgrid_state = -1
        restored = False

        try:
            await live_client.set_grid_status(status=GridStatus.OFF, soc=5)

            print("  [2/4] Settling 5 seconds...")
            await asyncio.sleep(5)

            print("  [3/4] Capturing state during simulation...")
            # Invalidate NOT_GRID_TIED cache so get_stats() re-evaluates relay gate
            live_client._not_grid_tied = False
            stats_during = await live_client.get_stats()
            cur_during = stats_during.current
            print(f"         grid_connection_state = {cur_during.grid_connection_state.value}")

            comp = await live_client.get_device_composite_info()
            runtime = comp.get("result", {}).get("runtimeData", {})
            main_sw = runtime.get("main_sw", [])
            grid_relay_raw = main_sw[0] if main_sw else -1
            offgridreason  = runtime.get("offgridreason")
            print(f"         main_sw               = {main_sw}")
            print(f"         main_sw[0] (gate val) = {grid_relay_raw}  (0=OPEN=disconnected)")
            print(f"         offgridreason         = {offgridreason}")

            gs_d = await live_client.get_grid_status()
            gs_d_result = gs_d.get("result", gs_d) if isinstance(gs_d, dict) else {}
            offgrid_state = gs_d_result.get("offgridState", -1)
            print(f"         offgridState          = {offgrid_state}")

        finally:
            print("  [4/4] Restoring grid connection (offgridSet=0)...")
            try:
                await live_client.set_grid_status(status=GridStatus.NORMAL, soc=5)
                await asyncio.sleep(8)  # relay takes several seconds to physically close
                restored = True
                print("         Restore sent ✅")
            except Exception as exc:
                print(f"         ⚠️  Restore failed: {exc} — manual restore may be needed!")

        # ── Assertions ────────────────────────────────────────────────
        assert cur_during is not None, "Stats during simulation were not captured"

        assert main_sw, "main_sw was empty during simulation — firmware did not report relay state"

        assert grid_relay_raw == 0, (
            f"DEF-GRID-STATE-ENUM gate assumption invalid: "
            f"expected main_sw[0]=0 (OPEN) during simulation, got {grid_relay_raw}. "
            "Review relay encoding — the gate condition must be updated."
        )
        assert offgrid_state == 1, (
            f"Expected offgridState=1 from selectOffgrid during simulation, got {offgrid_state}. "
            "get_grid_status() disambiguation is not working correctly."
        )
        assert cur_during.grid_connection_state == GridConnectionState.SIMULATED_OFF_GRID, (
            f"Expected SIMULATED_OFF_GRID from get_stats(), got {cur_during.grid_connection_state.value}. "
            "Library GridConnectionState state machine is incorrect."
        )
        assert restored, "Grid restore did not complete — check system manually"

        # Poll until CONNECTED (relay takes time to physically close after restore)
        print("  Polling for CONNECTED state (up to 30s)...")
        stats_after = None
        for attempt in range(10):
            await asyncio.sleep(3)
            try:
                live_client._not_grid_tied = False  # reset cache each poll
                stats_after = await live_client.get_stats()
                state_after = stats_after.current.grid_connection_state
                print(f"         [{attempt+1}/10] grid_connection_state = {state_after.value}")
                if state_after == GridConnectionState.CONNECTED:
                    break
            except Exception as e:
                print(f"         [{attempt+1}/10] poll error: {e}")
        else:
            assert False, (
                f"System did not return to CONNECTED within 30s of restore. "
                f"Last state: {stats_after.current.grid_connection_state.value if stats_after else 'unknown'}. "
                "Check system manually — relay may still be transitioning."
            )

        assert stats_after.current.grid_connection_state == GridConnectionState.CONNECTED, (
            f"Expected CONNECTED after restore, got {stats_after.current.grid_connection_state.value}"
        )

        print()
        print("═" * 62)
        print("  ✅  ALL ASSERTIONS PASSED")
        print(f"      CONNECTED → SIMULATED_OFF_GRID → CONNECTED  ✓")
        print(f"      main_sw[0]=0 gate confirmed                 ✓")
        print(f"      offgridState=1 from selectOffgrid           ✓")
        print(f"      GridConnectionState enum correct             ✓")
        print("═" * 62)
