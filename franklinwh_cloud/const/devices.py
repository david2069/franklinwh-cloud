"""FranklinWH device model identifiers and metadata.

Used for device discovery and HA config flow integration.
"""

# Network connectivity options.
#
# This is the encoding used by commSetPara.currentNetType (cmdType 317) and by
# the extended cmdType 339 payload.
#
# runtimeData.connType (cmdType 203), surfaced as Current.network_connection,
# uses THIS SAME encoding. A long-standing comment claimed it was
# 0=4G, 1=WiFi, 2=Ethernet and that the two were incompatible. That claim was
# never sourced and is contradicted by the corpus: across 20,471 runtimeData
# samples, connType is observed only as {2: 559, 3: 19797, 4: 115}. Values 0
# and 1 never occur, and 3 dominating matches a gateway that lives on WiFi.
# See DEF-CONNTYPE-ENCODING-WRONG.
# Labels are keyed to the API field name, NOT to the vendor's physical port
# numbering, because the two do not line up and the collision is dangerous.
#
# The FranklinWH System Installation Guide p.59 states: "The cable from the
# household network may only be connected to the Eth1 port." So the vendor's
# "Eth1" is the ONE port that reaches the internet. Calling API `eth0`
# "Ethernet 1" invited a reader to believe eth0 was that port. It is not:
# on the reference gateway eth0 is static with gateway 172.16.1.1 — a segment
# unrelated to the household LAN — while eth1 is DHCP, which is what a
# household port would be.
#
# That identification is inference from one gateway, so the labels deliberately
# assert nothing beyond the API field they came from. See
# DEF-ETH-PORT-IDENTITY-UNCONFIRMED.
NETWORK_TYPES = {
    1: "Ethernet (eth0)",
    2: "Ethernet (eth1)",
    3: "WiFi",
    4: "4G Mobile"
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
