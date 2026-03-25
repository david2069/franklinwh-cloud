import pytest
import json
from unittest.mock import patch
from franklinwh_cloud.client import Client

@pytest.fixture
def mock_client():
    c = Client.__new__(Client)
    c.gateway = "TEST-GW-001"
    c.snno = 0
    c.url_base = "https://energy.franklinwh.com/"
    c.token = "test-token"
    c.fetcher = None
    return c

@pytest.mark.asyncio
@patch.object(Client, '_mqtt_send', return_value={"result": {"dataArea": "{}"}})
async def test_set_smart_circuit_state(mock_send, mock_client):
    await mock_client.set_smart_circuit_state(1, True)
    
    encoded_payload = json.loads(mock_send.call_args[0][0])
    assert 310 == encoded_payload["cmdType"]
    assert "Sw1Mode" in str(encoded_payload["dataArea"])

@pytest.mark.asyncio
@patch.object(Client, '_mqtt_send', return_value={"result": {"dataArea": "{}"}})
async def test_set_smart_circuit_soc_cutoff(mock_send, mock_client):
    await mock_client.set_smart_circuit_soc_cutoff(2, enable=False, soc=0)
    
    encoded_payload = json.loads(mock_send.call_args[0][0])
    payload_str = str(encoded_payload["dataArea"])
    assert "Sw2SocLowSet" in payload_str
    assert "Sw2AtuoEn" in payload_str

def test_invalid_circuit_id(mock_client):
    with pytest.raises(ValueError, match="Circuit must be 1, 2, or 3"):
        import asyncio
        asyncio.run(mock_client.set_smart_circuit_state(4, True))
