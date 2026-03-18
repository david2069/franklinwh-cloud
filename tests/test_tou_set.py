"""Tests for TOU set functionality — rates, seasons, day types, wait confirmation.

Tests the CLI tou command handler logic with mocked API clients,
covering success/failure output, rates file loading, and the
--wait dispatch confirmation polling.
"""

import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from franklinwh_cloud.cli_commands.tou import (
    _load_rates_file,
    _build_extra_kwargs,
    _DAY_TYPE_MAP,
    _wait_for_dispatch,
    _print_set_result,
    validate_rates,
    validate_season_months,
    _VALID_RATE_KEYS,
)


class TestLoadRatesFile:
    """Tests for _load_rates_file helper."""

    def test_load_valid_rates_file(self, tmp_path):
        rates = {"peak": 0.32, "off_peak": 0.12, "sell_peak": 0.08}
        f = tmp_path / "rates.json"
        f.write_text(json.dumps(rates))
        result = _load_rates_file(str(f))
        assert result == rates

    def test_load_missing_file(self, capsys):
        result = _load_rates_file("/nonexistent/rates.json")
        assert result is None
        captured = capsys.readouterr()
        assert "not found" in captured.err.lower()

    def test_load_invalid_json(self, tmp_path, capsys):
        f = tmp_path / "bad.json"
        f.write_text("{invalid json}")
        result = _load_rates_file(str(f))
        assert result is None
        captured = capsys.readouterr()
        assert "invalid json" in captured.err.lower()

    def test_load_rates_with_unknown_key_rejected(self, tmp_path, capsys):
        f = tmp_path / "r.json"
        f.write_text(json.dumps({"peak": 0.32, "typo_key": 0.10}))
        result = _load_rates_file(str(f))
        assert result is None
        captured = capsys.readouterr()
        assert "unknown rate key" in captured.err.lower()

    def test_load_rates_with_negative_rejected(self, tmp_path, capsys):
        f = tmp_path / "r.json"
        f.write_text(json.dumps({"peak": -0.10}))
        result = _load_rates_file(str(f))
        assert result is None
        captured = capsys.readouterr()
        assert "negative" in captured.err.lower()


class TestValidateRates:
    """Tests for validate_rates validation function."""

    def test_valid_rates(self):
        assert validate_rates({"peak": 0.32, "off_peak": 0.12}) == []

    def test_not_a_dict(self):
        errors = validate_rates([1, 2, 3])
        assert len(errors) == 1
        assert "dict" in errors[0].lower()

    def test_empty_dict(self):
        errors = validate_rates({})
        assert len(errors) == 1
        assert "empty" in errors[0].lower()

    def test_unknown_key(self):
        errors = validate_rates({"peak": 0.32, "typo": 0.10})
        assert any("unknown" in e.lower() for e in errors)

    def test_non_numeric_value(self):
        errors = validate_rates({"peak": "expensive"})
        assert any("numeric" in e.lower() for e in errors)

    def test_negative_value(self):
        errors = validate_rates({"peak": -0.50})
        assert any("negative" in e.lower() for e in errors)

    def test_unreasonably_high(self):
        errors = validate_rates({"peak": 200.0})
        assert any("high" in e.lower() for e in errors)

    def test_zero_is_valid(self):
        assert validate_rates({"peak": 0}) == []

    def test_all_valid_keys_accepted(self):
        rates = {k: 0.10 for k in _VALID_RATE_KEYS}
        assert validate_rates(rates) == []

    def test_multiple_errors(self):
        errors = validate_rates({"bad_key": -5, "peak": "str"})
        assert len(errors) >= 2


class TestValidateSeasonMonths:
    """Tests for validate_season_months validation function."""

    def test_valid_months(self):
        assert validate_season_months("1,2,3,4,5,6") == []

    def test_single_month(self):
        assert validate_season_months("6") == []

    def test_all_months(self):
        assert validate_season_months("1,2,3,4,5,6,7,8,9,10,11,12") == []

    def test_empty_string(self):
        assert validate_season_months("") == []

    def test_none(self):
        assert validate_season_months(None) == []

    def test_month_out_of_range_zero(self):
        errors = validate_season_months("0,1,2")
        assert any("out of range" in e for e in errors)

    def test_month_out_of_range_13(self):
        errors = validate_season_months("1,13")
        assert any("out of range" in e for e in errors)

    def test_duplicate_month(self):
        errors = validate_season_months("1,2,3,2")
        assert any("duplicate" in e.lower() for e in errors)

    def test_non_integer(self):
        errors = validate_season_months("Jan,Feb")
        assert len(errors) >= 1
        assert any("integer" in e.lower() for e in errors)

    def test_whitespace_tolerance(self):
        assert validate_season_months(" 1, 2 , 3 ") == []


class TestBuildExtraKwargs:
    """Tests for _build_extra_kwargs helper."""

    def test_no_flags_returns_empty(self):
        result = _build_extra_kwargs(None, None, None, None, False)
        assert result == {}

    def test_rates_file_loads(self, tmp_path):
        rates = {"peak": 0.50}
        f = tmp_path / "r.json"
        f.write_text(json.dumps(rates))
        result = _build_extra_kwargs(str(f), None, None, None, True)
        assert result["rates"] == rates

    def test_rates_file_error_returns_none(self):
        result = _build_extra_kwargs("/nonexistent.json", None, None, None, True)
        assert result is None

    def test_season_flags(self):
        result = _build_extra_kwargs(None, "Summer", "10,11,12", None, True)
        assert result["seasons"] == [{"name": "Summer", "months": "10,11,12"}]

    def test_season_name_only(self):
        result = _build_extra_kwargs(None, "Winter", None, None, True)
        assert result["seasons"][0]["name"] == "Winter"
        assert "1,2,3,4,5,6,7,8,9,10,11,12" in result["seasons"][0]["months"]

    def test_day_type_flag(self):
        result = _build_extra_kwargs(None, None, None, "weekday", True)
        assert result["day_type"] == 1

    def test_day_type_weekend(self):
        result = _build_extra_kwargs(None, None, None, "weekend", True)
        assert result["day_type"] == 2

    def test_day_type_everyday(self):
        result = _build_extra_kwargs(None, None, None, "everyday", True)
        assert result["day_type"] == 3


class TestDayTypeMap:
    """Tests for _DAY_TYPE_MAP constants."""

    def test_everyday(self):
        assert _DAY_TYPE_MAP["everyday"] == 3

    def test_weekday(self):
        assert _DAY_TYPE_MAP["weekday"] == 1

    def test_weekend(self):
        assert _DAY_TYPE_MAP["weekend"] == 2


class TestPrintSetResult:
    """Tests for _print_set_result output handling."""

    @pytest.mark.asyncio
    async def test_success_prints_tou_id(self, capsys):
        result = {"code": 200, "result": {"id": 42}}
        ok = await _print_set_result(result, json_output=False, client=None)
        assert ok is True
        captured = capsys.readouterr()
        assert "42" in captured.out
        assert "submitted" in captured.out.lower()

    @pytest.mark.asyncio
    async def test_failure_prints_error(self, capsys):
        result = {"code": 500, "msg": "Internal error"}
        ok = await _print_set_result(result, json_output=False, client=None)
        assert ok is False
        captured = capsys.readouterr()
        assert "500" in captured.err
        assert "Internal error" in captured.err

    @pytest.mark.asyncio
    async def test_json_output_prints_json(self, capsys):
        result = {"code": 200, "result": {"id": 99}}
        ok = await _print_set_result(result, json_output=True, client=None)
        assert ok is True
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["code"] == 200

    @pytest.mark.asyncio
    async def test_unknown_error_format(self, capsys):
        result = {"code": 400}  # no msg key
        ok = await _print_set_result(result, json_output=False, client=None)
        assert ok is False
        captured = capsys.readouterr()
        assert "400" in captured.err


class TestWaitForDispatch:
    """Tests for _wait_for_dispatch polling logic."""

    @pytest.mark.asyncio
    async def test_immediate_confirmation(self):
        """touSendStatus=0 on first poll = confirmed immediately."""
        client = AsyncMock()
        client.get_gateway_tou_list.return_value = {
            "result": {"touSendStatus": 0, "workMode": 1}
        }
        result = await _wait_for_dispatch(client, timeout=10, interval=1)
        assert result["confirmed"] is True
        assert result["tou_active"] is True
        assert result["elapsed_seconds"] == 0

    @pytest.mark.asyncio
    async def test_confirmed_but_not_tou_mode(self):
        """touSendStatus=0 but workMode != 1 (e.g. still self-consumption)."""
        client = AsyncMock()
        client.get_gateway_tou_list.return_value = {
            "result": {"touSendStatus": 0, "workMode": 2}
        }
        result = await _wait_for_dispatch(client, timeout=10, interval=1)
        assert result["confirmed"] is True
        assert result["tou_active"] is False

    @pytest.mark.asyncio
    async def test_timeout(self):
        """touSendStatus stays 1 = timeout."""
        client = AsyncMock()
        client.get_gateway_tou_list.return_value = {
            "result": {"touSendStatus": 1, "workMode": 1}
        }
        result = await _wait_for_dispatch(client, timeout=3, interval=1)
        assert result["confirmed"] is False
        assert result["timeout"] is True

    @pytest.mark.asyncio
    async def test_poll_error_continues(self):
        """API error during poll should not crash — keeps trying."""
        client = AsyncMock()
        client.get_gateway_tou_list.side_effect = [
            Exception("network error"),
            {"result": {"touSendStatus": 0, "workMode": 1}},
        ]
        result = await _wait_for_dispatch(client, timeout=10, interval=1)
        assert result["confirmed"] is True

    @pytest.mark.asyncio
    async def test_verbose_output(self, capsys):
        """Verbose mode prints confirmation message."""
        client = AsyncMock()
        client.get_gateway_tou_list.return_value = {
            "result": {"touSendStatus": 0, "workMode": 1}
        }
        await _wait_for_dispatch(client, verbose=True, timeout=10, interval=1)
        captured = capsys.readouterr()
        assert "confirmed" in captured.out.lower() or "active" in captured.out.lower()


class TestRateFieldMap:
    """Tests for the RATE_FIELD_MAP on TouMixin."""

    def test_rate_field_map_has_all_buy_rates(self):
        from franklinwh_cloud.mixins.tou import TouMixin
        buy_rates = ["peak", "sharp", "shoulder", "off_peak", "super_off_peak"]
        for key in buy_rates:
            assert key in TouMixin.RATE_FIELD_MAP, f"Missing buy rate key: {key}"

    def test_rate_field_map_has_all_sell_rates(self):
        from franklinwh_cloud.mixins.tou import TouMixin
        sell_rates = ["sell_peak", "sell_sharp", "sell_shoulder", "sell_off_peak", "sell_super_off_peak"]
        for key in sell_rates:
            assert key in TouMixin.RATE_FIELD_MAP, f"Missing sell rate key: {key}"

    def test_rate_field_map_has_grid_fee(self):
        from franklinwh_cloud.mixins.tou import TouMixin
        assert "grid_fee" in TouMixin.RATE_FIELD_MAP

    def test_all_rate_fields_count(self):
        from franklinwh_cloud.mixins.tou import TouMixin
        assert len(TouMixin._ALL_RATE_FIELDS) == len(TouMixin.RATE_FIELD_MAP)
