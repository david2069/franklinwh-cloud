# `franklinwh-cli support` — Diagnostic Snapshot Reference

> **Status: Implemented** — Available in `franklinwh-cli`.
> Snapshot schema version: **3** (as of 2026-05-02).
> Supersedes the design proposal in [`archive/CLI_FUTURE_TODO.md`](archive/CLI_FUTURE_TODO.md).

The `support` command generates a **full-fidelity diagnostic snapshot** of a
FranklinWH gateway — hardware identity, live power state, battery health,
warranty analytics, TOU/tariff state, grid scheme enrolment, VPP programme
status, and global grid power limits — from a single CLI invocation.

The snapshot can be saved to JSON for offline analysis, redacted for sharing
with support teams, or compared against a prior snapshot to identify regressions.

---

## Commands

| Command | Description |
|---------|-------------|
| `franklinwh-cli support` | Full diagnostic snapshot — terminal output |
| `franklinwh-cli support --save` | Save snapshot JSON to `franklinwh_snapshot_<ts>_<serial>.json` |
| `franklinwh-cli support --redact` | Anonymise PII (serial, email, location) before display/save |
| `franklinwh-cli support --compare FILE` | Diff current snapshot against a saved snapshot |
| `franklinwh-cli support --info` | Topology tree + hardware summary + System Readiness |
| `franklinwh-cli support --info --diag` | Above + Feature Flags + System Relays |
| `franklinwh-cli support --info --json` | JSON export of topology object |
| `franklinwh-cli support --mock` | Instant simulated max-config output (no API calls) |

---

## Snapshot Architecture

The snapshot is a **client-side aggregation** — there is no single FranklinWH
API endpoint that returns a pre-composed support payload. The CLI calls ~20
individual REST/MQTT APIs and merges them into one structured document.

```
snapshot_version: 3
timestamp:        ISO-8601
gateway:          serial number
checksum:         sha256
data:
  identity        ← get_home_gateway_list()
  versions        ← get_agate_info() + siteinfo()
  network         ← get_network_info() + get_wifi_config_info()
  connectivity    ← get_agate_info() signal state
  power           ← get_device_composite_info() (cmdType 203)
  totals          ← get_device_composite_info() (cmdType 203)
  batteries       ← get_apower_info()
  relays          ← get_device_composite_info() + get_stats(electrical=True)
  electrical      ← get_stats(electrical=True) (cmdType 211)
  warranty        ← get_warranty_info() + computed analytics
  tou_status      ← get_gateway_tou_list()
  programmes      ← get_entrance_info() + get_programme_info()
                    + get_grid_profile_info() + get_power_control_settings()
                    + get_tou_dispatch_detail()
  api_health      ← client.get_metrics()
  schema_fingerprint ← derived
```

---

## Display Sections

### ⚡ Power

Live power flow snapshot from `getDeviceCompositeInfo` (cmdType 203).

| Field | Source | Notes |
|-------|--------|-------|
| Solar | `p_sun` | kW |
| Battery | `p_fhp` | kW (negative = charging) |
| Battery SoC | `soc` | % (on its own line, separate from Battery kW) |
| Grid | `p_uti` + grid state | kW + Connected/Disconnected |
| Home | `p_load` | kW |
| Mode | `work_mode_desc` | Time-Of-Use / Self-Consumption / Emergency Backup |
| TOU Programme | `tou_mode_desc` | Vendor tariff schedule name (e.g. "Ausgrid EA11 TOU") |
| Run Status | `run_status_desc` | Standby / Charging / Discharging / VPP Mode |
| Ambient Temp | `t_amb` | °C |
| Power Flow Breakdown | `gridChBat`, `soOutGrid`, `soChBat`, `batOutGrid` | kW flows |
| Signal | `wifiSignal`, `signal` | WiFi % + 4G dBm |

**aPower per-pack block:**

```
            aPower: [10050013A0XXXXXXXXXX, 10050013A0XXXXXXXXXX]
              SoC: 96.0%, 85.0%
              BMS: Charging, Standby
```

- Serials from `runtimeData.fhpSn`
- SoC from `runtimeData.fhpSoc` (per-pack)
- BMS decoded from `runtimeData.bms_work` using `BMS_STATE`: `{5: Standby, 6: Charging, 7: Discharging, 0: Off, 2: Fault, ...}`

---

### 📋 Warranty

Computed analytics on top of `get_warranty_info()` API data.

| Field | Meaning |
|-------|---------|
| Expires | Warranty expiry date |
| (days tag) | `X years, Y days  (N days) remaining` — or EXPIRED if past |
| Since Install | Days since `activatedDate`, formatted as `X years, Y days  (N,NNN days)` |
| Since PTO | Days since Permission to Operate date (from `get_tou_dispatch_detail`) |
| Throughput | `Rated kWh | Used kWh (%) | Remaining kWh (%)` |
| Avg Daily kWh | Average since install and/or PTO |
| Budget/day | `rated_kWh ÷ warranty_term` — the kWh/day the warranty **allows** |
| Remaining/day | `remaining_kWh ÷ days_to_expiry` — pace needed to exhaust budget by expiry |
| Per-device | Each aPower expiry date |

> [!NOTE]
> **Budget/day** and **Remaining/day** are distinct:
> - Budget/day = rated throughput spread evenly over the full warranty term
> - Remaining/day = how fast you need to use the remaining budget before expiry

**Example output:**

```
📋 Warranty
               Expires: 2036-07-22  10 years, 81 days  (3,734 days) remaining
          Since Install: 1 year, 285 days  (650 days)
             Since PTO: 1 year, 254 days  (619 days)
            Throughput: 43,000 kWh rated  | 6,217 kWh used (14.5%)  |  36,783 kWh left (85.5%)
          Avg Daily kWh: 9.57 kWh/day since install  |  10.05 kWh/day since PTO
            Budget/day: 11.79 kWh/day  (43,000 kWh ÷ 10 years, 0 days  (3,650 days) warranty term)
         Remaining/day: 9.85 kWh/day  (36,783 kWh remaining ÷ 10 years, 81 days  (3,734 days) to expiry)
               aGate X: Expires: 2036-07-22
              aPower X: Expires: 2036-07-22
```

---

### 🔌 Grid & Schemes

Sources: `get_entrance_info()` + `get_grid_profile_info()` + `get_tou_dispatch_detail()`

| Field | Source | Notes |
|-------|--------|-------|
| Grid Profile | `get_grid_profile_info()` | Actual profile name from API — never hardcoded |
| NEM Type | `nemType` from TOU dispatch | **US gateways only** — omitted for AU and other markets |
| DER Schedule | `template.derSchdule` | Only shown when not `"Other"` or blank |
| SGIP | `entrance.sgipEntrance` | Self-Generation Incentive Program (CA, US) |
| Backup Battery | `entrance.bbEntrance` | Backup Battery scheme |
| JA12 | `entrance.ja12Entrance` | JA12 grid compliance |
| SDCP | `entrance.sdcpFlag` | Smart Device Control Program |
| PCS | `entrance.pcsEntrance` | Power Control System |

Only **active/enrolled** scheme flags are shown (suppressed when `False`).

**Grid Power Limits** — decoded from `get_power_control_settings()`:

| Field | API key | Encoding |
|-------|---------|----------|
| Grid Import | `gridMax` | `-1` = Unlimited import, `0` = Charge from grid not allowed, `>0` = kW cap |
| Grid Export | `gridFeedMax` | `-1` = Unlimited export, `0` = Export not allowed, `>0` = kW cap |
| Global Charge | `globalGridChargeMax` | `-1` = Unlimited, `0` = Disabled |
| Global Export | `globalGridDischargeMax` | `-1` = Unlimited, `0` = Disabled |
| Solar Export | `notControlExportSolar` | Shown when `True` — solar export is unmetered/uncontrolled |
| Peak Demand | `peakDemandGridMax` | Only shown when not `None` |

> [!IMPORTANT]
> `get_power_control_settings()` is the **authoritative source** for grid limits —
> it is the same endpoint the FranklinWH mobile app uses. Values from `get_entrance_info()`
> may be stale; always trust `get_power_control_settings()` for display and control decisions.

**Example output:**

```
🔌 Grid & Schemes
      Grid Profile: AS/NZS 4777.2:2020
       Grid Import: Unlimited import
       Grid Export: 10.0 kW
    Global Charge: Unlimited
    Global Export: Unlimited
     Solar Export: Not controlled (solar export unmetered)
```

---

### 🏭 VPP Programme

Source: `get_programme_info()` + `vppSocVo` / `todayVppVo` from `get_tou_dispatch_detail()`

| Field | Source | Notes |
|-------|--------|-------|
| Enrolled | `flag` from `get_programme_info()` | `True/False` |
| Programme | `programName` | Vendor VPP programme name |
| Partner | `partnerName` | Utility/aggregator partner |
| VPP SoC | `vppSocVo.vppSoc` | Operating SoC target during VPP dispatch |
| VPP SoC range | `vppSocVo.vppMinSoc` / `vppMaxSoc` | Min/max SoC window |
| Today | `todayVppVo.vppFlag` | `⚡ VPP dispatch active today` if `True` |

**Example — enrolled:**

```
🏭 VPP Programme
          Enrolled: ✅ Virtual Peakers  (Ausgrid)
           VPP SoC: 20%  (range: 5% – 100%)
             Today: ⚡ VPP dispatch active today
```

**Example — not enrolled:**

```
🏭 VPP Programme
          Enrolled: Not enrolled
```

---

### 🏷️ TOU / Grid

Source: `get_gateway_tou_list()`

| Field | Notes |
|-------|-------|
| PTO Date | Permission to Operate date |
| Tariff | Plan name + electric company |
| Tariff Configured | `tariffSettingFlag` |
| Online | `onlineFlag` |
| Alert | `alertMessage` (if present) |
| Send Status | `sendStatus` — yellow "Pending" if set |
| Battery Capacity | `batteryRatedCapacity` kWh + aPower count |

---

## Country & Region Awareness

The snapshot captures `countryId` and `provinceId` from the gateway list.
The display layer uses these to suppress US/CA-specific fields for non-US gateways:

| Field | Shown for |
|-------|-----------|
| NEM Type (NEM 1.0 / 2.0 / 3.0) | US only (`countryId == 2`) |
| SGIP, ITC, isCalifornia flags | US only |
| Grid Profile | All countries (from real API, not hardcoded) |

---

## Snapshot JSON Structure

The snapshot JSON saved with `--save` has this top-level shape:

```json
{
  "snapshot_version": 3,
  "timestamp": "2026-05-02T12:19:43+00:00",
  "gateway": "10060006A0XXXXXXXXXX",
  "label": null,
  "checksum": "sha256:...",
  "data": {
    "identity": {
      "serial": "...", "model": "aGate X-01-AU", "sku": "...",
      "country": "Australia", "countryId": 3, "provinceId": 0,
      "timezone": "Australia/Sydney", "activatedDate": "2024-07-22"
    },
    "power": {
      "solar_kw": 1.2, "battery_kw": -0.7, "battery_soc": 96,
      "grid_kw": 0.0, "home_load_kw": 0.5,
      "operating_mode": "Time-Of-Use",
      "tou_mode_desc": "Ausgrid EA11 TOU",
      "run_status": "Charging",
      "apower_serials": ["10050013A0XXXXXXXXXX"],
      "apower_soc": [96.0],
      "apower_bms_mode": [6]
    },
    "warranty": {
      "expirationTime": "2036-07-22",
      "throughput_kWh": 43000,
      "used_kWh": 6217,
      "remainThroughput_kWh": 36783,
      "days_to_expiry": 3734,
      "days_since_install": 650,
      "days_since_pto": 619,
      "avg_kwh_per_day_install": 9.57,
      "avg_kwh_per_day_pto": 10.05,
      "daily_kwh_forecast": 11.79,
      "daily_rem_needed": 9.85,
      "total_warranty_days": 3650,
      "devices": [{"model": "aGate X", "expires": "2036-07-22"}]
    },
    "programmes": {
      "grid_profile": "AS/NZS 4777.2:2020",
      "sgip": false, "bb": false, "ja12": false,
      "sdcp": false, "pcs_enabled": true,
      "grid_limits_raw": {
        "gridMax": -1.0, "gridFeedMax": 10.0,
        "globalGridChargeMax": -1.0, "globalGridDischargeMax": -1.0,
        "notControlExportSolar": true
      },
      "vpp_enrolled": false,
      "vpp_programme_name": null, "vpp_partner_name": null,
      "nem_type": null
    },
    "tou_status": {
      "ptoDate": "2024-08-21",
      "tariffPlan": "Ausgrid EA11 TOU",
      "electricCompany": "Ausgrid",
      "tariffSettingFlag": true
    }
  }
}
```

---

## API Sources

All data is fetched per-gateway in `franklinwh_cloud/cli_commands/support.py`.

| API Call | Snapshot Key | Notes |
|----------|-------------|-------|
| `get_home_gateway_list()` | `identity` | countryId, provinceId now included |
| `get_agate_info()` | `versions` | Firmware versions |
| `get_network_info()` | `network` | WiFi/Eth/4G config |
| `get_device_composite_info()` | `power`, `totals`, `relays` | cmdType 203 + 211 |
| `get_stats(include_electrical=True)` | `electrical` | cmdType 211 — extended relays + measurements |
| `get_apower_info()` | `batteries` | Per-pack battery models |
| `get_warranty_info()` | `warranty` | Expiry + throughput; analytics computed locally |
| `get_gateway_tou_list()` | `tou_status` | Tariff, PTO date, alert state |
| `get_tou_dispatch_detail()` | `warranty` (PTO), `programmes` (VPP SoC, NEM, DER) | Called twice (ordering-safe) |
| `get_entrance_info()` | `programmes` | SGIP/BB/JA12/SDCP/PCS scheme flags |
| `get_programme_info()` | `programmes` | VPP enrollment + partner |
| `get_grid_profile_info(requestType=1)` | `programmes.grid_profile` | Actual profile name from API |
| `get_power_control_settings()` | `programmes.grid_limits_raw` | Authoritative grid power limits |
| `client.get_metrics()` | `api_health` | Call count, avg latency, errors |

---

## System Readiness Block (`--info` only)

Four health indicators are appended to every gateway in the topology tree:

| Indicator | ✅ Condition | ❌ Condition |
|-----------|-------------|-------------|
| `aGate` | `deviceStatus == 1` (Normal) | Any other status code |
| `aPower` | At least 1 battery SN in `runtimeData.fhpSn` | Empty array |
| `PCS Control` | `entrance.pcsEntrance == true` | Disabled / not provisioned |
| `TOU Schedule` | No `stopMode` flag set | `stopMode` active or Sync Pending |

---

## Feature Flags (`--info --diag`)

| Flag | Source | Notes |
|------|--------|-------|
| Solar | `runtimeData.installPv1Port`, `installPv2Port`, `installProximalsolar`, `solarHaveVo.remoteSolarEn` | Combination of ports shown |
| TOU/Tariff | `entrance.tariffSettingFlag` | |
| PCS Control | `entrance.pcsEntrance` | |
| Grid-Tied | `solarHaveVo.offGirdFlag` (permanent) + `offGridFlag` (live) | |
| MPPT | `entrance.mpptEnFlag` | DC-coupled solar |
| Three Phase | `runtimeData.isThreePhaseInstall` | |
| CT Split — Grid | `runtimeData.gridSplitCtEn` | |
| CT Split — PV | `runtimeData.pvSplitCtEn` | |
| Smart Circuits | Accessories API → MQTT `get_smart_circuits_info()` fallback | |
| V2L | Country + SC version + Generator presence | AU=no port; V2 SC=built-in; V1+Gen=CarSW |
| Generator Module | Accessories API `accessoryType` 201/203/301 | |
| Remote Solar (aPBox) | `solarHaveVo.remoteSolarEn` + DI/DO state | |
| aHub | `entrance.ahubAddressingFlag` | |
| VPP Programme | `get_programme_info().flag` | |

---

## Related Documentation

- [CLI Schema Command](CLI_SCHEMA_COMMAND.md) — Field-level API mapping (including grid limits)
- [CLI TOU Command](CLI_TOU_COMMAND.md) — TOU dispatch and scheduling
- [Discover vs Support](DISCOVER_VS_SUPPORT.md) — When to use each command
- [API Cookbook](API_COOKBOOK.md) — Transport architecture, gateway groups
