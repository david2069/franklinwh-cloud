"""Tests for the Phase 2 network write path.

Steps P2-1..P2-5 of docs/NETWORK_PHASE2_IMPLEMENTATION_PLAN.md.

No test in this module contacts hardware. Every payload is derived from the HAR
corpus with SSIDs and credentials redacted per .agents/policies/pii_policy.md.
"""

import pytest

from franklinwh_cloud.cache import MethodCache
from franklinwh_cloud.mixins.network import NETWORK_CACHED_READERS, NetworkMixin


# ── P2-1 cache invalidation (design G6; defects 6 and 7) ─────────────

class _CacheClient(NetworkMixin):
    """Minimal stand-in wiring NetworkMixin to a real MethodCache."""

    def __init__(self, cache: MethodCache | None):
        self.method_cache = cache

    def invalidate_cache(self, method=None):
        if self.method_cache:
            self.method_cache.invalidate(method)


@pytest.fixture
def cache():
    return MethodCache({
        "get_network_info": 120,
        "get_wifi_config": 300,
        "get_connectivity_overview": 120,
        "get_smart_circuits_info": 300,
    })


def test_invalidate_network_cache_clears_the_verify_loop_sources(cache):
    """317 and 337 reads must not survive a write — they feed the verifier."""
    cache.set("get_network_info", 0, {"currentNetType": 4})
    cache.set("get_wifi_config", 0, {"wifi_ssid": "old"})

    _CacheClient(cache)._invalidate_network_cache()

    assert cache.get("get_network_info", 0) is None
    assert cache.get("get_wifi_config", 0) is None


def test_invalidate_network_cache_clears_connectivity_overview(cache):
    """Defect 7 — 120 s TTL made it unusable as a post-write view."""
    cache.set("get_connectivity_overview", 0, {"stale": True})
    _CacheClient(cache)._invalidate_network_cache()
    assert cache.get("get_connectivity_overview", 0) is None


def test_invalidate_network_cache_leaves_unrelated_entries_alone(cache):
    """A network write says nothing about smart circuits."""
    cache.set("get_smart_circuits_info", 0, {"circuits": []})
    _CacheClient(cache)._invalidate_network_cache()
    assert cache.get("get_smart_circuits_info", 0) == {"circuits": []}


def test_invalidate_network_cache_clears_every_argument_slot(cache):
    """MethodCache keys on (method, args_hash) — all slots must go."""
    cache.set("get_network_info", 111, {"a": 1})
    cache.set("get_network_info", 222, {"b": 2})

    _CacheClient(cache)._invalidate_network_cache()

    assert cache.get("get_network_info", 111) is None
    assert cache.get("get_network_info", 222) is None


def test_invalidate_network_cache_tolerates_caching_disabled():
    """Clients may be built with cache=None; the write path must still run."""
    _CacheClient(None)._invalidate_network_cache()  # must not raise


def test_invalidate_network_cache_tolerates_a_bare_mixin():
    """Mixin used in isolation has no invalidate_cache attribute."""
    class Bare(NetworkMixin):
        pass

    Bare()._invalidate_network_cache()  # must not raise


def test_cached_reader_list_matches_the_cache_defaults():
    """Guard against a rename silently dropping an entry from invalidation."""
    from franklinwh_cloud.cache import DEFAULT_CACHE

    for name in NETWORK_CACHED_READERS:
        assert name in DEFAULT_CACHE, f"{name} is not a cached method any more"


def test_network_mixin_is_wired_into_client():
    """P2-1 wiring — the write path must be reachable from Client."""
    from franklinwh_cloud.client import Client

    assert issubclass(Client, NetworkMixin)
    assert hasattr(Client, "_invalidate_network_cache")


# ── P2-2 preflight (design section 3) ────────────────────────────────

from franklinwh_cloud.mixins.network import network_write_preflight


def _state(available, linked=None):
    """Minimal get_network_state() output — only the fields preflight reads."""
    return {
        "available_transports": list(available),
        "linked_transports": list(linked if linked is not None else available[:1]),
    }


def _scan(*pairs):
    return {"networks": [{"ssid": s, "signal_pct": p} for s, p in pairs]}


def test_preflight_refuses_when_nothing_would_survive():
    """The whole point: never strand the gateway."""
    r = network_write_preflight(_state(["wifi"]), "wifi")
    assert r["passed"] is False
    assert r["fallback"] is None
    assert "no transport other than 'wifi'" in r["reasons"][0]


def test_preflight_passes_with_a_surviving_transport():
    r = network_write_preflight(_state(["wifi", "4g"]), "wifi")
    assert r["passed"] is True
    assert r["fallback"] == "4g"
    assert r["reasons"] == []


def test_preflight_fallback_set_is_relative_to_the_target_not_the_active():
    """Regression, 2026-08-07.

    Gateway on 4G, rewriting the WiFi config. 4G is the fallback even though it
    is also the active transport. The first draft excluded the active transport
    and would have refused the primary use case outright.
    """
    state = _state(["4g"], linked=["4g"])
    assert network_write_preflight(state, "wifi")["passed"] is True
    assert network_write_preflight(state, "wifi")["fallback"] == "4g"


def test_preflight_uses_available_not_linked():
    """Regression, 2026-08-08.

    A full hour on WiFi with cellular enabled and in reception but parked:
    4GNetSwitch=1, operatorRSSI=22, 4GConnectBSStatus=0. Keying on
    linked_transports refuses every write to the transport carrying traffic.
    """
    state = _state(["wifi", "4g"], linked=["wifi"])
    r = network_write_preflight(state, "wifi")
    assert r["passed"] is True, "idle-but-available cellular is a valid fallback"
    assert r["fallbacks"] == ["4g"]


def test_preflight_allow_no_fallback_overrides_and_is_recorded():
    r = network_write_preflight(_state(["wifi"]), "wifi", allow_no_fallback=True)
    assert r["passed"] is True
    assert r["reasons"] == []
    assert any("allow_no_fallback" in o for o in r["overrides"])


def test_preflight_refuses_a_target_below_the_signal_floor():
    r = network_write_preflight(
        _state(["wifi", "4g"]), "wifi", ssid="weak-net", scan=_scan(("weak-net", 22)),
    )
    assert r["passed"] is False
    assert r["target_signal_pct"] == 22
    assert "below the 30% floor" in r["reasons"][0]


def test_preflight_accepts_a_target_at_the_floor():
    r = network_write_preflight(
        _state(["wifi", "4g"]), "wifi", ssid="ok-net", scan=_scan(("ok-net", 30)),
    )
    assert r["passed"] is True
    assert r["target_signal_pct"] == 30


def test_preflight_refuses_an_ssid_absent_from_the_scan():
    r = network_write_preflight(
        _state(["wifi", "4g"]), "wifi", ssid="hidden", scan=_scan(("other", 90)),
    )
    assert r["passed"] is False
    assert "was not seen in the scan" in r["reasons"][0]


def test_preflight_does_not_leak_the_ssid_into_the_refusal():
    """pii_policy — refusals are logged and land in tests/results/."""
    r = network_write_preflight(
        _state(["wifi", "4g"]), "wifi", ssid="MyHomeNetwork", scan=_scan(("x", 90)),
    )
    assert "MyHomeNetwork" not in r["reasons"][0]
    assert "My***" in r["reasons"][0]


def test_preflight_allow_weak_signal_overrides_the_floor():
    r = network_write_preflight(
        _state(["wifi", "4g"]), "wifi", ssid="weak", scan=_scan(("weak", 8)),
        allow_weak_signal=True,
    )
    assert r["passed"] is True
    assert any("allow_weak_signal" in o for o in r["overrides"])


def test_preflight_skips_the_signal_check_without_a_scan():
    """Unknown must not be treated as a failure, nor silently as a pass."""
    r = network_write_preflight(_state(["wifi", "4g"]), "wifi", ssid="whatever")
    assert r["passed"] is True
    assert r["target_signal_pct"] is None


def test_preflight_signal_check_does_not_apply_to_non_wifi_targets():
    r = network_write_preflight(
        _state(["wifi", "4g"]), "4g", scan=_scan(("x", 8)),
    )
    assert r["passed"] is True
    assert r["fallback"] == "wifi"


def test_preflight_two_independent_gates_both_reported():
    """A caller must see every reason, not just the first."""
    r = network_write_preflight(
        _state(["wifi"]), "wifi", ssid="weak", scan=_scan(("weak", 5)),
    )
    assert r["passed"] is False
    assert len(r["reasons"]) == 2


def test_preflight_allow_no_fallback_does_not_open_the_signal_gate():
    """The overrides are independent — one flag must not imply the other."""
    r = network_write_preflight(
        _state(["wifi"]), "wifi", ssid="weak", scan=_scan(("weak", 5)),
        allow_no_fallback=True,
    )
    assert r["passed"] is False
    assert len(r["reasons"]) == 1
    assert "below the 30% floor" in r["reasons"][0]


def test_preflight_handles_an_empty_available_set():
    r = network_write_preflight({"available_transports": []}, "wifi")
    assert r["passed"] is False
    assert "available=none" in r["reasons"][0]


def test_preflight_is_pure():
    """No mutation of the caller's state dict."""
    state = _state(["wifi", "4g"])
    before = dict(state)
    network_write_preflight(state, "wifi")
    assert state == before


# ── P2-3 set_wifi_credentials (cmdType 337 opt:1) ────────────────────

import json
from unittest.mock import AsyncMock, MagicMock

from franklinwh_cloud.exceptions import FranklinWHError

# Shape validated on live hardware 2026-08-09 — see
# tests/results/2026-08-09_U2-REAPPLY-WIFI_pass.txt
STORED_CFG = {
    "wifi_ssid": "home-net",
    "wifi_password": "stored-secret",
    "ap_ssid": "AP_1234",
    "ap_password": "ap-secret",
    "wifi_safety": 1,
}
ACK_338_OK = json.dumps({"opt": 1, "result": 0, "reason": 0})


class _WriteClient(NetworkMixin):
    """Client stand-in capturing the 337 payload without any I/O."""

    def __init__(self, cfg=STORED_CFG, ack=ACK_338_OK):
        self.sent = []
        self.invalidations = []
        self.get_wifi_config = AsyncMock(return_value=dict(cfg))
        self._mqtt_send = AsyncMock(return_value={"result": {"dataArea": ack}})

    def _build_payload(self, cmd, dataArea):
        self.sent.append((int(cmd), dataArea))
        return {"cmdType": int(cmd), "dataArea": dataArea}

    def invalidate_cache(self, method=None):
        self.invalidations.append(method)


async def test_set_wifi_credentials_refuses_without_confirm():
    """API-affecting write against physical hardware — CLAUDE.md rule 6."""
    c = _WriteClient()
    with pytest.raises(ValueError, match="confirm=True"):
        await c.set_wifi_credentials("home-net", "pw")
    assert c.sent == [], "nothing may reach the wire"


async def test_set_wifi_credentials_rejects_an_empty_ssid():
    c = _WriteClient()
    with pytest.raises(ValueError, match="non-empty"):
        await c.set_wifi_credentials("", "pw", confirm=True)
    assert c.sent == []


async def test_set_wifi_credentials_echoes_the_ap_identity_unchanged():
    """Design 2.3b-1 — ap_SSID/ap_Pw are the aGate's OWN AP and are required."""
    c = _WriteClient()
    await c.set_wifi_credentials("new-net", "new-pw", confirm=True)

    cmd, area = c.sent[0]
    assert cmd == 337
    assert area["opt"] == 1
    assert area["ap_SSID"] == "AP_1234"
    assert area["ap_Pw"] == "ap-secret"


async def test_set_wifi_credentials_sends_the_validated_payload_shape():
    """Exactly the five keys proven by U2; no more, no fewer."""
    c = _WriteClient()
    await c.set_wifi_credentials("new-net", "new-pw", confirm=True)

    _, area = c.sent[0]
    assert set(area) == {"opt", "wifi_SSID", "wifi_Pw", "ap_SSID", "ap_Pw"}
    assert area["wifi_SSID"] == "new-net"
    assert area["wifi_Pw"] == "new-pw"


async def test_set_wifi_credentials_sends_empty_string_for_a_null_password():
    """Open networks are untested, but the key must still be present."""
    c = _WriteClient()
    await c.set_wifi_credentials("open-net", None, confirm=True)
    assert c.sent[0][1]["wifi_Pw"] == ""


async def test_set_wifi_credentials_reports_accepted_not_connected():
    """Gotcha G7 — a wrong password also returns result:0."""
    c = _WriteClient()
    r = await c.set_wifi_credentials("n", "p", confirm=True)

    assert r == {"cmd": 338, "result": 0, "reason": 0, "accepted": True}
    assert "connected" not in r, "the ack must never claim association"


async def test_set_wifi_credentials_marks_a_rejected_write_not_accepted():
    c = _WriteClient(ack=json.dumps({"opt": 1, "result": 1, "reason": 3}))
    r = await c.set_wifi_credentials("n", "p", confirm=True)
    assert r["accepted"] is False
    assert r["reason"] == 3


async def test_set_wifi_credentials_never_returns_the_password():
    """pii_policy — the return value is logged and lands in tests/results/."""
    c = _WriteClient()
    r = await c.set_wifi_credentials("n", "hunter2", confirm=True)
    assert "hunter2" not in json.dumps(r)


async def test_set_wifi_credentials_invalidates_cache_before_and_after():
    """G6 — a stale ap_SSID must not be echoed, and the verifier reads next."""
    c = _WriteClient()
    await c.set_wifi_credentials("n", "p", confirm=True)

    assert "get_wifi_config" in c.invalidations
    assert "get_network_info" in c.invalidations
    assert c.invalidations.count("get_network_info") >= 2, "before read and after write"


async def test_set_wifi_credentials_refuses_when_the_agate_has_no_ap_identity():
    """Without ap_SSID the payload is incomplete; do not guess one."""
    c = _WriteClient(cfg={**STORED_CFG, "ap_ssid": None})
    with pytest.raises(FranklinWHError, match="ap_SSID"):
        await c.set_wifi_credentials("n", "p", confirm=True)
    assert c.sent == []


async def test_set_wifi_credentials_does_not_log_the_password(caplog):
    import logging

    c = _WriteClient()
    with caplog.at_level(logging.DEBUG, logger="franklinwh_cloud"):
        await c.set_wifi_credentials("MyHomeNetwork", "hunter2", confirm=True)

    assert "hunter2" not in caplog.text
    assert "MyHomeNetwork" not in caplog.text
    assert "My***" in caplog.text
