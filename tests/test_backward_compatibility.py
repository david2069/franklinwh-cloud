"""Tests for ensuring standard Legacy backward compatibility on strings and numerics."""
import pytest
from unittest.mock import AsyncMock

from franklinwh_cloud.const import TIME_OF_USE, SELF_CONSUMPTION, EMERGENCY_BACKUP

@pytest.fixture
def mock_client_internals():
    from franklinwh_cloud.client import Client
    client = Client.__new__(Client)
    client.gateway = "TEST-GW-001"
    client.url_base = "http://test/"
    client.get_device_composite_info = AsyncMock(return_value={"code": 200, "result": {"valid": 1, "currentWorkMode": 1, "deviceStatus": 1, "runtimeData": {"mode": 1}}})
    client.get_gateway_tou_list = AsyncMock(return_value={
        "result": {
            "currendId": 12345,
            "backupForeverFlag": 1,
            "nextWorkMode": 2,
            "tariffSettingFlag": False,
            "touSendStatus": 0,
            "stopMode": 0,
            "list": [
                {"workMode": 1, "id": 1001, "oldIndex": 3, "name": "Time of Use", "soc": 10, "editSocFlag": 1, "electricityType": 1, "maxSoc": 100, "minSoc": 0},
                {"workMode": 2, "id": 1002, "oldIndex": 2, "name": "Self Consumption", "soc": 20, "editSocFlag": 1, "electricityType": 1, "maxSoc": 100, "minSoc": 0},
                {"workMode": 3, "id": 1003, "oldIndex": 1, "name": "Emergency Backup", "soc": 100, "editSocFlag": 0, "electricityType": 1, "maxSoc": 100, "minSoc": 0}
            ]
        }
    })
    client.get_storm_settings = AsyncMock(return_value={"result": {"enableStorm": 1}})
    client._post = AsyncMock(return_value={"code": 200, "message": "Success", "result": {"id": 123}})
    
    # Mocks for set_tou_schedule
    client.get_tou_dispatch_detail = AsyncMock(return_value={
        "result": {
            "template": {
                "id": 1, "electricCompany": "", "name": "test", "workMode": 1, 
                "countryId": 1, "provinceId": 1, "countryEn": "", "countryZh": "", 
                "eleCompanyFullName": "", "eletricCompanyId": ""
            }
        }
    })
    client.get_home_gateway_list = AsyncMock(return_value={"result": [{"id": "TEST-GW-001", "account": "test"}]})
    return client


@pytest.mark.asyncio
class TestBackwardCompatibility:
    
    @pytest.mark.parametrize("input_mode, expected_work_mode", [
        (1, 1),
        ("1", 1),
        ("time_of_use", 1),
        ("TIME_OF_USE", 1),
        ("tou", 1),
        ("tou_battery_import", 1),
        (2, 2),
        ("2", 2),
        ("self_consumption", 2),
        ("self", 2),
        (3, 3),
        ("3", 3),
        ("emergency_backup", 3),
        ("backup", 3),
    ])
    async def test_set_mode_legacy_mapping(self, mock_client_internals, input_mode, expected_work_mode):
        """Test that legacy string and int types are mapped correctly internally."""
        client = mock_client_internals
        
        if expected_work_mode == 3:
            await client.set_mode(
                requestedOperatingMode=input_mode, 
                reqbackupForeverFlag=1, 
                reqnextWorkMode=2
            )
        else:
            await client.set_mode(requestedOperatingMode=input_mode)
            
        # Extract the URL from the _post call
        call_args = client._post.call_args[0]
        url = call_args[0]
        
        assert f"workMode={expected_work_mode}" in url
        # Validate that currendId null fallback (set earlier) works
        if expected_work_mode == 1:
            assert "currendId=1001" in url
        elif expected_work_mode == 2:
            assert "currendId=1002" in url
        elif expected_work_mode == 3:
            assert "currendId=1003" in url

    @pytest.mark.parametrize("input_dispatch, expected_string", [
        ("CUSTOM", "CUSTOM"),
        ("HOME", "HOME"),
        ("STANDBY", "STANDBY"),
        ("SELF", "SELF"),
        ("SOLAR", "SOLAR"),
        ("GRID_EXPORT", "GRID_EXPORT"),
        ("GRID_CHARGE", "GRID_CHARGE"),
        (8, "CHARGE_FROM_GRID"),
        ("8", "CHARGE_FROM_GRID"),
        (7, "EXPORT_TO_GRID_PEAKONLY"),
        ("7", "EXPORT_TO_GRID_PEAKONLY"),
    ])
    async def test_set_tou_schedule_legacy_mapping(self, mock_client_internals, input_dispatch, expected_string):
        """Test that legacy dispatch integers and string types map natively without throwing."""
        client = mock_client_internals
        
        # As long as it doesn't throw InvalidTOUScheduleOption, the backward compatibility validator passed!
        await client.set_tou_schedule(
            touMode=input_dispatch, 
            touSchedule=[dict(startHourTime="00:00", endHourTime="24:00", waveType=0, name="test", dispatchId=1)]
        )
        
        assert client._post.called
