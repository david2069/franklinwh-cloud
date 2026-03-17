"""Test fixtures for TOU schedule validation and testing.

⚠️ WARNING: These are for testing purposes only!
Do NOT import these in production code unless explicitly needed.

These predefined schedules are useful for:
- Testing TOU schedule uploads
- Validating JSON schema
- Examples for documentation

Usage:
    from franklinwh_cloud.const.test_fixtures import gap_schedule
    await client.set_tou_schedule(touSchedule=gap_schedule)
"""

from .tou import WaveType, dispatchCodeType


# Predefined test schedules
power_home_only = [
    {
        "startHourTime": "00:00",
        "endHourTime": "24:00",
        "waveType": WaveType.ON_PEAK.value,
        "name": "On-Peak",
        "dispatchId": dispatchCodeType.HOME_LOADS.value
    }
]

charge_from_solar = [
    {
        "startHourTime": "00:00",
        "endHourTime": "24:00",
        "waveType": WaveType.ON_PEAK.value,
        "name": "On-Peak",
        "dispatchId": dispatchCodeType.SOLAR.value
    }
]

charge_from_grid = [
    {
        "startHourTime": "00:00",
        "endHourTime": "24:00",
        "waveType": WaveType.ON_PEAK.value,
        "name": "On-Peak",
        "dispatchId": dispatchCodeType.SOLAR.value
    }
]

export_to_grid_always = [
    {
        "startHourTime": "00:00",
        "endHourTime": "24:00",
        "waveType": WaveType.ON_PEAK.value,
        "name": "On-Peak",
        "dispatchId": dispatchCodeType.GRID_EXPORT.value
    }
]

export_to_grid_peak2 = [
    {
        "startHourTime": "18:00",
        "endHourTime": "19:00",
        "waveType": WaveType.MID_PEAK.value,
        "name": "On-Peak",
        "dispatchId": dispatchCodeType.SELF_CONSUMPTION.value
    },
    {
        "startHourTime": "00:00",
        "endHourTime": "19:20",
        "waveType": WaveType.OFF_PEAK.value,
        "name": "On-Peak",
        "dispatchId": dispatchCodeType.SELF_CONSUMPTION.value
    },
    {
        "startHourTime": "17:00",
        "endHourTime": "19:00",
        "waveType": WaveType.ON_PEAK.value,
        "name": "On-Peak",
        "dispatchId": dispatchCodeType.GRID_EXPORT.value
    }
]

export_to_grid_peakonly = [
    {
        "startHourTime": "18:00",
        "endHourTime": "21:00",
        "waveType": WaveType.ON_PEAK.value,
        "name": "On-Peak",
        "dispatchId": dispatchCodeType.GRID_EXPORT.value
    }
]

standby_schedule = [
    {
        "startHourTime": "00:00",
        "endHourTime": "24:00",
        "waveType": WaveType.OFF_PEAK.value,
        "name": "Off-Peak",
        "dispatchId": dispatchCodeType.STANDBY.value
    }
]

self_schedule = [
    {
        "startHourTime": "19:00",
        "endHourTime": "23:10",
        "waveType": WaveType.ON_PEAK.value,
        "name": "On-Peak",
        "dispatchId": dispatchCodeType.SELF_CONSUMPTION.value
    }
]

custom_schedule = [
    {
        "startHourTime": "20:00",
        "endHourTime": "24:00",
        "waveType": WaveType.ON_PEAK.value,
        "name": "On-Peak",
        "dispatchId": dispatchCodeType.HOME_LOADS.value
    },
    {
        "startHourTime": "00:00",
        "endHourTime": "10:00",
        "waveType": WaveType.SUPER_OFF_PEAK.value,
        "name": "Super Off-Peak",
        "dispatchId": dispatchCodeType.HOME_LOADS.value
    },
    {
        "startHourTime": "10:00",
        "endHourTime": "12:00",
        "waveType": WaveType.SUPER_OFF_PEAK.value,
        "name": "On-Peak",
        "dispatchId": dispatchCodeType.SOLAR_CHARGE.value
    },
    {
        "startHourTime": "12:00",
        "endHourTime": "19:00",
        "waveType": WaveType.ON_PEAK.value,
        "name": "On-Peak",
        "dispatchId": dispatchCodeType.SELF_CONSUMPTION.value
    },
    {
        "startHourTime": "19:00",
        "endHourTime": "20:00",
        "waveType": WaveType.OFF_PEAK.value,
        "name": "Off-Peak",
        "dispatchId": dispatchCodeType.GRID_EXPORT.value
    }
]

gap_schedule = [
    {
        "startHourTime": "22:00",
        "endHourTime": "24:00",
        "waveType": WaveType.ON_PEAK.value,
        "name": "On-Peak",
        "dispatchId": dispatchCodeType.HOME_LOADS.value
    },
    {
        "startHourTime": "00:00",
        "endHourTime": "10:00",
        "waveType": WaveType.SUPER_OFF_PEAK.value,
        "name": "Super Off-Peak",
        "dispatchId": dispatchCodeType.HOME_LOADS.value
    },
    {
        "startHourTime": "10:00",
        "endHourTime": "12:00",
        "waveType": WaveType.SUPER_OFF_PEAK.value,
        "name": "On-Peak",
        "dispatchId": dispatchCodeType.SOLAR_CHARGE.value
    },
    {
        "startHourTime": "12:00",
        "endHourTime": "19:00",
        "waveType": WaveType.ON_PEAK.value,
        "name": "On-Peak",
        "dispatchId": dispatchCodeType.SELF_CONSUMPTION.value
    },
    {
        "startHourTime": "19:00",
        "endHourTime": "20:00",
        "waveType": WaveType.OFF_PEAK.value,
        "name": "Off-Peak",
        "dispatchId": dispatchCodeType.GRID_EXPORT.value
    }
]

# Exported fixture catalog
tou_predefined_builtin = {
    "charge_from_grid": charge_from_grid,
    "power_home_only": power_home_only,
    "charge_from_solar": charge_from_solar,
    "export_to_grid_always": export_to_grid_always,
    "export_to_grid_peakonly": export_to_grid_peakonly,
    "export_to_grid_peak2": export_to_grid_peak2,
    "standby_schedule": standby_schedule,
    "self_schedule": self_schedule,
    "custom_schedule": custom_schedule,
    "gap_schedule": gap_schedule
}
