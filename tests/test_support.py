"""Tests for the support command — redaction, connectivity analysis, and snapshot comparison."""

import pytest

from franklinwh_cloud.cli_commands.support import (
    _redact_email,
    _redact_serial,
    _redact_ip,
    _redact_mac,
    _redact_ssid,
    redact_snapshot,
    sign_snapshot,
    analyze_connectivity,
    compare_snapshots,
)


# ── Redaction tests ──────────────────────────────────────────────────

class TestRedactEmail:
    def test_partial(self):
        assert _redact_email("[REDACTED]@gmail.com", "partial") == "d***@g***.com"

    def test_full(self):
        assert _redact_email("[REDACTED]@gmail.com", "full") == "[REDACTED]"

    def test_empty(self):
        assert _redact_email("", "partial") == ""

    def test_no_at(self):
        assert _redact_email("noemail", "partial") == "noemail"


class TestRedactSerial:
    def test_partial(self):
        assert _redact_serial("10060006AXXXXXXXXX", "partial") == "1006***0091"

    def test_full(self):
        assert _redact_serial("10060006AXXXXXXXXX", "full") == "[REDACTED]"

    def test_short(self):
        assert _redact_serial("ABC", "partial") == "ABC"

    def test_empty(self):
        assert _redact_serial("", "partial") == ""


class TestRedactIP:
    def test_partial(self):
        assert _redact_ip("192.168.0.110", "partial") == "192.168.0.XXX"

    def test_full(self):
        assert _redact_ip("192.168.0.110", "full") == "[REDACTED]"

    def test_zero_ip_kept(self):
        assert _redact_ip("0.0.0.0", "partial") == "0.0.0.0"

    def test_empty(self):
        assert _redact_ip("", "partial") == ""


class TestRedactMAC:
    def test_partial(self):
        assert _redact_mac("4C:24:CE:67:3A:7C", "partial") == "4C:24:CE:XX:XX:XX"

    def test_full(self):
        assert _redact_mac("4C:24:CE:67:3A:7C", "full") == "[REDACTED]"

    def test_empty(self):
        assert _redact_mac("", "partial") == ""


class TestRedactSSID:
    def test_partial_keeps_ssid(self):
        assert _redact_ssid("do_not_trespass", "partial") == "do_not_trespass"

    def test_full(self):
        assert _redact_ssid("do_not_trespass", "full") == "[REDACTED]"


class TestRedactSnapshot:
    def test_partial_redacts_identity(self):
        data = {
            "identity": {
                "serial": "10060006AXXXXXXXXX",
                "email": "[REDACTED]@gmail.com",
            },
            "network": {
                "wifi": {"mac": "4C:24:CE:67:3A:7C", "ip": "192.168.0.110"},
            },
            "wifi_config": {
                "wifi_ssid": "mynet",
                "wifi_password": "secret123",
                "ap_ssid": "FranklinWH_AP",
                "ap_password": "ap_pass",
            },
        }
        result = redact_snapshot(data, "partial")
        assert result["identity"]["serial"] == "1006***0091"
        assert result["identity"]["email"] == "d***@g***.com"
        assert result["network"]["wifi"]["mac"] == "4C:24:CE:XX:XX:XX"
        assert result["network"]["wifi"]["ip"] == "192.168.0.XXX"
        assert result["wifi_config"]["wifi_password"] == "***"
        assert result["wifi_config"]["ap_password"] == "***"
        assert result["wifi_config"]["wifi_ssid"] == "mynet"  # kept in partial
        assert result["_redacted"] == "partial"

    def test_full_redacts_everything(self):
        data = {
            "identity": {"serial": "10060006AXXXXXXXXX", "email": "a@b.com"},
            "network": {"wifi": {"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.0.0.1"}},
            "wifi_config": {"wifi_ssid": "net", "wifi_password": "pw"},
        }
        result = redact_snapshot(data, "full")
        assert result["identity"]["serial"] == "[REDACTED]"
        assert result["identity"]["email"] == "[REDACTED]"
        assert result["network"]["wifi"]["mac"] == "[REDACTED]"
        assert result["network"]["wifi"]["ip"] == "[REDACTED]"
        assert result["wifi_config"]["wifi_ssid"] == "[REDACTED]"
        assert result["_redacted"] == "full"

    def test_does_not_mutate_original(self):
        data = {"identity": {"serial": "10060006AXXXXXXXXX"}}
        redact_snapshot(data, "partial")
        assert data["identity"]["serial"] == "10060006AXXXXXXXXX"


# ── Signing tests ────────────────────────────────────────────────────

class TestSignSnapshot:
    def test_deterministic(self):
        data = {"versions": {"ibgVersion": "V12R02B85D00"}}
        assert sign_snapshot(data) == sign_snapshot(data)

    def test_different_data_different_hash(self):
        a = {"versions": {"ibgVersion": "V12R02B85D00"}}
        b = {"versions": {"ibgVersion": "V12R02B84D00"}}
        assert sign_snapshot(a) != sign_snapshot(b)

    def test_returns_hex_string(self):
        result = sign_snapshot({"test": True})
        assert len(result) == 64  # SHA-256 hex
        assert all(c in "0123456789abcdef" for c in result)


# ── Connectivity analysis tests ──────────────────────────────────────

class TestAnalyzeConnectivity:
    def test_healthy_system(self):
        snapshot = {
            "connectivity": {"routerStatus": 1, "netStatus": 1, "awsStatus": 1},
            "network": {
                "currentNetType": 3,
                "wifi": {"mac": "4C:24:CE:67:3A:7C", "ip": "192.168.0.110", "dhcp": True},
                "eth0": {"mac": "88:C9:B3:20:00:80", "ip": "10.0.0.5"},
                "eth1": {"mac": "", "ip": ""},
                "operator": {"mac": "3A:24:91:B4:CA:64", "rssi": 21},
            },
            "wifi_config": {},
            "switches": {"wifiNetSwitch": 1, "ethernet0NetSwitch": 1, "ethernet1NetSwitch": 1, "4GNetSwitch": 1},
        }
        findings = analyze_connectivity(snapshot)
        criticals = [f for f in findings if f["severity"] == "critical"]
        assert len(criticals) == 0

    def test_wifi_dhcp_failure(self):
        """WiFi MAC present but IP 0.0.0.0 should be CRITICAL."""
        snapshot = {
            "connectivity": {"routerStatus": 0, "netStatus": 0, "awsStatus": 0},
            "network": {
                "currentNetType": 4,
                "wifi": {"mac": "4C:24:CE:67:3A:7C", "ip": "0.0.0.0", "dhcp": True},
                "eth0": {"mac": "", "ip": ""},
                "eth1": {"mac": "", "ip": ""},
                "operator": {"mac": "3A:24:91:B4:CA:64", "rssi": -65},
            },
            "wifi_config": {},
            "switches": {},
        }
        findings = analyze_connectivity(snapshot)
        wifi_dhcp = [f for f in findings if f["check"] == "WiFi DHCP"]
        assert len(wifi_dhcp) == 1
        assert wifi_dhcp[0]["severity"] == "critical"
        assert "0.0.0.0" in wifi_dhcp[0]["detail"]

    def test_4g_fallback_warning(self):
        """connType 4/5/6/13 with WiFi configured should warn."""
        snapshot = {
            "connectivity": {"routerStatus": 1, "netStatus": 1, "awsStatus": 1},
            "network": {
                "currentNetType": 5,
                "wifi": {"mac": "4C:24:CE:67:3A:7C", "ip": "0.0.0.0"},
                "eth0": {"mac": "", "ip": ""},
                "eth1": {"mac": "", "ip": ""},
                "operator": {"mac": "3A:24:91:B4:CA:64", "rssi": 21},
            },
            "wifi_config": {},
            "switches": {},
        }
        findings = analyze_connectivity(snapshot)
        fallback = [f for f in findings if f["check"] == "4G Fallback"]
        assert len(fallback) == 1
        assert fallback[0]["severity"] == "warning"

    def test_aws_disconnected(self):
        snapshot = {
            "connectivity": {"routerStatus": 1, "netStatus": 1, "awsStatus": 0},
            "network": {},
            "wifi_config": {},
            "switches": {},
        }
        findings = analyze_connectivity(snapshot)
        aws = [f for f in findings if f["check"] == "AWS Cloud"]
        assert aws[0]["severity"] == "critical"

    def test_interface_disabled_warning(self):
        snapshot = {
            "connectivity": {},
            "network": {},
            "wifi_config": {},
            "switches": {"wifiNetSwitch": 0, "ethernet0NetSwitch": 1, "4GNetSwitch": 1},
        }
        findings = analyze_connectivity(snapshot)
        disabled = [f for f in findings if "DISABLED" in f.get("detail", "")]
        assert len(disabled) == 1
        assert disabled[0]["check"] == "WiFi Switch"


# ── Snapshot comparison tests ────────────────────────────────────────

class TestCompareSnapshots:
    def test_no_changes(self):
        data = {"data": {"versions": {"ibgVersion": "V12R02B85D00"}}}
        assert compare_snapshots(data, data) == []

    def test_version_change_detected(self):
        old = {"data": {"versions": {"ibgVersion": "V12R02B84D00", "protocolVer": "V1.11.01"}}}
        new = {"data": {"versions": {"ibgVersion": "V12R02B85D00", "protocolVer": "V1.11.01"}}}
        changes = compare_snapshots(old, new, scope="software")
        assert len(changes) == 1
        assert changes[0]["key"] == "ibgVersion"
        assert changes[0]["old"] == "V12R02B84D00"
        assert changes[0]["new"] == "V12R02B85D00"

    def test_network_scope(self):
        old = {"data": {"versions": {"ibgVersion": "V1"}, "network": {"currentNetType": 1}}}
        new = {"data": {"versions": {"ibgVersion": "V2"}, "network": {"currentNetType": 3}}}
        changes = compare_snapshots(old, new, scope="network")
        # Should only have network changes, not version changes
        assert all(c["section"] in ("network", "connectivity", "wifi_config", "switches") for c in changes)
        assert len(changes) == 1
        assert changes[0]["key"] == "currentNetType"

    def test_nested_dict_diff(self):
        old = {"data": {"network": {"wifi": {"ip": "192.168.0.100", "mac": "AA:BB:CC:DD:EE:FF"}}}}
        new = {"data": {"network": {"wifi": {"ip": "192.168.0.110", "mac": "AA:BB:CC:DD:EE:FF"}}}}
        changes = compare_snapshots(old, new, scope="network")
        assert len(changes) == 1
        assert changes[0]["key"] == "wifi.ip"
        assert changes[0]["old"] == "192.168.0.100"
        assert changes[0]["new"] == "192.168.0.110"

    def test_all_scope_catches_everything(self):
        old = {"data": {"versions": {"ibgVersion": "V1"}, "power": {"solar_kw": 1.0}}}
        new = {"data": {"versions": {"ibgVersion": "V2"}, "power": {"solar_kw": 2.0}}}
        changes = compare_snapshots(old, new, scope="all")
        assert len(changes) == 2
