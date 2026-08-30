"""FranklinWH device model identifiers and metadata.

Used for device discovery and HA config flow integration.
"""

# Network connectivity options.
#
# This is the encoding used by commSetPara.currentNetType (cmdType 317) and by
# the extended cmdType 339 payload.
#
# WARNING: this is NOT the same encoding as Current.network_connection, which
# comes from runtimeData.connType and uses 0=4G, 1=WiFi, 2=Ethernet. The two are
# incompatible — never map one through the other.
NETWORK_TYPES = {
    1: "Ethernet 1",
    2: "Ethernet 2",
    3: "WiFi",
    4: "4G Mobile"
}

# The OTHER encoding. runtimeData.connType (cmdType 203), surfaced as
# Current.network_connection. It exists because the warning above was being
# ignored in practice: cli_commands/status.py rendered connType through
# NETWORK_TYPES and so reported a gateway on WiFi as "Ethernet 1".
#
# Never map one through the other. If you need a label for connType, use this.
CONN_TYPE_NAMES = {
    0: "4G Mobile",
    1: "WiFi",
    2: "Ethernet",
}

# currentNetType -> the interface key used by get_network_info() / get_network_state()
NETWORK_TYPE_KEYS = {
    1: "eth0",
    2: "eth1",
    3: "wifi",
    4: "4g",
}

# currentNetType -> the corresponding switch key in the cmdType 341 payload
NETWORK_SWITCH_KEYS = {
    1: "ethernet0NetSwitch",
    2: "ethernet1NetSwitch",
    3: "wifiNetSwitch",
    4: "4GNetSwitch",
}

# An IPv4 value the aGate reports when an interface has no DHCP lease.
# Observed live: WiFi associated with an SSID but holding 0.0.0.0 (see
# docs/troubleshooting/2026-03-21_wifi_dhcp_failure.md). "Associated" is not
# "connected" — always check the address too.
UNASSIGNED_IPS = (None, "", "0.0.0.0")

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
    7: {"name": "aPower X", "sku": "APR-05K13V2-AU", "model": "aPower X-02-AU"},
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
