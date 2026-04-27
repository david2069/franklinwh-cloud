# Operating Modes & Dynamic Discovery Guide

The FranklinWH Cloud API dictates that the list of available **Operating Modes** is not static. Downstream client integrations (such as Home Assistant or custom UIs) **must not** blindly hardcode all operating mode switches, as the FranklinWH aGate dynamically disables certain modes based on its physical wiring and installer setup.

To correctly present available operating modes to a user, clients must dynamically parse the Gateway Entrance topology.

---

## The Entrance API & Hardware Constraints

The availability of specific operating modes is constrained by the system's baseline capabilities, which are exposed via the Entrance response (often encapsulated in the initial login/site fetching process):

### 1. Grid-Tied Status
If the aGate is **permanently off-grid** (or not physically grid-tied):
- The system naturally cannot exchange power with a utility company. 
- You **cannot** set Grid-related Power Control System (PCS) settings like "Charge from Grid" or "Export to Grid".
- Time of Use (TOU) dispatch logic heavily dependent on rate offsets may not accurately dispatch if the system is mathematically isolated from utility bills.

### 2. Presence of Solar PV
If the aGate was **not** registered with an active Solar PV string / inverter:
- **Self-Consumption Mode** is structurally invalid and usually hidden or errored out.
- Installers can manually flag "Has Solar PV" within the provisioning portal if CTs are placed on third-party microinverters, which re-enables this mode capability. 

### 3. Time of Use (TOU) Context
If the system is grid-tied, the aGate will support rich TOU parameterization.
- TOU natively supports complex grid profiles (Flat Rate, Tiered Rate, True TOU).
- TOU mode acts as a master scheduling / dispatch engine. Customers can heavily customize these bands, meaning integrations must be aware when sending dynamic changes that TOU overrides PCS states temporally.

---

> [!IMPORTANT]  
> **The Emergency Fallback**  
> If an aGate is neither Grid-Tied (**False**) nor equipped with Solar PV (**False**), the firmware strictly restricts the system. The Cloud API will **only** validate and support the `Emergency Backup` mode. Any attempts by an API client to push an abstract `Self-Consumption` or `Load Shifting` Mode command to a mechanically isolated aGate will silently fail or reject.

## Client Responsibility
When building a custom dashboard (like the `franklinwh-ha-integrator`), perform the following on startup:
1. Hit the gateway/entrance discovery endpoints to retrieve the boolean definitions for `is_grid_tied` and `has_solar`.
2. Construct the mode drop-down menu dynamically based on those two booleans.
3. Fallback to *Emergency Backup Only* to prevent frustrating the end-user with broken/ignored commands.
