# Caching Strategy

> **Purpose:** This document is the single authoritative reference for every caching
> layer in the `franklinwh-cloud` library — what is cached, where, for how long,
> what triggers a cache hit, and what the consequences of a miss are.
>
> Agents and integrators **must** read this before modifying polling logic,
> adding new API calls to hot paths, or designing downstream consumers.

---

## Overview

The library uses **five distinct caching layers**, each targeting a different failure
mode or performance concern. They are independent and stack on top of each other.

| Layer | Class / Attr | Scope | TTL | Miss consequence |
|-------|-------------|-------|-----|-----------------|
| [1. HTTP Stale Cache](#1-http-stale-cache-staledatacache) | `StaleDataCache` | Per HTTP endpoint | 300s (configurable) | Network/timeout errors raise |
| [2. Grid Topology Cache](#2-grid-topology-cache-_not_grid_tied) | `client._not_grid_tied` | Per `Client` instance | Lifetime of power-up cycle | `get_entrance_info()` called once |
| [3. Stats Last-Known-Good](#3-stats-last-known-good-defect-def-blank-stats-passthrough) | _(not yet implemented — DEF-BLANK-STATS-PASSTHROUGH)_ | Per `Client` | Configurable | Zero telemetry published ⚠️ |
| [4. Static Site Data (Conceptual)](#4-static-site-data-gateway--device-info) | Caller responsibility | Per session | Until hardware changes | Re-fetched on every call |
| [5. CloudFront Edge Cache](#5-cloudfront-edge-cache) | AWS infrastructure | Per CDN node | Varies by endpoint | Transparent miss, slightly slower |

---

## 1. HTTP Stale Cache (`StaleDataCache`)

**File:** `franklinwh_cloud/metrics.py`
**Class:** `StaleDataCache`
**Used by:** `instrumented_retry()` wrapper — applied to every HTTP call

### What it caches
Every successful HTTP response, keyed by **endpoint name** (last URL path segment,
e.g. `getDeviceCompositeInfo`, `selectOffgrid`).

### When a cached response is served
Only on **transport failures**:
- `httpx.TimeoutException` — aGate or cloud unresponsive
- `httpx.ConnectError` — network unreachable

It does **not** serve stale data on:
- HTTP 200 with `result: null` (API glitch) ← **DEF-BLANK-STATS-PASSTHROUGH**
- HTTP 5xx server errors
- Parse/JSON errors

### TTL
Default **300 seconds (5 minutes)**. Configurable via `StaleDataCache(max_age_s=...)`.
Expired entries return `None` — the underlying exception is then re-raised.

### Opt-in — not always active
`StaleDataCache` is only active when passed to `Client(cache=...)`.
- **`FranklinWHCloud` wrapper:** ✅ active (`StaleDataCache()` created in wrapper init)
- **Raw `Client(auth, gateway)`:** ❌ not active — consumer must pass `cache=` explicitly

```python
from franklinwh_cloud.client import Client
from franklinwh_cloud.metrics import StaleDataCache

# Explicitly enable stale cache on a raw client
cache = StaleDataCache(max_age_s=120)   # 2 minute TTL
client = Client(auth, gateway, cache=cache)
```

### Benefit
Transparent resilience to transient aGate communication gaps. The aGate's internal
AWS MQTT relay occasionally stalls for 5–15 seconds; the stale cache bridges these
gaps without the downstream consumer (FHAI, monitor) seeing an error.

### Visibility
`franklinwh-cli metrics` shows stale cache hits and per-endpoint age.

---

## 2. Grid Topology (`not_grid_tied` constructor param)

**File:** `franklinwh_cloud/client.py`
**Attribute:** `client._not_grid_tied: bool`

### What it stores
Whether the site has **no utility grid connection** (`True` = permanent island,
`False` = grid-tied). Defaults to `False`, which is correct for the vast majority
of FranklinWH installations.

### Who sets it and when
**The integrator** — at `Client` construction time, from its own DB or config:

```python
# FHAI startup: read from DB, pass in — no API call needed
not_grid_tied = db.get_static("not_grid_tied", gateway_serial) or False
client = Client(auth, gateway, not_grid_tied=not_grid_tied)

# If not in DB yet (first run), fetch from API and persist
if not db.has("not_grid_tied", gateway_serial):
    entrance = await tmp_client.get_entrance_info()
    not_grid_tied = not bool(entrance["result"]["gridFlag"])
    db.set_static("not_grid_tied", gateway_serial, not_grid_tied)
    client = Client(auth, gateway, not_grid_tied=not_grid_tied)
```

### Why the library does NOT call `get_entrance_info()` for this
- `NOT_GRID_TIED` is **extremely rare** — the vast majority of sites are grid-tied
- Calling `get_entrance_info()` on every client startup taxes all users for a rare case
- The integrator already does a startup snapshot of static data (battery capacity,
  serials, etc.) — `gridFlag` is one more field in that same snapshot
- Persisting to DB means **zero API calls on subsequent restarts**

### `get_stats()` reads it directly — no API call, no async
```python
# stats.py — just reads the bool, no lazy-populate, no get_entrance_info()
if self._not_grid_tied:
    grid_connection_state = GridConnectionState.NOT_GRID_TIED
```

### Off-grid sites
Operators of permanently-off-grid sites explicitly pass `not_grid_tied=True`.
This is the correct layer for this decision — the operator knows their own site.

---

## 3. Stats Last-Known-Good ⚠️ NOT YET IMPLEMENTED

**Defect:** `DEF-BLANK-STATS-PASSTHROUGH`
**Priority:** S2 — High

### The gap
When `get_device_composite_info()` returns HTTP 200 with `result: null`
(a known FranklinWH cloud API glitch, distinct from a network error),
`get_stats()` currently returns `empty_stats()`:
```
battery_soc = 0      ← WRONG — looks like battery dead
solar = 0.0          ← WRONG — looks like no solar
grid_connection_state = CONNECTED   ← WRONG — we don't know the state
```
`StaleDataCache` does **not** catch this because it is triggered on exceptions,
not on valid-HTTP-empty-payload responses.

### Intended fix
Add a `_last_good_stats: Stats | None` attribute to `Client`.
In `get_stats()`, before returning `empty_stats()`, check if a prior good
reading exists and return it instead, with `Stats.is_stale = True`.

```python
# Proposed behaviour
if not data_v2:
    if self._last_good_stats is not None:
        logger.warning("get_stats: empty API response — returning last-known-good stats")
        self._last_good_stats.is_stale = True
        return self._last_good_stats
    return empty_stats()   # first-ever call, no prior data yet

# On successful parse, always update cache
self._last_good_stats = stats
stats.is_stale = False
return stats
```

### Downstream consumer responsibility
Consumers **must** check `stats.is_stale` before writing to HA / MQTT:
```python
stats = await client.get_stats()
if stats.is_stale:
    logger.warning("Skipping publish — stale stats from API glitch")
    return   # do not overwrite HA sensors with zeros
```

---

## 4. Static Site Data (Gateway & Device Info)

These are **not cached by the library** — they are the caller's responsibility.
However, they are explicitly documented here because they are **static for the
life of a hardware installation** and must never be polled at telemetry cadence.

| Data | API method | Change frequency | Recommended poll |
|------|-----------|-----------------|-----------------|
| Gateway serial / model | `get_home_gateway_list()` | Never (hardware) | Startup only |
| Battery capacity (kWh) | `get_device_info()` → `totalCap` | Never (hardware) | Startup only |
| Battery count | `get_device_info()` → `apowerList` | Rare (new battery added) | Startup + daily |
| aPower serials | `get_apower_info()` | Never (hardware) | Startup only |
| Grid flag (grid-tied?) | `get_entrance_info()` → `gridFlag` | Never | Cached by `_not_grid_tied` |
| Smart circuit config | `get_smart_circuits_info()` | Rare | Startup + hourly |
| Firmware version | `get_agate_info()` → `firmwareVersion` | Rare (OTA update) | Daily |
| Operating mode list | `get_gateway_tou_list()` | Rare | Startup only |

### The golden rule
> If the value would not change without someone visiting the property with tools,
> it is **static** and must never be included in the fast telemetry loop.

Polling static data at 5–15s intervals **will** cause `DeviceTimeoutException`
by overwhelming the aGate's MQTT relay. The aGate has a hard internal queue limit.

### Pattern for integrators
```python
# ── Startup (once) ──────────────────────────────────────────────────
device_info   = await client.get_device_info()
battery_kwh   = device_info["result"]["totalCap"]      # e.g. 13.6
battery_count = len(device_info["result"]["apowerList"])

# ── Fast loop (every 5–15s) ─────────────────────────────────────────
stats = await client.get_stats()    # composite info only
publish(stats)

# ── Slow loop (every 15–60 min) ─────────────────────────────────────
circuits = await client.get_smart_circuits_info()   # refresh if user changed
```

---

## 5. CloudFront Edge Cache

**Infrastructure:** AWS CloudFront CDN, transparent to the library
**Tracked by:** `EdgeTracker` in `metrics.py`

### What it caches
FranklinWH routes all API calls through CloudFront. Some read endpoints
(historically `getDeviceCompositeInfo`) are occasionally served from a CDN
cache for a short TTL (typically 1–10 seconds). This is entirely outside
library control.

### Effect
A `cache_hit_rate > 0%` in `franklinwh-cli metrics` means CloudFront is
serving some responses from its edge cache rather than forwarding to the
FranklinWH origin servers. This is **beneficial** — it reduces origin load
and improves response latency.

### Edge transitions
When CloudFront re-routes a session to a different PoP (Point of Presence),
`EdgeTracker` records a transition and logs a warning. Transitions correlate
with edge failovers and occasionally cause a 1–2 poll latency spike.

### Visibility
```bash
franklinwh-cli metrics     # shows PoP, cache hit rate, transition count
franklinwh-cli raw <url> --headers   # shows raw x-cache, x-amz-cf-pop headers
```

---

## Summary: What to do when the API glitches

| Scenario | What happens now | After DEF-BLANK-STATS-PASSTHROUGH fix |
|----------|-----------------|--------------------------------------|
| Network timeout | `StaleDataCache` serves last good HTTP payload | ✅ Same |
| `result: null` in 200 response | `empty_stats()` published (zeros) ⚠️ | Returns `last_good_stats` with `is_stale=True` |
| Full API outage (ConnectError) | `StaleDataCache` for up to 5 min, then raises | ✅ Same |
| First-ever poll with no data | Returns `empty_stats()` | Returns `empty_stats()` (no prior data to serve) |

---

## Related Documents

- [`API_COOKBOOK.md §🚫 API Anti-Patterns`](API_COOKBOOK.md) — polling cadence rules
- [`API_COOKBOOK.md §🔌 Grid Connection State`](API_COOKBOOK.md) — `_not_grid_tied` cache usage
- [`RATE_LIMITING.md`](RATE_LIMITING.md) — `RateLimiter` configuration
- [`defect_list.md`](../defect_list.md) — `DEF-BLANK-STATS-PASSTHROUGH` tracking
