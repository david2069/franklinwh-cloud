"""DEF-DIAG-NETTYPE-ENUM — `Active Network` label.

`diag` rendered `Active Network: WiFi+Ethernet` on a gateway that was on WiFi
only, with both Ethernet ports down. It indexed a local bitmask-style table
with `currentNetType`, which is positional. Gotcha G2: the codebase carries
three different network encodings and they are not interchangeable.
"""

import contextlib
import io
import json

import pytest

from franklinwh_cloud.cli_commands import diag
from franklinwh_cloud.const.devices import NETWORK_TYPES
from tests.test_diag_gateway_nulls import _NullClient, FULL_COMPOSITE


def _net_info(current_net_type):
    # Placeholder MACs. This fixture exercises enum labelling and has no need
    # of real hardware identifiers — and this is a public repository.
    return {
        "currentNetType": current_net_type,
        "wifi": {"mac": "AA:BB:CC:DD:EE:03", "dhcp": True,
                 "ip": "192.168.0.110", "dns": "8.8.8.8",
                 "gateway": "192.168.0.1"},
        "eth0": {"mac": "AA:BB:CC:DD:EE:01", "dhcp": False, "ip": "0.0.0.0",
                 "dns": "8.8.8.8", "gateway": "172.16.1.1"},
        "eth1": {"mac": "AA:BB:CC:DD:EE:02", "dhcp": True, "ip": "0.0.0.0",
                 "dns": "8.8.8.8", "gateway": "0.0.0.0"},
        "operator": {"mac": "AA:BB:CC:DD:EE:04", "rssi": 22,
                     "dns": "192.192.192.192"},
        "awsStatus": 1,
    }


async def _active_network_line(current_net_type):
    class _C(_NullClient):
        async def get_network_info(self):
            return _net_info(current_net_type)

        async def get_connectivity_overview(self, deep_scan=False):
            return {"primary": {"id": current_net_type, "name": "x"},
                    "backups": [], "signals": {}}

        async def get_network_state(self, probe_local=False):
            return {"active": {"key": "wifi"}, "interfaces": [],
                    "available_transports": ["wifi"]}

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        await diag.run(_C(FULL_COMPOSITE), json_output=False)
    for line in buf.getvalue().splitlines():
        if "Active Network" in line:
            return line
    raise AssertionError("Active Network row not rendered")


# ── the reported defect ──────────────────────────────────────────────

async def test_wifi_is_not_labelled_wifi_plus_ethernet():
    """The live case: currentNetType 3 is WiFi, not WiFi+Ethernet."""
    line = await _active_network_line(3)
    assert "WiFi" in line
    assert "Ethernet" not in line


async def test_eth0_is_not_labelled_wifi():
    """currentNetType 1 is an Ethernet port; the bitmask table called it WiFi."""
    line = await _active_network_line(1)
    assert "Ethernet" in line
    assert "WiFi" not in line


async def test_ethernet_labels_do_not_collide_with_vendor_port_numbers():
    """Installation Guide p.59: only the vendor's "Eth1" reaches the internet.

    Labelling API `eth0` as "Ethernet 1" invited exactly the wrong reading.
    Labels are keyed to the API field instead.
    """
    from franklinwh_cloud.const.devices import NETWORK_TYPES

    assert NETWORK_TYPES[1] == "Ethernet (eth0)"
    assert NETWORK_TYPES[2] == "Ethernet (eth1)"


# ── the whole enum, so no id regresses ───────────────────────────────

@pytest.mark.parametrize("net_type,expected", sorted(NETWORK_TYPES.items()))
async def test_every_network_type_matches_the_canonical_table(net_type, expected):
    line = await _active_network_line(net_type)
    assert expected in line


async def test_unknown_type_is_reported_as_unknown_not_guessed():
    line = await _active_network_line(99)
    assert "Unknown (99)" in line


async def test_missing_type_does_not_render_a_false_label():
    """Absent currentNetType previously defaulted to 0 -> 'None'."""
    line = await _active_network_line(None)
    assert "Unknown (None)" in line


def test_diag_uses_the_shared_constant_not_a_local_copy():
    """Guard against the bitmask table being reintroduced.

    Checks string *literals* rather than raw source, so the comment explaining
    the defect does not trip its own guard.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(diag))
    literals = {n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    combined = {s for s in literals if "+" in s and "WiFi" in s}
    assert not combined, f"bitmask enum labels must not return: {combined}"

    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "NETWORK_TYPES" in names
