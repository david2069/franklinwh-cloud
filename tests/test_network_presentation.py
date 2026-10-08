"""Presentation defects: wording, a missing column, and a missing caveat.

DEF-DIAG-PRIMARY-LINK-WORDING, DEF-SCHEMA-DHCP-NOT-RENDERED,
DEF-NET-STATUS-CLOUD-CAVEAT. Cosmetic in mechanism, not in effect: each one
led a reader toward a wrong conclusion about the gateway.
"""

import argparse
import contextlib
import io

import pytest

from franklinwh_cloud.cli_commands import network as netcmd
from tests.test_cli_network import STATE, _CliClient, _args
from tests.test_diag_gateway_nulls import _NullClient, FULL_COMPOSITE


# ── DEF-DIAG-PRIMARY-LINK-WORDING ────────────────────────────────────

async def test_diag_says_active_link_not_primary_link():
    """G9 — 'primary' implies a setting the user chose. There is none."""
    from franklinwh_cloud.cli_commands import diag

    class _C(_NullClient):
        async def get_connectivity_overview(self, deep_scan=False):
            return {"primary": {"id": 3, "name": "WiFi"}, "backups": [],
                    "signals": {}}

        async def get_network_state(self, probe_local=False):
            return {"active": {"key": "wifi"}, "interfaces": [],
                    "available_transports": ["wifi"]}

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        await diag.run(_C(FULL_COMPOSITE), json_output=True)
    # JSON keys are a public contract and deliberately unchanged; only the
    # human-facing label moves.
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        await diag.run(_C(FULL_COMPOSITE), json_output=False)
    out = buf2.getvalue()

    assert "Active Link" in out
    assert "Primary Link" not in out


async def test_diag_json_primary_key_is_unchanged():
    """Wording fix must not rename a key downstream code reads."""
    import json
    from franklinwh_cloud.cli_commands import diag

    class _C(_NullClient):
        async def get_connectivity_overview(self, deep_scan=False):
            return {"primary": {"id": 3, "name": "WiFi"}, "backups": [],
                    "signals": {}}

        async def get_network_state(self, probe_local=False):
            return {"active": {"key": "wifi"}, "interfaces": [],
                    "available_transports": ["wifi"]}

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        await diag.run(_C(FULL_COMPOSITE), json_output=True)
    payload = json.loads(buf.getvalue())
    assert "primary" in payload["connectivity_overview"]


# ── DEF-NET-STATUS-CLOUD-CAVEAT ──────────────────────────────────────

async def test_net_status_caveats_the_unreliable_cloud_flags(capsys):
    """339 reported all-zero while answering through the cloud (§2.5a)."""
    state = {**STATE, "cloud": {"aws_connected": False, "internet": False,
                                "router_status_raw": 0}}
    await netcmd.run(_CliClient(state=state), _args())
    out = capsys.readouterr().out

    assert "AWS ✗" in out
    assert "contradict" in out, "bare crosses read as 'gateway is offline'"


async def test_net_status_stays_quiet_when_the_flags_look_healthy(capsys):
    state = {**STATE, "cloud": {"aws_connected": True, "internet": True,
                                "router_status_raw": 4}}
    await netcmd.run(_CliClient(state=state), _args())
    out = capsys.readouterr().out

    assert "AWS ✓" in out
    assert "contradict" not in out, "no warning when there is nothing to explain"


async def test_net_status_caveat_fires_when_only_one_flag_is_down(capsys):
    state = {**STATE, "cloud": {"aws_connected": True, "internet": False,
                                "router_status_raw": 0}}
    await netcmd.run(_CliClient(state=state), _args())
    assert "contradict" in capsys.readouterr().out


# ── DEF-SCHEMA-DHCP-NOT-RENDERED ─────────────────────────────────────

def _render_schema_network(interfaces):
    """Drive the schema network table with a minimal live_network dict."""
    from franklinwh_cloud.cli_commands import schema

    live_network = {
        "gateway_id": "g", "active": {"label": "WiFi", "ip": "192.168.0.110",
                                      "gateway": "192.168.0.1",
                                      "selection": "device-managed"},
        "interfaces": interfaces,
        "cloud": {"aws_connected": False, "internet": False,
                  "router_status_raw": 0},
        "linked_transports": ["wifi"], "available_transports": ["wifi", "4g"],
        "redundant": True, "source": {"cmds": [317, 339, 341],
                                      "extended_339": True},
    }
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        schema._terminal_output(None, None, None, None, live_network=live_network)
    return buf.getvalue()


def _iface_row(out, key):
    """Just the interface table row, so prose elsewhere cannot match."""
    for line in out.splitlines():
        stripped = line.strip()
        if stripped.startswith(key + " ") or stripped.startswith(key + "  "):
            return line
    raise AssertionError(f"no table row for {key!r}")


def test_schema_renders_the_advertised_dhcp_field():
    """The inventory advertises interfaces[].dhcp; the table must show it."""
    out = _render_schema_network([
        {"id": 3, "key": "wifi", "label": "WiFi", "enabled": True, "link": True,
         "ip": "192.168.0.110", "dhcp": True, "is_active": True,
         "available": True, "signal_pct": 72},
    ])
    assert "addr src" in out, "column header must be present"
    assert "dhcp" in _iface_row(out, "wifi")


def test_schema_distinguishes_static_from_dhcp():
    out = _render_schema_network([
        {"id": 1, "key": "eth0", "label": "Ethernet 1", "enabled": True,
         "link": False, "ip": None, "dhcp": False, "is_active": False,
         "available": False},
    ])
    assert "static" in _iface_row(out, "eth0")


def test_schema_renders_unknown_dhcp_state_as_dash():
    """4G has no dhcp key at all — must not read as 'static'."""
    out = _render_schema_network([
        {"id": 4, "key": "4g", "label": "4G Mobile", "enabled": True,
         "link": False, "ip": None, "is_active": False, "available": True,
         "signal_raw": 22, "sim_status_name": "Active"},
    ])
    row = _iface_row(out, "4g")
    assert "static" not in row and "dhcp" not in row


# ── evidenced reachability vs gateway self-report ────────────────────

async def test_net_status_leads_with_evidenced_reachability(capsys):
    """The only trustworthy claim: this reading arrived through the cloud."""
    state = {**STATE, "cloud": {"gateway_reachable": True,
                                "aws_connected": False, "internet": False,
                                "router_status_raw": 0}}
    await netcmd.run(_CliClient(state=state), _args())
    out = capsys.readouterr().out

    assert "reachable" in out
    assert "arrived through it" in out


async def test_net_status_labels_the_flags_as_a_self_report(capsys):
    """They are the gateway's opinion, not an observation."""
    state = {**STATE, "cloud": {"gateway_reachable": True,
                                "aws_connected": False, "internet": False,
                                "router_status_raw": 0}}
    await netcmd.run(_CliClient(state=state), _args())
    out = capsys.readouterr().out

    assert "self-report" in out.lower()
    assert "Cloud: AWS ✗" not in out, "must not present the flag as the verdict"


def test_network_state_exposes_both_raw_aws_flags():
    """DEF-AWS-STATUS-SOURCE — 317 and 339 have been seen disagreeing."""
    import inspect

    from franklinwh_cloud.mixins import devices

    src = inspect.getsource(devices.DevicesMixin.get_network_state)
    assert "aws_status_317_raw" in src
    assert "aws_status_339_raw" in src
    assert "gateway_reachable" in src


def test_schema_health_check_reports_the_flag_disagreement():
    from franklinwh_cloud.cli_commands.schema import network_health

    findings = network_health({
        "interfaces": [],
        "available_transports": ["wifi", "4g"],
        "cloud": {"gateway_reachable": True, "aws_connected": False,
                  "aws_status_339_raw": 0, "aws_status_317_raw": 1},
    })
    unreliable = [f for f in findings if f["code"] == "cloud_flags_unreliable"]
    assert unreliable, "the caveat must still fire"
    assert "317 reports awsStatus=1" in unreliable[0]["detail"]


def test_schema_health_check_omits_the_comparison_when_flags_agree():
    from franklinwh_cloud.cli_commands.schema import network_health

    findings = network_health({
        "interfaces": [],
        "available_transports": ["wifi", "4g"],
        "cloud": {"gateway_reachable": True, "aws_connected": False,
                  "aws_status_339_raw": 0, "aws_status_317_raw": 0},
    })
    unreliable = [f for f in findings if f["code"] == "cloud_flags_unreliable"]
    assert "317 reports" not in unreliable[0]["detail"]
