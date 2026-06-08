# Technical Analysis: Rapid Shutdown Devices (RSD), Multiple aHubs & aPower S MPPTs

This document provides a technical design and integration analysis for supporting **Rapid Shutdown Devices (RSD)**, **multiple aHub solar expansion modules**, and **DC-coupled MPPTs** on the aPower S in the `franklinwh-cloud` ecosystem. 

No code modifications are performed; this document acts as a blueprint for future library releases.

---

## 1. Rapid Shutdown Device (RSD) Support

A Photovoltaic Rapid Shutdown System (PVRSS) is a safety system mandated by NEC Article 690.12 to reduce PV array voltages to safe levels (<30V inside the array boundary) within seconds of initiation to protect first responders.

```
       [ PV Array ] ──── [ APsmart/Tigo Rooftop Receiver ]
                                │ (PLC Signal)
    [ aPower S (RSD Terminals) ] ◄── (120/240V AC power)
                │
                ▼ (No PLC Signal when transmitter is powered off)
    == PV Voltage drops to < 30V within 30 seconds ==
```

### A. Hardware Operation and Wiring
1. **Internal (Factory-Installed) Initiator:**
   - On single-battery installations co-located within line of sight of the service entrance, the physical **ON/OFF switch** on the side of the aPower S acts as the RSD trigger.
   - When switched OFF, the battery inverter shuts down, de-energizing the auxiliary RSD PWR terminals (120V or 240V AC output on the control board).
   - The loss of AC power shuts down the RSS transmitter (APsmart or Tigo PLC transmitter), causing the rooftop receivers to collapse array string voltages.
2. **External RSD Switch:**
   - Required for multi-battery configurations or when the battery is not located near the service entrance.
   - A Normally Closed (NC) outdoor-rated (NEMA 3R) switch (typically a red mushroom E-Stop) is wired back to the aGate EMS module using 24-16 AWG wire (max length 150 ft / 45.3 m):
     - **aGate 1.3.1 (AGT-R1V3-US):** Wired to `DI2` terminal block (labeled `EPO RSD`).
     - **aGate 1.3 (AGT-R1V2-US):** Wired to `DI1` terminal block (labeled `EPO DI 1`).
   - The factory jumper on these terminal blocks must be removed. Triggering the external switch breaks the loop, signaling the controller to drop the RSD power lines.

### B. API Mappings and Telemetry
*   **System Settings Configuration:**
    - Sourced from `GET /hes-gateway/terminal/system/getSystemSetting` (mapped to `get_system_settings()`).
    - The boolean field `rsdEnable` indicates whether the software has enabled the rapid shutdown monitor loop.
*   **Hardware Registry status:**
    - Accessory list returns MAC-1 serial and configuration info, but the RSD physical loop status is generally opaque on older gateways.
    - On newer EMS systems (aGate X), DI input states are reflected in telemetry registers.
*   **Downstream Library Recommendations:**
    - Report the `rsd_enabled` state under system settings.
    - Provide a boolean state flag `rsd_active` (if exposed in telemetry in future firmware) to alert integrations immediately when a rapid shutdown sequence has been initiated.

---

## 2. Multiple aHubs Solar Configuration

The aHub (`ACCY-AHUBV1-US`, Accessory Type `253`) functions as an expansion module. If the primary aGate inputs are fully occupied, multiple aHubs can be daisy-chained to support auxiliary solar arrays, generator interlocks, or smart circuits.

### A. Commissioning Interface & Port Parameters
Based on the FranklinWH Commissioning Guide, the system supports multiple aHub modules configured as **"1st - aHub"** and **"2nd - aHub"**.
- Each aHub exposes **three solar PV input ports**: Port 2, Port 3, and Port 4.
- Each port can be enabled/disabled independently and supports two parameters:
  1. **Rated Solar Power (kW):** Defines the capacity of the PV array connected to that specific port (e.g. `10 kW`).
  2. **Allow Solar Export to the Grid:** Boolean toggle (`Allowed` / `Disallowed`).

### B. API Mappings & Telemetry
- **Presence Detection:**
  - `ahubAddressingFlag` (integer/boolean) inside the `get_entrance_info()` response.
  - Sourced from the list of accessories (`get_accessories()`), each active aHub is returned as an element with `accessoryType = 253` and its respective serial number.
- **Port Configurations:**
  - Sourced from `/hes-gateway/common/getPowerCapConfigList`. This endpoint returns arrays of solar port allocations.
  - In a multi-aHub system, configuration details are indexed by parent accessory IDs.

### C. Physical Port Specifications Modeling
The aHub operates with 4 auxiliary ports, each with distinct hardware-level electrical capabilities and limitations as shown below:

| Port | Hardware Function | Overcurrent Protection Device (OCPD) | Maximum Continuous Rated Current |
|------|-------------------|--------------------------------------|-----------------------------------|
| **Port 1** | Smart Circuit (Load Control) | 60 A | 48 A |
| **Port 2** | PV (Solar Input) / Smart Circuit | 60 A | 48 A |
| **Port 3** | PV (Solar Input) / Smart Circuit | 60 A | 48 A |
| **Port 4** | Generator / V2L / PV / Smart Circuit | 100 A | 80 A |

Currently, neither the `device_models` SQLite DB schema nor the `device_catalog.json` constants file defines this port layout. To validate setups, prevent configuration issues, and correctly gate capabilities downstream, it is recommended to model these port constraints.

#### Recommendation: Database & Catalog Schema Expansion
Add port constraints inside the `capability_flags` JSON block of the `device_models` seed data:
```json
{
  "ports": {
    "1": { "supported_types": ["smart_circuit"], "max_ocpd_a": 60, "max_continuous_a": 48 },
    "2": { "supported_types": ["pv", "smart_circuit"], "max_ocpd_a": 60, "max_continuous_a": 48 },
    "3": { "supported_types": ["pv", "smart_circuit"], "max_ocpd_a": 60, "max_continuous_a": 48 },
    "4": { "supported_types": ["generator", "v2l", "pv", "smart_circuit"], "max_ocpd_a": 100, "max_continuous_a": 80 }
  }
}
```

### D. Downstream Library Recommendations
- Update `models.py` to structure the aHub parameters as a list of accessories:
  ```python
  @dataclass
  class AHubSolarPort:
      port_number: int          # 2, 3, or 4
      rated_power_kw: float
      export_allowed: bool
      
  @dataclass
  class AHubConfig:
      serial_number: str
      ports: list[AHubSolarPort]
  ```
- Expose these configurations in the CLI `discover` command output under a nested "aHub Solar Configuration" header.

---

## 3. aPower S Direct DC MPPTs

Unlike the older aPower 2 (which relies on external microinverters or AC-coupling through primary lines), the newer aPower S features integrated **Maximum Power Point Trackers (MPPTs)**, allowing solar panels to connect directly to the battery's DC bus.

### A. Commissioning Parameters
*   **Enabling MPPTs:**
    - Toggled individually per physical unit.
    - For mixed systems (e.g., an aPower 2 and an aPower S), the commissioning screen lists:
      - `1st - aPower 2 (SN: 123456789)`: Marked as `Unsupported` (no direct DC inputs).
      - `2nd - aPower S (SN: 123456789)`: Enabled/Disabled switch.
*   **Grid Export Permission:**
    - "Allow MPPT export to the grid? Allowed / Disallowed" toggle.

### B. API Mappings & Telemetry
- **MPPT Status:**
  - Sourced from the `get_device_info()` or composite stats.
  - `mpptEnFlag` (integer, e.g. `0` or `1`) indicates whether MPPT controls are active.
  - The live charging power on the MPPT bus is returned in telemetry under statistics current readings.

### C. Downstream Library Recommendations
- Update `get_device_info` schemas to distinguish battery capabilities:
  ```python
  @dataclass
  class APowerBattery:
      serial_number: str
      model: str               # "aPower 2" or "aPower S"
      mppt_capable: bool       # derived from model type
      mppt_enabled: bool       # derived from mpptEnFlag
      mppt_export_allowed: bool
  ```
- Integrate direct MPPT DC charging stats into `status` and `monitor` commands so users see a split of AC-coupled solar production (primary/aHub) vs. DC-coupled solar production (MPPT).

---

## 4. Execution Phases for Library Implementation

Should code changes be scheduled in the future, the following execution phases are recommended:

### Phase 1: Models & API Mapping Expansion
1. Update `models.py` with the expanded structured definitions for `AHubConfig`, `AHubSolarPort`, and capability fields for `APowerBattery`.
2. Expand `get_system_settings()` response parses to read and write `rsdEnable` and custom solar export states.

### Phase 2: CLI Subcommand Integrations
1. Update `discover.py` CLI command to list all configured aHubs and active solar ports with rated capacities.
2. Update `diag.py` CLI command to print current RSD monitor status (`rsdEnable`).
3. Update `monitor.py` / `status.py` to display separate lines for AC Solar vs. DC MPPT Solar power flow.

### Phase 3: Local FastAPI Emulator Updates
1. Add mock handlers in `emulator/main.py` mimicking a multi-aHub, mixed aPower 2 / aPower S installation.
2. Add mock JSON responses representing RSD switches being engaged (DI inputs failing) to test error handling logic.
