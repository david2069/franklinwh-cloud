# Network Phase 2 — Implementation Plan

> **Status:** APPROVED 2026-08-29 — executing.
> **Authorises:** Phase 2 of [`NETWORK_CONNECTIVITY_DESIGN.md`](NETWORK_CONNECTIVITY_DESIGN.md) §9.
> **Traceability:** AGENT.md directive 4. Every commit in this phase cites a step ID below.
> **Sign-off basis:** `CLAUDE.md` rule 6 — API-affecting writes (`set_wifi_credentials`).
> **AP-1:** one step at a time, full cycle (code → test → verify → commit) per step.

---

## 1. Objective

Restore the aGate to a chosen WiFi SSID from the cloud, without the vendor app.

The field failure this closes: the aGate always falls back to 4G when local connectivity
drops, but does **not** reliably return to WiFi afterwards. It strands itself on cellular.
Documented on live hardware in `docs/troubleshooting/2026-03-21_wifi_dhcp_failure.md`,
where the only available fix was the vendor app's WiFi wizard.

**In scope:** getting the gateway *onto* WiFi (design §3 use case 1).
**Out of scope:** forcing it *off* WiFi (use case 2). The device does that unprompted
(§2.3a, U1). This is why open questions **U3** (`341 opt:1`, shape never captured, can
sever the 4G lifeline) and **U4b** (does `317 optType:1` force a switch, or is it merely
advisory) do **not** block this phase — they only ever served use case 2. No probe work
is on this critical path.

### Why this is safe to build now

`cmdType 337 opt:1` — the entire switch mechanism — is **already proven on this hardware**:
U2, `tests/results/2026-08-09_U2-REAPPLY-WIFI_pass.txt`, write accepted and reassociation
confirmed. Phase 2 is the library wrapper around a validated write, not a new experiment.

---

## 2. Steps

Each step is one commit. Tests green before the next starts (AP-1 verification cycle).

| ID | Step | Files | Risk |
|----|------|-------|------|
| **P2-1** | Cache invalidation on write paths (defects 6 & 7) | `cache.py`, `client.py` | none |
| **P2-2** | `_network_write_preflight()` — the §3 safety gate | `mixins/network.py` | none (read-only) |
| **P2-3** | `set_wifi_credentials()` — 337 read-modify-write | `mixins/network.py` | **API-affecting** |
| **P2-4** | `_verify_wifi_switch()` — the §4 debounced verify loop | `mixins/network.py` | none (read-only) |
| **P2-5** | `switch_to_wifi()` — orchestrator over P2-2/3/4 | `mixins/network.py` | **API-affecting** |
| **P2-6** | `fwh network` CLI subparser | `cli_commands/network.py`, `cli.py` | surface only |
| **P2-7** | Live validation on hardware (AP-13) | `tests/results/` | **live write** |

### P2-1 — Cache invalidation (defects 6, 7)

`MethodCache.invalidate()` and `client.invalidate_cache()` already exist; nothing calls
them on a network write, and there is no read-through bypass. Two changes:

- `set_wifi_credentials()` invalidates `get_wifi_config` and `get_network_info` after a
  successful write (G6 — otherwise the verifier reads 300 s-stale config).
- The verify loop invalidates `get_network_info` **before every poll**. A `use_cache=False`
  kwarg would not work: `_apply_method_cache` hashes kwargs into the cache key, so the flag
  would just create a second cache slot. Invalidate-then-read is the minimal correct fix.
- `get_connectivity_overview` (120 s TTL) is **not** used as a verifier (defect 7).

No signature changes. No TTL changes. Backward compatible.

### P2-2 — Preflight

```python
def _network_write_preflight(state, target, *, min_rssi=30, scan=None, allow_no_fallback=False)
```

Pure function over `get_network_state()` output — unit-testable with no device.

1. `survivors = set(state["available_transports"]) - {target}` → abort if empty.
   Keyed on `available_transports`, **not** `linked_transports` — §3 records this being
   corrected twice by live data, most recently 2026-08-08.
2. Target signal floor: refuse `wifi_RSSI < min_rssi` (default 30). Working links observed
   at 68–100; 8–28 are noise-floor neighbours.
3. `allow_no_fallback=True` overrides gate 1 only, and is not reachable from the CLI
   without an explicit flag.

Returns a `{passed, fallback, target_signal_pct, reasons}` dict → §5.3 `preflight` block.

### P2-3 — `set_wifi_credentials(ssid, password, *, confirm=False)`

Read `337 opt:0` → echo `ap_SSID`/`ap_Pw` back **unchanged** (§2.3b-1: they are the aGate's
own AP identity and are required in the write) → write `337 opt:1`.

- Raises unless `confirm=True`.
- Returns the raw 338 ack, documented as **"accepted", not "connected"** (G7 — a wrong
  password still returns `result:0`).
- Invalidates cache per P2-1.
- Password never logged, never returned, never written to `tests/results/` (pii_policy).

### P2-4 — Verify loop

Implements §4 verbatim. The three properties that must not be simplified away:

- **Debounce ≥ 2 consecutive passing polls.** The aGate roams on its own (G9), and
  reassociation transiently dips 3→4→3 within ~5 s.
- **SSID correlation.** `currentNetType == 3` alone is not proof — correlate `337 opt:0`
  `wifi_SSID` against the requested SSID, plus `wifi.ip ∉ {None, "0.0.0.0"}` (the
  2026-03-21 incident: associated but holding `0.0.0.0`).
- **Swallow `FranklinWHError`** (covers `DeviceTimeoutException`, `GatewayOfflineException`,
  and CloudFront HTML via `InvalidResponseError`). Unreachable polls are *expected*
  mid-cutover (G8, G10) and counted, not fatal.
- **Never auto-retry the write.** On timeout, report and stop.
- Does **not** gate success on `awsStatus`/`netStatus` — §2.5a proved those flags contradict
  observable reality.

### P2-5 — `switch_to_wifi(...)`

Orchestrator: resolve password → preflight → write → verify. Returns §5.3.

`password=None` reuses the stored `wifi_Pw`, permitted **only** when `ssid` matches the
stored `wifi_SSID` — `337 opt:0` returns a plaintext password for the currently-stored
network only, and there is no per-SSID credential lookup anywhere in the captured API.
This is the zero-input path for the primary use case (stranded on 4G, known house WiFi).

### P2-6 — CLI

`fwh network set-wifi` per §6, with `status` and `scan` (see decision D2 below).
`getpass` prompt when no password given; `--password` warns about shell history;
`FWH_WIFI_PASSWORD` accepted. Exit codes: 0 ok · 2 preflight refused · 3 verify timeout ·
4 gateway offline.

Phase 3 commands (`set-primary`, `interface`, `reboot`) are **excluded** — they need U3/U4b.

### P2-7 — Live validation

Per AP-13, on hardware, results to `tests/results/`. Test: gateway on its known WiFi →
`switch_to_wifi(<same ssid>, password=None)` → expect preflight `survivors=['4g']`, write
accepted, verify `connected`. This is a re-apply, which is exactly what U2 already did
safely. Requires your go-ahead at the time of running.

---

## 3. Tests (offline, no hardware)

New `tests/test_network_write.py`:

- preflight: no survivor → refuse; survivor present → pass; RSSI below floor → refuse;
  `allow_no_fallback` override; target-relative survivor set (the 2026-08-07 regression);
  active-but-idle 4G counts as available (the 2026-08-08 regression).
- `set_wifi_credentials`: `ap_SSID`/`ap_Pw` echoed unchanged; refuses without `confirm`;
  cache invalidated; password absent from returned payload and from `repr`.
- verify loop: single passing poll is **not** success; two consecutive are; 3→4→3 dip
  resets the counter; SSID mismatch resets; `0.0.0.0` is not success; unreachable polls
  counted not fatal; timeout returns `state="timeout"` with `last_known`; write never retried.
- `switch_to_wifi`: `password=None` on a non-stored SSID raises; §5.3 shape.

Target ≥ 25 new tests. Syntax check per CLAUDE.md rule 4 before every commit.

---

## 4. Decisions — APPROVED 2026-08-29

**D1 — Where does the new code live?** (AGENT.md directive 1: architecture needs approval.)
Design §4 says a new `mixins/network.py` with the five existing readers *moved* there behind
re-export shims — but §9 marks that split as Phase 1c, "deferred, not required".
**APPROVED:** new `mixins/network.py` containing **only the new write code**; existing
readers stay in `devices.py` untouched. Additive, nothing moves, zero breakage risk, and
the split can happen later as its own change.

**D2 — Ship `fwh network status` / `scan` with `set-wifi`?**
They are Phase 1c, but `set-wifi` needs the `network` subparser regardless, the SDK readers
already exist, and `status --watch` is the natural "did it work" view during a cutover.
**APPROVED:** yes — marginal cost, and it makes the phase usable on its own.

**D3 — Confirm P2-7 live write timing.** Build P2-1..P2-6 and stop for your go-ahead
before touching hardware? **APPROVED:** yes — stop and ask before any hardware write.
