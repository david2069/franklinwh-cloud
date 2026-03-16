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
softwareversion: franklinwh-python/0.2.0
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

| Aspect | Upstream HA Integration | This Library (franklinwh-python) |
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
from franklinwh.metrics import RateLimiter

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

## Metrics & Observability

Every `Client` instance tracks API usage automatically:

```python
metrics = client.get_metrics()
# {
#   "total_api_calls": 42,
#   "avg_response_time_s": 0.234,
#   "total_rate_limits": 0,     # 429 count
#   "total_throttle_waits": 0,  # proactive waits
#   "calls_by_endpoint": {"getDeviceCompositeInfo": 12, ...},
# }
```

CLI:
```bash
franklinwh-cli metrics        # pretty print
franklinwh-cli metrics --json # machine-readable
```

When a rate limiter is active, the metrics output includes a **Rate Limiting** section showing calls per time window and remaining budget.

## Credits

- [richo/homeassistant-franklinwh](https://github.com/richo/homeassistant-franklinwh) — the original HA integration that pioneered polling control with `update_interval` and `tolerate_stale_data`
- [richo/franklinwh-python](https://github.com/richo/franklinwh-python) — the upstream library this fork extends

Both projects demonstrate responsible API consumption patterns. This guide builds on their work while adding library-level protections for a broader range of use cases.
