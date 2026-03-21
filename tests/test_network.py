"""Tests for network API methods in DevicesMixin.

Tests cover: get_network_info, get_wifi_config, scan_wifi_networks,
scan_wifi_networks_poll, get_connection_status, get_network_switches,
and the deprecated get_agate_network_info.
"""

import json
import warnings

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from franklinwh_cloud.exceptions import DeviceTimeoutException


# ── Mock response data ──────────────────────────────────────────────

MOCK_NETWORK_INFO_RAW = json.dumps({
    "result": {
        "commSetPara": {
            "currentNetType": 3,
            "wifiMAC": "4C:24:CE:67:3A:7C",
            "wifiDHCP": 1,
            "wifiStaticIP": "192.168.0.110",
            "wifiDNS": "8.8.8.8",
            "wifiGateWay": "192.168.0.1",
            "eth0MAC": "AA:BB:CC:DD:EE:FF",
            "eth0DHCP": 0,
            "eth0StaticIP": "10.0.0.5",
            "eth0DNS": "8.8.4.4",
            "eth0GateWay": "10.0.0.1",
            "eth1MAC": "",
            "eth1DHCP": 0,
            "eth1StaticIP": "",
            "eth1DNS": "",
            "eth1GateWay": "",
            "operatorMAC": "11:22:33:44:55:66",
            "operatorDNS": "8.8.8.8",
            "operatorRSSI": -65,
            "awsStatus": 1,
        }
    }
})

MOCK_WIFI_CONFIG_RAW = json.dumps({
    "wifi_SSID": "do_not_trespass",
    "wifi_Pw": "secret123",
    "ap_SSID": "FranklinWH_AP",
    "ap_Pw": "ap_pass",
    "wifi_Safety": 1,
})

MOCK_SCAN_COMPLETE_RAW = json.dumps({
    "result": 0,
    "wifi_list": [
        {"ssid": "do_not_trespass", "rssi": -45, "security": 1},
        {"ssid": "neighbor_wifi", "rssi": -70, "security": 1},
    ],
})

MOCK_SCAN_PENDING_RAW = json.dumps({
    "result": 1,
    "reason": 3,
})

MOCK_CONNECTION_STATUS_RAW = json.dumps({
    "routerStatus": 1,
    "netStatus": 1,
    "awsStatus": 1,
})

MOCK_NETWORK_SWITCHES_RAW = json.dumps({
    "ethernet0NetSwitch": 1,
    "ethernet1NetSwitch": 0,
    "wifiNetSwitch": 1,
    "4GNetSwitch": 1,
})


# ── Mock client builder ─────────────────────────────────────────────

def _make_mock_client(mqtt_return_raw=None):
    """Create a mock Client with DevicesMixin methods bound."""
    from franklinwh_cloud.mixins.devices import DevicesMixin

    client = MagicMock(spec=DevicesMixin)
    client.gateway = "TEST_GATEWAY"

    # Mock _build_payload to return a dummy payload
    client._build_payload = MagicMock(return_value={"dummy": True})

    # Mock _mqtt_send to return the raw data in the expected structure
    if mqtt_return_raw is not None:
        client._mqtt_send = AsyncMock(return_value={
            "result": {"dataArea": mqtt_return_raw}
        })

    return client


def _bind_method(client, method_name):
    """Bind a real DevicesMixin method to the mock client."""
    from franklinwh_cloud.mixins.devices import DevicesMixin
    method = getattr(DevicesMixin, method_name)
    setattr(client, method_name, method.__get__(client))


# ── get_network_info tests ───────────────────────────────────────────

class TestGetNetworkInfo:
    """Tests for get_network_info()."""

    @pytest.mark.asyncio
    async def test_parses_all_interfaces(self):
        """Should return wifi, eth0, eth1, operator, and awsStatus keys."""
        client = _make_mock_client(MOCK_NETWORK_INFO_RAW)
        _bind_method(client, "get_network_info")
        result = await client.get_network_info()

        assert "wifi" in result
        assert "eth0" in result
        assert "eth1" in result
        assert "operator" in result
        assert "awsStatus" in result
        assert "currentNetType" in result

    @pytest.mark.asyncio
    async def test_dhcp_bool_conversion(self):
        """wifiDHCP: 1 should become dhcp: True, eth0DHCP: 0 → False."""
        client = _make_mock_client(MOCK_NETWORK_INFO_RAW)
        _bind_method(client, "get_network_info")
        result = await client.get_network_info()

        assert result["wifi"]["dhcp"] is True
        assert result["eth0"]["dhcp"] is False

    @pytest.mark.asyncio
    async def test_nested_commSetPara(self):
        """Should correctly extract data from nested result.commSetPara."""
        client = _make_mock_client(MOCK_NETWORK_INFO_RAW)
        _bind_method(client, "get_network_info")
        result = await client.get_network_info()

        assert result["wifi"]["mac"] == "4C:24:CE:67:3A:7C"
        assert result["wifi"]["ip"] == "192.168.0.110"
        assert result["currentNetType"] == 3
        assert result["awsStatus"] == 1

    @pytest.mark.asyncio
    async def test_invalid_json_raises(self):
        """Should raise DeviceTimeoutException on invalid JSON response."""
        client = _make_mock_client("not valid json {{")
        _bind_method(client, "get_network_info")

        with pytest.raises(DeviceTimeoutException, match="cmdType 317"):
            await client.get_network_info()


# ── get_wifi_config tests ────────────────────────────────────────────

class TestGetWifiConfig:
    """Tests for get_wifi_config()."""

    @pytest.mark.asyncio
    async def test_returns_expected_keys(self):
        """Should return wifi_ssid, wifi_password, ap_ssid, ap_password, wifi_safety."""
        client = _make_mock_client(MOCK_WIFI_CONFIG_RAW)
        _bind_method(client, "get_wifi_config")
        result = await client.get_wifi_config()

        assert result["wifi_ssid"] == "do_not_trespass"
        assert result["ap_ssid"] == "FranklinWH_AP"
        assert result["wifi_safety"] == 1

    @pytest.mark.asyncio
    async def test_invalid_json_raises(self):
        """Should raise DeviceTimeoutException on invalid JSON."""
        client = _make_mock_client("")
        _bind_method(client, "get_wifi_config")

        with pytest.raises(DeviceTimeoutException, match="cmdType 337"):
            await client.get_wifi_config()


# ── scan_wifi_networks tests ─────────────────────────────────────────

class TestScanWifiNetworks:
    """Tests for scan_wifi_networks()."""

    @pytest.mark.asyncio
    async def test_complete_scan(self):
        """result=0 should return scan data."""
        client = _make_mock_client(MOCK_SCAN_COMPLETE_RAW)
        _bind_method(client, "scan_wifi_networks")
        result = await client.scan_wifi_networks()

        assert result["result"] == 0
        assert len(result["wifi_list"]) == 2

    @pytest.mark.asyncio
    async def test_pending_scan(self):
        """result=1 should return pending status."""
        client = _make_mock_client(MOCK_SCAN_PENDING_RAW)
        _bind_method(client, "scan_wifi_networks")
        result = await client.scan_wifi_networks()

        assert result["result"] == 1
        assert result["reason"] == 3

    @pytest.mark.asyncio
    async def test_invalid_json_raises(self):
        """Should raise DeviceTimeoutException on bad response."""
        client = _make_mock_client(None)
        client._mqtt_send = AsyncMock(return_value={
            "result": {"dataArea": 12345}  # Not a string
        })
        _bind_method(client, "scan_wifi_networks")

        with pytest.raises(DeviceTimeoutException, match="cmdType 335"):
            await client.scan_wifi_networks()


# ── scan_wifi_networks_poll tests ────────────────────────────────────

class TestScanWifiNetworksPoll:
    """Tests for scan_wifi_networks_poll()."""

    @pytest.mark.asyncio
    async def test_returns_on_first_success(self):
        """Should return immediately when scan completes on first attempt."""
        client = _make_mock_client()
        _bind_method(client, "scan_wifi_networks_poll")
        client.scan_wifi_networks = AsyncMock(return_value={"result": 0, "wifi_list": []})

        result = await client.scan_wifi_networks_poll(max_attempts=3, delay_s=0)
        assert result["result"] == 0
        assert client.scan_wifi_networks.call_count == 1

    @pytest.mark.asyncio
    async def test_polls_until_complete(self):
        """Should retry when pending, then return on success."""
        client = _make_mock_client()
        _bind_method(client, "scan_wifi_networks_poll")
        client.scan_wifi_networks = AsyncMock(side_effect=[
            {"result": 1, "reason": 3},  # pending
            {"result": 1, "reason": 3},  # pending
            {"result": 0, "wifi_list": [{"ssid": "net1"}]},  # complete
        ])

        result = await client.scan_wifi_networks_poll(max_attempts=3, delay_s=0)
        assert result["result"] == 0
        assert client.scan_wifi_networks.call_count == 3

    @pytest.mark.asyncio
    async def test_exhausts_retries(self):
        """Should return last result after max attempts."""
        client = _make_mock_client()
        _bind_method(client, "scan_wifi_networks_poll")
        client.scan_wifi_networks = AsyncMock(return_value={"result": 1, "reason": 3})

        result = await client.scan_wifi_networks_poll(max_attempts=2, delay_s=0)
        assert result["result"] == 1
        assert client.scan_wifi_networks.call_count == 2


# ── get_connection_status tests ──────────────────────────────────────

class TestGetConnectionStatus:
    """Tests for get_connection_status()."""

    @pytest.mark.asyncio
    async def test_returns_expected_keys(self):
        """Should return routerStatus, netStatus, awsStatus."""
        client = _make_mock_client(MOCK_CONNECTION_STATUS_RAW)
        _bind_method(client, "get_connection_status")
        result = await client.get_connection_status()

        assert result["routerStatus"] == 1
        assert result["netStatus"] == 1
        assert result["awsStatus"] == 1

    @pytest.mark.asyncio
    async def test_invalid_json_raises(self):
        """Should raise DeviceTimeoutException on bad response."""
        client = _make_mock_client("}")
        _bind_method(client, "get_connection_status")

        with pytest.raises(DeviceTimeoutException, match="cmdType 339"):
            await client.get_connection_status()


# ── get_network_switches tests ───────────────────────────────────────

class TestGetNetworkSwitches:
    """Tests for get_network_switches()."""

    @pytest.mark.asyncio
    async def test_returns_all_switches(self):
        """Should return all 4 interface switch states."""
        client = _make_mock_client(MOCK_NETWORK_SWITCHES_RAW)
        _bind_method(client, "get_network_switches")
        result = await client.get_network_switches()

        assert result["ethernet0NetSwitch"] == 1
        assert result["ethernet1NetSwitch"] == 0
        assert result["wifiNetSwitch"] == 1
        assert result["4GNetSwitch"] == 1

    @pytest.mark.asyncio
    async def test_invalid_json_raises(self):
        """Should raise DeviceTimeoutException on bad response."""
        client = _make_mock_client(None)
        client._mqtt_send = AsyncMock(return_value={
            "result": {"dataArea": None}
        })
        _bind_method(client, "get_network_switches")

        with pytest.raises(DeviceTimeoutException, match="cmdType 341"):
            await client.get_network_switches()


# ── get_agate_network_info (deprecated) tests ────────────────────────

class TestGetAgateNetworkInfoDeprecated:
    """Tests for the deprecated get_agate_network_info()."""

    @pytest.mark.asyncio
    async def test_emits_deprecation_warning(self):
        """Should emit DeprecationWarning when called."""
        client = _make_mock_client(MOCK_CONNECTION_STATUS_RAW)
        _bind_method(client, "get_agate_network_info")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            await client.get_agate_network_info("2")
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "deprecated" in str(w[0].message).lower()

    @pytest.mark.asyncio
    async def test_type_1_uses_cmdtype_317(self):
        """requestType '1' should build payload with cmdType 317."""
        client = _make_mock_client(MOCK_NETWORK_INFO_RAW)
        _bind_method(client, "get_agate_network_info")

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            await client.get_agate_network_info("1")

        client._build_payload.assert_called_with(317, {"opt": 0, "paraType": 6})

    @pytest.mark.asyncio
    async def test_invalid_type_raises(self):
        """Invalid requestType should raise BadRequestParsingError."""
        from franklinwh_cloud.exceptions import BadRequestParsingError
        client = _make_mock_client(MOCK_CONNECTION_STATUS_RAW)
        _bind_method(client, "get_agate_network_info")

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            with pytest.raises(BadRequestParsingError):
                await client.get_agate_network_info("99")
