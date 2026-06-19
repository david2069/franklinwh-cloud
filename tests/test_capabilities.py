import pytest
from unittest.mock import patch, MagicMock
from franklinwh_cloud.client import Client
from franklinwh_cloud.discovery import compile_capabilities
from franklinwh_cloud.models import ResolvedCapabilities

@pytest.fixture
def mock_client():
    c = Client.__new__(Client)
    c.gateway = "10060006AXXXXXXXXX"
    c.snno = 0
    c.url_base = "https://energy.franklinwh.com/"
    c.token = "test-token"
    c.fetcher = MagicMock()
    c.fetcher.info = {"userId": 12345, "email": "user@example.com"}
    return c

def test_us_gateway_capabilities():
    # US site (countryId = 2), Gen 2 aGate (sysHdVersion = 103)
    entrance_data = {
        "result": {
            "countryId": 2,
            "solarFlag": True,
            "tariffSettingFlag": True,
            "gridFlag": True,
        }
    }
    device_data = {
        "result": {
            "countryId": 2,
            "gatewayId": "10060006AXXXXXXXXX",
            "sysHdVersion": "103",
            "v2lModeEnable": True,
            "mpptEnFlag": True,
            "apbox20Num": 1,
            "isThreePhaseInstall": 0,
        }
    }
    accessories_data = {
        "result": [
            {"accessoryType": 4, "snSerialNumber": "SC12345"}, # Smart Circuits
            {"accessoryType": 3, "sn": "GEN12345"} # Generator
        ]
    }
    vpp_data = {
        "result": {
            "isVppEligible": True
        }
    }

    caps = compile_capabilities(entrance_data, device_data, accessories_data, vpp_data)
    
    assert isinstance(caps, ResolvedCapabilities)
    assert caps.country_id == 2
    assert caps.agate_generation == 2
    assert caps.gateway_id == "10060006AXXXXXXXXX"
    
    # Solar
    assert caps.solar_installed is True
    assert caps.has_mppt is True
    assert caps.has_apbox is True
    
    # Accessories
    assert caps.has_smart_circuits is True
    assert caps.circuit_count == 3  # US Gen 2 supports 3 circuits
    assert caps.has_generator is True
    assert caps.has_v2l is True  # US supports V2L
    
    # Grid
    assert caps.grid_connected is True
    assert caps.three_phase is False
    
    # VPP & Tariff
    assert caps.vpp_eligible is True
    assert caps.tariff_configured is True

def test_au_gateway_quirks():
    # AU site (countryId = 3), Gen 1 aGate (sysHdVersion = 102)
    entrance_data = {
        "result": {
            "countryId": 3,
            "solarFlag": True,
            "tariffSettingFlag": False,
            "gridFlag": True,
        }
    }
    device_data = {
        "result": {
            "countryId": 3,
            "gatewayId": "10060006AXXXXXXXXX",
            "sysHdVersion": "102",
            "v2lModeEnable": True,  # Mock true to verify AU overrides it
            "mpptEnFlag": False,
            "apbox20Num": 0,
            "isThreePhaseInstall": 1,
        }
    }
    accessories_data = {
        "result": [
            {"accessoryType": 4, "snSerialNumber": "SC12345"}, # Smart Circuits
        ]
    }
    vpp_data = {
        "result": {
            "isVppEligible": True
        }
    }

    caps = compile_capabilities(entrance_data, device_data, accessories_data, vpp_data)
    
    assert caps.country_id == 3
    assert caps.agate_generation == 1
    assert caps.three_phase is True
    
    # Accessories & Quirks
    assert caps.has_smart_circuits is True
    assert caps.circuit_count == 2  # AU capped at 2 circuits
    assert caps.has_v2l is False    # V2L physically locked to False in AU
    
    # Pricing & VPP
    assert caps.vpp_eligible is True
    assert caps.tariff_configured is False

def test_offgrid_gateway_capabilities():
    # Off-grid US Gen 2 installation
    entrance_data = {
        "result": {
            "countryId": 2,
            "solarFlag": True,
            "tariffSettingFlag": True,
            "gridFlag": False,
        }
    }
    device_data = {
        "result": {
            "countryId": 2,
            "gatewayId": "10060006AXXXXXXXXX",
            "sysHdVersion": "103",
            "offGirdFlag": True,  # Off-grid flag
            "v2lModeEnable": True,
            "mpptEnFlag": True,
            "apbox20Num": 1,
            "isThreePhaseInstall": 0,
        }
    }
    accessories_data = {
        "result": []
    }
    vpp_data = {
        "result": {
            "isVppEligible": True  # Mock eligible to verify offgrid overrides it
        }
    }

    caps = compile_capabilities(entrance_data, device_data, accessories_data, vpp_data)
    
    assert caps.grid_connected is False
    assert caps.vpp_eligible is False  # Forced to False on off-grid installs

@pytest.mark.asyncio
async def test_get_resolved_capabilities_client_helper(mock_client):
    mock_entrance = {"result": {"countryId": 2, "solarFlag": True}}
    mock_device = {"result": {"countryId": 2, "gatewayId": "10060006AXXXXXXXXX", "sysHdVersion": "103"}}
    mock_accessories = {"result": []}
    mock_vpp = {"result": {"isVppEligible": True}}

    with patch.object(Client, "get_entrance_info", return_value=mock_entrance) as mock_get_ent, \
         patch.object(Client, "get_device_info", return_value=mock_device) as mock_get_dev, \
         patch.object(Client, "get_accessories", return_value=mock_accessories) as mock_get_acc, \
         patch.object(Client, "check_vpp_eligibility", return_value=mock_vpp) as mock_get_vpp:
         
        caps = await mock_client.get_resolved_capabilities()
        
        assert isinstance(caps, ResolvedCapabilities)
        assert caps.country_id == 2
        assert caps.agate_generation == 2
        assert caps.solar_installed is True
        assert caps.vpp_eligible is True
        
        mock_get_ent.assert_called_once()
        mock_get_dev.assert_called_once()
        mock_get_acc.assert_called_once_with(0)
        mock_get_vpp.assert_called_once()
