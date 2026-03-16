"""Tests for GridStatus enum — mapping, bounds, and edge cases."""

import pytest

from franklinwh.client import GridStatus


class TestGridStatusEnum:
    """GridStatus enum values and membership."""

    def test_normal_is_zero(self):
        assert GridStatus.NORMAL.value == 0

    def test_down_is_one(self):
        assert GridStatus.DOWN.value == 1

    def test_off_is_two(self):
        assert GridStatus.OFF.value == 2

    def test_all_values(self):
        """Enum has exactly 3 members."""
        assert len(GridStatus) == 3


class TestGridStatusMapping:
    """Offgrid reason → GridStatus mapping (fork's inline logic)."""

    def test_zero_reason_is_normal(self):
        """offgridreason=0 → NORMAL (no issue)."""
        reason_val = 0
        if reason_val > 0:
            status = GridStatus(min(2, int(reason_val)))
        else:
            status = GridStatus.NORMAL
        assert status == GridStatus.NORMAL

    def test_reason_one_is_down(self):
        """offgridreason=1 → DOWN."""
        reason_val = 1
        status = GridStatus(min(2, int(reason_val)))
        assert status == GridStatus.DOWN

    def test_reason_two_is_off(self):
        """offgridreason=2 → OFF."""
        reason_val = 2
        status = GridStatus(min(2, int(reason_val)))
        assert status == GridStatus.OFF

    def test_large_reason_capped_at_off(self):
        """offgridreason > 2 should be capped at OFF (2)."""
        reason_val = 99
        status = GridStatus(min(2, int(reason_val)))
        assert status == GridStatus.OFF

    def test_none_reason_treated_as_normal(self):
        """None offgridreason → NORMAL (fork's null-safe handling)."""
        offgridreason = None
        reason_val = int(offgridreason) if offgridreason is not None else 0
        if reason_val > 0:
            status = GridStatus(min(2, int(reason_val)))
        else:
            status = GridStatus.NORMAL
        assert status == GridStatus.NORMAL
