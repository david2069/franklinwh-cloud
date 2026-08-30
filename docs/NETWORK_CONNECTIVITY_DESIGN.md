# aGate Network Connectivity — Read & Switch Design

> **Status:** DESIGN / PLAN ONLY — no code written. Requires user sign-off before Phase 2+
> (API-affecting writes, per `CLAUDE.md` rule 6 and `.agents/policies/change_management.md`).
>
> **Evidence base:** 44 HAR captures in the repo (43 in `hars/`, 1 at root; APP1.9.5 → APP2.9.0),
> decoded `sendMqtt` request/response pairs. Every "CONFIRMED" claim below is backed by an
> observed request *and* its response in a capture. Credentials in captures are redacted here
> per `.agents/policies/pii_policy.md`.
>
> **The existing docs are not sufficient to derive this.** `docs/MQTT_CMD_CATALOG.md` lists only
> the five *read* commands (317/335/337/339/341), all with `{"opt": 0}` payloads, and has no
> write rows. Every write command below exists only as HAR evidence. Closing that gap is
> Phase 4 of this plan.
>
> **Corpus caveat:** `hars/HTTPToolkit_2026-03-20_05-38.har` is a merged superset containing
> duplicated capture segments (e.g. the `Extn` write appears at both entry 7687 and 12667 with
> identical timestamps, and it re-contains material from `HTTPToolkit_2025-10-29_08-28.har`).
> Raw call counts from it are inflated; distinct payloads are not.

---

## 1. Goal

Two deliverables:

1. **Read** — a CLI command + SDK call that answers "what is this aGate connected on
   right now?" (4G / Ethernet 0 / Ethernet 1 / WiFi), with signal, IP and cloud reachability.
2. **Switch** — the command/sequence to move the aGate onto a different transport,
   with the primary use case being **4G → WiFi**: scan, rank by signal, supply or reuse a
   password, apply, then verify the primary connection actually changed.

Both must expose a stable JSON contract so a UI can be built on top without reimplementing
the protocol.

---

## 2. Ground truth — what the wire actually does

All network control rides `POST hes-gateway/terminal/sendMqtt` with the CRC-framed envelope
already implemented in `client.py:723` (`_build_payload`). Request `cmdType` N is answered by
response `cmdType` N+1.

### 2.1 Read commands — all CONFIRMED

| cmd | Request `dataArea` | Response `dataArea` (observed) |
|-----|--------------------|-------------------------------|
| **317** `NETWORK_INTERFACES` | `{"optType":0,"paraType":6}` | `{"optType":0,"paraType":6,"result":0,"commSetPara":{"opt":0,"result":0,"reason":0,"currentNetType":4,"wifiDHCP":1,"wifiMAC":"…","wifiStaticIP":"0.0.0.0","wifiDNS":"8.8.8.8","wifiGateWay":"0.0.0.0","eth0DHCP":0,"eth0MAC":"…","eth0StaticIP":"0.0.0.0","eth0DNS":"8.8.8.8","eth0GateWay":"172.16.1.1","eth1…","operatorMAC":"…","operatorDNS":"…","operatorRSSI":22,"awsStatus":1}}` |
| **335** `WIFI_SCAN` | `{"wifi_ScanTime":0}` or `{"wifi_ScanTime":10}` | pending: `{"result":1,"reason":3}` · done: `{"result":0,"reason":0,"wifi_Info":[{"wifi_SSID":"…","wifi_RSSI":76,"wifi_Safety":1}, …]}` |
| **337** `WIFI_CONFIG` | `{"opt":0}` | `{"opt":0,"result":0,"reason":0,"wifi_SSID":"…","wifi_Pw":"<plaintext>","ap_SSID":"AP_<serial-tail>","ap_Pw":"<plaintext>","wifi_Safety":1}` |
| **339** `CLOUD_CONNECTIVITY` | `{"opt":0}` | short form: `{"opt":0,"result":0,"reason":0,"routerStatus":4,"netStatus":0,"awsStatus":0}` · **extended form (firmware-dependent):** adds `"EthConnectRouterStatus":1,"wifiConnectRouterStatus":0,"4GConnectBSStatus":0,"WifiSignalStrength":0,"4GSignalStrength":45,"currentNetType":2` |
| **341** `NETWORK_SWITCHES` | `{"opt":0}` | `{"opt":0,"result":0,"reason":0,"ethernet0NetSwitch":1,"ethernet1NetSwitch":0,"wifiNetSwitch":1,"4GNetSwitch":1}` |

Also present but out of scope: `317 {"optType":0,"paraType":12}` → `sysConfigPara` (grid/electrical
config, `"num":17`).

### 2.2 Write commands

| cmd | Request `dataArea` | Status | Evidence |
|-----|--------------------|--------|----------|
| **337 opt=1** | `{"opt":1,"wifi_SSID":"<new>","wifi_Pw":"<pw>","ap_SSID":"<echo>","ap_Pw":"<echo>"}` | ✅ **CONFIRMED, and it is the switch mechanism** | `HTTPToolkit_2026-02-09_08-24.har` [3160] and `HTTPToolkit_2025-10-29_08-28.har` [3769]. In the 2026-02-09 capture, this single write flipped `currentNetType` **4 (4G) → 3 (WiFi)** ~13 s later, with `wifiStaticIP` going `0.0.0.0` → `192.168.0.110`. |
| **317 optType=1** | `{"optType":1,"paraType":6,"commSetPara":{…all 20 keys…},"num":20}` | ⚠️ **Accepted (`result:0`) but effect unproven — and probably advisory** | Observed twice, both times writing `currentNetType:4` while *already* on 4. Never observed changing the value. Given §2.3a (the aGate re-selects transport on its own), this is more likely a priority hint than a forced switch. Treat "force primary via 317" as **hypothesis, not fact.** |
| **341 opt=1** | *(inferred)* `{"opt":1,"ethernet0NetSwitch":…,"wifiNetSwitch":…,"4GNetSwitch":…}` | ❌ **Never observed in any of the 44 captures** | Shape inferred by analogy with 311/327/337 read-modify-write. Must be validated live before shipping. Note this is likely the *correct* lever for forcing a transport, since disabling an interface removes it from the aGate's own failover candidate set. |
| **315 opt=1** | `{"opt":1,"paraType":1,"reboot":1}` → 316 `{"paraType":1,"opt":1,"reboot":1,"cleanUnlockAlarm":0,"cleanLockAlarm":0,"cleanAlarmFlag":0,"reset":0,"result":0}` | ✅ CONFIRMED — aGate reboot | Useful as a last-resort recovery step. **`reset` in the same payload is almost certainly factory reset — never populate it.** |

### 2.3 The app's actual sequence (verbatim from capture)

`HTTPToolkit_2026-02-09_08-24.har`, entries 3157–3175 — a real 4G → WiFi switch:

```
09:30:08  335 {"wifi_ScanTime":10}          → {"result":1,"reason":3}      # pending
09:30:20  335 {"wifi_ScanTime":10}          → wifi_Info[12]                # ~12 s later
09:30:46  337 {"opt":0}                     → current SSID + ap_SSID/ap_Pw # read before write
09:30:48  337 {"opt":1, …}                  → {"opt":1,"result":0,"reason":0}
09:30:51  317 {"optType":0,"paraType":6}    → currentNetType:4             # still 4G
09:30:54  339 {"opt":0}                     → routerStatus:4
09:30:56  317 …                             → currentNetType:4
09:31:01  317 …                             → currentNetType:3, wifiStaticIP 192.168.0.110  ← SWITCHED
09:31:11  317 …                             → (null — gateway unreachable)
09:31:16  317 …                             → (null)
09:31:21  317 …                             → currentNetType:3             # back
```

### 2.3a `currentNetType` is observed state, not a setting — the aGate roams on its own

**This is the single most important finding, and it invalidates the naive design.**

Tracing every `currentNetType` change across `hars/HTTPToolkit_2026-03-20_05-38.har`:
**19 transport transitions, of which only 2 followed any write.** The other 17 are the aGate
failing over autonomously, unprompted, sometimes days apart with zero commands in between:

```
3 → 2   2025-12-24 18:20:32      2 → 3   2025-12-25 02:18:52     # WiFi ⇄ Ethernet, no write
3 → 2   2025-12-30 01:44:20      2 → 3   2025-10-02 23:56:18
3 → 2   2025-10-17 19:30:35      2 → 4   2025-10-17 19:35:07     # → cellular, no write
3 → 2   2026-03-20 02:16:49      2 → 4   2026-03-20 02:17:46     4 → 3   2026-03-20 02:18:40
```

Consequences for the design:

- **There is no "primary transport" setting to read back.** `currentNetType` reports which
  transport the aGate is *presently using*, chosen by its own failover logic. A `set-primary`
  command, if 317 `optType:1` works at all, is most likely advisory (a priority hint) rather
  than authoritative.
- **Verification cannot rely on `currentNetType` alone.** A poll that sees `3` after a WiFi
  write may be observing an unrelated autonomous roam. Success must be confirmed by
  correlating **317 `currentNetType == 3` AND 337 `wifi_SSID == <requested>` AND a non-zero
  `wifiStaticIP`**, and must hold across ≥ 2 consecutive polls.
- **Reassociation transiently drops to another transport.** After the `Extn` write:
  `3 → 4` at 18:49:32, back to `3` at 18:49:37 — five seconds apart. A verifier that latches
  on the first reading will report the wrong answer in either direction. Debouncing is mandatory.
- **Use case 2 may need no command at all.** If the aGate already falls back to 4G on its own
  when WiFi is unavailable, "switch back to cellular" is better expressed as *disable the WiFi
  interface via 341* (or simply let it fail over) than as a forced primary set.

### 2.3b Three things to copy exactly from the app:

1. **Read 337 before writing 337.** `ap_SSID` / `ap_Pw` are *required* in the write and must be
   echoed back unchanged — they are the aGate's own AP identity, not the target network.
2. **Poll 317 every 5 s.** That is the app's cadence. Switch landed at ~13 s; full settle ~35 s.
3. **Tolerate a blackout.** Entries 3167/3168/3172/3187 returned no response body at all while
   the aGate re-homed its MQTT session. A verifier that treats one null as failure will
   report a false negative on a successful switch.

### 2.4 Gotchas that will bite an implementation

| # | Gotcha | Consequence |
|---|--------|-------------|
| G1 | `num` in a 317 write = **the key count of the `commSetPara` object** (20 keys → `"num":20`; the paraType-12 `sysConfigPara` has 17 keys → `"num":17`). | Must be computed from the dict, never hardcoded. |
| G2 | **Two incompatible network enums.** `commSetPara.currentNetType` and `NETWORK_TYPES` (`const/devices.py:7`) use `1=Eth0, 2=Eth1, 3=WiFi, 4=4G`. `runtimeData.connType` (`models.py:123`) uses `0=4G, 1=WiFi, 2=Ethernet`. | Mixing them silently mislabels the active transport. Never derive primary from `connType`. |
| G3 | `wifi_RSSI` in the 335 scan is a **0–100 quality percentage**, not dBm (observed 8, 22, 76, 100). `discovery.py:60` annotates `wifi_signal` as dBm. | Existing annotation is wrong; UI sorting/thresholds must use the % scale. |
| G4 | `routerStatus` is **not boolean** — observed 0, 1 and 4. `get_connectivity_overview` (`mixins/devices.py:980`) does `bool(conn_status.get("routerStatus"))`. | `routerStatus:4` reads as "connected"; may be a transport code, not a flag. Semantics unresolved — do not present it as a boolean to a UI. |
| G5 | Scan results contain **duplicate SSIDs** (mesh nodes / 2.4+5 GHz), e.g. `"JJ"` appears 3× at 26/26/28 and `" snab"` 4× at 38/80/98/100. No BSSID, band or channel is returned. | Must dedupe by SSID keeping max RSSI. Cannot target a specific AP or band. |
| G6 | `get_wifi_config` is cached 300 s and `get_network_info` 120 s (`cache.py:47,55`). | Post-write verification will read stale data unless the cache is invalidated on write. |
| G7 | The 338 ack (`result:0`) means **"aGate accepted the config"**, not "aGate associated with the AP". | A wrong password still returns `result:0`. Success can only be established by 317/339 polling. |
| G8 | `_mqtt_send` raises `DeviceTimeoutException` (code 102) and `GatewayOfflineException` (code 136). | Both are *expected, non-fatal* during cut-over and must be swallowed by the verify loop. |
| G9 | The aGate changes transport **autonomously** — 17 of 19 observed transitions followed no command at all (§2.3a). | `currentNetType` is a status field, not a setting. Neither a UI nor a verifier may present it as "the configured primary", and no verification may rest on it alone. |
| G10 | The cloud sits behind **CloudFront**, which serves HTML error pages for 502/503/504. These are not API responses and carry no `code` field. Observed killing a 60-minute poll on its second iteration. | Any long-running loop must survive them. `client._decode_json` raises `InvalidResponseError`, which subclasses `FranklinWHError` — so a single `except FranklinWHError` covers both application-level rejections and CDN failures. |

---

### 2.5 Why there is no setter today

`docs/cli-raw.md` → *Devices & Network* exposes five methods, all getters
(`get_network_info`, `get_wifi_config`, `scan_wifi_networks`, `get_connection_status`,
`get_network_switches`). That is a **gap in this SDK, not in the FranklinWH API.**

The setters exist and are the *same* cmdTypes with the opt flag flipped:

| Read (implemented) | Write (exists on the wire, not implemented here) |
|---|---|
| `317 {"optType":0,"paraType":6}` | `317 {"optType":1,"paraType":6,"commSetPara":{…},"num":N}` |
| `337 {"opt":0}` | `337 {"opt":1,"wifi_SSID","wifi_Pw","ap_SSID","ap_Pw"}` |
| `341 {"opt":0}` | `341 {"opt":1,…}` — inferred, never captured |
| — | `315 {"opt":1,"paraType":1,"reboot":1}` |

So the `opt:0` / `opt:1` read-write convention already used by `_update_smart_circuit_config`
(`mixins/devices.py:285`) and `led_light_settings` (`:235`) applies to the network commands too —
nobody has written the network half yet. Phase 2 is exactly that.

### 2.5a U1 ANSWERED — autonomous roaming confirmed on live hardware (2026-08-08)

Observed directly via `tools/network_probe.py`, with **no commands issued at any point**:

| Time | Active | WiFi | 4G | Note |
|---|---|---|---|---|
| ~08:25 | **4G** | enabled, 76%, `link=false`, `ip=null` | linked | `linked_transports=["4g"]` |
| ~08:59 | — | — | — | cloud returns code 136 *"Current gateway offline"* |
| ~09:07 | **WiFi** | `link=true`, `ip=192.168.0.110` | `link=false` | `linked_transports=["wifi"]` |

The aGate moved itself from cellular to WiFi, acquired a DHCP lease, and dropped the
cellular link — unprompted. This confirms §2.3a on live hardware, and settles U1: **yes,
failover and recovery are autonomous.** Option C in §3 ("do nothing") is therefore viable
and should be tried before any write-based approach to use case 2.

Two further findings from the same window:

- **The offline blip is real and mid-transition.** A probe or verify loop that treats a
  single `GatewayOfflineException` as failure will report false negatives. The blackout
  tolerance in the verify loop is not defensive over-engineering — it is required.
- **The cmdType 339 reachability booleans cannot be trusted.** While the aGate was on WiFi
  with a valid lease and answering MQTT through the cloud, 339 still reported
  `netStatus=0`, `awsStatus=0`, `routerStatus=0`. Since those calls demonstrably round-trip
  through the cloud to the device, the flags contradict observable reality. **Do not gate
  switch success on `awsStatus`/`netStatus`** — use `currentNetType` + a real address +
  SSID correlation, as §4's verify loop already does.

### 2.6 Real-world corroboration

`docs/troubleshooting/2026-03-21_wifi_dhcp_failure.md` documents this happening on live
hardware, and independently confirms three design assumptions:

- WiFi associated with the SSID but held IP `0.0.0.0` (no DHCP lease) — which is why the
  verify loop must check **`wifi.ip not in {None, "0.0.0.0"}`** and not merely "associated".
- The aGate **fell back to 4G by itself**, no command issued — direct field confirmation of
  G9 / §2.3a, and of option C in §3.
- The fix was the mobile app's WiFi Configuration wizard — i.e. exactly the
  `335 scan → 337 opt:1 write → poll` sequence this design reproduces. `switch_to_wifi()`
  would have resolved that incident without touching the app.

That incident is also the strongest argument for shipping Phase 2: the recovery path currently
requires the vendor app.

---

## 3. Feasibility verdict

### Use case 1 — currently on 4G, switch to a scanned WiFi network

**Verdict: FEASIBLE. High confidence.** Every step has a confirmed request/response pair, and
the end-to-end transition is directly observed in a capture.

| Step | Feasible? | Notes |
|------|-----------|-------|
| Detect current transport | ✅ | 317 `currentNetType` — authoritative. |
| Scan for networks | ✅ | 335, async, poll to `result:0`. |
| Sort by signal strength | ✅ | `wifi_RSSI` 0–100, dedupe by SSID (G5). |
| Accept a typed password | ✅ | 337 `opt:1`. |
| **Reuse a password from the cloud API** | ⚠️ **Partial** | 337 `opt:0` returns `wifi_Pw` **in plaintext** — but only for the SSID *currently stored on that aGate*. There is no per-SSID lookup and no credential vault anywhere in the captured API surface. So "use retrieved password" works for **re-apply / reconnect to the already-known network**, not for joining a new one. |
| Verify the switch landed | ✅ | Poll 317 for `currentNetType==3` **and** `wifi.ip ∉ {None, "0.0.0.0"}`, then 339. |

Residual unknowns for this path:

- **Open networks** (`wifi_Safety:0`, e.g. `ENVOY_038186` in the scans) — never written to in any
  capture. Whether `wifi_Pw:""` is accepted is untested.
- **Hidden SSIDs** — won't appear in a scan; a blind write may or may not work. Untested.
- **Wrong-password diagnosis** — no error surfaces. The only signal is "verify loop timed out".
  Cannot distinguish bad password from weak signal from DHCP failure.
- Mesh/band selection is impossible (G5).

### Use case 2 — switch *back* to 4G (or to Ethernet)

**Verdict: FEASIBLE BUT UNPROVEN — and the framing is probably wrong. Do not ship in the same phase.**

§2.3a shows the aGate already moves itself between WiFi, Ethernet and 4G without being asked.
So "switch to 4G" is likely not a command you send, but a *candidate set* you constrain:

- **B (preferred) — 341 `opt:1` with `wifiNetSwitch:0`**, removing WiFi from the aGate's own
  failover candidates and letting it settle on cellular. Consistent with the observed autonomous
  behaviour. Write shape never captured, so unproven.
- **A — 317 `optType:1` with a changed `currentNetType`.** Payload confirmed and accepted, but
  only ever observed as a no-op, and §2.3a suggests any value written would be overridden by the
  aGate's own selection within minutes. Plausibly advisory only.
- **C — do nothing.** If WiFi credentials are cleared or the AP goes away, failover to 4G appears
  to be automatic. This is worth testing first because it costs no writes and carries no risk.

Test C before building A or B.

### The safety problem, and the preflight that solves it

If a WiFi write is applied with a bad password **and** 4G is disabled **and** no Ethernet link
is up, the aGate goes dark. Recovery is then physical (AP mode / on-site), because the cloud
path you'd use to fix it is the path you just broke.

**Mandatory preflight before *any* network write** — abort unless a transport *other than
the one being modified* is live:

```python
state = await client.get_network_state()
survivors = set(state["available_transports"]) - {target_interface}
if not survivors:
    abort("no fallback transport would survive this write")
```

> **Corrected twice, both times by live data.**
>
> *2026-08-07* — the first draft excluded the *active* transport from the fallback set.
> Wrong: the gateway was on 4G with WiFi enabled but holding no lease, so excluding the
> active transport yielded "no fallback" and would have refused the primary use case, even
> though 4G was about to carry the connection through the WiFi rewrite. **The fallback set
> is relative to the target of the write, not to the active transport.**
>
> *2026-08-08* — the second draft keyed on `linked_transports`. Also wrong. The 60-minute
> observation (§2.5a) showed the aGate **parks the transports it is not using**: for a full
> hour it sat on WiFi with `4GNetSwitch=1` and `operatorRSSI=21-22` but `4GConnectBSStatus=0`.
> Cellular was idle, not dead — it had carried the connection that same morning. Since at
> most one transport is ever linked, subtracting the target from `linked_transports` refuses
> **every** write to whichever transport is currently carrying traffic.
>
> `get_network_state()` therefore returns both, and the preflight uses `available`:
>
> - `linked_transports` — carrying traffic right now (factual, at most one entry)
> - `available_transports` — would actually carry traffic if the one in use stopped.
>   This is the write-safety set, and the two transport families are judged differently:
>   **4G needs an active SIM plus reception** (it is the by-design fallback and holds no IP
>   while idle — 317 exposes no address for `operator`), while **WiFi and Ethernet must be
>   connected and holding an address**, static or DHCP.
>
> The WiFi rule earns its strictness: on 2026-03-21 and again on 2026-08-08 the aGate sat
> associated at ~76% holding `0.0.0.0`. Signal alone is a candidate to switch *to* — that
> is what `scan_wifi_networks_ranked()` is for — never a fallback to rely *on*.

Applied to the two use cases against live state on 2026-08-08 (active WiFi, cellular idle):

| Write target | `available_transports - {target}` | Verdict |
|---|---|---|
| WiFi (use case 1) | `{"4g"}` | proceed — idle cellular is ready to take over |
| 4G (use case 2) | `{"wifi"}` | proceed — WiFi is carrying traffic |

Ethernet correctly stays out of the set: both ports are enabled but have no link and no
address, so neither is a credible fallback.

Plus a minimum signal floor on the target: **refuse `wifi_RSSI < 30`** (captures show working
links at 68–100; 8–28 are noise-floor neighbours). Overridable only with an explicit flag.

---

## 4. SDK surface

New module **`franklinwh_cloud/mixins/network.py`** — `devices.py` is already 1,240 lines and
holds ~35 unrelated methods. Move the five existing network readers there behind
re-export shims in `DevicesMixin` so nothing downstream breaks (per `docs/BACKWARD_COMPATIBILITY.md`).

### Read

```python
async def get_network_state(self) -> dict
```
The single "what am I on" call. Composes 317 + 339 + 341 (3 sendMqtt) and returns §5.1.
Uses the extended-339 fields when the firmware provides them, falls back to 317 otherwise.

```python
async def scan_wifi_networks_ranked(
    self, *, scan_time: int = 10, min_rssi: int = 0,
    dedupe: bool = True, max_attempts: int = 6, delay_s: float = 5.0,
) -> list[dict]
```
Wraps 335. Deduped by SSID (max RSSI wins), sorted RSSI desc, `secured` derived from
`wifi_Safety`, `is_current` flagged against 337. Defaults raised from the existing
`scan_wifi_networks_poll` (3 × 2.0 s = 6 s) — the capture shows scans completing at ~12 s,
so the current defaults will usually time out.

### Write — all gated behind `confirm=True` and the §3 preflight

```python
async def set_wifi_credentials(self, ssid: str, password: str, *, confirm: bool = False) -> dict
```
Read-modify-write on 337: read `opt:0` → echo `ap_SSID`/`ap_Pw` → write `opt:1`. Invalidates
the `get_wifi_config` / `get_network_info` cache entries. Returns the raw 338 ack —
**explicitly documented as "accepted", not "connected"** (G7).

```python
async def switch_to_wifi(
    self, ssid: str, password: str | None = None, *,
    confirm: bool = False, verify: bool = True,
    timeout_s: int = 180, poll_interval_s: float = 5.0,
    min_rssi: int = 30, allow_no_fallback: bool = False,
) -> dict
```
The orchestrator. `password=None` → reuse the stored `wifi_Pw`, permitted **only** when
`ssid` equals the stored `wifi_SSID` (the cloud has no other credential source).

```python
async def set_primary_network(self, net_type: int | str, *, confirm: bool = False) -> dict   # EXPERIMENTAL
async def set_network_interface(self, iface: str, enabled: bool, *, confirm: bool = False) -> dict  # EXPERIMENTAL
async def reboot_agate(self, *, confirm: bool = False) -> dict                                # 315, recovery only
```

`set_primary_network` = read 317 `paraType:6` → mutate `currentNetType` → write with computed
`num` (G1). `set_network_interface` = read 341 → mutate one switch → write `opt:1`.
Both raise `NotImplementedError` unless an explicit opt-in flag is set, until live-validated.

Add to `MqttCmd` (`models.py:10`): `SYSTEM_CONTROL = 315`. Consider a parallel
`MqttResponse` enum (316/318/336/338/340/342) for response-type assertion.

### The verify loop (the part that has to be right)

```
deadline = now + timeout_s
unreachable = 0
stable = 0                                      # consecutive polls meeting ALL criteria
while now < deadline:
    sleep(poll_interval_s)                      # 5 s — matches the app
    try:
        net = 317 optType=0 paraType=6          # cache bypassed
    except (DeviceTimeoutException, GatewayOfflineException, FranklinWHError):
        unreachable += 1; stable = 0            # EXPECTED during cut-over — not a failure
        continue

    on_wifi = net.currentNetType == 3 and net.wifi.ip not in (None, "0.0.0.0")
    if not on_wifi:
        stable = 0; continue                    # incl. the transient 3→4→3 dip (§2.3a)

    # currentNetType alone is not proof — the aGate roams unprompted (§2.3a).
    # Correlate the SSID actually in use before declaring success.
    if 337(opt=0).wifi_SSID != requested_ssid:
        stable = 0; continue                    # roamed for unrelated reasons

    stable += 1
    if stable >= 2:                             # debounce — two consecutive confirmations
        conn = 339 opt=0                        # best-effort cloud confirmation
        return {"state": "connected", ...}

return {"state": "timeout", "last_known": …, "unreachable_polls": unreachable}
```

Cost note: the SSID correlation adds a 337 read per candidate poll. Only issue it once
`on_wifi` is already true, so a typical successful switch costs ~4 extra `sendMqtt` calls
against the 5,000/day budget tracked in `cache.py`.

Never auto-retry the 337 write on timeout. Report and stop — a retry loop against an aGate
that is mid-reassociation is how you turn a slow switch into a dead gateway.

State machine the UI binds to:

```
idle → scanning → applying → transitioning → verifying → connected
                                    ↓                        ↓
                              (unreachable, expected)      timeout
```

---

## 5. JSON contracts (UI-facing, frozen at Phase 4)

### 5.1 `GET` network state — `fwh network status --json`

```json
{
  "gateway_id": "<agate_serial>",
  "timestamp": "2026-08-06T09:31:01Z",
  "primary": {
    "type_id": 3, "type": "wifi", "label": "WiFi",
    "ip": "192.168.0.110", "gateway": "192.168.0.1", "dns": "8.8.8.8",
    "dhcp": true, "mac": "4C:24:CE:67:3A:7C",
    "signal_pct": 82, "signal_scale": "percent"
  },
  "interfaces": [
    {"id": 1, "key": "eth0", "label": "Ethernet 1", "enabled": true,  "link": true,  "ip": "172.16.1.50", "dhcp": false, "is_primary": false},
    {"id": 2, "key": "eth1", "label": "Ethernet 2", "enabled": false, "link": false, "ip": null,          "dhcp": true,  "is_primary": false},
    {"id": 3, "key": "wifi", "label": "WiFi",       "enabled": true,  "link": true,  "ip": "192.168.0.110","dhcp": true, "is_primary": true,  "ssid": "<ssid>", "signal_pct": 82},
    {"id": 4, "key": "4g",   "label": "4G Mobile",  "enabled": true,  "link": true,  "ip": null,          "dhcp": null,  "is_primary": false, "signal_pct": 45}
  ],
  "cloud": {"aws_connected": true, "internet": true, "router_status_raw": 4},
  "fallback_available": true,
  "source": {"cmds": [317, 339, 341], "extended_339": true}
}
```

`fallback_available` is the field a UI must check before enabling the "Switch" button.
`router_status_raw` is passed through unmapped and unstyled until G4 is resolved.

The key is named `primary`, but per G9 it is the transport the aGate is **currently using**, not
one it was configured to use — the aGate re-selects on its own. UI copy must say *"Active
connection"*, never *"Configured primary"*, and should not imply the user chose it. Same reason
the object carries `"selection": "device-managed"` rather than a user-set flag.

### 5.2 `GET` scan — `fwh network scan --json`

```json
{
  "scanned_at": "2026-08-06T09:30:20Z",
  "scan_seconds": 10,
  "current_ssid": "<ssid>",
  "networks": [
    {"ssid": "<ssid-a>", "signal_pct": 100, "signal_bars": 4, "secured": true,  "is_current": true,  "seen_count": 4, "usable": true},
    {"ssid": "<ssid-b>", "signal_pct": 76,  "signal_bars": 3, "secured": true,  "is_current": false, "seen_count": 1, "usable": true},
    {"ssid": "<ssid-c>", "signal_pct": 22,  "signal_bars": 1, "secured": false, "is_current": false, "seen_count": 1, "usable": false}
  ],
  "warnings": ["3 duplicate SSIDs collapsed (mesh or dual-band)"]
}
```

`signal_bars` = `pct` bucketed 0–25/26–50/51–75/76–100. `usable` = `signal_pct >= 30`.
Open networks (`secured:false`) are returned but flagged unsupported until tested.

### 5.3 `POST` switch — `fwh network set-wifi --json`

```json
{
  "requested": {"ssid": "<ssid>", "password_source": "user|stored"},
  "preflight": {"passed": true, "fallback": "4g", "target_signal_pct": 82},
  "write_ack": {"cmd": 338, "result": 0, "reason": 0},
  "verification": {
    "state": "connected",
    "elapsed_s": 13.4,
    "polls": 3,
    "unreachable_polls": 0,
    "before": {"type_id": 4, "type": "4g",   "ip": null},
    "after":  {"type_id": 3, "type": "wifi", "ip": "192.168.0.110"}
  }
}
```

`verification.state ∈ {connected, timeout, skipped}`. On `timeout` the payload carries
`last_known` plus a `recovery_hint` string; exit code 3.

---

## 6. CLI design

New `franklinwh_cloud/cli_commands/network.py`, registered as a `network` (alias `net`)
subparser in `cli.py` alongside the existing 14 subcommands.

```
fwh network status  [--json] [--watch [SECS]]
fwh network scan    [--json] [--min-rssi N] [--all] [--scan-time 10]
fwh network set-wifi --ssid SSID [--password PW | --use-stored]
                     [--yes] [--no-verify] [--timeout 180] [--min-rssi 30]
                     [--allow-no-fallback] [--json]
fwh network set-primary {eth0|eth1|wifi|4g} [--yes]          # EXPERIMENTAL
fwh network interface {eth0|eth1|wifi|4g} {enable|disable} [--yes]   # EXPERIMENTAL
fwh network reboot [--yes]                                    # cmd 315, recovery
```

Behaviour notes:

- `set-wifi` with no `--password` and no `--use-stored` → **interactive prompt via `getpass`**;
  never echoed, never logged, never written to `tests/results/`.
- `--password` on the command line emits a warning about shell history. Also accept
  `FWH_WIFI_PASSWORD` from the environment.
- All write subcommands print the preflight result and require `y/N` confirmation unless
  `--yes`. `set-primary` / `interface` additionally require `FWH_EXPERIMENTAL=1` until live-validated.
- `--watch` on `status` is the natural "did it work" view during a switch, and must render
  unreachable polls as `⟳ transitioning` rather than an error.
- Exit codes: `0` success · `2` preflight refused · `3` verify timeout · `4` gateway offline.
- `support --scope network` gains the new state block; `diag` (which already calls
  `get_network_info` at `cli_commands/diag.py:333` and `get_connectivity_overview` at `:379`)
  switches to `get_network_state()`.

Terminal output sketch for `status`:

```
aGate Network — <agate_serial>

  PRIMARY   WiFi                    192.168.0.110/24  gw 192.168.0.1   ▂▄▆█  82%
  Cloud     ✓ AWS connected    ✓ Internet

  eth0      enabled   link up     172.16.1.50   (static)
  eth1      disabled  —
  wifi      enabled   link up     192.168.0.110  SSID <ssid>      82%   ← primary
  4G        enabled   registered  —                                45%

  Fallback available: 4G ✓
```

---

## 7. Test plan

Per `.agents/policies/live_test_protocol.md` (AP-13). Results to `tests/results/`.

> **Running these:** see [Network Probe Test Plan](NETWORK_PROBE_TEST_PLAN.md) for the
> remote-safe runbook — ordering, pre-run checklist, abort criteria and the recovery ladder.
> The short version: the 4G lifeline is the safety invariant, and **cmdType 341 is the only
> command that can sever it, so it is never run off site.**

### 7.0 Open questions and their status

These are the device-behaviour unknowns that no amount of HAR analysis can settle.
`tools/network_probe.py` exists to answer them and is retired once they are all closed.

| #  | Question | Risk | Probe command | Status |
|----|----------|------|---------------|--------|
| U1 | Does the aGate fail over between transports on its own? | none | `observe` | ✅ **ANSWERED YES** — §2.5a, observed 4G → WiFi unprompted 2026-08-08 |
| U2 ✅ | Does re-applying identical WiFi credentials work? Timing envelope? | low | `reapply-wifi` | ✅ **ANSWERED YES** — see §7.0a, run 2026-08-09 |
| U3 | Does `341 opt=1` exist, and is the inferred shape correct? | **high** | `noop 341` | open — no-op probe first; a wrong shape could disable an interface |
| U4a ✅ | Is the `317 optType=1` payload shape accepted (num, key stripping)? | low | `noop 317` | ✅ **ANSWERED YES** — see §7.0b, run 2026-08-09 |
| U4b | Does `317 optType=1` force a transport *switch*, or is it advisory? | medium | not implemented | open — needs a **changed** `currentNetType`. §2.3a makes "advisory" the leading hypothesis |
| U5 | Does an open network (`wifi_Safety 0`) accept an empty password? | medium | — | open — needs a throwaway AP; not yet implemented in the probe |

### 7.0a U2 ANSWERED — cmdType 337 write verified live (2026-08-09)

`tools/network_probe.py reapply-wifi`, writing back the credentials already stored.
Preflight passed with `survivors=['4g']` and the lifeline intact.

| t+ | Event |
|---|---|
| 5 s | `337 opt=1` accepted — `result:0 reason:0`, **1.2 s** round trip |
| 15 s | still on WiFi with its lease — no disruption yet |
| 40 s | `wifiStaticIP` = `0.0.0.0` — lease dropped, reassociating |
| 49 s | lease restored, `192.168.0.110` |
| 85 s | 3 × CloudFront 504 (unrelated infrastructure blip) |
| 115 s | confirmed on two consecutive polls |

**The write works.** Ack in ~1.2 s, reassociation complete inside ~45 s.

Four findings that change Phase 2:

1. **`currentNetType` never left 3.** Re-applying credentials for the SSID already in use
   re-associates *without* changing transport — no 4G fallback occurred. That differs from
   capture [3160], where the same command moved the gateway 4G → WiFi, because there the
   target was a network it was not already on.
2. **The debounce prevented a false positive.** Poll 1 at t+15 s matched — WiFi active with
   a valid address — *before the reassociation had even begun*. A verifier latching on the
   first match would have declared success 25 s before the lease actually dropped.
   Requiring two consecutive matches is not belt-and-braces; it is load-bearing.
3. **The blackout is a lost DHCP lease, not a lost gateway.** `currentNetType` stayed 3 and
   the aGate stayed reachable throughout; only `wifiStaticIP` went to `0.0.0.0`. So the
   verify predicate must test the address, not just the transport — checking
   `currentNetType == 3` alone would never have noticed anything happened.
4. **A 5 s poll interval is not achievable via `get_network_state()`.** Each call makes
   three MQTT reads plus a REST lookup and took 15–25 s in this run, so the effective
   cadence was ~30 s. Phase 2's verify loop should poll **cmdType 317 alone** (~3–10 s) and
   only compose the full state once, at the end.

Also confirmed in passing: the `InvalidResponseError` fix earned itself. Three CloudFront
504s landed mid-verify at t+85 s and were absorbed as one unreachable poll. Before that fix
they raised a bare `JSONDecodeError`, which would have aborted the run and reported failure
on a successful operation.

### 7.0b U4a ANSWERED — cmdType 317 write shape validated (2026-08-09)

`tools/network_probe.py noop 317` — read the current `commSetPara`, wrote back exactly what
was read, re-read and diffed. Preflight passed with `survivors=['4g']`, lifeline intact.

```
request : optType=1  paraType=6  num=20  keys=20   currentNetType=3
response: result=0   commSetPara.result=0  reason=0  opt=1  currentNetType=3
re-read : changed={}          # nothing moved
```

Total 20 s; the write itself took 2.6 s.

- **The payload construction is correct.** 20 keys and `num=20` reproduces the app's own
  captured write byte-for-byte in structure, confirming both the computed `num` (G1) and the
  stripping of the response-only `opt`/`result`/`reason` keys.
- **A no-op really is a no-op.** The post-write diff was empty and connectivity was
  untouched, which is what makes this safe to run remotely.

**What this does NOT answer.** U4a validates that the firmware *accepts* the shape. It says
nothing about whether a **changed** `currentNetType` would actually move the gateway — we
wrote back the value already in force. That is U4b, it needs a write with a different value,
and it is deliberately unimplemented. §2.3a still makes "advisory hint, overridden by the
aGate's own selection" the leading hypothesis, and the U1/U2 evidence strengthens it: the
gateway re-selects transport on its own and did so unprompted during this session.

**Do not run U3/U4b while `available_transports` has only one entry.** The preflight enforces
this. As of 2026-08-08 the gateway reports `available_transports == ["wifi", "4g"]`
(`redundant: true`), so U2 and U3/U4 are unblocked — WiFi carries traffic and idle cellular
is ready to take over.

U3 remains the one to run with physical access to the aGate: if the inferred `341 opt=1`
shape is wrong it could disable an interface, and the no-op probe validates the shape but
cannot prove the firmware interprets a *changed* value as intended.

**Gate 1 — unit (mocked, no network).** Fixtures extracted from the HAR corpus into
`tests/fixtures/network/`: both 340 shapes (short + extended), 318 both `result`-nesting
variants already handled at `mixins/devices.py:668`, 336 pending + complete, 338 read + write
ack, 342. Cases: `num` computation (G1); enum separation (G2); dedupe + sort + bars (G5);
verify-loop tolerance of `None` / 102 / 136 / malformed (G8) — assert the loop survives 3
consecutive unreachable polls and still reports `connected`; preflight refusal when no
fallback; `--use-stored` rejected for a non-matching SSID; cache invalidation after write (G6).

**Gate 2 — emulator.** Extend `emulator/` to serve 317/335/337/339/341 and model the
transition: accept the 337 write, hold `currentNetType:4` for 2 polls, return null for 2 polls,
then flip to `3` with a DHCP address. Drives the whole state machine with zero live risk.
Add a bad-password variant that never flips, to exercise the timeout path. Add two more
variants driven by §2.3a: (a) an **autonomous roam** to `currentNetType:3` with the *old* SSID
still in 337 — the verifier must NOT report success; (b) a **transient dip** `3→4→3` mid-verify —
the debounce must ride through it. Also model the DHCP-failure case from
`docs/troubleshooting/2026-03-21_wifi_dhcp_failure.md`: `currentNetType:3`, correct SSID,
but `wifiStaticIP` stuck at `0.0.0.0` — must time out, not succeed.

**Gate 3 — live, staged, each with explicit user sign-off:**

| Stage | Action | Risk |
|-------|--------|------|
| L1 | `network status`, `network scan` — read-only | None |
| L2 | `set-wifi --use-stored` — re-apply *identical* credentials | Low. Exactly what the app did at capture [3160]; observed to succeed. |
| L3 | Real 4G → WiFi change | Medium. Only with 4G fallback verified enabled and target RSSI ≥ 30. Attended. |
| L4 | `set-primary`, `interface` | **High — unproven writes.** Attended, physical access to the aGate available, never unattended, never in a `/loop`. |

---

## 8. Defects found while surveying (queue under AP-1, do not fix ad-hoc)

1. **`get_connection_status()`** (`mixins/devices.py:800`) — docstring claims 3 keys; firmware
   returns 6 more (`EthConnectRouterStatus`, `wifiConnectRouterStatus`, `4GConnectBSStatus`,
   `WifiSignalStrength`, `4GSignalStrength`, `currentNetType`). Silently discarded downstream.
2. **`bool(routerStatus)`** (`mixins/devices.py:980`) — field takes 0/1/4; boolean coercion is
   unsound (G4).
3. **`discovery.py:60`** — `wifi_signal` annotated `# dBm`; the wire value is 0–100 % (G3).
4. **`scan_wifi_networks_poll` defaults** (`mixins/devices.py:766`) — 3 attempts × 2.0 s = 6 s
   ceiling; observed scans complete at ~12 s. Will report failure on healthy hardware.
5. **`MqttCmd`** (`models.py:10`) — missing 315; response cmdTypes undocumented.
6. **Cache TTLs** (`cache.py:47,55`) — no invalidation hook, so any write path reads stale state (G6).
7. **`get_connectivity_overview`** — cached 120 s and unusable as a post-write verifier.

Items 1–5 are read-side and land in Phase 1. 6–7 are prerequisites for Phase 2.

---

## 9. Phasing and sign-off

| Phase | Scope | Sign-off |
|-------|-------|----------|
| **1a** ✅ | `get_network_state()` + `scan_wifi_networks_ranked()` + defects 1–5. **Read-only.** Shipped `feat/network-readers` (b6308fe); 18 new tests; verified live. | Done |
| **1b** ✅ | Remediation: live tests made opt-in (0475f40), `FranklinWHError` defined (737e058), fictional scan fixtures corrected (bcf9421). | Done |
| **1c** ◐ | `mixins/network.py` module split + `fwh network status\|scan` CLI. The CLI shipped with Phase 2 (decision D2); the **module split remains deferred** — `network.py` holds only the write path and the five readers stay in `devices.py` (decision D1). | Not required |
| **2** ✅ | `set_wifi_credentials()` + `switch_to_wifi()` + preflight + verify loop + `fwh network status\|scan\|set-wifi` + defects 6–7. Offline work complete and unit-tested (92 tests); **live validation P2-7 parked 2026-08-30** — site access required, see the plan's section 5. See [Phase 2 plan](NETWORK_PHASE2_IMPLEMENTATION_PLAN.md). | Approved 2026-08-29 |
| **3** | `set_primary_network()` / `set_network_interface()` / `reboot_agate()`, behind `FWH_EXPERIMENTAL`. | **Required** + L4 live validation first |
| **4** | Freeze §5 contracts; add write rows to `MQTT_CMD_CATALOG.md` (currently read-only, §2.5); add the setters to `docs/cli-raw.md` *Devices & Network*; update `docs/franklinwh_openapi.json` and `API_REFERENCE.md`. | Not required |

Phase 1 is independently useful and carries no risk to the gateway. Phase 2 is where the
value is and where the danger is; it should not start until the preflight and verify-loop
unit tests from Gate 1 are green.
