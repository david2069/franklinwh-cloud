"""Tests for get_network_state() and scan_wifi_networks_ranked().

All fixtures in this module are verbatim payloads captured from live hardware
in the HAR corpus (see docs/NETWORK_CONNECTIVITY_DESIGN.md section 2.1), with
SSIDs and credentials redacted per .agents/policies/pii_policy.md. Where a
payload shape varies by firmware, both variants are covered.
"""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock


# ── HAR-derived fixtures ─────────────────────────────────────────────
# Source: hars/HTTPToolkit_2026-03-20_05-38.har entry 3165 (post-switch, on WiFi)

MOCK_317_ON_WIFI = json.dumps({
    "optType": 0, "paraType": 6, "result": 0,
    "commSetPara": {
        "opt": 0, "result": 0, "reason": 0,
        "currentNetType": 3,
        "wifiDHCP": 1, "wifiMAC": "4C:24:CE:67:3A:7C",
        "wifiStaticIP": "192.168.0.110", "wifiDNS": "8.8.8.8",
        "wifiGateWay": "192.168.0.1",
        "eth0DHCP": 0, "eth0MAC": "88:C9:B3:20:00:80",
        "eth0StaticIP": "0.0.0.0", "eth0DNS": "8.8.8.8",
        "eth0GateWay": "172.16.1.1",
        "eth1DHCP": 1, "eth1MAC": "88:C9:B3:21:2C:B8",
        "eth1StaticIP": "0.0.0.0", "eth1DNS": "8.8.8.8",
        "eth1GateWay": "0.0.0.0",
        "operatorMAC": "E6:4F:68:B1:91:5C", "operatorDNS": "192.192.192.192",
        "operatorRSSI": 22,
        "awsStatus": 1,
    },
})

# Source: same HAR, entry 3141 (on 4G, WiFi holding no lease)
MOCK_317_ON_4G = json.dumps({
    "optType": 0, "paraType": 6, "result": 0,
    "commSetPara": {
        "opt": 0, "result": 0, "reason": 0,
        "currentNetType": 4,
        "wifiDHCP": 1, "wifiMAC": "4C:24:CE:67:3A:7C",
        "wifiStaticIP": "0.0.0.0", "wifiDNS": "8.8.8.8",
        "wifiGateWay": "0.0.0.0",
        "eth0DHCP": 0, "eth0MAC": "88:C9:B3:20:00:80",
        "eth0StaticIP": "0.0.0.0", "eth0DNS": "8.8.8.8",
        "eth0GateWay": "172.16.1.1",
        "eth1DHCP": 1, "eth1MAC": "88:C9:B3:21:2C:B8",
        "eth1StaticIP": "0.0.0.0", "eth1DNS": "8.8.8.8",
        "eth1GateWay": "0.0.0.0",
        "operatorMAC": "E6:4F:68:B1:91:5C", "operatorDNS": "192.192.192.192",
        "operatorRSSI": 22,
        "awsStatus": 1,
    },
})

# Short-form 339 — older firmware, no extended fields
MOCK_339_SHORT = json.dumps({
    "opt": 0, "result": 0, "reason": 0,
    "routerStatus": 0, "netStatus": 0, "awsStatus": 0,
})

# Extended-form 339 — newer firmware. Note routerStatus == 4, which is exactly
# the value that made the old bool() coercion report "connected".
MOCK_339_EXTENDED_4G = json.dumps({
    "opt": 0, "result": 0, "reason": 0,
    "routerStatus": 4, "netStatus": 0, "awsStatus": 0,
    "EthConnectRouterStatus": 0, "wifiConnectRouterStatus": 0,
    "4GConnectBSStatus": 1,
    "WifiSignalStrength": 0, "4GSignalStrength": 45,
    "currentNetType": 4,
})

MOCK_341_ALL_ON = json.dumps({
    "opt": 0, "result": 0, "reason": 0,
    "ethernet0NetSwitch": 1, "ethernet1NetSwitch": 1,
    "wifiNetSwitch": 1, "4GNetSwitch": 1,
})

MOCK_341_ONLY_WIFI = json.dumps({
    "opt": 0, "result": 0, "reason": 0,
    "ethernet0NetSwitch": 0, "ethernet1NetSwitch": 0,
    "wifiNetSwitch": 1, "4GNetSwitch": 0,
})

# Source: same HAR, entry 3158 — real scan, SSIDs redacted, RSSI values verbatim.
MOCK_335_COMPLETE = json.dumps({
    "result": 0, "reason": 0,
    "wifi_Info": [
        {"wifi_SSID": "net_a", "wifi_RSSI": 76, "wifi_Safety": 1},
        {"wifi_SSID": "net_b", "wifi_RSSI": 100, "wifi_Safety": 1},
        {"wifi_SSID": "net_c", "wifi_RSSI": 62, "wifi_Safety": 1},
        {"wifi_SSID": "net_b", "wifi_RSSI": 82, "wifi_Safety": 1},
        {"wifi_SSID": "net_b", "wifi_RSSI": 100, "wifi_Safety": 1},
        {"wifi_SSID": "net_d", "wifi_RSSI": 68, "wifi_Safety": 1},
        {"wifi_SSID": "net_e", "wifi_RSSI": 26, "wifi_Safety": 1},
        {"wifi_SSID": "net_open", "wifi_RSSI": 100, "wifi_Safety": 0},
        {"wifi_SSID": "net_b", "wifi_RSSI": 38, "wifi_Safety": 1},
    ],
})

MOCK_335_PENDING = json.dumps({"result": 1, "reason": 3})


# ── Helpers ──────────────────────────────────────────────────────────

GATEWAY = "AGATE_TEST_SERIAL_0001"

# simCardStatus lives on the gateway-list object, not in any cmdType. 2 = Active.
SIM_ACTIVE = 2
SIM_INACTIVE = 1


def _client_with_reads(raw_317, raw_339, raw_341, sim_status=SIM_ACTIVE,
                       gateway_list_fails=False):
    """Build a mock client whose network reads return the given payloads.

    get_home_gateway_list lives on AccountMixin rather than DevicesMixin, so it
    is stubbed rather than bound — get_network_state() consults it for SIM state.
    """
    from franklinwh_cloud.mixins.devices import DevicesMixin

    client = MagicMock(spec=DevicesMixin)
    client.gateway = GATEWAY
    client._build_payload = MagicMock(return_value={"dummy": True})

    async def _send(payload):
        cmd = client._build_payload.call_args[0][0]
        return {"result": {"dataArea": {317: raw_317, 339: raw_339, 341: raw_341}[int(cmd)]}}

    client._mqtt_send = AsyncMock(side_effect=_send)

    if gateway_list_fails:
        client.get_home_gateway_list = AsyncMock(side_effect=RuntimeError("REST down"))
    else:
        client.get_home_gateway_list = AsyncMock(return_value={
            "result": [{"id": GATEWAY, "simCardStatus": sim_status}]
        })

    for name in ("get_network_info", "get_connection_status",
                 "get_network_switches", "get_network_state"):
        setattr(client, name, getattr(DevicesMixin, name).__get__(client))
    return client


def _client_with_scan(*raw_sequence):
    from franklinwh_cloud.mixins.devices import DevicesMixin

    client = MagicMock(spec=DevicesMixin)
    client.gateway = "TEST"
    client._build_payload = MagicMock(return_value={"dummy": True})
    client._mqtt_send = AsyncMock(
        side_effect=[{"result": {"dataArea": r}} for r in raw_sequence]
    )
    client.scan_wifi_networks_ranked = (
        DevicesMixin.scan_wifi_networks_ranked.__get__(client)
    )
    return client


# ── get_network_state ────────────────────────────────────────────────

class TestGetNetworkState:

    @pytest.mark.asyncio
    async def test_active_is_wifi_with_address(self):
        client = _client_with_reads(MOCK_317_ON_WIFI, MOCK_339_SHORT, MOCK_341_ALL_ON)
        state = await client.get_network_state()

        assert state["active"]["id"] == 3
        assert state["active"]["key"] == "wifi"
        assert state["active"]["label"] == "WiFi"
        assert state["active"]["ip"] == "192.168.0.110"
        assert state["active"]["gateway"] == "192.168.0.1"

    @pytest.mark.asyncio
    async def test_active_is_never_presented_as_user_configured(self):
        """The aGate self-selects transport — the contract must say so."""
        client = _client_with_reads(MOCK_317_ON_WIFI, MOCK_339_SHORT, MOCK_341_ALL_ON)
        state = await client.get_network_state()
        assert state["active"]["selection"] == "device-managed"

    @pytest.mark.asyncio
    async def test_unassigned_ip_reported_as_none_not_zero(self):
        """0.0.0.0 means 'associated but no DHCP lease' — must not look like an IP."""
        client = _client_with_reads(MOCK_317_ON_4G, MOCK_339_SHORT, MOCK_341_ALL_ON)
        state = await client.get_network_state()

        wifi = next(i for i in state["interfaces"] if i["key"] == "wifi")
        assert wifi["ip"] is None
        assert wifi["link"] is False

    @pytest.mark.asyncio
    async def test_all_four_interfaces_present(self):
        client = _client_with_reads(MOCK_317_ON_WIFI, MOCK_339_SHORT, MOCK_341_ALL_ON)
        state = await client.get_network_state()

        assert [i["key"] for i in state["interfaces"]] == ["eth0", "eth1", "wifi", "4g"]
        assert sum(1 for i in state["interfaces"] if i["is_active"]) == 1

    @pytest.mark.asyncio
    async def test_router_status_4_is_not_reported_as_connected(self):
        """routerStatus is not a boolean — 4 must not become True."""
        client = _client_with_reads(MOCK_317_ON_4G, MOCK_339_EXTENDED_4G, MOCK_341_ALL_ON)
        state = await client.get_network_state()

        assert state["cloud"]["router_status_raw"] == 4
        assert state["cloud"]["aws_connected"] is False
        assert state["cloud"]["internet"] is False

    @pytest.mark.asyncio
    async def test_extended_339_is_detected_and_used(self):
        client = _client_with_reads(MOCK_317_ON_4G, MOCK_339_EXTENDED_4G, MOCK_341_ALL_ON)
        state = await client.get_network_state()

        assert state["source"]["extended_339"] is True
        cell = next(i for i in state["interfaces"] if i["key"] == "4g")
        assert cell["link"] is True          # from 4GConnectBSStatus
        eth0 = next(i for i in state["interfaces"] if i["key"] == "eth0")
        assert eth0["link"] is False         # from EthConnectRouterStatus

    @pytest.mark.asyncio
    async def test_short_339_falls_back_without_crashing(self):
        client = _client_with_reads(MOCK_317_ON_WIFI, MOCK_339_SHORT, MOCK_341_ALL_ON)
        state = await client.get_network_state()
        assert state["source"]["extended_339"] is False

    @pytest.mark.asyncio
    async def test_cellular_signal_not_labelled_as_percentage(self):
        """operatorRSSI is a vendor scale (0-52), not a percentage."""
        client = _client_with_reads(MOCK_317_ON_WIFI, MOCK_339_SHORT, MOCK_341_ALL_ON)
        state = await client.get_network_state()

        cell = next(i for i in state["interfaces"] if i["key"] == "4g")
        assert cell["signal_raw"] == 22
        assert "signal_pct" not in cell

    @pytest.mark.asyncio
    async def test_active_transport_counts_as_fallback_for_a_different_target(self):
        """Live case: on 4G, WiFi has no lease. Rewriting WiFi is safe — 4G holds.

        Reproduces the real gateway state observed 2026-08-07: active=4g,
        wifi enabled but link down with no address. A preflight that excluded
        the active transport would wrongly refuse this switch.
        """
        client = _client_with_reads(MOCK_317_ON_4G, MOCK_339_EXTENDED_4G, MOCK_341_ALL_ON)
        state = await client.get_network_state()

        assert state["linked_transports"] == ["4g"]
        assert set(state["available_transports"]) - {"wifi"} >= {"4g"}  # WiFi write safe

    @pytest.mark.asyncio
    async def test_idle_cellular_is_available_even_though_not_linked(self):
        """The finding from the 2026-08-08 60-minute observation.

        On WiFi for a full hour with 4GNetSwitch=1 and operatorRSSI=21-22 but
        4GConnectBSStatus=0. Cellular was idle, not dead — it had carried the
        connection that same morning. Keying the preflight on `link` would have
        refused every WiFi write despite a ready fallback.
        """
        on_wifi_4g_idle = json.dumps({
            "opt": 0, "result": 0, "reason": 0,
            "routerStatus": 0, "netStatus": 0, "awsStatus": 0,
            "EthConnectRouterStatus": 0, "wifiConnectRouterStatus": 1,
            "4GConnectBSStatus": 0,              # idle
            "WifiSignalStrength": 78, "4GSignalStrength": 0,
            "currentNetType": 3,
        })
        client = _client_with_reads(MOCK_317_ON_WIFI, on_wifi_4g_idle, MOCK_341_ALL_ON)
        state = await client.get_network_state()

        assert state["linked_transports"] == ["wifi"]        # only WiFi carries traffic
        assert "4g" in state["available_transports"]         # but cellular can take over
        assert state["redundant"] is True

        # The preflight this exists to serve: a WiFi write is safe here.
        assert set(state["available_transports"]) - {"wifi"} >= {"4g"}

    @pytest.mark.asyncio
    async def test_no_fallback_when_wifi_is_the_only_enabled_transport(self):
        """This is the state in which a WiFi write could strand the gateway."""
        client = _client_with_reads(MOCK_317_ON_WIFI, MOCK_339_SHORT, MOCK_341_ONLY_WIFI)
        state = await client.get_network_state()

        assert state["available_transports"] == ["wifi"]
        assert state["redundant"] is False
        assert set(state["available_transports"]) - {"wifi"} == set()

    @pytest.mark.asyncio
    async def test_wifi_with_signal_but_no_lease_is_not_a_fallback(self):
        """The 2026-03-21 and 2026-08-08 failure mode, and the reason `available`
        is not simply `has signal`.

        WiFi associated at 76% while holding 0.0.0.0 is a candidate to switch TO
        (it appears in scan_wifi_networks_ranked), never a fallback to rely ON —
        there is no working path through it.
        """
        associated_no_lease = json.dumps({
            "opt": 0, "result": 0, "reason": 0,
            "routerStatus": 0, "netStatus": 0, "awsStatus": 0,
            "EthConnectRouterStatus": 0, "wifiConnectRouterStatus": 0,
            "4GConnectBSStatus": 1,
            "WifiSignalStrength": 76, "4GSignalStrength": 45,
            "currentNetType": 4,
        })
        client = _client_with_reads(MOCK_317_ON_4G, associated_no_lease, MOCK_341_ALL_ON)
        state = await client.get_network_state()

        wifi = next(i for i in state["interfaces"] if i["key"] == "wifi")
        assert wifi["signal_pct"] == 76      # in range
        assert wifi["ip"] is None            # but no address
        assert wifi["available"] is False
        assert "wifi" not in state["available_transports"]
        assert state["available_transports"] == ["4g"]

    @pytest.mark.asyncio
    async def test_cellular_with_inactive_sim_is_not_a_fallback(self):
        """Reception without an active SIM is not a usable lifeline."""
        client = _client_with_reads(MOCK_317_ON_WIFI, MOCK_339_SHORT,
                                    MOCK_341_ALL_ON, sim_status=SIM_INACTIVE)
        state = await client.get_network_state()

        cell = next(i for i in state["interfaces"] if i["key"] == "4g")
        assert cell["signal_raw"] == 22               # has reception
        assert cell["sim_status_name"] == "Installed (Inactive)"
        assert cell["available"] is False
        assert "4g" not in state["available_transports"]

    @pytest.mark.asyncio
    async def test_active_sim_with_reception_is_a_fallback(self):
        client = _client_with_reads(MOCK_317_ON_WIFI, MOCK_339_SHORT,
                                    MOCK_341_ALL_ON, sim_status=SIM_ACTIVE)
        state = await client.get_network_state()

        cell = next(i for i in state["interfaces"] if i["key"] == "4g")
        assert cell["sim_status_name"] == "Active"
        assert cell["available"] is True

    @pytest.mark.asyncio
    async def test_sim_lookup_failure_does_not_falsely_kill_the_lifeline(self):
        """If the REST call fails, fall back to signal alone rather than
        declaring 4G dead — that would refuse writes that are in fact safe."""
        client = _client_with_reads(MOCK_317_ON_WIFI, MOCK_339_SHORT,
                                    MOCK_341_ALL_ON, gateway_list_fails=True)
        state = await client.get_network_state()

        cell = next(i for i in state["interfaces"] if i["key"] == "4g")
        assert cell["sim_status"] is None
        assert cell["available"] is True           # signal alone carries it
        assert "4g" in state["available_transports"]

    @pytest.mark.asyncio
    async def test_mqtt_failure_still_propagates(self):
        """Only the SIM lookup is best-effort — the three MQTT reads are not."""
        from franklinwh_cloud.exceptions import GatewayOfflineException
        client = _client_with_reads(MOCK_317_ON_WIFI, MOCK_339_SHORT, MOCK_341_ALL_ON)
        client._mqtt_send = AsyncMock(side_effect=GatewayOfflineException("offline"))

        with pytest.raises(GatewayOfflineException):
            await client.get_network_state()

    @pytest.mark.asyncio
    async def test_disabled_transport_is_never_available(self):
        """A registered modem behind a switched-off interface is not a fallback."""
        client = _client_with_reads(MOCK_317_ON_WIFI, MOCK_339_SHORT, MOCK_341_ONLY_WIFI)
        state = await client.get_network_state()

        cell = next(i for i in state["interfaces"] if i["key"] == "4g")
        assert cell["signal_raw"] == 22        # modem has signal
        assert cell["enabled"] is False        # but the switch is off
        assert cell["available"] is False
        assert "4g" not in state["available_transports"]


# ── scan_wifi_networks_ranked ────────────────────────────────────────

class TestScanRanked:

    @pytest.mark.asyncio
    async def test_sorted_by_signal_descending(self):
        client = _client_with_scan(MOCK_335_COMPLETE)
        res = await client.scan_wifi_networks_ranked()

        pcts = [n["signal_pct"] for n in res["networks"]]
        assert pcts == sorted(pcts, reverse=True)

    @pytest.mark.asyncio
    async def test_duplicate_ssids_collapsed_keeping_strongest(self):
        """net_b appears 4x at 100/82/100/38 — one entry, at 100."""
        client = _client_with_scan(MOCK_335_COMPLETE)
        res = await client.scan_wifi_networks_ranked()

        b = [n for n in res["networks"] if n["ssid"] == "net_b"]
        assert len(b) == 1
        assert b[0]["signal_pct"] == 100
        assert b[0]["seen_count"] == 4
        assert any("collapsed" in w for w in res["warnings"])

    @pytest.mark.asyncio
    async def test_security_flag_mapped(self):
        client = _client_with_scan(MOCK_335_COMPLETE)
        res = await client.scan_wifi_networks_ranked()

        by_ssid = {n["ssid"]: n for n in res["networks"]}
        assert by_ssid["net_open"]["secured"] is False
        assert by_ssid["net_a"]["secured"] is True

    @pytest.mark.asyncio
    async def test_usable_threshold(self):
        client = _client_with_scan(MOCK_335_COMPLETE)
        res = await client.scan_wifi_networks_ranked(usable_rssi=30)

        by_ssid = {n["ssid"]: n for n in res["networks"]}
        assert by_ssid["net_e"]["signal_pct"] == 26
        assert by_ssid["net_e"]["usable"] is False
        assert by_ssid["net_a"]["usable"] is True

    @pytest.mark.asyncio
    async def test_min_rssi_filters(self):
        client = _client_with_scan(MOCK_335_COMPLETE)
        res = await client.scan_wifi_networks_ranked(min_rssi=65)

        assert all(n["signal_pct"] >= 65 for n in res["networks"])
        assert "net_e" not in [n["ssid"] for n in res["networks"]]

    @pytest.mark.asyncio
    async def test_signal_bars_bucketing(self):
        client = _client_with_scan(MOCK_335_COMPLETE)
        res = await client.scan_wifi_networks_ranked()

        by_ssid = {n["ssid"]: n for n in res["networks"]}
        assert by_ssid["net_b"]["signal_bars"] == 4     # 100
        assert by_ssid["net_a"]["signal_bars"] == 4     # 76
        assert by_ssid["net_c"]["signal_bars"] == 3     # 62
        assert by_ssid["net_e"]["signal_bars"] == 2     # 26

    @pytest.mark.asyncio
    async def test_polls_through_pending_then_returns_results(self):
        """First call returns result=1/reason=3 — the app sees this routinely."""
        client = _client_with_scan(MOCK_335_PENDING, MOCK_335_PENDING, MOCK_335_COMPLETE)
        res = await client.scan_wifi_networks_ranked(delay_s=0)

        assert len(res["networks"]) == 6
        assert client._mqtt_send.call_count == 3
        # Warnings are now either the dedup note or the 2.4 GHz band caveat,
        # which is emitted on every non-empty scan (Installation Guide p.59).
        assert all("collapsed" in w or "2.4 GHz" in w for w in res["warnings"])

    @pytest.mark.asyncio
    async def test_never_completing_scan_warns_and_returns_empty(self):
        client = _client_with_scan(*[MOCK_335_PENDING] * 3)
        res = await client.scan_wifi_networks_ranked(max_attempts=3, delay_s=0)

        assert res["networks"] == []
        assert any("did not complete" in w for w in res["warnings"])


class TestScanBandCaveat:
    """The aGate joins 2.4 GHz only, but scans both bands.

    FranklinWH System Installation Guide p.59, Method 2: "The aGate supports
    only 2.4Ghz Wi-Fi connection to the family router." cmdType 335 returns no
    band field, so a 5 GHz-only SSID cannot be filtered out — it is returned at
    full signal, is writable, and simply never associates. Afterwards it is
    indistinguishable from a wrong password, because neither surfaces an error.

    The scan cannot prevent this, so it must at least say so.
    """

    async def test_scan_warns_about_the_band_limit(self):
        client = _client_with_scan(MOCK_335_COMPLETE)
        res = await client.scan_wifi_networks_ranked(delay_s=0)

        band = [w for w in res["warnings"] if "2.4 GHz" in w]
        assert band, "every scan must carry the band caveat"
        assert "cannot be filtered" in band[0]

    async def test_no_band_warning_when_nothing_was_found(self):
        """Nothing to mislead the reader about."""
        client = _client_with_scan(MOCK_335_PENDING)
        res = await client.scan_wifi_networks_ranked(delay_s=0, max_attempts=1)

        assert res["networks"] == []
        assert not [w for w in res["warnings"] if "2.4 GHz" in w]

    def test_the_timeout_hint_names_the_band_trap(self):
        """A 5 GHz target is a leading cause of an unexplained verify timeout."""
        import inspect

        from franklinwh_cloud.mixins import network

        src = inspect.getsource(network.NetworkMixin._verify_wifi_switch)
        assert "5 GHz" in src
