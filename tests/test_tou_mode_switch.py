"""DEF-TOU-SAVE-NO-LONGER-SWITCHES-MODE.

`saveTouDispatch` used to save a schedule AND switch the system to TOU mode.
CONFIRMED for the capture window: 38 distinct saves spanning app 2.3.1 to
2.11.0 (2025-03 to 2026-03), none followed by `updateTouModeV2` — the backend
did it. The corpus ends 2026-03-20.

OBSERVED ~2026-06 (user report, current firmware): it no longer does. The app
saves, reports success, and offers the switch as a separate step, calling the
ordinary mode endpoint only if accepted.

Consequence: a caller who saves a schedule expecting it to take effect gets a
stored, idle schedule and no error.
"""

import inspect

import pytest


def _tou_mixin_src():
    from franklinwh_cloud.mixins import tou

    return inspect.getsource(tou)


# ── the claim that is no longer true ─────────────────────────────────

def test_the_unconditional_auto_switch_claim_is_gone():
    """It was asserted twice as plain fact, with no version qualifier."""
    src = _tou_mixin_src()
    assert "AND switches the system to TOU mode" not in src
    assert "always forces a TOU mode switch" not in src


def test_the_claim_is_replaced_by_a_dated_one():
    """AP-14: version-dependent behaviour must carry its evidence window."""
    src = _tou_mixin_src()
    assert "2.11.0" in src, "the confirmed window must be stated"
    assert "CONFIRMED" in src and "OBSERVED" in src


def test_callers_are_told_to_set_the_mode_themselves():
    src = _tou_mixin_src()
    assert 'set_mode("Time of Use")' in src


def test_the_destructive_overwrite_warning_survives():
    """That part is unchanged and still matters."""
    src = _tou_mixin_src()
    assert "destructive" in src
    assert "update data only" in src


# ── the CLI no longer calls the normal case a failure ────────────────

def _cli_src():
    from franklinwh_cloud.cli_commands import tou

    return inspect.getsource(tou)


def test_cli_does_not_frame_a_non_tou_mode_as_unexpected():
    src = _cli_src()
    assert "(expected 1=TOU)" not in src, (
        "a non-TOU mode after saving is now normal, not an anomaly"
    )


def test_cli_still_reports_the_save_succeeded():
    """The save DID work; only the activation did not happen."""
    src = _cli_src()
    assert "Schedule saved" in src


def test_cli_tells_the_user_how_to_activate():
    src = _cli_src()
    assert "fwh mode --set tou" in src


def test_cli_does_not_block_waiting_for_a_mode_change():
    """It returns on touSendStatus; waiting on workMode would now hang."""
    src = _cli_src()
    body = src[src.index("async def _wait_for_dispatch"):]
    body = body[:body.index("\nasync def ", 1)] if "\nasync def " in body[1:] else body
    assert "if confirmed:" in body
    assert "while tou_active" not in body


def test_the_two_step_pattern_is_reachable():
    """set_mode is the endpoint the app itself now uses for the switch."""
    from franklinwh_cloud.client import Client

    assert hasattr(Client, "set_tou_schedule")
    assert hasattr(Client, "set_mode")
