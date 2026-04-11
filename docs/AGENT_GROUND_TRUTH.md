# FranklinWH Cloud — Agent Ground Truth

> [!CAUTION]
> This document contains **established facts** confirmed by live hardware data
> and prior deliberate decisions. AI agents MUST treat every item here as
> authoritative. Do NOT re-derive, second-guess, or "correct" any of these
> without explicit user approval AND new live evidence that contradicts them.
>
> Repeated re-investigation of these facts wastes time and introduces
> regression bugs. If you think something here is wrong, **ask the user first**.

---

## 1. Relay encoding — ALL relays

**`1 = OPEN (connected)`, `0 = CLOSED (disconnected)`**

> [!CAUTION]
> This has been flipped incorrectly multiple times by successive agents.
> DO NOT change this. DO NOT "correct" it based on electrical engineering
> intuition. This is the vendor's convention, confirmed by live hardware.

This applies uniformly to **every** relay field in the library, including:
- Primary relays from `runtimeData.main_sw[]` (cmdType 203)
- Extended relays from `get_power_info` (cmdType 211)

### Live evidence (confirmed 2026-04-11)

```
get_device_composite_info → runtimeData.main_sw: [1, 0, 1]
  grid_relay1     = 1  →  CLOSED  (grid is connected ✓)
  generator_relay = 0  →  OPEN    (no generator ✓)
  solar_relay1    = 1  →  CLOSED  (solar producing ✓)

get_power_info (cmdType 211):
  gridRelayStat   = 1  →  CLOSED  (grid connected ✓)
  solarRelayStat  = 1  →  CLOSED  (solar connected ✓)
  oilRelayStat    = 0  →  OPEN    (no generator ✓)
  gridRelay2      = 1  →  CLOSED
  blackStartRelay = 1  →  CLOSED
  pvRelay2        = 0  →  OPEN
  BFPVApboxRelay  = 0  →  OPEN
```

### What NOT to do
- Do NOT write "1=CLOSED (connected)" — this is the **wrong** way round for this vendor
- Do NOT add "inversion" notes between primary and extended relays — there is no inversion
- Do NOT re-derive relay encoding from first principles — use this document
- Do NOT "fix" this based on normal electrical relay conventions; vendor uses their own

---

## 2. GridConnectionState enum — four states, no ambiguity

The four states and their detection logic (from `mixins/stats.py`):

| State | Condition |
|-------|-----------|
| `NOT_GRID_TIED` | `client._not_grid_tied == True` (set at construction, rare) |
| `OUTAGE` | `offGridFlag == 1` (firmware-authoritative real outage) |
| `SIMULATED_OFF_GRID` | `main_sw[0] == 0` OR `offgridreason != 0` → then `get_grid_status().offgridState == 1` |
| `CONNECTED` | Default — none of the above |

### Dual-gate design (do NOT simplify)
The `SIMULATED_OFF_GRID` check uses a dual-gate because the API reports
`offgridreason=1` **before** `main_sw` updates due to relay settling lag.
Both conditions must be checked. This was confirmed by live testing on 2026-04-10.

### What NOT to do
- Do NOT revert to a boolean `grid_outage` field — it was replaced by this enum
- Do NOT collapse the dual-gate into a single condition
- Do NOT call `get_entrance_info()` inside `get_stats()` — `_not_grid_tied` is
  set at `Client()` construction by the integrator from its DB

---

## 3. Operating mode canonical name

**"Time-Of-Use"** — always hyphenated, capitalised exactly this way.

| ❌ Wrong | ✅ Correct |
|----------|-----------|
| `Time of Use` | `Time-Of-Use` |
| `Time Of Use` | `Time-Of-Use` |
| `TimeOfUse` | `Time-Of-Use` |
| `TOU` (as a display name) | `Time-Of-Use` |

`TOU` is acceptable as an abbreviation in technical/internal contexts only
(variable names, logging, CLI section headers). User-facing strings must use
`Time-Of-Use`.

Source of truth: `franklinwh_cloud/const/modes.py` → `OPERATING_MODES[1]`

---

## 4. `_not_grid_tied` — set at construction, never lazily populated

`Client._not_grid_tied` is a **constructor parameter**, not a lazy-populated cache.
`get_entrance_info()` is **never called inside `get_stats()`** for this purpose.

```python
# CORRECT — integrator reads from DB on startup, passes in
client = Client(auth, gateway, not_grid_tied=db_value)

# WRONG — do not do this
# if self._not_grid_tied is None:
#     entrance = await self.get_entrance_info()  ← REMOVED
```

The integrator (FHAI) is responsible for fetching `gridFlag` from
`get_entrance_info()` on first run, persisting it to its `static_site_data` DB
table, and passing it into `Client()` on subsequent restarts.

---

## 5. Totals fields — `kwhSolarLoad` / `kwhGridLoad` / `kwhFhpLoad` / `kwhGenLoad`

These fields appear to return **cumulative Wh** (possibly lifetime totals), **not**
daily kWh. Live evidence: values of `13442`, `3933`, `2632` observed on a normal day
where daily generation was ~30 kWh.

- Treat these fields with caution — do not display as "today's kWh"
- The daily totals to use are: `kwh_sun`, `kwh_uti_in`, `kwh_uti_out`, `kwh_fhp_chg`,
  `kwh_fhp_di`, `kwh_load` (from `Totals.solar`, `.grid_import`, etc.)
- Status: **unconfirmed** — pending cross-reference against FEM app lifetime view

---

## 6. `GridStatus` enum — write path only

`GridStatus` (in `franklinwh_cloud.models`) is used **exclusively** for the
`set_grid_status()` write path. It is **not** used for telemetry or status reporting.

- Telemetry: use `GridConnectionState` (read path)
- Control: use `GridStatus` (write path)

Do NOT remove `GridStatus`. Do NOT use `GridConnectionState` for `set_grid_status()`.

---

## 7. Relay field mapping — cmdType 211 raw names

| Python attribute | Raw API field (get_power_info) |
|-----------------|-------------------------------|
| `grid_relay2` | `gridRelayStat` |
| `black_start_relay` | `blackStartRelay` |
| `pv_relay2` | `pvRelay2` |
| `bfpv_apbox_relay` | `BFPVApboxRelay` |

Note: the `gridRelay2` field in the raw API is a **different** field from
`gridRelayStat`. `grid_relay2` in the library maps to `gridRelayStat` (the
primary second contactor status), not to the raw `gridRelay2` field.

---

## 8. `--json` flag position — works anywhere

Global flags (`--json`, `--no-color`, `-v`, etc.) can appear **before or after**
the subcommand. The CLI pre-normalises argv to hoist them before the subcommand.

```bash
franklinwh-cli schema --live --json      # works ✓
franklinwh-cli --json schema --live      # works ✓
franklinwh-cli status --json             # works ✓
```

---

## Maintenance

When you confirm a new ground-truth fact, **add it here immediately** before
making any code changes. This document is the first thing any agent should read.

Reference this file path in your onboarding: `docs/AGENT_GROUND_TRUTH.md`
