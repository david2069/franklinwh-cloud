"""aGate network write path — getting the gateway onto a chosen WiFi network.

Phase 2 of ``docs/NETWORK_CONNECTIVITY_DESIGN.md``; step IDs below refer to
``docs/NETWORK_PHASE2_IMPLEMENTATION_PLAN.md``.

The five network *readers* deliberately remain in :class:`DevicesMixin` — the
module split proposed in design section 4 is deferred Phase 1c and was not
approved as part of this phase. This module is additive: it holds only the new
write path, so nothing downstream moves.

Why this exists
---------------
The aGate always falls back to 4G when local connectivity drops, but it does not
reliably come back to WiFi afterwards — it strands itself on cellular. Recovering
from that currently requires the vendor mobile app's WiFi wizard
(``docs/troubleshooting/2026-03-21_wifi_dhcp_failure.md``). This module is the
SDK equivalent of that wizard.
"""

import logging

logger = logging.getLogger("franklinwh_cloud")


# Cached readers whose contents a network write invalidates. Their TTLs are
# 300 s (get_wifi_config) and 120 s (get_network_info, get_connectivity_overview)
# per cache.py DEFAULT_CACHE, so without this a post-write verifier reads state
# from before the write and reports the wrong answer in either direction.
# Design gotcha G6; defects 6 and 7 in design section 8.
NETWORK_CACHED_READERS = (
    "get_network_info",          # cmdType 317 — the verify loop's primary source
    "get_wifi_config",           # cmdType 337 — SSID correlation in the verify loop
    "get_connectivity_overview", # derived from network_info; never used as a verifier
)


class NetworkMixin:
    """Network configuration write methods (cmdType 337)."""

    def _invalidate_network_cache(self) -> None:
        """Drop cached network reads so the next one hits the gateway.

        Called both *after* a write (the cached config is now stale) and
        *before* every verify poll (a poll that reads a cached answer is not a
        verification at all).

        Note
        ----
        A ``use_cache=False`` keyword on the readers would not work as a bypass:
        ``Client._apply_method_cache`` hashes kwargs into the cache key, so the
        flag would simply populate a second cache slot rather than skip the
        cache. Invalidate-then-read is the minimal correct approach against the
        existing caching design.

        Safe to call on a client built with caching disabled — ``invalidate_cache``
        is a no-op when ``method_cache`` is unset.
        """
        invalidate = getattr(self, "invalidate_cache", None)
        if invalidate is None:
            # Not a full Client (e.g. the mixin under unit test in isolation).
            logger.debug("_invalidate_network_cache: no cache on this client")
            return
        for method_name in NETWORK_CACHED_READERS:
            invalidate(method_name)
