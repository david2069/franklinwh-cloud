"""Helpers for interating with the FranklinWH Python Client Library"""

__version__ = "0.4.0"

from .client import Client, TokenFetcher
from .models import Stats, Current, Totals, GridStatus, empty_stats
from .exceptions import (
    TokenExpiredException, AccountLockedException, InvalidCredentialsException,
    DeviceTimeoutException, GatewayOfflineException, InvalidOperatingMode,
    InvalidOperatingModeOption, UauthorizedRequest, BadRequestParsingError,
    InvalidTOUScheduleOption,
)

# Operating Work and Run mode constants
from .const import RUN_STATUS, OPERATING_MODES, workModeType
from .const import MODE_MAP, MODE_TIME_OF_USE, MODE_SELF_CONSUMPTION, MODE_EMERGENCY_BACKUP
# Power Control Settings and Emergency Backup periods
from .const import PCS_CONTROL, EMERGENCY_BACKUP_PERIODS
# TOU Schedule dispatch codes and wave types (tariffs)
from .const import dispatchCodeType, DISPATCH_CODES, WaveType, WAVE_TYPES
# NOTE: TOU Schedule presets (primarily for testing / examples)
from .const.test_fixtures import (
    gap_schedule, export_to_grid_always, export_to_grid_peak2, 
    export_to_grid_peakonly, charge_from_grid, standby_schedule, 
    power_home_only, charge_from_solar, self_schedule, custom_schedule
)

__all__ = [
    "DEFAULT_URL_BASE",
    "AccessoryType",
    "AccountLockedException",
    "BadRequestParsingError",
    "Client",
    "Current",
    "DeviceTimeoutException",
    "GatewayOfflineException",
    "GridStatus",
    "InvalidCredentialsException",
    "InvalidOperatingMode",
    "InvalidOperatingModeOption",
    "InvalidTOUScheduleOption",
    "Stats",
    "TokenExpiredException",
    "TokenFetcher",
    "Totals",
    "UauthorizedRequest",
    "empty_stats",
]

