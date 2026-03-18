"""Tests for TOU CLI command helpers and validation.

Tests the pure helper functions in cli_commands/tou.py that don't require
a live API connection. These are the helpers that format output, validate
input, and resolve dispatch codes.
"""

import pytest
from franklinwh_cloud.cli_commands.tou import (
    _validate_time,
    _dispatch_name,
    _time_to_minutes,
    _format_duration,
    _format_duration_short,
    _resolve_dispatch_name,
    _dispatch_color,
)


# ── _validate_time ──────────────────────────────────────────────────

class TestValidateTime:
    """Test HH:MM time format validation."""

    def test_valid_times(self):
        assert _validate_time("00:00") is True
        assert _validate_time("12:30") is True
        assert _validate_time("23:59") is True
        assert _validate_time("24:00") is True
        assert _validate_time("0:00") is True
        assert _validate_time("9:30") is True

    def test_invalid_times(self):
        assert _validate_time("25:00") is False
        assert _validate_time("12:60") is False
        assert _validate_time("abc") is False
        assert _validate_time("") is False
        assert _validate_time("12") is False
        assert _validate_time("12:00:00") is False

    def test_edge_cases(self):
        assert _validate_time("00:00") is True
        assert _validate_time("24:00") is True   # midnight boundary
        assert _validate_time("24:01") is False   # past midnight boundary


# ── _dispatch_name ──────────────────────────────────────────────────

class TestDispatchName:
    """Test dispatch ID to name resolution."""

    def test_known_dispatch_ids(self):
        assert "Self-consumption" in _dispatch_name(6)
        assert "solar/grid" in _dispatch_name(8).lower() or "charge" in _dispatch_name(8).lower()

    def test_unknown_dispatch_id(self):
        result = _dispatch_name(999)
        assert "Unknown" in result or "999" in result

    def test_common_ids(self):
        # These should all return non-empty strings
        for dispatch_id in [1, 2, 3, 6, 7, 8]:
            name = _dispatch_name(dispatch_id)
            assert isinstance(name, str)
            assert len(name) > 0


# ── _time_to_minutes ────────────────────────────────────────────────

class TestTimeToMinutes:
    """Test HH:MM to minutes-since-midnight conversion."""

    def test_midnight(self):
        assert _time_to_minutes("00:00") == 0

    def test_end_of_day(self):
        assert _time_to_minutes("24:00") == 1440

    def test_noon(self):
        assert _time_to_minutes("12:00") == 720

    def test_arbitrary_time(self):
        assert _time_to_minutes("13:31") == 811

    def test_single_digit_hour(self):
        assert _time_to_minutes("9:30") == 570

    def test_minutes_only(self):
        assert _time_to_minutes("00:45") == 45


# ── _format_duration ────────────────────────────────────────────────

class TestFormatDuration:
    """Test seconds to HH:MM:SS formatting."""

    def test_zero(self):
        assert _format_duration(0) == "00:00:00"

    def test_one_hour(self):
        assert _format_duration(3600) == "01:00:00"

    def test_mixed(self):
        assert _format_duration(3661) == "01:01:01"

    def test_large(self):
        # 9 hours exactly
        assert _format_duration(32400) == "09:00:00"

    def test_negative_clamped_to_zero(self):
        assert _format_duration(-100) == "00:00:00"


# ── _format_duration_short ──────────────────────────────────────────

class TestFormatDurationShort:
    """Test seconds to Xh Ym formatting."""

    def test_hours_and_minutes(self):
        assert _format_duration_short(5400) == "1h 30m"

    def test_hours_only(self):
        assert _format_duration_short(7200) == "2h 00m"

    def test_minutes_only(self):
        assert _format_duration_short(1800) == "30m"

    def test_zero(self):
        assert _format_duration_short(0) == "0m"

    def test_negative_clamped(self):
        assert _format_duration_short(-100) == "0m"

    def test_large(self):
        # 13h 31m
        assert _format_duration_short(48660) == "13h 31m"


# ── _resolve_dispatch_name ──────────────────────────────────────────

class TestResolveDispatchName:
    """Test dispatch ID resolution with lookup dict."""

    def test_with_lookup_title(self):
        lookup = {6: {"title": "Self Consumption Mode", "dispatchId": 6}}
        assert _resolve_dispatch_name(6, lookup) == "Self Consumption Mode"

    def test_fallback_to_dispatch_codes(self):
        # Empty lookup → falls back to DISPATCH_CODES constant
        name = _resolve_dispatch_name(6, {})
        assert isinstance(name, str)
        assert len(name) > 0

    def test_unknown_id_no_lookup(self):
        name = _resolve_dispatch_name(999, {})
        assert "999" in name or "Dispatch" in name

    def test_lookup_without_title(self):
        # Lookup exists but no title key
        lookup = {8: {"dispatchId": 8}}
        name = _resolve_dispatch_name(8, lookup)
        assert isinstance(name, str)
        assert len(name) > 0


# ── _dispatch_color ─────────────────────────────────────────────────

class TestDispatchColor:
    """Test dispatch name to terminal colour mapping."""

    def test_self_consumption(self):
        assert _dispatch_color("Self-consumption") == "green"

    def test_grid_charge(self):
        assert _dispatch_color("aPower charges from solar/grid") == "cyan"

    def test_grid_export(self):
        color = _dispatch_color("aPower to home/grid")
        assert color in ("yellow", "cyan", "green", "magenta", "dim")

    def test_unknown_returns_dim(self):
        assert _dispatch_color("Some Unknown Mode") == "dim"

    def test_case_insensitive(self):
        # The function lowercases internally
        assert _dispatch_color("SELF-CONSUMPTION") == "green"


# ── Dispatch code constant validation ───────────────────────────────

class TestDispatchCodeConstants:
    """Validate dispatch code constants used by the CLI."""

    def test_numeric_dispatch_ids_resolve(self):
        """All numeric dispatch IDs used in the CLI should resolve to names."""
        from franklinwh_cloud.const.tou import DISPATCH_CODES
        for dispatch_id in [1, 2, 3, 6, 7, 8]:
            assert dispatch_id in DISPATCH_CODES
            assert isinstance(DISPATCH_CODES[dispatch_id], str)

    def test_mnemonic_names_resolve(self):
        """All mnemonic names should resolve to numeric IDs."""
        from franklinwh_cloud.const.tou import DISPATCH_CODES
        for name in ["SELF", "SELF_CONSUMPTION", "GRID_CHARGE", "GRID_EXPORT",
                      "FORCE_CHARGE", "FORCE_DISCHARGE", "STANDBY", "HOME"]:
            assert name in DISPATCH_CODES
            assert isinstance(DISPATCH_CODES[name], int)

    def test_numeric_to_mnemonic_round_trip(self):
        """Numeric ID → name → ID should be consistent."""
        from franklinwh_cloud.const.tou import DISPATCH_CODES
        assert DISPATCH_CODES["SELF"] == 6
        assert DISPATCH_CODES["GRID_CHARGE"] == 8
        assert DISPATCH_CODES["GRID_EXPORT"] == 7

    def test_wave_types_valid(self):
        """Wave type constants match expected values."""
        from franklinwh_cloud.const.tou import WaveType
        assert WaveType.OFF_PEAK.value == 0
        assert WaveType.MID_PEAK.value == 1
        assert WaveType.ON_PEAK.value == 2
        assert WaveType.SUPER_OFF_PEAK.value == 4
