# Smart Circuits & Generator — API and CLI Design

> **Status:** BACKLOG — design only, no code. Queued per
> [AP-1](../.agents/policies/change_management.md) (Queue → Plan → Execute).
> Write paths are API-affecting and need sign-off (`CLAUDE.md` rule 6).
>
> Evidence tiers per [AP-14](../.agents/policies/evidence_standard.md).

## 1. Goal

One coherent surface for Smart Circuits and the Generator module:

- **Read** per-circuit configuration, schedule **and** live metrics together.
- **Write** switch state (exists), schedules (missing) and generator mode
  (exists), through a consistent interface.

Today these are split across two commands, two payload shapes and two CLI
commands, and the schedule half cannot be written at all.

## 2. What exists

| Concern | Source | Method | CLI |
|---|---|---|---|
| Circuit config, mode, SoC cutoff, schedule | cmdType **311** | `get_smart_circuits()` | `sc` |
| Circuit live metrics | cmdType **353/354** | `get_accessories_power_info()` | `accessories` |
| Circuit on/off, mode | 311 write | `set_smart_circuit_state()`, `set_smart_switch_state()` | `sc --on/--off` |
| SoC cutoff, load limit | 311 write | `set_smart_circuit_soc_cutoff()`, `set_smart_circuit_load_limit()` | `sc --cutoff/--load-limit` |
| **Circuit schedule write** | — | **none** | **none** |
| Generator config/state | 311 + 203 | `get_generator_info()` | `accessories` |
| Generator live metrics | cmdType **354** | `get_accessories_power_info(3)` | — |
| Generator mode | | `set_generator_mode()` | — |

**CONFIRMED** cmdType 354 payload (corpus sample, 2025-10-04):

```
opt, result, Sw1Volt, Sw2Volt, SW1Curr, SW2Curr, SW1ExpPower, SW2ExpPower,
SW1ExpEnergy, SW2ExpEnergy, CarSWCurr, CarSWPower, CarSWExpEnergy,
CarSWImpEnergy, CarSwConsSupExpEnerge, power, curr, volt, freq, genpowerGen
```

Note: circuits use an `SW`/`Sw` prefix, V2L uses `CarSW`, and the **generator
fields are unprefixed** (`power`, `curr`, `volt`, `freq`, `genpowerGen`) — so
they cannot be disambiguated by name alone.

## 3. Defects this design must not inherit

- **`DEF-ACCESSORY-POWER-OPTION-TYPE`** — `get_accessories_power_info(option=1)`
  declares an **int** default but compares against **strings** (`option == "1"`).
  The default call therefore matches nothing and returns the raw payload, not
  the documented Smart Circuits view. Only caller passes `"0"`, so it has gone
  unnoticed.
- **Hardcoded to two circuits.** The Smart Circuits branch builds ids 1 and 2
  only. US SC V2 has three (`circuit_count: 3`); aHub has 4–8.
- **`DEF-SC-SCHEDULE-NOT-RENDERED`** (fixed) showed the config path already
  carried schedule data nothing displayed. The unified view must not repeat
  that: if a field is parsed, it is rendered or explicitly excluded.

## 4. Proposed SDK surface

```python
async def get_smart_circuit_detail(self, circuit: int | None = None) -> dict
```

Composes **311** (config + schedule) with **354** (live metrics) into one
per-circuit view. `circuit=None` returns all. Circuit count comes from
`ResolvedCapabilities.circuit_count`, never a hardcoded range.

```python
{
  "id": 1, "name": "Circuit 1",
  "config":   {"mode", "is_on", "soc_cutoff_enabled", "soc_cutoff_limit",
               "load_limit", "pro_load_type"},
  "schedule": {"slots": [...], "enabled": [...], "raw_time_set": [...]},
  "metrics":  {"current", "voltage", "power", "energy", "scale_note"},
  "source":   {"config_cmd": 311, "metrics_cmd": 354},
}
```

```python
async def get_generator_detail(self) -> dict
```

Same shape for the generator: `config` from 311/203 (`genStat`, `genStartSoc`,
`genStopSoc`, `genEn`), `metrics` from 354 (`power`, `curr`, `volt`, `freq`,
`genpowerGen`).

### Writes

```python
async def set_smart_circuit_schedule(self, circuit, slots, *, confirm=False)
async def set_generator_soc_thresholds(self, start_soc, stop_soc, *, confirm=False)
```

Both ride the existing `_update_smart_circuit_config()` read-modify-write 311
cycle, which already handles the full-overwrite semantics. `confirm=True`
required, matching `switch_to_wifi()`.

**`set_smart_circuit_schedule` is blocked** — see §6.

## 5. Proposed CLI

```
fwh sc                      # unchanged: config + schedule for all circuits
fwh sc --detail [N]         # config + schedule + live metrics, one or all
fwh sc --metrics            # metrics only, watch-friendly
fwh sc --set-schedule N ... # BLOCKED, see §6
fwh gen                     # generator config + metrics + mode
fwh gen --mode MODE         # wraps set_generator_mode()
fwh gen --soc START STOP    # start/stop SoC thresholds
```

`--json` everywhere, already global. Generator currently has **no CLI command at
all** — `gen` is new; `accessories` keeps its existing summary role.

## 6. Blockers — do not implement past these

1. ~~**`DEF-SC-TIMESET-UNDECIPHERED`**~~ — **CLEARED 2026-09-18.** `SwNTimeSet`
   is `[1,0,1,0]`: the four slots are **two start/end pairs**. Confirmed by the
   app's own message *"Only two time slots can be scheduled"* and by live reads.
2. ~~**Slot pairing unverified**~~ — **CLEARED.** Also established live:
   `SwNTimeEn` arms slots individually (the app's *Time Schedule* row read
   **Off** with the bits zeroed, **On** with them set); `SwNFreq` is a cycle in
   **days** with `0` = *"Once only"*; and execution date is `base + k x cycle`
   (2026-06-19 + 2x60 = 2026-10-17, matching the app exactly).
3. **Metric scaling is unverified.** `freq: 500` is almost certainly 50.0 Hz
   (÷10), and `Sw1Volt: 1004` plausibly 100.4 V — but `volt: 2` alongside
   suggests the generator fields may scale differently, or be inactive. **Do not
   apply a divisor without establishing it per field.** Until then, expose raw
   values with an explicit `scale_note`, as the JA12 block does.
4. **Generator field names are unprefixed**, so `power`/`curr`/`volt`/`freq`
   cannot be attributed to the generator by name alone — only by position in the
   354 payload. Confirm before presenting them as generator readings.

**Blockers 1 and 2 were cleared by live hardware, not a capture.** Blocker 3
still stands: a 354 response with the generator running would settle the
scaling.

### The write path — solved, and not where it was expected

`set_smart_circuit_schedule()` shipped and then **silently did nothing**: the
gateway returned `result: 0` and discarded every write. The cause was one
field. **`SwNMsgType` selects what KIND of change a 311 write is**, and the
firmware drops a write whose kind does not match its content:

| `SwNMsgType` | corpus | content | meaning |
|---|---|---|---|
| `1` | 39 writes | `Mode` 0/1, schedule disarmed | switch the circuit on/off |
| `2` | 9 writes | `Mode` **2**, schedule armed | edit the schedule / config |

`_update_smart_circuit_config()` hardcoded `1`, so schedule, SoC-cutoff and
load-limit writes all went out as **switch commands** and vanished. Switch
writes were never broken, which is why it went unnoticed for months — nothing
read back. Fixed by making `msg_type` a parameter. See
`DEF-311-CONFIG-WRITES-WRONG-MSGTYPE`.

**Method note worth keeping:** the first diagnosis ran five experiments against
the transport — stale dates, propagation delay, payload shape, frame envelope —
and found nothing, because the fault was in a field already being sent. The
answer was in the capture corpus the whole time: **278 cmdType 311 requests
across 24 HAR files, 52 of them writes**. One query correlating `MsgType`
against write content found it. Check the corpus before instrumenting the wire.

## 7. Sequencing

| Step | Scope | Blocked by |
|---|---|---|
| **A** | Fix `DEF-ACCESSORY-POWER-OPTION-TYPE`; drive circuit count from capabilities | — |
| **B** | `get_smart_circuit_detail()` + `sc --detail` (read-only) | — |
| **C** | `get_generator_detail()` + `fwh gen` (read-only) | blocker 4 for labelling |
| **D** | `fwh gen --mode` / `--soc` (wraps existing setters) | sign-off |
| **E** | `set_smart_circuit_schedule()` + `sc --set-schedule` | ✅ **done** — verified live |

A–C are unblocked and deliver most of the value: every metric and schedule
already retrievable, in one place, for circuits and generator alike. **E is
complete** and verified against hardware: the write reports *stored and
verified*, circuit 1 and the global fields are untouched by a circuit-2 write,
and the read-back reports honestly when a write does not land.

## 7a. Transport asymmetry — generator is REST, circuits are not

Worth knowing before looking for an endpoint that does not exist:

| | read | write |
|---|---|---|
| **Generator** | `selectIotGenerator` (REST) | `updateIotGenerator` (REST) |
| **Smart Circuits** | cmdType 311 over `sendMqtt` | cmdType 311 over `sendMqtt` |

**There is no REST endpoint for Smart Circuits** — no `selectIotSwitch`,
no `updateIotSwitch`, nothing in the corpus. Both directions go through the
CRC-framed MQTT envelope, which is why circuit writes are a read-modify-write
of the whole `Sw*` block while generator writes post a handful of fields. It
also explains why `set_generator_charge_schedule()` worked immediately while
the circuit equivalent did not: they share no transport code.

## 8. Open

- Does `353/354` expose `SW3*` on a three-circuit system? The corpus is an
  AU two-circuit gateway, so **absence of `SW3Curr` here is not evidence**.
- aHub's 4–8 circuits cannot be represented by 311's `Sw1`/`Sw2`/`Sw3` slots —
  see `FEAT-SC-CMDTYPE-387-389`. This design targets 311; an aHub path is
  separate work.
