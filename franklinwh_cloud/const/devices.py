"""FranklinWH device model identifiers and metadata.

Used for device discovery and HA config flow integration.
"""

# Network connectivity options
NETWORK_TYPES = {
    1: "Ethernet 1",
    2: "Ethernet 2",
    3: "WiFi",
    4: "4G Mobile"
}

# aGate Health Status
# Note: 1=Normal verified against live system (deviceStatus=1 with healthy operation)
# Previously had 0=Normal/1=Fault which was inverted.
AGATE_STATE = {
    0: "Fault",
    1: "Normal",
}

# aGate Activity Status
AGATE_ACTIVE = {
    0: "Inactive",
    1: "Active"
}

# SIM Card Status
SIM_STATUS = {
    0: "Not Installed",
    1: "Installed (Inactive)",
    2: "Active",
    3: "Error",
}

# Country Identifiers
COUNTRY_ID = {
    1: "China",
    2: "United States",
    3: "Australia"
}

# FranklinWH Device Models
# System ID, Model Designation, SKU and Model Type
# Devices in 900 range are unknown until someone has one and reports ID
FRANKLINWH_MODELS = {
    0: {"name": "aPower X", "sku": "APR-05K1V1-US", "model": "aPower X-10"},
    1: {"name": "aPower X", "sku": "APR-05K11V1-US", "model": "aPower X-10"},
    2: {"name": "aPower X", "sku": "APR-05K13V1-AU", "model": "aPower X-01-AU"},
    3: {"name": "aPower 2", "sku": "APR-10K15V2-US", "model": "aPower X-20"},
    4: {"name": "aPower S", "sku": "APRS-10K15V1-US", "model": "aPower S-10"},
    5: {"name": "aPower S", "sku": "APRS-11K15V2-US", "model": "aPower S-10"},
    6: {"name": "aPower X", "sku": "APR-05K15V1-US", "model": "aPower X-10"},
    100: {"name": "aGate X", "sku": "AGT-R1V1-US", "model": "aGate X-10"},
    101: {"name": "aGate X", "sku": "AGT-R1V2-US", "model": "aGate X-20"},
    102: {"name": "aGate X", "sku": "AGT-R1V1-AU", "model": "aGate X-01-AU"},
    103: {"name": "aGate X", "sku": "AGT-R1V3-US", "model": "aGate X 20 (US)"},
    104: {"name": "aGate X", "sku": "AGT-R1V3-US", "model": "aGate X 20 (US)"}
}

# Accessories
# Device ID = countryID "-" accessoryType "-" version
# Model, SKU, Model Version, Compatible aGate/aPowerS ID
FRANKLINWH_ACCESSORIES = {
    301: {"name": "Generator Module", "sku": "ACCY-GENV1-AU", "model": "Generator Module-01-AU", "compatiable": "102"},
    302: {"name": "Smart Circuits", "sku": "ACCY-SCV1-AU", "model": "Smart Circuits-01-AU", "compatiable": "102"},
    201: {"name": "Generator Module", "sku": "ACCY-GENV1-US", "model": "Generator Module-01", "compatiable": "100|101"},
    202: {"name": "Smart Circuits", "sku": "ACCY-SCV1-US", "model": "Smart Circuits-01", "compatiable": "100|101"},
    203: {"name": "Generator Module", "sku": "ACCY-GENV2-US", "model": "Generator Module-02", "compatiable": "103|104"},
    204: {"name": "Smart Circuits", "sku": " ACCY-SCV2-US", "model": "Smart Circuits-02", "compatiable": "102|103|104"},
    251: {"name": "aPbox", "sku": "ACCY-RCV1-US", "model": "aPbox-10", "compatiable": "ALL"},
    252: {"name": "Split-CT", "sku": "ACCY-CT200V1-US", "model": "Split-CT-US", "compatiable": "ALL"},
    253: {"name": "aHub", "sku": "ACCY-AHUBV1-US", "model": "aHub-20-04", "compatiable": "4|5"},
    254: {"name": "Meter Adapter Controller", "sku": "MAC-R1V1-US", "compatiable": "4|5"},
}
