"""Tests for get_all_mode_soc() — reserve SoC retrieval for all operating modes.

Tests the new ModesMixin.get_all_mode_soc() method which wraps
getGatewayTouListV2 to return SoC configuration for all 3 modes.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock


# ── Mock TOU list response ──────────────────────────────────────────

MOCK_TOU_LIST_RESPONSE = {
    "code": 200,
    "result": {
        "currendId": 9323,  # Self-Consumption is active
        "backupForeverFlag": 1,
        "nextWorkMode": 2,
        "tariffSettingFlag": 0,
        "touSendStatus": 0,
        "stopMode": 0,
        "stromEn": 1,
        "gridChargeEn": 0,
        "touAlertMessage": "",
        "timerEndTime": "00:00:00.000000",
        "timerEndTimeZero": "00:00:00.000000",
        "timerStartTime": "00:00:00.000000",
        "timerStartTimeZero": "00:00:00.000000",
        "zoneInfo": "Australia/Sydney",
        "list": [
            {
                "id": 9322,
                "workMode": 1,
                "name": "Time of Use",
                "soc": 15,
                "minSoc": 10,
                "maxSoc": 100,
                "editSocFlag": 1,
                "oldIndex": 3,
                "electricityType": 1,
            },
            {
                "id": 9323,
                "workMode": 2,
                "name": "Self Consumption",
                "soc": 20,
                "minSoc": 10,
                "maxSoc": 100,
                "editSocFlag": 1,
                "oldIndex": 2,
                "electricityType": 1,
            },
            {
                "id": 9324,
                "workMode": 3,
                "name": "Emergency Backup",
                "soc": 100,
                "minSoc": 10,
                "maxSoc": 100,
                "editSocFlag": 0,
                "oldIndex": 1,
                "electricityType": 1,
            },
        ],
    },
}


def _make_mock_client(tou_response=None):
    """Create a mock client with ModesMixin.get_all_mode_soc bound."""
    from franklinwh_cloud.mixins.modes import ModesMixin

    client = MagicMock(spec=ModesMixin)
    client.get_gateway_tou_list = AsyncMock(
        return_value=tou_response or MOCK_TOU_LIST_RESPONSE
    )
    # Bind the real method to the mock
    client.get_all_mode_soc = ModesMixin.get_all_mode_soc.__get__(client)
    return client


# ── Tests ────────────────────────────────────────────────────────────

class TestGetAllModeSoc:
    """Tests for get_all_mode_soc()."""

    @pytest.mark.asyncio
    async def test_returns_three_modes(self):
        """Should return one entry per operating mode."""
        client = _make_mock_client()
        result = await client.get_all_mode_soc()
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_entries_have_required_keys(self):
        """Each entry must have workMode, name, soc, minSoc, maxSoc, editSocFlag, active."""
        client = _make_mock_client()
        result = await client.get_all_mode_soc()
        required_keys = {"workMode", "name", "soc", "minSoc", "maxSoc", "editSocFlag", "active"}
        for entry in result:
            assert required_keys.issubset(entry.keys()), f"Missing keys in {entry}"

    @pytest.mark.asyncio
    async def test_soc_values_correct(self):
        """SoC values should match the mock data."""
        client = _make_mock_client()
        result = await client.get_all_mode_soc()
        soc_by_mode = {e["workMode"]: e["soc"] for e in result}
        assert soc_by_mode[1] == 15   # TOU
        assert soc_by_mode[2] == 20   # Self-Consumption
        assert soc_by_mode[3] == 100  # Emergency Backup

    @pytest.mark.asyncio
    async def test_active_flag_marks_correct_mode(self):
        """Only Self-Consumption (currendId=9323) should be marked active."""
        client = _make_mock_client()
        result = await client.get_all_mode_soc()
        active_modes = [e for e in result if e["active"]]
        assert len(active_modes) == 1
        assert active_modes[0]["workMode"] == 2
        assert active_modes[0]["name"] == "Self-Consumption"

    @pytest.mark.asyncio
    async def test_non_active_modes_not_flagged(self):
        """TOU and Emergency Backup should NOT be active."""
        client = _make_mock_client()
        result = await client.get_all_mode_soc()
        inactive = [e for e in result if not e["active"]]
        assert len(inactive) == 2

    @pytest.mark.asyncio
    async def test_editable_flag(self):
        """Emergency Backup has editSocFlag=0, others have 1."""
        client = _make_mock_client()
        result = await client.get_all_mode_soc()
        edit_by_mode = {e["workMode"]: e["editSocFlag"] for e in result}
        assert edit_by_mode[1] == 1
        assert edit_by_mode[2] == 1
        assert edit_by_mode[3] == 0

    @pytest.mark.asyncio
    async def test_min_max_soc(self):
        """All modes should have minSoc=10 and maxSoc=100 in mock data."""
        client = _make_mock_client()
        result = await client.get_all_mode_soc()
        for entry in result:
            assert entry["minSoc"] == 10
            assert entry["maxSoc"] == 100

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self):
        """If TOU list is empty, return empty list."""
        response = {
            "code": 200,
            "result": {
                "currendId": 0,
                "list": [],
            },
        }
        client = _make_mock_client(response)
        result = await client.get_all_mode_soc()
        assert result == []

    @pytest.mark.asyncio
    async def test_mode_names_from_const(self):
        """Mode names should come from OPERATING_MODES constant."""
        from franklinwh_cloud.const import OPERATING_MODES
        client = _make_mock_client()
        result = await client.get_all_mode_soc()
        for entry in result:
            assert entry["name"] == OPERATING_MODES[entry["workMode"]]
