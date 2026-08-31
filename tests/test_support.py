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
    _collect_keys,
    compute_schema_fingerprint,
)


# ── Redaction tests ──────────────────────────────────────────────────

class TestRedactEmail:
    def test_partial(self):
        assert _redact_email("dave@example.com", "partial") == "d***@e***.com"

    def test_full(self):
        assert _redact_email("dave@example.com", "full") == "[REDACTED]"

    def test_empty(self):
        assert _redact_email("", "partial") == ""

    def test_no_at(self):
        assert _redact_email("noemail", "partial") == "noemail"


class TestRedactSerial:
    def test_partial(self):
        assert _redact_serial("10060006AXXXXXXXXX", "partial") == "1006***XXXX"

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
                "email": "dave@example.com",
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
        assert result["identity"]["serial"] == "1006***XXXX"
        assert result["identity"]["email"] == "d***@e***.com"
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
        """currentNetType 4 (cellular) with WiFi configured should warn.

        Was written as currentNetType=5. That is a bitmask value from the old
        NET_TYPES table and cannot occur: currentNetType is positional with the
        domain 1-4 (const.devices.NETWORK_TYPES; the HAR corpus shows 2, 3 and
        4). The fixture was encoding the defect, so it asserted behaviour for a
        value the gateway never emits. DEF-SUPPORT-NETTYPE-ENUM.
        """
        snapshot = {
            "connectivity": {"routerStatus": 1, "netStatus": 1, "awsStatus": 1},
            "network": {
                "currentNetType": 4,
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

    def test_aws_disconnected_no_api(self):
        """AWS disconnected with no other data should be critical."""
        snapshot = {
            "connectivity": {"routerStatus": 1, "netStatus": 1, "awsStatus": 0},
            "network": {},
            "wifi_config": {},
            "switches": {},
        }
        findings = analyze_connectivity(snapshot)
        aws = [f for f in findings if f["check"] == "AWS Cloud"]
        assert aws[0]["severity"] == "critical"

    def test_all_zero_but_api_reachable(self):
        """All-zero connection status with working API should be single warning, not 3 criticals."""
        snapshot = {
            "connectivity": {"routerStatus": 0, "netStatus": 0, "awsStatus": 0},
            "versions": {"ibgVersion": "V12R02B85D00"},
            "network": {},
            "wifi_config": {},
            "switches": {},
        }
        findings = analyze_connectivity(snapshot)
        criticals = [f for f in findings if f["severity"] == "critical"]
        warnings = [f for f in findings if f["severity"] == "warning" and "stale" in f.get("detail", "")]
        assert len(criticals) == 0
        assert len(warnings) == 1

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


# ── Schema fingerprint tests ────────────────────────────────────────

class TestSchemaFingerprint:
    def test_collect_keys_flat(self):
        obj = {"a": 1, "b": 2}
        keys = _collect_keys(obj)
        assert keys == ["a", "b"]

    def test_collect_keys_nested(self):
        obj = {"wifi": {"mac": "AA", "ip": "10.0.0.1"}}
        keys = _collect_keys(obj, "network")
        assert "network.wifi" in keys
        assert "network.wifi.ip" in keys
        assert "network.wifi.mac" in keys

    def test_collect_keys_list(self):
        obj = {"items": [{"id": 1, "name": "a"}]}
        keys = _collect_keys(obj)
        assert "items" in keys
        assert "items[].id" in keys
        assert "items[].name" in keys

    def test_fingerprint_deterministic(self):
        snap = {"versions": {"ibgVersion": "V1"}, "network": {"wifi": {"ip": "10.0.0.1"}}}
        fp1 = compute_schema_fingerprint(snap)
        fp2 = compute_schema_fingerprint(snap)
        assert fp1["fingerprint"] == fp2["fingerprint"]
        assert fp1["key_count"] == fp2["key_count"]

    def test_fingerprint_changes_on_new_key(self):
        snap1 = {"versions": {"ibgVersion": "V1"}}
        snap2 = {"versions": {"ibgVersion": "V1", "newField": "x"}}
        fp1 = compute_schema_fingerprint(snap1)
        fp2 = compute_schema_fingerprint(snap2)
        assert fp1["fingerprint"] != fp2["fingerprint"]
        assert fp2["key_count"] > fp1["key_count"]

    def test_fingerprint_ignores_values(self):
        """Same keys, different values = same fingerprint."""
        snap1 = {"versions": {"ibgVersion": "V1"}}
        snap2 = {"versions": {"ibgVersion": "V999"}}
        fp1 = compute_schema_fingerprint(snap1)
        fp2 = compute_schema_fingerprint(snap2)
        assert fp1["fingerprint"] == fp2["fingerprint"]

    def test_fingerprint_skips_error_sections(self):
        snap = {"versions": {"ibgVersion": "V1"}, "network": {"error": "timeout"}}
        fp = compute_schema_fingerprint(snap)
        # Should not include network keys since it has an error
        assert not any("network" in k for k in fp["keys"])


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


class TestSupportNetworkEnum:
    """DEF-SUPPORT-NETTYPE-ENUM — currentNetType must use the positional map.

    support.py held its own bitmask-style table indexed with currentNetType,
    the same defect already fixed in diag. All three call sites read
    currentNetType; the variable and key names saying "connType" are a misnomer
    and are what disguised it.
    """

    def test_ethernet_is_not_labelled_wifi(self):
        from franklinwh_cloud.cli_commands.support import NET_TYPES

        assert NET_TYPES.get(1) == "Ethernet (eth0)"

    def test_wifi_is_labelled_wifi(self):
        from franklinwh_cloud.cli_commands.support import NET_TYPES

        assert NET_TYPES.get(3) == "WiFi"

    def test_the_bitmask_table_is_gone(self):
        from franklinwh_cloud.cli_commands.support import NET_TYPES

        assert 5 not in NET_TYPES, "bitmask values cannot occur for currentNetType"
        assert 13 not in NET_TYPES
        assert 0 not in NET_TYPES, "0 was 'None'; the domain starts at 1"

    def test_support_shares_the_canonical_table(self):
        from franklinwh_cloud.cli_commands.support import NET_TYPES
        from franklinwh_cloud.const.devices import NETWORK_TYPES

        assert NET_TYPES is NETWORK_TYPES, "no local copy to drift again"

    def test_an_impossible_value_does_not_raise_a_4g_warning(self):
        """5 was a dead branch — it can never be emitted."""
        from franklinwh_cloud.cli_commands.support import analyze_connectivity

        snapshot = {
            "connectivity": {"routerStatus": 1, "netStatus": 1, "awsStatus": 1},
            "network": {
                "currentNetType": 5,
                "wifi": {"mac": "AA:BB:CC:DD:EE:01", "ip": "0.0.0.0"},
                "eth0": {"mac": "", "ip": ""}, "eth1": {"mac": "", "ip": ""},
                "operator": {"mac": "AA:BB:CC:DD:EE:02", "rssi": 21},
            },
            "wifi_config": {}, "switches": {},
        }
        findings = analyze_connectivity(snapshot)
        assert [f for f in findings if f["check"] == "4G Fallback"] == []


class TestConnTypeEncoding:
    """DEF-CONNTYPE-ENCODING-WRONG — connType shares the currentNetType encoding.

    A long-standing annotation on models.py claimed runtimeData.connType used
    0=4G, 1=WiFi, 2=Ethernet, and const/devices.py warned that the two
    encodings were incompatible. Neither claim was ever sourced.

    The HAR corpus contradicts both. Across **20,471 runtimeData samples**,
    connType is observed only as::

        {2: 559, 3: 19797, 4: 115}

    Values 0 and 1 never occur. Under the claimed encoding, 97% of samples
    would be undefined and a gateway that lives on WiFi would report 1 — it
    never does. Under NETWORK_TYPES (1=Eth0, 2=Eth1, 3=WiFi, 4=4G) the
    distribution is exactly what the roaming behaviour in
    NETWORK_CONNECTIVITY_DESIGN.md section 2.3a describes: mostly WiFi,
    sometimes Ethernet, occasionally cellular.

    I acted on the unsourced comment and changed status.py to a new map,
    which turned "WiFi" into "Unknown (3)" on every healthy gateway. These
    tests exist so the claim cannot be reintroduced from the comment again.
    """

    def test_observed_conn_type_values_are_covered_by_network_types(self):
        from franklinwh_cloud.const.devices import NETWORK_TYPES

        for observed in (2, 3, 4):
            assert observed in NETWORK_TYPES, \
                f"connType={observed} occurs on the wire and must have a label"

    def test_the_dominant_observed_value_is_wifi(self):
        """3 is 19,797 of 20,471 samples, on a gateway that lives on WiFi."""
        from franklinwh_cloud.const.devices import NETWORK_TYPES

        assert NETWORK_TYPES[3] == "WiFi"

    def test_the_disproven_map_is_gone(self):
        """CONN_TYPE_NAMES was added on a false premise and removed."""
        from franklinwh_cloud.const import devices

        assert not hasattr(devices, "CONN_TYPE_NAMES")

    def test_status_renders_conn_type_through_network_types(self):
        import inspect

        from franklinwh_cloud.cli_commands import status

        src = inspect.getsource(status)
        assert "NETWORK_TYPES.get(conn_type" in src
        assert "CONN_TYPE_NAMES" not in src

    def test_unknown_values_are_still_reported_as_unknown(self):
        """The 1=Ethernet 1 slot is never observed, but must not be fabricated."""
        from franklinwh_cloud.const.devices import NETWORK_TYPES

        assert NETWORK_TYPES.get(0) is None
        assert NETWORK_TYPES.get(99) is None
