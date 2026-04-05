"""Tests for franklinwh_cloud.cache — MethodCache and DEFAULT_CACHE.

Trace: FEAT-TTL-CACHE
"""

import time
import pytest
from franklinwh_cloud.cache import MethodCache, DEFAULT_CACHE


class TestMethodCacheBasics:
    """Core get/set/expire behaviour."""

    def test_miss_on_empty_cache(self):
        cache = MethodCache({"get_network_info": 60})
        assert cache.get("get_network_info", 0) is None

    def test_set_then_get_returns_result(self):
        cache = MethodCache({"get_network_info": 60})
        cache.set("get_network_info", 0, {"ip": "192.168.1.1"})
        result = cache.get("get_network_info", 0)
        assert result == {"ip": "192.168.1.1"}

    def test_ttl_zero_never_caches(self):
        cache = MethodCache({"get_network_info": 0})
        cache.set("get_network_info", 0, {"ip": "192.168.1.1"})
        assert cache.get("get_network_info", 0) is None

    def test_unconfigured_method_not_cached(self):
        cache = MethodCache({"get_network_info": 60})
        cache.set("get_bms_info", 0, {"data": "x"})
        assert cache.get("get_bms_info", 0) is None

    def test_different_args_separate_slots(self):
        cache = MethodCache({"get_bms_info": 60})
        h1 = hash((("serial_A",), ()))
        h2 = hash((("serial_B",), ()))
        cache.set("get_bms_info", h1, {"serial": "A"})
        cache.set("get_bms_info", h2, {"serial": "B"})
        assert cache.get("get_bms_info", h1) == {"serial": "A"}
        assert cache.get("get_bms_info", h2) == {"serial": "B"}

    def test_expired_entry_returns_none(self):
        cache = MethodCache({"get_network_info": 1})
        # Manually insert an already-expired entry
        from franklinwh_cloud.cache import time as cache_time
        import time as t
        cache._store["get_network_info:0"] = ({"ip": "x"}, t.monotonic() - 1)
        assert cache.get("get_network_info", 0) is None

    def test_expired_entry_is_evicted(self):
        cache = MethodCache({"get_network_info": 1})
        import time as t
        cache._store["get_network_info:0"] = ({"ip": "x"}, t.monotonic() - 1)
        cache.get("get_network_info", 0)  # triggers eviction
        assert "get_network_info:0" not in cache._store


class TestMethodCacheInvalidation:

    def test_invalidate_specific_method(self):
        cache = MethodCache({"get_network_info": 60, "get_bms_info": 60})
        cache.set("get_network_info", 0, {"ip": "x"})
        cache.set("get_bms_info", 0, {"bms": "y"})
        cache.invalidate("get_network_info")
        assert cache.get("get_network_info", 0) is None
        assert cache.get("get_bms_info", 0) == {"bms": "y"}

    def test_invalidate_all(self):
        cache = MethodCache({"get_network_info": 60, "get_bms_info": 60})
        cache.set("get_network_info", 0, {"ip": "x"})
        cache.set("get_bms_info", 0, {"bms": "y"})
        cache.invalidate()
        assert cache.get("get_network_info", 0) is None
        assert cache.get("get_bms_info", 0) is None


class TestMethodCacheMetrics:

    def test_hit_miss_counters(self):
        cache = MethodCache({"get_network_info": 60})
        cache.set("get_network_info", 0, {"ip": "x"})
        cache.get("get_network_info", 0)   # hit
        cache.get("get_network_info", 0)   # hit
        # unconfigured method returns None immediately — does not count as a miss
        # (the miss counter tracks configured-but-expired/absent entries only)
        cache.get("get_network_info", 999)  # miss (configured method, different args)
        snap = cache.snapshot()
        assert snap["hits"] == 2
        assert snap["misses"] == 1

    def test_snapshot_structure(self):
        cache = MethodCache(DEFAULT_CACHE)
        snap = cache.snapshot()
        assert "hits" in snap
        assert "misses" in snap
        assert "hit_rate" in snap
        assert "live_entries" in snap
        assert "configured_methods" in snap
        assert snap["configured_methods"] == len(DEFAULT_CACHE)


class TestDefaultCache:

    def test_default_cache_is_dict(self):
        assert isinstance(DEFAULT_CACHE, dict)

    def test_default_cache_has_expected_methods(self):
        expected = {
            "get_accessories_power_info",
            "get_network_info",
            "get_bms_info",
            "get_smart_circuits_info",
            "get_connectivity_overview",
            "get_device_info",
            "get_wifi_config",
            "get_accessories",
        }
        for m in expected:
            assert m in DEFAULT_CACHE, f"{m} missing from DEFAULT_CACHE"

    def test_default_cache_all_ttls_positive(self):
        for method, ttl in DEFAULT_CACHE.items():
            assert ttl > 0, f"{method} has TTL={ttl} — use dict exclusion to disable, not 0 in template"

    def test_get_accessories_power_info_ttl_meaningful(self):
        # Must be at least 60s to meaningfully reduce the 30s poll impact
        assert DEFAULT_CACHE["get_accessories_power_info"] >= 60
