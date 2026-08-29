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
