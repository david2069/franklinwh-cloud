"""DEF-DIAG-BACKUP-FALSE-NEGATIVE — `diag` fallback viability.

`diag` reported "Backup Links: None viable" on a gateway that demonstrably
held a working 4G lifeline, because it keyed 4G viability on
signals.mobile_signal (203/runtimeData), which reads 0.0 on that hardware
while 317 operatorRSSI reports 22/52 with the SIM active.

Viability now comes from get_network_state()['available_transports'].
"""

from franklinwh_cloud.cli_commands.diag import _fallback_summary


# ── the live case that exposed the defect (2026-08-30) ───────────────
# Active WiFi, both Ethernet ports down, 4G enabled with SIM Active at 22/52.
# get_network_state reports available=['wifi','4g'], redundant=True.

LIVE_STATE = {
    "active": {"id": 3, "key": "wifi", "label": "WiFi", "ip": "192.168.0.110"},
    "interfaces": [
        {"id": 1, "key": "eth0", "label": "Ethernet 1", "available": False},
        {"id": 2, "key": "eth1", "label": "Ethernet 2", "available": False},
        {"id": 3, "key": "wifi", "label": "WiFi", "available": True},
        {"id": 4, "key": "4g", "label": "4G Mobile", "available": True},
    ],
    "available_transports": ["wifi", "4g"],
    "linked_transports": ["wifi"],
    "redundant": True,
}

# What get_connectivity_overview returned for the same gateway: runtimeData
# signal is 0.0, which is what drove the false negative.
LIVE_OVERVIEW = {
    "primary": {"id": 3, "name": "WiFi", "ip": "192.168.0.110"},
    "backups": [
        {"id": 1, "name": "Ethernet 1", "ip": "0.0.0.0"},
        {"id": 2, "name": "Ethernet 2", "ip": "0.0.0.0"},
        {"id": 4, "name": "4G Mobile", "rssi": 22},
    ],
    "signals": {"wifi_signal": 0.0, "mobile_signal": 0.0},
}


def test_the_reported_defect_is_fixed():
    """The exact live case: 4G is a viable fallback and must be named."""
    assert _fallback_summary(LIVE_STATE, LIVE_OVERVIEW) == "4G Mobile"


def test_legacy_path_still_reproduces_the_defect():
    """Guard: proves the fix is the network-state path, not a coincidence."""
    assert "None viable" in _fallback_summary(None, LIVE_OVERVIEW)


def test_active_transport_is_not_listed_as_its_own_backup():
    out = _fallback_summary(LIVE_STATE, LIVE_OVERVIEW)
    assert "WiFi" not in out


def test_genuinely_no_fallback_still_says_so():
    """The warning must survive — it gates a network write."""
    state = {**LIVE_STATE, "available_transports": ["wifi"], "redundant": False}
    assert "None viable" in _fallback_summary(state, LIVE_OVERVIEW)


def test_multiple_fallbacks_are_all_named():
    state = {**LIVE_STATE, "available_transports": ["wifi", "4g", "eth0"]}
    out = _fallback_summary(state, LIVE_OVERVIEW)
    assert "4G Mobile" in out and "Ethernet 1" in out


def test_idle_cellular_counts_as_available():
    """2026-08-08 — the aGate parks transports it is not using.

    4G carrying no traffic (link down, no IP) is still the lifeline.
    """
    state = {
        **LIVE_STATE,
        "linked_transports": ["wifi"],
        "available_transports": ["wifi", "4g"],
    }
    assert _fallback_summary(state, LIVE_OVERVIEW) == "4G Mobile"


def test_falls_back_to_legacy_when_network_state_is_unavailable():
    """A failed extra call must not make this row worse than it was."""
    overview = {
        **LIVE_OVERVIEW,
        "signals": {"wifi_signal": 60.0, "mobile_signal": 40.0},
    }
    assert "4G Mobile" in _fallback_summary(None, overview)


def test_unknown_transport_key_degrades_to_the_raw_key():
    state = {**LIVE_STATE, "available_transports": ["wifi", "wibble"]}
    assert "wibble" in _fallback_summary(state, LIVE_OVERVIEW)


def test_missing_interfaces_list_does_not_crash():
    state = {"active": {"key": "wifi"}, "available_transports": ["wifi", "4g"]}
    assert _fallback_summary(state, LIVE_OVERVIEW) == "4g"


def test_empty_state_is_treated_as_no_fallback_not_a_crash():
    assert "None viable" in _fallback_summary({}, {})


# ── render smoke test ────────────────────────────────────────────────

import pytest
from unittest.mock import AsyncMock, MagicMock

from franklinwh_cloud.cli_commands import diag


class _DiagClient:
    """Every call fails except the connectivity path, which must render fully.

    diag wraps each section in try/except, so a bare mock exercises the
    Connectivity Overview renderer end to end while the rest degrade to their
    error rows. This is the shape that catches NameErrors in that renderer —
    the try/except would swallow them at runtime but the row would silently
    vanish from a support report.
    """

    gateway = "test-gateway"
    # Plain attributes diag reads directly (not awaited) must not be mocks.
    edge_tracker = None
    metrics = None
    rate_limiter = None

    def __init__(self, net_state=LIVE_STATE):
        self._net_state = net_state
        self.method_cache = None

    async def get_home_gateway_list(self):
        # diag returns early unless auth succeeds.
        return {"result": [{"id": "test-gateway"}]}

    async def get_connectivity_overview(self, deep_scan=False):
        return dict(LIVE_OVERVIEW, span_connected=False,
                    modbus_tcp_502_open=True)

    async def get_network_state(self, probe_local=False):
        if isinstance(self._net_state, BaseException):
            raise self._net_state
        return self._net_state

    def __getattr__(self, name):
        return AsyncMock(side_effect=RuntimeError(f"not mocked: {name}"))

    def get_metrics(self):
        return {
            "total_api_calls": 0, "avg_response_time_s": 0.0,
            "min_response_time_s": 0.0, "max_response_time_s": 0.0,
            "total_errors": 0, "total_rate_limits": 0, "retry_count": 0,
            "uptime_s": 0.0, "calls_by_endpoint": {},
        }


async def test_diag_renders_the_connectivity_section_without_error(capsys):
    await diag.run(_DiagClient(), json_output=False)
    out = capsys.readouterr().out

    assert "Connectivity Overview" in out
    assert "Backup Links" in out
    assert "4G Mobile" in out, "the live case must render as a viable fallback"
    assert "None viable" not in out


async def test_diag_still_renders_when_network_state_fails(capsys):
    """The extra call is best-effort — its failure must not drop the row."""
    client = _DiagClient(net_state=RuntimeError("gateway offline"))
    await diag.run(client, json_output=False)
    out = capsys.readouterr().out

    assert "Backup Links" in out, "row must survive on the legacy path"


async def test_diag_json_exposes_network_state(capsys):
    await diag.run(_DiagClient(), json_output=True)
    import json as _json
    payload = _json.loads(capsys.readouterr().out)

    assert payload["network_state"]["available_transports"] == ["wifi", "4g"]
    assert "connectivity_overview" in payload, "existing key must not be removed"
