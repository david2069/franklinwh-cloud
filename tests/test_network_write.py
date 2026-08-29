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
