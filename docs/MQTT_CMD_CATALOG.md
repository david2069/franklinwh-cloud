# FranklinWH MQTT Command Catalog

The `sendMqtt` gateway bridge endpoint (`POST /hes-gateway/terminal/sendMqtt`) is the legacy method FranklinWH used to relay highly-specific configuration and polling commands directly from the cloud to the physical aGate using numerical `cmdType` and parameter fields.

!!! warning "V2 API Discovery Warnings"
    Extensive architectural fuzzing has proven that modern V2 REST endpoints (like `getDeviceRealTimeData` or `getHotSpotInfo/v2`) **are not** 1:1 replacements for these MQTT relays. V2 endpoints drop over 99% of structural physics arrays (reducing massive voltage blocks to a single `batterySoc` cache value) to accelerate mobile-app load times. As a result, the `sendMqtt` payloads cataloged below remain the **exclusive source of truth** for deep hardware telemetry!

This ledger catalogs our library's Python mixin dependencies against known `cmdType` relays so we can effectively track hardware regressions.

---

## Command Catalog

Below is the exhaustive index of numerical `sendMqtt` values mapped strictly to the Python wrapper methods that trigger them. 
Click any link in the **Python Method** column to view its formal definition in the [API Reference](API_REFERENCE.md).

| `cmdType` | `MqttCmd` Enum | `dataArea` Sub-Type / Opt | Python Method | Payload Description |
| :---: | :--- | :--- | :--- | :--- |
| <a id="cmd-203"></a>**`203`** | `STATUS` | `{"opt": 1}` | [`_status()`](API_REFERENCE.md#franklinwh_cloud.mixins.stats.StatsMixin._status) | High-level device component status polling |
| <a id="cmd-211-1"></a>**`211`** | `POWER_AND_RELAYS` | `{"type": 1}` | [`get_power_info()`](API_REFERENCE.md#franklinwh_cloud.mixins.devices.DevicesMixin.get_power_info) | Full Gateway Electrical voltage/freq/relays |
| <a id="cmd-211-2"></a>**`211`** | `POWER_AND_RELAYS` | `{"type": 2}` | [`get_bms_info()`](API_REFERENCE.md#franklinwh_cloud.mixins.devices.DevicesMixin.get_bms_info) | Detailed raw battery module info (Layer 1) |
| <a id="cmd-211-3"></a>**`211`** | `POWER_AND_RELAYS` | `{"type": 3}` | [`get_bms_info()`](API_REFERENCE.md#franklinwh_cloud.mixins.devices.DevicesMixin.get_bms_info) | Detailed raw battery module info (Layer 2) |
| <a id="cmd-310"></a>**`310`** | `SMART_CIRCUIT_TOGGLE` | *(Varies)* | [`set_smart_circuit_state()`](API_REFERENCE.md#franklinwh_cloud.mixins.devices.DevicesMixin.set_smart_circuit_state) | Toggle Smart Circuits (`SwXMode`) or limits |
| <a id="cmd-311"></a>**`311`** | `SMART_CIRCUIT_INFO` | `{"opt": 0}` | [`get_smart_circuits_info()`](API_REFERENCE.md#franklinwh_cloud.mixins.devices.DevicesMixin.get_smart_circuits_info) | Smart Circuit naming and statuses |
| <a id="cmd-317"></a>**`317`** | `NETWORK_INTERFACES` | `{"opt": 0}` | [`get_network_info()`](API_REFERENCE.md#franklinwh_cloud.mixins.devices.DevicesMixin.get_network_info) | Verbose eth/wifi interface IP and DHCP |
| <a id="cmd-327"></a>**`327`** | `AESTHETICS` | *(Varies)* | [`led_light_settings()`](API_REFERENCE.md#franklinwh_cloud.mixins.devices.DevicesMixin.led_light_settings) | aPower RGB LED aesthetic limits |
| <a id="cmd-335"></a>**`335`** | `WIFI_SCAN` | `{"wifi_ScanTime": 0}` | [`scan_wifi_networks()`](API_REFERENCE.md#franklinwh_cloud.mixins.devices.DevicesMixin.scan_wifi_networks) | Trigger active 2.4/5GHz AP discovery |
| <a id="cmd-337"></a>**`337`** | `WIFI_CONFIG` | `{"opt": 0}` | [`get_wifi_config()`](API_REFERENCE.md#franklinwh_cloud.mixins.devices.DevicesMixin.get_wifi_config) | Connected SSID & local AP broadcast limits |
| <a id="cmd-339"></a>**`339`** | `CLOUD_CONNECTIVITY`| `{"opt": 0}` | [`get_connection_status()`](API_REFERENCE.md#franklinwh_cloud.mixins.devices.DevicesMixin.get_connection_status) | AWS Cloud / Internet reachability checks |
| <a id="cmd-341"></a>**`341`** | `NETWORK_SWITCHES` | `{"opt": 0}` | [`get_network_switches()`](API_REFERENCE.md#franklinwh_cloud.mixins.devices.DevicesMixin.get_network_switches) | Boolean flags for eth0/eth1/4G/wifi |
| <a id="cmd-353"></a>**`353`** | `ACCESSORY_LOADS` | `{"opt": 0}` | [`get_accessories_power_info()`](API_REFERENCE.md#franklinwh_cloud.mixins.devices.DevicesMixin.get_accessories_power_info) | SC / V2L / Generator current draw payloads |

## Deprecation & Traceability

- **API V2 Fallacies**: Previous hypotheses assumed modern V2 endpoints (like `getHotSpotInfo/v2`) replaced `sendMqtt` analogs. Our local matrix fuzzing verified this is false for integration developers requiring hardware physics arrays. The `MqttCmd` payloads listed above must be retained.
- **M713 Limitations**: The LocRemCtl mode logic natively attempts to bypass these cloud relays altogether using Modbus TCP when users invoke local operations, which is why cataloging the `sendMqtt` trace is strictly tied to Remote-Only operations.
