"""Hardware and accessory discrete state translations."""

# APBox Digital I/O
APBOX_IO_STATE = {
    0: "Open / OFF",
    1: "Closed / ON"
}

# Smart Circuit Relay
SMART_CIRCUIT_RELAY = {
    0: "OFF",
    1: "ON"
}

# Smart Circuit Operational Mode (`SwXMode`)
SMART_CIRCUIT_MODE = {
    0: "Manual",
    1: "Schedule",
    2: "Smart / Auto"
}

# Generator Module State (`genStat`)
GENERATOR_STATE = {
    0: "Standby / OFF",
    1: "Running / ON",
    2: "Cooldown",
    3: "Fault"
}

# V2L Run State (`v2lRunState`)
V2L_RUN_STATE = {
    0: "Disabled",
    1: "Standby",
    2: "Discharging / Active",
    3: "Fault"
}

# Power Electronics (PCS) State (`pe_stat`)
PCS_STATE = {
    0: "Off",
    1: "Standby",
    2: "Initialization",
    3: "Fault",
    4: "Warning",
    5: "Running / Active",
    6: "Charging",
    7: "Discharging",
    8: "Online / Running",
    9: "Off-grid"
}

# Battery Management System (BMS) Run State (`bms_work`)
# Firmware encoding confirmed on V10R01B04D00 (captured 2026-02-23).
# Invariant: bms_work = run_status + BMS_WORK_OFFSET (always)
# DO NOT look up bms_work values against RUN_STATUS — different offset, different dict.
BMS_WORK_OFFSET = 5  # bms_work is always run_status + 5

BMS_STATE = {
    0: "Off",
    1: "Initialization",
    2: "Fault",
    3: "Warning",
    4: "Shutdown",
    5: "Standby",       # run_status 0 (Standby) + 5
    6: "Charging",      # run_status 1 (Charging) + 5  — was "Discharging" (incorrect)
    7: "Discharging"    # run_status 2 (Discharging) + 5 — was "Charging" (incorrect)
}

# DCDC Controller State (`DCDCStatus`) — mirrors bms_work exactly
# Standby=4, Charging=6, Discharging=7 (different standby offset from bms_work)
DCDC_STATE = {
    4: "Standby",
    6: "Charging",
    7: "Discharging"
}
