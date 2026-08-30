"""Gateway cloud-contact heartbeat.

FEAT-CLOUD-UPTIME-HEARTBEAT. Warranty and support terms require the aGate to
hold cloud connectivity, so sustained loss needs flagging.

Why not the gateway's own flags
-------------------------------
``awsStatus`` is a self-report and cannot do this job: cmdType 339 has been
observed reporting all three connectivity flags as zero while the gateway was
answering MQTT *through the very cloud it claimed was down*
(``docs/NETWORK_CONNECTIVITY_DESIGN.md`` section 2.5a). An alert built on it
fires constantly on a healthy system, which trains the reader to ignore it.

What this measures instead
--------------------------
Whether a **gateway round trip** succeeded. Every ``sendMqtt`` goes through one
chokepoint, and a response to one proves the gateway is talking to the cloud —
no flag needed. When it is not, the cloud says so authoritatively with code 136
"Current gateway offline".

The distinction matters: a REST call succeeding proves only that *we* reached
the cloud, not that the **gateway** did. So only gateway round trips count.

Why two timestamps
------------------
``last_success`` alone cannot tell "the gateway is down" from "nothing has run
since Tuesday". Downtime is ``last_attempt`` recent **and** ``last_success``
old. Recording both is what makes the difference observable at all.

Thresholds live in the consumer
-------------------------------
This exposes ``offline_for_s`` and stops. Home Assistant already polls
continuously and is the natural monitor; a daemon inside an SDK would be the
wrong shape and would give two monitors that can disagree.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("franklinwh_cloud")

#: Minimum seconds between disk writes. State is always current in memory; the
#: file exists to survive process restarts, and Home Assistant polling every
#: 30 s should not mean a write per poll.
DEFAULT_FLUSH_INTERVAL_S = 30.0


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class GatewayHeartbeat:
    """Tracks when a gateway last completed a cloud round trip.

    Parameters
    ----------
    gateway_id : str
        Scopes the state file, so several gateways in one process do not
        overwrite each other.
    state_dir : str | Path | None
        Directory for the state file. ``None`` keeps everything in memory,
        which is what unit tests want.
    flush_interval_s : float
        Rate limit for disk writes.
    """

    def __init__(self, gateway_id, state_dir=None, flush_interval_s=DEFAULT_FLUSH_INTERVAL_S):
        self.gateway_id = gateway_id
        self.flush_interval_s = flush_interval_s
        self._path = None
        if state_dir:
            self._path = Path(state_dir) / f"{gateway_id}.json"

        self.last_success = None      # ISO 8601, or None if never seen
        self.last_attempt = None
        self.last_outcome = None      # "success" | "failure" | None
        self.consecutive_failures = 0
        self._last_success_monotonic = None
        self._last_flush = 0.0

        self._load()

    # ── persistence ──────────────────────────────────────────────────

    def _load(self):
        """Restore prior state. A corrupt or missing file is not an error."""
        if not self._path or not self._path.is_file():
            return
        try:
            data = json.loads(self._path.read_text())
        except (OSError, ValueError) as e:
            logger.debug("heartbeat: ignoring unreadable state file (%s)", e)
            return
        self.last_success = data.get("last_success")
        self.last_attempt = data.get("last_attempt")
        self.last_outcome = data.get("last_outcome")
        self.consecutive_failures = data.get("consecutive_failures", 0) or 0

    def _flush(self, force=False):
        if not self._path:
            return
        now = time.monotonic()
        if not force and (now - self._last_flush) < self.flush_interval_s:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            # Write-then-replace, so a crash mid-write cannot leave a truncated
            # file that reads as "never contacted".
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps({
                "gateway_id": self.gateway_id,
                "last_success": self.last_success,
                "last_attempt": self.last_attempt,
                "last_outcome": self.last_outcome,
                "consecutive_failures": self.consecutive_failures,
            }, indent=2))
            os.replace(tmp, self._path)
            self._last_flush = now
        except OSError as e:
            # Never let telemetry break a working API call.
            logger.debug("heartbeat: could not persist state (%s)", e)

    # ── recording ────────────────────────────────────────────────────

    def record_success(self):
        """A gateway round trip completed."""
        self.last_attempt = self.last_success = _now_iso()
        self._last_success_monotonic = time.monotonic()
        self.last_outcome = "success"
        recovered = self.consecutive_failures > 0
        self.consecutive_failures = 0
        # Force the write on recovery: the transition from down to up is the
        # event a reader most needs to have survived a restart.
        self._flush(force=recovered)

    def record_failure(self):
        """A gateway round trip failed."""
        self.last_attempt = _now_iso()
        self.last_outcome = "failure"
        self.consecutive_failures += 1
        # Force on the first failure so the onset time is not lost to the
        # flush interval.
        self._flush(force=self.consecutive_failures == 1)

    # ── reporting ────────────────────────────────────────────────────

    def snapshot(self):
        """Current state.

        ``offline_for_s`` is populated **only when the most recent attempt
        failed**. If the last attempt succeeded the gateway is reachable and
        the value is 0. It is None when the outcome is unknown, or when a
        failure has been seen but there is no prior success to measure from —
        "down for an unknown period" must not be reported as "down for 0
        seconds".
        """
        offline_for_s = None
        if self.last_outcome == "success":
            offline_for_s = 0.0
        elif self.last_outcome == "failure" and self.last_success:
            try:
                since = datetime.fromisoformat(self.last_success)
                offline_for_s = round(
                    (datetime.now(timezone.utc) - since).total_seconds(), 1
                )
            except ValueError:
                offline_for_s = None

        return {
            "gateway_id": self.gateway_id,
            "last_success": self.last_success,
            "last_attempt": self.last_attempt,
            "last_outcome": self.last_outcome,
            "consecutive_failures": self.consecutive_failures,
            "offline_for_s": offline_for_s,
            "persisted": self._path is not None,
        }

    def close(self):
        """Flush unconditionally, e.g. at process shutdown."""
        self._flush(force=True)
