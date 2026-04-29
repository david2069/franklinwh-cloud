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


# ── Season Resolution Unit Tests (DEF-TOU-IMPLICIT-MERGE fix) ──────────────

def _make_two_season_dispatch_detail(active_month_in_winter=True):
    """Fixture: two-season config Summer (Oct-Mar) / Winter (Apr-Sep)."""
    return {
        "code": 200,
        "result": {
            "template": {"id": 1, "gatewayId": "TEST-SN", "name": "Test Tariff",
                         "electricCompany": "Test Co", "eletricCompanyId": -1,
                         "electricityType": 1, "workMode": 1, "countryId": 3,
                         "provinceId": 87, "countryEn": "Australia", "countryZh": "澳大利亚",
                         "eleCompanyFullName": "Test Co", "tariffName": "Test Tariff"},
            "strategyList": [
                {
                    "seasonName": "Summer",
                    "month": "10,11,12,1,2,3",
                    "dayTypeVoList": [{"dayType": 3, "dayName": "everyday",
                                       "detailVoList": [{"startHourTime": "00:00",
                                                          "endHourTime": "24:00",
                                                          "waveType": 0, "name": "Off-Peak",
                                                          "dispatchId": 6}]}],
                },
                {
                    "seasonName": "Winter",
                    "month": "4,5,6,7,8,9",
                    "dayTypeVoList": [{"dayType": 3, "dayName": "everyday",
                                       "detailVoList": [{"startHourTime": "00:00",
                                                          "endHourTime": "24:00",
                                                          "waveType": 0, "name": "Off-Peak",
                                                          "dispatchId": 6}]}],
                },
            ],
            "detailDefaultVo": {"touDispatchList": []},
        }
    }


def _make_single_season_dispatch_detail():
    """Fixture: single-season config covering all months."""
    return {
        "code": 200,
        "result": {
            "template": {"id": 1, "gatewayId": "TEST-SN", "name": "Test Tariff",
                         "electricCompany": "Test Co", "eletricCompanyId": -1,
                         "electricityType": 1, "workMode": 1, "countryId": 3,
                         "provinceId": 87, "countryEn": "Australia", "countryZh": "澳大利亚",
                         "eleCompanyFullName": "Test Co", "tariffName": "Test Tariff"},
            "strategyList": [
                {
                    "seasonName": "Season 1",
                    "month": "1,2,3,4,5,6,7,8,9,10,11,12",
                    "dayTypeVoList": [{"dayType": 3, "dayName": "everyday",
                                       "detailVoList": [{"startHourTime": "00:00",
                                                          "endHourTime": "24:00",
                                                          "waveType": 0, "name": "Off-Peak",
                                                          "dispatchId": 6}]}],
                }
            ],
            "detailDefaultVo": {"touDispatchList": []},
        }
    }


def _make_empty_dispatch_detail():
    """Fixture: no existing TOU config."""
    return {
        "code": 200,
        "result": {
            "template": {},
            "strategyList": [],
            "detailDefaultVo": {"touDispatchList": []},
        }
    }


def _make_save_ok():
    return {"code": 200, "result": {"id": 999}}


def _make_sr_client(dispatch_detail):
    """Build a full Client instance with necessary internals mocked for SR tests.

    Uses the same pattern as test_backward_compatibility.py:
    Client.__new__(Client) + gateway attribute + AsyncMock internals.
    """
    from franklinwh_cloud.client import Client
    client = Client.__new__(Client)
    client.gateway = "TEST-GW-001"
    client.url_base = "http://test/"
    client.get_tou_dispatch_detail = AsyncMock(return_value=dispatch_detail)
    client.get_home_gateway_list = AsyncMock(
        return_value={"result": [{"id": "TEST-GW-001", "account": "test@example.com"}]}
    )
    client.get_pcs_hintinfo = AsyncMock(return_value={"result": {}})
    client._post = AsyncMock(return_value={"code": 200, "result": {"id": 999}})
    return client


def _extract_strategy_from_post(client):
    """Extract strategyList from the _post call payload."""
    call_args = client._post.call_args
    assert call_args is not None, "_post was never called (set_tou_schedule did not submit)"
    payload = call_args[0][1]  # second positional arg to _post is the payload
    return payload.get("strategyList", [])


@pytest.mark.asyncio
class TestSeasonResolution:
    """T-SR-01 to T-SR-06: Verify set_tou_schedule season resolution logic.

    Uses Client.__new__ + AsyncMock internals. Inspects the strategyList
    sent to _post (= saveTouDispatch) to verify correct season targeting.
    """

    async def test_T_SR_01_single_season_updates_in_place(self):
        """T-SR-01: Single-season config, no month= → updates the one season."""
        client = _make_sr_client(_make_single_season_dispatch_detail())

        await client.set_tou_schedule(
            touMode="CUSTOM",
            touSchedule=[{"startHourTime": "01:00", "endHourTime": "02:00",
                          "waveType": 0, "name": "Grid Charge", "dispatchId": 8}],
        )
        strategy = _extract_strategy_from_post(client)
        assert len(strategy) == 1
        assert strategy[0]["month"] == "1,2,3,4,5,6,7,8,9,10,11,12"
        # New dispatch block should be present
        blocks = strategy[0]["dayTypeVoList"][0]["detailVoList"]
        dispatch_ids = [b["dispatchId"] for b in blocks]
        assert 8 in dispatch_ids, "Grid charge block (dispatchId=8) should be in submitted schedule"

    async def test_T_SR_02_two_season_april_updates_winter_only(self):
        """T-SR-02: Two-season config, month=4 → updates Winter, Summer untouched."""
        client = _make_sr_client(_make_two_season_dispatch_detail())

        await client.set_tou_schedule(
            touMode="CUSTOM",
            touSchedule=[{"startHourTime": "01:00", "endHourTime": "02:00",
                          "waveType": 0, "name": "Grid Charge", "dispatchId": 8}],
            month=4,
        )
        strategy = _extract_strategy_from_post(client)
        assert len(strategy) == 2

        summer = next(s for s in strategy if "10" in s["month"].split(","))
        summer_blocks = summer["dayTypeVoList"][0]["detailVoList"]
        assert all(b["dispatchId"] == 6 for b in summer_blocks), \
            "Summer season should be untouched (dispatchId=6 only)"

        winter = next(s for s in strategy if "4" in s["month"].split(","))
        winter_blocks = winter["dayTypeVoList"][0]["detailVoList"]
        dispatch_ids = [b["dispatchId"] for b in winter_blocks]
        assert 8 in dispatch_ids, "Winter season should have grid charge block (dispatchId=8)"

    async def test_T_SR_03_explicit_month_10_updates_summer(self):
        """T-SR-03: Two-season config, month=10 → updates Summer, Winter untouched."""
        client = _make_sr_client(_make_two_season_dispatch_detail())

        await client.set_tou_schedule(
            touMode="CUSTOM",
            touSchedule=[{"startHourTime": "02:00", "endHourTime": "03:00",
                          "waveType": 0, "name": "Export", "dispatchId": 7}],
            month=10,
        )
        strategy = _extract_strategy_from_post(client)
        assert len(strategy) == 2

        summer = next(s for s in strategy if "10" in s["month"].split(","))
        summer_blocks = summer["dayTypeVoList"][0]["detailVoList"]
        dispatch_ids = [b["dispatchId"] for b in summer_blocks]
        assert 7 in dispatch_ids, "Summer should have export block (dispatchId=7)"

        winter = next(s for s in strategy if "4" in s["month"].split(","))
        winter_blocks = winter["dayTypeVoList"][0]["detailVoList"]
        assert all(b["dispatchId"] == 6 for b in winter_blocks), \
            "Winter should be untouched (dispatchId=6 only)"

    async def test_T_SR_04_no_existing_config_creates_single_season(self):
        """T-SR-04: No existing TOU config → creates single all-months season."""
        client = _make_sr_client(_make_empty_dispatch_detail())

        await client.set_tou_schedule(
            touMode="CUSTOM",
            touSchedule=[{"startHourTime": "01:00", "endHourTime": "02:00",
                          "waveType": 0, "name": "Grid Charge", "dispatchId": 8}],
        )
        strategy = _extract_strategy_from_post(client)
        assert len(strategy) == 1
        assert strategy[0]["month"] == "1,2,3,4,5,6,7,8,9,10,11,12"

    async def test_T_SR_05_explicit_seasons_bypasses_read_merge(self):
        """T-SR-05: seasons= explicitly provided → uses caller's seasons, ignores existing."""
        client = _make_sr_client(_make_two_season_dispatch_detail())

        await client.set_tou_schedule(
            touMode="CUSTOM",
            touSchedule=[{"startHourTime": "01:00", "endHourTime": "02:00",
                          "waveType": 0, "name": "Grid Charge", "dispatchId": 8}],
            seasons=[{"name": "Dispatch", "months": "1,2,3,4,5,6,7,8,9,10,11,12"}],
        )
        strategy = _extract_strategy_from_post(client)
        # Should be exactly 1 season (caller's explicit override)
        assert len(strategy) == 1
        assert strategy[0]["seasonName"] == "Dispatch"
        assert strategy[0]["month"] == "1,2,3,4,5,6,7,8,9,10,11,12"

    async def test_T_SR_06_set_tou_schedule_multi_deprecation_notice_in_docstring(self):
        """T-SR-06: set_tou_schedule_multi() docstring mentions deprecation."""
        from franklinwh_cloud.client import Client
        doc = Client.set_tou_schedule_multi.__doc__
        assert doc is not None
        assert "deprecated" in doc.lower() or "Deprecated" in doc, \
            "set_tou_schedule_multi docstring should document the deprecation notice"

