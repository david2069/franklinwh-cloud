"""Tests for Real-Time TOU Pricing calculations.

Verifies the logic inside get_current_tou_price() which maps a provided
datetime object against the active dispatch table to find the current block.
"""

from datetime import datetime
import pytest
import respx
import httpx

from franklinwh_cloud.client import Client
from franklinwh_cloud.auth import TokenAuth

@pytest.fixture
def mock_client():
    """Client configured for mocked backend responses."""
    return Client(TokenAuth("test-token"), "123456789")

@respx.mock
async def test_get_current_tou_price_finds_active_block(mock_client):
    """Test standard fallback matching against everyday blocks."""
    # Define a simplified season table
    test_season = {
        "strategyList": [{
            "seasonName": "Winter",
            "month": "1,2,3,4,11,12",
            "dayTypeVoList": [{
                "dayType": 3,  # Everyday
                "detailVoList": [
                    {
                        "name": "off-peak",
                        "startHourTime": "00:00",
                        "endHourTime": "12:00",
                        "waveType": 0,
                        "dispatchId": 6
                    },
                    {
                        "name": "on-peak",
                        "startHourTime": "12:00",
                        "endHourTime": "19:00",
                        "waveType": 2,
                        "dispatchId": 6
                    },
                    {
                        "name": "off-peak-2",
                        "startHourTime": "19:00",
                        "endHourTime": "24:00",
                        "waveType": 0,
                        "dispatchId": 6
                    }
                ]
            }]
        }]
    }

    respx.get("https://energy.franklinwh.com/hes-gateway/terminal/tou/getTouDispatchDetail?gatewayId=123456789&lang=en_US").mock(
        return_value=httpx.Response(200, json={
            "code": 200,
            "success": True,
            "result": test_season
        })
    )

    # Injecting time inside the On-Peak block
    test_time = datetime(year=2026, month=12, day=2, hour=14, minute=30)
    
    price = await mock_client.get_current_tou_price(now=test_time)
    
    assert price is not None
    assert price["season_name"] == "Winter"
    assert price["day_type_name"] == "Everyday"
    assert price["block_name"] == "on-peak"
    assert price["wave_type_name"] == "On-Peak"
    assert price["minutes_remaining"] == 270  # 19:00 is 1140 minutes - 870 minutes = 270

@respx.mock
async def test_get_current_tou_price_out_of_season(mock_client):
    """Test response when month does not map to any season."""
    test_season = {
        "strategyList": [{
            "seasonName": "Summer",
            "month": "6,7,8",
            "dayTypeVoList": []
        }]
    }

    respx.get("https://energy.franklinwh.com/hes-gateway/terminal/tou/getTouDispatchDetail?gatewayId=123456789&lang=en_US").mock(
        return_value=httpx.Response(200, json={
            "code": 200,
            "success": True,
            "result": test_season
        })
    )

    # Injecting Winter
    test_time = datetime(year=2026, month=12, day=2, hour=14, minute=30)
    
    price = await mock_client.get_current_tou_price(now=test_time)
    assert price == {}

@respx.mock
async def test_get_current_tou_price_day_type_prioritization(mock_client):
    """Ensure it maps to the correct weekday (1) or weekend (2) ruleset natively."""
    test_season = {
        "strategyList": [{
            "seasonName": "Spring",
            "month": "4,5",
            "dayTypeVoList": [
                {
                    "dayType": 2,  # Weekend
                    "detailVoList": [
                        {
                            "name": "weekend-block",
                            "startHourTime": "00:00",
                            "endHourTime": "24:00",
                            "waveType": 0,
                            "dispatchId": 6
                        }
                    ]
                },
                {
                    "dayType": 1,  # Weekday
                    "detailVoList": [
                        {
                            "name": "weekday-block",
                            "startHourTime": "00:00",
                            "endHourTime": "24:00",
                            "waveType": 1,
                            "dispatchId": 7
                        }
                    ]
                }
            ]
        }]
    }

    respx.get("https://energy.franklinwh.com/hes-gateway/terminal/tou/getTouDispatchDetail?gatewayId=123456789&lang=en_US").mock(
        return_value=httpx.Response(200, json={
            "code": 200,
            "success": True,
            "result": test_season
        })
    )

    # April 4, 2026 is a Saturday (Weekend)
    test_weekend = datetime(year=2026, month=4, day=4, hour=12, minute=0)
    price_weekend = await mock_client.get_current_tou_price(now=test_weekend)
    
    assert price_weekend["day_type_name"] == "Weekend"
    assert price_weekend["wave_type_name"] == "Off-Peak"

    # April 6, 2026 is a Monday (Weekday)
    test_weekday = datetime(year=2026, month=4, day=6, hour=12, minute=0)
    price_weekday = await mock_client.get_current_tou_price(now=test_weekday)
    
    assert price_weekday["day_type_name"] == "Weekday"
    assert price_weekday["wave_type_name"] == "Mid-Peak"
