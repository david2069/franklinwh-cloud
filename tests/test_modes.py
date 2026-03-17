"""Tests for operating modes, run statuses, and mode constants.

Tests the const/modes.py data structures and validation.
"""

import pytest

from franklinwh_cloud.const import OPERATING_MODES, RUN_STATUS
from franklinwh_cloud.const.modes import (
    MODE_TIME_OF_USE,
    MODE_SELF_CONSUMPTION,
    MODE_EMERGENCY_BACKUP,
    MODE_MAP,
    workModeType,
)


class TestModeMap:
    """MODE_MAP: int → string mode name."""

    def test_has_all_three_modes(self):
        assert 1 in MODE_MAP
        assert 2 in MODE_MAP
        assert 3 in MODE_MAP

    def test_mode_map_values(self):
        assert MODE_MAP[1] == MODE_TIME_OF_USE
        assert MODE_MAP[2] == MODE_SELF_CONSUMPTION
        assert MODE_MAP[3] == MODE_EMERGENCY_BACKUP

    def test_mode_constants(self):
        assert MODE_TIME_OF_USE == "time_of_use"
        assert MODE_SELF_CONSUMPTION == "self_consumption"
        assert MODE_EMERGENCY_BACKUP == "emergency_backup"


class TestOperatingModes:
    """OPERATING_MODES: bidirectional int ↔ string lookup."""

    def test_int_to_string(self):
        assert OPERATING_MODES[1] == "Time of Use"
        assert OPERATING_MODES[2] == "Self-Consumption"
        assert OPERATING_MODES[3] == "Emergency Backup"

    def test_string_to_int(self):
        assert OPERATING_MODES["Time of Use"] == 1
        assert OPERATING_MODES["Self-Consumption"] == 2
        assert OPERATING_MODES["Emergency Backup"] == 3

    def test_snake_case_to_int(self):
        """snake_case strings also map to mode ints."""
        assert OPERATING_MODES["time_of_use"] == 1
        assert OPERATING_MODES["self_consumption"] == 2
        assert OPERATING_MODES["emergency_backup"] == 3

    def test_bidirectional_consistency(self):
        """Every int→str has a corresponding str→int entry."""
        for key in [1, 2, 3]:
            name = OPERATING_MODES[key]
            assert OPERATING_MODES[name] == key


class TestWorkModeType:
    """workModeType enum."""

    def test_enum_values(self):
        assert workModeType.TIME_OF_USE.value == 1
        assert workModeType.SELF_CONSUMPTION.value == 2
        assert workModeType.EMERGENCY_BACKUP.value == 3


class TestRunStatus:
    """RUN_STATUS map for runtime states."""

    def test_has_expected_statuses(self):
        assert RUN_STATUS[0] == "Standby"
        assert RUN_STATUS[1] == "Charging"
        assert RUN_STATUS[2] == "Discharging"

    def test_all_keys_are_ints(self):
        assert all(isinstance(k, int) for k in RUN_STATUS)

    def test_all_values_are_strings(self):
        assert all(isinstance(v, str) for v in RUN_STATUS.values())

    def test_has_off_grid_variants(self):
        assert RUN_STATUS[5] == "Off-Grid Standby"
        assert RUN_STATUS[6] == "Off-Grid Charging"
        assert RUN_STATUS[7] == "Off-Grid Discharging"
