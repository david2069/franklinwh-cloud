"""Tests for the const/ package — enums, maps, and TOU fixtures.

Validates WaveType, dispatchCodeType, and the predefined schedule catalog.
"""

import pytest

from franklinwh.const.tou import WaveType, dispatchCodeType
from franklinwh.const.test_fixtures import tou_predefined_builtin


REQUIRED_SCHEDULE_KEYS = {"startHourTime", "endHourTime", "waveType", "name", "dispatchId"}


class TestWaveType:
    """WaveType enum for TOU tariff periods."""

    def test_has_expected_members(self):
        assert hasattr(WaveType, "ON_PEAK")
        assert hasattr(WaveType, "OFF_PEAK")

    def test_values_are_ints(self):
        for member in WaveType:
            assert isinstance(member.value, int)


class TestDispatchCodeType:
    """dispatchCodeType enum for TOU dispatch modes."""

    def test_has_core_modes(self):
        assert hasattr(dispatchCodeType, "SELF_CONSUMPTION")
        assert hasattr(dispatchCodeType, "HOME_LOADS")

    def test_values_are_ints(self):
        for member in dispatchCodeType:
            assert isinstance(member.value, int)


class TestTouPredefinedBuiltin:
    """Predefined TOU schedule catalog from test_fixtures.py."""

    def test_catalog_not_empty(self):
        assert len(tou_predefined_builtin) > 0

    def test_expected_schedules_exist(self):
        expected = [
            "power_home_only",
            "charge_from_solar",
            "charge_from_grid",
            "export_to_grid_always",
            "standby_schedule",
            "gap_schedule",
        ]
        for name in expected:
            assert name in tou_predefined_builtin, f"Missing schedule: {name}"

    def test_all_schedules_have_required_keys(self):
        """Every period in every schedule must have the required keys."""
        for name, periods in tou_predefined_builtin.items():
            assert isinstance(periods, list), f"{name} should be a list"
            assert len(periods) > 0, f"{name} should have at least one period"
            for i, period in enumerate(periods):
                missing = REQUIRED_SCHEDULE_KEYS - set(period.keys())
                assert not missing, f"{name}[{i}] missing keys: {missing}"

    def test_wave_types_are_valid(self):
        """All waveType values should be valid WaveType enum values."""
        valid_values = {m.value for m in WaveType}
        for name, periods in tou_predefined_builtin.items():
            for i, period in enumerate(periods):
                assert period["waveType"] in valid_values, (
                    f"{name}[{i}] has invalid waveType: {period['waveType']}"
                )

    def test_dispatch_ids_are_valid(self):
        """All dispatchId values should be valid dispatchCodeType enum values."""
        valid_values = {m.value for m in dispatchCodeType}
        for name, periods in tou_predefined_builtin.items():
            for i, period in enumerate(periods):
                assert period["dispatchId"] in valid_values, (
                    f"{name}[{i}] has invalid dispatchId: {period['dispatchId']}"
                )

    def test_time_format(self):
        """startHourTime and endHourTime should be HH:MM format."""
        import re
        time_pattern = re.compile(r"^\d{2}:\d{2}$")
        for name, periods in tou_predefined_builtin.items():
            for i, period in enumerate(periods):
                assert time_pattern.match(period["startHourTime"]), (
                    f"{name}[{i}] bad startHourTime: {period['startHourTime']}"
                )
                assert time_pattern.match(period["endHourTime"]), (
                    f"{name}[{i}] bad endHourTime: {period['endHourTime']}"
                )
