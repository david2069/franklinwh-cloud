# Capture Requests — evidence this project needs

> **Purpose:** several open questions cannot be answered from the existing
> capture corpus, which is a **single Australian gateway**. This page states
> exactly what is missing, what to run, and what it would close — so the ask can
> be handed to someone without explaining the whole project.

Per [AP-14](../.agents/policies/evidence_standard.md), these questions stay
open rather than being guessed at. Each one below is currently blocking real
work.

---

## Before sharing anything: redaction

Snapshots and HAR files contain **credentials, tokens, serial numbers, email
addresses and GPS coordinates**. Do not send raw output.

```bash
franklinwh-cli support --save --redact full
```

`--redact full` removes PII rather than masking it. The tool writes a
timestamped JSON file; check it before sending. A HAR capture is **not**
redacted by anything here — it contains live auth tokens and must be scrubbed
by hand, or shared only with someone you trust.

---

## Tier 1 — two commands, no tooling

Anyone with a FranklinWH account can produce these. **No proxy, no certificate
install.** This is the low-friction ask, and it closes most of the US-blocked
questions.

```bash
franklinwh-cli support --save --redact full
franklinwh-cli --json schema --live > schema-live.json
```

### What a US gateway would settle

| Question | What the file shows |
|---|---|
| `DEF-AC-TOPOLOGY-NO-US-SAMPLE` | `grid_voltage_l1_v` / `_l2_v` on a genuine split-phase site. We assume ~120/120; **nobody has confirmed it.** |
| `DEF-PHASE-FLAG-AMBIGUOUS` | Whether any field distinguishes split-phase from single-phase directly, instead of inferring from country |
| `DEF-NEM-TYPE-ZERO-UNRESOLVED` | Whether `nemType: 0` means NEM 2.0 or is an unset sentinel. **661 of 672 corpus samples are `0`, all on an Australian gateway where NEM does not exist.** A US install with a known enrolment settles it |
| `DEF-SDCP-MEANING-UNSOURCED` | What `sdcpFlag` tracks, and whether it is set outside SDCP's service area |
| `DEF-JA12-ENTRANCE-VS-JOINED` | Needs a gateway reporting `ja12Entrance: 1` (California). Would show whether `*Entrance` means *eligible* or *enrolled* — which also governs how SGIP and Battery Bonus are reported |
| `DEF-OPERATOR-RSSI-SCALE-UNSOURCED` | Any gateway with a different cellular signal level. We have **4 samples, all the value 22**, and assert a "0–52 scale" on that basis in 10 places |

### From any gateway, including AU

```bash
franklinwh-cli --json bms > bms.json
```

Closes `DEF-BMS-211-STATE-CODES-UNDECODED`: `bmsState`, `mosState`,
`inverterStatus`, `DCDCStatus`, `runMode` and `switchState` are printed as raw
integers because no cmdType 211 payload exists in the corpus to establish their
domains.

---

## Tier 2 — HAR capture

Needs HTTP Toolkit or similar, plus a certificate on the phone. See
[CAPTURING_MOBILE_APP_TRAFFIC.md](CAPTURING_MOBILE_APP_TRAFFIC.md).

### A. Smart Circuits on newer hardware — the largest gap

**Who:** a US user with **Smart Circuits V2** or an **aHub**.

**What to do:** open the FranklinWH app, go to Smart Circuits, view the
configuration, and **edit a schedule** — set a window, save it.

**What it would close:**

- **`FEAT-SC-CMDTYPE-387-389`** — a third-party fork drives smart circuits with
  cmdType **387/389**, whose response carries a structured
  `data["smartSwitch"][i]["schedule"]`. **Neither appears anywhere in our 44
  captures** (highest observed: 354). If real, this is a second Smart Circuits
  protocol we should support alongside cmdType 311 — see
  [CAPABILITY_RESOLUTION_SPEC.md](CAPABILITY_RESOLUTION_SPEC.md).
- **`DEF-SC-TIMESET-UNDECIPHERED`** — `SwNTimeSet` is observed only as
  `[1,0,1,0]` and `[0,0,0,0]`, never changing. Its meaning is unknown.
- **`FEAT-SC-SCHEDULE-SETTER`** — there is **no way to write a circuit
  schedule** today. A circuit can be told to follow a schedule it has no way of
  receiving. Blocked because writing a guessed array layout could switch real
  loads at the wrong times.
- **`DEF-CATALOG-AHUB-CIRCUIT-COUNT`** — aHub supports **4×240 V or 8×120 V**
  circuits (vendor manual p.10), but cmdType 311 has three hardcoded slots and
  cannot represent them. How the API enumerates aHub circuits is unknown.

**An edit is the critical part.** Every captured sample is the unconfigured
default (`00:00` / `23:59`, all flags `0`), so nothing reveals which array
position means what. One save, with a schedule that differs between slots,
resolves the layout.

### B. A DST transition

**Who:** anyone, but the capture must **span the changeover**.

Closes the open questions in [TIME_AND_TIMEZONES.md](TIME_AND_TIMEZONES.md):
whether the numeric `timeZone` offset tracks DST or stays at standard time,
whether the gateway applies DST itself, and how a TOU boundary inside a skipped
or repeated hour is resolved. **TOU blocks are wall-clock**, so they shift by an
hour in absolute terms twice a year — which matters for anyone coordinating
against a market price or an external signal.

### C. Ethernet port identity

**Who:** anyone willing to plug a household cable in, **on site**.

Closes `DEF-ETH-PORT-IDENTITY-UNCONFIRMED`. Vendor port naming is
revision-dependent and **reverses meaning**: the household cable goes to "Eth1"
in the Installation Guide, but to "Eth2" on aGate X 1.1, where "Eth1" is the
**Debug** port. Plug in, then note which API field (`eth0` or `eth1`) acquires
the address — and record `sysHdVersion` alongside, since the answer differs per
revision.

---

## Why this page exists

The corpus is 44 captures from one gateway in one market. That is enough to have
built most of this library, and **not** enough to answer anything about
hardware, tariffs or grid topology we do not have.

The honest position is that several defaults here — US split-phase voltages,
`nemType` labels, the `0–52` cellular scale — are inferences from market
standards and vendor datasheets, not observations. They are marked as such in
the code. A single cooperative user in another market would convert a
meaningful share of this list into settled fact.
