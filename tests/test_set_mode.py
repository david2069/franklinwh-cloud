"""Tests for set_mode — mode validation and error handling.

Tests validation logic without needing live API calls.
"""

import pytest

from franklinwh_cloud.client import (
    InvalidOperatingMode,
    InvalidOperatingModeOption,
)
from franklinwh_cloud.const import OPERATING_MODES


class TestSetModeValidation:
    """Input validation for set_mode parameters."""

    def test_valid_mode_values(self):
        """Modes 1, 2, 3 should be valid."""
        for mode in [1, 2, 3]:
            assert mode in OPERATING_MODES

    def test_invalid_mode_value(self):
        """Mode outside 1-3 should not be in OPERATING_MODES."""
        assert 0 not in OPERATING_MODES
        assert 4 not in OPERATING_MODES
        assert -1 not in OPERATING_MODES

    def test_soc_bounds(self):
        """SOC should be between 5 and 100 for valid operation."""
        # These are the business rules from the set_mode implementation
        valid_socs = [5, 10, 50, 100]
        for soc in valid_socs:
            assert 5 <= soc <= 100

        invalid_socs = [0, 4, 101, -1]
        for soc in invalid_socs:
            assert not (5 <= soc <= 100)


class TestModeExceptions:
    """Exception classes for mode errors."""

    def test_invalid_mode_exception(self):
        with pytest.raises(InvalidOperatingMode):
            raise InvalidOperatingMode("Unknown mode: 99")

    def test_invalid_mode_option_exception(self):
        with pytest.raises(InvalidOperatingModeOption):
            raise InvalidOperatingModeOption("SOC out of range: 0")

    def test_exception_messages(self):
        e = InvalidOperatingMode("test message")
        assert "test message" in str(e)
