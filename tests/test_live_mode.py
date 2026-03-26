"""Live integration tests for operating modes."""
import pytest
from franklinwh_cloud.client import Client, TokenFetcher
from franklinwh_cloud.const import TIME_OF_USE, SELF_CONSUMPTION, EMERGENCY_BACKUP

@pytest.mark.live
@pytest.mark.asyncio
async def test_live_set_mode(live_credentials):
    """Test setting operating modes dynamically directly against the Cloud API."""
    email, password, gateway = live_credentials
    fetcher = TokenFetcher(email, password)
    client = Client(fetcher, gateway)
    
    # 1. Switch to Self-Consumption without explicit SOC bounds
    # Validates we do not send literal `&soc=None` causing an upstream HTTP 400
    res = await client.set_mode(
        requestedOperatingMode=SELF_CONSUMPTION,
        requestedSOC=None,
        reqbackupForeverFlag=None,
        reqnextWorkMode=None,
        reqdurationMinutes=None
    )
    assert res is True, "Failed to set SELF_CONSUMPTION mode natively"

    # 2. Switch to Time-Of-Use with an explicit SOC
    res = await client.set_mode(
        requestedOperatingMode=TIME_OF_USE,
        requestedSOC=5,
        reqbackupForeverFlag=None,
        reqnextWorkMode=None,
        reqdurationMinutes=None
    )
    assert res is True, "Failed to set TIME_OF_USE mode natively"
    
    # 3. Mode validation check using get_mode
    current_mode = await client.get_mode()
    assert isinstance(current_mode, dict)
    assert current_mode.get("workMode") == TIME_OF_USE
