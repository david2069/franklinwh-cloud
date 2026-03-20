# TOU Tariff, Wave Types & Rate Fields Reference

> [!NOTE]
> This document maps the relationship between **wave types** (tariff tiers),
> **rate field names**, and **dispatch codes** in the FranklinWH Cloud API.
> The API field names are non-obvious — this is the authoritative reference.

---

## Wave Type → Tariff Tier Mapping

The API uses **`waveType`** (an integer) on each TOU block to indicate the **tariff tier**
(pricing period). This determines which electricity rates apply during that block.

| waveType | Tier Name | Enum (`WaveType`) | Typical Usage |
|----------|-----------|-------------------|---------------|
| 0 | Off-Peak | `OFF_PEAK` | Night / low-demand hours |
| 1 | Mid-Peak | `MID_PEAK` | Shoulder / transition hours |
| 2 | On-Peak | `ON_PEAK` | Peak demand / highest tariff |
| 3 | _(reserved)_ | — | Not currently used |
| 4 | Super Off-Peak | `SUPER_OFF_PEAK` | Cheapest / overnight / excess solar |

> [!IMPORTANT]
> `waveType` is **not** the dispatch mode — it's the **pricing tier**. A block can
> have `waveType=0` (off-peak pricing) with `dispatchId=8` (grid charge).
> The two are independent axes: **when you pay** vs **what the battery does**.

---

## Rate Field Names → Wave Type Mapping

Each `dayTypeVoList` entry carries rate fields. The **buy** and **sell** rate fields map
to specific wave types (tariff tiers). The API field names use non-standard terms:

### Buy Rates (Grid Import Cost)

| API Field | Maps to waveType | Human Name | Description |
|-----------|-----------------|------------|-------------|
| `eleticRateValley` | 0 (Off-Peak) | Off-Peak Buy Rate | Cost per kWh during off-peak |
| `eleticRateShoulder` | 1 (Mid-Peak) | Mid-Peak Buy Rate | Cost per kWh during mid-peak |
| `eleticRatePeak` | 2 (On-Peak) | On-Peak Buy Rate | Cost per kWh during on-peak |
| `eleticRateSuperOffPeak` | 4 (Super Off-Peak) | Super Off-Peak Buy | Cost per kWh, cheapest tier |
| `eleticRateSharp` | _(Sharp)_ | Sharp Buy Rate | Highest-cost tier (rarely used) |
| `eleticRateGridFee` | _(all)_ | Grid Fee | Fixed grid access/demand charge |

### Sell Rates (Grid Export Credit)

| API Field | Maps to waveType | Human Name | Description |
|-----------|-----------------|------------|-------------|
| `eleticSellValley` | 0 (Off-Peak) | Off-Peak Sell Rate | Credit per kWh exported off-peak |
| `eleticSellShoulder` | 1 (Mid-Peak) | Mid-Peak Sell Rate | Credit per kWh exported mid-peak |
| `eleticSellPeak` | 2 (On-Peak) | On-Peak Sell Rate | Credit per kWh exported on-peak |
| `eleticSellSuperOffPeak` | 4 (Super Off-Peak) | Super Off-Peak Sell | Credit per kWh, cheapest tier |
| `eleticSellSharp` | _(Sharp)_ | Sharp Sell Rate | Highest-tier export credit |

> [!WARNING]
> **Field name quirks:**
> - `eletic` is a typo for "electric" — consistent across the API
> - `Valley` = Off-Peak, `Shoulder` = Mid-Peak, `Peak` = On-Peak
> - `Sharp` appears to map to an unlisted waveType (possibly 3 or 5)
> - `null` means "not applicable for this tier" — **not the same as `0`**

### Rate Resolution Logic

To find the **active rate** for a given block:

```
block.waveType → tier name → rate field

Example: block has waveType=2 (On-Peak)
  Buy rate  = dayType.eleticRatePeak       (2 → Peak)
  Sell rate = dayType.eleticSellPeak       (2 → Peak)

Example: block has waveType=0 (Off-Peak)
  Buy rate  = dayType.eleticRateValley     (0 → Valley)
  Sell rate = dayType.eleticSellValley     (0 → Valley)
```

### Programmatic Mapping (`RATE_FIELD_MAP`)

```python
WAVE_TO_RATE = {
    0: {"buy": "eleticRateValley",      "sell": "eleticSellValley"},       # Off-Peak
    1: {"buy": "eleticRateShoulder",    "sell": "eleticSellShoulder"},     # Mid-Peak
    2: {"buy": "eleticRatePeak",        "sell": "eleticSellPeak"},         # On-Peak
    4: {"buy": "eleticRateSuperOffPeak", "sell": "eleticSellSuperOffPeak"}, # Super Off-Peak
}
```

---

## Dispatch Code Reference (from `touDispatchList`)

Dispatch codes control **what the battery does** during a TOU block.
These are independent of the tariff tier (waveType).

| dispatchId | Code | Title | Battery Behaviour |
|-----------|------|-------|-------------------|
| 1 | `F` | aPower to home | Battery → home loads; solar → grid |
| 2 | `B` | aPower on standby | Battery idle; solar → home → grid |
| 3 | `E` | aPower charges from solar | Solar → battery; grid → home |
| 6 | `D` | Self-consumption | Solar → battery → home → grid |
| 7 | `H` | aPower to home/grid | Battery → home + grid export |
| 8 | `G` | aPower charges from solar/grid | Solar + grid → battery |

> [!NOTE]
> The `dispatchCode` letter (F, B, E, D, H, G) and `dispatchId` number (1-8)
> are **both** non-sequential and non-obvious. IDs 4 and 5 do not exist.
> Always use the lookup table or `touDispatchList` from the API response.

---

## Tariff Types

The API supports three tariff structures via `electricityType`:

| electricityType | Name | Description |
|----------------|------|-------------|
| 1 | **Time-of-Use (TOU)** | Different rates by time of day (most common) |
| 2 | **Flat Rate** | Single rate all day, all seasons |
| 3 | **Tiered / Ladder** | Rate changes based on cumulative usage (via `ladderRate`) |

> [!IMPORTANT]
> Flat and Tiered samples not yet captured. Need HTTPToolkit captures from
> accounts using these tariff types to document their payload structures.

---

## Day Type Codes

| dayType | API sends | API returns | Description |
|---------|-----------|-------------|-------------|
| 1 | `"weekday"` | `"Weekdays"` | Monday–Friday |
| 2 | `"weekend"` | `"Weekends,Holidays"` | Saturday–Sunday + holidays |
| 3 | `"everyday"` | `"Everyday"` | All days (no split) |

---

## Season Structure

Each `strategyList` entry defines a season with:
- `seasonName`: Display name (e.g. "Season 1", "Summer")
- `month`: Comma-separated month numbers (e.g. "1,2,3" for Jan–Mar)
- `dayTypeVoList`: Array of day types, each containing rates and schedule blocks

**Constraints:**
- 1–4 seasons supported
- All 12 months must be covered (no gaps)
- No month can appear in multiple seasons

### Real-World Example (from HTTPToolkit capture)

```
Season 1 (Jan-Mar) — Summer
├── Weekday: 3 blocks (off-peak/mid-peak/on-peak), full rates
└── Weekend: 1 block (off-peak), valley rates only

Season 2 (Apr-Jun) — Autumn
├── Weekday: 1 block (mid-peak), shoulder rates
└── Weekend: 1 block (mid-peak), shoulder rates

Season 3 (Jul-Sep) — Winter  
├── Weekday: 1 block (mid-peak), shoulder rates
└── Weekend: 1 block (mid-peak), shoulder rates

Season 4 (Oct-Dec) — Spring
├── Weekday: 1 block (mid-peak), shoulder rates
└── Weekend: 1 block (mid-peak), shoulder rates
```

---

## Priority Lists

The `priorityList` in `detailDefaultVo` defines default solar and load priority
orderings per wave type:

| waveType | Solar Priority | Load Priority | Notes |
|----------|---------------|---------------|-------|
| -1 (default) | `1,3,2` | `1,3,2` | Solar → Grid → Battery |
| 0 (Off-Peak) | `1,2,3` | `2,3,0` | Solar → Battery → Grid; `gridChargeMax=-1` |
| 1 (Mid-Peak) | `2,3,0` | `2,3,0` | Battery → Grid → (none) |
| 2 (On-Peak) | `1,3,2` | `1,3,2` | Solar → Grid → Battery |
| 4 (Super Off-Peak) | `1,2,3` | `2,3,0` | Same as Off-Peak; `gridChargeMax=-1` |

Priority values: `0`=None/Disabled, `1`=Solar, `2`=Battery, `3`=Grid
