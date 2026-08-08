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
| <a id="cmd-203"></a>**`203`** | `STATUS` | `{"opt": 1}` | [`_status()`](API_REFERENCE.md#franklinwh_cloud.mixins.stats.StatsMixin._status) | High-level device component status polling. ⚠️ **Legacy path** — `_status()` is a private method not called by `get_stats()`. Normal polling uses `getDeviceCompositeInfo` REST GET (not this MQTT relay). See [Transport Architecture](API_COOKBOOK.md#-transport-architecture-rest-get-vs-mqtt-relay). |
| <a id="cmd-211-1"></a>**`211`** | `POWER_AND_RELAYS` | `{"type": 1}` | [`get_power_info()`](API_REFERENCE.md#franklinwh_cloud.mixins.devices.DevicesMixin.get_power_info) | Full Gateway Electrical voltage/freq/relays |
| <a id="cmd-211-2"></a>**`211`** | `POWER_AND_RELAYS` | `{"type": 2}` | [`get_bms_info()`](API_REFERENCE.md#franklinwh_cloud.mixins.devices.DevicesMixin.get_bms_info) | Detailed raw battery module info (Layer 1) |
| <a id="cmd-211-3"></a>**`211`** | `POWER_AND_RELAYS` | `{"type": 3}` | [`get_bms_info()`](API_REFERENCE.md#franklinwh_cloud.mixins.devices.DevicesMixin.get_bms_info) | Detailed raw battery module info (Layer 2) |
| <a id="cmd-310"></a>**`310`** | `SMART_CIRCUIT_TOGGLE` | *(Varies)* | [`set_smart_circuit_state()`](API_REFERENCE.md#franklinwh_cloud.mixins.devices.DevicesMixin.set_smart_circuit_state) | Toggle Smart Circuits (`SwXMode`) or limits |
| <a id="cmd-311"></a>**`311`** | `SMART_CIRCUIT_INFO` | `{"opt": 0}` | [`get_smart_circuits_info()`](API_REFERENCE.md#franklinwh_cloud.mixins.devices.DevicesMixin.get_smart_circuits_info) | Smart Circuit naming and statuses |
| <a id="cmd-315"></a>**`315`** | `SYSTEM_CONTROL` | `{"opt": 1, "paraType": 1, "reboot": 1}` | *(none — not implemented)* | aGate reboot. ⛔ The same payload exposes `reset`, `cleanUnlockAlarm`, `cleanLockAlarm`, `cleanAlarmFlag` — **never populate `reset`**, it is almost certainly a factory reset. |
| <a id="cmd-317"></a>**`317`** | `NETWORK_INTERFACES` | `{"opt": 0}` | [`get_network_info()`](API_REFERENCE.md#franklinwh_cloud.mixins.devices.DevicesMixin.get_network_info) | Verbose eth/wifi interface IP and DHCP |
| <a id="cmd-327"></a>**`327`** | `AESTHETICS` | *(Varies)* | [`led_light_settings()`](API_REFERENCE.md#franklinwh_cloud.mixins.devices.DevicesMixin.led_light_settings) | aPower RGB LED aesthetic limits |
| <a id="cmd-335"></a>**`335`** | `WIFI_SCAN` | `{"wifi_ScanTime": 0}` | [`scan_wifi_networks()`](API_REFERENCE.md#franklinwh_cloud.mixins.devices.DevicesMixin.scan_wifi_networks) | Trigger active 2.4/5GHz AP discovery |
| <a id="cmd-337"></a>**`337`** | `WIFI_CONFIG` | `{"opt": 0}` | [`get_wifi_config()`](API_REFERENCE.md#franklinwh_cloud.mixins.devices.DevicesMixin.get_wifi_config) | Connected SSID & local AP broadcast limits |
| <a id="cmd-339"></a>**`339`** | `CLOUD_CONNECTIVITY`| `{"opt": 0}` | [`get_connection_status()`](API_REFERENCE.md#franklinwh_cloud.mixins.devices.DevicesMixin.get_connection_status) | AWS Cloud / Internet reachability checks |
| <a id="cmd-341"></a>**`341`** | `NETWORK_SWITCHES` | `{"opt": 0}` | [`get_network_switches()`](API_REFERENCE.md#franklinwh_cloud.mixins.devices.DevicesMixin.get_network_switches) | Boolean flags for eth0/eth1/4G/wifi |
| <a id="cmd-353"></a>**`353`** | `ACCESSORY_LOADS` | `{"opt": 0}` | [`get_accessories_power_info()`](API_REFERENCE.md#franklinwh_cloud.mixins.devices.DevicesMixin.get_accessories_power_info) | SC / V2L / Generator current draw payloads |

## Response `cmdType` Mapping

The gateway answers request `cmdType` N with response N+1 — **except `STATUS`, where 203
answers with 201.** Do not assume N+1; use `MqttResponse` in `franklinwh_cloud.models`.

| Request | Response | Confirmed occurrences |
| :---: | :---: | :--- |
| `203` | **`201`** ⚠️ | 780 — the one exception to the N+1 rule |
| `211` | `212` | 137 |
| `311` | `312` | 283 |
| `315` | `316` | 2 |
| `317` | `318` | 484 |
| `327` | `328` | 418 |
| `335` | `336` | 39 |
| `337` | `338` | 388 |
| `339` | `340` | 67 |
| `341` | `342` | 38 |
| `353` | `354` | 1267 |

`310` (`SMART_CIRCUIT_TOGGLE`) is absent deliberately: it has never been observed as a
request in any capture, so its response code is unknown.

## Read vs Write

Most commands use an `opt` flag (or `optType` for 317) to select direction: `0` reads, `1`
writes. The library currently implements the **read** half of the network commands only.

The write payloads below are confirmed on the wire but **not implemented** — see
[Network Connectivity & WiFi Switching](NETWORK_CONNECTIVITY_DESIGN.md) for the full
analysis, safety preflight and phasing.

| `cmdType` | Write `dataArea` | Status |
| :---: | :--- | :--- |
| `337` | `{"opt":1,"wifi_SSID","wifi_Pw","ap_SSID","ap_Pw"}` | ✅ Confirmed. Sets WiFi credentials — and observed to move the gateway from 4G to WiFi on its own. `ap_SSID`/`ap_Pw` must be echoed from a preceding `opt:0` read. |
| `317` | `{"optType":1,"paraType":6,"commSetPara":{…},"num":N}` | ⚠️ Accepted (`result:0`) but only ever observed writing an unchanged `currentNetType`. `num` is the **key count** of `commSetPara` — compute it, never hardcode. |
| `341` | `{"opt":1, …four switches…}` | ❌ Never observed. Shape inferred by analogy; must be validated no-op-first. |
| `315` | `{"opt":1,"paraType":1,"reboot":1}` | ✅ Confirmed. Reboot only — never populate `reset`. |

> ⚠️ A write ack (`result:0`) means the aGate **accepted the config**, not that it applied
> or associated successfully. A wrong WiFi password still returns `result:0`. Success can
> only be established by polling `317` afterwards.

## Deprecation & Traceability

- **API V2 Fallacies**: Previous hypotheses assumed modern V2 endpoints (like `getHotSpotInfo/v2`) replaced `sendMqtt` analogs. Our local matrix fuzzing verified this is false for integration developers requiring hardware physics arrays. The `MqttCmd` payloads listed above must be retained.
- **M713 Limitations**: The LocRemCtl mode logic natively attempts to bypass these cloud relays altogether using Modbus TCP when users invoke local operations, which is why cataloging the `sendMqtt` trace is strictly tied to Remote-Only operations.
