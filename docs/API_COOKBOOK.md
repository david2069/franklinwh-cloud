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
        "waveType": WaveType.OFF_PEAK.value,             # 0 = Off-peak pricing tier
    }],
    default_mode="SELF",       # Outside window = self-consumption
)

# View current pricing tier, active block, and rates
price = await client.get_current_tou_price()
print(f"Current Tier: {price.get('wave_type_name')} — {price.get('minutes_remaining')} mins left")

# Set a complex multi-season / weekday-weekend schedule
import json
with open("seasons.json", "r") as f:
    strategy_list = json.load(f).get("strategyList")
await client.set_tou_schedule_multi(strategy_list)
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

### Diagnostics & Metrics

The `franklinwh-cloud` client tracks detailed telemetry about every API call, retry, and HTTP connection it makes. You can pull this snapshot at any time to build API health dashboards.

```python
# Get a realtime snapshot of API client health
metrics = client.get_metrics()

# The snapshot contains detailed routing and latency info:
print(f"Total API Calls: {metrics['uptime']['total_requests']}")
print(f"CloudFront Edge: {metrics['edge']['last_pop']}")
print(f"Average Latency: {metrics['timing']['avg_ms']:.0f} ms")

# Endpoint specific hit-counts
for ep, hits in metrics['endpoints'].items():
    print(f"  {ep}: {hits} calls")

# Error tracking and token refreshes
print(f"Parse Errors: {metrics['errors']['parse']}")
print(f"Auth Refreshes: {metrics['uptime']['token_refreshes']}")
```


---

## Full Example: System Dashboard with SoC Estimation

A complete script that displays power flow, operating state, and estimates time to full charge or reserve SoC.

```python
import asyncio
from franklinwh_cloud import FranklinWHCloud

RESERVE_SOC = 20    # Your backup reserve %

async def main():
    client = FranklinWHCloud.from_config("franklinwh.ini")
    await client.login()
    await client.select_gateway()

    # Get dynamic battery capacity directly from the API
    device_info = await client.get_device_info()
    battery_kwh = device_info.get("result", {}).get("totalCap", 13.6)

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
        current_kwh = (c.soc / 100) * battery_kwh
        if c.battery_power < 0:  # Charging
            remaining_kwh = battery_kwh - current_kwh
            hours = remaining_kwh / bat_kw
            h, m = int(hours), int((hours % 1) * 60)
            print(f"⏱️  Estimated ~{h}h {m}m to 100%  (at {bat_kw:.1f} kW)")
        else:  # Discharging
            usable_kwh = current_kwh - (RESERVE_SOC / 100) * battery_kwh
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

A production-ready script that demonstrates the complete lifecycle: save state → configure PCS → set schedule → monitor → restore.

### Phase 1: PCS Preamble — Check Limits & Battery Capacity

Before dispatching, ensure the PCS (Power Control System) allows grid charging/discharging
at the desired power levels, and check battery capacity to calculate target SoC.

```python
import asyncio
from franklinwh_cloud import FranklinWHCloud
from franklinwh_cloud.const import (
    TIME_OF_USE, SELF_CONSUMPTION, EMERGENCY_BACKUP,
    dispatchCodeType, WaveType,
)
from franklinwh_cloud.models import GridStatus

# ── Configuration ──
CHARGE_START = "11:30"
CHARGE_END   = "15:00"
TARGET_SOC   = 95.0       # Stop monitoring when SoC reaches this %
POLL_INTERVAL = 60        # Seconds between monitoring polls
DISPATCH      = dispatchCodeType.GRID_CHARGE   # 8 = charge from solar+grid
WAVE_TYPE     = WaveType.OFF_PEAK              # 0 = off-peak pricing tier


async def main():
    client = FranklinWHCloud.from_config("franklinwh.ini")
    await client.login()
    await client.select_gateway()

    # ── 1a. Save original state (for restore later) ──
    original_mode = await client.get_mode()
    original_mode_id = original_mode.get("workMode", SELF_CONSUMPTION)
    original_mode_name = original_mode.get("modeName", "?")
    original_schedule = await client.get_tou_dispatch_detail()
    print(f"📋 Saved state — Mode: {original_mode_name} (workMode={original_mode_id})")

    # ── 1b. Check battery capacity via API ──
    device_info = await client.get_device_info()
    result_data = device_info.get("result", {})
    battery_count = len(result_data.get("apowerList", [])) or 1
    total_capacity_kwh = result_data.get("totalCap", 13.6)
    print(f"🔋 Batteries: {battery_count} = {total_capacity_kwh:.1f} kWh")

    stats = await client.get_stats()
    current_soc = stats.current.soc
    print(f"🔋 Current SoC: {current_soc:.0f}%  →  Target: {TARGET_SOC:.0f}%")

    if current_soc >= TARGET_SOC:
        print("✅ Already at target SoC — nothing to do.")
        return

    # ── 1c. Check and set PCS limits ──
    pcs = await client.get_power_control_settings()
    charge_limit = pcs.get("result", {}).get("globalGridChargeMax", -1)
    discharge_limit = pcs.get("result", {}).get("globalGridDischargeMax", -1)
    print(f"⚡ PCS limits — Grid charge: {charge_limit} kW, Grid discharge: {discharge_limit} kW")
    print(f"   (-1 = unlimited, 0 = disabled)")

    if charge_limit == 0:
        print("⚠️  Grid charging is DISABLED (0 kW). Enabling unlimited...")
        await client.set_power_control_settings(
            globalGridChargeMax=-1,        # -1 = unlimited
            globalGridDischargeMax=discharge_limit,  # keep existing
        )
        print("✓ Grid charging enabled")

    # ── 1d. Ensure we are in TOU mode ──
    if original_mode_id != TIME_OF_USE:
        print(f"🔄 Switching to TOU mode (was {original_mode_name})...")
        await client.set_mode(TIME_OF_USE, None, None, None, None)
        await asyncio.sleep(3)
        print("✓ Now in TOU mode")
```

### Phase 2: Submit Schedule with Error Handling

Handle common errors: invalid time format, bad dispatch codes, and API failures.

```python
    # ── 2. Set charge schedule with error handling ──
    print(f"\n⏱️  Setting grid charge window {CHARGE_START}–{CHARGE_END}...")

    try:
        result = await client.set_tou_schedule(
            touMode="CUSTOM",
            touSchedule=[{
                "startTime": CHARGE_START,
                "endTime": CHARGE_END,
                "dispatchId": DISPATCH.value,       # dispatchCodeType.GRID_CHARGE = 8
                "waveType": WAVE_TYPE.value,      # WaveType.OFF_PEAK = 0
            }],
            default_mode="SELF",   # Outside window = self-consumption (dispatchId=6)
        )
    except ValueError as e:
        # set_tou_schedule validates times, dispatch codes, and JSON structure
        # Common errors:
        #   - Invalid time: "25:00" or "11:70" or missing startTime
        #   - Bad dispatch: dispatchId=99 (not in valid set 1,2,3,6,7,8)
        #   - Malformed JSON: missing required fields
        print(f"❌ Validation error: {e}")
        print("   Check: times must be HH:MM (00:00–24:00), 30-min boundaries")
        print("   Check: dispatchId must be one of: 1,2,3,6,7,8")
        return
    except Exception as e:
        # API-level errors (network, auth, server-side rejection)
        print(f"❌ API error: {type(e).__name__}: {e}")
        return

    # Check API response for success
    status = result.get("status")
    if status != 0:
        msg = result.get("msg", "Unknown error")
        print(f"❌ Server rejected schedule: status={status}, msg={msg}")
        return

    tou_id = result.get("result", {}).get("id", "?")
    print(f"✓ Schedule submitted — touId={tou_id}")

    # ── 2b. Verify schedule applied ──
    await asyncio.sleep(5)   # Give aGate time to apply

    detail = await client.get_tou_dispatch_detail()
    blocks = detail.get("result", {}).get("detailVoList", [])
    print(f"\n📅 Active schedule ({len(blocks)} blocks):")
    for b in blocks:
        name = b.get("dispatchName", "?")
        start = b.get("startTime", "?")
        end = b.get("endTime", "?")
        wave = b.get("waveType", "?")
        print(f"  {start}–{end}  {name}  (waveType={wave})")

    if not blocks:
        print("⚠️  No dispatch blocks found — schedule may not have applied!")
```

### Phase 3: Monitor Power Flow & SoC

Poll the system to confirm the dispatch is executing correctly — checking that
the operating mode is still TOU, power is flowing in the expected direction,
and the SoC target has been reached.

```python
    # ── 3. Monitor loop ──
    print(f"\n🔍 Monitoring every {POLL_INTERVAL}s until SoC ≥ {TARGET_SOC}%...")
    print(f"   Press Ctrl+C to stop monitoring early.\n")

    try:
        while True:
            stats = await client.get_stats()
            c = stats.current

            soc = c.soc
            bat_kw = c.battery_power     # negative = charging, positive = discharging
            grid_kw = c.grid_power       # positive = importing, negative = exporting
            solar_kw = c.solar_production
            mode_desc = c.work_mode_desc
            grid_status = c.grid_status

            # ── 3a. Mode check — still in TOU? ──
            if "Time of Use" not in mode_desc:
                print(f"⚠️  Mode changed to '{mode_desc}' — expected TOU!")
                print(f"    The system may have switched due to storm hedge or app override.")
                break

            # ── 3b. Grid check — still connected? ──
            if grid_status != GridStatus.NORMAL:
                print(f"⚠️  Grid status: {grid_status.name} — cannot charge from grid while off-grid!")
                break

            # ── 3c. Power flow direction ──
            charging = bat_kw < -0.05   # Battery drawing > 50W = charging

            if DISPATCH == dispatchCodeType.GRID_CHARGE:
                # Grid charge: expect battery charging (bat_kw < 0) AND grid importing (grid_kw > 0)
                flow_ok = charging
                direction = "⬇ CHARGING" if charging else "⏸ IDLE/DISCHARGING"
                grid_dir = f"grid={'importing' if grid_kw > 0 else 'exporting'} {abs(grid_kw):.2f} kW"

            elif DISPATCH == dispatchCodeType.GRID_EXPORT:
                # Grid export: expect battery discharging (bat_kw > 0) AND grid exporting (grid_kw < 0)
                discharging = bat_kw > 0.05
                flow_ok = discharging
                direction = "⬆ DISCHARGING" if discharging else "⏸ IDLE/CHARGING"
                grid_dir = f"grid={'exporting' if grid_kw < 0 else 'importing'} {abs(grid_kw):.2f} kW"

            else:
                # Other dispatches (SELF, SOLAR, HOME, STANDBY)
                flow_ok = True
                direction = f"bat={bat_kw:+.2f} kW"
                grid_dir = f"grid={grid_kw:+.2f} kW"

            status_icon = "✅" if flow_ok else "⚠️"
            print(
                f"  {status_icon} SoC: {soc:5.1f}% | "
                f"Battery: {bat_kw:+6.2f} kW {direction} | "
                f"Solar: {solar_kw:.2f} kW | {grid_dir}"
            )

            # ── 3d. SoC target reached? ──
            if DISPATCH == dispatchCodeType.GRID_CHARGE and soc >= TARGET_SOC:
                print(f"\n🎯 Target SoC reached: {soc:.0f}% ≥ {TARGET_SOC:.0f}%")
                break

            if DISPATCH == dispatchCodeType.GRID_EXPORT and soc <= TARGET_SOC:
                # For export, TARGET_SOC is the minimum SoC before stopping
                print(f"\n🎯 Minimum SoC reached: {soc:.0f}% ≤ {TARGET_SOC:.0f}%")
                break

            await asyncio.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\n⏹️  Monitoring stopped by user.")
```

### Phase 4: Restore Original State

Always restore the original TOU schedule and operating mode — even if monitoring
was interrupted.

```python
    # ── 4. Restore original state ──
    print(f"\n🔄 Restoring original state...")

    # 4a. Restore original TOU schedule
    try:
        orig_blocks = original_schedule.get("result", {}).get("detailVoList", [])
        if orig_blocks:
            # Re-submit the original schedule blocks
            restore_schedule = []
            for b in orig_blocks:
                restore_schedule.append({
                    "startTime": b.get("startTime", "0:00"),
                    "endTime": b.get("endTime", "24:00"),
                    "dispatchId": b.get("dispatchId", 6),
                    "waveType": b.get("waveType", 0),
                })
            await client.set_tou_schedule(
                touMode="CUSTOM",
                touSchedule=restore_schedule,
                default_mode="SELF",
            )
            print(f"✓ Restored original TOU schedule ({len(orig_blocks)} blocks)")
        else:
            # No blocks = was flat self-consumption
            await client.set_tou_schedule(touMode="SELF")
            print("✓ Restored to full-day self-consumption")
    except Exception as e:
        print(f"⚠️  Could not restore TOU schedule: {e}")
        print(f"    You may need to manually restore via the FranklinWH app.")

    # 4b. Restore original operating mode
    if original_mode_id != TIME_OF_USE:
        try:
            await client.set_mode(original_mode_id, None, None, None, None)
            print(f"✓ Restored operating mode to {original_mode_name} (workMode={original_mode_id})")
        except Exception as e:
            print(f"⚠️  Could not restore mode: {e}")

    # 4c. Final state confirmation
    await asyncio.sleep(3)
    final_mode = await client.get_mode()
    final_stats = await client.get_stats()
    print(f"\n📋 Final state:")
    print(f"   Mode: {final_mode.get('modeName', '?')}")
    print(f"   SoC:  {final_stats.current.soc:.0f}%")
    print(f"   Grid: {final_stats.current.grid_status.name}")
    print("✅ Done!")

asyncio.run(main())
```

**Expected output (grid charge scenario):**
```
📋 Saved state — Mode: Self Consumption (workMode=2)
🔋 Batteries: 1 × aPower = ~13.6 kWh
🔋 Current SoC: 42%  →  Target: 95%
⚡ PCS limits — Grid charge: -1 kW, Grid discharge: -1 kW
   (-1 = unlimited, 0 = disabled)
🔄 Switching to TOU mode (was Self Consumption)...
✓ Now in TOU mode

⏱️  Setting grid charge window 11:30–15:00...
✓ Schedule submitted — touId=12345

📅 Active schedule (3 blocks):
  0:00–11:30   Self-consumption  (waveType=0)
  11:30–15:00  Grid charge       (waveType=0)
  15:00–24:00  Self-consumption  (waveType=0)

🔍 Monitoring every 60s until SoC ≥ 95%...

  ✅ SoC:  42.3% | Battery:  -4.80 kW ⬇ CHARGING | Solar: 2.10 kW | grid=importing 2.70 kW
  ✅ SoC:  48.7% | Battery:  -4.90 kW ⬇ CHARGING | Solar: 3.40 kW | grid=importing 1.50 kW
  ✅ SoC:  55.1% | Battery:  -5.00 kW ⬇ CHARGING | Solar: 4.20 kW | grid=importing 0.80 kW
  ...
  ✅ SoC:  94.8% | Battery:  -1.20 kW ⬇ CHARGING | Solar: 3.80 kW | grid=importing 0.00 kW

🎯 Target SoC reached: 95% ≥ 95%

🔄 Restoring original state...
✓ Restored original TOU schedule (3 blocks)
✓ Restored operating mode to Self Consumption (workMode=2)

📋 Final state:
   Mode: Self Consumption
   SoC:  95%
   Grid: NORMAL
✅ Done!
```

> [!CAUTION]
> This script modifies your live aGate TOU schedule and operating mode.
> Always test during off-peak hours. The script saves and restores state, 
> but if it crashes mid-execution, restore manually via the FranklinWH app.

> See [TOU_SCHEDULE_GUIDE.md](TOU_SCHEDULE_GUIDE.md) for dispatch codes, known limitations, and the 30-minute boundary rule.

---

## Smart Circuits & EV Charging

### V2 Firmware Mutations & Compatibility
FranklinWH recently migrated Smart Circuit (`Sw`) payloads from V1 integer timers (`Sw1OpenTime`/`Sw1CloseTime2`) to V2 string arrays (`time_enabled`, `time_schedules`, `time_set`). 
* **Impact**: Writing schedules using the V1 integer schema will aggressively fail or be ignored by modern aGates. 
* **Reading**: `franklinwh-cloud` transparently handles the parsing into `SmartCircuitDetail` dataclasses. You will see string representations like `'2025-10-04 20:11'`.
* **Writing**: Until the exact V2 payload constructor is fully mapped natively, schedules should only be modified manually or toggled dynamically using boolean switches (`set_smart_switch_state`) and Amperage limits (`set_smart_circuit_load_limit`).

### Advanced Regional Discovery & Renaming
US and AU/EU markets exhibit vastly different Smart Circuit topologies. US grids support multiple aGates chained together and "merged" Smart Circuits, while AU grids standardise on 3 physical outputs per aGate with V2L. You can parse the `DeviceSnapshot` tree to adapt your integration intelligently:

```python
import asyncio
from franklinwh_cloud import Client

async def diagnose_regional_smart_circuits():
    client = Client("user@example.com", "secret")
    await client.login()
    await client.select_gateway()

    # Discover Tier 2 loads all hardware Quirks and Accessories 
    snapshot = await client.discover(tier=2)
    acc = snapshot.accessories
    
    # Check if this gateway supports the US "merge" functionality or AU V2L
    quirks = acc.get("gateway", {}).get("region_quirks", {})
    if quirks.get("supports_smart_circuit_merge"):
        print("🌍 US Region Detected: Application may contain merged Smart Circuits spanning multiple aGates.")
    elif quirks.get("supports_v2l"):
        print("🌍 AU Region Detected: Vehicle-to-Load output may occupy Smart Circuit 1.")

    # Detect if a Generator or Smart Circuits are physically installed
    installed = acc.get("installed", [])
    if "Generator" in installed:
        gen_status = acc.get("accessories", {}).get("generator", {}).get("status_desc")
        print(f"⚡ Generator physically wired. Current State: {gen_status}")
    if "Smart_Circuit" in installed:
        count = acc.get("accessories", {}).get("smart_circuits", {}).get("count", 0)
        print(f"🔌 {count} Smart Circuits physically tracked by this aGate.")

    # Renaming a Smart Circuit requires a raw dictionary invoke as the API is undocumented
    print("📝 Renaming Circuit 2 to 'EV Charger'...")
    circuit_payload = {"swId": 2, "name": "EV Charger"}
    await client._post("/hes-gateway/terminal/updateSmartCircuitName", payload=circuit_payload)

# asyncio.run(diagnose_regional_smart_circuits())
```

### Complex Automation: Adaptive EV Solar Charging
This script tracks Solar PV, SOC, and Home Load exactly as requested: it waits until native Solar generation exceeds a set threshold, confirms no grid export is currently required, checks that the battery is sufficiently high, and optionally reaches out to a Home Assistant WebSocket (like the Enphase integration) to verify EV presence before throwing the FranklinWH Smart Circuit ON.

```python
import asyncio
import json
import websockets # pip install websockets
from franklinwh_cloud import FranklinWHCloud

# Configuration Thresholds
SOLAR_THRESHOLD_KW = 4.0      # Minimum solar generation required to charge EV
MIN_SOC_PERCENT = 80          # Minimum FranklinWH battery level required
EV_CIRCUIT_ID = 2             # The Smart Circuit physical port (1, 2, or 3)
HA_WS_URL = "ws://homeassistant.local:8123/api/websocket"
HA_TOKEN = "eyJhbGciOiJIUzI1..." 

async def check_ev_presence_ha():
    """Reach out to Home Assistant to verify the EV is plugged in and needs charge."""
    try:
        async with websockets.connect(HA_WS_URL) as ws:
            await ws.send(json.dumps({"type": "auth", "access_token": HA_TOKEN}))
            await ws.recv() # Wait for auth_ok
            
            # Request EV state from a custom HA Enphase/Tesla integration entity
            req_id = 1
            await ws.send(json.dumps({"id": req_id, "type": "get_states"}))
            response = json.loads(await ws.recv())
            
            for entity in response.get("result", []):
                if entity["entity_id"] == "sensor.ev_charger_status":
                    return entity["state"] == "plugged_in"
    except Exception as e:
        print(f"HA WebSocket unreachable: {e}. Defaulting to True for safety.")
    return True

async def adaptive_ev_charging_loop():
    client = FranklinWHCloud("user@example.com", "secret")
    
    while True:
        try:
            if not client.is_authenticated():
                await client.login()
                await client.select_gateway()

            stats = await client.get_stats()
            solar_kw = stats.current.solar_production
            grid_kw = stats.current.grid_power
            soc = stats.current.soc
            
            # Check if Smart Circuit is already ON
            circuits = await client.get_smart_circuits_info()
            ev_circuit_active = circuits.get(EV_CIRCUIT_ID).is_on
            
            # Criteria 1: Plenty of solar headroom
            # Criteria 2: Battery SOC is healthy
            # Criteria 3: Grid export is negative (we possess excess power not consumed by home)
            solar_sufficient = solar_kw >= SOLAR_THRESHOLD_KW
            battery_sufficient = soc >= MIN_SOC_PERCENT
            excess_power_available = grid_kw < 0 
            
            if solar_sufficient and battery_sufficient and excess_power_available:
                if not ev_circuit_active:
                    # Optional: Verify the EV is physically connected via Home Assistant
                    ev_plugged_in = await check_ev_presence_ha()
                    if ev_plugged_in:
                        print(f"Criteria Met (Solar: {solar_kw}kW, SOC: {soc}%, Grid: {grid_kw}kW). Activating EV Circuit!")
                        # Toggle the specific Smart Circuit ON dynamically
                        switches = [None, None, None]
                        switches[EV_CIRCUIT_ID - 1] = True 
                        await client.set_smart_switch_state(tuple(switches))
                        
            # Hysteresis / Shutdown Logic 
            # If clouds roll in and we start heavily draining from the grid, cut the charger
            elif grid_kw > 1.0 and ev_circuit_active:
                print("Solar dropped or grid demand spiked. Deactivating EV circuit.")
                switches = [None, None, None]
                switches[EV_CIRCUIT_ID - 1] = False
                await client.set_smart_switch_state(tuple(switches))

        except Exception as e:
            print(f"Polling fault: {e}")
            
        await asyncio.sleep(60) # Poll every 60 seconds

# asyncio.run(adaptive_ev_charging_loop())
```

---

## Storm Hedge 

### Real-Time Weather Event Polling
The FranklinWH aGate constantly polls national weather services indicating incoming storm cells. You can proactively poll these internal lists to hook into Home Assistant automations triggering shutters or pre-chilling HVAC systems.

```python
async def poll_weather_events():
    client = FranklinWHCloud("user@example.com", "secret")
    await client.login()
    await client.select_gateway()

    # Get active storm warnings tracked by the aGate
    active_storms = await client.get_progressing_storm_list()
    if active_storms:
        for storm in active_storms:
            print(f"🚨 Storm Detected: {storm.get('title')}")
            print(f"   Severity: {storm.get('severity')}")
            print(f"   Time: {storm.get('effective')} -> {storm.get('expires')}")
    else:
        print("☀️ No severe weather events tracked by FranklinWH.")

    # Check if Storm Hedge is actively protecting the battery
    storm_settings = await client.get_storm_settings()
    if storm_settings.get("switchStatus") == 1:
        print(f"Storm Hedge Enabled! Reserve SOC protected at {storm_settings.get('backUpSoc')}%")
```

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

---

## Exception Handling & Reliability

FranklinWH Cloud infrastructure can occasionally experience timeouts, offline gateways, or session invalidation. Ensure your integration scripts are wrapped in the library's strictly defined exception structures.

```python
import asyncio
from franklinwh_cloud import FranklinWHCloud
from franklinwh_cloud.exceptions import (
    FranklinWHTimeoutError,
    DeviceTimeoutException,
    GatewayOfflineException,
    TokenExpiredException
)

async def reliable_polling_loop():
    client = FranklinWHCloud("user@example.com", "secret")

    while True:
        try:
            if not client.is_authenticated():
                await client.login()
                await client.select_gateway()

            # Perform routine queries
            snapshot = await client.get_stats()
            print(f"Current SoC: {snapshot.current.soc}%")

        except FranklinWHTimeoutError as e:
            # Raised globally when httpx or socket drops the connection natively
            print(f"Cloud API timed out: {e}. Retrying in 60s...")

        except DeviceTimeoutException as e:
            # Raised when the Cloud API is online, but your physical aGate stopped communicating
            print(f"Your Gateway dropped offline from the mesh: {e}")

        except GatewayOfflineException as e:
            # Raised explicitly when attempting a WRITE command to a known offline box
            print(f"WRITE blocked. Gateway disconnected: {e}")

        except TokenExpiredException as e:
            # Raised when the JWT natively expires
            print("Session dead. Flagging rotation for next loop...")
            client.clear_token()

        except Exception as e:
            # Generic catch-all for parsing failures
            print(f"Unexpected fault: {e}")

        await asyncio.sleep(60)

```

### Key Exception Hierarchy
All library-specific exceptions inherit from `FranklinWHError`. Below are the primary failure modes:

| Exception Class | Cause | Resolution |
|-----------------|-------|------------|
| `FranklinWHTimeoutError` | Raw API unresponsive / Connection reset | Standard retry backoff. |
| `DeviceTimeoutException` | Node-to-Cloud telemetry lost (`offlineReason` triggered). | Investigate Edge WiFi or wait for 4G cellular failover. |
| `TokenExpiredException` | JWT session rotation required. | Invoke `client.login()` or `client.get_token()` to renew. |
| `InvalidCredentialsException` | 401 Unauthorized (`Code 10009`). | Verify username/password or `LOGIN_TYPE` flag. |
| `BadRequestParsingError` | JSON blob abruptly mutated (V1 to V2). | Ensure dependencies are tracking the latest PyPI distribution. |
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
