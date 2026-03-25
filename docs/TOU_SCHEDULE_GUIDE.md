# TOU Schedule API — Read, Write, Verify & Error Handling

> [!CAUTION]
> **Use at your own risk — test extensively before relying on this in production.**
>
> The FranklinWH Cloud API **does not have native "force charge" or "force discharge" commands** with fixed time windows or target SoC parameters. TOU schedule manipulation via `GRID_CHARGE` (dispatchId=8) and `GRID_EXPORT` (dispatchId=7) dispatch codes is the **nearest equivalent** — it tells the aGate to charge/discharge during specific time periods, but behaviour depends on grid conditions, battery state, and firmware.
>
> **Known limitations:**
> - `maxChargeSoc` — accepted by the API but **not verified in all firmware versions**
> - `minDischargeSoc` — **does not work** in recent testing (aGate ignores this field)
> - Not all advanced TOU fields (`gridChargeMax`, `dischargePower`, `rampTime`, etc.) are fully supported or implemented by the aGate firmware
> - For **compatibility with the official FranklinWH mobile app**, keep time periods in **30-minute boundaries** (e.g. 11:30, 12:00, 14:30). Arbitrary times like 11:49 work via the API but may display incorrectly or be overwritten in the app
> - `set_tou_schedule` applies a single schedule to all 12 months. For complex multi-season or weekday/weekend schedules, use `set_tou_schedule_multi(strategy_list)`.

---

## Prerequisites — Check TOU Availability

> [!WARNING]
> **Not all sites have TOU configured.** Before calling TOU endpoints, check `get_entrance_info()` to avoid errors on sites without a tariff setup.

```bash
franklinwh-cli raw get_entrance_info
```

| Flag | Meaning | `0` / `False` = |
|------|---------|-----------------|
| `tariffSettingFlag` | TOU tariff is configured | No tariff — TOU schedule endpoints may return empty/error |
| `pcsEntrance` | PCS power control available | Power control settings not accessible |
| `bbEntrance` | Battery Bonus enrolled | No Battery Bonus programme |
| `sgipEntrance` | SGIP (California Self-Generation Incentive Program) | Not enrolled in SGIP |
| `ja12Entrance` | JA12 (California Energy Code, Joint Appendix 12 — battery storage compliance) | Not in JA12 programme |

```python
info = await client.get_entrance_info()
if not info.get("tariffSettingFlag"):
    print("No TOU tariff configured — schedule endpoints unavailable")
```

---

## TOU Setup Workflows

There are **two distinct paths** to configure a TOU schedule. The template-based path mirrors the FranklinWH mobile app's multi-step wizard. The direct dispatch path is what `franklinwh-cli tou --set` uses.

### Workflow A: Template-Based (App Wizard)

This is the full tariff setup used by the app when changing electric company, rate plan, or creating a new schedule from a utility template. **Each step depends on the previous step's output.**

```mermaid
flowchart TD
    A["1. get_entrance_info()
    Check tariffSettingFlag, pcsEntrance"] --> B

    B["2. get_utility_companies(country_id, province_id)
    Returns: dataList → [{id, companyName}]"] --> C

    C["3. get_tariff_list(company_id)
    Returns: dataList → [{id, name, electricityType}]"] --> D

    D["4. get_tariff_detail(tariff_id)
    Returns: template, strategyList, advancedSettings"] --> E

    E{"User reviews rates/waves"}
    E -->|Accept| F
    E -->|Customise| G

    G["5a. get_custom_dispatch_list(strategy_list)
    Returns: valid dispatch codes for custom blocks"] --> F

    F["5b. get_recommend_dispatch_list(strategy_list)
    Returns: AI-recommended dispatch codes"] --> H

    H["6. calculate_expected_earnings(template)
    Returns: estimatedSavings30, estimatedSavings365"] --> I

    I["7. apply_tariff_template(template_id, name)
    WRITE: saveTouDispatchUseTemplate
    Returns: {id: touId}"]

    style A fill:#2d5016,color:#fff
    style I fill:#7a1a1a,color:#fff
    style E fill:#5a4a00,color:#fff
```

> [!IMPORTANT]
> `apply_tariff_template` is a **write** operation. It replaces the active TOU schedule with the selected template. It is NOT suitable as a standalone CLI command — it requires the prior steps to provide valid `template_id` and `strategy_list` inputs.

### Workflow B: Direct Dispatch (CLI)

Used by `franklinwh-cli tou --set`. Skips utility/tariff selection — directly writes dispatch windows to the existing schedule.

```mermaid
flowchart TD
    A["1. get_entrance_info()
    Check tariffSettingFlag"] --> B

    B["2. get_gateway_tou_list()
    Get current schedule, dispatchId, seasons"] --> C

    C["3. Build payload
    construct_tou_payload(windows, mode, rates)"] --> D

    D["4. set_tou_schedule(payload)
    WRITE: setGatewayIotTouV2
    Returns: {id: touId}"] --> E

    E["5. Verify dispatch
    get_gateway_tou_list() — confirm new schedule active"]

    style A fill:#2d5016,color:#fff
    style D fill:#7a1a1a,color:#fff
```

### API Endpoint Reference

| Step | Method | HTTP | Endpoint | R/W |
|------|--------|------|----------|-----|
| Prerequisites | `get_entrance_info` | GET | `terminal/getEntranceInfo` | Read |
| Utility search | `get_utility_companies` | POST | `terminal/tou/getTouCompanyListPageV2` | Read |
| Tariff plans | `get_tariff_list` | GET | `terminal/tou/getTariffListByCompanyId` | Read |
| Tariff detail | `get_tariff_detail` | GET | `terminal/tou/getTariffDetailByIdV2` | Read |
| Saved TOU detail | `get_tou_detail_by_id` | POST | `terminal/tou/getIotTouDetailById` | Read |
| Custom dispatches | `get_custom_dispatch_list` | POST | `terminal/tou/getCustomEnergyDispatchList` | Read |
| AI dispatch | `get_recommend_dispatch_list` | POST | `terminal/tou/getRecommendEnergyDispatchList` | Read |
| Savings estimate | `calculate_expected_earnings` | POST | `terminal/tou/calculate/expected/earnings` | Read |
| Apply template | `apply_tariff_template` | POST | `terminal/tou/saveTouDispatchUseTemplate` | **Write** |
| Direct dispatch | `set_tou_schedule` | POST | `terminal/tou/setGatewayIotTouV2` | **Write** |
| Bonus info | `get_bonus_info` | GET | `terminal/tou/getBonusInfo` | Read |
| VPP tips | `get_vpp_tip` | GET | `terminal/tou/getVppTipForUpdateTou` | Read |

---

## Dispatch Code Reference

| Code | dispatchId | Enum Name | Battery Behaviour |
|------|-----------|-----------|-------------------|
| `HOME` | `1` | `HOME_LOADS` | aPower → home loads, surplus solar → grid |
| `STANDBY` | `2` | `STANDBY` | Battery idle, solar → home, excess → grid |
| `SOLAR` | `3` | `SOLAR_CHARGE` | Charge battery from solar only |
| `SELF` | `6` | `SELF_CONSUMPTION` | Solar → battery → home, excess → grid |
| `GRID_EXPORT` | `7` | `GRID_EXPORT` | Force discharge battery → grid |
| `GRID_CHARGE` | `8` | `GRID_CHARGE` | Force charge battery from grid + solar |

Wave types (tariff periods): `OFF_PEAK=0`, `MID_PEAK=1`, `ON_PEAK=2`, `SUPER_OFF_PEAK=4`

---

## API Methods

### Reading

| Method | Endpoint | Returns |
|--------|----------|---------|
| `get_tou_dispatch_detail()` | `GET /tou/getTouDispatchDetail` | Full template + strategies + dispatch list |
| `get_gateway_tou_list()` | `POST /tou/getGatewayTouListV2` | TOU config status, send status, alerts |
| `get_tou_info(option)` | _(wraps above)_ | `0`=raw, `1`=current+next, `2`=full detailVoList |
| `get_current_tou_price()` | _(wraps above)_ | Current tier, wave type, rates, and remaining time |
| `get_charge_power_details()` | `GET /chargePowerDetails` | SoC, estimated runtime, consumption |

### Writing

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `set_tou_schedule(touMode, touSchedule)` | → `POST /tou/saveTouDispatch` | Set a single 24h schedule for all days/months |
| `set_tou_schedule_multi(strategy_list)` | → `POST /tou/saveTouDispatch` | Submit a multi-season or weekday/weekend schedule |

---

## Schedule Entry Format (detailVoList)

Each time block is a dict with **5 mandatory fields**:

```python
{
    "name":          "Off-Peak",       # Human label (e.g. tariff tier name)
    "startHourTime": "11:49",          # HH:MM (24h)
    "endHourTime":   "14:59",          # HH:MM or "24:00"
    "waveType":      0,                # Tariff tier (0=Off-Peak, 2=On-Peak, etc.)
    "dispatchId":    8                  # Dispatch mode (see table above)
}
```

> [!IMPORTANT]
> The full 24 hours (00:00 → 24:00 = 1440 minutes) must be covered. If your entries have gaps, `set_tou_schedule` auto-fills them using `default_mode` (default: `SELF`) and `default_tariff` (default: `OFF_PEAK`).

Optional fields: `maxChargeSoc`, `minDischargeSoc`, `solarCutoff`, `gridChargeMax`, `gridDischargeMax`, `chargePower`, `dischargePower`, `gridMax`, `gridFeedMax`, `rampTime`, `heatEnable`, `offGrid`, etc.

---

## Flow Diagram — Setting a TOU Schedule

```mermaid
sequenceDiagram
    participant App as Your Code
    participant Lib as franklinwh-cloud
    participant API as FranklinWH Cloud API
    participant Gate as aGate

    App->>Lib: set_tou_schedule("CUSTOM", schedule)
    
    Note over Lib: 1. Validate touMode ∈ valid_tou_modes
    Note over Lib: 2. JSON schema validation (jsonschema)
    
    Lib->>API: GET getTouDispatchDetail
    API-->>Lib: template + strategyList + detailDefaultVo
    
    Lib->>API: GET getHomeGatewayList
    API-->>Lib: account info for payload
    
    Note over Lib: 3. Compute durations per block
    Note over Lib: 4. Sort by startHourTime
    Note over Lib: 5. Gap-fill to 1440 minutes
    Note over Lib: 6. Verify total = 1440 min
    
    Lib->>API: GET getPcsHintInfo (dispatchId check)
    API-->>Lib: PCS validation result
    
    Lib->>API: POST saveTouDispatch (payload)
    API-->>Lib: {code: 200, result: {id: touId}}
    
    Note over API,Gate: Schedule queued → touSendStatus=1
    Note over Gate: aGate applies within ~1 min
    
    Lib-->>App: response dict
```

## Flow Diagram — Verification After Submission

```mermaid
flowchart TD
    A[Submit schedule] --> B[Wait 5-10s]
    B --> C[get_gateway_tou_list]
    C --> D{touSendStatus?}
    D -->|1 = Pending| E[Wait & retry up to 60s]
    E --> C
    D -->|0 or None| F[get_tou_dispatch_detail]
    F --> G{Compare detailVoList}
    G -->|Matches| H["✅ Schedule applied"]
    G -->|Mismatch| I["⚠️ Retry or alert"]
    
    style H fill:#2d5016,color:#fff
    style I fill:#8b1a1a,color:#fff
```

---

## Example 1 — Grid Charging 11:49 → 14:59, Self-Consumption Otherwise

### Visual timeline

```
00:00 ─────────────── 11:49 ──────── 14:59 ─────────────── 24:00
│  SELF-CONSUMPTION   │ GRID CHARGE  │  SELF-CONSUMPTION   │
│  (auto-filled gap)  │  (your block)│  (auto-filled gap)  │
│  dispatchId=6       │  dispatchId=8│  dispatchId=6       │
```

### Python code

```python
import asyncio
import logging
from franklinwh_cloud.client import Client, TokenFetcher
from franklinwh_cloud.const import dispatchCodeType, WaveType

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("tou_example")

async def set_grid_charge_window():
    """Set grid charging from 11:49 to 14:59, self-consumption all other times."""
    
    fetcher = TokenFetcher("your@email.com", "your_password")
    await fetcher.get_token()
    client = Client(fetcher, "YOUR-AGATE-SN")

    # ── Step 1: Read current schedule ────────────────────────────
    logger.info("Reading current TOU schedule...")
    current = await client.get_tou_dispatch_detail()
    template = current.get("result", {}).get("template", {})
    logger.info(f"Current tariff: {template.get('name', '?')}")
    
    # Read current status
    tou_status = await client.get_gateway_tou_list()
    send_status = tou_status.get("result", {}).get("touSendStatus", 0)
    if send_status:
        logger.warning("A schedule change is already pending (touSendStatus=1)")

    # ── Step 2: Define the schedule ──────────────────────────────
    # Only define the NON-DEFAULT block.
    # Everything else auto-fills with default_mode="SELF" (dispatchId=6)
    schedule = [
        {
            "name":          "Off-Peak",
            "startHourTime": "11:49",
            "endHourTime":   "14:59",
            "waveType":      WaveType.OFF_PEAK.value,      # 0
            "dispatchId":    dispatchCodeType.GRID_CHARGE.value,  # 8
        }
    ]
    
    # ── Step 3: Submit ───────────────────────────────────────────
    logger.info("Submitting TOU schedule...")
    try:
        result = await client.set_tou_schedule(
            touMode="CUSTOM",
            touSchedule=schedule,
            default_mode="SELF",        # Gap-fill with self-consumption
            default_tariff="OFF_PEAK",  # Gap-fill tariff tier
        )
        
        if result.get("code") == 200:
            tou_id = result["result"]["id"]
            logger.info(f"✅ Schedule submitted — touId={tou_id}")
        else:
            logger.error(f"❌ Unexpected response: {result}")
            return
            
    except Exception as e:
        logger.error(f"❌ Schedule submission failed: {e}")
        return

    # ── Step 4: Verify ───────────────────────────────────────────
    logger.info("Verifying schedule was applied...")
    await asyncio.sleep(5)  # Wait for aGate processing
    
    for attempt in range(6):  # Retry up to 30s
        verify = await client.get_gateway_tou_list()
        status = verify.get("result", {}).get("touSendStatus", 0)
        if not status:
            break
        logger.info(f"  Still pending... (attempt {attempt + 1}/6)")
        await asyncio.sleep(5)
    
    # Read back and confirm
    readback = await client.get_tou_info(2)  # option=2: full detailVoList
    logger.info(f"Schedule has {len(readback)} time blocks:")
    for block in readback:
        disp = block.get("dispatchId", "?")
        logger.info(f"  {block['startHourTime']} → {block['endHourTime']}  "
                     f"dispatch={disp}  wave={block.get('waveType', '?')}")

asyncio.run(set_grid_charge_window())
```

### What `set_tou_schedule` generates (after gap-fill)

The library auto-fills the gaps, producing a **3-block** schedule:

```python
[
    {"startHourTime": "00:00", "endHourTime": "11:49", "dispatchId": 6, "waveType": 0, "name": "Off-Peak"},  # auto-filled
    {"startHourTime": "11:49", "endHourTime": "14:59", "dispatchId": 8, "waveType": 0, "name": "Off-Peak"},  # your block
    {"startHourTime": "14:59", "endHourTime": "24:00", "dispatchId": 6, "waveType": 0, "name": "Off-Peak"},  # auto-filled
]
```

---

## Example 2 — Custom: Self → Grid Export → Home Loads

### Visual timeline

```
00:00 ─────────────── 18:30 ──────── 19:45 ─────────────── 24:00
│  SELF-CONSUMPTION   │ GRID EXPORT  │   HOME LOADS        │
│  dispatchId=6       │  dispatchId=7│  dispatchId=1       │
│  waveType=0 OffPeak │  waveType=2  │  waveType=2 OnPeak  │
```

### Python code

```python
async def set_custom_three_phase_schedule():
    """Self-consumption → Grid export 18:30-19:45 → Home loads after."""
    
    fetcher = TokenFetcher("your@email.com", "your_password")
    await fetcher.get_token()
    client = Client(fetcher, "YOUR-AGATE-SN")

    # Define all 3 blocks explicitly (covers full 24h — no gap-fill needed)
    schedule = [
        {
            "name":          "Off-Peak",
            "startHourTime": "00:00",
            "endHourTime":   "18:30",
            "waveType":      WaveType.OFF_PEAK.value,            # 0
            "dispatchId":    dispatchCodeType.SELF_CONSUMPTION.value,  # 6
        },
        {
            "name":          "On-Peak",
            "startHourTime": "18:30",
            "endHourTime":   "19:45",
            "waveType":      WaveType.ON_PEAK.value,             # 2
            "dispatchId":    dispatchCodeType.GRID_EXPORT.value,  # 7
        },
        {
            "name":          "On-Peak",
            "startHourTime": "19:45",
            "endHourTime":   "24:00",
            "waveType":      WaveType.ON_PEAK.value,             # 2
            "dispatchId":    dispatchCodeType.HOME_LOADS.value,   # 1
        },
    ]

    try:
        result = await client.set_tou_schedule(
            touMode="CUSTOM",
            touSchedule=schedule,
        )
        
        if result.get("code") == 200:
            print(f"✅ touId={result['result']['id']}")
        else:
            print(f"❌ API error: code={result.get('code')} msg={result.get('msg', '?')}")
            
    except InvalidTOUScheduleOption as e:
        # Bad touMode, invalid predefined name, or JSON schema failure
        print(f"❌ Validation error: {e}")
    except ValidationError as e:
        # Schedule doesn't cover 24h, or saveTouDispatch returned non-200
        print(f"❌ Schedule error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {type(e).__name__}: {e}")
```

---

## Error Handling Reference

```mermaid
flowchart TD
    A[set_tou_schedule called] --> B{touMode valid?}
    B -->|No| C["InvalidTOUScheduleOption\n'Invalid TOU mode requested: X'"]
    B -->|Yes| D{Mode = CUSTOM?}
    D -->|Yes| E{JSON schema valid?}
    E -->|No| F["InvalidTOUScheduleOption\n'JSON Validation failed: ...'"]
    E -->|Yes| G[Parse times + sort]
    D -->|PREDEFINED| H{Fixture name exists?}
    H -->|No| I["InvalidTOUScheduleOption\n'tou_predefined specified is invalid'"]
    H -->|Yes| G
    D -->|Simple mode| G
    G --> J{Total = 1440 min?}
    J -->|No| K["ValidationError\n'Total elapsed minutes not equal to 1440'"]
    J -->|Yes| L[POST saveTouDispatch]
    L --> M{code == 200?}
    M -->|No| N["ValidationError\n'saveTouDispatch failed with response: ...'"]
    M -->|Yes| O["✅ Return touId"]
    
    style C fill:#8b1a1a,color:#fff
    style F fill:#8b1a1a,color:#fff
    style I fill:#8b1a1a,color:#fff
    style K fill:#8b1a1a,color:#fff
    style N fill:#8b1a1a,color:#fff
    style O fill:#2d5016,color:#fff
```

### Exception Types

| Exception | When | Common Cause |
|-----------|------|--------------|
| `InvalidTOUScheduleOption` | Before API call | Bad touMode, invalid predefined name, JSON schema violation |
| `ValidationError` | After gap-fill | Schedule ≠ 1440 min (overlapping/impossible times) |
| `ValidationError` | After API call | `saveTouDispatch` returned non-200 (server rejected payload) |
| `httpx` exceptions | Network | Timeout, DNS, auth token expired |

### Logging

All `set_tou_schedule` operations log to `"franklinwh_cloud"` logger. Enable with:

```python
logging.getLogger("franklinwh_cloud").setLevel(logging.INFO)
# or for full trace:
logging.getLogger("franklinwh_cloud").setLevel(logging.DEBUG)
```

Key log messages to watch for:
- `set_tou_schedule: Inserting missing time period entry at start/end` — gap-fill triggered
- `set_tou_schedule: Amended sorted_data with missing time periods` — gaps were repaired
- `set_tou_schedule: saveTouDispatch successful, touId = X` — success
- `set_tou_schedule: Error: saveTouDispatch failed` — API rejection

---

## CLI Usage

### Reading schedules (available now)

```bash
franklinwh-cli tou                    # Schedule overview with dispatch blocks
franklinwh-cli tou --dispatch         # Include raw dispatch metadata
franklinwh-cli tou --json             # Machine-readable JSON
```

### Setting schedules from CLI

> [!WARNING]
> `tou --set` is **not yet implemented** in the CLI. The `tou` subcommand is read-only.

**Workarounds to set from CLI:**

**Option A** — Use `mode --set` for simple whole-day modes:
```bash
franklinwh-cli mode --set self_consumption
franklinwh-cli mode --set tou
franklinwh-cli mode --set emergency_backup --soc 30
```

**Option B** — Use `raw` for direct API passthrough:
```bash
# Read current schedule
franklinwh-cli raw get_tou_dispatch_detail --json

# Read with option=2 (full detailVoList)
franklinwh-cli raw get_tou_info 2 --json
```

**Option C** — Python one-liner:
```bash
python3 -c "
import asyncio
from franklinwh_cloud.client import Client, TokenFetcher
from franklinwh_cloud.const import dispatchCodeType as D, WaveType as W

async def go():
    f = TokenFetcher('email', 'pass')
    await f.get_token()
    c = Client(f, 'AGATE-SN')
    r = await c.set_tou_schedule('CUSTOM', [
        {'name':'Off-Peak','startHourTime':'11:49','endHourTime':'14:59',
         'waveType':W.OFF_PEAK.value,'dispatchId':D.GRID_CHARGE.value}
    ])
    print(f'touId={r[\"result\"][\"id\"]}' if r['code']==200 else f'ERROR: {r}')

asyncio.run(go())
"
```

### Future CLI Enhancement

A `tou --set` subcommand could accept:
```bash
# Proposed (not yet built):
franklinwh-cli tou --set GRID_CHARGE --start 11:49 --end 14:59
franklinwh-cli tou --set CUSTOM --file schedule.json
```

---

## Key Constraints & Gotchas

| Constraint | Detail |
|-----------|--------|
| **No native force charge/discharge** | Cloud API has no dedicated timed charge/discharge or target-SoC command. TOU dispatch is the nearest equivalent |
| **`minDischargeSoc` broken** | API accepts the field but aGate ignores it in recent testing — does not enforce minimum SoC during discharge |
| **`maxChargeSoc` unverified** | May work on some firmware versions — test before relying on it |
| **Advanced fields unsupported** | `gridChargeMax`, `dischargePower`, `rampTime`, `gridFeedMax`, etc. are accepted but may be ignored by aGate |
| **30-minute boundaries** | For mobile app compatibility, use times like `11:30`, `12:00`, `14:30`. Arbitrary times (e.g. `11:49`) work via API but may render incorrectly in the official app or be overwritten when the user edits the schedule |
| **24h coverage** | Schedule must total exactly 1440 minutes. Gap-fill handles this automatically |
| **All months coverage** | Multi-season schedules must cover all 12 months exactly once (no gaps, no overlaps). |
| **Day Types** | `dayType=3` is everyday. `dayType=1` is weekday, `dayType=2` is weekend. |
| **Tariff must be TOU** | May not work if user has "Flat" or "Tiered" rate plans configured |
| **touSendStatus** | After submit, `=1` means pending. May persist as false positive even after applied |
| **String `'null'`** | The code uses the string `'null'` (not Python `None`) in some payload fields — this is intentional for the API |

---

## Multi-Season and Day-Type Setup

For complex tariffs (like Australian/Californian separate Summer/Winter rates, or Weekday/Weekend splits), use `set_tou_schedule_multi(strategy_list)`.

This accepts a list of season objects matching the exact format from the API's `getTouDispatchDetail` response.

### Payload Structure

```json
[
  {
    "months": "10,11,12,1,2,3",
    "name": "Summer",
    "dayTypeVoList": [
      {
        "dayType": 1,
        "name": "Weekday",
        "detailVoList": [
          { "name": "Off-Peak", "startHourTime": "00:00", "endHourTime": "15:00", "waveType": 0, "dispatchId": 6 },
          { "name": "Peak", "startHourTime": "15:00", "endHourTime": "21:00", "waveType": 2, "dispatchId": 8 },
          { "name": "Off-Peak", "startHourTime": "21:00", "endHourTime": "24:00", "waveType": 0, "dispatchId": 6 }
        ]
      },
      {
        "dayType": 2,
        "name": "Weekend",
        "detailVoList": [
          { "name": "Off-Peak", "startHourTime": "00:00", "endHourTime": "24:00", "waveType": 0, "dispatchId": 6 }
        ]
      }
    ]
  },
  {
    "months": "4,5,6,7,8,9",
    "name": "Winter",
    "dayTypeVoList": [
      {
        "dayType": 3,
        "name": "Everyday",
        "detailVoList": [
          { "name": "Off-Peak", "startHourTime": "00:00", "endHourTime": "24:00", "waveType": 0, "dispatchId": 6 }
        ]
      }
    ]
  }
]
```

### Validation Rules
1. **Months**: Every integer from 1 to 12 must appear exactly once across all seasons.
2. **Day Types**: Each season must define `dayType=3` (Everyday) OR both `dayType=1` (Weekday) and `dayType=2` (Weekend).
3. **24-hour Coverage**: Inside every `detailVoList`, the time blocks must span exactly `00:00` to `24:00` (1440 minutes).

`set_tou_schedule_multi` automatically validates these rules, strips existing database IDs (`strategyId`, `id`), and preserves the existing TOU template metadata.

---

## Real-Time Pricing

To determine the current active tariff block, use `get_current_tou_price()`. It downloads the current schedule and matches the local system clock against the season, day type, and time block.

**Returns:**
```python
{
    "tier": 2,
    "wave_type": 2,
    "wave_type_name": "On-Peak",
    "season_name": "Summer",
    "day_type_name": "Weekday",
    "block_name": "Peak",
    "block_start": "15:00",
    "block_end": "21:00",
    "minutes_remaining": 120,
    "dispatch_id": 8,
    "buy_rates": {"peak": 0.55, "valley": 0.20},
    "sell_rates": {"peak": 0.40, "valley": 0.05}
}
```
