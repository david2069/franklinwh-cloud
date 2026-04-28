# `franklinwh support --info` — Site Topology & Diagnostic Reference

> **Status: Implemented** — Available in `franklinwh-cli` as of 2026-04-28.
> Supersedes the design proposal in [`archive/CLI_FUTURE_TODO.md`](archive/CLI_FUTURE_TODO.md).

The `support --info` family of commands provides a complete view of an account's
physical hardware topology — user → site → group → aGate → accessories — enriched
with live telemetry and installation state diagnostics.

---

## Commands

| Command | Description |
|---|---|
| `franklinwh support --info` | Topology tree + hardware summary + System Readiness |
| `franklinwh support --info --diag` | Above + Feature Flags inventory + System Relays |
| `franklinwh support --info --json` | JSON export of complete topology object |
| `franklinwh support --mock` | Instant simulated max-config output (no API calls) |

---

## Output Anatomy

### Standard `--info`

```
david@example.com (UserId: 21447)
└── Home (SiteId: 3447) — 123 Example Street, Sydney NSW
    └── FHP (aGate X-01-AU: 10060006A0XXXXXXXXXX)
        ├── Status: Discharging (Self-Consumption)
        ├── Grid: Connected
        ├── Solar PV: PV1 + Proximal (2.7 kW live)
        ├── Smart Circuit: Circuit 1 [Manual]
        ├── Smart Circuit: Circuit Test [Manual]
        ├── aPower (Serial: 10050013A0XXXXXXXXXX)
        ├── Lifecycle: Created 2024-04-23 | Activated 2024-07-22 | Expires 2036-07-22 | PTO: 2024-08-21
        ├── Grid Profile: User Defined
        ├── ✅ aGate: Normal
        ├── ✅ aPower: 1 unit(s), SoC 98.0%
        ├── ✅ PCS Control: Enabled
        └── ✅ TOU Schedule: Configured
```

### With `--diag`

The `--diag` flag appends two additional sub-sections per gateway, rendered
**after** the tree items:

```
        🏷️  Feature Flags
          ✅ Solar: PV1 + Proximal (AC-coupled)
          ✅ TOU/Tariff: Configured
          ✅ PCS Power Control: Enabled
          ✅ Grid-Tied: Connected
          ❌ MPPT (DC-coupled): Not available
          ❌ Three Phase: Single-phase
          ❌ CT Split — Grid: Not installed
          ❌ CT Split — PV: Not installed
          ✅ Smart Circuits: V1, 2 circuits (Circuit 1, Circuit Test)
              ❌ V2L: AU Smart Circuits have no V2L port
          ❌ Generator Module: Not installed
          ❌ Remote Solar (aPBox): Not connected
          ❌ aHub: Not detected
          ❌ VPP Programme: Not enrolled
        🔧  System Relays
                 Grid Relay: ○ OPEN
            Generator Relay: ● CLOSED
             Solar PV Relay: ○ OPEN
               Grid Relay 2: ○ OPEN
          Black Start Relay: ○ OPEN
           Solar PV Relay 2: ● CLOSED
           BFPV/aPBox Relay: ● CLOSED
```

---

## Group-Aware Topology

When a site has gateways assigned to named groups (i.e., any gateway returns
`groupFlag=1` from `get_home_gateway_list()`), the tree inserts a **Group tier**
between site and aGate:

```
└── Smallsville (SiteId: 1203)
      ├── Group: "Main House" (GroupId: 501)
      │     ├── FHP1 (aGate X-02-US: 10060006A0XXXXXXXXXX)
      │     └── FHP2 (aGate X-01-AU: 10060006A0XXXXXXXXXX)
      └── Group: (ungrouped)
            └── FHP3 (aGate X-01-AU: 10060006A0XXXXXXXXXX)
```

Single-gateway accounts and fully-ungrouped accounts show **no group tier** —
the tree goes directly from site to aGate.

> See also: [API Cookbook — Gateway Groups](API_COOKBOOK.md#gateway-groups--get_home_gateway_list-group-fields)
> for the authoritative description of `groupId` / `groupName` / `groupFlag` semantics.

---

## System Readiness Block (always shown)

Four health indicators are appended to every gateway's tree items regardless of
flags:

| Indicator | ✅ Condition | ❌ Condition |
|---|---|---|
| `aGate` | `deviceStatus == 1` (Normal) | Any other status code |
| `aPower` | At least 1 battery SN in `runtimeData.fhpSn` | Empty array |
| `PCS Control` | `entrance.pcsEntrance == true` | Disabled / not provisioned |
| `TOU Schedule` | No `stopMode` flag set | `stopMode` active or Sync Pending |

---

## Feature Flags (`--diag`)

| Flag | Source | Notes |
|---|---|---|
| Solar | `runtimeData.installPv1Port`, `installPv2Port`, `installProximalsolar`, `solarHaveVo.remoteSolarEn` | Combination of ports shown |
| TOU/Tariff | `entrance.tariffSettingFlag` | |
| PCS Control | `entrance.pcsEntrance` | |
| Grid-Tied | `solarHaveVo.offGirdFlag` (permanent) + `offGridFlag` (live) | |
| MPPT | `entrance.mpptEnFlag` | DC-coupled solar |
| Three Phase | `runtimeData.isThreePhaseInstall` | |
| CT Split — Grid | `runtimeData.gridSplitCtEn` | |
| CT Split — PV | `runtimeData.pvSplitCtEn` | |
| Smart Circuits | Accessories API → MQTT `get_smart_circuits_info()` fallback | AU accounts use MQTT path; trimmed to 2 circuits on AU hardware |
| V2L | Country + SC version + Generator presence | Logic: AU=no port; V2 SC=built-in; V1+Gen=CarSW; V1 only=not eligible |
| Generator Module | Accessories API `accessoryType` 201/203/301 | |
| Remote Solar (aPBox) | `solarHaveVo.remoteSolarEn` + DI/DO state | |
| aHub | `entrance.ahubAddressingFlag` | |
| VPP Programme | `get_programme_info().flag` | |

---

## System Relays (`--diag`)

| Label | Source |
|---|---|
| Grid Relay | `runtimeData.main_sw[0]` |
| Generator Relay | `runtimeData.main_sw[1]` |
| Solar PV Relay | `runtimeData.main_sw[2]` |
| Grid Relay 2 | `get_stats(include_electrical=True).current.grid_relay2` |
| Black Start Relay | `stats_ext.current.black_start_relay` |
| Solar PV Relay 2 | `stats_ext.current.pv_relay2` |
| BFPV/aPBox Relay | `stats_ext.current.bfpv_apbox_relay` |

Relay encoding: `1 = OPEN (○)`, `0 = CLOSED (●)` — i.e. `not bool(raw_value)`.

---

## `--mock` — Simulated Output

`franklinwh support --mock` prints a fully-fabricated max-configuration output
with no API calls, no credentials required. Use it to:

- Understand what each field looks like when present
- Verify output formatting after refactors (regression test)
- Demo the command to others without exposing real account data

The mock represents a fictional two-gateway grouped site with all accessories
installed: 3× aPower (inc. aPower S), aPBox, aHub, 3× Smart Circuits, Generator,
dual CT splits, three-phase, MPPT, V2L, and VPP enrolment.

Output is clearly bookended by yellow `⚠ SIMULATED DATA` banners.

---

## JSON Export

`franklinwh support --info --json` returns a structured topology object:

```json
{
  "email": "user@example.com",
  "userId": "12345",
  "sites": [
    {
      "siteName": "Home",
      "siteId": "3447",
      "completeAddress": "...",
      "groups": [],
      "gateways": [
        {
          "gatewayId": "10060006A0XXXXXXXXXX",
          "gatewayName": "FHP",
          "gatewayModel": "aGate X-01-AU",
          "group": null,
          "status": "Discharging (Self-Consumption)",
          "grid": { "label": "Connected", "connected": true },
          "solar": { "installed": true, "pv1": true, "pv2": false, "proximal": true, "remote": false, "live_kw": 2.7 },
          "ct_splits": { "grid": false, "pv": false },
          "ahub": false,
          "apbox": { "detected": false, "remote_solar": false },
          "mppt": { "enabled": false, "units": [] },
          "smart_circuits": [
            { "serial": null, "type": 302, "name": "Circuit 1", "mode": "Manual" }
          ],
          "v2l": {},
          "generator": {},
          "batteries": [
            { "type": "battery", "model": "aPower", "serial": "10050013A0XXXXXXXXXX" }
          ],
          "derating": {},
          "readiness": {
            "agate": { "ok": true, "label": "Normal" },
            "apower": { "count": 1 },
            "pcs": { "enabled": true },
            "tou": { "ok": true, "label": "Configured" }
          },
          "lifecycle": {
            "createdOn": "2024-04-23",
            "activatedOn": "2024-07-22",
            "expiresOn": "2036-07-22",
            "ptoDate": "2024-08-21"
          },
          "grid_profile": "User Defined",
          "relays": {
            "grid_1": false,
            "generator": true,
            "solar_pv_1": false,
            "grid_2": false,
            "black_start": false,
            "solar_pv_2": true,
            "apbox": true
          }
        }
      ]
    }
  ]
}
```

---

## API Sources

All data is fetched per-gateway within the `run_info()` function in
`franklinwh_cloud/cli_commands/support.py`. No new endpoints beyond the
standard discovery pipeline are required.

| API Call | Data Used |
|---|---|
| `get_home_gateway_list()` | Group metadata, lifecycle timestamps, hw_ver |
| `get_site_and_device_info()` | Site name, address, gateway list |
| `get_stats()` | Status, work mode, grid connection, SoC, basic relays |
| `get_stats(include_electrical=True)` | Extended relay states (diag only) |
| `get_device_composite_info()` | runtimeData (solar ports, CTs, V2L, generator), solarHaveVo |
| `get_entrance_info()` | aHub, PCS, MPPT, V2L enable, generator enable, tariff |
| `get_power_cap_config_list()` | aPower models, derating |
| `get_accessories(0)` | Smart Circuits, Generator (accessory type codes) |
| `get_smart_circuits_info()` | SC names + modes (AU MQTT fallback) |
| `get_gateway_tou_list()` | TOU sync status, stop mode, alert messages |
| `get_tou_dispatch_detail()` | PTO date |
| `get_warranty_info()` | Warranty expiry |
| `get_grid_profile_info()` | Active grid profile name |
| `get_programme_info()` | VPP enrolment (diag only) |

---

## Related Documentation

- [API Cookbook — Gateway Groups](API_COOKBOOK.md#gateway-groups--get_home_gateway_list-group-fields)
- [Discover vs Support](DISCOVER_VS_SUPPORT.md) — When to use each command
- [CLI Schema Command](CLI_SCHEMA_COMMAND.md) — Field-level API mapping
