# FranklinWH MQTT Command Catalog

The `sendMqtt` gateway bridge endpoint (`POST /hes-gateway/terminal/sendMqtt`) is the legacy method FranklinWH used to relay highly-specific configuration and polling commands directly from the cloud to the physical aGate using numerical `cmdType` and `opt` codes.

As the FranklinWH API evolves (V2), many of these raw MQTT relays are being superseded by dedicated, higher-level REST API endpoints (e.g. `getHotSpotInfo/v2`).

This ledger catalogs our library's Python mixin dependencies against known `cmdType` relays so we can effectively track hardware regressions and API deprecations.

## `sendMqtt` Command Mappings

| Python Method | `cmdType` | Payload Description | Potential API V2 Replacement |
| :--- | :---: | :--- | :--- |
| **`_status()`** | `203` | High-level device component status polling | `GET /hes-gateway/terminal/getDeviceInfo` |
| **`get_bms_info()`** | `211` | Detailed raw battery module info (types 2, 3) | *(No V2 replacement identified)* |
| **`get_power_info()`** | `211` | Electrical voltage/freq/relays (type 1) | `GET /hes-gateway/common/getDeviceRealTimeData` |
| **`set_smart_circuit_state()`** | `310` | Toggle Smart Circuits (SwXMode) | *(Partial overlap with `setPowerControlV2`)* |
| **`set_smart_circuit_soc_cutoff()`** | `310` | Set Auto Shed SoC Threshold (SwXAtuoEn) | *(None)* |
| **`set_smart_circuit_load_limit()`** | `310` | Peak Amperage bounds (SwXLoadLimit) | *(None)* |
| **`get_smart_circuits_info()`** | `311` | Smart Circuit naming and statuses | *(None)* |
| **`_switch_status()`** | `311` | Legacy SC status poll | *(None)* |
| **`get_network_info()`** | `317` | Verbose eth/wifi interface IP and DHCP | *(None)* |
| **`led_light_settings()`** | `327` | aPower RGB LED aesthetic limits | *(None)* |
| **`scan_wifi_networks()`** | `335` | Trigger active 2.4/5GHz AP discovery | *(None)* |
| **`get_wifi_config()`** | `337` | Connected SSID & local AP broadcast limits | `GET /hes-gateway/manage/getHotSpotInfo/v2` |
| **`get_connection_status()`** | `339` | AWS Cloud / Internet reachability checks | `GET /hes-gateway/common/getMaintenanceInfo` |
| **`get_network_switches()`** | `341` | Boolean flags for eth0/eth1/4G/wifi | *(None)* |
| **`get_accessories_power_info()`** | `353` | SC / V2L / Generator current draw payloads | *(None)* |
| **`_switch_usage()`** | `353` | Legacy V1 real-time switch loads | *(None)* |

## Deprecation Notes
- **`getHotSpotInfo/v2`**: Officially replaces `cmdType 337` (`get_wifi_config()`). The V2 REST endpoint handles gateway local access point metrics synchronously, removing the brittle requirement for the mobile app to await asynchronous MQTT responses for WiFi state boundaries.
- **`setPowerControlV2`**: Likely wraps `cmdType 310` logic for load management with stronger backend assertions.
- **M713 Limitations**: The LocRemCtl mode logic natively attempts to bypass these cloud relays altogether using Modbus TCP when users invoke local operations, which is why cataloging the `sendMqtt` trace is strictly tied to Remote-Only operations.
