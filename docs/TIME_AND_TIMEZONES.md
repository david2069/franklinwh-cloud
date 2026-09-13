# Time and Time Zones

> **Who this is for:** anyone scheduling against a gateway that is not in their
> own time zone, or coordinating several gateways across zones. If your
> operator, your automation host and your hardware are all in one zone, most of
> this reduces to "it just works" — but the traps below still apply across a DST
> boundary.

Evidence tiers per [AP-14](../.agents/policies/evidence_standard.md). Counts are
from the HAR corpus (2025-02 → 2026-03).

---

## The short answer

**One call gives you the gateway's own clock and zone together:**

```python
info = await client.get_device_info()        # GET getDeviceInfoV2
result = info["result"]
result["deviceTime"]   # "2025-08-07 22:05:06"   — gateway LOCAL wall clock
result["zoneInfo"]     # "Australia/Sydney"      — IANA zone name
```

**CONFIRMED:** both fields present at `result` level in **2,485 of 2,505**
captured `getDeviceInfoV2` responses (99.2%). `get_home_gateway_list()` carries
the same pair (163 samples), which is where `discover()` reads them.

---

## Three clocks, and which one wins

| Clock | Where it comes from | Authoritative for |
|---|---|---|
| **Gateway local** | `deviceTime`, `zoneInfo` | **Everything the gateway does.** TOU windows, schedules, the day boundary for daily energy totals |
| **Client local** | your machine | Nothing on the device. Only CLI header timestamps |
| **Epoch / absolute** | `timestamp`, `activeTime`, `installTime`, `createTime` | Ordering events, comparing across gateways |

**The gateway acts on its own clock, not yours.** A TOU block written as `16:00`
starts at 16:00 *where the gateway is*.

---

## Field inventory

| Field | Endpoint | Example | Tier |
|---|---|---|---|
| `deviceTime` | `getDeviceInfoV2`, `getHomeGatewayList` | `"2025-08-07 22:05:06"` | CONFIRMED (2,808 samples) |
| `zoneInfo` | `getDeviceInfoV2`, `getGatewayTouListV2`, `getHomeGatewayList` | `"Australia/Sydney"` | CONFIRMED (4,087) |
| `startHourTime` / `endHourTime` | TOU dispatch | `"16:00"`, `"24:00"` | CONFIRMED (4,867 each) |
| `timestamp` | `getDeviceCompositeInfo` | `1754568303` | CONFIRMED (19,892) |
| `dst` | `getEquipmentLocationDetail` | `0` | CONFIRMED but thin (67) |
| `timeZone` (numeric offset) | `listAppUserDevice`, `getStormList` | `10.0` | **ASSUMED** — 23 and 7 samples |

### Formats are naive — no offset, ever

- `deviceTime` is **19 characters**, `YYYY-MM-DD HH:MM:SS`. No `Z`, no `+10:00`.
  Verified across 325 samples.
- TOU block times are `HH:MM`. No offset, no date. `24:00` is a valid end value.

So **no timestamp the gateway hands you carries its own zone.** You must pair
it with `zoneInfo` yourself. A naive string parsed by a host in another zone is
silently wrong, not an error.

---

## The traps

### 1. Epoch fields are rendered in *your* local time

`discover()` and `support` convert `activeTime` / `installTime` / `createTime`
with `datetime.fromtimestamp(ts / 1000.0)` — **no `tz` argument**, so Python
uses the *client's* zone.

Managing a Californian gateway from Sydney, an install timestamp near midnight
renders as **the wrong date**. This is tracked as
`DEF-EPOCH-RENDERED-IN-CLIENT-TZ` and is not yet fixed; until then, treat those
dates as approximate and derive from the raw epoch if the day matters.

### 2. TOU schedules are written in gateway local time

When you set a schedule, the `HH:MM` values you send are interpreted by the
gateway in **its** zone. There is no conversion anywhere in this library — the
strings pass through untouched. Building a schedule from your own local clock
puts the blocks in the wrong place by the offset between you and the hardware.

Convert deliberately:

```python
from zoneinfo import ZoneInfo

info = (await client.get_device_info())["result"]
gw_zone = ZoneInfo(info["zoneInfo"])
local_1600 = my_datetime.astimezone(gw_zone).strftime("%H:%M")
```

### 3. DST shifts the schedule, not the wall clock

`HH:MM` is wall-clock, so a block at `16:00` stays at 16:00 across a DST
transition and moves by an hour in absolute terms. If you are coordinating a
gateway against an external signal — a market price, another site, a grid event
— that hour appears and disappears twice a year.

Two further cautions on the transition days themselves:

- A local time in the skipped hour does not exist in spring; one in the repeated
  hour is ambiguous in autumn. `zoneinfo` resolves both, naive strings do not.
- **ASSUMED:** whether the numeric `timeZone` field tracks DST or stays at
  standard time is unverified. The corpus shows `10.0` for Sydney (AEST, UTC+10)
  alongside `dst: 0`, which is consistent — but with 23 and 7 samples, and none
  observed across a transition, this is a guess. **Prefer `zoneInfo` plus a real
  tz database.** Do not compute offsets from `timeZone`.

### 4. The gateway's clock can be wrong

`deviceTime` is what the gateway *believes*, which is what it acts on. Comparing
it against UTC tells you whether it has drifted:

```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

info = (await client.get_device_info())["result"]
gw_now = datetime.strptime(info["deviceTime"], "%Y-%m-%d %H:%M:%S") \
                 .replace(tzinfo=ZoneInfo(info["zoneInfo"]))
skew = (datetime.now(timezone.utc) - gw_now).total_seconds()
```

A large `skew` means schedule boundaries will not fire when you expect. Note
this includes API round-trip latency, so a few seconds is normal.

---

## Coordinating several gateways

Resolve each gateway's zone **from that gateway**, never from a config file or
from the operator's own clock:

```python
async def gateway_now(client):
    r = (await client.get_device_info())["result"]
    return (
        datetime.strptime(r["deviceTime"], "%Y-%m-%d %H:%M:%S")
                .replace(tzinfo=ZoneInfo(r["zoneInfo"])),
        r["zoneInfo"],
    )
```

Rules that hold across zones:

1. **Compare in UTC, act in local.** Convert every gateway's time to UTC to
   decide ordering; convert back to that gateway's zone to write `HH:MM`.
2. **Never reuse one gateway's `HH:MM` on another.** `16:00` in Sydney is not
   `16:00` in California — re-derive per gateway from a common absolute instant.
3. **Day boundaries differ.** Daily energy totals roll over at each gateway's
   own midnight, so "today" is not the same window across a fleet.
4. **Re-read `zoneInfo` rather than caching it.** It is site configuration and
   can be changed in the app.

---

## What the CLI shows

```bash
franklinwh-cli discover     # Timezone (Site) and Device Time (aGate)
franklinwh-cli diag         # Timezone and Device Time, together
franklinwh-cli --json support   # timezone + deviceTime
```

`discover` reports the two in different sections, some distance apart; they come
from one API response.

---

## Not established

- Whether numeric `timeZone` tracks DST (see trap 3).
- Whether the gateway applies DST itself or relies on the cloud — no capture
  spans a transition.
- How the gateway resolves a TOU boundary inside a skipped or repeated hour.
- Whether `deviceTime` is NTP-disciplined or free-running between syncs.

Per AP-14 these are open questions, not assumptions to build on. A capture
spanning a DST changeover would settle the first three.
