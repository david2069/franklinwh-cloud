import pytest
from unittest.mock import AsyncMock, MagicMock
from franklinwh_cloud.client import Client
from franklinwh_cloud.force_state import VPPDetection

@pytest.fixture
def mock_client(tmp_path):
    fetcher = MagicMock()
    fetcher.info = {"token": "fake-token"}
    
    client = Client(fetcher, "GW123", force_state_dir=str(tmp_path))
    
    # Mock network methods
    client.get_device_composite_info = AsyncMock()
    client.get_gateway_tou_list = AsyncMock()
    client.get_programme_info = AsyncMock()
    client.get_programme_info.return_value = {"flag": 0}
    client.set_mode = AsyncMock()
    client.set_tou_schedule = AsyncMock()
    client.update_soc = AsyncMock()
    
    return client


@pytest.mark.asyncio
async def test_force_preflight_no_vpp(mock_client):
    mock_client.get_device_composite_info.return_value = {
        "result": {"runtimeData": {"run_status": 2}}
    }
    mock_client.get_gateway_tou_list.return_value = {
        "result": {}
    }
    
    vpp = await mock_client._force_preflight("force_charge")
    assert not vpp.is_locked
    assert not vpp.cloud_vpp_enrolled


@pytest.mark.asyncio
async def test_force_preflight_vpp_locked(mock_client):
    mock_client.get_device_composite_info.return_value = {
        "result": {"runtimeData": {"run_status": 9}}
    }
    mock_client.get_gateway_tou_list.return_value = {
        "result": {}
    }
    
    from franklinwh_cloud.exceptions import ForceVPPLockError
    
    with pytest.raises(ForceVPPLockError):
        await mock_client._force_preflight("force_charge")


@pytest.mark.asyncio
async def test_force_charge_activate(mock_client):
    mock_client.get_device_composite_info.return_value = {
        "result": {
            "currentWorkMode": 2,
            "runtimeData": {"run_status": 2, "soc": 20}
        }
    }
    mock_client.get_gateway_tou_list.return_value = {
        "result": {
            "list": [{"workMode": 2, "soc": 20}]
        }
    }
    
    session = await mock_client.force_charge(max_soc=90)
    
    assert session.action == "force_charge"
    assert session.max_soc == 90
    
    # Assert network calls
    mock_client.set_mode.assert_called_once_with("tou_custom")
    mock_client.set_tou_schedule.assert_called_once()
    mock_client.update_soc.assert_called_once_with(requestedSOC=90, workMode=1, electricityType=1)
    
    # Assert state store
    assert mock_client._force_state.has_active("GW123")


@pytest.mark.asyncio
async def test_force_discharge_vpp_clamp(mock_client):
    mock_client.get_device_composite_info.return_value = {
        "result": {
            "currentWorkMode": 2,
            "runtimeData": {"run_status": 2, "soc": 80}
        }
    }
    mock_client.get_gateway_tou_list.return_value = {
        "result": {
            "list": [{"workMode": 2, "soc": 20}],
            "todayVppVo": {"vppFlag": 1},
            "vppSocVo": {"vppSoc": 30, "vppType": 1}
        }
    }
    
    # Try to discharge to 10%, but VPP reserve is 30%
    session = await mock_client.force_discharge(min_soc=10)
    
    assert session.action == "force_discharge"
    assert session.min_soc == 30  # Clamped!
    
    mock_client.update_soc.assert_called_once_with(requestedSOC=30, workMode=1, electricityType=1)
