"""Metrics command — API performance, rate limiter, and CloudFront edge data.

Makes a single probe API call so metrics show real data even on a fresh
CLI invocation. For continuous monitoring, use `franklinwh-cli monitor`.

Usage:
    franklinwh-cli metrics           # one-shot probe + metrics display
    franklinwh-cli metrics --json    # machine-readable output
"""

import time

from franklinwh_cloud.cli_output import (
    print_header, print_section, print_kv, print_json_output, print_warning,
    c,
)


async def run(client, *, json_output: bool = False):
    """Execute the metrics command with a probe call."""

    # ── Probe call to populate real metrics ───────────────────────
    probe_start = time.time()
    try:
        await client.get_stats()
        probe_ms = (time.time() - probe_start) * 1000
        probe_ok = True
    except Exception as e:
        probe_ms = (time.time() - probe_start) * 1000
        probe_ok = False
        probe_error = str(e)

    # Collect all metrics
    metrics = client.get_metrics()

    # Rate limiter
    rl_snapshot = None
    if client.rate_limiter:
        rl_snapshot = client.rate_limiter.snapshot()
        metrics["rate_limiter"] = rl_snapshot

    # Edge tracker
    et_snapshot = None
    if hasattr(client, 'edge_tracker') and client.edge_tracker and client.edge_tracker.total_requests > 0:
        et_snapshot = client.edge_tracker.snapshot()
        metrics["edge_tracker"] = et_snapshot

    metrics["probe_ms"] = round(probe_ms, 1)
    metrics["probe_ok"] = probe_ok

    if json_output:
        print_json_output(metrics)
        return

    # ── Rich text output ─────────────────────────────────────────

    print_header("API Metrics")

    # Probe result
    if probe_ok:
        resp_color = "green" if probe_ms < 2000 else ("yellow" if probe_ms < 5000 else "red")
        print_kv("Probe", c(resp_color, f"{probe_ms:.0f}ms") + " (get_stats)")
    else:
        print_kv("Probe", c("red", f"FAILED ({probe_ms:.0f}ms) — {probe_error}"))
    print()

    # API call stats
    print_section("📊", "API Calls")
    print_kv("Total Calls", metrics["total_api_calls"])
    print_kv("Avg Response", f'{metrics["avg_response_time_s"]:.3f}s')
    print_kv("Min / Max", f'{metrics["min_response_time_s"]:.3f}s / {metrics["max_response_time_s"]:.3f}s')
    print_kv("By HTTP Verb", str(metrics["calls_by_method"]))

    python_methods = metrics.get("calls_by_python_method", {})
    if python_methods:
        print_kv("By Python Method", "")
        for meth, count in sorted(python_methods.items(), key=lambda x: -x[1]):
            print_kv(f"    {meth}", f"{count} calls")
    else:
        print_kv("By Python Method", c("dim", "disabled — pass track_python_methods=True to Client"))

    print_kv("Errors", metrics["total_errors"])


    if metrics["calls_by_endpoint"]:
        print_section("🔗", "Endpoints")
        for ep, count in sorted(metrics["calls_by_endpoint"].items()):
            # Shorten endpoint paths
            short = ep.split("/")[-1] if "/" in ep else ep
            print_kv(f"  {short}", f"{count} calls")

    # Rate limiter
    if rl_snapshot:
        print_section("⏱️", "Rate Limiting")
        print_kv("Calls (last min)", f'{rl_snapshot["calls_last_minute"]} / {rl_snapshot["limit_per_minute"]}')
        print_kv("Calls (last hr)", f'{rl_snapshot["calls_last_hour"]} / {rl_snapshot["limit_per_hour"] or "∞"}')
        print_kv("Calls (today)", f'{rl_snapshot["calls_today"]} / {rl_snapshot["daily_budget"] or "∞"}')
        if rl_snapshot["remaining_daily"] is not None:
            print_kv("Remaining", rl_snapshot["remaining_daily"])
        throttled = c("red", "Yes ⚠️") if rl_snapshot["is_throttled"] else c("green", "No")
        print_kv("Throttled", throttled)
        print_kv("Rate Limits (429)", metrics["total_rate_limits"])
        print_kv("Throttle Waits", metrics["total_throttle_waits"])
        print_kv("Retries", metrics["retry_count"])

    # CloudFront edge tracker
    if et_snapshot:
        print_section("☁️", "CloudFront Edge")
        pop = et_snapshot["current_pop"] or "—"
        print_kv("Current PoP", c("cyan", pop))
        print_kv("CF Requests", et_snapshot["total_cf_requests"])

        # Cache rate
        cache_rate = et_snapshot.get("cache_hit_rate", 0)
        if isinstance(cache_rate, (int, float)):
            cache_str = f"{cache_rate:.0%}"
        else:
            cache_str = str(cache_rate)
        cache_color = "green" if cache_str != "0%" else "yellow"
        print_kv("Cache Hit Rate", c(cache_color, cache_str))

        # PoP distribution
        pop_dist = et_snapshot.get("pop_distribution", {})
        if pop_dist:
            print_kv("PoP Distribution", "")
            for pop_name, cnt in sorted(pop_dist.items(), key=lambda x: -x[1]):
                print_kv(f"  {pop_name}", f"{cnt} requests")

        # Edge transitions
        transitions = et_snapshot.get("edge_transitions", 0)
        if transitions > 0:
            print_kv("⚠️ Edge Transitions", c("yellow", str(transitions)))
            for t in et_snapshot.get("transition_log", []):
                print_kv(f"  {t['from']} → {t['to']}", t.get("at_iso", ""))
        else:
            print_kv("Edge Transitions", c("green", "0 (stable)"))

        # CDN distribution IDs
        dist_ids = et_snapshot.get("distribution_ids", [])
        if dist_ids:
            print_kv("CDN Distribution", ", ".join(d[:16] for d in dist_ids))
    else:
        print_section("☁️", "CloudFront Edge")
        print_warning("No CloudFront data — API may not route through CDN")

    # Uptime
    print()
    print_kv("Session Uptime", f'{metrics["uptime_s"]:.1f}s')

    # Tip
    print()
    print(f"  {c('dim', 'For continuous monitoring: franklinwh-cli monitor -d <minutes>')}")
    print()
