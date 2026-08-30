"""Network command — see the aGate's connection, and put it back on WiFi.

Phase 2 of docs/NETWORK_CONNECTIVITY_DESIGN.md; step P2-6 of
docs/NETWORK_PHASE2_IMPLEMENTATION_PLAN.md.

Usage:
    franklinwh-cli network status                 # what is it connected on?
    franklinwh-cli network status --watch 5       # live view during a cutover
    franklinwh-cli network scan                   # visible networks, by signal
    franklinwh-cli network set-wifi --ssid X      # join X (prompts for password)
    franklinwh-cli network set-wifi --ssid X --use-stored   # re-assert a known net

The set-wifi case that matters: the aGate always falls back to 4G when local
connectivity drops but does not reliably come back, so it strands itself on
cellular. ``--use-stored`` puts it back on the network it already knows without
needing the password at all.

Exit codes: 0 success · 2 preflight refused · 3 verify timeout · 4 gateway offline
"""

import asyncio
import os
import sys

from franklinwh_cloud.cli_output import (
    c, print_error, print_header, print_json_output, print_kv, print_section,
    print_success, print_warning,
)
from franklinwh_cloud.exceptions import GatewayOfflineException

EXIT_OK = 0
EXIT_PREFLIGHT_REFUSED = 2
EXIT_VERIFY_TIMEOUT = 3
EXIT_GATEWAY_OFFLINE = 4


def _bars(pct):
    """Render a signal percentage as a four-step bar, plus the number."""
    if pct is None:
        return "     —"
    filled = min(4, max(0, (int(pct) + 24) // 25))
    return "▁▂▄▆█"[filled] * 1 + f" {int(pct):3d}%"


def _fmt_age(seconds):
    """Human-readable age. Warranty questions are asked in hours and days."""
    if seconds is None:
        return "unknown"
    s = int(seconds)
    if s < 90:
        return f"{s}s"
    if s < 5400:
        return f"{s // 60}m"
    if s < 172800:
        return f"{s // 3600}h"
    return f"{s // 86400}d"


def _render_heartbeat(hb):
    """Cloud-contact history — the part a single reading cannot show."""
    if not hb or not hb.get("last_success"):
        if hb and hb.get("last_outcome") == "failure":
            print_warning(
                f"No successful gateway contact on record, and the last "
                f"{hb.get('consecutive_failures')} attempt(s) failed."
            )
        return

    offline = hb.get("offline_for_s")
    if hb.get("last_outcome") == "failure" and offline:
        # This is the warranty-relevant state, and the only one a single
        # reading could never have told you.
        print_error(
            f"No cloud contact for {_fmt_age(offline)} "
            f"({hb['consecutive_failures']} consecutive failures). "
            f"Last confirmed: {hb['last_success']}"
        )
    else:
        print_kv("Last contact", f"{hb['last_success']}   ({_fmt_age(offline)} ago)")


def _render_status(state, heartbeat=None):
    """The section 6 terminal sketch."""
    print_header(f"aGate Network — {state.get('gateway_id')}")

    active = state.get("active") or {}
    print_section("🌐", "Active connection")
    # Never "configured primary": the aGate selects for itself, and 17 of 19
    # observed transport changes followed no command at all (gotcha G9).
    label = active.get("label") or "unknown"
    print_kv("Transport", f"{label}  (selected by the gateway, not configured)")
    if active.get("ip"):
        print_kv("Address", f"{active['ip']}   gw {active.get('gateway') or '—'}"
                            f"   dns {active.get('dns') or '—'}")

    cloud = state.get("cloud") or {}
    # Lead with the evidenced claim, not the self-report. This reading reached
    # us through the cloud, so the cloud path demonstrably works.
    if cloud.get("gateway_reachable"):
        print_kv("Cloud", c("green", "✓ reachable")
                          + "   (this reading arrived through it)")
    # The gateway's own flags follow, clearly marked as unreliable rather than
    # printed as bare crosses that read as "gateway offline".
    # DEF-NET-STATUS-CLOUD-CAVEAT.
    print_kv("Gateway self-report",
             f"AWS {'✓' if cloud.get('aws_connected') else '✗'}"
             f"   Internet {'✓' if cloud.get('internet') else '✗'}"
             f"   routerStatus={cloud.get('router_status_raw')} (raw)")
    if not (cloud.get("aws_connected") and cloud.get("internet")):
        print_warning(
            "Self-report disagrees with the evidence above and has been "
            "observed contradicting reality (design 2.5a). Do not act on it."
        )

    local = state.get("local") or {}
    if local.get("probed"):
        if local.get("reachable"):
            print_kv("Local", c("green", f"✓ answering on :{local['port']}")
                              + f"   ({local.get('host')})")
        else:
            # Not a fault on its own — you may simply not be on its LAN.
            print_kv("Local", c("dim", "✗ no answer on :9000 or :22")
                              + f"   ({local.get('host')})")
            print_warning(
                "A local miss is only meaningful from the gateway's own LAN. "
                "From anywhere else it says nothing about the gateway."
            )

    print_section("🔌", "Interfaces")
    for iface in state.get("interfaces") or []:
        signal = iface.get("signal_pct")
        raw = iface.get("signal_raw")
        sig = _bars(signal) if signal is not None else (
            f"  raw {raw}" if raw is not None else "")
        flags = []
        if iface.get("is_active"):
            flags.append(c("green", "← active"))
        if iface.get("available"):
            flags.append("available")
        if iface.get("link_shared"):
            # DEF-ETH-LINK-SHARED-FLAG — one firmware status covers both ports.
            flags.append(c("dim", "link flag shared with the other Eth port"))
        print_kv(
            iface["key"],
            f"{'enabled ' if iface.get('enabled') else 'disabled'} "
            f"{'link up  ' if iface.get('link') else 'link down'} "
            f"{(iface.get('ip') or '—'):<16}{sig}  {'  '.join(flags)}",
        )

    _render_heartbeat(heartbeat)

    fallbacks = [t for t in (state.get("available_transports") or [])
                 if t != (active.get("key"))]
    print_section("🛟", "Write safety")
    if fallbacks:
        print_success(f"Fallback available: {', '.join(fallbacks)}")
    else:
        print_warning("No fallback — a network write could strand this gateway.")


def _heartbeat_of(client):
    """Best-effort: a client built without a heartbeat must still render."""
    getter = getattr(client, "get_gateway_heartbeat", None)
    return getter() if getter else None


async def _cmd_status(client, *, json_output, watch, probe_local=False):
    if not watch:
        state = await client.get_network_state(probe_local=probe_local)
        hb = _heartbeat_of(client)
        if json_output:
            print_json_output({**state, "heartbeat": hb})
        else:
            _render_status(state, hb)
        return EXIT_OK

    # --watch is the natural "did it work" view during a cutover, so an
    # unreachable gateway must render as transitioning, not as an error: the
    # aGate genuinely disappears mid-switch (gotcha G8).
    try:
        while True:
            try:
                client._invalidate_network_cache()
                state = await client.get_network_state(probe_local=probe_local)
                print("\033[2J\033[H", end="")
                _render_status(state, _heartbeat_of(client))
            except Exception as e:
                print(c("yellow", f"⟳ transitioning — gateway unreachable ({type(e).__name__})"))
            await asyncio.sleep(watch)
    except KeyboardInterrupt:
        return EXIT_OK


async def _cmd_scan(client, *, json_output, min_rssi, scan_time, show_all):
    result = await client.scan_wifi_networks_ranked(
        scan_time=scan_time, min_rssi=0 if show_all else min_rssi,
    )
    if json_output:
        print_json_output(result)
        return EXIT_OK

    print_header("WiFi scan")
    for w in result.get("networks") or []:
        mark = "🔒" if w.get("secured") else "🔓"
        usable = "" if w.get("usable") else c("yellow", "  (too weak to rely on)")
        print_kv(w["ssid"], f"{_bars(w.get('signal_pct'))}  {mark}{usable}")
    for warn in result.get("warnings") or []:
        print_warning(warn)
    if not result.get("networks"):
        print_warning("No networks returned. Scans can take ~12s; try again.")
    return EXIT_OK


def _resolve_password(args):
    """Get the passphrase without putting it in shell history or a log."""
    if args.use_stored:
        return None                      # switch_to_wifi reads it off the aGate
    if args.password:
        print_warning(
            "--password is visible in your shell history and process list. "
            "Prefer --use-stored, the FWH_WIFI_PASSWORD environment variable, "
            "or the interactive prompt."
        )
        return args.password
    env = os.environ.get("FWH_WIFI_PASSWORD")
    if env:
        return env
    import getpass
    return getpass.getpass(f"Password for {args.ssid}: ")


async def _cmd_set_wifi(client, args):
    password = _resolve_password(args)

    if not args.yes:
        # Show the preflight before asking, so the answer is informed.
        state = await client.get_network_state()
        from franklinwh_cloud.mixins.network import network_write_preflight
        pre = network_write_preflight(
            state, "wifi", allow_no_fallback=args.allow_no_fallback,
        )
        print_header("Preflight")
        print_kv("Target", f"WiFi — SSID {args.ssid}")
        print_kv("Active now", (state.get("active") or {}).get("label"))
        print_kv("Would survive", ", ".join(pre["fallbacks"]) or c("red", "nothing"))
        for reason in pre["reasons"]:
            print_error(reason)
        print_warning(
            "This rewrites the gateway's WiFi configuration. An accepted write "
            "is not a working link — a wrong password is accepted too."
        )
        answer = input("Proceed? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted.")
            return EXIT_PREFLIGHT_REFUSED

    result = await client.switch_to_wifi(
        args.ssid,
        password,
        confirm=True,
        verify=not args.no_verify,
        timeout_s=args.timeout,
        min_rssi=args.min_rssi,
        allow_no_fallback=args.allow_no_fallback,
        allow_weak_signal=args.allow_weak_signal,
        trust_ethernet=getattr(args, "trust_ethernet", False),
    )

    if args.json:
        print_json_output(result)
    else:
        _render_switch(result)

    if not result["preflight"]["passed"]:
        return EXIT_PREFLIGHT_REFUSED
    if result["verification"]["state"] == "timeout":
        return EXIT_VERIFY_TIMEOUT
    return EXIT_OK


def _render_switch(result):
    pre = result["preflight"]
    print_header("Switch to WiFi")
    print_kv("SSID", result["requested"]["ssid"])
    print_kv("Password", f"from {result['requested']['password_source']}")

    print_section("🛟", "Preflight")
    if pre["passed"]:
        print_success(f"Fallback if this fails: {pre['fallback']}")
        if pre.get("target_signal_pct") is not None:
            print_kv("Target signal", _bars(pre["target_signal_pct"]))
    else:
        for reason in pre["reasons"]:
            print_error(reason)
        print_warning("No write was sent.")
        return
    for over in pre.get("overrides") or []:
        print_warning(f"OVERRIDDEN — {over}")

    ack = result.get("write_ack") or {}
    print_section("📡", "Write")
    print_kv("cmdType 338", f"result={ack.get('result')} reason={ack.get('reason')}")
    print_warning("Accepted by the aGate. That is not the same as connected.")

    v = result["verification"]
    print_section("🔎", "Verification")
    if v["state"] == "connected":
        after = v.get("after") or {}
        print_success(
            f"Connected in {v['elapsed_s']}s over {v['polls']} polls "
            f"({v['unreachable_polls']} unreachable) — {after.get('ip')}"
        )
    elif v["state"] == "skipped":
        print_warning(f"Skipped ({v.get('reason')}). The link is unconfirmed.")
    else:
        print_error(f"Not confirmed after {v['elapsed_s']}s.")
        print_kv("Last seen", v.get("last_known"))
        print_warning(v.get("recovery_hint", ""))


async def run(client, args):
    """Dispatch a ``network`` subcommand. Returns a process exit code."""
    action = getattr(args, "network_action", None) or "status"
    try:
        if action == "status":
            return await _cmd_status(
                client, json_output=args.json,
                watch=getattr(args, "watch", None),
                probe_local=getattr(args, "probe_local", False),
            )
        if action == "scan":
            return await _cmd_scan(
                client, json_output=args.json,
                min_rssi=args.min_rssi, scan_time=args.scan_time,
                show_all=args.all,
            )
        if action == "set-wifi":
            return await _cmd_set_wifi(client, args)
    except GatewayOfflineException as e:
        print_error(f"Gateway offline: {e}")
        return EXIT_GATEWAY_OFFLINE

    print_error(f"Unknown network action: {action}")
    return 1


def register(subs):
    """Add the ``network`` subparser tree to the CLI."""
    p = subs.add_parser(
        "network", aliases=["net"],
        help="Inspect the aGate's connection, or put it back on WiFi",
    )
    actions = p.add_subparsers(dest="network_action")

    st = actions.add_parser("status", help="What is the aGate connected on?")
    st.add_argument("--watch", type=int, nargs="?", const=5, metavar="SECS",
                    help="Refresh every SECS seconds (default 5)")
    st.add_argument("--probe-local", action="store_true",
                    help="Also check whether the aGate answers on the LAN "
                         "(TCP 9000, else 22). Distinguishes 'gateway alive, "
                         "cloud path broken' from 'gateway down'. Only "
                         "meaningful from the gateway's own network.")

    sc = actions.add_parser("scan", help="List visible WiFi networks by signal")
    sc.add_argument("--min-rssi", type=int, default=0, metavar="PCT",
                    help="Hide networks below this signal percentage")
    sc.add_argument("--scan-time", type=int, default=10, metavar="SECS",
                    help="wifi_ScanTime value (default 10)")
    sc.add_argument("--all", action="store_true",
                    help="Include everything, however weak")

    sw = actions.add_parser(
        "set-wifi",
        help="Join a WiFi network, or re-assert one the aGate already knows",
    )
    sw.add_argument("--ssid", required=True, help="Network to join")
    pw = sw.add_mutually_exclusive_group()
    pw.add_argument("--password", help="Passphrase (visible in shell history)")
    pw.add_argument("--use-stored", action="store_true",
                    help="Reuse the password already on the aGate. Only valid "
                         "for the SSID it currently stores — which is exactly "
                         "the case when it has stranded itself on 4G.")
    sw.add_argument("--yes", "-y", action="store_true", help="Skip the confirmation")
    sw.add_argument("--no-verify", action="store_true",
                    help="Do not poll to confirm the link came up")
    sw.add_argument("--timeout", type=int, default=180, metavar="SECS",
                    help="Verification deadline (default 180)")
    sw.add_argument("--min-rssi", type=int, default=30, metavar="PCT",
                    help="Refuse a target weaker than this (default 30)")
    sw.add_argument("--allow-no-fallback", action="store_true",
                    help="DANGEROUS: write even when nothing else could take "
                         "over if it fails")
    sw.add_argument("--allow-weak-signal", action="store_true",
                    help="Write even if the target is weak or not in the scan")
    sw.add_argument("--trust-ethernet", action="store_true",
                    help="Count an idle Ethernet port as a fallback. Off by "
                         "default: one aGate port is reserved for "
                         "FranklinWH-internal use and may hold an address "
                         "while having no route to the cloud.")
    return p
