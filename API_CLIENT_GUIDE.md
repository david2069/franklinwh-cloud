# API Client Utilisation Guide

> Best practices for consuming the FranklinWH Cloud API responsibly.

## ⚠️ Important Context

This library accesses FranklinWH's **installer/consumer API** at `energy.franklinwh.com` — the same endpoints used by their official mobile app and installer web portal. There is **no published third-party API** or developer programme (yet). This means:

- FranklinWH can change, rate-limit, or block third-party clients at any time
- The API hostname is likely to migrate (e.g. `api.energy.franklinwh.com`) when they formalise an API
- Authentication may shift from MD5 password hash to OAuth2 or API keys
- Rate limits may be imposed globally, per-endpoint, or per-account

**Being a good API citizen today increases the chances of being welcomed into a future developer programme.**

## Client Identity Headers

Since v0.2.0, this library identifies itself honestly in every request:

```
softwareversion: franklinwh-cloud/0.2.0
optdevice:       your-hostname
optdevicename:   python
optsource:       3
optsystemversion: Python/3.14.0
lang:            EN_US
```

This lets FranklinWH distinguish our traffic from their official apps in their analytics. You can customise or disable these:

```python
# Custom identity
client = Client(fetcher, gateway, client_headers={
    "softwareversion": "my-energy-app/1.0",
    "optdevicename": "raspberry-pi",
})

# Anonymous (not recommended)
client = Client(fetcher, gateway, client_headers=None)
```

## Rate Limiting Strategies Compared

The upstream [homeassistant-franklinwh](https://github.com/richo/homeassistant-franklinwh) HACS integration implements rate control at the **application** layer. This library implements it at the **HTTP client** layer. Both approaches have merit.

### Comparison Table

| Aspect | Upstream HA Integration | This Library (franklinwh-cloud) |
|--------|------------------------|----------------------------------|
| **Layer** | Application (HA `DataUpdateCoordinator`) | HTTP client (inside `Client`) |
| **Mechanism** | `update_interval` — fixed poll period (default 30s) | `RateLimiter` — sliding window with per-min/hr/daily budgets |
| **Scope** | Controls one call (`get_stats()`) per interval | Covers **all** API calls (stats, TOU, mode, fetch, etc.) |
| **Stale data** | `tolerate_stale_data` returns cached `Stats` on failure | `tolerate_stale_data=True` — per-endpoint TTL cache with hit/miss metrics |
| **429 handling** | Not implemented — retries 3× on timeout/offline | Reactive — detects `429`, backs off per `Retry-After` header |
| **Proactive throttle** | Poll interval prevents over-calling | Sliding window blocks when approaching limits |
| **Daily budget** | No concept | Configurable — raises `RateLimitExceeded` when exhausted |
| **Granularity** | Single interval for all sensors | Per-minute, per-hour, per-day independently |
| **Opt-in** | Always active (configured in HA YAML) | Off by default — clients opt in when needed |
| **Configuration** | HA YAML: `update_interval: 30` | Python: `RateLimiter(calls_per_minute=60)` |

### When to Use Which

**Application-layer polling** (like the HA integration does) is appropriate when:
- You have a single recurring data fetch loop
- You control the scheduling (e.g. HA's coordinator, FEM's MQTT publish loop)
- You want simple, predictable API usage

**Library-layer rate limiting** (what this library provides) is appropriate when:
- Multiple independent callers share one client (CLI, scripts, automation)
- You're exploring undiscovered endpoints via `fetch` and want guardrails
- FranklinWH has imposed rate limits you need to respect
- You want a daily API budget to cap runaway scripts

**Best practice**: Use **both**. Control your poll interval at the application layer, and enable the library's `RateLimiter` as a safety net:

```python
from franklinwh import Client, TokenFetcher
from franklinwh_cloud.metrics import RateLimiter

client = Client(
    fetcher, gateway,
    rate_limiter=RateLimiter(
        calls_per_minute=30,    # conservative
        calls_per_hour=500,     # ~8/min sustained
        daily_budget=5000,      # hard cap
    ),
)
```

## Preparing for Breaking Changes

### Authentication Migration

The current flow uses MD5-hashed passwords sent as form data:

```
POST /hes-gateway/terminal/initialize/appUserOrInstallerLogin
  account=user@email.com
  password=<MD5 hash>
```

When FranklinWH moves to OAuth2 or API keys, update the `TokenFetcher` or use the forthcoming `AuthStrategy` abstraction (see roadmap). The `Client` class itself won't change.

### Endpoint Migration

If the API hostname changes (e.g. `api.energy.franklinwh.com`), update `url_base`:

```python
client = Client(fetcher, gateway, url_base="https://api.energy.franklinwh.com/")
```

### Version Monitoring

The `siteinfo()` method now returns the server version:

```python
info = await client.siteinfo()
print(info["version"])  # e.g. "2.0.0.250506_release"
```

The `fetch` command captures HTTP response headers including server info:
```bash
franklinwh-cli fetch GET /any-endpoint --json
# Response includes: via, x-cache, content-type, date, softwareversion
```

Monitor these for changes — a version bump may signal breaking API changes.

## Performance Monitoring & Observability

Every `Client` instance provides three layers of automatic monitoring:

### API Call Metrics

Per-session tracking of call counts, timing, and errors — always on, zero config:

```python
metrics = client.get_metrics()
# {
#   "total_api_calls": 42,
#   "avg_response_time_s": 0.234,
#   "min_response_time_s": 0.089,
#   "max_response_time_s": 1.456,
#   "total_errors": 0,
#   "total_rate_limits": 0,     # 429 count
#   "total_throttle_waits": 0,  # proactive waits
#   "calls_by_endpoint": {"getDeviceCompositeInfo": 12, ...},
# }
```

### CloudFront Edge Tracking

The library automatically captures CloudFront PoP (Point of Presence) information from every API response via httpx event hooks. This is invaluable for diagnosing performance issues and outages:

```python
edge = client.edge_tracker.snapshot()
# {
#   "current_pop": "SYD62-P1",          # Sydney edge, rack P1
#   "total_cf_requests": 42,
#   "cache_hits": 0,
#   "cache_misses": 42,
#   "cache_hit_rate": "0%",             # expected for dynamic API
#   "pop_distribution": {"SYD62-P1": 42},
#   "edge_transitions": 0,              # failover count
#   "transition_log": [],               # [{from, to, at_iso}]
#   "distribution_ids": ["8bec1389...cloudfront.net"],
#   "last_cf_trace_id": "7DdZaIMj..."   # per-request trace
# }
```

**What it tells you:**

| Metric | Diagnostic Value |
|--------|-----------------|
| `current_pop` | Which AWS region serves you (SYD62 = Sydney, NRT52 = Tokyo, etc.) |
| `pop_distribution` | Request distribution across edges — reveals load balancing |
| `edge_transitions` | ⚠️ Non-zero = failover detected — correlate with timeouts/errors |
| `cache_hit_rate` | Expected 0% for API (dynamic), but reveals if FranklinWH adds CDN layer |
| `distribution_ids` | CloudFront distribution hash — changes signal infrastructure redeployment |
| `last_cf_trace_id` | Unique request ID for support tickets or AWS troubleshooting |

#### Stable Connection (Normal)

```json
{
  "current_pop": "SYD62-P1",
  "total_cf_requests": 47,
  "pop_distribution": {"SYD62-P1": 47},
  "edge_transitions": 0,
  "transition_log": []
}
```
All traffic staying on one edge. ✅ No failovers.

#### Failover Detected

```json
{
  "current_pop": "MEL50-C1",
  "total_cf_requests": 47,
  "pop_distribution": {
    "SYD62-P1": 42,
    "MEL50-C1": 5
  },
  "edge_transitions": 1,
  "transition_log": [
    {"from": "SYD62-P1", "to": "MEL50-C1", "at": "2026-03-17T12:34:56"}
  ]
}
```
⚠️ CloudFront rerouted 5 requests to Melbourne. Check if latency spiked at `12:34:56`.

#### Unstable / Flapping

```json
{
  "current_pop": "NRT52-P3",
  "total_cf_requests": 100,
  "pop_distribution": {
    "SYD62-P1": 60,
    "MEL50-C1": 25,
    "NRT52-P3": 15
  },
  "edge_transitions": 4,
  "transition_log": [
    {"from": "SYD62-P1", "to": "MEL50-C1", "at": "2026-03-17T12:30:00"},
    {"from": "MEL50-C1", "to": "SYD62-P1", "at": "2026-03-17T12:35:00"},
    {"from": "SYD62-P1", "to": "NRT52-P3", "at": "2026-03-17T13:10:00"},
    {"from": "NRT52-P3", "to": "NRT52-P3", "at": "2026-03-17T13:15:00"}
  ]
}
```
🚨 Multiple failovers across 3 regions — indicative of a CloudFront or network issue.

#### Common PoP Codes (Asia-Pacific)

| Code | Location |
|------|----------|
| `SYD` | Sydney, Australia |
| `MEL` | Melbourne, Australia |
| `NRT` | Tokyo, Japan |
| `SIN` | Singapore |
| `HKG` | Hong Kong |
| `BOM` | Mumbai, India |
| `ICN` | Seoul, South Korea |

#### What Triggers Edge Switches?

- **PoP overloaded** → CloudFront reroutes to nearest available edge
- **Network path change** → ISP routing shifts (common overnight)
- **CloudFront maintenance** → Planned failover to alternate edge
- **Outage** → Requests jump to distant region (e.g., SYD → NRT)
- **DNS TTL expiry** → Normal re-evaluation, may land on different edge

#### Diagnostic Correlation

`edge_transitions > 0` **strongly correlates** with latency spikes:

| Scenario | Same PoP? | High Latency? | Likely Cause |
|----------|-----------|---------------|-------------|
| Slow responses | ✅ Yes | ✅ Yes | FranklinWH API backend slow |
| Slow responses | ❌ No | ✅ Yes | CloudFront rerouted to distant edge |
| Errors / timeouts | ✅ Yes | N/A | FranklinWH API outage |
| Errors / timeouts | ❌ No | N/A | CloudFront / network outage |

**Edge transitions are logged automatically:**
```
WARNING ☁️ CloudFront edge transition: SYD62-P1 → NRT52-P3
```

### Stale Data Cache

Per-endpoint TTL cache providing graceful degradation when the cloud is slow or unreachable:

```python
client = Client(fetcher, gateway, tolerate_stale_data=True, stale_cache_ttl=300)

# Check cache state
cache = client.stale_cache.snapshot()
# {
#   "enabled": true,
#   "cached_endpoints": 3,
#   "hits": 5,               # stale data served
#   "misses": 2,             # no cached data available
# }
```

When triggered, logs: `WARNING: Serving stale data for getDeviceCompositeInfo (age: 45s)`

### CLI Metrics

One-shot API probe with full performance and edge data:

```bash
franklinwh-cli metrics        # pretty print — probe call + metrics + CloudFront
franklinwh-cli metrics --json # machine-readable — includes edge_tracker object
```

The `metrics` command makes a single probe API call (`get_stats()`) so it shows
real data even on a fresh CLI invocation. For continuous monitoring, use `monitor`.

Sample CLI output:
```
═══ API Metrics ═══
               Probe: 845ms (get_stats)

📊 API Calls
         Total Calls: 3
        Avg Response: 0.845s
           Min / Max: 0.089s / 1.456s
              Errors: 0

☁️ CloudFront Edge
         Current PoP: SYD62-P1
         CF Requests: 3
      Cache Hit Rate: 0%
            SYD62-P1: 3 requests
    Edge Transitions: 0 (stable)
    CDN Distribution: 8bec1389...

  For continuous monitoring: franklinwh-cli monitor -d <minutes>
```

When a rate limiter is active, the output additionally includes a **Rate Limiting** section showing calls per time window and remaining budget.

### CLI Monitor — Real-Time Dashboard

Continuous battery monitoring with auto-refresh:

```bash
franklinwh-cli monitor              # full dashboard, 30s refresh
franklinwh-cli monitor -i 10        # refresh every 10 seconds
franklinwh-cli monitor -d 5         # run for 5 minutes then stop
franklinwh-cli monitor --compact    # single-line per poll (scrolling log)
franklinwh-cli monitor --json       # JSON stream per interval (for piping)
```

**Full dashboard mode** clears the screen each refresh and shows:
- Power flow bars (solar, battery, grid, home) with direction indicators
- Battery SoC (color-coded: green ≥80%, yellow ≥30%, red <30%)
- Grid status (connected/disconnected/off-grid)
- Operating mode and run status
- Daily energy totals
- Smart circuit loads (if active)
- Footer: refresh interval, uptime, poll count, API calls, CloudFront PoP

**Compact mode** appends one line per poll — ideal for logging:
```
[14:35:22] ☀  3400W  🔋  76% ↓  600W  ⚡ ● +200W  🏠  2100W  │ Self-Consumption
[14:35:52] ☀  3350W  🔋  77% ↓  550W  ⚡ ●  +50W  🏠  2100W  │ Self-Consumption
[14:36:22] ☀  3200W  🔋  78% ─    0W  ⚡ ●  +10W  🏠  2100W  │ Self-Consumption
```

**JSON mode** outputs one complete JSON object per poll — useful for piping to ETL or logging:
```bash
franklinwh-cli monitor --json -i 60 > battery_log.jsonl
```

All modes exit gracefully on `Ctrl+C`, displaying final session metrics.

## 🔄 Compatibility with Upstream HA Integration

This fork (`david2069/franklinwh-cloud`) is a **drop-in replacement** for the upstream `richo/franklinwh-python` library. All new parameters have backward-compatible defaults:

```python
# Existing code continues to work unchanged:
client = franklinwh.Client(fetcher, gateway)
# → identity headers ON, rate limiter OFF, stale cache OFF
```

### Can you use this fork under the HACS integration?

**Yes — but you don't need our resilience features there.** The HACS integration already handles these concerns at the Home Assistant application layer:

| Concern | HACS handles it in `sensor.py` | Our library handles it in `Client` |
|---------|-------------------------------|-----------------------------------|
| Poll rate | `DataUpdateCoordinator(update_interval=30)` | `RateLimiter` (disabled by default) |
| Stale data | `StaleDataCache` + `tolerate_stale_data` | `StaleDataCache` (disabled by default) |
| Retries | `for attempt in range(3)` loop | `instrumented_retry()` |

If you enable `tolerate_stale_data` in **both** the HACS config and our library, you'd get double caching — redundant but harmless, not conflicting.

### Who benefits from our library-level features?

| Consumer | Benefit |
|----------|---------|
| **FEM** (Energy Manager) | Rate limiting + stale cache for the MQTT publish loop — no HA coordinator available |
| **CLI users** | `franklinwh-cli` scripts get rate guardrails and identity headers automatically |
| **Custom Python scripts** | Anyone importing `Client` directly gets production-grade resilience |
| **Future official API** | When FranklinWH publishes rate limits, `RateLimiter` is ready |

### Should you NOT mix and match?

There is **no conflict** — the features are additive. However:
- HACS users **don't need** to enable `rate_limiter` or `tolerate_stale_data` (HA already does this)
- Non-HA users (FEM, CLI, scripts) **should consider** enabling them, since there's no outer framework doing it for you

## Credits

- [richo/homeassistant-franklinwh](https://github.com/richo/homeassistant-franklinwh) — the original HA integration that pioneered polling control with `update_interval` and `tolerate_stale_data`
- [richo/franklinwh-python](https://github.com/richo/franklinwh-python) — the upstream library this fork extends

Both projects demonstrate responsible API consumption patterns. This guide builds on their work while adding library-level protections for a broader range of use cases.

---

## Accessories & Peripherals Cookbook

The `accessories` command provides a unified view of Smart Circuits, V2L, Generator, and device hardware with cross-referenced model/SKU/compatibility data.

### CLI Usage

```bash
franklinwh-cli accessories              # inventory + status
franklinwh-cli accessories --power      # include live power data (extra MQTT call)
franklinwh-cli accessories --json       # machine-readable output
franklinwh-cli acc --power --json       # alias + power + JSON
```

Sample output:
```
════════════════════════════════════════════════════════════
  FranklinWH Accessories & Devices
════════════════════════════════════════════════════════════

🏠 aGate Gateway
              Serial: AGT-XXXXXXXXXX
               Model: aGate X-01-AU
                 SKU: AGT-R1V1-AU
            Firmware: 3.2.1

🔋 aPower Batteries (1 units, 13.6 kWh)
   aPower XXXXXX: Rated: 5000W  Capacity: 13600Wh  Warranty: 2036-01-15

🔌 Installed Accessories (2)
   Smart Circuits: SN: SC-123456  Model: Smart Circuits-01-AU  SKU: ACCY-SCV1-AU  ✓ compatible
   Generator Mod: SN: GN-789012  Model: Generator Module-01-AU  SKU: ACCY-GENV1-AU  ✓ compatible

⚡ Smart Circuits
       Hot Water: Enabled  (Always On)
          Pool Pump: Disabled  (Off)

🚗 V2L (Vehicle-to-Load)
              Status: Not enabled

⛽ Generator
              Status: Active
                Mode: Auto-Schedule
           Start SoC: 20%
            Stop SoC: 90%
```

### Python API — Querying Accessories

```python
import asyncio
import json
from franklinwh_cloud.client import Client, TokenFetcher
from franklinwh_cloud.const import FRANKLINWH_MODELS, FRANKLINWH_ACCESSORIES

async def main():
    fetcher = TokenFetcher("user@email.com", "password")
    await fetcher.get_token()
    client = Client(fetcher, "YOUR-AGATE-SERIAL")

    # ── 1. Installed accessories with cross-referencing ──────────
    gw_res = await client.get_home_gateway_list()
    gw = gw_res["result"][0]
    hw_ver = int(gw.get("sysHdVersion", 0))
    agate_model = FRANKLINWH_MODELS.get(hw_ver, {})
    print(f"aGate: {agate_model.get('model', 'Unknown')} (SKU: {agate_model.get('sku', '?')})")

    acc_res = await client.get_accessories(2)
    for accy in acc_res.get("result", []):
        a_type = accy.get("accessoryType")
        info = FRANKLINWH_ACCESSORIES.get(a_type, {})
        compat_ids = info.get("compatiable", "").split("|")
        is_compat = "ALL" in compat_ids or str(hw_ver) in compat_ids
        print(f"  {accy['accessoryName']}: {info.get('model', '?')} "
              f"(SKU: {info.get('sku', '?')}) "
              f"{'✓' if is_compat else '✗'} compatible")

    # ── 2. Smart Circuit configuration ───────────────────────────
    sc = await client.get_smart_circuits_info()
    for i in range(1, 4):
        name = sc.get(f"Sw{i}Name", f"Circuit {i}")
        mode = sc.get(f"Sw{i}Mode", 0)
        if name or mode:
            print(f"  SC{i}: {name} — {'Enabled' if mode else 'Disabled'}")

    # ── 3. Accessory power data ──────────────────────────────────
    # Smart Circuit power
    sc_power = await client.get_accessories_power_info("1")
    print(f"  SC1 Power: {sc_power['smart_circuits'][0]['power']}W")

    # V2L power
    v2l = await client.get_accessories_power_info("2")
    print(f"  V2L Power: {v2l['v2l']['power']}W")

    # Generator power
    gen = await client.get_accessories_power_info("3")
    print(f"  Gen Power: {gen['generator']['power']}W")

    # ── 4. Generator state ───────────────────────────────────────
    gen_info = await client.get_generator_info()
    if gen_info:
        mode = "Manual" if gen_info.get("manuSw") == 2 else "Auto"
        print(f"  Generator: {mode}, "
              f"Start SoC: {gen_info.get('startSoc')}%, "
              f"Stop SoC: {gen_info.get('stopSoc')}%")

    # ── 5. V2L state (from device info) ──────────────────────────
    dev = await client.get_device_info()
    result = dev.get("result", {})
    v2l_en = result.get("v2lModeEnable", 0)
    v2l_st = result.get("v2lRunState", 0)
    print(f"  V2L: {'Enabled' if v2l_en else 'Disabled'}, "
          f"State: {'Running' if v2l_st >= 1 else 'Standby'}")

    # ── 6. Full JSON dump ────────────────────────────────────────
    raw = await client.get_accessories_power_info("0")
    print(json.dumps(raw, indent=2))

asyncio.run(main())
```

### API Method Reference

| Method | Transport | Returns |
|--------|-----------|---------|
| `get_accessories(option)` | REST | Accessory list (1=common, 2=IoT, 3=equipment, 4=IoT by GW) |
| `get_smart_circuits_info()` | MQTT 311 | Per-circuit name, mode, protected load, SoC threshold |
| `get_accessories_power_info(opt)` | MQTT 353 | Live power/energy (0=raw, 1=SC, 2=V2L, 3=Generator) |
| `get_generator_info()` | REST | Generator state, mode, SoC thresholds |
| `set_smart_switch_state(tuple)` | MQTT 310 | Set circuit on/off (True/False/None per circuit) |
| `set_generator_mode(mode)` | REST | Set generator mode (1=Auto, 2=Manual) |

### Cross-Reference Constants

Accessory types map to `FRANKLINWH_ACCESSORIES` in `const/devices.py`:

| Type ID | Name | SKU | Compatible aGates |
|---------|------|-----|-------------------|
| 201 | Generator Module | ACCY-GENV1-US | 100, 101 |
| 202 | Smart Circuits | ACCY-SCV1-US | 100, 101 |
| 203 | Generator Module | ACCY-GENV2-US | 103, 104 |
| 204 | Smart Circuits | ACCY-SCV2-US | 102, 103, 104 |
| 251 | aPbox | ACCY-RCV1-US | ALL |
| 301 | Generator Module (AU) | ACCY-GENV1-AU | 102 |
| 302 | Smart Circuits (AU) | ACCY-SCV1-AU | 102 |
