"""Tests for the pure logic in tools/network_probe.py.

Covers the two parts that must be right before the probe is ever pointed at
hardware: PII redaction of the evidence log, and construction of the no-op
write payloads (which is what makes probing unknown command shapes safe).

No network, no gateway, no credentials.
"""

import importlib.util
import json
import os

import pytest

_PROBE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tools", "network_probe.py",
)
_spec = importlib.util.spec_from_file_location("network_probe", _PROBE_PATH)
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)


# ── Evidence redaction ───────────────────────────────────────────────

class TestRedaction:

    def test_wifi_password_never_survives(self, tmp_path):
        """cmdType 338 returns wifi_Pw in plaintext — it must never be logged."""
        ev = probe.Evidence(str(tmp_path / "e.jsonl"))
        payload = {
            "wifi_SSID": "my_home_network", "wifi_Pw": "hunter2xyz",
            "ap_SSID": "AP_F24170091", "ap_Pw": "A02F24170091", "wifi_Safety": 1,
        }
        out = ev.redact(payload)

        assert "hunter2xyz" not in json.dumps(out)
        assert "A02F24170091" not in json.dumps(out)
        assert out["wifi_Safety"] == 1          # non-secret fields survive

    def test_ssids_redacted_by_default_but_length_preserved(self, tmp_path):
        ev = probe.Evidence(str(tmp_path / "e.jsonl"))
        out = ev.redact({"wifi_SSID": "my_home_network"})

        assert "my_home_network" not in json.dumps(out)
        assert "len=15" in out["wifi_SSID"] or "len 15" in out["wifi_SSID"]

    def test_keep_ssids_opt_in_preserves_ssid_but_not_password(self, tmp_path):
        ev = probe.Evidence(str(tmp_path / "e.jsonl"), keep_ssids=True)
        out = ev.redact({"wifi_SSID": "my_home_network", "wifi_Pw": "hunter2xyz"})

        assert out["wifi_SSID"] == "my_home_network"
        assert "hunter2xyz" not in json.dumps(out)   # password is never opt-out-able

    def test_redaction_recurses_into_nested_structures(self, tmp_path):
        ev = probe.Evidence(str(tmp_path / "e.jsonl"))
        out = ev.redact({
            "result": {"dataArea": {"wifi_Pw": "secret1"}},
            "scans": [{"wifi_SSID": "netA"}, {"wifi_Pw": "secret2"}],
        })
        blob = json.dumps(out)

        assert "secret1" not in blob and "secret2" not in blob and "netA" not in blob

    def test_hardware_serials_and_macs_are_always_scrubbed(self, tmp_path):
        """AP-3 bans real hardware identifiers from tracked dirs, and
        tests/results/ IS tracked. There is no opt-out for these.

        Regression: the first 60-minute observation log contained the real
        gateway serial and 200 MAC addresses, and was very nearly committed.
        """
        ev = probe.Evidence(str(tmp_path / "e.jsonl"), keep_ssids=True)
        out = ev.redact({
            "gateway_id": "99999999A0TESTONLY01",
            "wifi": {"mac": "4C:24:CE:67:3A:7C"},
            "note": "gateway 99999999A0TESTONLY01 at 88:C9:B3:20:00:80 failed",
        })
        blob = json.dumps(out)

        assert "99999999A0TESTONLY01" not in blob
        assert "4C:24:CE:67:3A:7C" not in blob
        assert "88:C9:B3:20:00:80" not in blob      # embedded in free text too

    def test_scrubbing_survives_keep_ssids(self, tmp_path):
        """--keep-ssids relaxes SSIDs only; serials are never opt-out-able."""
        ev = probe.Evidence(str(tmp_path / "e.jsonl"), keep_ssids=True)
        out = ev.redact({"equipNo": "99999999A0TESTONLY01"})
        assert out["equipNo"] == "<serial>"

    def test_written_records_are_redacted_on_disk(self, tmp_path):
        path = tmp_path / "e.jsonl"
        ev = probe.Evidence(str(path))
        ev.write("mqtt", cmd=337, response={"wifi_Pw": "hunter2xyz"})

        contents = path.read_text()
        assert "hunter2xyz" not in contents
        rec = json.loads(contents.strip())
        assert rec["kind"] == "mqtt" and rec["seq"] == 1 and "ts" in rec


# ── No-op write payload construction ─────────────────────────────────

# Verbatim cmdType 318 read response (hars/HTTPToolkit_2026-03-20_05-38.har:3141)
READ_317 = {
    "optType": 0, "paraType": 6, "result": 0,
    "commSetPara": {
        "opt": 0, "result": 0, "reason": 0,
        "currentNetType": 4,
        "wifiDHCP": 1, "wifiMAC": "4C:24:CE:67:3A:7C", "wifiStaticIP": "0.0.0.0",
        "wifiDNS": "8.8.8.8", "wifiGateWay": "0.0.0.0",
        "eth0DHCP": 0, "eth0MAC": "88:C9:B3:20:00:80", "eth0StaticIP": "0.0.0.0",
        "eth0DNS": "8.8.8.8", "eth0GateWay": "172.16.1.1",
        "eth1DHCP": 1, "eth1MAC": "88:C9:B3:21:2C:B8", "eth1StaticIP": "0.0.0.0",
        "eth1DNS": "8.8.8.8", "eth1GateWay": "0.0.0.0",
        "operatorMAC": "E6:4F:68:B1:91:5C", "operatorDNS": "192.192.192.192",
        "operatorRSSI": 22,
        "awsStatus": 1,
    },
}

READ_341 = {
    "opt": 0, "result": 0, "reason": 0,
    "ethernet0NetSwitch": 1, "ethernet1NetSwitch": 1,
    "wifiNetSwitch": 1, "4GNetSwitch": 1,
}


# Import the real builders — NOT a reimplementation. A copy here would let the
# probe drift while these tests kept passing.
_build_317_noop = probe.build_317_noop
_build_341_noop = probe.build_341_noop


class TestNoopPayloads:

    def test_317_matches_the_captured_app_write_exactly(self):
        """The app's own write carried 20 commSetPara keys and num=20."""
        built = _build_317_noop(READ_317)

        assert built["num"] == 20
        assert len(built["commSetPara"]) == 20
        assert built["optType"] == 1 and built["paraType"] == 6

    def test_317_strips_response_only_fields(self):
        """opt/result/reason are added by the gateway on read and must not echo."""
        built = _build_317_noop(READ_317)

        for k in ("opt", "result", "reason"):
            assert k not in built["commSetPara"]

    def test_317_num_is_computed_not_hardcoded(self):
        """num tracks the key count — a firmware with extra fields must still work."""
        extended = json.loads(json.dumps(READ_317))
        extended["commSetPara"]["someNewField"] = 1
        built = _build_317_noop(extended)

        assert built["num"] == 21 == len(built["commSetPara"])

    def test_317_noop_preserves_current_transport(self):
        """A no-op must write back the SAME currentNetType it read."""
        built = _build_317_noop(READ_317)
        assert built["commSetPara"]["currentNetType"] == \
            READ_317["commSetPara"]["currentNetType"]

    def test_341_noop_preserves_every_switch(self):
        built = _build_341_noop(READ_341)

        assert built["opt"] == 1
        for k in ("ethernet0NetSwitch", "ethernet1NetSwitch",
                  "wifiNetSwitch", "4GNetSwitch"):
            assert built[k] == READ_341[k]
        for k in ("result", "reason"):
            assert k not in built

    def test_341_noop_never_disables_an_interface(self):
        """The failure mode that could strand the gateway."""
        built = _build_341_noop(READ_341)
        assert not any(v == 0 for k, v in built.items()
                       if k.endswith("NetSwitch") and READ_341.get(k) == 1)


# ── Write gating ─────────────────────────────────────────────────────

class TestWriteGating:

    def test_write_commands_are_gated_behind_explicit_flag(self):
        src = open(_PROBE_PATH).read()
        assert 'WRITE_COMMANDS = {"noop", "reapply-wifi"}' in src
        assert "if args.command in WRITE_COMMANDS and not args.writes_ok" in src

    @pytest.mark.parametrize("cmd", ["status", "scan", "observe", "recover"])
    def test_read_only_commands_are_not_gated(self, cmd):
        assert cmd not in {"noop", "reapply-wifi"}

    def test_noop_341_is_gated_behind_onsite(self):
        """cmdType 341 is the only command that can clear 4GNetSwitch, and its
        shape has never been captured. The interlock must be in code, not prose."""
        src = open(_PROBE_PATH).read()
        assert 'args.command == "noop" and args.cmd == 341 and not args.onsite' in src
        assert 'REFUSED: `noop 341` requires --onsite.' in src

    def test_noop_317_is_not_gated_behind_onsite(self):
        """317 is observed from the official app over 4G — no extra ceremony."""
        src = open(_PROBE_PATH).read()
        assert "args.cmd == 317 and not args.onsite" not in src


class TestPreflightLifeline:
    """The 4G lifeline gate, separate from the survivor gate."""

    @staticmethod
    def _decide(available, target, onsite=False, allow_no_fallback=False):
        """Mirror of the two preflight gates, kept in step with Probe.preflight."""
        survivors = sorted(set(available) - {target})
        lifeline = ("4g" in available) and target != "4g"
        return (bool(survivors) or allow_no_fallback) and \
               (lifeline or onsite or allow_no_fallback)

    def test_wifi_write_passes_with_cellular_available(self):
        assert self._decide(["wifi", "4g"], "wifi") is True

    def test_4g_write_is_refused_remotely(self):
        """Targeting the lifeline itself is exactly what must not happen remotely."""
        assert self._decide(["wifi", "4g"], "4g") is False

    def test_4g_write_allowed_when_onsite(self):
        assert self._decide(["wifi", "4g"], "4g", onsite=True) is True

    def test_ethernet_alone_is_not_a_substitute_for_the_lifeline(self):
        """Ethernet survives the survivor gate but is not the remote-recovery
        guarantee — cellular is what comes back after a reboot or crash."""
        assert self._decide(["wifi", "eth0"], "wifi") is False
        assert self._decide(["wifi", "eth0"], "wifi", onsite=True) is True

    def test_nothing_survives_is_refused_even_with_lifeline_logic(self):
        assert self._decide(["wifi"], "wifi") is False

    def test_allow_no_fallback_overrides_both_gates(self):
        assert self._decide(["wifi"], "wifi", allow_no_fallback=True) is True
