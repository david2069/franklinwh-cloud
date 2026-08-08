# Network Probe Test Plan — Remote-Safe Runbook

> **Operational runbook** for `tools/network_probe.py`, written for the case where **nobody
> is on site**. Companion to [Network Connectivity & WiFi Switching](NETWORK_CONNECTIVITY_DESIGN.md),
> which carries the protocol analysis; this document is only about what is safe to run,
> in what order, and what to do when it goes wrong.
>
> Governed by `.agents/policies/live_test_protocol.md` (AP-13). Every run writes evidence to
> `tests/results/`.

---

## 1. The safety invariant

Everything in this plan rests on one property:

> **As long as the aGate falls back to 4G and reconnects to the FranklinWH cloud, control is
> never lost.** From there the preferred primary (WiFi or Ethernet) can be reconfigured
> remotely, and the aGate will move back to it on its own.

This is not a hope — it is the observed behaviour of the hardware:

| Date | Event | Outcome |
|---|---|---|
| 2026-03-21 | WiFi associated but lost its DHCP lease | aGate fell back to 4G unprompted, stayed cloud-reachable; only the WiFi config needed fixing ([incident note](troubleshooting/2026-03-21_wifi_dhcp_failure.md)) |
| 2026-08-08 ~08:25 | On 4G, WiFi enabled at 76% but holding no lease | cellular carrying the connection |
| 2026-08-08 ~09:07 | WiFi obtained a lease | aGate moved itself back to WiFi, no command issued |
| HAR corpus | 19 transport transitions | 17 followed **no command at all** |

So the aGate both **falls back** when a transport fails and **returns** to the better one
when it recovers. That is the whole basis for probing remotely.

A valid 4G lifeline is precisely: **an active SIM with reception.** That is the
out-of-the-box default fallback — it comes up on reboot, on crash, and whenever the primary
transport fails. It is also what the official app relies on: it happily runs over cellular
while letting you pick an available WiFi SSID or a connected Ethernet port.

### 1.1 The one thing that breaks the invariant

The lifeline fails only if **4G itself is disabled or deregistered**. Concretely:

- `4GNetSwitch` set to `0` — the aGate stops considering cellular at all.
- SIM inactive or removed — `simCardStatus` leaves `2 (Active)`.
- No coverage — `operatorRSSI` drops to 0.

The pre-run checklist in §3 gates on all three.

`4GNetSwitch` is written by **cmdType 341**, whose write shape has *never been observed on
the wire* and is inferred by analogy. **That is the single command capable of severing the
recovery path, and it is the single command whose payload we are least sure about.**

> ⛔ **Do not run any 341 write while off site.** No exceptions. Not even the no-op.
> A no-op validates that the firmware *accepts* the shape; it cannot prove the firmware
> parses it the way we assume. If it misparses and zeroes `4GNetSwitch`, the lifeline is
> gone and recovery is physical.

### 1.2 Residual risk, stated honestly

- The fallback behaviour is **empirical, not documented by the vendor**. Four independent
  observations support it; none of them is a guarantee.
- The `reason` field on a write ack has never been seen non-zero, so there is no known
  error taxonomy. A failure looks like silence, not a message.
- Cellular data plan status is not visible through this API. `operatorRSSI > 0` proves the
  modem is registered, not that data will pass.

---

## 2. What the probe can actually do today

This bounds the blast radius, and it is smaller than the design document's eventual surface:

| Subcommand | Writes? | What it writes |
|---|---|---|
| `status`, `scan`, `observe`, `recover` | no | — |
| `noop 317` | yes | cmdType 317 with **the exact commSetPara it just read**, `currentNetType` unchanged |
| `noop 341` | yes | cmdType 341 with **the exact switches it just read**, all values unchanged |
| `reapply-wifi` | yes | cmdType 337 with **the SSID and password already stored** on the aGate |

**No subcommand can set a network value to something new.** There is no `set-primary`, no
`set-iface`, no "join a different SSID". Those are deliberately unimplemented — they belong
to Phase 2 and to an on-site session.

Every write additionally requires `--i-understand-writes` and passes the preflight
(§3), which refuses unless a transport other than the target could take over.

---

## 3. Pre-run checklist — run before every probe

```bash
python tools/network_probe.py \
  --config ~/dev/franklinwh-cloud-test/franklinwh.ini \
  --lan-host <agate_lan_ip> \
  status
```

Do not proceed unless **all** of these hold:

- [ ] `available_transports` contains `4g`
- [ ] the `4g` interface shows `enabled: true`, `sim_status_name: "Active"`, and a non-zero
      `signal_raw` — **an active SIM plus reception is what makes 4G a valid lifeline**
- [ ] `redundant: true`
- [ ] `active` is **not** `4g` — if the aGate is already on cellular, a WiFi write has
      nothing to prove and you are spending the lifeline as the live transport
- [ ] you can reach the aGate on the LAN, or you accept losing that check

Baseline observed 2026-08-09 (a passing example):

```
active              : WiFi
linked_transports   : ['wifi']
available_transports: ['wifi', '4g']
redundant           : True
   eth0  enabled=True  link=False ip=None            available=False
   eth1  enabled=True  link=False ip=None            available=False
   wifi  enabled=True  link=True  ip=192.168.0.110   available=True  sig=84
   4g    enabled=True  link=False ip=None            available=True  sig=23 sim=Active
```

### 3.1 What "available" means, per transport

The two families fail differently, so they are judged differently:

| Transport | Available when | Why |
|---|---|---|
| **4G** | `4GNetSwitch=1` **and** SIM Active **and** `operatorRSSI > 0` | It is the out-of-the-box fallback and holds **no IP while idle** — cmdType 317 exposes no address for `operator` at all. An active SIM with reception is the whole test. |
| **WiFi / Ethernet** | switch on **and** linked **and** holding an address (static or DHCP) | These must be genuinely *connected and active*. Signal or a plugged cable is not enough. |

That WiFi rule is not pedantry — it is the exact failure mode seen twice. On 2026-03-21 and
again on 2026-08-08 the aGate sat associated at ~76% holding `0.0.0.0`, with no working path
through it. **WiFi with signal but no lease is a candidate to switch *to*; it is never a
fallback to rely *on*.** Candidates come from `scan_wifi_networks_ranked()`; fallbacks come
from `available_transports`.

Ethernet showing `available=False` above is correct — both ports are enabled but have no
link and no address, so neither is a credible fallback.

> If the SIM lookup itself fails (it is a REST call to `getHomeGatewayList`, not a cmdType),
> `sim_status` comes back `null` and 4G availability falls back to reception alone. That is
> deliberate: a transient REST failure must not falsely declare the lifeline dead and block
> a write that is in fact safe.

---

## 4. Probe schedule

### Remote-safe

#### U2 — re-apply stored WiFi credentials · **LOW RISK · run first**

Writes cmdType 337 with the SSID and password the aGate already holds.

*Why it is safe:* this is byte-for-byte what the mobile app did at capture entry 3160, and
it succeeded. Worst case is a WiFi reassociation glitch, which drops WiFi — and the aGate
then falls back to 4G, exactly per §1.

```bash
python tools/network_probe.py --config <ini> --lan-host <ip> \
  --i-understand-writes reapply-wifi
```

Answers: does a 337 write take effect, and what is the real timing envelope from ack to
re-association? Both are needed to size the Phase 2 verify loop.

Expect: `result:0` ack, then WiFi back with a lease within ~15–40s. A brief
`GatewayOfflineException` during reassociation is **normal**, not failure.

---

#### U4a — cmdType 317 no-op shape validation · **LOW RISK**

Writes back the identical 20-key `commSetPara`, `currentNetType` unchanged.

*Why it is safe:* the app itself issued exactly this write twice (capture entries 3145 and
3151), both times with the transport unchanged, and nothing happened. It cannot select a
different transport because it writes back the value it read.

```bash
python tools/network_probe.py --config <ini> --lan-host <ip> \
  --i-understand-writes noop 317
```

Answers: is the `num`-computed payload accepted, and does the state genuinely not move?

**U4b — forcing a *changed* `currentNetType` is NOT in this plan.** It is unimplemented, and
§2.3a of the design doc suggests the field is advisory anyway. Defer to an on-site session.

---

### On-site only — do not run remotely

#### U3 — cmdType 341 write shape · **HIGH RISK · ONSITE ONLY**

The only command that can write `4GNetSwitch`. Shape never observed. See §1.1.

Run it standing next to the aGate, with the AP-mode recovery path confirmed working first.

#### U5 — open network with an empty password · **ONSITE ONLY**

Needs a throwaway open AP in radio range, so it cannot be done remotely regardless of risk.
Not implemented in the probe.

---

## 5. If it goes pear-shaped

Work down this ladder. Stop at the first step that restores control.

**Step 0 — wait 5 minutes.** Most "failures" are the transition blackout. The aGate re-homes
its MQTT session after the interface settles; the 2026-08-08 run saw it unreachable for
several minutes mid-move and come back on its own.

**Step 1 — is it actually down, or just the cloud path?**

```bash
python tools/network_probe.py --config <ini> --lan-host <ip> status
```

The command degrades on purpose: if the cloud call fails it falls back to a LAN check on
Modbus TCP 502 and exits 4. `LAN reachable` means the aGate is alive and only its cloud
link is affected.

**Step 2 — wait for the 4G fallback.** This is the invariant doing its job. Poll every few
minutes:

```bash
python tools/network_probe.py --config <ini> observe --minutes 30 --interval 60
```

`observe` survives transient CloudFront 5xx failures and logs every poll, so it is the right
tool for an unattended watch. Once `active` shows `4g`, control is back.

**Step 3 — once on 4G, fix WiFi remotely.** With cloud control restored, the WiFi config can
be rewritten and the aGate will move back to it by itself. (The write path for a *new* SSID
is Phase 2 and not yet implemented — today this means the vendor app.)

**Step 4 — reboot.** cmdType 315 `{"opt":1,"paraType":1,"reboot":1}`, only if a path still
reaches the device. **Never populate the `reset` field in that payload** — it is almost
certainly a factory reset.

**Step 5 — on-site.** Join the aGate's own AP, which broadcasts even with every uplink down:

```
SSID     : AP_<last 9 of gateway serial>
password : A02<last 9 of gateway serial>     (pattern — confirm via get_wifi_config)
```

`python tools/network_probe.py recover` prints this runbook with the real AP credentials
filled in, and degrades gracefully if it cannot read them.

---

## 6. Abort criteria

Stop probing and wait for an on-site window if any of these occur:

- `available_transports` loses `4g` at any point
- the `4g` interface reports `signal_raw: 0` or `enabled: false`
- the gateway is unreachable for more than **30 consecutive minutes** with the LAN check
  also failing
- any write returns a non-zero `reason` (never yet observed — treat as unknown territory)
- two consecutive probes produce results that contradict each other

---

## 7. Evidence and traceability

Each run writes JSONL to `tests/results/`, capturing every raw request/response with timings.

- Passwords, gateway serials and MAC addresses are **always** scrubbed; SSIDs are scrubbed
  unless `--keep-ssids` is passed.
- Raw `.jsonl` logs are gitignored — they hold live device fingerprints. Commit a sanitised
  summary instead, following `tests/results/2026-08-08_U1-OBSERVE-60MIN_pass.txt`.
- Record the outcome against the U-number in §7.0 of the
  [design doc](NETWORK_CONNECTIVITY_DESIGN.md), which is the single status ledger.

---

## 8. Recommended hardening (not yet implemented)

This plan's central rule — *never target 4G, never run 341 remotely* — currently depends on
whoever is at the keyboard remembering it. That is the weakest part of the setup.

Suggested: a `--require-4g-lifeline` flag that makes the probe refuse to run any write
unless `4g` is in `available_transports` and is not the write target, plus an outright block
on `noop 341` unless a separate `--onsite` flag is passed. Encoding the rule is strictly
safer than documenting it.
