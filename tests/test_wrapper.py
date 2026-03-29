import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from franklinwh_cloud import FranklinWHCloud

@pytest.fixture
def mock_password_auth():
    with patch("franklinwh_cloud.wrapper.PasswordAuth") as MockAuth:
        mock_auth_instance = MagicMock()
        mock_auth_instance.get_token = AsyncMock(return_value="mock_jwt_token")
        mock_auth_instance.info = {"gatewayList": [{"sn": "10060006A02F241XXXX"}]}
        MockAuth.return_value = mock_auth_instance
        yield MockAuth

@pytest.fixture
def mock_client():
    with patch("franklinwh_cloud.wrapper.Client") as MockClient:
        mock_client_instance = AsyncMock()
        mock_client_instance.get_stats = AsyncMock(return_value="mock_stats")
        mock_client_instance.get_mode = AsyncMock(return_value="mock_mode")
        MockClient.return_value = mock_client_instance
        yield MockClient

@pytest.mark.asyncio
async def test_wrapper_initializes_and_proxies_to_client(mock_password_auth, mock_client):
    # 1. Instantiate the legacy wrapper
    client = FranklinWHCloud("user@example.com", "secret")
    
    # 2. Login (should initialize Auth)
    await client.login()
    mock_password_auth.assert_called_once_with("user@example.com", "secret")
    
    # 3. Select Gateway (should auto-discover gateway and initialize Client)
    await client.select_gateway()
    mock_client.assert_called_once()
    
    # 4. Proxy Calls (should route to the inner Client)
    stats = await client.get_stats()
    assert stats == "mock_stats"
    mock_client.return_value.get_stats.assert_called_once()
    
    mode = await client.get_mode()
    assert mode == "mock_mode"
    mock_client.return_value.get_mode.assert_called_once()

@pytest.mark.asyncio
async def test_wrapper_explicit_gateway(mock_password_auth, mock_client):
    client = FranklinWHCloud("user@example.com", "secret")
    await client.select_gateway(serial="SPECIFIC_SERIAL")
    mock_client.assert_called_once_with(mock_password_auth.return_value, "SPECIFIC_SERIAL")

@pytest.mark.asyncio
async def test_proxy_without_init_raises_runtime_error():
    client = FranklinWHCloud("user@example.com", "secret")
    with pytest.raises(RuntimeError, match="Client not initialized"):
        await client.get_stats()
