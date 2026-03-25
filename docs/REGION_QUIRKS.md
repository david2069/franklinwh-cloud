# Region & Accessory Quirks

The FranklinWH Cloud API and official documentation are overwhelmingly US/North America-centric. Australian attributes tend to be sparse, and many features present in the API payload are simply not implemented or available on AU hardware. 

Furthermore, several accessories like the aHub and Meter Adapter Controller (MAC) are completely opaque to the Cloud API—meaning the API cannot retrieve their firmware version or live status.

This document serves as a living registry of these known limitations and quirks.

## Regional Limitations (US vs AU)

All FranklinWH aGate and aPower models are functionally similar, but their capabilities differ dramatically based on their installation region due to grid compliance standards (UL9540 vs AS4777).

### United States (Country ID: 2)
The baseline for the API. Most features are fully supported.
* **Grid Standard:** UL9540 / IEEE 1547
* **Voltage:** 120/240V split-phase
* **V2L (Vehicle-to-Load):** Fully supported (requires Smart Circuits V2 or Generator Module + SC V1)
* **Net Energy Metering (NEM):** Applicable (NEM 2.0 / 3.0 via CA/HI)
* **Utility Programmes:** SGIP, Battery Bonus (Hawaii), JA12, SDCP

### Australia (Country ID: 3)
The API returns a lot of `null` fields for Australian systems. This is expected behaviour, not an error.
* **Grid Standard:** AS4777 / Clean Energy Council
* **Voltage:** 230V single-phase (or 415V 3-phase on compatible setups)
* **V2L (Vehicle-to-Load):** **Not supported** on AU hardware. 
* **Export Limit:** Typically constrained to **10kW** per phase via DNSP regulations.
* **API Null Fields (Expected):** `nemType`, `sgipEntrance`, `bbEntrance`, `ja12Entrance`, `isJoinJA12`, `sdcpFlag`, `programmeList`.

---

## Accessory Quirks 

The FranklinWH Cloud API struggles to see certain devices installed on the local RS485 bus. In many cases, it can only confirm the *presence* of an accessory, but not its firmware version, serial number, or live operating state.

| Accessory | Known API Limitations | Workaround / Notes |
|-----------|-----------------------|--------------------|
| **aHub** | Firmware, serial, and port statuses are **completely opaque**. Only presence is reported via the `ahubAddressingFlag`. | The aHub's firmware version is only accessible locally via the Modbus `15xxx` register range. |
| **aPBox** | Firmware and serial are opaque. | The digital input/output states *are* visible via `getApBoxStatus` commands. |
| **MAC-1** | Firmware and RSD switch state are opaque. | The model and serial *are* reported via the `site_software_info` endpoint. RSD physical inspection required. |
| **Split-CT** | Firmware, serial, and calibration state are opaque. | Calibration tests can be detected via `needCtTest`, but actual drift cannot be evaluated remotely. |
| **Generator** | Firmware, brand, kW rating, and lifetime hours are opaque. | Configured locally by the installer. The API only tracks live running state. |
| **Smart Circuits** | Firmware, individual circuit current, and thermal state are opaque. | SC1+SC2 can be merged for 240V loads. Live current draw is only visible via Modbus or the local Smart Circuits app. |

## Library Implementation Note

This library does **not** hardcode these rules into Python. All region and accessory limitations are maintained within `franklinwh_cloud/const/device_catalog.json`. 

The `discover` command parses this JSON file and dynamically suppresses irrelevant API outputs, while rendering a `🌍 Region Details` notice and `⚠ API opaque` warnings using exactly the data stored in the catalog.
