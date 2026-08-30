"""Local reachability discriminator (TCP 9000 / 22).

Port confirmed against the sibling franklinwh-local project
(franklinwh_local/transport.py DEFAULT_PORT = 9000) rather than assumed —
the aGate's local broker protocol, the mobile app's "Direct Connection".

The whole point is that local reachability answers a DIFFERENT question from
cloud connectivity. It must never stand in for it, and never gate a write.
"""

import pytest

from franklinwh_cloud.mixins import network as netmod
from franklinwh_cloud.mixins.network import (
    LOCAL_API_PORT,
    LOCAL_SSH_PORT,
    network_write_preflight,
    probe_local_reachability,
)


@pytest.fixture
def fake_ports(monkeypatch):
    """Control which ports 'answer' without touching a socket."""
    open_ports = set()

    async def _probe(host, port, timeout_s=1.5):
        return port in open_ports

    monkeypatch.setattr(netmod, "probe_tcp", _probe)
    return open_ports


# ── port selection ───────────────────────────────────────────────────

def test_the_local_api_port_is_9000_not_10000():
    """Verified against franklinwh-local, not assumed."""
    assert LOCAL_API_PORT == 9000
    assert LOCAL_SSH_PORT == 22


async def test_prefers_the_local_api_port(fake_ports):
    """9000 proves the application is up; 22 only proves the box booted."""
    fake_ports.update({9000, 22})
    r = await probe_local_reachability("192.168.0.110")
    assert r["reachable"] is True
    assert r["port"] == 9000


async def test_falls_back_to_ssh(fake_ports):
    fake_ports.add(22)
    r = await probe_local_reachability("192.168.0.110")
    assert r["reachable"] is True
    assert r["port"] == 22


async def test_reports_unreachable_when_nothing_answers(fake_ports):
    r = await probe_local_reachability("192.168.0.110")
    assert r["reachable"] is False
    assert r["port"] is None


async def test_modbus_is_never_used_for_liveness(fake_ports):
    """502 listens only when enabled — a closed port proves nothing."""
    fake_ports.add(502)
    r = await probe_local_reachability("192.168.0.110")
    assert r["reachable"] is False, "502 must not count as liveness"


# ── the gap that exists by design ────────────────────────────────────

@pytest.mark.parametrize("host", [None, "", "0.0.0.0"])
async def test_no_address_means_not_probed_not_unreachable(host, fake_ports):
    """Mid-reassociation there is no address — exactly when it's most wanted.

    'Could not check' must not be recorded as 'did not answer'.
    """
    r = await probe_local_reachability(host)
    assert r["probed"] is False
    assert r["reachable"] is None


# ── it must never become a verdict ───────────────────────────────────

def test_local_reachability_does_not_enter_the_write_preflight():
    """Answering on the LAN says nothing about reaching the cloud."""
    state = {
        "available_transports": ["wifi"],
        "linked_transports": ["wifi"],
        "active": {"key": "wifi"},
        "local": {"probed": True, "reachable": True, "port": 9000},
    }
    r = network_write_preflight(state, "wifi")
    assert r["passed"] is False, "a local answer is not a fallback transport"


async def test_get_network_state_does_not_probe_by_default():
    """I/O stays opt-in; existing callers are unaffected."""
    import inspect

    from franklinwh_cloud.mixins.devices import DevicesMixin

    sig = inspect.signature(DevicesMixin.get_network_state)
    assert sig.parameters["probe_local"].default is False


# ── CLI rendering ────────────────────────────────────────────────────

from franklinwh_cloud.cli_commands import network as netcmd
from tests.test_cli_network import STATE, _CliClient, _args


class _LocalClient(_CliClient):
    def __init__(self, local, **kw):
        super().__init__(**kw)
        self._local = local

    async def get_network_state(self, probe_local=False):
        return {**self._state, "local": self._local if probe_local else
                {"probed": False, "reachable": None, "port": None}}


async def test_status_shows_the_answering_port(capsys):
    client = _LocalClient({"probed": True, "reachable": True, "port": 9000,
                           "host": "192.168.0.110"})
    await netcmd.run(client, _args(probe_local=True))
    out = capsys.readouterr().out
    assert ":9000" in out


async def test_status_caveats_a_local_miss(capsys):
    """You may simply not be on its LAN — that is not a gateway fault."""
    client = _LocalClient({"probed": True, "reachable": False, "port": None,
                           "host": "192.168.0.110"})
    await netcmd.run(client, _args(probe_local=True))
    out = capsys.readouterr().out
    assert "only meaningful from the gateway's own LAN" in out


async def test_status_says_nothing_when_not_probed(capsys):
    client = _LocalClient({"probed": True, "reachable": True, "port": 9000,
                           "host": "1.2.3.4"})
    await netcmd.run(client, _args(probe_local=False))
    out = capsys.readouterr().out
    assert "Local" not in out
