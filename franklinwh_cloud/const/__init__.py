"""FranklinWH Constants Package

Core constants used across the franklinwh library.
Test fixtures are available in const.test_fixtures (not auto-imported

).

For backward compatibility, commonly-used constants are re-exported here.
Advanced users can import directly from submodules for clarity.
"""

# Operating modes
from .modes import (
    MODE_TIME_OF_USE,
    MODE_SELF_CONSUMPTION,
    MODE_EMERGENCY_BACKUP,
    MODE_MAP,
    OPERATING_MODES,
    RUN_STATUS,
    workModeType,
    TIME_OF_USE,
    SELF_CONSUMPTION,
    EMERGENCY_BACKUP,
    PCS_CONTROL,
    EMERGENCY_BACKUP_PERIODS,
    # Modbus TCP work mode codes (oldIndex from Cloud API)
    MODBUS_TIME_OF_USE,
    MODBUS_SELF_CONSUMPTION,
    MODBUS_EMERGENCY_BACKUP,
    modbusWorkMode,
    CLOUD_TO_MODBUS_MODE,
    MODBUS_TO_CLOUD_MODE,
)

# TOU scheduling
from .tou import (
    DISPATCH_CODES,
    WAVE_TYPES,
    dispatchCodeType,
    WaveType,
    tou_json_schema,
    valid_tou_modes
)

# Device metadata
from .devices import (
    FRANKLINWH_MODELS,
    FRANKLINWH_ACCESSORIES,
    NETWORK_TYPES,
    AGATE_STATE,
    AGATE_ACTIVE,
    COUNTRY_ID,
    SIM_STATUS,
)

# Test fixtures - re-exported for backward compatibility (used by cli.py)
from .test_fixtures import (
    tou_predefined_builtin,
    gap_schedule,
    export_to_grid_always,
    export_to_grid_peak2,
    export_to_grid_peakonly,
    charge_from_grid,
    standby_schedule,
    power_home_only,
    charge_from_solar,
    self_schedule,
    custom_schedule,
)

__all__ = [
    # Modes (Cloud API)
    "MODE_TIME_OF_USE", "MODE_SELF_CONSUMPTION", "MODE_EMERGENCY_BACKUP",
    "MODE_MAP", "OPERATING_MODES", "RUN_STATUS", "workModeType",
    "TIME_OF_USE", "SELF_CONSUMPTION", "EMERGENCY_BACKUP",
    "PCS_CONTROL", "EMERGENCY_BACKUP_PERIODS",
    # Modes (Modbus TCP)
    "MODBUS_TIME_OF_USE", "MODBUS_SELF_CONSUMPTION", "MODBUS_EMERGENCY_BACKUP",
    "modbusWorkMode", "CLOUD_TO_MODBUS_MODE", "MODBUS_TO_CLOUD_MODE",
    # TOU
    "DISPATCH_CODES", "WAVE_TYPES", "dispatchCodeType", "WaveType",
    "tou_json_schema", "valid_tou_modes",
    # Devices
    "FRANKLINWH_MODELS", "FRANKLINWH_ACCESSORIES",
    "NETWORK_TYPES", "AGATE_STATE", "AGATE_ACTIVE", "COUNTRY_ID", "SIM_STATUS",
    # Test fixtures (exported for cli.py)
    "tou_predefined_builtin",
    "gap_schedule", "export_to_grid_always", "export_to_grid_peak2",
    "export_to_grid_peakonly", "charge_from_grid", "standby_schedule",
    "power_home_only", "charge_from_solar", "self_schedule", "custom_schedule",
]
