# Fork Analysis: david2069 vs richo/franklinwh-python

**Date**: 2026-03-16

---

## Overview

| Metric | richo (original) | david2069 (fork) |
|--------|:-:|:-:|
| `client.py` lines | ~500 | **3,581** |
| `Current` dataclass fields | 11 | **45+** |
| `Totals` dataclass fields | 11 | **17** |
| Client methods | ~15 | **60+** |
| Exception classes | 4 | **10** |
| Constants/modes | inline in client.py | Extracted to `const/` package |
| Modules | `client.py`, `api.py`, `caching_thread.py` | `client.py`, `api.py`, `cli.py`, `const/`, `endpoints.py` |

---

## `get_stats()` Deep Comparison

### Original (richo)
```python
async def get_stats(self) -> Stats:
    tasks = [f() for f in [self.get_composite_info, self._switch_usage]]
    info, sw_data = await asyncio.gather(*tasks)    # Always 2 API calls
    data = info["runtimeData"]
    grid_status = GridStatus.from_offgridreason(data.get("offgridreason"))
    return Stats(Current(...11 fields...), Totals(...11 fields...))
```

- **Always** calls both `get_composite_info` + `_switch_usage` (MQTT 353) via `asyncio.gather`
- `generator_enabled` is a `bool` derived from `genStat > 1`
- No defensive `.get()` calls — will crash if keys missing
- No work mode, relay, or grid electrical data

### Fork (david2069)
```python
async def get_stats(self) -> Stats:
    res = await self.get_device_composite_info()   # REST, not MQTT
    # Conditionally fetch switch_usage only if smart circuits active
    if any(runtimedata_v2.get("pro_load", [0,0,0])):
        sw_data = await self._switch_usage()
    # Conditionally fetch power_info only if V2L or generator active
    if v2lRunState >= 1 or genEnable >= 1:
        power_info = await self.get_power_info()
    return Stats(Current(...45+ fields...), Totals(...17 fields...))
```

Key differences:

| Aspect | Original | Fork |
|--------|----------|------|
| **Primary API** | MQTT `get_composite_info` | REST `get_device_composite_info` |
| **API calls** | Always 2 (parallel) | 1–3 (conditional) |
| **Smart circuits** | Always fetched | Only if `pro_load` has active circuits |
| **Power info** | Not fetched | Only if V2L or generator enabled |
| **Null safety** | None — will crash on missing keys | All `.get()` with defaults |
| **Grid status** | `from_offgridreason()` static method | Inline mapping with `min(2, val)` cap |

### Additional Fields in Fork's `Current`

> [!IMPORTANT]
> The fork exposes **34 additional sensor values** not available in the original:

| Category | Fields Added |
|----------|-------------|
| **Operating mode** | `work_mode`, `work_mode_desc`, `device_status`, `tou_mode`, `tou_mode_desc`, `run_status`, `run_status_dec` |
| **Per-battery** | `apower_serial_numbers`, `apower_soc`, `apower_power`, `apower_bms_mode` |
| **Environment** | `agate_ambient_temparture` |
| **Relays** | `grid_relay1`, `generator_relay`, `solar_relay1`, `grid_relay2`, `black_start_relay`, `pv_relay2`, `bfpv_apbox_relay` |
| **Network** | `mobile_signal`, `wifi_signal`, `network_connection` |
| **V2L** | `v2l_enabled`, `v2l_status` |
| **Generator** | `generator_enabled` (int), `generator_status` |
| **Energy flow** | `grid_charging_battery`, `solar_export_to_grid`, `solar_charging_battery`, `battery_export_to_grid` |
| **Remote solar** | `apbox_remote_solar`, `remote_solar_enabled`, `remote_solar_pv1`, `remote_solar_pv2` |
| **MPPT** | `mppt_status`, `mppt_all_power`, `mppt_active_power`, `mpan_pv1_power`, `mpan_pv2_power` |
| **Grid electrical** | `grid_voltage1`, `grid_voltage2`, `grid_current1`, `grid_current2`, `grid_frequency`, `grid_set_frequency`, `grid_line_voltage`, `generator_voltage` |
| **Alarms** | `alarms_count` |

### Additional Fields in Fork's `Totals`

| Field | Source Key | Description |
|-------|-----------|-------------|
| `solar_load_kwh` | `kwhSolarLoad` | Solar → Home kWh |
| `grid_load_kwh` | `kwhGridLoad` | Grid → Home kWh |
| `battery_load_kwh` | `kwhFhpLoad` | Battery → Home kWh |
| `generator_load_kwh` | `kwhGenLoad` | Generator → Home kWh |
| `mpan_pv1_wh` | `mpanPv1Wh` | MPPT PV1 Wh |
| `mpan_pv2_wh` | `mpanPv2Wh` | MPPT PV2 Wh |

---

## Full Method Inventory

### Methods in Both (with differences noted)

| Method | Original | Fork | Notes |
|--------|:--------:|:----:|-------|
| `_post` | Simple, one variant | Complex, URL parsing, `**kwargs` for suppress flags | Fork also has `_post2` (original-style) |
| `_post_form` | ✅ | ✅ | Identical |
| `_get` | Simple | Complex, `**kwargs` for suppress flags | Fork also has `_get2` (original-style) |
| `refresh_token` | `get_token()` | `get_token(force_refresh=True)` | Fork forces fresh token |
| `get_accessories` | No params, returns `result` | `option=1..4`, returns full response | Fork supports 4 different accessory endpoints |
| `set_smart_switch_state` | ✅ | ✅ | Similar |
| `_status` | ✅ | ✅ | Identical MQTT 203 |
| `_switch_status` | ✅ | ✅ | Identical MQTT 311 |
| `_switch_usage` | ✅ | ✅ | Identical MQTT 353 |
| `set_mode` | Simple `_post_form` | **Massive** (260 lines), validates modes, handles backup-forever, duration, next-mode transitions | Completely rewritten |
| `get_mode` | Gets from MQTT 311 data | **200+ lines**, enriches with TOU schedule info, active period, alarms | Completely rewritten |
| `get_stats` | 2 parallel API calls, 11+11 fields | 1–3 conditional calls, 45+17 fields | See detailed comparison above |
| `_build_payload` | ✅ | ✅ | Minor encoding fix |
| `_mqtt_send` | ✅ | ✅ | Identical |
| `set_grid_status` | ✅ | ✅ | Identical |
| `get_home_gateway_list` | In Client | ✅ | Similar |

### Methods Only in Fork (46 additional)

#### Device & System Info
| Method | Description |
|--------|-------------|
| `get_device_composite_info` | REST replacement for MQTT composite info |
| `get_device_info` | Detailed gateway device information |
| `get_agate_info` | aGate-specific information |
| `get_apower_info` | aPower battery unit information |
| `get_bms_info(serial)` | Per-battery BMS details |
| `get_runtime_data` | Raw runtime data endpoint |
| `get_grid_status` | Read current grid/off-grid status |

#### TOU Schedule Management
| Method | Description |
|--------|-------------|
| `get_gateway_tou_list` | List all TOU schedules |
| `get_tou_info(option)` | Detailed TOU info (~300 lines!) |
| `get_tou_dispatch_detail` | Active TOU dispatch details |
| `set_tou_schedule(...)` | Create/modify TOU schedules (~500 lines) |
| `save_tou_dispatch(payload)` | Save dispatch configuration |
| `backup_tou_schedule(...)` | Backup TOU config to file |
| `get_charge_power_details` | Charge/discharge power limits |
| `update_soc(...)` | Update SoC reserve settings |
| `get_mode_info(work_mode)` | Mode-specific operating info |

#### Power Control & Grid
| Method | Description |
|--------|-------------|
| `get_power_control_settings` | Grid charge/discharge limits |
| `set_power_control_settings(...)` | Set grid power limits |
| `get_power_info` | Relay states, voltages, currents |
| `get_power_by_day(dayTime)` | Historical daily power data |
| `get_power_details(type, period)` | Detailed power breakdown |
| `get_accessories_power_info(option)` | Accessory power metrics |

#### Storm & Weather
| Method | Description |
|--------|-------------|
| `get_storm_list(...)` | Storm watch events |
| `get_progressing_storm_list` | Active storms |
| `get_weather` | Weather data for location |
| `get_storm_settings` | Storm watch configuration |
| `set_storm_settings(...)` | Configure storm watch |

#### Generator
| Method | Description |
|--------|-------------|
| `get_generator_info` | Generator state and settings |
| `set_generator_mode(mode)` | Control generator operation |

#### Network & Hardware
| Method | Description |
|--------|-------------|
| `get_agate_network_info(type)` | Network diagnostics |
| `get_span_settings(type)` | SPAN panel configuration |
| `get_span_setting` | SPAN panel detection flag |
| `led_light_settings(mode, data)` | LED indicator control |
| `get_grid_profile_info(type)` | Grid profile/standards info |

#### Account & Site
| Method | Description |
|--------|-------------|
| `siteinfo` | Site/location information |
| `get_site_and_device_info(...)` | Multi-site device inventory |
| `get_warranty_info` | Warranty and throughput data |
| `get_equipment_location` | Equipment GPS/location |
| `get_user_resources` | User account resources |
| `get_entrance_info` | Account entrance/login info |

#### Notifications & Alarms
| Method | Description |
|--------|-------------|
| `get_unread_count` | Unread notification count |
| `get_notifications(...)` | Paginated notifications |
| `get_notification_settings` | Notification preferences |
| `get_alarm_codes_list` | Known alarm code definitions |
| `get_gateway_alarm` | Active gateway alarms |
| `get_backup_history(...)` | Backup event history |

#### Other
| Method | Description |
|--------|-------------|
| `get_programme_info` | VPP programme info |
| `get_benefit_info` | Energy benefit/savings info |
| `get_geography_list(country)` | Geography/region data |
| `smart_assistant(...)` | AI assistant queries |
| `get_smart_circuits_info` | Smart circuit configuration |
| `set_pcs_hint_info(...)` | PCS dispatch hint configuration |
| `get_pcs_hintinfo(...)` | PCS hint information |

### Methods Only in Original

| Method | Description |
|--------|-------------|
| `get_smart_switch_state` | Read switch states (fork removed) |
| `set_generator` | Simple enable/disable (fork uses `set_generator_mode`) |
| `get_composite_info` | Renamed to `get_device_composite_info` in fork |

### Architectural Differences

| Feature | Original | Fork |
|---------|----------|------|
| `HttpClientFactory` | Abstract factory pattern for httpx clients | Removed, direct `httpx.AsyncClient` |
| `CachingThread` | Background polling thread with locking | Not used |
| `SwitchState` | Named tuple subclass | Removed |
| `TokenFetcher` | Inherits `HttpClientFactory` | Standalone class with `access_token` property |
| Constants | Inline `MODE_MAP` etc. in client.py | Extracted to `const/` package |
| CLI | None | Full CLI with `argparse` (728 lines) |
| Endpoints | Inline URLs | Separate `endpoints.py` |

---

## Future Optimisation Opportunities

> [!NOTE]
> The fork is feature-rich but has significant opportunities for performance and observability work.

### 1. Performance

| Area | Current State | Recommendation |
|------|---------------|----------------|
| **`get_stats` API calls** | 1–3 sequential calls | Use `asyncio.gather` for parallel calls when multiple needed |
| **HTTP session** | Single persistent session, no pool tuning | Configure connection pool limits, keep-alive, and timeouts |
| **`get_tou_info`** | ~300 lines, heavy parsing inline | Cache TOU info (changes rarely), separate parser class |
| **`set_tou_schedule`** | ~500 lines in one method | Break into smaller composable methods |
| **Token refresh** | On-demand with retry | Proactive refresh before expiry using token TTL |
| **Unnecessary imports** | Test fixtures imported in client.py | Lazy-load or remove from client.py |

### 2. Metrics & Observability

Currently the fork has **zero instrumentation**. Recommended additions:

```python
@dataclass
class ClientMetrics:
    start_time: float
    total_api_calls: int = 0
    calls_by_endpoint: dict[str, int]       # e.g. {"getDeviceCompositeInfo": 142}
    errors_by_type: dict[str, int]          # e.g. {"timeout": 3, "401": 1}
    total_errors: int = 0
    total_timeouts: int = 0
    total_retries: int = 0
    avg_response_time_ms: float = 0.0
    response_times_by_endpoint: dict[str, list[float]]
    last_successful_call: float | None = None
    last_error_time: float | None = None
    token_refreshes: int = 0
    uptime_seconds: float                   # time.time() - start_time
```

**Implementation approach**: Wrap `_post`, `_get`, and `retry` with timing decorators that update a `ClientMetrics` instance. Expose via a `client.metrics` property.

### 3. Code Quality

| Issue | Impact | Effort |
|-------|--------|--------|
| `client.py` is 3,581 lines | Hard to navigate/test | Split into modules: `client.py`, `tou.py`, `power.py`, `device.py` |
| `_post` / `_post2` and `_get` / `_get2` coexist | Confusing which to use | Consolidate to single implementations |
| Many `print()` statements | Debug noise in production | Replace with `logger.debug()` |
| No type hints on many returns | Poor IDE support | Add `-> dict` / `-> list` hints |
| Hardcoded URL construction | Fragile | Use `endpoints.py` constants consistently |
| `generator_enabled` changed from `bool` to `int` | Breaking for original HA integration | Document or add compat property |

---

## Summary

The fork is a **7× expansion** of the original library, transforming it from a minimal HA sensor poller into a comprehensive energy management API client with TOU scheduling, power control, storm watch, notifications, and deep device introspection. The `get_stats` function alone went from 11+11 fields to 45+17 fields, with smart conditional API calls to avoid unnecessary network traffic.

The main areas for optimisation are: **parallelising API calls**, **adding metrics instrumentation**, and **modularising the 3,581-line monolith** into domain-focused modules.
