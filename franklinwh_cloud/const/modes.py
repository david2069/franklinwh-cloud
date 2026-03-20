"""Operating modes and power control constants."""

from enum import Enum


# Operating Work Modes
MODE_TIME_OF_USE = "time_of_use"
MODE_SELF_CONSUMPTION = "self_consumption"
MODE_EMERGENCY_BACKUP = "emergency_backup"

MODE_MAP = {
    1: MODE_TIME_OF_USE,
    2: MODE_SELF_CONSUMPTION,
    3: MODE_EMERGENCY_BACKUP,
}

TIME_OF_USE = 1
SELF_CONSUMPTION = 2
EMERGENCY_BACKUP = 3


class workModeType(Enum):
    """Operating work mode enumeration (Cloud API workMode codes)."""
    TIME_OF_USE = 1
    SELF_CONSUMPTION = 2
    EMERGENCY_BACKUP = 3


# ── Modbus TCP Work Modes ────────────────────────────────────────
# The aGate uses different mode codes on its Modbus TCP interface
# (exposed as "oldIndex" in the Cloud API's getGatewayTouListV2).
# TOU and Emergency Backup are SWAPPED vs Cloud API; Self-Consumption
# is the same (2) in both systems.
MODBUS_EMERGENCY_BACKUP = 1
MODBUS_SELF_CONSUMPTION = 2
MODBUS_TIME_OF_USE = 3


class modbusWorkMode(Enum):
    """Operating work mode enumeration (Modbus TCP / oldIndex codes)."""
    EMERGENCY_BACKUP = 1
    SELF_CONSUMPTION = 2
    TIME_OF_USE = 3


# ── Cross-reference mappings ────────────────────────────────────
# Cloud API workMode → Modbus oldIndex
CLOUD_TO_MODBUS_MODE = {
    TIME_OF_USE: MODBUS_TIME_OF_USE,           # 1 → 3
    SELF_CONSUMPTION: MODBUS_SELF_CONSUMPTION,  # 2 → 2
    EMERGENCY_BACKUP: MODBUS_EMERGENCY_BACKUP,  # 3 → 1
}

# Modbus oldIndex → Cloud API workMode
MODBUS_TO_CLOUD_MODE = {v: k for k, v in CLOUD_TO_MODBUS_MODE.items()}


OPERATING_MODES = {
    1: "Time of Use",
    2: "Self-Consumption",
    3: "Emergency Backup",
    "Time of Use": 1,
    "Self-Consumption": 2,
    "Emergency Backup": 3,
    "time_of_use": 1,
    "self_consumption": 2,
    "emergency_backup": 3
}

# Run mode of Gateway
RUN_STATUS = {
    0: "Standby",               # Inactive or Idle
    1: "Charging",
    2: "Discharging",
    3: "Unknown 3",             # To be added
    4: "Unknown 4",             # To be added
    5: "Off-Grid Standby",
    6: "Off-Grid Charging",
    7: "Off-Grid Discharging",
    8: "Debug Mode",           # Franklin Remote Support
    9: "VPP mode"              # Virtual Power Plant mode controlled
}

# Power Control Settings for aGate
# Grid Export/Import Enable/Disable or power level settings:
# Values: 0=Disabled, -1.0=Unlimited, >0.1 to 10000 is the amount in kW to export/import
PCS_CONTROL = {
    "ENABLED": 0.1,
    "DISABLED": 0,
    "UNLIMITED": -1.0,
    "disable_grid_export": 0,
    "unlimted_grid_export": -1.0,
    "disable_grid_import": 0,
    "unlimited_grid_import": -1.0,
    "custom_power_setting": 0.1,
    1: "disable_grid_export",
    2: "unlimted_grid_export",
    3: "disable_grid_import",
    4: "unlimited_grid_import",
    5: "custom_power_setting"
}

# Emergency Backup Periods
# reqbackupForeverFlag: 1 => Indefinite, 2 => Custom duration
# Custom option is duration in minutes - range: >=30 AND <=1440
EMERGENCY_BACKUP_PERIODS = {
    "one_day": 1440,
    "two_day": 2880,
    "three_day": 4320,
    "indefinite": 1,
    "custom": 2,
    1: "one_day",
    2: "two_day",
    3: "three_day",
    4: "indefinite",
    5: "custom"
}
