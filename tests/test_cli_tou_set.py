"""CLI integration tests for franklinwh-cli tou --set.

Tests the full CLI handler path using AsyncMock clients — no live API calls.
Live hardware tests (T-LIVE-*) are in test_live.py and require FRANKLINWH_LIVE=1.

T-CLI-01: tou --set GRID_CHARGE --start 01:00 --end 02:00 (single-season fixture)
T-CLI-02: tou --set GRID_CHARGE --start 01:00 --end 02:00 (multi-season, April active)
T-CLI-03: tou --set SELF (full-day mode, no start/end)
T-CLI-04: tou --set GRID_CHARGE --start 01:00 --end 02:00 --month 10
T-CLI-05: tou --set GRID_CHARGE (no --start/--end → error)
T-CLI-06: tou --set CUSTOM --file schedule.json (file-based custom schedule)
T-CLI-07: tou --set GRID_CHARGE --start 01:00 --end 02:00 --wait (dispatch polling)
"""

import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch

from franklinwh_cloud.cli_commands import tou as tou_cmd


# ── Shared fixtures ──────────────────────────────────────────────────────────

def _mock_save_ok():
    return {"code": 200, "result": {"id": 1234}}


def _make_client_single_season():
    """AsyncMock client with single-season TOU config."""
    client = AsyncMock()
    client.gateway = "TEST-SN"
    client.get_tou_dispatch_detail.return_value = {
        "code": 200,
        "result": {
            "template": {"id": 1, "gatewayId": "TEST-SN", "name": "Test",
                         "electricCompany": "Test Co", "eletricCompanyId": -1,
                         "electricityType": 1, "workMode": 1, "countryId": 3,
                         "provinceId": 87, "countryEn": "Australia", "countryZh": "澳大利亚",
                         "eleCompanyFullName": "Test Co", "tariffName": "Test"},
            "strategyList": [{
                "seasonName": "Season 1",
                "month": "1,2,3,4,5,6,7,8,9,10,11,12",
                "dayTypeVoList": [{"dayType": 3, "dayName": "everyday",
                                   "detailVoList": [{"startHourTime": "00:00",
                                                      "endHourTime": "24:00",
                                                      "waveType": 0, "name": "Off-Peak",
                                                      "dispatchId": 6}]}],
            }],
            "detailDefaultVo": {"touDispatchList": []},
        }
    }
    client.get_home_gateway_list.return_value = {
        "result": [{"account": "test@example.com"}]
    }
    client.save_tou_dispatch.return_value = _mock_save_ok()
    client.set_tou_schedule = AsyncMock(return_value=_mock_save_ok())
    client.get_tou_info.return_value = {}
    return client


def _make_client_two_season():
    """AsyncMock client with two-season TOU config (Summer Oct–Mar / Winter Apr–Sep)."""
    client = AsyncMock()
    client.gateway = "TEST-SN"
    client.get_tou_dispatch_detail.return_value = {
        "code": 200,
        "result": {
            "template": {"id": 1, "gatewayId": "TEST-SN", "name": "Test",
                         "electricCompany": "Test Co", "eletricCompanyId": -1,
                         "electricityType": 1, "workMode": 1, "countryId": 3,
                         "provinceId": 87, "countryEn": "Australia", "countryZh": "澳大利亚",
                         "eleCompanyFullName": "Test Co", "tariffName": "Test"},
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
    client.get_home_gateway_list.return_value = {
        "result": [{"account": "test@example.com"}]
    }
    client.save_tou_dispatch.return_value = _mock_save_ok()
    client.set_tou_schedule = AsyncMock(return_value=_mock_save_ok())
    client.get_tou_info.return_value = {}
    return client


# ── T-CLI-01 ─────────────────────────────────────────────────────────────────

class TestCliSet01SingleSeason:
    """T-CLI-01: Grid charge window on single-season fixture."""

    @pytest.mark.asyncio
    async def test_set_grid_charge_window_single_season(self, capsys):
        """set_tou_schedule called, success printed with touId."""
        client = _make_client_single_season()

        await tou_cmd._handle_set(
            client=client,
            set_mode="GRID_CHARGE",
            start="01:00",
            end="02:00",
            default_mode=None,
            schedule_file=None,
            rates_file=None,
            season_name=None,
            season_months=None,
            tou_month=None,
            day_type_str=None,
            wait_confirm=False,
            json_output=False,
        )

        client.set_tou_schedule.assert_called_once()
        call_kwargs = client.set_tou_schedule.call_args[1]
        assert call_kwargs.get("touMode") == "CUSTOM" or \
               client.set_tou_schedule.call_args[0][0] == "CUSTOM"
        captured = capsys.readouterr()
        assert "1234" in captured.out  # touId


# ── T-CLI-02 ─────────────────────────────────────────────────────────────────

class TestCliSet02MultiSeasonActive:
    """T-CLI-02: Grid charge window on multi-season — month resolution automatic."""

    @pytest.mark.asyncio
    async def test_set_grid_charge_month_resolved(self):
        """set_tou_schedule called with correct month=None (auto-resolves today)."""
        client = _make_client_two_season()

        await tou_cmd._handle_set(
            client=client,
            set_mode="GRID_CHARGE",
            start="01:00",
            end="02:00",
            default_mode=None,
            schedule_file=None,
            rates_file=None,
            season_name=None,
            season_months=None,
            tou_month=None,
            day_type_str=None,
            wait_confirm=False,
            json_output=False,
        )

        client.set_tou_schedule.assert_called_once()
        # month=None should be passed (library resolves today's month)
        call_kwargs = client.set_tou_schedule.call_args[1]
        assert call_kwargs.get("month") is None


# ── T-CLI-03 ─────────────────────────────────────────────────────────────────

class TestCliSet03FullDaySelf:
    """T-CLI-03: Full-day self-consumption mode (no start/end)."""

    @pytest.mark.asyncio
    async def test_set_full_day_self(self, capsys):
        """SELF mode: set_tou_schedule called with touMode=SELF."""
        client = _make_client_single_season()

        await tou_cmd._handle_set(
            client=client,
            set_mode="SELF",
            start=None,
            end=None,
            default_mode=None,
            schedule_file=None,
            rates_file=None,
            season_name=None,
            season_months=None,
            tou_month=None,
            day_type_str=None,
            wait_confirm=False,
            json_output=False,
        )

        client.set_tou_schedule.assert_called_once()
        # Should call with touMode="SELF" (full-day, no schedule)
        call_args = client.set_tou_schedule.call_args
        mode = call_args[1].get("touMode") or call_args[0][0]
        assert mode == "SELF"


# ── T-CLI-04 ─────────────────────────────────────────────────────────────────

class TestCliSet04MonthFlag:
    """T-CLI-04: --month flag passed through to set_tou_schedule."""

    @pytest.mark.asyncio
    async def test_explicit_month_passed_to_library(self):
        """month=10 is forwarded to the library call."""
        client = _make_client_two_season()

        await tou_cmd._handle_set(
            client=client,
            set_mode="GRID_CHARGE",
            start="01:00",
            end="02:00",
            default_mode=None,
            schedule_file=None,
            rates_file=None,
            season_name=None,
            season_months=None,
            tou_month=10,
            day_type_str=None,
            wait_confirm=False,
            json_output=False,
        )

        client.set_tou_schedule.assert_called_once()
        call_kwargs = client.set_tou_schedule.call_args[1]
        assert call_kwargs.get("month") == 10


# ── T-CLI-05 ─────────────────────────────────────────────────────────────────

class TestCliSet05MissingStartEnd:
    """T-CLI-05: --set with only one of --start or --end → error."""

    @pytest.mark.asyncio
    async def test_start_without_end_prints_error(self, capsys):
        """--start without --end: should print error, not call set_tou_schedule."""
        client = _make_client_single_season()

        await tou_cmd._handle_set(
            client=client,
            set_mode="GRID_CHARGE",
            start="01:00",
            end=None,       # ← missing
            default_mode=None,
            schedule_file=None,
            rates_file=None,
            season_name=None,
            season_months=None,
            tou_month=None,
            day_type_str=None,
            wait_confirm=False,
            json_output=False,
        )

        client.set_tou_schedule.assert_not_called()
        captured = capsys.readouterr()
        assert "required" in captured.err.lower() or "error" in captured.err.lower()

    @pytest.mark.asyncio
    async def test_end_without_start_prints_error(self, capsys):
        """--end without --start: should print error, not call set_tou_schedule."""
        client = _make_client_single_season()

        await tou_cmd._handle_set(
            client=client,
            set_mode="GRID_CHARGE",
            start=None,     # ← missing
            end="02:00",
            default_mode=None,
            schedule_file=None,
            rates_file=None,
            season_name=None,
            season_months=None,
            tou_month=None,
            day_type_str=None,
            wait_confirm=False,
            json_output=False,
        )

        client.set_tou_schedule.assert_not_called()
        captured = capsys.readouterr()
        assert "required" in captured.err.lower() or "error" in captured.err.lower()


# ── T-CLI-06 ─────────────────────────────────────────────────────────────────

class TestCliSet06CustomFile:
    """T-CLI-06: tou --set CUSTOM --file schedule.json."""

    @pytest.mark.asyncio
    async def test_custom_file_blocks_submitted(self, tmp_path, capsys):
        """File blocks loaded and passed to set_tou_schedule."""
        schedule = [
            {"name": "Grid Charge", "startHourTime": "01:00", "endHourTime": "02:00",
             "waveType": 0, "dispatchId": 8},
            {"name": "Self", "startHourTime": "02:00", "endHourTime": "24:00",
             "waveType": 0, "dispatchId": 6},
        ]
        f = tmp_path / "schedule.json"
        f.write_text(json.dumps(schedule))

        client = _make_client_single_season()

        await tou_cmd._handle_set(
            client=client,
            set_mode="CUSTOM",
            start=None,
            end=None,
            default_mode="SELF",
            schedule_file=str(f),
            rates_file=None,
            season_name=None,
            season_months=None,
            tou_month=None,
            day_type_str=None,
            wait_confirm=False,
            json_output=False,
        )

        client.set_tou_schedule.assert_called_once()
        call_kwargs = client.set_tou_schedule.call_args[1]
        submitted = call_kwargs.get("touSchedule") or \
                    client.set_tou_schedule.call_args[0][1]
        assert len(submitted) == 2
        assert submitted[0]["dispatchId"] == 8

    @pytest.mark.asyncio
    async def test_custom_missing_file_prints_error(self, capsys):
        """File not found: error printed, set_tou_schedule not called."""
        client = _make_client_single_season()

        await tou_cmd._handle_set(
            client=client,
            set_mode="CUSTOM",
            start=None,
            end=None,
            default_mode="SELF",
            schedule_file="/nonexistent/schedule.json",
            rates_file=None,
            season_name=None,
            season_months=None,
            tou_month=None,
            day_type_str=None,
            wait_confirm=False,
            json_output=False,
        )

        client.set_tou_schedule.assert_not_called()
        captured = capsys.readouterr()
        assert "not found" in captured.err.lower()


# ── T-CLI-07 ─────────────────────────────────────────────────────────────────

class TestCliSet07Wait:
    """T-CLI-07: --wait triggers supervised dispatch (backup → confirm → hold → restore)."""

    @pytest.mark.asyncio
    async def test_wait_enters_supervised_dispatch(self, capsys):
        """With --wait, _supervised_dispatch is called after successful submit."""
        client = _make_client_single_season()
        # Add backup methods to the mock client
        client.tou_backup_save = AsyncMock(return_value=None)
        client.tou_backup_restore = AsyncMock(return_value=[])
        client.tou_backup_delete = AsyncMock()

        # Patch _supervised_dispatch so the hold loop does not block
        with patch("franklinwh_cloud.cli_commands.tou._supervised_dispatch",
                   new=AsyncMock()) as mock_supervised:
            await tou_cmd._handle_set(
                client=client,
                set_mode="GRID_CHARGE",
                start="01:00",
                end="02:00",
                default_mode=None,
                schedule_file=None,
                rates_file=None,
                season_name=None,
                season_months=None,
                tou_month=None,
                day_type_str=None,
                wait_confirm=True,
                json_output=False,
            )

        client.set_tou_schedule.assert_called_once()
        mock_supervised.assert_called_once()
        captured = capsys.readouterr()
        assert "1234" in captured.out or "submitted" in captured.out.lower()
