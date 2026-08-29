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

import asyncio
import json
import logging
import time

from franklinwh_cloud.exceptions import FranklinWHError
from franklinwh_cloud.models import MqttCmd

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
# ── P2-2 preflight ───────────────────────────────────────────────────

#: Minimum target signal percentage accepted by default. Working links are
#: observed at 68-100 across the HAR corpus; 8-28 are noise-floor neighbours.
DEFAULT_MIN_RSSI = 30


def network_write_preflight(
    state,
    target,
    *,
    ssid=None,
    scan=None,
    min_rssi=DEFAULT_MIN_RSSI,
    allow_no_fallback=False,
    allow_weak_signal=False,
):
    """Decide whether a network write is safe to send.

    Pure function over :meth:`get_network_state` output — no I/O, so the safety
    rule is unit-testable without hardware. Design section 3.

    The rule: **a transport other than the one being modified must be able to
    take over.** If a WiFi write lands with a bad password while nothing else
    can carry traffic, the aGate goes dark and recovery becomes physical,
    because the cloud path you would use to fix it is the path you just broke.

    Parameters
    ----------
    state : dict
        Output of :meth:`get_network_state`.
    target : str
        Interface key being modified — ``"wifi"``, ``"eth0"``, ``"eth1"`` or
        ``"4g"``. The fallback set is computed relative to *this*, not to the
        transport currently active.
    ssid : str, optional
        SSID being switched to. Only used for the signal check.
    scan : dict, optional
        Output of :meth:`scan_wifi_networks_ranked`. Without it the signal
        check is skipped as unknown rather than assumed to pass.
    min_rssi : int
        Signal floor for the target network (default 30).
    allow_no_fallback : bool
        Override the fallback gate. This is the dangerous one.
    allow_weak_signal : bool
        Override the signal gate, including "SSID not present in the scan"
        (hidden SSIDs never appear in a scan, and joining one blind is
        untested — design section 3).

    Returns
    -------
    dict
        ``{passed, target, fallback, fallbacks, target_signal_pct, reasons,
        overrides}`` — the ``preflight`` block of the section 5.3 contract.
        ``reasons`` lists refusals; ``overrides`` lists gates that failed but
        were forced open by a caller flag.

    Note
    ----
    Keyed on ``available_transports``, never ``linked_transports``. This was
    corrected twice by live data and both mistakes would have been shipped:

    * *2026-08-07* — excluding the **active** transport yielded "no fallback"
      while the gateway sat on 4G rewriting its WiFi config, refusing the
      primary use case. The set is relative to the write target.
    * *2026-08-08* — keying on ``linked_transports`` refuses **every** write to
      whichever transport is carrying traffic, because the aGate parks the ones
      it is not using: a full hour on WiFi with ``4GNetSwitch=1`` and
      ``operatorRSSI=21-22`` but ``4GConnectBSStatus=0``. Cellular was idle,
      not dead — it had carried the connection that same morning.
    """
    reasons = []
    overrides = []

    available = set(state.get("available_transports") or [])
    fallbacks = sorted(available - {target})

    if not fallbacks:
        msg = (
            f"no transport other than {target!r} could carry traffic if this "
            f"write fails (available={sorted(available) or 'none'})"
        )
        if allow_no_fallback:
            overrides.append(f"allow_no_fallback: {msg}")
        else:
            reasons.append(msg)

    # Signal floor on the target network. Only meaningful for WiFi, and only
    # when a scan was supplied — absent a scan the answer is unknown, and
    # unknown must not read as "fine".
    target_signal_pct = None
    if target == "wifi" and scan is not None and ssid is not None:
        match = next(
            (n for n in (scan.get("networks") or []) if n.get("ssid") == ssid),
            None,
        )
        if match is None:
            msg = (
                f"SSID {_redact(ssid)} was not seen in the scan; hidden networks "
                f"never appear in one and joining blind is untested"
            )
            if allow_weak_signal:
                overrides.append(f"allow_weak_signal: {msg}")
            else:
                reasons.append(msg)
        else:
            target_signal_pct = match.get("signal_pct")
            if (target_signal_pct or 0) < min_rssi:
                msg = (
                    f"target signal {target_signal_pct}% is below the {min_rssi}% "
                    f"floor; associating may succeed while DHCP never completes"
                )
                if allow_weak_signal:
                    overrides.append(f"allow_weak_signal: {msg}")
                else:
                    reasons.append(msg)

    return {
        "passed": not reasons,
        "target": target,
        "fallback": fallbacks[0] if fallbacks else None,
        "fallbacks": fallbacks,
        "target_signal_pct": target_signal_pct,
        "reasons": reasons,
        "overrides": overrides,
    }


def _redact(ssid):
    """Render an SSID for a log or error without printing it in full."""
    if not ssid:
        return "<empty>"
    return f"{ssid[:2]}***" if len(ssid) > 2 else "***"


# ── P2-3 the write path ──────────────────────────────────────────────

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

    async def set_wifi_credentials(self, ssid, password, *, confirm=False):
        """Write WiFi credentials to the aGate (cmdType 337 ``opt:1``).

        Read-modify-write: reads ``337 opt:0`` for the aGate's own access-point
        identity, then writes ``opt:1`` with that identity echoed back unchanged
        alongside the new SSID and password.

        This is the *entire* switch mechanism. In the captured app session a
        single 337 write flipped ``currentNetType`` 4 (4G) to 3 (WiFi) about
        13 s later, with ``wifiStaticIP`` going 0.0.0.0 to a real lease. There
        is no separate "make this primary" command — see
        :func:`network_write_preflight` and design section 2.3a.

        Parameters
        ----------
        ssid : str
            SSID to join.
        password : str
            Passphrase. Never logged, never echoed back in the return value.
        confirm : bool
            Must be True. This is an API-affecting write against physical
            hardware (CLAUDE.md rule 6).

        Returns
        -------
        dict
            ``{"cmd": 338, "result": int, "reason": int, "accepted": bool}``.

        Warning
        -------
        A ``result`` of 0 means **the aGate accepted the configuration**, not
        that it associated with the access point. A wrong password returns 0
        too (gotcha G7). Only :meth:`switch_to_wifi`'s verify loop can
        establish that the link actually came up.

        Raises
        ------
        ValueError
            If ``confirm`` is not True, or ``ssid`` is empty.
        FranklinWHError
            If the aGate has no stored access-point identity to echo.
        """
        if not confirm:
            raise ValueError(
                "set_wifi_credentials() changes the network configuration of "
                "physical hardware and can strand the gateway. Pass confirm=True."
            )
        if not ssid:
            raise ValueError("ssid must be a non-empty string")

        # Read fresh: ap_SSID/ap_Pw are required in the write and a 300 s-stale
        # copy is not something to echo back into a config write.
        self._invalidate_network_cache()
        cfg = await self.get_wifi_config()

        ap_ssid = cfg.get("ap_ssid")
        ap_pw = cfg.get("ap_password")
        if not ap_ssid:
            raise FranklinWHError(
                "aGate returned no ap_SSID; refusing to write a 337 payload "
                "without echoing back its own access-point identity"
            )

        # Shape validated on live hardware 2026-08-09 (U2,
        # tests/results/2026-08-09_U2-REAPPLY-WIFI_pass.txt) and matching the
        # mobile app verbatim. ap_SSID/ap_Pw are the aGate's OWN access point,
        # not the target network — they must be echoed back unchanged
        # (design section 2.3b-1).
        dataArea = {
            "opt": 1,
            "wifi_SSID": ssid,
            "wifi_Pw": password or "",
            "ap_SSID": ap_ssid,
            "ap_Pw": ap_pw,
        }
        logger.info(
            "set_wifi_credentials: writing 337 opt=1 for SSID %s (password withheld)",
            _redact(ssid),
        )
        wire_payload = self._build_payload(MqttCmd.WIFI_CONFIG, dataArea)  # cmdType 337
        raw = (await self._mqtt_send(wire_payload))["result"]["dataArea"]
        ack = json.loads(raw) if isinstance(raw, str) else (raw or {})

        # The config we just changed is now stale in cache, and the verify loop
        # is about to read it (gotcha G6).
        self._invalidate_network_cache()

        return {
            "cmd": 338,
            "result": ack.get("result"),
            "reason": ack.get("reason"),
            # "accepted", deliberately not "connected" — see the warning above.
            "accepted": ack.get("result") == 0,
        }
