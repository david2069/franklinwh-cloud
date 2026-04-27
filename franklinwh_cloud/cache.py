"""Method-level TTL cache for FranklinWH API client.

Provides in-process, per-method result caching to protect against callers
polling expensive MQTT endpoints (sendMqtt) more frequently than the data
actually changes.

Usage::

    from franklinwh_cloud.cache import DEFAULT_CACHE

    # Use library-recommended defaults:
    client = FranklinWHCloud(email, password, cache=DEFAULT_CACHE)

    # Override specific TTLs:
    from franklinwh_cloud.cache import DEFAULT_CACHE
    client = FranklinWHCloud(email, password, cache={
        **DEFAULT_CACHE,
        "get_bms_info": 120,         # extend to 2 min
        "get_accessories_power_info": 0,  # disable (always live)
    })

    # No caching (default — current behaviour unchanged):
    client = FranklinWHCloud(email, password)

TTL of 0 disables caching for that method. Missing keys use 0 (not cached).

Design notes:
  - Cache is in-process only, not persistent across restarts.
  - Keys are (method_name, args_hash) so methods with arguments (e.g.
    get_bms_info(serial)) maintain separate cache slots per argument set.
  - Cache is invalidated on write operations that would change the cached
    data (e.g. set_smart_circuit_state invalidates get_smart_circuits_info).
  - snapshot() data is surfaced via client.get_metrics() for observability.
"""

import time


# -------------------------------------------------------------------
# Library-shipped default template
# Callers import and use this directly, or use it as a base to override.
# -------------------------------------------------------------------

DEFAULT_CACHE: dict[str, int] = {
    # sendMqtt calls (expensive — each costs against the 5000/day budget)
    "get_accessories_power_info": 120,   # cmdType 353 — data already in get_stats()
    "get_network_info":           120,   # cmdType 317 — static config
    "get_bms_info":                60,   # cmdType 211×2 — user-triggered but spammable
    "get_smart_circuits_info":    300,   # cmdType 311 — static config, event-driven refresh
    "get_span_setting":           300,   # cmdType 317 variant — static hardware flag

    # REST calls (cheaper but still worth caching for static data)
    "get_connectivity_overview":  120,   # derived from network_info
    "get_device_info":            300,   # static hardware identity
    "get_wifi_config":            300,   # static WiFi config
    "get_accessories":            300,   # static accessory list
}


# -------------------------------------------------------------------
# Cache implementation
# -------------------------------------------------------------------

class MethodCache:
    """In-process TTL cache keyed by (method_name, args_hash).

    Parameters
    ----------
    config : dict[str, int]
        Mapping of method name → TTL in seconds. TTL of 0 disables that
        method. Methods not present in the config are not cached.
    """

    def __init__(self, config: dict[str, int]) -> None:
        self._config: dict[str, int] = config
        self._store: dict[str, tuple] = {}   # key → (result, expires_at)
        self._hits: int = 0
        self._misses: int = 0

    # ------------------------------------------------------------------

    def _key(self, method: str, args_hash: int) -> str:
        return f"{method}:{args_hash}"

    def get(self, method: str, args_hash: int):
        """Return cached result or ``None`` if missing/expired."""
        ttl = self._config.get(method, 0)
        if ttl == 0:
            return None
        k = self._key(method, args_hash)
        entry = self._store.get(k)
        if entry is not None:
            result, expires_at = entry
            if time.monotonic() < expires_at:
                self._hits += 1
                return result
            del self._store[k]
        self._misses += 1
        return None

    def set(self, method: str, args_hash: int, result) -> None:
        """Store a result with its TTL expiry."""
        ttl = self._config.get(method, 0)
        if ttl == 0:
            return
        k = self._key(method, args_hash)
        self._store[k] = (result, time.monotonic() + ttl)

    def invalidate(self, method: str | None = None) -> None:
        """Invalidate one method's cache entries, or the entire cache.

        Parameters
        ----------
        method : str | None
            Method name to invalidate, or ``None`` to clear all entries.
        """
        if method is None:
            self._store.clear()
        else:
            prefix = f"{method}:"
            self._store = {k: v for k, v in self._store.items()
                           if not k.startswith(prefix)}

    def snapshot(self) -> dict:
        """Return cache stats suitable for inclusion in ``get_metrics()``."""
        now = time.monotonic()
        live = sum(1 for _, exp in self._store.values() if now < exp)
        total = self._hits + self._misses
        hit_rate = round(self._hits / total, 3) if total else 0.0
        return {
            "total_entries": len(self._store),
            "live_entries": live,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "configured_methods": len(self._config),
        }
