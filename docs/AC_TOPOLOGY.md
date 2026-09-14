# AC Topology: split-phase, single-phase, three-phase

> **Short version:** the FranklinWH API models everything as **split-phase**
> (L1 + L2), including single-phase installations where no L2 exists. On an
> AU/NZ system, `L1` and `L2` are not two independent legs — treat
> `gridLineVol` as the real measurement.

Evidence tiers per [AP-14](../.agents/policies/evidence_standard.md).

---

## What the API reports

Every AC reading arrives with L1/L2 companions, regardless of what is actually
installed:

| Concern | Fields |
|---|---|
| Grid voltage | `gridVol1`, `gridVol2`, `gridLineVol` |
| Inverter | `invVolt1`, `invVolt2`, `invLineVol` |
| Current | `gridCurr1`, `gridCurr2` |
| BMS detail | `gridVoltAN`, `gridVoltBN`, `solarVoltAN`, `solarVoltBN` |

The A/B and 1/2 naming is split-phase vocabulary: two 120 V legs in antiphase
summing to 240 V, which is the North American residential standard.

## On a single-phase system this is a modelling artifact

**OBSERVED** on a live AU gateway (user report, 2026-09):

```
GRID VOLTAGES      INVERTER LINES      Frequency
  L1   119.7 V       L1   119.6 V        49.93 Hz
  L2   119.7 V       L2   119.6 V
  Line 239.4 V       Line 239.4 V
```

**CONFIRMED** from the vendor datasheet (*System Datasheet aGate X-01-AU &
aPower X-02-AU*): the AU/NZ system is **`230/240 VAC L/N/PE`, 50 Hz** — line,
neutral and protective earth. There is no second active conductor.

So the two "legs" are the API halving a single L-N measurement, or reporting
the same measurement twice. `49.93 Hz` confirms this is a 50 Hz installation,
not a US one. **`L1 = 119.7 V` does not mean the site has 120 V legs.**

### Consequences

- **Do not treat L1 and L2 as independent measurements** on single-phase. They
  are not two circuits, and an alarm on "L2 low" has no physical referent.
- **Do not sum them.** `gridLineVol` is already the L-N voltage. (This library
  performs **no** L1/L2 arithmetic anywhere — verified — so nothing currently
  double-counts. Keep it that way.)
- **`gridLineVol` is tenths of a volt** — `2440` = 244.0 V. Handled in
  `mixins/stats.py`.

## The `three_phase` flag is ambiguous

`isThreePhaseInstall` is a **boolean**, and `models.py` documents `0` as
"split-phase". That is a US-centric reading: on an AU/NZ site, `0` means
**single-phase**, which is a different topology.

So the library can distinguish three-phase from everything-else, but **cannot
distinguish split-phase from single-phase** from that flag alone. Today the
gap is bridged by region:

```python
is_single_phase = not snap.flags.three_phase
is_au = snap.site.country_id == 3
if is_au and is_single_phase:   # ... treat as L-N, suppress L2
```

**ASSUMED:** that `country_id == 3` implies single-phase. It holds for AU/NZ
residential and matches the datasheet, but it is an inference from market, not
a reading from the device. A US 208 V commercial installation, or any market
added later, would not be covered.

## Current handling is inconsistent

| Surface | Single-phase aware? |
|---|---|
| `discover` | **Yes** — labels "Voltage"/"Current", suppresses L2 for AU |
| `diag` | Partial — says "Single Phase (L1)" but renders L1/L2 elsewhere |
| `bms` | **No** — always "Grid Feed (L1/L2)", "Inv Bus (L1/L2)" |
| `support` | **No** — emits `grid_voltage_l1_v` / `_l2_v` unconditionally |
| `schema` | **No** — lists both with no topology note |

`discover` got this right and the rest were never updated. Tracked as
`DEF-AC-TOPOLOGY-INCONSISTENT`.

## Guidance

**Reading:** on single-phase, use `gridLineVol` / `invLineVol`. Ignore the
per-leg values, or present them explicitly as an API artifact.

**Building automations:** do not alarm on per-leg imbalance on single-phase —
the legs are derived, so imbalance is meaningless. Frequency and line voltage
are the meaningful grid-quality signals.

**Three-phase:** `isThreePhaseInstall == 1`. How L1/L2/L3 map onto these
two-leg fields is **not established** — no three-phase capture exists in the
corpus. Do not assume L1/L2 carry two of the three phases.

## Not established

- Whether single-phase L1/L2 are a halved measurement or the same value
  reported twice. The observed values are equal to 0.1 V, which is consistent
  with either.
- Whether any field distinguishes split-phase from single-phase directly,
  removing the need for the region inference.
- How three-phase sites populate these fields.
- Whether 208 V US commercial installs behave as split-phase here.
