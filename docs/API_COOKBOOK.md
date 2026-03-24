# API Cookbook

Practical recipes for the FranklinWH Cloud API. Each recipe is copy-paste ready.

> **Prerequisites:** See [SANDBOX_SETUP.md](SANDBOX_SETUP.md) for venv and credentials setup.
> **Full method reference:** See [API_REFERENCE.md](API_REFERENCE.md) for all 70+ methods with args.

---

## Connection Preamble

All recipes start with this. Copy once, paste at the top of your script:

```python
import asyncio
from franklinwh_cloud import FranklinWHCloud

async def main():
    client = FranklinWHCloud(email="user@example.com", password="secret")
    await client.login()
    await client.select_gateway()   # auto-selects first gateway

    # ... your recipe code here ...

asyncio.run(main())
```

Or load from config file:

```python
from franklinwh_cloud import FranklinWHCloud

client = FranklinWHCloud.from_config("franklinwh.ini")
```

---

## Quick Reference

One-liner recipes. All assume `client` is connected (see preamble above).

### Power Flow & Status

```python
stats = await client.get_stats()

# Instantaneous power (kW)
solar_kw     = stats.current.solar_production    # p_sun
battery_kw   = stats.current.battery_power       # p_fhp (negative = charging)
grid_kw      = stats.current.grid_power          # p_uti
home_kw      = stats.current.home_consumption    # p_load
soc          = stats.current.soc                 # Battery %

# Operating state
mode_name    = stats.current.work_mode_desc      # "Self Consumption"
run_status   = stats.current.run_status_desc     # "Normal operation"
grid_status  = stats.current.grid_status         # GridStatus.NORMAL

# Daily totals (kWh)
solar_kwh    = stats.totals.solar                # kwh_sun
grid_in_kwh  = stats.totals.grid_import          # kwh_uti_in
grid_out_kwh = stats.totals.grid_export          # kwh_uti_out
bat_chg_kwh  = stats.totals.battery_charge       # kwh_fhp_chg
bat_dis_kwh  = stats.totals.battery_discharge    # kwh_fhp_di
home_kwh     = stats.totals.home                 # kwh_load
```

### Operating Mode

```python
from franklinwh_cloud.const import (
    TIME_OF_USE, SELF_CONSUMPTION, EMERGENCY_BACKUP,  # 1, 2, 3
)

# Get current mode
mode = await client.get_mode()
print(f"Mode: {mode['modeName']}, Run: {mode['run_desc']}")

# Get reserve SoC for all modes
soc_all = await client.get_all_mode_soc()
# Returns: [{'workMode': 1, 'name': 'Time of Use', 'soc': 7.0, ...}, ...]

# Switch to Self-Consumption, keep current SoC
await client.set_mode(SELF_CONSUMPTION, None, None, None, None)
#                     workMode=2        soc  forever nextMode duration

# Switch to Emergency Backup — indefinite
await client.set_mode(EMERGENCY_BACKUP, None, 1, SELF_CONSUMPTION, None)
#                     workMode=3        soc  forever=1 nextMode=2   duration

# Switch to Emergency Backup — 2 hours, then revert to Self-Consumption
await client.set_mode(EMERGENCY_BACKUP, None, 2, SELF_CONSUMPTION, 120)
#                     workMode=3        soc  timed=2  nextMode=2    mins

# Update backup reserve SoC to 20% for Self-Consumption mode
await client.update_soc(requestedSOC=20, workMode=SELF_CONSUMPTION)
#                                        workMode=2
```

### TOU Scheduling

```python
from franklinwh_cloud.const import (
    dispatchCodeType,  # SELF=6, GRID_CHARGE=8, GRID_EXPORT=7, ...
    WaveType,          # OFF_PEAK=0, MID_PEAK=1, ON_PEAK=2, SUPER_OFF_PEAK=4
)

# View current schedule
schedule = await client.get_tou_dispatch_detail()

# Set full-day self-consumption
await client.set_tou_schedule(touMode="SELF")

# Set grid charge window 11:30–15:00, rest = self-consumption
await client.set_tou_schedule(
    touMode="CUSTOM",
    touSchedule=[{
        "startTime": "11:30", "endTime": "15:00",
        "dispatchId": dispatchCodeType.GRID_CHARGE.value,   # 8 = aPower charges from solar+grid
        "tWaveTypeId": WaveType.OFF_PEAK.value,             # 0 = Off-peak pricing tier
    }],
    default_mode="SELF",       # Outside window = self-consumption
)
```

> **Dispatch codes** — see [reference table](#dispatch-code-reference) below.

### Power Control (PCS)

```python
from franklinwh_cloud.models import GridStatus

# Get current grid import/export limits
pcs = await client.get_power_control_settings()

# Set grid export max to 5 kW, import unlimited
await client.set_power_control_settings(
    globalGridDischargeMax=5.0,   # export limit kW (-1=unlimited, 0=disabled)
    globalGridChargeMax=-1,       # import limit kW (-1=unlimited, 0=disabled)
)

# Go off-grid (simulate outage — opens grid contactor)
await client.set_grid_status(GridStatus.OFF, soc=5)
#                            GridStatus.OFF=2  minimum SoC

# Restore grid connection
await client.set_grid_status(GridStatus.NORMAL)
#                            GridStatus.NORMAL=0
```

### Devices & BMS

```python
# Get aGate info (firmware, serial)
agate = await client.get_agate_info()

# Get aPower battery info (capacity, serial)
apower = await client.get_apower_info()

# Get BMS cell data for a specific battery
bms = await client.get_bms_info("APOWER_SERIAL_NUMBER")

# Get smart circuit states
circuits = await client.get_smart_circuits_info()

# Toggle smart switch 1 ON, switch 2 OFF, switch 3 unchanged
await client.set_smart_switch_state((True, False, None))

# Get relay states + grid voltage/current/frequency
power_info = await client.get_power_info()

# Device discovery — structured snapshot of entire system
snapshot = await client.discover(tier=2)  # tier 1=basic, 2=verbose, 3=pedantic
print(f"aGate: {snapshot.agate.model}, aPowers: {snapshot.batteries.count}")
```

### LED Strip

```python
# Get current LED settings
led = await client.led_light_settings(mode="1", dataArea={})

# Turn LED on with colour and brightness (aPower 2/S)
await client.led_light_settings(mode="2", dataArea={
    "lightStat": 2,              # 1=Off, 2=On
    "rgb": "FF6600",             # Hex colour
    "bright": 80,                # Brightness 0-100
    "timeEn": 1,                 # 0=No schedule, 1=Schedule enabled
    "lightOpenTime": "06:00",
    "lightCloseTime": "22:00",
})
```

### Smart Assistant (AI)

```python
# Get example queries
examples = await client.smart_assistant(requestType="1")  # 1=list examples

# Ask a question
answer = await client.smart_assistant(requestType="2", query="What is my battery level?")
#                                     requestType="2"  # 2=ask question
print(answer)
```

> ⚠️ Some AI commands may only execute on the mobile app.

### Historical Energy Data

```python
from datetime import date

# Today's energy breakdown
day = await client.get_power_details(type=1, timeperiod="2026-03-18")
#                                   type=1  # DAY — hourly breakdown

# This week
week = await client.get_power_details(type=2, timeperiod="2026-03-18")
#                                     type=2  # WEEK — daily breakdown

# This month
month = await client.get_power_details(type=3, timeperiod="2026-03-01")
#                                      type=3  # MONTH — daily breakdown

# This year
year = await client.get_power_details(type=4, timeperiod="2026-01-01")
#                                     type=4  # YEAR — monthly breakdown

# Lifetime totals
lifetime = await client.get_power_details(type=5, timeperiod=str(date.today()))
#                                         type=5  # LIFETIME — all-time
```

### Weather & Storm Hedge

```python
weather = await client.get_weather()
storms = await client.get_storm_settings()

# Enable Storm Hedge, 60 min advance backup
await client.set_storm_settings(
    stormEn=1,                  # 0=Disabled, 1=Enabled
    setAdvanceBackupTime=60,    # Minutes before storm to switch to backup
)
```

### Account & Notifications

```python
# List all gateways on account
gateways = await client.get_home_gateway_list()

# Get unread notification count
unread = await client.get_unread_count()

# Get recent notifications
notes = await client.get_notifications(pageNum=1, pageSize=20)

# Get warranty info
warranty = await client.get_warranty_info()

# Site info (user ID, roles, distributor)
site = await client.siteinfo()
```

---

## Full Example: System Dashboard with SoC Estimation

A complete script that displays power flow, operating state, and estimates time to full charge or reserve SoC.

```python
import asyncio
from franklinwh_cloud import FranklinWHCloud

RESERVE_SOC = 20    # Your backup reserve %
BATTERY_KWH = 13.6  # aPower 2 capacity (check get_apower_info for yours)

async def main():
    client = FranklinWHCloud.from_config("franklinwh.ini")
    await client.login()
    await client.select_gateway()

    stats = await client.get_stats()
    c = stats.current
    t = stats.totals

    # ── Power Flow ──
    print("⚡ Power Flow (kW)")
    print(f"  Solar:   {c.solar_production:6.2f} kW")
    print(f"  Battery: {c.battery_power:6.2f} kW  {'⬇ charging' if c.battery_power < 0 else '⬆ discharging'}")
    print(f"  Grid:    {c.grid_power:6.2f} kW")
    print(f"  Home:    {c.home_consumption:6.2f} kW")
    print()

    # ── Status ──
    print(f"🔋 Battery: {c.soc:.0f}%")
    print(f"📋 Mode:    {c.work_mode_desc}")
    print(f"🏃 Status:  {c.run_status_desc}")
    print(f"🔌 Grid:    {c.grid_status.name}")
    print()

    # ── SoC Time Estimation ──
    bat_kw = abs(c.battery_power)
    if bat_kw > 0.05:  # ignore noise below 50W
        current_kwh = (c.soc / 100) * BATTERY_KWH
        if c.battery_power < 0:  # Charging
            remaining_kwh = BATTERY_KWH - current_kwh
            hours = remaining_kwh / bat_kw
            h, m = int(hours), int((hours % 1) * 60)
            print(f"⏱️  Estimated ~{h}h {m}m to 100%  (at {bat_kw:.1f} kW)")
        else:  # Discharging
            usable_kwh = current_kwh - (RESERVE_SOC / 100) * BATTERY_KWH
            if usable_kwh > 0:
                hours = usable_kwh / bat_kw
                h, m = int(hours), int((hours % 1) * 60)
                print(f"⏱️  Estimated ~{h}h {m}m to reserve ({RESERVE_SOC}%)  (at {bat_kw:.1f} kW)")
            else:
                print(f"⚠️  Battery at or below reserve ({RESERVE_SOC}%)")
    else:
        print("⏸️  Battery idle")

    print()

    # ── Daily Totals ──
    print("📊 Today (kWh)")
    print(f"  Solar:      {t.solar:6.1f}")
    print(f"  Grid in:    {t.grid_import:6.1f}")
    print(f"  Grid out:   {t.grid_export:6.1f}")
    print(f"  Bat charge: {t.battery_charge:6.1f}")
    print(f"  Bat disc:   {t.battery_discharge:6.1f}")
    print(f"  Home:       {t.home:6.1f}")

asyncio.run(main())
```

**Expected output:**
```
⚡ Power Flow (kW)
  Solar:     4.20 kW
  Battery:  -2.10 kW  ⬇ charging
  Grid:      0.00 kW
  Home:      2.10 kW

🔋 Battery: 72%
📋 Mode:    Self Consumption
🏃 Status:  Normal operation
🔌 Grid:    NORMAL

⏱️  Estimated ~1h 49m to 100%  (at 2.1 kW)

📊 Today (kWh)
  Solar:       18.3
  Grid in:      2.1
  Grid out:     0.0
  Bat charge:   8.4
  Bat disc:     5.2
  Home:        12.0
```

---

## Full Example: Force Charge via Custom TOU

Set a grid charge window, verify it applied, then restore self-consumption.

```python
import asyncio
from franklinwh_cloud import FranklinWHCloud
from franklinwh_cloud.const import dispatchCodeType, WaveType

async def main():
    client = FranklinWHCloud.from_config("franklinwh.ini")
    await client.login()
    await client.select_gateway()

    # ── Step 1: Set grid charge 11:30–15:00 ──
    print("Setting grid charge window 11:30–15:00...")
    result = await client.set_tou_schedule(
        touMode="CUSTOM",
        touSchedule=[{
            "startTime": "11:30",
            "endTime": "15:00",
            "dispatchId": dispatchCodeType.GRID_CHARGE.value,  # 8 = aPower charges from solar+grid
            "tWaveTypeId": WaveType.OFF_PEAK.value,            # 0 = Off-peak pricing tier
        }],
        default_mode="SELF",       # Outside window = self-consumption (dispatchId=6)
    )
    tou_id = result.get("result", {}).get("id", "?")
    print(f"✓ Schedule submitted — touId={tou_id}")

    # ── Step 2: Verify ──
    import asyncio as aio
    await aio.sleep(5)  # Give aGate time to apply

    detail = await client.get_tou_dispatch_detail()
    blocks = detail.get("result", {}).get("detailVoList", [])
    print(f"\nActive schedule ({len(blocks)} blocks):")
    for b in blocks:
        name = b.get("dispatchName", "?")
        start = b.get("startTime", "?")
        end = b.get("endTime", "?")
        print(f"  {start}–{end}  {name}")

    # ── Step 3: Restore full-day self-consumption ──
    input("\nPress Enter to restore self-consumption...")
    await client.set_tou_schedule(touMode="SELF")
    print("✓ Restored to full-day self-consumption")

asyncio.run(main())
```

> **CAUTION:** This script modifies your live aGate TOU schedule. Test during off-peak hours.
> See [TOU_SCHEDULE_GUIDE.md](TOU_SCHEDULE_GUIDE.md) for dispatch codes, known limitations, and the 30-minute boundary rule.

---

## Dispatch Code Reference

| Code | `dispatchCodeType` Enum | Description |
|------|------------------------|-------------|
| 1 | `HOME` / `HOME_LOADS` | aPower to home (surplus solar to grid) |
| 2 | `STANDBY` | aPower on standby (surplus solar to grid) |
| 3 | `SOLAR` / `SOLAR_CHARGE` | aPower charges from solar |
| 6 | `SELF` / `SELF_CONSUMPTION` | Self-consumption (surplus solar to grid) |
| 7 | `GRID_EXPORT` / `GRID_DISCHARGE` / `FORCE_DISCHARGE` | aPower to home/grid |
| 8 | `GRID_CHARGE` / `GRID_IMPORT` / `FORCE_CHARGE` | aPower charges from solar/grid |

## Wave Type (Pricing Tier) Reference

| Code | `WaveType` Enum | Description |
|------|----------------|-------------|
| 0 | `OFF_PEAK` | Off-peak pricing tier |
| 1 | `MID_PEAK` | Mid-peak pricing tier |
| 2 | `ON_PEAK` | On-peak pricing tier |
| 4 | `SUPER_OFF_PEAK` | Super off-peak pricing tier |

## Work Mode Reference

| Code | `workModeType` Enum | Constant | Description |
|------|--------------------|-----------|----|
| 1 | `TIME_OF_USE` | `TIME_OF_USE` | TOU dispatch schedule controls the battery |
| 2 | `SELF_CONSUMPTION` | `SELF_CONSUMPTION` | Maximise solar self-use |
| 3 | `EMERGENCY_BACKUP` | `EMERGENCY_BACKUP` | Full battery backup |

> Import: `from franklinwh_cloud.const import TIME_OF_USE, SELF_CONSUMPTION, EMERGENCY_BACKUP`

> Full details in [TOU_SCHEDULE_GUIDE.md](TOU_SCHEDULE_GUIDE.md)
