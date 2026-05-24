"""Unit tests for the get_gateway_tou_list() name override logic."""

import pytest
from unittest.mock import AsyncMock, MagicMock

# Simulated payload returning the exact issue layout provided by the user
RAW_GATEWAY_RESPONSE = {
    "code": 200,
    "message": "Operate success!",
    "result": {
        "currendId": 85232,
        "list": [
            {
                "id": 29287,
                "oldIndex": 3,
                "name": "Ausgrid EA11 TOU",
                "soc": 10,
                "maxSoc": 100,
                "minSoc": 0,
                "dischargeDepthSoc": None,
                "editSocFlag": True,
                "multiSOCFlag": False,
                "workMode": 1,
                "socExceedTimerEndTime": None,
                "complianceSoc": None,
                "delayMinutes": None,
                "energyIncentivesType": 0,
                "electricityType": 1,
                "displayFlag": None
            },
            {
                "id": 85232,
                "oldIndex": 2,
                "name": "Self-Consumption",
                "soc": 6,
                "maxSoc": 100,
                "minSoc": 0,
                "dischargeDepthSoc": None,
                "editSocFlag": True,
                "multiSOCFlag": False,
                "workMode": 2,
                "socExceedTimerEndTime": None,
                "complianceSoc": None,
                "delayMinutes": None,
                "energyIncentivesType": 0,
                "electricityType": 1,
                "displayFlag": None
            },
            {
                "id": 47522,
                "oldIndex": 1,
                "name": "Emergency Backup",
                "soc": 100,
                "maxSoc": 100,
                "minSoc": 0,
                "dischargeDepthSoc": None,
                "editSocFlag": False,
                "multiSOCFlag": False,
                "workMode": 3,
                "socExceedTimerEndTime": None,
                "complianceSoc": None,
                "delayMinutes": None,
                "energyIncentivesType": 0,
                "electricityType": 1,
                "displayFlag": None
            }
        ],
        "stromEn": 0,
        "sgipFlag": 1,
        "itcFlag": 1,
        "stopMode": 0,
        "gridChargeEn": 0,
        "touSendStatus": None,
        "touAlertMessage": None,
        "backupForeverFlag": 1,
        "timerEndTime": None,
        "timerEndTimeZero": None,
        "timerStartTime": None,
        "timerStartTimeZero": None,
        "zoneInfo": "Australia/Sydney",
        "nextWorkMode": None,
        "tariffSettingFlag": True,
        "tariffName": "Ausgrid EA11 TOU",
        "vppSocVo": {
            "vppSoc": 20,
            "vppMinSoc": 5,
            "vppMaxSoc": 100,
            "vppSocDisplayFlag": False,
            "vppType": 0
        },
        "offlineAiDisableFlag": None
    },
    "success": True
}


def _make_mock_client(post_response):
    """Create a mock client bound with TouMixin.get_gateway_tou_list."""
    from franklinwh_cloud.mixins.tou import TouMixin

    client = MagicMock(spec=TouMixin)
    client.url_base = "https://energy.franklinwh.com/"
    client.gateway = "10060006AXXXXXXXXX"
    client._post = AsyncMock(return_value=post_response)
    
    # Bind get_gateway_tou_list to the mocked instance
    client.get_gateway_tou_list = TouMixin.get_gateway_tou_list.__get__(client)
    return client


@pytest.mark.asyncio
class TestGatewayTouNameOverride:
    """Verify that get_gateway_tou_list intercepts and replaces dynamic TOU names."""

    async def test_overwrites_matching_name_with_trailing_space(self):
        """Must replace 'Ausgrid EA11 TOU' with 'Time-of-Use ' for oldIndex=3, workMode=1."""
        client = _make_mock_client(RAW_GATEWAY_RESPONSE)
        
        data = await client.get_gateway_tou_list()
        
        mode_list = data["result"]["list"]
        tou_mode = next(x for x in mode_list if x["workMode"] == 1)
        
        assert tou_mode["oldIndex"] == 3
        assert tou_mode["name"] == "Time-of-Use "

    async def test_does_not_overwrite_other_operating_modes(self):
        """Must keep 'Self-Consumption' and 'Emergency Backup' untouched."""
        client = _make_mock_client(RAW_GATEWAY_RESPONSE)
        
        data = await client.get_gateway_tou_list()
        
        mode_list = data["result"]["list"]
        self_consumption = next(x for x in mode_list if x["workMode"] == 2)
        emergency_backup = next(x for x in mode_list if x["workMode"] == 3)
        
        assert self_consumption["name"] == "Self-Consumption"
        assert emergency_backup["name"] == "Emergency Backup"

    async def test_graceful_handling_of_malformed_payload(self):
        """Ensure no exception is raised and response passes through if result format is atypical."""
        atypical_response = {
            "code": 200,
            "message": "Operate success!",
            "result": None,
            "success": True
        }
        client = _make_mock_client(atypical_response)
        
        # This call must complete without raising any exceptions
        data = await client.get_gateway_tou_list()
        assert data["result"] is None
