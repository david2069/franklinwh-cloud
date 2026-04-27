# API Rate Limiting & Good Citizenship

> **Why this matters:** `franklinwh-cloud` is an *unofficial* library calling a *privately operated*
> cloud API that serves real paying customers. Every call you make competes with the FranklinWH
> mobile app, firmware update checks, and other third-party integrations. Being a good API citizen
> is not optional — it is what keeps everyone's systems stable and prevents the entire third-party
> ecosystem from being blocked.

---

## What Is the Rate Limiter?

The library ships a built-in **client-side rate limiter** (`RateLimiter` in `metrics.py`).
It enforces three independent, configurable limits:

| Limit | Default | Behaviour when hit |
|---|---|---|
| **Per Minute** | 60 calls/min | Proactively sleeps and retries — *never raises* |
| **Per Hour** | unlimited | Proactively sleeps and retries — *never raises* |
| **Daily Budget** | unlimited | Raises `RateLimitExceeded` — **hard stop** |

The limiter also handles **reactive 429 responses** from the server: if the FranklinWH API returns
HTTP 429, the library reads the `Retry-After` header and parks all calls for that duration before
transparently resuming.

---

## Why Does It Exist?

The FranklinWH Cloud API is an unofficial, undocumented endpoint with **no published rate limit
policy**. That makes it critical to be *self-governing*:

1. **Protect the FranklinWH backend.**
   Hammering an unofficial API is the fastest way to get the entire third-party ecosystem banned
   by a firewall rule or IP block. That would break every user of this library simultaneously —
   not just the runaway script.

2. **Protect your account.**
   Unusual call volumes can trigger security reviews, temporary account locks, or token
   invalidation by FranklinWH. A hard daily budget stops a misbehaving integration from burning
   through calls you never intended to make.

3. **Protect the community.**
   If one user's agent goes rogue and the API responds by blocking that IP range, everyone behind
   the same ISP or cloud provider is collateral damage.

4. **Protect your hardware.**
   Repeated rapid-fire write operations against the aGate (mode changes, TOU schedule writes,
   off-grid toggles) can stress-test or confuse firmware state machines in ways that matter for
   real-world battery safety.

---

## How It Works

```
Your code
   │
   ▼
RateLimiter.acquire()
   │  ├─ checks 429 backoff window  → sleeps if recovering
   │  ├─ per-minute sliding window  → sleeps if approaching limit
   │  ├─ per-hour sliding window    → sleeps if approaching limit
   │  └─ daily budget counter       → raises RateLimitExceeded if exhausted
   ▼
HTTP call
   │
   ▼
instrumented_retry()
   │  ├─ handles 401 token refresh → retries once transparently
   │  ├─ records timing and error metrics
   │  └─ serves stale-cache on timeout/network error (if enabled)
   ▼
Response
```

### Sliding Windows

The per-minute and per-hour limits use **sliding windows** — not fixed clock intervals. If you
made 59 calls between 10:00:30 and 10:01:00, the 60th call is allowed at 10:01:30 (not at
10:02:00). This is fairer and avoids thundering-herd resets at the top of each minute.

### Daily Budget — Hard Stop

The daily counter resets exactly 24 hours after the first call in that session (not at midnight).
When the budget is exhausted:

- An `ERROR` log is emitted: `Daily API budget exhausted (N calls). Blocking.`
- `RateLimitExceeded` is raised on **every subsequent call** until the 24-hour window resets.
- **The library does not silently drop calls.** If you do not catch `RateLimitExceeded`, your
  integration will surface the error — which is the correct behaviour.

---

## How to Configure It

Pass a `RateLimiter` instance when constructing the client:

```python
from franklinwh_cloud import FranklinWHCloud
from franklinwh_cloud.metrics import RateLimiter

client = FranklinWHCloud(
    email="user@example.com",
    password="••••••••",
    rate_limiter=RateLimiter(
        calls_per_minute=30,   # conservative — half the default
        calls_per_hour=200,
        daily_budget=1000,     # hard stop: 1000 calls/day
    )
)
```

Pass `0` to any parameter to **disable** that specific limit:

```python
# Unlimited per-minute, but hard stop at 500/day
RateLimiter(calls_per_minute=0, daily_budget=500)
```

### Default (No Arguments)

```python
RateLimiter()
# calls_per_minute=60, calls_per_hour=0 (unlimited), daily_budget=0 (unlimited)
```

The library default is intentionally permissive — it is up to each integration to set a
`daily_budget` appropriate for its use case.

---

## Recommended Budgets

| Use Case | Per-Minute | Per-Hour | Daily Budget |
|---|---|---|---|
| **Home automation (30s poll)** | 10 | 120 | 5 000 |
| **Developer / debugging** | 30 | 200 | 2 000 |
| **CLI one-off queries** | 60 | — | — |
| **AI agent / automation script** | 10 | 60 | **500** |

!!! warning "AI agents should use the most conservative budget"
    An agent that panics, retries, or enters a loop will saturate a loose daily budget in minutes.
    A 500/day hard cap is a meaningful circuit breaker — it surfaces a hard `RateLimitExceeded`
    error that you will see, rather than silently draining your API headroom while the agent
    reports everything is fine.

---

## Monitoring Your Usage

### CLI

```bash
franklinwh-cli metrics
```

Displays a live snapshot of calls made today, calls per minute, remaining daily budget, and
any active 429 backoff state.

### Programmatically

```python
print(client.rate_limiter.snapshot())
# {
#   "calls_today":       142,
#   "daily_budget":      5000,
#   "remaining_daily":   4858,
#   "calls_last_minute": 3,
#   "calls_last_hour":   89,
#   "limit_per_minute":  60,
#   "limit_per_hour":    0,
#   "is_throttled":      false
# }
```

---

## Handling `RateLimitExceeded`

Catch it explicitly and alert — don't swallow it silently:

```python
from franklinwh_cloud.metrics import RateLimitExceeded

try:
    stats = await client.get_stats(gateway_id)
except RateLimitExceeded as e:
    logger.error(f"Daily API budget exhausted: {e}")
    # serve stale data, pause polling, alert the user —
    # do NOT retry in a loop
```

---

## FAQ

**Q: My integration is working perfectly. Do I even need a daily budget?**

The budget is for the day your code *stops* working correctly — not for today. A polling loop
that hits an unexpected exception and retries in a tight loop can exhaust thousands of calls in
seconds. The budget is the last line of defence between a bug in your code and a FranklinWH
account action.

---

**Q: Are there any downsides to setting a daily budget?**

Genuinely, no functional downsides. The only "cost" is that a hard-stop daily budget means your
app goes read-only once the budget is exhausted and stays that way until the 24-hour window
resets. But that is *exactly the right trade-off* — a frozen dashboard is recoverable; a
FranklinWH IP ban or account suspension is not.

---

**Q: Does the daily counter reset at midnight?**

No — it resets 24 hours after the *first call in the current session*. This is intentional: a
session that starts at 11 PM doesn't get a free budget reset at midnight after only one hour of
operation.

---

**Q: What happens if the FranklinWH API itself returns a 429?**

The library reads the `Retry-After` header and automatically parks all calls for that duration.
When the backoff clears, calls resume normally. This is independent of the client-side limiter —
both can be active simultaneously, and both protect you by different mechanisms.

---

**Q: Can I raise the budget for a specific debugging session and reset it afterwards?**

Yes — pass a different `RateLimiter` instance at client construction time. Since the counter is
in-memory and per-session, it resets every time the process restarts. For one-off debugging,
simply use `daily_budget=0` (unlimited) and remember to restore your production limit before
deploying.

---

**Q: I'm building an AI agent integration. What settings should I use?**

```python
RateLimiter(calls_per_minute=10, calls_per_hour=60, daily_budget=500)
```

Agents can panic-loop. A tight daily budget means a misbehaving agent burns out quickly and
surfaces a hard `RateLimitExceeded` error that you will see and can act on — rather than
silently draining your API headroom while the agent reports that everything is fine.

---

**Q: If I'm hitting the rate limiter legitimately, how do I increase throughput without risk?**

Review your polling pattern first:

- Are you calling read-only endpoints more frequently than your display actually refreshes?
- Are you fetching TOU schedules or static config on every poll cycle? → use the stale-data
  cache instead (read-once endpoints are explicitly marked in the API reference).
- Are multiple services sharing the same `FranklinWHCloud` instance and therefore the same
  `RateLimiter`? → this is correct and intended behaviour.

If after reviewing you genuinely need more calls, raise `calls_per_hour` before raising
`daily_budget`. The daily budget is your safety net — keep it set.

---

## Good Citizenship Summary

| ✅ Do | ❌ Don't |
|---|---|
| Set a `daily_budget` on every long-running integration | Leave `daily_budget=0` in production |
| Use conservative per-minute limits for agents | Poll faster than your display refreshes |
| Catch `RateLimitExceeded` and alert — don't swallow it | Retry on `RateLimitExceeded` — wait for the reset |
| Use stale-cache for read-once / low-change data | Make a live API call for data fetched 10 seconds ago |
| Check `franklinwh-cli metrics` after debugging sessions | Leave debug-level polling running overnight |
| Think about per-hour limits as a secondary guardrail | Rely solely on the daily budget as the only safety |
