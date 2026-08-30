"""FEAT-CLOUD-UPTIME-HEARTBEAT — gateway cloud-contact tracking.

Warranty terms require the aGate to hold cloud connectivity, so sustained loss
needs flagging. The gateway's own awsStatus cannot do that job: it has been
observed reading zero while the gateway answered through the cloud. What this
measures instead is whether GATEWAY round trips succeed.
"""

import json

import pytest

from franklinwh_cloud.heartbeat import GatewayHeartbeat


# ── the two-timestamp design ─────────────────────────────────────────

def test_a_fresh_heartbeat_reports_nothing_known():
    """Never contacted is not the same as down."""
    snap = GatewayHeartbeat("gw", None).snapshot()
    assert snap["last_success"] is None
    assert snap["last_outcome"] is None
    assert snap["offline_for_s"] is None, "unknown must not read as 0s of downtime"


def test_success_marks_the_gateway_reachable():
    hb = GatewayHeartbeat("gw", None)
    hb.record_success()
    snap = hb.snapshot()

    assert snap["last_outcome"] == "success"
    assert snap["offline_for_s"] == 0.0
    assert snap["last_success"] == snap["last_attempt"]


def test_failure_after_a_success_measures_from_the_success():
    hb = GatewayHeartbeat("gw", None)
    hb.record_success()
    hb.record_failure()
    snap = hb.snapshot()

    assert snap["last_outcome"] == "failure"
    assert snap["offline_for_s"] is not None
    assert snap["offline_for_s"] >= 0


def test_a_failure_does_not_advance_last_success():
    """The invariant behind the two-timestamp design.

    Downtime is 'last_attempt recent AND last_success old', so a failure must
    move only the former. Asserted structurally rather than by comparing the
    two strings: timestamps are second-resolution, so a success and an
    immediate failure legitimately land in the same second.
    """
    hb = GatewayHeartbeat("gw", None)
    hb.record_success()
    first_success = hb.snapshot()["last_success"]

    for _ in range(3):
        hb.record_failure()

    assert hb.snapshot()["last_success"] == first_success


def test_failure_with_no_prior_success_reports_unknown_not_zero():
    """'Down for an unknown period' must not render as 'down for 0 seconds'."""
    hb = GatewayHeartbeat("gw", None)
    hb.record_failure()
    assert hb.snapshot()["offline_for_s"] is None


def test_recovery_clears_the_outage():
    hb = GatewayHeartbeat("gw", None)
    hb.record_success()
    hb.record_failure()
    hb.record_failure()
    assert hb.snapshot()["consecutive_failures"] == 2

    hb.record_success()
    snap = hb.snapshot()
    assert snap["consecutive_failures"] == 0
    assert snap["offline_for_s"] == 0.0


def test_consecutive_failures_accumulate():
    hb = GatewayHeartbeat("gw", None)
    for _ in range(3):
        hb.record_failure()
    assert hb.snapshot()["consecutive_failures"] == 3


# ── persistence: surviving a restart is the whole point ──────────────

def test_state_survives_a_restart(tmp_path):
    hb = GatewayHeartbeat("gw", tmp_path)
    hb.record_success()
    hb.record_failure()

    revived = GatewayHeartbeat("gw", tmp_path)
    snap = revived.snapshot()
    assert snap["last_outcome"] == "failure"
    assert snap["consecutive_failures"] == 1
    assert snap["offline_for_s"] is not None, "outage onset must survive"


def test_the_first_failure_is_flushed_immediately(tmp_path):
    """Onset must not be lost to the flush interval."""
    hb = GatewayHeartbeat("gw", tmp_path, flush_interval_s=9999)
    hb.record_failure()
    assert (tmp_path / "gw.json").is_file()


def test_recovery_is_flushed_immediately(tmp_path):
    """Down-to-up is the transition a reader most needs to survive a restart."""
    hb = GatewayHeartbeat("gw", tmp_path, flush_interval_s=9999)
    hb.record_failure()
    hb.record_success()

    revived = GatewayHeartbeat("gw", tmp_path)
    assert revived.snapshot()["last_outcome"] == "success"


def test_repeat_successes_are_rate_limited(tmp_path):
    """HA polling every 30s must not mean a disk write per poll.

    The FIRST success does write, deliberately: a short-lived CLI process that
    succeeds must still record it, or last_success would never advance for
    anyone not running a long-lived poller. What is rate-limited is the
    repeats.
    """
    hb = GatewayHeartbeat("gw", tmp_path, flush_interval_s=9999)
    hb.record_success()
    first = (tmp_path / "gw.json").stat().st_mtime_ns
    stored = (tmp_path / "gw.json").read_text()

    for _ in range(50):
        hb.record_success()

    assert (tmp_path / "gw.json").stat().st_mtime_ns == first
    assert (tmp_path / "gw.json").read_text() == stored


def test_gateways_do_not_overwrite_each_other(tmp_path):
    GatewayHeartbeat("gw-a", tmp_path).record_failure()
    GatewayHeartbeat("gw-b", tmp_path).record_failure()
    assert (tmp_path / "gw-a.json").is_file()
    assert (tmp_path / "gw-b.json").is_file()


def test_a_corrupt_state_file_is_ignored_not_fatal(tmp_path):
    (tmp_path / "gw.json").write_text("{ this is not json")
    snap = GatewayHeartbeat("gw", tmp_path).snapshot()
    assert snap["last_success"] is None


def test_an_unwritable_directory_does_not_break_the_api_call(tmp_path):
    """Telemetry must never take down a working call."""
    target = tmp_path / "nope"
    target.write_text("I am a file, not a directory")
    hb = GatewayHeartbeat("gw", target)
    hb.record_failure()   # must not raise
    assert hb.snapshot()["consecutive_failures"] == 1


def test_in_memory_mode_writes_nothing(tmp_path):
    hb = GatewayHeartbeat("gw", None)
    hb.record_failure()
    hb.close()
    assert list(tmp_path.iterdir()) == []
    assert hb.snapshot()["persisted"] is False


def test_close_flushes_unconditionally(tmp_path):
    hb = GatewayHeartbeat("gw", tmp_path, flush_interval_s=9999)
    hb.record_success()
    hb.close()
    data = json.loads((tmp_path / "gw.json").read_text())
    assert data["last_outcome"] == "success"


# ── client wiring ────────────────────────────────────────────────────

async def test_mqtt_success_records_a_heartbeat():
    from tests.test_mqtt_send_errors import _client

    c = _client({"code": 200, "result": {}})
    await c._mqtt_send("wire")
    assert c._heartbeat.snapshot()["last_outcome"] == "success"


@pytest.mark.parametrize("code", [102, 136, 400])
async def test_mqtt_failure_records_a_heartbeat(code):
    """Gateway offline (136) is the authoritative outage signal."""
    from tests.test_mqtt_send_errors import _client

    c = _client({"code": code, "message": "nope"})
    with pytest.raises(Exception):
        await c._mqtt_send("wire")
    assert c._heartbeat.snapshot()["last_outcome"] == "failure"


def test_client_exposes_the_getter():
    from franklinwh_cloud.client import Client

    assert hasattr(Client, "get_gateway_heartbeat")


def test_constructing_a_client_writes_nothing(tmp_path):
    """No surprise disk activity just from building a Client."""
    from franklinwh_cloud.client import Client

    Client.__new__(Client)  # __init__ needs a fetcher; the point is the dir
    assert list(tmp_path.iterdir()) == []


def test_heartbeat_can_be_disabled():
    hb = GatewayHeartbeat("gw", None)
    assert hb.snapshot()["persisted"] is False


# ── CLI surface ──────────────────────────────────────────────────────

from franklinwh_cloud.cli_commands import network as netcmd
from franklinwh_cloud.cli_commands.network import _fmt_age
from tests.test_cli_network import STATE, _CliClient, _args


class _HbClient(_CliClient):
    def __init__(self, hb, **kw):
        super().__init__(**kw)
        self._hb = hb

    def get_gateway_heartbeat(self):
        return self._hb


@pytest.mark.parametrize("seconds,expected", [
    (0, "0s"), (45, "45s"), (300, "5m"), (7200, "2h"), (259200, "3d"),
    (None, "unknown"),
])
def test_age_formatting(seconds, expected):
    """Warranty questions are asked in hours and days, not seconds."""
    assert _fmt_age(seconds) == expected


async def test_status_shows_the_last_confirmed_contact(capsys):
    hb = {"last_success": "2026-08-30T07:00:00+00:00", "last_attempt": "x",
          "last_outcome": "success", "consecutive_failures": 0,
          "offline_for_s": 0.0, "persisted": True}
    await netcmd.run(_HbClient(hb), _args())
    out = capsys.readouterr().out
    assert "Last contact" in out


async def test_status_escalates_a_sustained_outage(capsys):
    """The state a single reading could never have shown you."""
    hb = {"last_success": "2026-08-28T07:00:00+00:00", "last_attempt": "y",
          "last_outcome": "failure", "consecutive_failures": 91,
          "offline_for_s": 180000.0, "persisted": True}
    await netcmd.run(_HbClient(hb), _args())
    captured = capsys.readouterr()          # one read; a second returns empty
    out = captured.out + captured.err       # print_error writes to stderr

    assert "No cloud contact for 2d" in out
    assert "91 consecutive failures" in out


async def test_status_flags_a_gateway_never_seen(capsys):
    hb = {"last_success": None, "last_attempt": "z", "last_outcome": "failure",
          "consecutive_failures": 3, "offline_for_s": None, "persisted": True}
    await netcmd.run(_HbClient(hb), _args())
    out = capsys.readouterr().out
    assert "No successful gateway contact on record" in out


async def test_status_stays_quiet_with_no_heartbeat_data(capsys):
    """A client built without one must still render."""
    await netcmd.run(_CliClient(), _args())
    out = capsys.readouterr().out
    assert "Last contact" not in out
    assert "No cloud contact" not in out


async def test_status_json_includes_the_heartbeat(capsys):
    hb = {"last_success": "2026-08-30T07:00:00+00:00", "last_attempt": "x",
          "last_outcome": "success", "consecutive_failures": 0,
          "offline_for_s": 0.0, "persisted": True}
    await netcmd.run(_HbClient(hb), _args(json=True))
    payload = json.loads(capsys.readouterr().out)
    assert payload["heartbeat"]["last_success"] == "2026-08-30T07:00:00+00:00"
    assert "available_transports" in payload, "state keys must survive"
