"""Tests for the mode CLI command."""
import pytest
from unittest.mock import AsyncMock, patch

from franklinwh_cloud.cli_commands.mode import run
from franklinwh_cloud.const import TIME_OF_USE, SELF_CONSUMPTION, EMERGENCY_BACKUP

@pytest.fixture
def mock_client():
    from franklinwh_cloud.client import Client
    # We only need the methods used by mode.py
    client = Client.__new__(Client)
    client.set_mode = AsyncMock(return_value=True)
    client.get_mode = AsyncMock(return_value={"name": "Time of Use", "soc": 15, "run_desc": "Normal"})
    client.get_all_mode_soc = AsyncMock(return_value=[
        {"name": "Time of Use", "soc": 15, "minSoc": 0, "maxSoc": 100, "active": True, "editSocFlag": True},
        {"name": "Self Consumption", "soc": 5, "minSoc": 0, "maxSoc": 100, "active": False, "editSocFlag": True},
    ])
    return client

@pytest.mark.asyncio
class TestCliMode:

    async def test_run_get_mode(self, mock_client, capsys):
        """Test reading the current mode without modifying it."""
        try:
            await run(mock_client)
        except SystemExit:
            pass
        mock_client.get_mode.assert_called_once()
        mock_client.get_all_mode_soc.assert_called_once()

    async def test_run_get_mode_json(self, mock_client, capsys):
        """Test getting current mode under JSON output format."""
        await run(mock_client, json_output=True)
        # Should not raise exception
        mock_client.get_mode.assert_called_once()
        
    async def test_run_set_mode_by_name(self, mock_client):
        """Test setting the mode using a string mnemonic."""
        await run(mock_client, set_mode="Time", soc=15)
        mock_client.set_mode.assert_called_once_with(
            requestedOperatingMode=TIME_OF_USE,
            requestedSOC=15,
            reqbackupForeverFlag=None,
            reqnextWorkMode=None,
            reqdurationMinutes=None
        )

    async def test_run_set_mode_by_number(self, mock_client):
        """Test setting the mode using a direct integer ID string."""
        await run(mock_client, set_mode="2")
        mock_client.set_mode.assert_called_once_with(
            requestedOperatingMode=SELF_CONSUMPTION,
            reqbackupForeverFlag=None,
            reqnextWorkMode=None,
            reqdurationMinutes=None
        )
        
    async def test_run_set_mode_unknown(self, mock_client, capsys):
        """Test gracefully rejecting invalid mode strings."""
        await run(mock_client, set_mode="UNKNOWN_PLANET")
        mock_client.set_mode.assert_not_called()
        captured = capsys.readouterr()
        assert "Unknown mode: UNKNOWN_PLANET" in captured.out
        assert "Available modes: 1, 2, 3" in captured.out
        
    async def test_run_set_mode_json_output(self, mock_client):
        """Test setting the mode and rendering JSON response."""
        await run(mock_client, set_mode="3", json_output=True)
        mock_client.set_mode.assert_called_once_with(
            requestedOperatingMode=EMERGENCY_BACKUP,
            reqbackupForeverFlag=None,
            reqnextWorkMode=None,
            reqdurationMinutes=None
        )

    async def test_run_get_mode_full_terminal_render(self, mock_client, capsys):
        """Test that the CLI correctly renders a complex get_mode dictionary without crashing."""
        mock_client.get_mode = AsyncMock(return_value={
            "name": "Time of Use",
            "soc": 15,
            "minSoc": 5,
            "maxSoc": 100,
            "run_desc": "Normal",
            "deviceStatus": "1",
            "alarmsCount": 2,
            "unreadMsgCount": 5,
            "offgridState": 1,
            "touScheduleList": {
                "current": {"startHourTime": "10:00", "endHourTime": "12:00", "dispatchName": "Self-consumption"},
                "next": {"startHourTime": "12:00", "endHourTime": "14:00", "dispatchName": "Grid charge", "remaining": "2h"}
            },
            "backupForeverFlag": 1,
            "nextWorkMode": "2"
        })
        
        await run(mock_client)
        captured = capsys.readouterr()
        assert "Current Mode" in captured.out
        assert "Time of Use" in captured.out
        assert "(range: 5–100%)" in captured.out
        assert "System" in captured.out
        assert "Active Alarms" in captured.out
        assert "Active TOU Schedule" in captured.out
        assert "Emergency Backup" in captured.out
        assert "Indefinite" in captured.out

    async def test_run_get_mode_string_fallback(self, mock_client, capsys):
        """Test getting mode when it returns a simple string or None to ensure fallback logic holds."""
        mock_client.get_mode = AsyncMock(return_value="UNKNOWN_STATE")
        mock_client.get_all_mode_soc = AsyncMock(side_effect=Exception("Failed to load generic soc"))
        
        await run(mock_client)
        captured = capsys.readouterr()
        assert "UNKNOWN_STATE" in captured.out
        assert "Could not retrieve SoC summary: Failed to load generic soc" in captured.out
