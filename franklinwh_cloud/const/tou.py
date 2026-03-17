"""Time-of-Use scheduling constants and validation."""

from enum import Enum


class dispatchCodeType(Enum):
    """Dispatch mode codes for TOU scheduling."""
    HOME = 2
    HOME_LOADS = 2
    STANDBY = 3
    SELF = 6
    SELF_CONSUMPTION = 6
    SOLAR = 1
    SOLAR_CHARGE = 1
    GRID_CHARGE = 8
    GRID_IMPORT = 8
    FORCE_CHARGE = 8
    GRID_EXPORT = 7
    GRID_DISCHARGE = 7
    FORCE_DISCHARGE = 7
    CUSTOM = 0
    PREDEFINED = 0


valid_tou_modes = [
    "HOME",
    "HOME_LOADS",
    "STANDBY",
    "SOLAR",
    "SOLAR_CHARGE",
    "SELF",
    "SELF_CONSUMPTION",
    "GRID_EXPORT",
    "GRID_DISCHARGE",
    "GRID_IMPORT",
    "GRID_DISCHARGE",
    "FORCE_CHARGE",
    "FORCE_DISCHARGE",
    "CUSTOM",           # No dispatch code - as specific to this interface
    "PREDEFINED",       # As above
    "JSON"              # As above
]


DISPATCH_CODES = {
    "HOME": 1,
    "HOME_LOADS": 1,
    "STANDBY": 2,
    "SOLAR": 3,
    "SOLAR_CHARGING": 3,
    "SELF": 6,
    "SELF_CONSUMPTION": 6,
    "GRID_EXPORT": 7,
    "GRID_DISCHARGE": 7,
    "FORCE_DISCHARGE": 7,
    "GRID_CHARGE": 8,
    "GRID_IMPORT": 8,
    "FORCE_CHARGE": 8,
    1: "aPower to home (surplus solar to grid)",
    2: "aPower on standby (surplus solar to grid)",
    6: "Self-consumption (surplus solar to grid)",
    3: "aPower charges from solar",
    7: "aPower to home/grid",
    8: "aPower charges from solar/grid",
    "B": 2,
    "D": 6,
    "E": 3,
    "F": 1,
    "G": 8,
    "H": 7
}


class WaveType(Enum):
    """Tariff period codes for TOU scheduling.
    
    These reference pricing rates or different strategies to dispatch the battery.
    """
    OFF_PEAK = 0
    MID_PEAK = 1
    ON_PEAK = 2
    SUPER_OFF_PEAK = 4


WAVE_TYPES = {
    0: "Off-Peak",
    1: "Mid-Peak",
    2: "On-Peak",
    4: "Super Off-Peak",
    "OFF_PEAK": 0,
    "MID_PEAK": 1,
    "ON_PEAK": 2,
    "SUPER_OFF_PEAK": 4,
    "Off-Peak": 0,
    "Mid-Peak": 1,
    "On-Peak": 2,
    "Super Off-Peak": 4
}

# JSON Schema for TOU schedule validation (detailVolList)
# "required" is specifically for emulating mobile app of the minimum data elements
# If you are "amending" existing entries, the mandatory fields are greater (not supported)
tou_json_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "array",
    "minItems": 1,
    "items": {
        "type": "object",
        "required": [
            "name",
            "startHourTime",
            "endHourTime",
            "waveType",
            "dispatchId"
        ],
        "properties": {
            # --- MANDATORY FIELDS (Strict) ---
            "name": {"type": "string"},
            "startHourTime": {
                "type": "string",
                "pattern": "^([0-1]?[0-9]|2[0-3]):[0-5][0-9]|24:00$"
            },
            "endHourTime": {
                "type": "string",
                "pattern": "^([0-1]?[0-9]|2[0-3]):[0-5][0-9]|24:00$"
            },
            "waveType": {
                "type": "integer",
                "enum": [0, 1, 2, 4]
            },
            "dispatchId": {
                "type": "integer",
                "enum": [1, 2, 3, 6, 7, 8]
            },

            # --- OPTIONAL FIELDS (Nullable) ---
            # Numeric fields: Accept Integer OR Null
            "id": {"type": ["integer", "null"]},
            "strategyId": {"type": ["integer", "null"]},
            "gridDischargeMax": {"type": ["integer", "null"]},
            "gridChargeMax": {"type": ["integer", "null"]},
            "chargeMax": {"type": ["integer", "null"]},
            "chargePower": {"type": ["integer", "null"]},
            "gridFeedMax": {"type": ["integer", "null"]},
            "dischargePower": {"type": ["integer", "null"]},
            "dischargeMax": {"type": ["integer", "null"]},
            "solarCutoff": {"type": ["integer", "null"]},
            "gridMax": {"type": ["integer", "null"]},
            "maxChargeSoc": {"type": ["integer", "null"]},
            "minDischargeSoc": {"type": ["integer", "null"]},
            "heatEnable": {"type": ["integer", "null"]},
            "powerOffApower": {"type": ["integer", "null"]},
            "offGrid": {"type": ["integer", "null"]},
            "gcaoMax": {"type": ["integer", "null"]},
            "rampTime": {"type": ["integer", "null"]},
            "useModeFlag": {"type": ["integer", "null"]},

            # String fields: Accept String OR Null
            "briefDescribe": {"type": ["string", "null"]},
            "solarPriority": {"type": ["string", "null"]},
            "loadPriority": {"type": ["string", "null"]},
            "dispatch": {"type": ["string", "null"]}
        }
    }
}
