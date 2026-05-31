# CLI Reference: `franklinwh-cli tou`

> **Purpose:** The `tou` command is the primary interface for reading and writing
> Time-of-Use schedules on an aGate — inspecting the configured tariff blocks,
> setting ephemeral or permanent dispatch windows, pricing tier monitoring,
> multi-season schedule loading, and supervised backup/restore.

See also:
- [TOU_SCHEDULE_GUIDE.md](TOU_SCHEDULE_GUIDE.md) — Python API and data model reference
- [TOU_TARIFF_REFERENCE.md](TOU_TARIFF_REFERENCE.md) — Dispatch code and wave type reference
- [CLI_SCHEMA_COMMAND.md](CLI_SCHEMA_COMMAND.md) — Field registry for TOU schema blocks

---

## Quick Reference

```bash
# ── Read ───────────────────────────────────────────────────────────────
franklinwh-cli tou                          # full schedule overview (all seasons)
franklinwh-cli tou --current                # only show the active season
franklinwh-cli tou --next                   # current block + next block + remaining time
franklinwh-cli tou --price                  # active pricing tier and rates
franklinwh-cli tou --price --all            # all pricing tiers (not just active)
franklinwh-cli tou --price --active-only    # one-line "Buy: X | Sell: Y" (scripts)
franklinwh-cli tou --dispatch               # include raw dispatch strategy metadata
franklinwh-cli tou --extended               # always show SoC columns even if empty
franklinwh-cli tou --json                   # machine-readable output

# ── Write: single window ────────────────────────────────────────────────
franklinwh-cli tou --set GRID_CHARGE --start 11:30 --end 15:00
franklinwh-cli tou --set GRID_EXPORT --start 18:00 --end 20:00 --default SELF
franklinwh-cli tou --set SELF              # full-day self-consumption (no --start/--end)
franklinwh-cli tou --set GRID_CHARGE --start 11:30 --end 15:00 --month 7
franklinwh-cli tou --set GRID_CHARGE --start 23:00 --end 01:00 --default SELF --wait

# ── Write: supervised (auto-restore) ────────────────────────────────────
franklinwh-cli tou --set GRID_CHARGE --start 23:00 --end 01:00 --wait
# → auto-restores the original schedule at 01:00

# ── Write: custom JSON ──────────────────────────────────────────────────
franklinwh-cli tou --set CUSTOM --file schedule.json
franklinwh-cli tou --multi-season seasons.json

# ── Recovery ────────────────────────────────────────────────────────────
franklinwh-cli tou --restore               # restore from an unrestored backup
```

---

## Implementation Status

All flags listed in `-h` are implemented. The table below documents the
**actual tested behaviour** of each flag, including any known limitations or
caveats.

| Flag | Status | Notes |
|------|--------|-------|
| _(no flags)_ | ✅ **Full** | Full schedule table, all seasons/day types |
| `--dispatch` | ✅ **Full** | Appends raw dispatch strategy and charge power detail |
| `--next` | ✅ **Full** | Current block, remaining time, next block |
| `--price` | ✅ **Full** | Active tier, rates, block window, time remaining |
| `--price --all` | ✅ **Full** | All 5 tier rates in active season |
| `--price --active-only` | ✅ **Full** | Script-safe one-liner output |
| `--current` | ✅ **Full** | Filters schedule table to active season only |
| `--extended` | ✅ **Full** | Forces SoC columns (maxChargeSoc / minDischargeSoc) even if empty |
| `--json` | ✅ **Full** | All sub-modes output valid JSON |
| `--set MODE` | ✅ **Full** | All 6 dispatch modes + CUSTOM (see Dispatch Modes table) |
| `--set MODE --start/--end` | ✅ **Full** | Single-window, auto-fills remaining 24h |
| `--set MODE --default` | ✅ **Full** | Sets dispatch for times outside window |
| `--set MODE --month N` | ✅ **Full** | Targets specific month's season, leaves others untouched |
| `--set MODE --day-type` | ✅ **Full** | Targets weekday/weekend/everyday sub-type within season |
| `--set CUSTOM --file` | ✅ **Full** | Full 24h block list from JSON file |
| `--rates-file` | ✅ **Full** | Injects pricing rates (buy/sell per tier) into the schedule |
| `--season / --months` | ✅ **Full** | Explicit season name + month override for `--set` |
| `--multi-season FILE` | ✅ **Full** | Full multi-season strategyList replacement |
| `--wait` | ✅ **Full** | Supervised dispatch with backup, confirm, auto-restore at `--end` |
| `--restore` | ✅ **Full** | Interactive restore of unrestored backups from disk |

### Known Firmware Limitations (not CLI bugs)

| Feature | Status |
|---------|--------|
| `maxChargeSoc` | ⚠️ Accepted by API but not enforced by all firmware versions |
| `minDischargeSoc` | ❌ Ignored by aGate firmware in all tested configurations |
| 30-minute boundaries | ⚠️ Arbitrary times (e.g. `11:49`) work via API but may display incorrectly in the FranklinWH app or be overwritten when the user edits in-app |

---

## Full Flag Reference

### Read Flags

#### `franklinwh-cli tou` (no flags)

Displays the full TOU schedule for all configured seasons and day types.

Output includes:
- Tariff plan name, utility, work mode, NEM type
- One table per season × day type combination
- Per-block: start/end time, dispatch mode name, wave type (tariff tier), duration, buy/sell rates
- Total block count across all seasons

```
============================================================
  Time-of-Use Schedule
============================================================

📅 Schedule — All Year

     START     END       NAME            DISPATCH                        WAVE           BUY     SELL
     ───────── ───────── ─────────────── ─────────────────────────────── ────────────── ─────── ───────
     00:00     23:20     Off-Peak        Self-consumption                Off-Peak       $0.00   $0.00
     23:20     23:40     Off-Peak        aPower charges from solar/grid  Off-Peak       $0.00   $0.00
     23:40     24:00     Off-Peak        Self-consumption                Off-Peak       $0.00   $0.00
```

---

#### `--dispatch`

Appended to the default output. Shows:
- Raw template PTO date, battery savings flag, aPower count
- Full list of available dispatch codes (dispatchId, title, code, description)
- Charge power details: SoC, TOU min SoC, estimated runtime at current/high/avg consumption

Use this for debugging dispatch ID mapping issues or inspecting raw strategy data.

---

#### `--current`

Filters the schedule table to only the season whose month list includes today's month. All other seasons are skipped.

```bash
franklinwh-cli tou --current
```

Useful when you have multiple seasons configured and only want to see what's active right now.

---

#### `--next`

Shows the current active block and next upcoming block using the `get_tou_info(1)` API response. Includes remaining time formatted as `HH:MM`.

```
============================================================
  TOU Schedule — Current & Next
============================================================

📋 Schedule
     START     END       DISPATCH                        WAVE        DURATION
     ───────── ───────── ─────────────────────────────── ─────────── ────────
     00:00     23:20     Self-consumption                Off-Peak    23h 20m
  ▸ 23:20     23:40     aPower charges from solar/grid  Off-Peak    20m
     23:40     24:00     Self-consumption                Off-Peak    20m

⏱️  Now
               Current: aPower charges from solar/grid
             Remaining: 00:12
                  Next: Self-consumption at 23:40
              Duration: 00:20:00
```

---

#### `--price`

Reads the current pricing tier using `get_current_tou_price()`. Displays:
- Pricing tier (Off-Peak / On-Peak / etc.)
- Season and day type
- Block window (start → end)
- Time remaining in block
- Dispatch strategy ID
- Current buy/sell rates

```bash
franklinwh-cli tou --price
```

#### `--price --all`

Same as `--price`, but shows all 5 tariff tiers (On-Peak, Sharp, Shoulder/Mid-Peak, Off-Peak, Super Off-Peak) instead of just the active one. Use this to inspect the full rate table for the current season/day-type.

#### `--price --active-only`

Outputs a single line:
```
Buy: 0.35 | Sell: 0.10
```
Designed for shell scripts, Home Assistant `command_line` sensors, or other
one-line consumers. No header, no colour, no labels.

```bash
# Shell example: read current buy rate
RATE=$(franklinwh-cli tou --price --active-only | awk '{print $2}')
```

---

#### `--extended`

Forces the schedule table to always show the `MAX SoC` and `MIN SoC` columns,
even when no blocks have `maxChargeSoc` or `minDischargeSoc` set (they display
as `—`). Without this flag, SoC columns only appear when at least one block
has a value.

---

#### `--json`

Outputs machine-readable JSON for all sub-modes. The structure varies by sub-mode:

| Command | JSON keys |
|---------|-----------|
| `tou --json` | `tou_list`, `dispatch_detail`, `charge_power` |
| `tou --next --json` | `now`, `blocks[]`, `current`, `next` |
| `tou --price --json` | Full `get_current_tou_price()` dict |
| `tou --set ... --json` | API response + `wait_result` (if `--wait`) |
| `tou --multi-season ... --json` | API response |

---

### Write Flags

> [!CAUTION]
> All `--set` and `--multi-season` operations are **live writes** to your aGate's
> TOU schedule. The aGate applies changes within ~1 minute. Always use `--wait`
> for temporary windows so the original schedule is automatically restored.

---

#### `--set MODE`

Sets a TOU dispatch mode. Modes map to dispatch IDs:

| CLI Mode | dispatchId | Behaviour |
|----------|-----------|-----------|
| `SELF` | 6 | Self-consumption: solar → battery → home, surplus → grid |
| `HOME` | 1 | aPower → home loads, surplus solar → grid |
| `STANDBY` | 2 | Battery idle; solar → home, excess → grid |
| `SOLAR` | 3 | Charge battery from solar only |
| `GRID_EXPORT` | 7 | Force discharge battery → grid |
| `GRID_CHARGE` | 8 | Force charge battery from grid + solar |
| `CUSTOM` | — | Full JSON schedule (requires `--file`) |

**Full-day mode** (no `--start`/`--end`): Sets the dispatch for the entire 24h period.

```bash
franklinwh-cli tou --set SELF          # full-day self-consumption
franklinwh-cli tou --set GRID_CHARGE   # full-day grid charging
```

**Window mode** (`--start`/`--end`): Sets the dispatch for a specific window.
Remaining time is filled with `--default` (default: `SELF`).

```bash
franklinwh-cli tou --set GRID_CHARGE --start 23:00 --end 01:00
franklinwh-cli tou --set GRID_EXPORT --start 18:00 --end 20:00 --default HOME
```

> [!NOTE]
> For window commands crossing midnight (e.g. `23:00 → 01:00`), the `--end`
> time is treated as a wall-clock deadline for `--wait`, rolling to tomorrow
> if already past.

---

#### `--start HH:MM` / `--end HH:MM`

Required together for a window dispatch. Both must be valid `HH:MM` (24-hour).
`24:00` is accepted for end-of-day. Arbitrary minute boundaries (e.g. `11:49`)
work via the API but use 30-minute boundaries for mobile app compatibility.

---

#### `--default MODE`

Sets the dispatch mode for all time **outside** the `--start`/`--end` window.
Must be a valid dispatch mode name (same as `--set`). Defaults to `SELF` if
not provided (a warning is printed).

```bash
franklinwh-cli tou --set GRID_EXPORT --start 18:00 --end 20:00 --default SELF
```

---

#### `--month 1-12`

Targets the season that owns the specified month, leaving all other seasons
untouched. Without this flag, the current month's season is updated.

```bash
# Update July's season only (e.g. Summer schedule)
franklinwh-cli tou --set GRID_CHARGE --start 23:00 --end 01:00 --month 7
```

---

#### `--season NAME` / `--months M,M,...`

Explicitly override or create a named season spanning the specified months.
Use with `--set` to update a season by name and month list in a single call.

```bash
franklinwh-cli tou --set GRID_CHARGE --start 23:00 --end 01:00 \
    --season "Winter" --months "5,6,7,8,9"
```

> [!IMPORTANT]
> All 12 months must be covered across all seasons in the submitted payload.
> Using `--season`/`--months` with `--set` replaces only the targeted season.

---

#### `--day-type TYPE`

Targets a specific day-type within the season. Choices: `everyday` (default),
`weekday`, `weekend`.

```bash
# Charge overnight only on weekdays
franklinwh-cli tou --set GRID_CHARGE --start 23:00 --end 01:00 \
    --default SELF --day-type weekday
```

---

#### `--file PATH`

Loads a full 24-hour schedule from a JSON file for use with `--set CUSTOM`.
The file must be a JSON array of time block objects:

```json
[
  {"name": "Off-Peak", "startHourTime": "00:00", "endHourTime": "11:30",
   "waveType": 0, "dispatchId": 6},
  {"name": "On-Peak",  "startHourTime": "11:30", "endHourTime": "14:30",
   "waveType": 2, "dispatchId": 8},
  {"name": "Off-Peak", "startHourTime": "14:30", "endHourTime": "24:00",
   "waveType": 0, "dispatchId": 6}
]
```

Mandatory fields per block: `name`, `startHourTime`, `endHourTime`, `waveType`, `dispatchId`.
The blocks do not need to cover the full 24h — `set_tou_schedule` auto-fills gaps with `--default` (or `SELF`).

Wave types: `0`=Off-Peak, `1`=Mid-Peak/Shoulder, `2`=On-Peak, `3`=Sharp Peak, `4`=Super Off-Peak.

```bash
franklinwh-cli tou --set CUSTOM --file my_schedule.json
franklinwh-cli tou --set CUSTOM --file my_schedule.json --default HOME
```

---

#### `--rates-file PATH`

Injects pricing rates (buy/sell per tariff tier) into the submitted schedule.
The file must be a JSON object with numeric values:

```json
{
  "peak":            0.55,
  "shoulder":        0.35,
  "off_peak":        0.20,
  "super_off_peak":  0.15,
  "sell_peak":       0.40,
  "sell_shoulder":   0.25,
  "sell_off_peak":   0.08,
  "sell_super_off_peak": 0.05
}
```

Valid keys: `peak`, `sharp`, `shoulder`, `off_peak`, `super_off_peak`,
`sell_peak`, `sell_sharp`, `sell_shoulder`, `sell_off_peak`, `sell_super_off_peak`, `grid_fee`.

All values are validated: must be numeric, non-negative, and `≤ $100/kWh`.

```bash
franklinwh-cli tou --set GRID_CHARGE --start 23:00 --end 01:00 \
    --rates-file my_rates.json
```

---

#### `--multi-season FILE`

Loads and applies a full multi-season/multi-day-type strategy list from a JSON
file using `set_tou_schedule_multi`. This is a **complete schedule replacement**
— all seasons and day types are replaced atomically.

The file can be either:
- A bare JSON array (list of season objects)
- An object with a `"strategyList"` key

```json
[
  {
    "seasonName": "Summer",
    "month": "10,11,12,1,2,3",
    "dayTypeVoList": [
      {
        "dayType": 1,
        "dayName": "Weekday",
        "eleticRatePeak": 0.55,
        "eleticSellPeak": 0.40,
        "detailVoList": [
          {"name": "Off-Peak", "startHourTime": "00:00", "endHourTime": "15:00", "waveType": 0, "dispatchId": 6},
          {"name": "Peak",     "startHourTime": "15:00", "endHourTime": "21:00", "waveType": 2, "dispatchId": 8},
          {"name": "Off-Peak", "startHourTime": "21:00", "endHourTime": "24:00", "waveType": 0, "dispatchId": 6}
        ]
      },
      {
        "dayType": 2,
        "dayName": "Weekend",
        "detailVoList": [
          {"name": "Off-Peak", "startHourTime": "00:00", "endHourTime": "24:00", "waveType": 0, "dispatchId": 6}
        ]
      }
    ]
  },
  {
    "seasonName": "Winter",
    "month": "4,5,6,7,8,9",
    "dayTypeVoList": [
      {
        "dayType": 3,
        "dayName": "Everyday",
        "detailVoList": [
          {"name": "Off-Peak", "startHourTime": "00:00", "endHourTime": "24:00", "waveType": 0, "dispatchId": 6}
        ]
      }
    ]
  }
]
```

Validation rules enforced by the library:
1. All 12 months must appear exactly once across all seasons
2. Each season must define `dayType=3` (Everyday) OR both `dayType=1` + `dayType=2`
3. Each `detailVoList` must span exactly 00:00 → 24:00 (1440 minutes)

```bash
franklinwh-cli tou --multi-season seasons.json
franklinwh-cli tou --multi-season seasons.json --json
```

> [!CAUTION]
> `--multi-season` does **not** auto-backup the prior schedule. If you need
> rollback capability, first run `franklinwh-cli raw get_tou_dispatch_detail --json`
> to save the current state before writing.

---

### Supervised Dispatch Flags

#### `--wait`

Activates supervised dispatch mode. When combined with `--set`:

1. **Backup** — saves the current `strategyList` to a local JSON file before submitting
2. **Submit** — applies the new schedule via `set_tou_schedule`
3. **Confirm** — polls `touSendStatus` for up to 90s until the aGate acknowledges
4. **Hold** — prints heartbeats; waits for either:
   - **Auto-exit**: the `--end` time passes (wall-clock deadline)
   - **Manual exit**: Ctrl+C
5. **Restore** — resubmits the saved backup to the aGate and deletes the backup file

**Auto-restore at `--end` time** (added 2026-04-30):
When `--start`/`--end` are provided, the hold loop exits automatically when
the wall clock reaches `--end`. The process terminates cleanly without any
user input. Full-day modes (`--set SELF` without `--start`/`--end`) require
manual Ctrl+C.

```bash
# Charge from grid 23:00–01:00 — process exits at 01:00 and restores
franklinwh-cli tou --set GRID_CHARGE --start 23:00 --end 01:00 \
    --default SELF --wait

# Export from 18:00–20:00 — process exits at 20:00 and restores
franklinwh-cli tou --set GRID_EXPORT --start 18:00 --end 20:00 \
    --default SELF --wait
```

**Heartbeat output:**
```
  ✓ Dispatch active — will auto-restore at 01:00 (58m remaining) or press Ctrl+C to restore now
  Dispatch active — 00:00:30 elapsed — auto-restore in 57m30s — Ctrl+C to restore now
  Dispatch active — 00:01:00 elapsed — auto-restore in 57m00s — Ctrl+C to restore now
  ...

  Schedule window ended (01:00) — restoring original schedule...
✓ Schedule restored (1 season(s), checksum verified)
  Backup deleted: 10060006A00000000000_20260430T025848Z_c4a59515.json
```

**Backup files** are stored in the same directory as `franklinwh.ini`, named:
```
{GATEWAY_SN}_{TIMESTAMP}_{CHECKSUM_PREFIX}.json
```
They are automatically deleted after a successful restore. Stale backups
(older than 7 days) are auto-expired on any `tou` invocation.

> [!WARNING]
> If the process is killed (`kill -9`, power loss, etc.) before the restore
> step, the backup file remains on disk. On the next `tou` invocation, a
> warning is printed: `Unrestored TOU backup from YYYY-MM-DD HH:MM (pid=N)`.
> Run `franklinwh-cli tou --restore` to recover.

---

#### `--restore`

Manually restores the most recently saved (unrestored) TOU backup for the
current gateway. Use this if a `--wait` session was interrupted before the
restore step completed.

If only one backup exists, it is auto-selected. If multiple exist, an
interactive menu is shown.

```bash
franklinwh-cli tou --restore
```

```
  #    Timestamp              Seasons  Age      CLI Args
  ──── ────────────────────── ──────── ──────── ──────────────────────────────────────────
  0    2026-04-30T02:58:48    1        <1d      tou --set GRID_EXPORT --start 12:50 --end

  Auto-selecting the only backup: 10060006A00000000000_20260430T025848Z_c4a59515.json
  Restoring from 10060006A00000000000_20260430T025848Z_c4a59515.json...
✓ Schedule restored (1 season(s), checksum verified)
```

---

## Dispatch Confirmation: `touSendStatus` Behaviour

After submitting a schedule, the API sets `touSendStatus=1` (pending). The
`--wait` flow polls `get_gateway_tou_list()` every 5s for up to 90s waiting
for it to clear to `0`.

Known quirk: `touSendStatus` sometimes clears immediately (before the aGate
has actually processed the schedule) — the value is not always reliable as a
confirmation signal. The `--wait` flow treats `0 or None` as "confirmed" and
proceeds.

If `workMode` is not `1` (TOU) after the poll completes, a warning is printed:
```
⚠ Dispatch sent but workMode=None (expected 1=TOU) after 0s
```
This is common on sites without TOU tariff configured (`tariffSettingFlag=0`).

---

## Common Combinations

```bash
# ── View ───────────────────────────────────────────────────────────────

# Show only what's happening right now
franklinwh-cli tou --next

# Show current tier pricing (for a smart script)
franklinwh-cli tou --price --active-only

# Show full schedule for the current active season only
franklinwh-cli tou --current

# Inspect raw dispatch strategy data
franklinwh-cli tou --dispatch

# ── Set (permanent / fire-and-forget) ──────────────────────────────────

# Charge from grid tonight 23:00–01:00, self-consumption otherwise
franklinwh-cli tou --set GRID_CHARGE --start 23:00 --end 01:00 --default SELF

# Discharge to grid during peak 18:00–20:00, home loads otherwise
franklinwh-cli tou --set GRID_EXPORT --start 18:00 --end 20:00 --default HOME

# Set full-day self-consumption (restore from a manual override)
franklinwh-cli tou --set SELF

# Update only July's season
franklinwh-cli tou --set GRID_CHARGE --start 23:00 --end 01:00 --month 7

# ── Set + auto-restore (supervised) ────────────────────────────────────

# Supervised: auto-restore at 01:00 without needing Ctrl+C
franklinwh-cli tou --set GRID_CHARGE --start 23:00 --end 01:00 \
    --default SELF --wait

# ── Multi-season ────────────────────────────────────────────────────────

# Apply a full summer/winter schedule
franklinwh-cli tou --multi-season my_schedule.json

# ── Scripts and automation ──────────────────────────────────────────────

# Get current buy rate (for cron/automation)
franklinwh-cli tou --price --active-only --no-color

# Machine-readable full schedule
franklinwh-cli tou --json
```

---

## Error Reference

| Error | Cause | Fix |
|-------|-------|-----|
| `Invalid start time: X` | `--start`/`--end` not in HH:MM format | Use `HH:MM` (e.g. `23:00`) |
| `Unknown dispatch mode: X` | Unrecognised `--set` mode | Use `GRID_CHARGE`, `GRID_EXPORT`, `SELF`, `HOME`, `STANDBY`, `SOLAR`, `CUSTOM` |
| `Unknown default mode: X` | Unrecognised `--default` mode | Same list as above |
| `CUSTOM mode requires --file` | `--set CUSTOM` used without `--file` | Add `--file path/to/schedule.json` |
| `File not found: X` | `--file` / `--rates-file` / `--multi-season` path wrong | Check path |
| `Unknown rate key 'X'` | Invalid key in `--rates-file` | See valid keys list in `--rates-file` section |
| `API returned code=X` | Server rejected the payload | Check `--dispatch` output for constraint violations |
| `Dispatch sent but workMode=None` | aGate not in TOU mode | Site may not have TOU tariff configured — check `tariffSettingFlag` |
| `Total elapsed minutes not equal to 1440` | `--file` schedule has gaps or overlaps | Ensure blocks cover 00:00 → 24:00; gaps are auto-filled for `--set` mode |
| `strategyList is empty` | `--multi-season` JSON file has no seasons | Check file structure |
| `Unrestored TOU backup from YYYY-MM-DD` | Prior `--wait` session was interrupted | Run `franklinwh-cli tou --restore` |

---

## Implementation Notes

- **Source module:** `franklinwh_cloud/cli_commands/tou.py`
- **API methods used:** `get_gateway_tou_list()`, `get_tou_dispatch_detail()`, `get_tou_info(option)`, `get_current_tou_price()`, `get_charge_power_details()`, `set_tou_schedule()`, `set_tou_schedule_multi()`, `tou_backup_save()`, `tou_backup_restore()`, `tou_backup_delete()`, `tou_backup_list()`
- **Backup directory:** same directory as `franklinwh.ini` (or CWD if ini not found)
- **Backup format:** JSON with `strategyList`, `checksum` (SHA-256), `cli_args`, `pid`, `timestamp`, `gateway`
- **`--wait` deadline:** computed at dispatch time as a wall-clock `datetime`. If `--end` is already past (e.g. 01:00 called at 02:00), it rolls to tomorrow
- **Stale backup TTL:** 7 days — auto-expired silently on any `tou` invocation
- **Signal handling:** `SIGINT` and `SIGTERM` both trigger graceful restore in `--wait` mode; `loop.add_signal_handler` used (asyncio-native, no `asyncio.shield`)
