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

from franklinwh_cloud.const.devices import UNASSIGNED_IPS
from franklinwh_cloud.exceptions import (
    DeviceTimeoutException,
    FranklinWHError,
    GatewayOfflineException,
)
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
# ── local reachability probe ─────────────────────────────────────────

#: The aGate's local broker protocol, the "Direct Connection" the mobile app
#: uses over the gateway's own hotspot. Verified against franklinwh-local
#: (``franklinwh_local/transport.py`` ``DEFAULT_PORT``). It also answers on the
#: LAN address on the firmware observed here. Preferred probe target because it
#: proves the APPLICATION is up, and because it is a product feature FranklinWH
#: has reason to keep.
LOCAL_API_PORT = 9000

#: Fallback only. SSH answering proves the box booted, not that the API works,
#: and it is incidental rather than a feature — a hardening release could close
#: it, at which point anything depending on it reports a healthy gateway dead.
LOCAL_SSH_PORT = 22

#: Probed for information only, never for liveness: Modbus listens only when
#: explicitly enabled, so a closed port is evidence of nothing.
LOCAL_MODBUS_PORT = 502


async def probe_tcp(host, port, timeout_s=1.5):
    """Return True if a TCP connect to ``host:port`` succeeds.

    Runs the blocking connect off the event loop. The pre-existing probe in
    ``get_connectivity_overview``'s deep scan blocks it for up to 1.5 s.
    """
    import socket

    def _connect():
        try:
            with socket.create_connection((host, port), timeout=timeout_s):
                return True
        except OSError:
            return False

    try:
        return await asyncio.to_thread(_connect)
    except Exception:  # pragma: no cover - defensive
        return False


async def probe_local_reachability(host, *, timeout_s=1.5):
    """Is the aGate answering on the LAN, and on which port?

    A **discriminator, not a verdict.** Local reachability proves the gateway
    is powered, on the network and holding an address. It proves nothing about
    whether it can reach FranklinWH — a gateway with a dead WAN, broken DNS or
    an expired certificate answers these ports perfectly while being exactly as
    disconnected as one that is switched off.

    Its value is in combination with cloud round-trip success:

    ==========  ==========  ==================================================
    local       cloud       meaning
    ==========  ==========  ==================================================
    yes         yes         healthy
    yes         no          gateway alive, WAN or cloud path broken
    no          yes         the caller is not on the gateway's LAN
    no          no          gateway down, or caller off-network entirely
    ==========  ==========  ==================================================

    Only meaningful from the same LAN, so a negative result is never by itself
    evidence of a fault, and this must never gate a write.

    Returns ``{"probed", "reachable", "port", "host"}``. ``reachable`` is None
    when there was no address to probe — which is the case mid-reassociation,
    exactly when it would be most wanted.
    """
    if not host or host in UNASSIGNED_IPS:
        return {"probed": False, "reachable": None, "port": None, "host": None}

    for port in (LOCAL_API_PORT, LOCAL_SSH_PORT):
        if await probe_tcp(host, port, timeout_s=timeout_s):
            return {"probed": True, "reachable": True, "port": port,
                    "host": host}
    return {"probed": True, "reachable": False, "port": None, "host": host}


# ── P2-2 preflight ───────────────────────────────────────────────────

#: Minimum target signal percentage accepted by default. Working links are
#: observed at 68-100 across the HAR corpus; 8-28 are noise-floor neighbours.
DEFAULT_MIN_RSSI = 30


#: Interfaces whose presence on the LAN does not prove a path to the cloud.
#: At least one aGate Ethernet port is reserved for FranklinWH-internal use and
#: sits on a segment with no internet route, and the API exposes nothing that
#: distinguishes it from a user port. See :func:`network_write_preflight`.
UNVERIFIED_FALLBACK_KEYS = ("eth0", "eth1")


def network_write_preflight(
    state,
    target,
    *,
    ssid=None,
    scan=None,
    min_rssi=DEFAULT_MIN_RSSI,
    allow_no_fallback=False,
    allow_weak_signal=False,
    trust_ethernet=False,
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

    # An Ethernet port that is not currently carrying traffic cannot be shown
    # to reach the cloud. One aGate port is reserved for FranklinWH-internal
    # use on a segment with no internet route, and nothing in the API says
    # which. A port that is *active* is proven — the gateway is answering
    # through it right now. A port that merely holds an address is not.
    #
    # The asymmetry decides the default: trusting a bad fallback strands the
    # gateway and recovery becomes physical, while distrusting a good one costs
    # a refusal the caller can override. So unverified Ethernet does not count.
    active_key = (state.get("active") or {}).get("key")
    unverified = sorted(
        k for k in fallbacks
        if k in UNVERIFIED_FALLBACK_KEYS and k != active_key
    )
    if unverified and not trust_ethernet:
        fallbacks = [k for k in fallbacks if k not in unverified]
    elif unverified:
        overrides.append(
            f"trust_ethernet: counting {', '.join(unverified)} as a fallback "
            f"without proof it reaches the cloud"
        )

    if not fallbacks:
        msg = (
            f"no transport other than {target!r} could carry traffic if this "
            f"write fails (available={sorted(available) or 'none'})"
        )
        if unverified and not trust_ethernet:
            msg += (
                f"; {', '.join(unverified)} holds an address but is not the "
                f"active transport, so it is not proven to reach the cloud — "
                f"one aGate Ethernet port is reserved for FranklinWH-internal "
                f"use. Pass trust_ethernet=True if you know it is a real path."
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
        "unverified_fallbacks": unverified,
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

    async def _verify_wifi_switch(
        self,
        ssid,
        *,
        timeout_s=180,
        poll_interval_s=5.0,
        required_stable=2,
        before=None,
    ):
        """Poll until the aGate is demonstrably on ``ssid``, or give up.

        Implements design section 4. Returns the ``verification`` block of the
        section 5.3 contract. Read-only — it never writes, and in particular it
        **never retries the 337 write**: retrying against a gateway that is
        mid-reassociation is how a slow switch becomes a dead one.

        Success requires all three of these, on ``required_stable`` consecutive
        polls:

        1. ``currentNetType == 3`` (WiFi).
        2. A real address — ``wifi.ip`` not in ``UNASSIGNED_IPS``. On 2026-03-21
           and again on 2026-08-08 the aGate sat *associated* at ~76% holding
           0.0.0.0 with no working path. Association is not connectivity.
        3. The SSID actually in use matches the one requested. ``currentNetType``
           alone proves nothing: the aGate roams unprompted, and 17 of 19
           observed transport changes followed no command at all (gotcha G9).

        The debounce exists because reassociation transiently dips through
        another transport — 3 to 4 and back to 3 within five seconds was
        observed directly. A verifier that latches on the first reading reports
        the wrong answer in either direction.

        Unreachable polls are **expected, not failures**. The gateway genuinely
        disappears mid-cutover (gotcha G8), and the cloud sits behind CloudFront,
        which serves HTML error pages for 502/503/504 that killed a 60-minute
        poll on its second iteration (G10). They are counted and reported.

        Note
        ----
        Success is never gated on ``awsStatus``/``netStatus``. On 2026-08-08 the
        aGate was on WiFi with a valid lease, answering MQTT *through the cloud*,
        while cmdType 339 reported ``netStatus=0, awsStatus=0, routerStatus=0``.
        Those flags contradict observable reality (design section 2.5a).
        """
        start = time.monotonic()
        deadline = start + timeout_s
        # Bound by poll count as well as wall clock: a clock that fails to
        # advance must not turn this into an unbounded loop against hardware.
        max_polls = int(timeout_s / poll_interval_s) + 2

        polls = 0
        unreachable = 0
        stable = 0
        last_known = None

        while time.monotonic() < deadline and polls < max_polls:
            await asyncio.sleep(poll_interval_s)  # 5 s — the app's own cadence
            polls += 1

            try:
                # Invalidate first: a poll that reads a 120 s-cached answer is
                # not a verification at all (defect 6).
                self._invalidate_network_cache()
                net = await self.get_network_info()
            except (DeviceTimeoutException, GatewayOfflineException, FranklinWHError):
                unreachable += 1
                stable = 0
                logger.debug(
                    "verify: poll %d unreachable (expected during cut-over)", polls
                )
                continue

            wifi = net.get("wifi") or {}
            ip = wifi.get("ip")
            last_known = {
                "type_id": net.get("currentNetType"),
                "ip": ip if ip not in UNASSIGNED_IPS else None,
            }

            if net.get("currentNetType") != 3 or ip in UNASSIGNED_IPS:
                stable = 0
                continue

            # Only now is the extra 337 read worth its sendMqtt budget.
            try:
                cfg = await self.get_wifi_config()
            except (DeviceTimeoutException, GatewayOfflineException, FranklinWHError):
                unreachable += 1
                stable = 0
                continue

            if cfg.get("wifi_ssid") != ssid:
                # On WiFi, but not the network that was asked for — the aGate
                # roamed for unrelated reasons.
                stable = 0
                continue

            stable += 1
            if stable >= required_stable:
                cloud = {}
                try:
                    conn = await self.get_connection_status()
                    cloud = {
                        "aws_status_raw": conn.get("awsStatus"),
                        "net_status_raw": conn.get("netStatus"),
                    }
                except (DeviceTimeoutException, GatewayOfflineException,
                        FranklinWHError):
                    pass  # best-effort only; never gates success

                return {
                    "state": "connected",
                    "elapsed_s": round(time.monotonic() - start, 1),
                    "polls": polls,
                    "unreachable_polls": unreachable,
                    "before": before,
                    "after": {"type_id": 3, "type": "wifi", "ip": ip},
                    "cloud": cloud,
                }

        return {
            "state": "timeout",
            "elapsed_s": round(time.monotonic() - start, 1),
            "polls": polls,
            "unreachable_polls": unreachable,
            "before": before,
            "last_known": last_known,
            "recovery_hint": (
                "The write was accepted but the link was not confirmed within "
                f"{timeout_s}s. The write has NOT been retried, deliberately. "
                "The aGate falls back to 4G on its own; check "
                "'fwh network status' before changing anything else. If it is "
                "unreachable, recovery is via the aGate's own AP "
                "(tools/network_probe.py recover)."
            ),
        }

    async def switch_to_wifi(
        self,
        ssid,
        password=None,
        *,
        confirm=False,
        verify=True,
        scan=True,
        timeout_s=180,
        poll_interval_s=5.0,
        min_rssi=DEFAULT_MIN_RSSI,
        allow_no_fallback=False,
        allow_weak_signal=False,
        trust_ethernet=False,
    ):
        """Put the aGate onto ``ssid`` and confirm it actually landed there.

        The SDK equivalent of the vendor app's WiFi Configuration wizard:
        scan, preflight, write, verify. Design sections 3-5; the returned dict
        is the section 5.3 contract.

        The problem this solves: the aGate always falls back to 4G when local
        connectivity drops, but does not reliably come back to WiFi, so it
        strands itself on cellular. Recovering from that has until now required
        the vendor app (``docs/troubleshooting/2026-03-21_wifi_dhcp_failure.md``).

        Parameters
        ----------
        ssid : str
            Network to join.
        password : str, optional
            Passphrase. ``None`` reuses the password already stored on the
            aGate, which is permitted **only** when ``ssid`` matches the stored
            SSID — cmdType 337 returns a plaintext password for the currently
            stored network only, and there is no per-SSID credential lookup
            anywhere in the API. That restriction is not a limitation in
            practice: the common case is a gateway stranded on 4G that needs
            putting back on the WiFi it already knows, which needs no password
            at all.
        confirm : bool
            Must be True — this writes to physical hardware.
        verify : bool
            Poll until the link is confirmed (default True). With False the
            result carries ``verification.state == "skipped"``.
        scan : bool
            Run a scan first so the preflight can check the target's signal
            (default True). Without it the signal gate is skipped as unknown.
        min_rssi, allow_no_fallback, allow_weak_signal
            Passed to :func:`network_write_preflight`.
        timeout_s, poll_interval_s
            Passed to the verify loop.

        Returns
        -------
        dict
            ``{requested, preflight, write_ack, verification}`` per section 5.3.

        Important
        ---------
        **A refused preflight is returned, not raised.** Check
        ``result["preflight"]["passed"]`` — on refusal no write is sent,
        ``write_ack`` is None and ``verification.state`` is ``"skipped"``.
        The refusal carries ``reasons``, which a caller needs in order to
        decide whether an override is appropriate. A verify timeout likewise
        comes back as ``verification.state == "timeout"``; the write was
        accepted but the link was not confirmed, and it is deliberately not
        retried.

        Raises
        ------
        ValueError
            If ``confirm`` is not True, or ``password`` is None for an SSID
            other than the one currently stored.
        """
        if not confirm:
            raise ValueError(
                "switch_to_wifi() changes the network configuration of physical "
                "hardware and can strand the gateway. Pass confirm=True."
            )

        # 1. Resolve the password. The cloud is not a credential vault.
        password_source = "user"
        if password is None:
            self._invalidate_network_cache()
            stored = await self.get_wifi_config()
            if stored.get("wifi_ssid") != ssid:
                raise ValueError(
                    f"no password given for SSID {_redact(ssid)}, and it is not "
                    f"the network currently stored on the aGate. cmdType 337 "
                    f"returns a password only for the stored network, so there "
                    f"is nothing to reuse. Supply password= explicitly."
                )
            password = stored.get("wifi_password") or ""
            password_source = "stored"

        # 2. Snapshot before, for the caller's before/after.
        state = await self.get_network_state()
        active = state.get("active") or {}
        before = {
            "type_id": active.get("id"),
            "type": active.get("key"),
            "ip": active.get("ip"),
        }

        # 3. Scan, so the preflight can judge the target's signal.
        scan_result = None
        if scan:
            try:
                scan_result = await self.scan_wifi_networks_ranked()
            except (DeviceTimeoutException, GatewayOfflineException, FranklinWHError) as e:
                # Unknown signal is not the same as bad signal; the fallback
                # gate still applies and is the one that protects the gateway.
                logger.warning("switch_to_wifi: scan failed (%s); signal gate skipped", e)

        # 4. Preflight. The target is the WiFi interface, and the fallback set
        #    is computed relative to it — not to whatever is active now.
        preflight = network_write_preflight(
            state, "wifi",
            ssid=ssid, scan=scan_result, min_rssi=min_rssi,
            allow_no_fallback=allow_no_fallback,
            allow_weak_signal=allow_weak_signal,
            trust_ethernet=trust_ethernet,
        )
        requested = {"ssid": ssid, "password_source": password_source}

        if not preflight["passed"]:
            logger.warning(
                "switch_to_wifi: preflight refused: %s", "; ".join(preflight["reasons"])
            )
            return {
                "requested": requested,
                "preflight": preflight,
                "write_ack": None,
                "verification": {"state": "skipped", "reason": "preflight refused"},
            }

        # 5. The write.
        ack = await self.set_wifi_credentials(ssid, password, confirm=True)

        if not verify:
            return {
                "requested": requested,
                "preflight": preflight,
                "write_ack": ack,
                # "accepted" is not "connected" (G7) — say so rather than
                # letting a caller read skipped verification as success.
                "verification": {"state": "skipped", "reason": "verify=False"},
            }

        verification = await self._verify_wifi_switch(
            ssid,
            timeout_s=timeout_s,
            poll_interval_s=poll_interval_s,
            before=before,
        )
        return {
            "requested": requested,
            "preflight": preflight,
            "write_ack": ack,
            "verification": verification,
        }
