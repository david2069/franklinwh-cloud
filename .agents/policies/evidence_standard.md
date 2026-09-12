# AP-14: Evidence Standard for a Reverse-Engineered API

> Every claim in this repository about what a FranklinWH field *means* is an
> inference. There is no specification. This policy sets out what may be
> asserted, what must be labelled, and how to cite.

## Why this exists

Five defects in this repository were caused by acting on an unsourced comment
rather than checking evidence. In each case the comment was plausible, had
survived review, and was wrong:

| Defect | The unsourced claim | Reality |
|---|---|---|
| `DEF-CONNTYPE-ENCODING-WRONG` | "`connType` uses 0=4G, 1=WiFi, 2=Ethernet" | 20,471 samples show `{2, 3, 4}`; 0 and 1 never occur |
| `DEF-NEM-TYPE-ZERO-UNRESOLVED` | catalog maps `nemType: 0` → "NEM 2.0" | 661 of 672 samples are 0, on Australian gateways where NEM does not exist |
| `DEF-OPERATOR-RSSI-SCALE-UNSOURCED` | "`operatorRSSI` is a 0-52 vendor scale", asserted in 10 places | 4 samples, all the value 22 |
| `DEF-ETH-PORT-IDENTITY-UNCONFIRMED` | "the vendor's Eth1 is the internet port" | True for one revision; on aGate X 1.1 Eth1 is the **Debug** port |
| `DEF-PROGRAMME-ENTRANCE-OVERCLAIM` | `*Entrance = 1` rendered as "Enrolled" | Field name denotes an entry point *offered*; enrolment never established |

The pattern is identical every time: a confident label is worse than a blank
one, because a blank invites a question and a wrong label ends it.

## What we fundamentally cannot determine

The API is reverse-engineered from captured traffic and vendor PDFs. For any
field we observe, **these possibilities are indistinguishable from outside**:

- **Deprecated** — retained for older app versions, ignored by the backend.
- **Not yet released** — shipped in the schema ahead of the feature.
- **Regionally gated** — meaningful in one market, inert in another.
- **Firmware-gated** — present only on some hardware revisions.
- **Tier-gated** — visible only to installer or admin accounts.
- **Defective** — the backend's own bug.
- **Simply unused** — carried by a shared DTO and never populated.

**Never assert which of these applies.** "`bbDischargePower` is null in 3,930
samples" is an observation. "`bbDischargePower` is deprecated" is a guess
wearing an observation's clothes.

The same applies to the cloud's *behaviour*: we cannot tell a FranklinWH defect
from intended behaviour we have misunderstood. cmdType 339 reporting
`awsStatus=0` while answering through the cloud looks like a bug, and is
recorded as "contradicts observable reality" — not as "FranklinWH bug".

### Absence is not evidence

- A field **absent from the corpus** may simply never have been exercised by
  the captured sessions. `4GSignalStrength` appears nowhere in 44 captures; that
  does not mean the firmware never sends it.
- A field **present and null** may be inapplicable, unset, not-yet-computed, or
  withheld. Do not collapse these into "not applicable".
- **One account, one region.** Nearly the whole corpus is a single Australian
  gateway. Any claim of the form "the API always…" is really "this gateway,
  in this market, during these captures…".

## Evidence tiers

Every claim about wire semantics carries a tier. Use these words literally.

| Tier | Means | Requires |
|---|---|---|
| **CONFIRMED** | Observed in traffic or stated by the vendor | A citation: sample count, or document + page |
| **OBSERVED** | Seen once on live hardware | Date and the `tests/results/` file |
| **INFERRED** | Reasoning from confirmed facts | The reasoning, plus what would disprove it |
| **ASSUMED** | A working guess | Explicitly flagged, plus what would settle it |

### Citing

A citation is a number or a reference, never an adjective:

```python
# CONFIRMED: connType observed as {2: 559, 3: 19797, 4: 115} across 20,471
# runtimeData samples in the HAR corpus. Values 0 and 1 never occur.

# CONFIRMED: FranklinWH System Installation Guide p.59 — "The aGate supports
# only 2.4Ghz Wi-Fi connection to the family router."

# INFERRED: eth0 is static on 172.16.1.1, unrelated to the household LAN, so
# it is probably the Debug port. Disproved by any capture where eth0 holds a
# household-range lease.

# ASSUMED: nemType 0 may be an unset sentinel rather than NEM 2.0. Settled by
# a capture from a US install with a known enrolment.
```

"Verified", "known to be", "always" and "confirmed" without a number are not
citations. If the number is not to hand, the tier is INFERRED or ASSUMED.

## Rules

1. **Record speculation — labelled.** Speculation is valuable; it is how the
   next question gets asked. Write it as ASSUMED with what would settle it, so
   the next reader inherits a question rather than a false fact.
2. **Never promote a tier without new evidence.** A claim does not become
   CONFIRMED by being repeated, surviving review, or being convenient.
3. **A comment is not a source.** If an existing comment is the only basis for
   a change, verify against the corpus first. That step alone would have
   prevented every defect in the table above.
4. **Prefer the blank to the guess in user-facing output.** Where a label
   would assert more than the evidence supports, say less. `nem_type` is blank
   outside the US; `bmsState` prints a raw code rather than a decoded word.
5. **Keep the raw value when withholding a label.** `flags.nem_type_raw` and
   `flags.ja12_joined` exist so that declining to interpret does not destroy
   the evidence a future answer needs.
6. **Asymmetric claims get asymmetric treatment.** `*Entrance = 0` safely
   implies not enrolled; `= 1` does not safely imply enrolled. Only the unsafe
   direction needs hedging.
7. **State disagreements between sources.** Where captures and vendor
   documentation conflict, record both and say which is being followed — see
   `NETWORK_CONNECTIVITY_DESIGN.md` §2.3c and §2.3d, where two vendor documents
   contradict each other on port naming.

## Applying this to defect tickets

A ticket asserting an API defect must distinguish **our** defect from
**theirs**. Ours is actionable; theirs is an observation to design around and
cannot be fixed here. When in doubt it is ours — that assumption is cheap and
the reverse is not.
