"""discover(probe_local=True) — LAN reachability on the snapshot.

`discover()` is otherwise cloud-only: all 18 of its calls are API requests, so
it behaves the same wherever it runs. A port probe does not — it only means
something on the gateway's own network. Hence opt-in.
"""

import pytest
from unittest.mock import AsyncMock

from franklinwh_cloud.discovery import DeviceSnapshot, LocalReachability
from franklinwh_cloud.mixins.discover import DiscoverMixin

NET_WIFI = {"currentNetType": 3, "wifi": {"ip": "192.168.0.110"},
            "eth0": {"ip": "0.0.0.0"}, "eth1": {"ip": "0.0.0.0"},
            "operator": {}}
NET_4G = {"currentNetType": 4, "wifi": {"ip": "0.0.0.0"},
          "eth0": {}, "eth1": {}, "operator": {}}


class _Client(DiscoverMixin):
    gateway = "gw"

    def __init__(self, net=NET_WIFI, net_error=None):
        self._net, self._net_error = net, net_error
        self.probed_hosts = []

    async def get_network_info(self):
        if self._net_error:
            raise self._net_error
        return self._net

    def __getattr__(self, name):
        async def _fail(*a, **k):
            raise RuntimeError(f"not mocked: {name}")
        return _fail


@pytest.fixture
def fake_probe(monkeypatch):
    """Control probe results without opening a socket."""
    state = {"open": {9000}, "calls": []}

    async def _probe_tcp(host, port, timeout_s=1.5):
        state["calls"].append((host, port))
        return port in state["open"]

    async def _probe_local(host, *, timeout_s=1.5):
        from franklinwh_cloud.mixins import network as nm
        if not host or host in ("0.0.0.0", ""):
            return {"probed": False, "reachable": None, "port": None, "host": None}
        for p in (nm.LOCAL_API_PORT, nm.LOCAL_SSH_PORT):
            if await _probe_tcp(host, p):
                return {"probed": True, "reachable": True, "port": p, "host": host}
        return {"probed": True, "reachable": False, "port": None, "host": host}

    from franklinwh_cloud.mixins import network as nm
    monkeypatch.setattr(nm, "probe_tcp", _probe_tcp)
    monkeypatch.setattr(nm, "probe_local_reachability", _probe_local)
    return state


async def _run(client, **kw):
    snap = DeviceSnapshot()
    await client._discover_local(snap, kw.get("host"), 1.5)
    return snap


# ── default is off ───────────────────────────────────────────────────

async def test_probing_is_opt_in():
    """discover() must behave identically wherever it runs, unless asked."""
    import inspect

    sig = inspect.signature(DiscoverMixin.discover)
    assert sig.parameters["probe_local"].default is False


def test_a_fresh_snapshot_reports_nothing_probed():
    lr = LocalReachability()
    assert lr.probed is False
    assert lr.reachable is None, "unknown must not read as unreachable"


# ── the happy path ───────────────────────────────────────────────────

async def test_resolves_the_address_from_the_active_transport(fake_probe):
    snap = await _run(_Client())
    assert snap.local.host == "192.168.0.110"
    assert snap.local.reachable is True
    assert snap.local.port == 9000


async def test_an_explicit_host_skips_the_lookup(fake_probe):
    """No extra cmdType 317 read when the caller supplies the address."""
    c = _Client(net_error=RuntimeError("317 must not be called"))
    snap = await _run(c, host="10.0.0.5")
    assert snap.local.host == "10.0.0.5"


async def test_falls_back_to_ssh_when_the_api_port_is_shut(fake_probe):
    fake_probe["open"] = {22}
    snap = await _run(_Client())
    assert snap.local.port == 22


async def test_modbus_is_probed_separately_as_informational(fake_probe):
    fake_probe["open"] = {9000, 502}
    snap = await _run(_Client())
    assert snap.local.modbus_502_open is True
    assert (snap.local.host, 502) in fake_probe["calls"]


async def test_a_closed_modbus_port_is_not_treated_as_a_fault(fake_probe):
    """Modbus listens only when enabled — closed proves nothing."""
    fake_probe["open"] = {9000}
    snap = await _run(_Client())
    assert snap.local.reachable is True
    assert snap.local.modbus_502_open is False


# ── "could not check" is not "not listening" ─────────────────────────

async def test_no_address_on_the_active_transport_yields_unknown(fake_probe):
    """4G holds no IP; mid-reassociation there is none either."""
    snap = await _run(_Client(net=NET_4G))
    assert snap.local.reachable is None
    assert snap.local.probed is False
    assert "no LAN address" in snap.local.note


async def test_a_failed_address_lookup_yields_unknown(fake_probe):
    snap = await _run(_Client(net_error=RuntimeError("mqtt down")))
    assert snap.local.reachable is None
    assert "address lookup failed" in snap.local.note


async def test_an_unreachable_host_is_false_not_none(fake_probe):
    """A probe that ran and found nothing is a real negative."""
    fake_probe["open"] = set()
    snap = await _run(_Client())
    assert snap.local.probed is True
    assert snap.local.reachable is False


async def test_a_probe_exception_never_breaks_discovery(fake_probe, monkeypatch):
    from franklinwh_cloud.mixins import network as nm

    async def _boom(*a, **k):
        raise OSError("socket exploded")

    monkeypatch.setattr(nm, "probe_local_reachability", _boom)
    snap = await _run(_Client())
    assert "probe failed" in snap.local.note


# ── serialisation and schema ─────────────────────────────────────────

def test_local_block_serialises():
    snap = DeviceSnapshot()
    snap.local.reachable = True
    snap.local.port = 9000
    assert snap.to_dict()["local"]["port"] == 9000


@pytest.mark.parametrize("field", ["local.probed", "local.reachable",
                                   "local.port", "local.host"])
def test_schema_documents_the_local_fields(field):
    from franklinwh_cloud.cli_commands.schema import NETWORK_SCHEMA

    assert field in NETWORK_SCHEMA


def test_schema_marks_them_as_a_probe_not_a_gateway_field():
    """Every other entry is something the gateway sent; these are not."""
    from franklinwh_cloud.cli_commands.schema import NETWORK_NOTES, NETWORK_SCHEMA

    assert NETWORK_SCHEMA["local.port"][1] == "TCP probe"
    assert any("not a gateway field" in n for n in NETWORK_NOTES)
