"""Tests for the `fwh network` CLI (step P2-6).

No hardware, no live cloud. The client is a stand-in; these cover argument
wiring, exit codes, password handling and the refusal paths.
"""

import argparse
import json

import pytest

from franklinwh_cloud.cli_commands import network as netcmd


# ── fixtures ─────────────────────────────────────────────────────────

STATE = {
    "gateway_id": "agate-test",
    "active": {"id": 4, "key": "4g", "label": "4G Mobile", "ip": None,
               "gateway": None, "dns": None, "selection": "device-managed"},
    "interfaces": [
        {"id": 3, "key": "wifi", "label": "WiFi", "enabled": True, "link": False,
         "ip": None, "signal_pct": 76, "is_active": False, "available": False},
        {"id": 4, "key": "4g", "label": "4G Mobile", "enabled": True, "link": True,
         "ip": None, "signal_raw": 22, "is_active": True, "available": True},
    ],
    "cloud": {"aws_connected": True, "internet": True, "router_status_raw": 4},
    "linked_transports": ["4g"],
    "available_transports": ["4g"],
    "redundant": False,
    "source": {"cmds": [317, 339, 341], "extended_339": True},
}

SWITCH_OK = {
    "requested": {"ssid": "home-net", "password_source": "stored"},
    "preflight": {"passed": True, "target": "wifi", "fallback": "4g",
                  "fallbacks": ["4g"], "target_signal_pct": 88,
                  "reasons": [], "overrides": []},
    "write_ack": {"cmd": 338, "result": 0, "reason": 0, "accepted": True},
    "verification": {"state": "connected", "elapsed_s": 13.4, "polls": 3,
                     "unreachable_polls": 0, "before": {}, "cloud": {},
                     "after": {"type_id": 3, "type": "wifi",
                               "ip": "192.168.0.110"}},
}


class _CliClient:
    def __init__(self, switch_result=None, state=STATE):
        self._state = state
        self._switch_result = switch_result or SWITCH_OK
        self.switch_calls = []

    def _invalidate_network_cache(self):
        pass

    async def get_network_state(self, probe_local=False):
        # Mirrors the real signature; the local probe is opt-in I/O.
        return self._state

    async def scan_wifi_networks_ranked(self, **kw):
        return {"scan_seconds": 10, "warnings": ["1 duplicate SSID collapsed"],
                "networks": [
                    {"ssid": "home-net", "signal_pct": 88, "signal_bars": 4,
                     "secured": True, "seen_count": 2, "usable": True},
                    {"ssid": "far-net", "signal_pct": 12, "signal_bars": 1,
                     "secured": False, "seen_count": 1, "usable": False},
                ]}

    async def switch_to_wifi(self, ssid, password, **kw):
        self.switch_calls.append({"ssid": ssid, "password": password, **kw})
        return self._switch_result


def _args(**kw):
    base = dict(json=False, network_action="status", watch=None,
                min_rssi=30, scan_time=10, all=False,
                ssid="home-net", password=None, use_stored=True, yes=True,
                no_verify=False, timeout=180, allow_no_fallback=False,
                allow_weak_signal=False)
    base.update(kw)
    return argparse.Namespace(**base)


# ── parser wiring ────────────────────────────────────────────────────

def test_network_is_registered_on_the_real_cli():
    """P2-6 wiring — reachable as `fwh network` and `fwh net`."""
    from franklinwh_cloud.cli import build_parser

    parser = build_parser()
    assert parser.parse_args(["network", "status"]).command == "network"
    assert parser.parse_args(["net", "scan"]).command == "net"
    ns = parser.parse_args(["network", "set-wifi", "--ssid", "x", "--use-stored"])
    assert ns.use_stored is True


def test_register_builds_the_three_subcommands():
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="command")
    netcmd.register(subs)

    for action, extra in (("status", []), ("scan", []),
                          ("set-wifi", ["--ssid", "x"])):
        ns = parser.parse_args(["network", action] + extra)
        assert ns.network_action == action


def test_set_wifi_requires_an_ssid():
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="command")
    netcmd.register(subs)
    with pytest.raises(SystemExit):
        parser.parse_args(["network", "set-wifi"])


def test_password_and_use_stored_are_mutually_exclusive():
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="command")
    netcmd.register(subs)
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["network", "set-wifi", "--ssid", "x", "--password", "p", "--use-stored"]
        )


def test_net_alias_resolves():
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="command")
    netcmd.register(subs)
    assert parser.parse_args(["net", "status"]).network_action == "status"


# ── status ───────────────────────────────────────────────────────────

async def test_status_json_emits_the_state_contract(capsys):
    code = await netcmd.run(_CliClient(), _args(json=True))
    assert code == netcmd.EXIT_OK
    assert json.loads(capsys.readouterr().out)["gateway_id"] == "agate-test"


async def test_status_never_calls_the_active_transport_configured(capsys):
    """G9 — the gateway selects for itself; UI copy must not imply otherwise."""
    await netcmd.run(_CliClient(), _args())
    out = capsys.readouterr().out
    assert "selected by the gateway" in out
    assert "Configured primary" not in out


async def test_status_warns_when_there_is_no_fallback(capsys):
    await netcmd.run(_CliClient(), _args())
    assert "No fallback" in capsys.readouterr().out


async def test_status_reports_a_fallback_when_one_exists(capsys):
    state = {**STATE, "available_transports": ["4g", "wifi"]}
    await netcmd.run(_CliClient(state=state), _args())
    assert "Fallback available" in capsys.readouterr().out


# ── scan ─────────────────────────────────────────────────────────────

async def test_scan_json_emits_the_scan_contract(capsys):
    code = await netcmd.run(_CliClient(), _args(network_action="scan", json=True))
    assert code == netcmd.EXIT_OK
    assert len(json.loads(capsys.readouterr().out)["networks"]) == 2


async def test_scan_flags_unusable_networks(capsys):
    await netcmd.run(_CliClient(), _args(network_action="scan"))
    assert "too weak to rely on" in capsys.readouterr().out


async def test_scan_surfaces_warnings(capsys):
    await netcmd.run(_CliClient(), _args(network_action="scan"))
    assert "duplicate SSID collapsed" in capsys.readouterr().out


# ── set-wifi ─────────────────────────────────────────────────────────

async def test_set_wifi_success_exits_zero(capsys):
    client = _CliClient()
    code = await netcmd.run(client, _args(network_action="set-wifi"))
    assert code == netcmd.EXIT_OK
    assert "Connected in 13.4s" in capsys.readouterr().out


async def test_set_wifi_use_stored_passes_none_as_the_password():
    client = _CliClient()
    await netcmd.run(client, _args(network_action="set-wifi", use_stored=True))
    assert client.switch_calls[0]["password"] is None


async def test_set_wifi_reads_the_password_from_the_environment(monkeypatch):
    monkeypatch.setenv("FWH_WIFI_PASSWORD", "env-secret")
    client = _CliClient()
    await netcmd.run(client, _args(network_action="set-wifi", use_stored=False))
    assert client.switch_calls[0]["password"] == "env-secret"


async def test_set_wifi_warns_that_password_flag_leaks(capsys, monkeypatch):
    monkeypatch.delenv("FWH_WIFI_PASSWORD", raising=False)
    await netcmd.run(_CliClient(),
                     _args(network_action="set-wifi", use_stored=False,
                           password="cli-secret"))
    assert "shell history" in capsys.readouterr().out


async def test_set_wifi_prompts_when_no_password_source_given(monkeypatch):
    monkeypatch.delenv("FWH_WIFI_PASSWORD", raising=False)
    monkeypatch.setattr("getpass.getpass", lambda *_a, **_k: "typed-secret")
    client = _CliClient()
    await netcmd.run(client, _args(network_action="set-wifi", use_stored=False))
    assert client.switch_calls[0]["password"] == "typed-secret"


async def test_set_wifi_refused_preflight_exits_two(capsys):
    refused = {
        **SWITCH_OK,
        "preflight": {"passed": False, "target": "wifi", "fallback": None,
                      "fallbacks": [], "target_signal_pct": None,
                      "reasons": ["no transport other than 'wifi' could carry traffic"],
                      "overrides": []},
        "write_ack": None,
        "verification": {"state": "skipped", "reason": "preflight refused"},
    }
    code = await netcmd.run(_CliClient(switch_result=refused),
                            _args(network_action="set-wifi"))
    assert code == netcmd.EXIT_PREFLIGHT_REFUSED
    assert "No write was sent" in capsys.readouterr().out


async def test_set_wifi_verify_timeout_exits_three(capsys):
    timed_out = {
        **SWITCH_OK,
        "verification": {"state": "timeout", "elapsed_s": 180.0, "polls": 36,
                         "unreachable_polls": 4, "before": {},
                         "last_known": {"type_id": 4, "ip": None},
                         "recovery_hint": "The write has NOT been retried."},
    }
    code = await netcmd.run(_CliClient(switch_result=timed_out),
                            _args(network_action="set-wifi"))
    assert code == netcmd.EXIT_VERIFY_TIMEOUT
    assert "NOT been retried" in capsys.readouterr().out


async def test_set_wifi_skipped_verification_is_not_reported_as_success(capsys):
    """G7 — an accepted write is not an association."""
    skipped = {**SWITCH_OK,
               "verification": {"state": "skipped", "reason": "verify=False"}}
    await netcmd.run(_CliClient(switch_result=skipped),
                     _args(network_action="set-wifi", no_verify=True))
    out = capsys.readouterr().out
    assert "unconfirmed" in out
    assert "Connected in" not in out


async def test_set_wifi_always_says_accepted_is_not_connected(capsys):
    await netcmd.run(_CliClient(), _args(network_action="set-wifi"))
    assert "not the same as connected" in capsys.readouterr().out


async def test_set_wifi_json_emits_the_5_3_contract(capsys):
    code = await netcmd.run(_CliClient(), _args(network_action="set-wifi", json=True))
    payload = json.loads(capsys.readouterr().out)
    assert code == netcmd.EXIT_OK
    assert set(payload) == {"requested", "preflight", "write_ack", "verification"}


async def test_set_wifi_never_prints_the_password(capsys, monkeypatch):
    monkeypatch.setenv("FWH_WIFI_PASSWORD", "hunter2")
    await netcmd.run(_CliClient(), _args(network_action="set-wifi",
                                         use_stored=False, json=True))
    assert "hunter2" not in capsys.readouterr().out


async def test_set_wifi_forwards_the_override_flags():
    client = _CliClient()
    await netcmd.run(client, _args(network_action="set-wifi",
                                   allow_no_fallback=True,
                                   allow_weak_signal=True, timeout=42))
    call = client.switch_calls[0]
    assert call["allow_no_fallback"] is True
    assert call["allow_weak_signal"] is True
    assert call["timeout_s"] == 42


async def test_gateway_offline_exits_four(capsys):
    from franklinwh_cloud.exceptions import GatewayOfflineException

    class _Offline(_CliClient):
        async def get_network_state(self, probe_local=False):
            raise GatewayOfflineException("code 136")

    code = await netcmd.run(_Offline(), _args())
    assert code == netcmd.EXIT_GATEWAY_OFFLINE
    # print_error writes to stderr, which is where an operator expects it.
    assert "Gateway offline" in capsys.readouterr().err
