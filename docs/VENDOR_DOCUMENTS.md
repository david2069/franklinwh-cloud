# Vendor Documents — citation register

> Documents cited across this project, with the **version and date printed in
> the document itself**. Cite from here rather than by title alone: a title
> without a version ages silently, and FranklinWH revises these.

Per [AP-14](../.agents/policies/evidence_standard.md), a vendor statement is
**CONFIRMED** evidence — but only against a stated revision. Behaviour has
already been observed changing between revisions (see the Eth port naming
below), so "the manual says" is not a durable citation on its own.

## Register

| Key | Document | Version | Issued | Pages |
|---|---|---|---|---|
| `INST-1.2.07` | FranklinWH System Installation Guide | **1.2.07** | **May 09, 2026** | 89 |
| `COMM-AU-2.15.0` | FranklinWH Commissioning Guide – AU & NZ (App Version 2.15.0) | **2.15.0** | **June 12, 2026** | 61 |
| `COMM-2.8.0` | FranklinWH Commissioning Guide (MAC 1 & aPower 2 & aPower S) | — | **Dec 30, 2025** | 82 |
| `DS-AGATE-AU-V1.7` | System Datasheet aGate X-01-AU & aPower X-02-AU | **V1.7** | **2026-05-30** | 2 |
| `AHUB-V1.0` | aHub Installation and Operations Manual | **V1.0** (initial release) | **2026-01-22** | 37 |
| `SPAN-APPNOTE-FWH` | SPAN Tech Portal — *App Note: Integration with FranklinWH* | — | retrieved 2026-09-18 | — |
| `DS-SC-AU` | Smart Circuits Module Datasheet (AU & NZ) | — | **2026-03-25** | 2 |

Versions above are quoted from the documents' own title pages or revision
history, **not** inferred from filenames or PDF metadata. Where a document
prints no version, the column reads `—` rather than guessing.

## Why revisions matter here

Two documents in this register **contradict each other**, and the contradiction
is only resolvable because each is dated and scoped:

| Source | Hardware | Household cable → | Other port |
|---|---|---|---|
| `INST-1.2.07` p.62 | (unqualified) | **Eth1** | — |
| `COMM-2.8.0` p.7 | aGate X 1.1 (`AGT-R1V1-US`) | **Eth2** | **Eth1 (Debug)** |
| `COMM-2.8.0` p.7 | aGate X 1.3 / 1.3.1 | single **ETH** port | — |

"Eth1" is the internet port in one and the **Debug** port in the other. Citing
either without its revision and hardware scope produces a confident wrong
answer — which is how `DEF-ETH-PORT-IDENTITY-UNCONFIRMED` arose.

## Citations in use

| Claim | Source |
|---|---|
| AU/NZ supply is `230/240 VAC L/N/PE`, 50 Hz | `DS-AGATE-AU-V1.7` |
| AU/NZ Smart Circuits: two circuits per aGate | `DS-AGATE-AU-V1.7` |
| aGate X-01-AU = `AGT-R1V1-AU`; aPower X-02-AU = `APR-05K15V1-AU` | `DS-AGATE-AU-V1.7` |
| aGate joins 2.4 GHz Wi-Fi only | `INST-1.2.07` p.59 |
| Household cable to Eth1 | `INST-1.2.07` p.62 |
| 4G is backup only | `INST-1.2.07` p.59 |
| aGate AP is `AP_<last 9 of SN>`, password `<last 12 of SN>` | `INST-1.2.07` p.59, `COMM-AU-2.15.0` p.11 |
| Port naming differs by revision; Eth1 is Debug on aGate X 1.1 | `COMM-2.8.0` p.7 |
| Wi-Fi is commissioned over the aGate's own hotspot, locally | `COMM-AU-2.15.0` pp.10–13 |
| 4G connected by default; app offers Skip | `COMM-AU-2.15.0` p.12 |
| Phone may drop the aGate connection after a successful Wi-Fi change | `COMM-AU-2.15.0` p.12 |
| aHub: 4×240 V or 8×120 V circuits, programmable scheduling | `AHUB-V1.0` p.10, p.28 |
| SPAN link is SunSpec Modbus TCP 502, aGate as client; SPAN Aux Comms/ETH-1 to aGate Ethernet; SPAN supplies the aGate's internet | `SPAN-APPNOTE-FWH` |

> **Note on `SPAN-APPNOTE-FWH`:** the SPAN Tech Portal is a JavaScript-rendered
> Salesforce site and cannot be fetched programmatically; this entry was
> recorded from screenshots. It prints no version or date, so the register
> records only the retrieval date — an honest `—` rather than an invented
> revision.

## Keeping this current

When a newer revision appears, **add a row — do not overwrite one.** A claim
cited against `INST-1.2.07` remains true of that revision even after 1.3 ships;
what changes is whether it is still true of current hardware. Overwriting
destroys the ability to tell those apart, which is the whole reason the Eth port
contradiction was resolvable.
