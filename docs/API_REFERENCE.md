# API Method Reference

Complete reference for all `FranklinWHCloud` client methods — arguments, types, return values, and notes.

> 🔌 **OpenAPI Specification**: Building a client in another language (Go, Rust, JS)? Check out the massive 123-endpoint [franklinwh_openapi.json](franklinwh_openapi.json) spec dynamically generated from strict mobile app intercepts to bootstrap your external clients instantly.

## Connection

```python
import asyncio
from franklinwh_cloud import FranklinWHCloud

async def main():
    client = FranklinWHCloud(email="user@example.com", password="secret")
    await client.login()
    await client.select_gateway()   # auto-selects first gateway

    # ... call any method below ...

asyncio.run(main())
```

> **Config file alternative:** Place credentials in `franklinwh.ini` (see [SANDBOX_SETUP.md](SANDBOX_SETUP.md)).

---

## Device Discovery — `discover.py`

Structured device survey returning a `DeviceSnapshot` — usable as a Python API or via CLI.

| Method | Arguments | Returns | Description |
|--------|-----------|---------|-------------|
| `discover(tier=1)` | `tier: int` 1–3 | `DeviceSnapshot` | Full device discovery snapshot |

### Tiers

| Tier | CLI Flag | API Calls | Includes |
|------|----------|-----------|----------|
| 1 | (default) | ~7 | Site, aGate, batteries, feature flags, operating state, grid status, diagnostics |
| 2 | `-v` | ~14 | + per-aPower firmware, accessories, smart circuits config, warranty, grid profile, programmes, relays, TOU status |
| 3 | `-vv` | ~20 | + full aGate firmware (IBG/SL/AWS/App/Meter), NEM type, PTO date, site detail |

### `DeviceSnapshot` structure

| Category | Dataclass | Key fields |
|----------|-----------|------------|
| Site | `SiteInfo` | `address`, `timezone`, `country_id`, `pto_date` |
| aGate | `AgateInfo` | `serial`, `model`, `sku`, `firmware`, `generation`, `sim_status` |
| Batteries | `BatteryInfo` | `count`, `total_capacity_kwh`, `units[].soc`, `units[].fpga_ver` |
| Flags | `FeatureFlags` | `solar`, `off_grid`, `v2l_eligible`, `ct_split_grid`, `mac1_detected` |
| Accessories | `AccessoriesInfo` | `has_smart_circuits`, `smart_circuits.count`, `smart_circuits.v2l_port` |
| Grid | `GridInfo` | `connected`, `global_discharge_max_kw`, `feed_max_kw` |
| Warranty | `WarrantyInfo` | `expiry`, `remaining_kwh`, `installer_company` |
| Electrical | `ElectricalInfo` | `soc`, `operating_mode_name`, `relays`, `tou_status` |
| Programmes | `ProgrammeInfo` | `enrolled`, `program_name`, `vpp_soc` |

```python
snap = await client.discover(tier=2)
print(snap.agate.model)              # "aGate X-01-AU"
print(snap.batteries.total_capacity_kwh)  # 13.6
print(snap.flags.v2l_eligible)        # False
print(snap.warranty.remaining_kwh)    # 37164

# JSON export
import json
print(json.dumps(snap.to_dict(), indent=2))
```

---

## Power Flow & Runtime — `stats.py`

| Method | Arguments | Returns | Description |
|--------|-----------|---------|-------------|
| `get_stats()` | — | `Stats(Current, Totals)` | Full power snapshot: solar, battery, grid, home kW + daily kWh + SoC + mode + run status |
| `get_runtime_data()` | — | `dict` | Runtime data with relay states (similar to `get_device_composite_info`) |
| `get_power_by_day(dayTime)` | `dayTime: str` "YYYY-MM-DD" | `dict` | Power details for a specific day |
| `get_power_details(type, timeperiod)` | `type: int`, `timeperiod: str` | `dict` | Aggregated power data — see worked example below |

### `get_power_details()` — worked example

Pre-aggregated energy data from Franklin's servers. No client-side math needed.

| `type` | Period | `timeperiod` format | Example |
|--------|--------|---------------------|---------|
| 1 | Day | `YYYY-MM-DD` | `"2026-03-18"` |
| 2 | Week | `YYYY-MM-DD` (end of week) | `"2026-03-18"` |
| 3 | Month | `YYYY-MM-01` | `"2026-03-01"` |
| 4 | Year | `YYYY-01-01` | `"2026-01-01"` |
| 5 | Lifetime | Today's date | `"2026-03-18"` |

```python
import asyncio
from franklinwh_cloud import FranklinWHCloud

async def main():
    client = FranklinWHCloud(email="...", password="...")
    await client.login()
    await client.select_gateway()

    # Today's energy breakdown
    day = await client.get_power_details(type=1, timeperiod="2026-03-18")
    print(f"Solar:    {day.get('kwh_sun', 0):.1f} kWh")
    print(f"Grid ↓:   {day.get('kwh_uti_in', 0):.1f} kWh")
    print(f"Grid ↑:   {day.get('kwh_uti_out', 0):.1f} kWh")
    print(f"Battery:  {day.get('kwh_fhp_chg', 0):.1f} kWh charged")
    print(f"Home:     {day.get('kwh_load', 0):.1f} kWh consumed")

    # This year's totals
    year = await client.get_power_details(type=4, timeperiod="2026-01-01")
    print(f"\nYear-to-date solar: {year.get('kwh_sun', 0):.1f} kWh")

    # Lifetime totals
    from datetime import date
    lifetime = await client.get_power_details(type=5, timeperiod=str(date.today()))
    print(f"Lifetime solar: {lifetime.get('kwh_sun', 0):.1f} kWh")

asyncio.run(main())
```

### `Stats` data model fields

| Field path | Unit | Description |
|------------|------|-------------|
| `.current.solar_production` (`p_sun`) | kW | Solar PV power |
| `.current.battery_power` (`p_fhp`) | kW | Battery power (negative = charging) |
| `.current.grid_power` (`p_uti`) | kW | Grid power |
| `.current.home_consumption` (`p_load`) | kW | Home load |
| `.current.generator_power` (`p_gen`) | kW | Generator power |
| `.current.soc` | % | Battery state of charge |
| `.current.work_mode` | int | Operating mode (1=TOU, 2=Self, 3=Emergency) |
| `.current.work_mode_desc` | str | Mode name |
| `.current.run_status` | int | Run status code |
| `.current.run_status_desc` | str | Run status name |
| `.current.grid_status` | `GridStatus` | NORMAL / DOWN / OFF |
| `.current.ambient_temp` (`t_amb`) | °C | Ambient temperature |
| `.current.sw1_power` | kW | Smart circuit 1 |
| `.current.sw2_power` | kW | Smart circuit 2 |
| `.current.car_sw_power` | kW | V2L / car charger |
| `.totals.battery_charge` (`kwh_fhp_chg`) | kWh | Daily battery charge |
| `.totals.battery_discharge` (`kwh_fhp_di`) | kWh | Daily battery discharge |
| `.totals.grid_import` (`kwh_uti_in`) | kWh | Daily grid import |
| `.totals.grid_export` (`kwh_uti_out`) | kWh | Daily grid export |
| `.totals.solar` (`kwh_sun`) | kWh | Daily solar production |
| `.totals.home` (`kwh_load`) | kWh | Daily home consumption |

---

## Operating Mode — `modes.py`

| Method | Arguments | Returns | Description |
|--------|-----------|---------|-------------|
| `set_mode(...)` | See below | `bool` | Switch operating mode |
| `get_mode(requestedMode=None)` | `requestedMode: int` optional (1/2/3) | `dict` | Current or requested mode details incl. `soc`, `minSoc`, `maxSoc` |
| `update_soc(requestedSOC, workMode, electricityType)` | `requestedSOC: int` %, `workMode: int`, `electricityType: int` (default 1) | `dict` | Update backup reserve SoC setpoint |
| `get_mode_info(requested_work_mode=1)` | `requested_work_mode: int` (1/2/3) | `list[dict]` | Raw TOU list entry for specified mode |
| `get_all_mode_soc()` | — | `list[dict]` | Reserve SoC for all modes: `workMode`, `name`, `soc`, `minSoc`, `maxSoc`, `editSocFlag`, `active` |

### `set_mode()` arguments

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `requestedOperatingMode` | `int` or `str` | ✅ | `1`=TOU, `2`=Self-Consumption, `3`=Emergency Backup. Also accepts `tou_battery_import`, `tou_battery_export`, `tou_custom`, `tou_json` |
| `requestedSOC` | `int`, `str`, or `None` | TOU/Self only | Reserve SoC % (0–100). Accepts `"20"`, `20`, `"20%"`, `None` |
| `reqbackupForeverFlag` | `int` | Emergency only | `1`=Indefinite, `2`=Fixed duration |
| `reqnextWorkMode` | `int` | Emergency only | Next mode after backup: `1`=TOU, `2`=Self |
| `reqdurationMinutes` | `int` | Emergency w/ flag=2 | Duration 30–4320 minutes |

---

## TOU Scheduling — `tou.py`

| Method | Arguments | Returns | Description |
|--------|-----------|---------|-------------|
| `get_gateway_tou_list()` | — | `dict` | Full TOU config: currendId, mode list, timers, flags |
| `get_charge_power_details()` | — | `dict` | Charge power details |
| `save_tou_dispatch(payload)` | `payload: dict` full dispatch payload | `dict` | Submit raw TOU dispatch to aGate |
| `get_tou_dispatch_detail()` | — | `dict` | Current TOU dispatch template from aGate |
| `backup_tou_schedule(filename, payload)` | `filename: str` optional, `payload: dict` optional | `bool` | Write schedule backup to file |
| `get_tou_info(option)` | `option: int` 0=raw, 1=current+next, 2=full schedule | `dict` or `list` | TOU schedule info (parsed) |
| `set_tou_schedule(...)` | See below | `dict` | Set TOU schedule via high-level API |

### `set_tou_schedule()` arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `touMode` | `str` | — ✅ | `"CUSTOM"`, `"SELF"`, `"GRID_CHARGE"`, `"GRID_EXPORT"`, etc. |
| `touSchedule` | `list[dict]` | `None` | Schedule blocks (`detailVoList` format) |
| `operation` | `int` | `0` | 0=Set schedule |
| `default_mode` | `str` | `"SELF"` | Dispatch for non-specified time windows |
| `default_tariff` | `str` | `"OFF_PEAK"` | Tariff for non-specified windows |

> See [TOU_SCHEDULE_GUIDE.md](TOU_SCHEDULE_GUIDE.md) for dispatch codes, schema, and examples.

### Tariff Management Endpoints

These endpoints support the template-based tariff setup workflow used by the FranklinWH app. See [TOU_SCHEDULE_GUIDE.md § TOU Setup Workflows](TOU_SCHEDULE_GUIDE.md#tou-setup-workflows) for the full workflow diagram.

| Method | HTTP | Arguments | Returns | Description |
|--------|------|-----------|---------|-------------|
| `get_utility_companies(country_id, province_id)` | POST | `country_id: int`, `province_id: int`, `page_num: int`, `page_size: int` | `dict` | Search utility companies by region |
| `get_tariff_list(company_id)` | GET | `company_id: int`, `search_key: str` | `dict` | List tariff plans for a utility company |
| `get_tariff_detail(tariff_id)` | GET | `tariff_id: int` | `dict` | Full tariff template (seasons, rates, dispatch blocks) |
| `get_tou_detail_by_id(tou_id)` | POST | `tou_id: int`, `from_type: int` | `dict` | Get applied/saved TOU configuration by ID |
| `get_custom_dispatch_list(strategy_list)` | POST | `strategy_list: list` | `dict` | Valid dispatch codes for custom time blocks |
| `get_recommend_dispatch_list(strategy_list)` | POST | `strategy_list: list` | `dict` | AI-recommended dispatch codes |
| `calculate_expected_earnings(template)` | POST | `template: dict` | `dict` | Projected savings for a tariff template |
| `apply_tariff_template(template_id, name)` | POST | `template_id: int`, `name: str`, `work_mode: int`, `electricity_type: int` | `dict` | **WRITE** — Apply utility tariff template |
| `get_bonus_info()` | GET | — | `dict` | TOU bonus/incentive information |
| `get_vpp_tip()` | GET | — | `dict` | VPP participation tips |

> [!WARNING]
> `apply_tariff_template` is an **in-flight workflow API** — it requires prior steps (`get_utility_companies` → `get_tariff_list` → `get_tariff_detail`) to obtain a valid `template_id`. It is NOT suitable as a standalone CLI command.

---

## Power Control & PCS — `power.py`

| Method | Arguments | Returns | Description |
|--------|-----------|---------|-------------|
| `set_grid_status(status, soc=5)` | `status: GridStatus` (NORMAL/DOWN/OFF), `soc: int` | — | Go off-grid or restore grid |
| `get_grid_status()` | — | `dict` | `offgridSet`, `offGridState` |
| `get_power_control_settings()` | — | `dict` | Grid import/export kW limits |
| `set_power_control_settings(discharge, charge)` | `globalGridDischargeMax: float`, `globalGridChargeMax: float` | `dict` | Set grid export/import limits. `-1`=unlimited, `0`=disabled, `≥0.1`=kW limit |
| `get_pcs_hintinfo(dispatchIdList)` | `dispatchIdList: list[int]` | `dict` | PCS capability hints for dispatch IDs |

---

## Devices & Hardware — `devices.py`

| Method | Arguments | Returns | Description |
|--------|-----------|---------|-------------|
| `get_accessories(option=1)` | `option: int` 1=common, 2=IoT, 3=equipment, 4=IoT+gateway | `dict` | List of connected accessories |
| `get_device_composite_info()` | — | `dict` | Master data: runtime, mode, solar, alarms (used by `get_stats`) |
| `get_agate_info()` | — | `dict` | aGate firmware version, serial, network |
| `get_apower_info()` | — | `dict` | aPower battery details (capacity, serial, firmware) |
| `get_bms_info(apower_serial_no)` | `apower_serial_no: str` | `dict` | BMS cell voltages, temps, modules |
| `get_smart_circuits_info()` | — | `dict` | Raw smart circuit JSON blobs |
| `get_smart_circuits()` | — | `dict[int, SmartCircuitDetail]` | Parsed Smart Circuit config mapped natively bridging V1/V2 firmware gaps |
| `set_smart_circuit_state(circuit, turn_on)` | `circuit: int` (1-3), `turn_on: bool` | `dict` | Toggle individual smart circuit |
| `set_smart_circuit_soc_cutoff(circuit, enable, soc)` | `circuit: int` (1-3), `enable: bool`, `soc: int` | `dict` | Set automatic battery cutoff capacity |
| `set_smart_circuit_load_limit(circuit, max_amps)` | `circuit: int` (1-3), `max_amps: int` | `dict` | Set hardware amperage constraints (V1 Firmwares) |
| `set_smart_switch_state(state)` | `state: tuple` (SW1, SW2, SW3) — `True`=on, `False`=off, `None`=unchanged | `dict` | Legacy composite toggles |
| `get_device_info()` | — | `dict` | Detailed device info (v2) |
| `get_agate_network_info(requestType)` | `requestType: str` "1"=Network, "2"=Connectivity, "3"=WiFi | `dict` | aGate network/WiFi settings |
| `get_power_info()` | — | `dict` | Grid/load voltages, currents, frequencies, relay states |
| `get_accessories_power_info(option=1)` | `option: str` "0"=raw, "1"=Smart Circuits, "2"=V2L, "3"=Generator | `dict` | Accessory power and energy readings |
| `get_span_settings(requestType)` | `requestType: int` | `dict` | SPAN panel settings |
| `get_span_setting()` | — | `dict` | `{spanFlag: 0\|1}` — SPAN panel detected? |
| `get_generator_info()` | — | `dict` | Generator state info |
| `set_generator_mode(mode)` | `mode: int` 1=Auto, 2=Manual | `dict` | Set generator operating mode |

### LED Strip — `led_light_settings()`

```python
# Get current LED settings
result = await client.led_light_settings(mode="1", dataArea={})

# Set LED (on/off, colour, brightness, schedule)
result = await client.led_light_settings(mode="2", dataArea={
    "lightStat": 2,              # 1=Off, 2=On
    "timeEn": 1,                 # 0=Schedule off, 1=Schedule on
    "lightOpenTime": "06:00",    # HH:MM turn on
    "lightCloseTime": "22:00",   # HH:MM turn off
    "rgb": "FF6600",             # RGB colour (aPower 2/S only)
    "bright": 80,                # Brightness 0-100 (aPower 2/S only)
})
```

> aPower LED reference: https://www.franklinwh.com/support/overview/apower-led/

---

## Storm & Weather — `storm.py`

| Method | Arguments | Returns | Description |
|--------|-----------|---------|-------------|
| `get_storm_list(pageNum=1, pageSize=10)` | `pageNum: int`, `pageSize: int` | `dict` | Storm notification history |
| `get_progressing_storm_list()` | — | `dict` | Active storms (if any) |
| `get_weather()` | — | `dict` | Current brief weather |
| `get_storm_settings()` | — | `dict` | Storm Hedge configuration |
| `set_storm_settings(...)` | See below | `bool` | Configure Storm Hedge |

### `set_storm_settings()` arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `stormEn` | `int` | `None` | `1`=Enable, `0`=Disable Storm Hedge |
| `setAdvanceBackupTime` | `int` | `None` | Minutes before storm to start backup (30–300) |
| `stormNoticeEn` | `int` | `None` | `0`=Auto-activate, `1`=Ask each time |
| `advanceTime` | `int` | `None` | Notification lead time in minutes (5–30) |

> Storm Hedge reference: https://www.franklinwh.com/support/overview/storm-hedge

---

## Account & Notifications — `account.py`

| Method | Arguments | Returns | Description |
|--------|-----------|---------|-------------|
| `get_home_gateway_list()` | — | `dict` | All gateways on the account |
| `siteinfo()` | — | `dict` | User ID, email, roles, distributor info |
| `get_entrance_info()` | — | `dict` | SGIP, PCS, grid-tied flags, TOU tariff config |
| `get_unread_count()` | — | `dict` | Count of unread notifications |
| `get_notifications(pageNum=1, pageSize=10)` | `pageNum: int`, `pageSize: int` | `list` | Push notification messages |
| `get_notification_settings()` | — | `dict` | Notification event classifications |
| `get_site_and_device_info(**kwargs)` | `userId: str`, `email: str` (both optional) | `dict` | Full site + device inventory |
| `get_warranty_info()` | — | `dict` | Warranty dates, status |
| `get_equipment_location()` | — | `dict` | Equipment GPS coordinates |
| `get_user_resources()` | — | `dict` | User resource permissions |
| `get_alarm_codes_list()` | — | `list` | All alarm log entries |
| `get_programme_info()` | — | `list` | VPP / utility programme enrolment |
| `get_benefit_info()` | — | `dict` | Benefit (earnings) info |
| `get_gateway_alarm()` | — | `dict` | Active alarms on the gateway |
| `get_grid_profile_info(requestType=1)` | `requestType: int` 1=Compliance list, 2=Active details | `dict` | Grid compliance / utility profile |
| `get_geography_list(countryId=None)` | `countryId: int` optional | `dict` | States/provinces for a country |
| `get_backup_history(requestType, ...)` | `requestType: str` "1"=Summary "2"=Full, `pageNum: int`, `pageSize: int` | `dict` | Backup event history |

### Smart Assistant — `smart_assistant()`

```python
# Get example queries the AI can answer
examples = await client.smart_assistant(requestType="1")

# Ask a question
answer = await client.smart_assistant(requestType="2", query="What is my battery SoC?")
```

> ⚠️ Some commands may only execute on the mobile app.

---

## Method Count Summary

| Mixin | Methods | Category |
|-------|---------|----------|
| `discover.py` | 1 | Device discovery (3-tier survey) |
| `stats.py` | 4 | Power flow, runtime data |
| `modes.py` | 4 | Operating mode control |
| `tou.py` | 17 | TOU schedule + tariff management |
| `power.py` | 5 | Grid status, PCS settings |
| `devices.py` | 16 | Hardware, BMS, smart circuits, LED, generator |
| `storm.py` | 5 | Weather, Storm Hedge |
| `account.py` | 18 | Account, notifications, alarms, AI |
| **Total** | **70** | |
