"""Client metrics instrumentation for API call tracking.

Provides lightweight, zero-dependency counters and timers for monitoring
API call patterns, error rates, and performance. Includes client-side
rate limiting (proactive throttle + reactive 429 handling).
"""

import asyncio
import logging
import platform
import time
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger("franklinwh_cloud")


# ── Client Identity ──────────────────────────────────────────────────

# Library version — kept in sync with pyproject.toml
__version__ = "0.4.3"

# Legal disclaimer — logged once at Client init
DISCLAIMER = (
    f"franklinwh-cloud-client v{__version__} | UNOFFICIAL · NOT AFFILIATED WITH FRANKLINWH "
    "| NO WARRANTY · PROVIDED AS-IS · USE AT YOUR OWN RISK "
    "| You must read and understand the LICENSE and its Additional Terms before use. "
    "| This software may break without notice due to upstream API changes, "
    "outages, or authentication changes by FranklinWH. "
    "| MIT License — see LICENSE for details. "
    "| TELEMETRY Priv: Opt-in strictly via config (telemetry.enabled) — see TELEMETRY.md."
)


def get_default_client_headers() -> dict:
    """Return default client identification headers.

    We send the certified baseline ``softwareversion`` (``APP2.4.1``) to
    identify the client as a known-good app version. Empirical testing has
    shown that varying this header does **not** alter JSON payload structure
    on current endpoints — its primary role is authentication negotiation and
    server-side telemetry/analytics.

    We honestly identify as a third-party Python client via the ``optsource``
    and ``optsystemversion`` telemetry headers ("good citizen" practice).
    """
    return {
        "softwareversion": "APP2.4.1",
        "optdevice": platform.node() or "unknown",
        "optdevicename": "python",
        "optsource": "3",  # 3 = third-party
        "optsystemversion": f"Python/{platform.python_version()}",
        "lang": "EN_US",
    }


# ── Rate Limiter ─────────────────────────────────────────────────────


class RateLimiter:
    """Client-side rate limiter using a sliding window.

    Two modes:
      - Proactive: delays requests to stay under configured limits
      - Reactive: handles 429 responses with Retry-After backoff

    Parameters
    ----------
    calls_per_minute : int
        Max calls per minute (0 = unlimited)
    calls_per_hour : int
        Max calls per hour (0 = unlimited)
    daily_budget : int
        Max calls per day (0 = unlimited)
    burst_size : int
        Max burst of rapid calls before throttling kicks in
    """

    def __init__(self, calls_per_minute: int = 60, calls_per_hour: int = 0,
                 daily_budget: int = 0, burst_size: int = 10):
        self.calls_per_minute = calls_per_minute
        self.calls_per_hour = calls_per_hour
        self.daily_budget = daily_budget
        self.burst_size = burst_size

        # Sliding windows
        self._minute_window: deque = deque()  # timestamps of last 60s
        self._hour_window: deque = deque()    # timestamps of last 3600s
        self._day_count: int = 0
        self._day_start: float = time.time()

        # 429 backoff state
        self._retry_after_until: float = 0.0

    @property
    def is_rate_limited(self) -> bool:
        """Check if we're currently in a 429 backoff period."""
        return time.time() < self._retry_after_until

    @property
    def remaining_daily(self) -> int | None:
        """Remaining daily budget, or None if unlimited."""
        if self.daily_budget <= 0:
            return None
        return max(0, self.daily_budget - self._day_count)

    def _clean_windows(self):
        """Remove expired entries from sliding windows."""
        now = time.time()
        while self._minute_window and self._minute_window[0] < now - 60:
            self._minute_window.popleft()
        while self._hour_window and self._hour_window[0] < now - 3600:
            self._hour_window.popleft()
        # Reset daily counter
        if now - self._day_start > 86400:
            self._day_count = 0
            self._day_start = now

    async def acquire(self):
        """Wait until it's safe to make a request.

        Blocks if we're approaching rate limits or in a 429 backoff.
        """
        # Handle 429 backoff
        if self._retry_after_until > 0:
            wait = self._retry_after_until - time.time()
            if wait > 0:
                logger.warning(f"Rate limited (429). Waiting {wait:.1f}s")
                await asyncio.sleep(wait)
                self._retry_after_until = 0.0

        self._clean_windows()

        # Check per-minute limit
        if self.calls_per_minute > 0 and len(self._minute_window) >= self.calls_per_minute:
            oldest = self._minute_window[0]
            wait = 60 - (time.time() - oldest) + 0.1
            if wait > 0:
                logger.info(f"Throttling: {self.calls_per_minute}/min limit reached. Waiting {wait:.1f}s")
                await asyncio.sleep(wait)
                self._clean_windows()

        # Check per-hour limit
        if self.calls_per_hour > 0 and len(self._hour_window) >= self.calls_per_hour:
            oldest = self._hour_window[0]
            wait = 3600 - (time.time() - oldest) + 0.1
            if wait > 0:
                logger.warning(f"Throttling: {self.calls_per_hour}/hr limit reached. Waiting {wait:.1f}s")
                await asyncio.sleep(wait)
                self._clean_windows()

        # Check daily budget
        if self.daily_budget > 0 and self._day_count >= self.daily_budget:
            logger.error(f"Daily API budget exhausted ({self.daily_budget} calls). Blocking.")
            raise RateLimitExceeded(
                f"Daily API budget of {self.daily_budget} calls exceeded. "
                f"Resets in {86400 - (time.time() - self._day_start):.0f}s."
            )

    def record_call(self):
        """Record a call in the sliding windows."""
        now = time.time()
        self._minute_window.append(now)
        self._hour_window.append(now)
        self._day_count += 1

    def record_429(self, retry_after: int = 30):
        """Record a 429 response and set backoff timer."""
        self._retry_after_until = time.time() + retry_after

    def snapshot(self) -> dict:
        """Return rate limiter state for diagnostics."""
        self._clean_windows()
        return {
            "calls_last_minute": len(self._minute_window),
            "calls_last_hour": len(self._hour_window),
            "calls_today": self._day_count,
            "limit_per_minute": self.calls_per_minute,
            "limit_per_hour": self.calls_per_hour,
            "daily_budget": self.daily_budget,
            "remaining_daily": self.remaining_daily,
            "is_throttled": self.is_rate_limited,
        }


class RateLimitExceeded(Exception):
    """Raised when daily API budget is exhausted."""


class StaleDataCache:
    """Cache last-known-good API responses for graceful degradation.

    When the FranklinWH cloud is slow, overloaded, or unreachable, this
    cache returns the last successful response rather than failing outright.

    Inspired by the `tolerate_stale_data` pattern in
    richo/homeassistant-franklinwh.

    Parameters
    ----------
    max_age_s : float
        Maximum age of cached data in seconds. 0 = no expiry.
        Default 300s (5 minutes).
    enabled : bool
        Whether to serve stale data on failure.
    """

    def __init__(self, max_age_s: float = 300, enabled: bool = True):
        self.max_age_s = max_age_s
        self.enabled = enabled
        self._cache: dict[str, tuple[float, object]] = {}  # endpoint -> (timestamp, data)
        self.hits: int = 0
        self.misses: int = 0

    def store(self, endpoint: str, data: object) -> None:
        """Cache a successful response."""
        self._cache[endpoint] = (time.time(), data)

    def get(self, endpoint: str) -> object | None:
        """Retrieve cached data if available and not expired.

        Returns None if cache is empty, disabled, or expired.
        """
        if not self.enabled:
            return None
        entry = self._cache.get(endpoint)
        if entry is None:
            self.misses += 1
            return None
        ts, data = entry
        if self.max_age_s > 0 and (time.time() - ts) > self.max_age_s:
            self.misses += 1
            logger.info(f"Stale cache expired for {endpoint} "
                        f"(age: {time.time() - ts:.0f}s > {self.max_age_s}s)")
            return None
        self.hits += 1
        age = time.time() - ts
        logger.warning(f"Serving stale data for {endpoint} (age: {age:.0f}s)")
        return data

    def is_populated(self, endpoint: str) -> bool:
        """Check if cache has data for this endpoint."""
        return endpoint in self._cache

    def clear(self) -> None:
        """Clear all cached data."""
        self._cache.clear()

    def snapshot(self) -> dict:
        """Return cache state for diagnostics."""
        cached_endpoints = {}
        now = time.time()
        for ep, (ts, _) in self._cache.items():
            cached_endpoints[ep] = {
                "age_s": round(now - ts, 1),
                "expired": self.max_age_s > 0 and (now - ts) > self.max_age_s,
            }
        return {
            "enabled": self.enabled,
            "max_age_s": self.max_age_s,
            "cached_endpoints": len(self._cache),
            "hits": self.hits,
            "misses": self.misses,
            "endpoints": cached_endpoints,
        }


# ── Edge Tracker ─────────────────────────────────────────────────────


class EdgeTracker:
    """Track CloudFront edge locations and cache behaviour across API calls.

    Records which CloudFront PoP (Point of Presence) serves each request,
    detects edge transitions (failovers), and tracks cache hit rates.

    Captured from response headers:
        x-amz-cf-pop  — edge location code (e.g. SYD62-P1 = Sydney)
        x-cache       — Miss/Hit from cloudfront
        via           — CloudFront distribution ID
        x-amz-cf-id  — per-request trace ID
    """

    def __init__(self):
        self.total_requests: int = 0
        self.cache_hits: int = 0
        self.cache_misses: int = 0
        self.current_pop: str | None = None
        self.pop_counts: dict[str, int] = {}          # pop -> count
        self.transitions: list[dict] = []              # [{from, to, at}]
        self._distribution_ids: set[str] = set()       # unique CF distributions
        self._last_cf_id: str | None = None
        self._last_response_headers: dict | None = None  # last full response headers
        self._last_request_url: str | None = None          # last request URL
        self._last_request_method: str | None = None       # last HTTP method

    def record_response(self, headers: dict | object) -> None:
        """Extract and record CloudFront info from response headers.

        Parameters
        ----------
        headers : dict-like
            Response headers (httpx.Headers or plain dict).
        """
        # Support both dict and httpx.Headers (which has .get())
        get = headers.get if hasattr(headers, 'get') else lambda k, d=None: headers.get(k, d)
        # Store full headers for --headers display
        self._last_response_headers = dict(headers) if hasattr(headers, 'items') else {}

        pop = get("x-amz-cf-pop")
        cache_status = get("x-cache", "")
        via = get("via", "")
        cf_id = get("x-amz-cf-id")

        if not pop and not cache_status:
            return  # Not a CloudFront response

        self.total_requests += 1

        # Track cache hit/miss
        if "Hit" in cache_status:
            self.cache_hits += 1
        elif "Miss" in cache_status:
            self.cache_misses += 1

        # Track edge PoP
        if pop:
            self.pop_counts[pop] = self.pop_counts.get(pop, 0) + 1

            # Detect edge transition (failover)
            if self.current_pop and self.current_pop != pop:
                self.transitions.append({
                    "from": self.current_pop,
                    "to": pop,
                    "at": time.time(),
                    "at_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                })
                logger.warning(
                    f"☁️ CloudFront edge transition: {self.current_pop} → {pop}"
                )
            self.current_pop = pop

        # Track distribution IDs from 'via' header
        if "cloudfront" in via.lower():
            # e.g. "1.1 abc123.cloudfront.net (CloudFront)"
            parts = via.split()
            for p in parts:
                if ".cloudfront.net" in p:
                    self._distribution_ids.add(p)

        if cf_id:
            self._last_cf_id = cf_id

    def snapshot(self) -> dict:
        """Return edge tracking state for diagnostics."""
        return {
            "current_pop": self.current_pop,
            "total_cf_requests": self.total_requests,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_rate": (
                f"{(self.cache_hits / self.total_requests * 100):.0f}%"
                if self.total_requests > 0 else "n/a"
            ),
            "pop_distribution": dict(self.pop_counts),
            "edge_transitions": len(self.transitions),
            "transition_log": self.transitions[-10:],  # last 10
            "distribution_ids": list(self._distribution_ids),
            "last_cf_trace_id": self._last_cf_id,
        }


def extract_endpoint(url: str) -> str:
    """Extract short endpoint name from full URL.

    Examples:
        >>> extract_endpoint("https://energy.franklinwh.com/hes-gateway/terminal/getDeviceCompositeInfo")
        'getDeviceCompositeInfo'
        >>> extract_endpoint("https://energy.franklinwh.com/hes-gateway/common/getAccessoryList?gatewayId=123")
        'getAccessoryList'
    """
    # Strip query params
    base = url.split("?")[0]
    # Get last path segment
    return base.rstrip("/").rsplit("/", 1)[-1]


@dataclass
class ClientMetrics:
    """Lightweight API call metrics for a Client session.

    All counters are simple ints/floats — no locks needed for
    single-threaded async usage.
    """

    # Session timing
    started_at: float = field(default_factory=time.time)

    # API call counters
    total_calls: int = 0
    calls_by_method: dict = field(default_factory=dict)
    calls_by_endpoint: dict = field(default_factory=dict)

    # Response timing
    total_time_s: float = 0.0
    last_call_time_s: float = 0.0
    min_call_time_s: float = float("inf")
    max_call_time_s: float = 0.0

    # Error tracking
    total_errors: int = 0
    errors_by_type: dict = field(default_factory=lambda: {
        "timeout": 0,
        "auth_401": 0,
        "server_5xx": 0,
        "network": 0,
        "parse": 0,
    })

    # Retry & auth
    retry_count: int = 0
    token_refresh_count: int = 0
    last_token_refresh_at: float = 0.0
    login_count: int = 0

    # Rate limiting
    total_rate_limits: int = 0
    total_throttle_waits: int = 0

    # Backend version telemetry — populated on login and each token refresh.
    # Contains the softwareVersion the server echoed back in its login response
    # (e.g. "APP2.4.1"). None until the first token refresh completes.
    _latest_backend_software_version: str | None = None

    def record_call(self, method: str, endpoint: str, elapsed: float) -> None:
        """Record a successful API call."""
        self.total_calls += 1
        self.calls_by_method[method] = self.calls_by_method.get(method, 0) + 1
        self.calls_by_endpoint[endpoint] = self.calls_by_endpoint.get(endpoint, 0) + 1
        self.total_time_s += elapsed
        self.last_call_time_s = elapsed
        if elapsed < self.min_call_time_s:
            self.min_call_time_s = elapsed
        if elapsed > self.max_call_time_s:
            self.max_call_time_s = elapsed

    def record_error(self, error_type: str) -> None:
        """Record an API error by category."""
        self.total_errors += 1
        self.errors_by_type[error_type] = self.errors_by_type.get(error_type, 0) + 1

    def record_retry(self) -> None:
        """Record a retry event (401 → refresh → retry)."""
        self.retry_count += 1

    def record_token_refresh(self) -> None:
        """Record a token refresh."""
        self.token_refresh_count += 1
        self.last_token_refresh_at = time.time()

    def record_login(self) -> None:
        """Record a login attempt."""
        self.login_count += 1

    def record_rate_limit(self) -> None:
        """Record a 429 rate limit response."""
        self.total_rate_limits += 1

    def record_throttle_wait(self) -> None:
        """Record a proactive throttle wait."""
        self.total_throttle_waits += 1

    @property
    def uptime_s(self) -> float:
        """Seconds since this metrics instance was created."""
        return time.time() - self.started_at

    @property
    def avg_call_time_s(self) -> float:
        """Average API call time in seconds."""
        return self.total_time_s / self.total_calls if self.total_calls > 0 else 0.0

    def snapshot(self) -> dict:
        """Return a dict snapshot of all metrics for external consumption."""
        return {
            "uptime_s": round(self.uptime_s, 1),
            "total_api_calls": self.total_calls,
            "calls_by_method": dict(self.calls_by_method),
            "calls_by_endpoint": dict(self.calls_by_endpoint),
            "avg_response_time_s": round(self.avg_call_time_s, 4),
            "min_response_time_s": round(self.min_call_time_s, 4) if self.total_calls > 0 else 0.0,
            "max_response_time_s": round(self.max_call_time_s, 4),
            "last_response_time_s": round(self.last_call_time_s, 4),
            "total_errors": self.total_errors,
            "errors_by_type": dict(self.errors_by_type),
            "retry_count": self.retry_count,
            "token_refresh_count": self.token_refresh_count,
            "last_token_refresh_s_ago": round(time.time() - self.last_token_refresh_at, 1) if self.last_token_refresh_at > 0 else None,
            "login_count": self.login_count,
            "total_rate_limits": self.total_rate_limits,
            "total_throttle_waits": self.total_throttle_waits,
            # Backend version echoed by the server on login/refresh.
            # None until first token refresh. Used by the canary trap.
            "latest_backend_software_version": self._latest_backend_software_version,
        }


async def instrumented_retry(metrics, endpoint, method, func, filter_fn, refresh_fn,
                             rate_limiter: RateLimiter | None = None,
                             stale_cache: StaleDataCache | None = None):
    """Wrap retry() with metrics instrumentation.

    Parameters
    ----------
    metrics : ClientMetrics
        The metrics instance to record to.
    endpoint : str
        Short endpoint name (e.g. 'getDeviceCompositeInfo').
    method : str
        HTTP method ('GET' or 'POST').
    func : callable
        Async function to call (the inner __get or __post closure).
    filter_fn : callable
        Filter function — returns True if response is OK.
    refresh_fn : callable
        Async function to refresh token on 401.
    rate_limiter : RateLimiter | None
        Optional rate limiter for proactive throttling.
    stale_cache : StaleDataCache | None
        Optional cache for graceful degradation on errors.
    """
    import httpx

    # Proactive rate limiting — wait if approaching limits
    if rate_limiter is not None:
        await rate_limiter.acquire()

    t0 = time.time()
    try:
        res = await func()
        # Record in rate limiter window
        if rate_limiter is not None:
            rate_limiter.record_call()
        elapsed = time.time() - t0

        if filter_fn(res):
            metrics.record_call(method, endpoint, elapsed)
            # Cache successful response
            if stale_cache is not None:
                stale_cache.store(endpoint, res)
            return res

        # Filter failed (401) — refresh and retry
        metrics.record_error("auth_401")
        metrics.record_retry()
        await refresh_fn()

        t1 = time.time()
        res = await func()
        elapsed2 = time.time() - t1
        metrics.record_call(method, endpoint, elapsed2)
        # Cache successful retry
        if stale_cache is not None:
            stale_cache.store(endpoint, res)
        return res

    except httpx.TimeoutException:
        elapsed = time.time() - t0
        metrics.record_call(method, endpoint, elapsed)
        metrics.record_error("timeout")
        # Try stale cache before raising
        if stale_cache is not None:
            cached = stale_cache.get(endpoint)
            if cached is not None:
                logger.warning(f"Timeout on {endpoint} — returning cached data")
                return cached
        raise
    except httpx.ConnectError:
        elapsed = time.time() - t0
        metrics.record_call(method, endpoint, elapsed)
        metrics.record_error("network")
        # Try stale cache before raising
        if stale_cache is not None:
            cached = stale_cache.get(endpoint)
            if cached is not None:
                logger.warning(f"Network error on {endpoint} — returning cached data")
                return cached
        raise
    except (ValueError, KeyError):
        elapsed = time.time() - t0
        metrics.record_call(method, endpoint, elapsed)
        metrics.record_error("parse")
        raise
