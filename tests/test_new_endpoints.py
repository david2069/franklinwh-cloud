import pytest
from unittest.mock import patch, MagicMock
from franklinwh_cloud.client import Client

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

@pytest.mark.asyncio
@patch.object(Client, '_get', return_value={"result": {"upFlag": True}})
async def test_get_notification_settings(mock_get, mock_client):
    res = await mock_client.get_notification_settings(lang="EN_US")
    assert res == {"upFlag": True}
    mock_get.assert_called_once_with(
        "https://energy.franklinwh.com/hes-gateway/terminal/selectEventClassification",
        params={"lang": "EN_US"},
        suppress_gateway=True
    )

@pytest.mark.asyncio
@patch.object(Client, '_get', return_value={"data": {"resources": "dummy"}})
async def test_get_user_resources_new_schema(mock_get, mock_client):
    res = await mock_client.get_user_resources()
    assert res == {"resources": "dummy"}
    mock_get.assert_called_once_with(
        "https://energy.franklinwh.com/hes-gateway/newApi/api-user/app/resource/getUserResources/v2",
        params={"gatewayId": "10060006AXXXXXXXXX"}
    )

@pytest.mark.asyncio
@patch.object(Client, '_get', return_value={"result": {"resources": "legacy"}})
async def test_get_user_resources_legacy_fallback(mock_get, mock_client):
    res = await mock_client.get_user_resources()
    assert res == {"resources": "legacy"}

@pytest.mark.asyncio
@patch.object(Client, '_get', return_value={"result": {"account": "user@example.com"}})
async def test_query_terminal_user_info(mock_get, mock_client):
    res = await mock_client.query_terminal_user_info()
    assert res == {"account": "user@example.com"}
    mock_get.assert_called_once_with(
        "https://energy.franklinwh.com/hes-gateway/terminal/v2/queryTerminalUserInfo",
        suppress_params=True,
        suppress_gateway=True
    )

@pytest.mark.asyncio
@patch.object(Client, '_post', return_value={"code": 200})
async def test_logout(mock_post, mock_client):
    res = await mock_client.logout(refresh_token="ref-tok")
    assert res == {"code": 200}
    mock_post.assert_called_once_with(
        "https://energy.franklinwh.com/hes-gateway/terminal/v2/loginOut",
        {
            "userId": 12345,
            "account": "user@example.com",
            "accountType": 0,
            "refreshToken": "ref-tok",
        },
        suppress_params=True,
        suppress_gateway=True
    )

@pytest.mark.asyncio
@patch.object(Client, '_post', return_value={"code": 200})
async def test_update_fcm_token(mock_post, mock_client):
    res = await mock_client.update_fcm_token(token="fcm-tok", identity="device-id")
    assert res == {"code": 200}
    mock_post.assert_called_once_with(
        "https://energy.franklinwh.com/hes-gateway/terminal/updateTerUserFcmToken",
        None,
        params={"token": "fcm-tok", "identity": "device-id", "lang": "EN_US"},
        suppress_gateway=True
    )

@pytest.mark.asyncio
@patch.object(Client, '_get', return_value={"result": ["msg1"]})
async def test_get_messages_by_type(mock_get, mock_client):
    res = await mock_client.get_messages_by_type(event_types="17,43")
    assert res == ["msg1"]
    mock_get.assert_called_once_with(
        "https://energy.franklinwh.com/hes-gateway/terminal/listDeviceMessagesByType",
        params={
            "pageNum": 1,
            "pageSize": 10,
            "eventTypes": "17,43",
            "gatewayId": "10060006AXXXXXXXXX",
        }
    )

@pytest.mark.asyncio
@patch.object(Client, '_get', return_value={"result": ["log1"]})
async def test_get_run_log_list(mock_get, mock_client):
    res = await mock_client.get_run_log_list(country_id=3)
    assert res == ["log1"]
    mock_get.assert_called_once_with(
        "https://energy.franklinwh.com/hes-gateway/common/country/selectRunLogList",
        params={"countryId": 3},
        suppress_gateway=True
    )

@pytest.mark.asyncio
@patch.object(Client, '_get', return_value={"result": {"isPcsDischgEn": 1}})
async def test_get_system_settings(mock_get, mock_client):
    res = await mock_client.get_system_settings()
    assert res == {"isPcsDischgEn": 1}
    mock_get.assert_called_once_with(
        "https://energy.franklinwh.com/hes-gateway/terminal/system/getSystemSetting",
        params={"gatewayId": "10060006AXXXXXXXXX"}
    )

@pytest.mark.asyncio
@patch.object(Client, '_post', return_value={"code": 200})
async def test_update_system_settings(mock_post, mock_client):
    res = await mock_client.update_system_settings(is_pcs_dischg_en=0, other_flag=1)
    assert res == {"code": 200}
    mock_post.assert_called_once_with(
        "https://energy.franklinwh.com/hes-gateway/terminal/system/updateSystemSetting",
        {
            "gatewayId": "10060006AXXXXXXXXX",
            "isPcsDischgEn": 0,
            "other_flag": 1,
        },
        suppress_params=True,
        suppress_gateway=True
    )

@pytest.mark.asyncio
@patch.object(Client, '_get', return_value={"result": ["tip1"]})
async def test_get_page_by_type_list(mock_get, mock_client):
    res = await mock_client.get_page_by_type_list("typeA")
    assert res == ["tip1"]
    mock_get.assert_called_once_with(
        "https://energy.franklinwh.com/hes-gateway/common/getPageByTypeList",
        params={"typeList": "typeA", "gatewayId": "10060006AXXXXXXXXX"}
    )

@pytest.mark.asyncio
@patch.object(Client, '_get', return_value={"result": True})
async def test_check_ai_dispatch_invitation(mock_get, mock_client):
    res = await mock_client.check_ai_dispatch_invitation()
    assert res is True
    mock_get.assert_called_once_with(
        "https://energy.franklinwh.com/hes-gateway/terminal/aiDispatch/checkAiDispatchInvitation",
        params={"gatewayId": "10060006AXXXXXXXXX"}
    )

@pytest.mark.asyncio
@patch.object(Client, '_get', return_value={"result": 1})
async def test_get_ai_offline_disable_flag(mock_get, mock_client):
    res = await mock_client.get_ai_offline_disable_flag()
    assert res == 1
    mock_get.assert_called_once_with(
        "https://energy.franklinwh.com/hes-gateway/terminal/aiDispatch/getAiOfflineDisableFlag",
        params={"gatewayId": "10060006AXXXXXXXXX"}
    )

@pytest.mark.asyncio
@patch.object(Client, '_get', return_value={"result": {"isVppEligible": True}})
async def test_check_vpp_eligibility(mock_get, mock_client):
    res = await mock_client.check_vpp_eligibility()
    assert res == {"isVppEligible": True}
    mock_get.assert_called_once_with(
        "https://energy.franklinwh.com/hes-gateway/terminal/checkUserVppEligibility",
        suppress_params=True,
        suppress_gateway=True
    )

@pytest.mark.asyncio
@patch.object(Client, '_get', return_value={"result": {"complianceSoc": 20}})
async def test_query_compliance_capacity(mock_get, mock_client):
    res = await mock_client.query_compliance_capacity()
    assert res == {"complianceSoc": 20}
    mock_get.assert_called_once_with(
        "https://energy.franklinwh.com/hes-gateway/terminal/ja12/queryComplianceCapacity",
        params={"gatewayId": "10060006AXXXXXXXXX"}
    )

@pytest.mark.asyncio
@patch.object(Client, '_post', return_value={"code": 200})
async def test_notify_ai_cache(mock_post, mock_client):
    res = await mock_client.notify_ai_cache()
    assert res == {"code": 200}
    mock_post.assert_called_once_with(
        "https://energy.franklinwh.com/hes-gateway/terminal/tou/notify/ai/cache",
        {"gatewayId": "10060006AXXXXXXXXX"},
        suppress_params=True,
        suppress_gateway=True
    )

@pytest.mark.asyncio
@patch.object(Client, '_post', return_value={"result": {"showTipFlag": 1}})
async def test_get_nps_show_tip(mock_post, mock_client):
    res = await mock_client.get_nps_show_tip()
    assert res == {"showTipFlag": 1}
    mock_post.assert_called_once_with(
        "https://energy.franklinwh.com/hes-gateway/terminal/nps/getNpsShowTip",
        {},
        suppress_params=True,
        suppress_gateway=True
    )

@pytest.mark.asyncio
@patch.object(Client, '_get', return_value={"result": {"upFlag": True}})
async def test_whether_popup(mock_get, mock_client):
    res = await mock_client.whether_popup(popup_type=3)
    assert res == {"upFlag": True}
    mock_get.assert_called_once_with(
        "https://energy.franklinwh.com/hes-gateway/terminal/feedback/whetherPopUp",
        params={"gatewayId": "10060006AXXXXXXXXX", "type": "3"}
    )
