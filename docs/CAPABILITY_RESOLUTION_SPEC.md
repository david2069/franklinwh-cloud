# SDK Spec: Programmatic Capability Resolution

This design document specifies the capability resolution architecture within the `franklinwh-cloud` Python SDK. Downstream consumers (such as the `franklinwh-ha-integrator` Home Assistant integration, custom scripts, and the CLI) require a single, unified method to query the active capabilities of a gateway, rather than parsing multiple raw API endpoints and resolving regional hardware exceptions individually.

---

## 1. SDK Capability Resolution Architecture

The `franklinwh-cloud` client library will expose a single programmatic helper to resolve and freeze system capabilities based on live Cloud API responses.

```mermaid
flowchart TD
    Client[Client instance] -->|get_entrance_info| Ent[Entrance Data]
    Client -->|get_device_info| Dev[Device Data]
    Client -->|get_accessories| Acc[Accessories Data]
    
    Ent & Dev & Acc --> Resolver[SDK Capability Resolver]
    Resolver -->|Apply AU/US Region Exceptions| Final[ResolvedCapabilities Dataclass]
    Final -->|to_dict| JSON[Serialized JSON / Dictionary]
```

### Location in SDK
- **Data Model:** `franklinwh_cloud/models.py` (add `ResolvedCapabilities` dataclass).
- **Resolver Function:** `franklinwh_cloud/discovery.py` (implement capability compilation).
- **Client Interface:** `franklinwh_cloud/client.py` (add `get_resolved_capabilities()` async method).

---

## 2. Capability Schema & Rule Resolver

The SDK resolves a frozen `ResolvedCapabilities` snapshot by combining three endpoints:
1. `get_entrance_info()` (grid limits, solar port config, tariff configurations)
2. `get_device_info()` (battery counts, v2l configuration, system hardware version)
3. `get_accessories(option=0)` (smart circuit lists and generators)

### Python Dataclass Definition (`franklinwh_cloud/models.py`)
```python
@dataclass(frozen=True)
class ResolvedCapabilities:
    # Identity
    country_id: int            # 1=CN, 2=US, 3=AU (site location)
    agate_generation: int      # 1=Gen 1, 2=Gen 2 (derived from sysHdVersion)
    gateway_id: str            # Gateway serial number
    
    # Solar Capabilities
    solar_installed: bool      # Sourced from solarFlag / pv1Port / pv2Port
    pv1_installed: bool
    pv2_installed: bool
    has_mppt: bool             # Sourced from mpptEnFlag (aPower S support)
    has_apbox: bool            # Sourced from apbox20Num > 0
    
    # Accessories
    has_smart_circuits: bool   # Sourced from get_accessories() type=4
    circuit_count: int         # Sourced from country_id rules (3 for US, 2 for AU)
    has_generator: bool        # Sourced from get_accessories() type=3 / genEn
    has_v2l: bool              # Sourced from v2lModeEnable
    
    # Grid
    grid_connected: bool       # Sourced from gridFlag / offGridFlag
    three_phase: bool          # Sourced from isThreePhaseInstall
    
    # Pricing & VPP
    vpp_eligible: bool         # Sourced from checkUserVppEligibility()
    tariff_configured: bool    # Sourced from tariffSettingFlag
    
    def to_dict(self) -> dict:
        """Convert capabilities to a plain dictionary for API/CLI serialization."""
        ...
```

---

## 3. SDK Regional Exception Rules

To ensure correct status reporting across different international markets, the SDK resolver enforces regional overrides:

### Rule 1: Australian V2L Lock
*   **Condition:** `country_id == 3` (Australia).
*   **Logic:** Force `has_v2l = False` regardless of whether the API returns `v2lModeEnable = 1`.
*   **Rationale:** V2L functionality is physically disabled/uncertified on Australian hardware profiles.

### Rule 2: Australian Smart Circuit Channels
*   **Condition:** `country_id == 3`.
*   **Logic:** Limit `circuit_count = 2`.
*   **Rationale:** Australian smart circuit enclosures only support 2 control channels (Channel 3 controls are ignored or hidden).

### Rule 3: Off-Grid Installation Mode
*   **Condition:** `grid_connected == False` (islanded or off-grid configuration).
*   **Logic:** Disable `vpp_eligible = False`.
*   **Rationale:** VPP/DR events require a utility grid connection.

---

## 4. Downstream Integration Interface

Downstream clients (like the Home Assistant integration) can query this resolved state programmatically:

```python
# Programmatic SDK Usage Example
client = Client(auth, "10060006AXXXXXXXXX")
capabilities = await client.get_resolved_capabilities()

if capabilities.solar_installed:
    # Register solar sensors and energy telemetry entities
    ...
    
if capabilities.has_smart_circuits:
    # Register circuit relay controls up to capabilities.circuit_count channels
    ...
```

---

## 5. Test & Verification Plan

### Automated SDK Tests (`tests/test_capabilities.py`)
Write Python test cases asserting resolution correctness:
1.  **Test US Configuration:**
    *   Mock `countryId = 2`, `v2lModeEnable = 1`, and 3 smart circuits.
    *   Assert `has_v2l == True` and `circuit_count == 3`.
2.  **Test Australian Configuration Quirks:**
    *   Mock `countryId = 3`, `v2lModeEnable = 1`, and 3 smart circuits.
    *   Assert `has_v2l == False` (overridden) and `circuit_count == 2` (overridden).
3.  **Test Off-Grid Configuration:**
    *   Mock `gridFlag = 0`.
    *   Assert `vpp_eligible == False`.


---

## Smart Circuits: two protocol generations

Added 2026-09-14. **Design recorded ahead of implementation** — the newer path
has no captured evidence yet. See
[AP-14](../.agents/policies/evidence_standard.md).

### The situation

This library drives Smart Circuits with **cmdType 311**, whose schedule arrives
as flat parallel arrays (`SwNTime`, `SwNTimeEn`, `SwNTimeSet`). A third-party
fork drives them with **cmdType 387/389**, where the schedule arrives as a
structured `data["smartSwitch"][i]["schedule"]` object.

`SmartCircuitDetail` already bridges two *payload* shapes within 311 — V1
integer minute offsets and V2 datetime-string arrays. A 387/389 path would be a
third shape, and a different command, not merely another field layout.

### Why a hardware/region split is plausible

**CONFIRMED** from `FRANKLINWH_MODELS`:

| sysHdVersion | SKU | Model |
|---|---|---|
| 100 | `AGT-R1V1-US` | aGate X-10 |
| 101 | `AGT-R1V2-US` | aGate X-20 |
| 102 | `AGT-R1V1-AU` | aGate X-01-AU |
| 103, 104 | `AGT-R1V3-US` | aGate X 20 (US) |

**Australia has exactly one aGate SKU, on the oldest revision (R1V1). The US has
three, spanning R1V1 → R1V3.** Newer generations are US-only in the catalogue we
hold, which is consistent with a North-America-first rollout — and with a newer
Smart Circuits generation appearing there first.

Corroborating: `circuit_count` already varies by generation (2 on gen 1, 3 on
gen 2), so smart-circuit capability is *already* known to differ across
revisions.

**ASSUMED, not established:** that 387/389 belongs to newer hardware, or to a
"Smart Circuits V2" product generation, or is North-America-only. The SKU split
makes it plausible. It does not make it true.

### How to support both

The rule that matters: **do not key protocol selection off `sysHdVersion`.**

That mapping is precisely what we cannot verify — we have no capture pairing a
hardware revision with a 387 response. Encoding it would bake a guess into a
dispatch decision, where being wrong means sending an unrecognised command to
hardware that controls real loads.

Prefer, in order:

1. **Observed support.** If the gateway advertises which path it speaks — an
   accessory type, a capability flag, a protocol version — use that. Whether
   such a field exists is unknown; look for one in the settling capture.
2. **Probe and fall back.** Attempt the newer read (389, status — never a
   write), and fall back to 311 on rejection. Requires knowing how the gateway
   answers an unsupported cmdType; `franklinwh-local` documents a generic error
   frame (`9999`) on the local protocol, but whether the cloud path behaves the
   same is **unverified**.
3. **Explicit opt-in.** A caller-supplied flag until either of the above is
   established. Least magic, and honest about what is not known.

Whichever is chosen, 311 remains the default: it is the path with 283 captured
request/response pairs behind it.

### Shape of the change

- `ResolvedCapabilities` gains a smart-circuit protocol field, resolved by one
  of the mechanisms above rather than inferred from hardware.
- `SmartCircuitDetail` gains a third `from_*` constructor for the structured
  schedule; the existing V1/V2 bridging is untouched.
- The mixin dispatches on the resolved capability. `_update_smart_circuit_config`
  stays the 311 implementation.
- CLI output is unchanged in shape — a schedule renders the same whichever
  command supplied it.

### What settles it

One capture from a current app session touching Smart Circuits on a gateway that
uses the newer path. That yields the request shape, the response shape, the
schedule structure, and — if the session includes a schedule edit — resolves
`DEF-SC-TIMESET-UNDECIPHERED` and `FEAT-SC-SCHEDULE-SETTER` at the same time.

Until then this section is a plan, not a contract.
