#!/usr/bin/env python3
"""aGate network probe — an evidence-gathering instrument, not a feature prototype.

Step 2 of docs/NETWORK_CONNECTIVITY_DESIGN.md. Its job is to answer the five
open questions that only live hardware can settle, emit a machine-readable
evidence log, and then retire. It is deliberately NOT the implementation of the
network write path — that lands in the library in Phase 2, informed by what this
produces.

    U1  Does the aGate fail over to 4G on its own when WiFi dies?     (no risk)
    U2  Does re-applying identical WiFi credentials work? Timing?     (low)
    U3  Does cmdType 341 opt=1 exist, and is the inferred shape right? (HIGH)
    U4  Does cmdType 317 optType=1 actually force a transport switch?  (medium)
    U5  Does an open network (wifi_Safety 0) accept an empty password? (medium)

Safety model
------------
* Read-only by default. Every write subcommand additionally requires
  --i-understand-writes.
* Unknown write shapes are validated NO-OP FIRST: read the current values, write
  back exactly what was read, confirm nothing changed. This proves the payload
  shape is accepted without touching connectivity. It is what the mobile app
  itself does with cmdType 317.
* Preflight refuses any write unless a transport OTHER THAN THE TARGET has a
  live link, so a failed write cannot strand the gateway.
* Out-of-band LAN check runs independently of the cloud path being modified.
* If the gateway does not return within the deadline, a recovery runbook is
  printed, including the aGate's own AP credentials.

Usage
-----
    python tools/network_probe.py status
    python tools/network_probe.py scan
    python tools/network_probe.py observe --minutes 60          # U1
    python tools/network_probe.py noop 341 --i-understand-writes   # U3 shape
    python tools/network_probe.py noop 317 --i-understand-writes   # U4 shape
    python tools/network_probe.py reapply-wifi --i-understand-writes  # U2
    python tools/network_probe.py recover

Evidence is appended as JSONL to tests/results/network_probe_<ts>.jsonl.
WiFi passwords are ALWAYS redacted. SSIDs are redacted unless --keep-ssids.
Run scripts/check_pii.py over the log before committing it.

RETIREMENT: delete this file once Phase 2 ships and U1-U5 are recorded in
docs/NETWORK_CONNECTIVITY_DESIGN.md. The diagnostic half (preflight, LAN check,
recovery runbook) graduates to `fwh network doctor`; the shape-probing half does
not belong in the library.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from franklinwh_cloud.client import Client, TokenFetcher  # noqa: E402
from franklinwh_cloud.exceptions import (  # noqa: E402
    DeviceTimeoutException,
    FranklinWHError,
    GatewayOfflineException,
)

# Response-only fields the gateway adds to a read but which must NOT be echoed
# back in a write. Confirmed against the cmdType 317 write payload in
# hars/HTTPToolkit_2026-03-20_05-38.har entry 3145, which carried exactly the 20
# commSetPara keys and none of these.
RESPONSE_ONLY_KEYS = ("opt", "result", "reason")

SECRET_KEYS = ("wifi_Pw", "ap_Pw", "password", "token", "email")
SSID_KEYS = ("wifi_SSID", "ap_SSID")

TRANSPORT_TIMEOUT_ERRORS = (DeviceTimeoutException, GatewayOfflineException)


# ── No-op write payload construction ─────────────────────────────────
# Module-level and pure, so tests exercise the same code the probe runs rather
# than a copy of it. These are the safety-critical bits: get `num` or the
# stripped keys wrong and a "no-op" stops being one.

def build_317_noop(read_response):
    """Echo a cmdType 318 read back as an identical cmdType 317 write.

    `num` is the key count of commSetPara — the app's own write carried 20 keys
    and num=20, and the paraType-12 variant carried 17 and num=17. It must be
    computed, never hardcoded, so firmware with extra fields still works.
    """
    para = read_response.get("commSetPara") or {}
    body = {k: v for k, v in para.items() if k not in RESPONSE_ONLY_KEYS}
    return {"optType": 1, "paraType": 6, "commSetPara": body, "num": len(body)}


def build_341_noop(read_response):
    """Echo a cmdType 342 read back as an identical cmdType 341 write.

    The 341 write shape has never been observed on the wire; this is inferred by
    analogy with 311/327/337, which is precisely why it is probed as a no-op
    first.
    """
    body = {k: v for k, v in read_response.items() if k not in RESPONSE_ONLY_KEYS}
    return {"opt": 1, **body}


# ── Evidence log ─────────────────────────────────────────────────────

class Evidence:
    """Append-only JSONL log of every probe action and raw wire exchange."""

    def __init__(self, path, keep_ssids=False):
        self.path = path
        self.keep_ssids = keep_ssids
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._n = 0

    def redact(self, obj):
        """Strip secrets. Passwords always; SSIDs unless explicitly kept."""
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                if k in SECRET_KEYS:
                    out[k] = f"<redacted len={len(v)}>" if isinstance(v, str) else "<redacted>"
                elif k in SSID_KEYS and not self.keep_ssids:
                    out[k] = f"<ssid len={len(v)}>" if isinstance(v, str) else "<ssid>"
                else:
                    out[k] = self.redact(v)
            return out
        if isinstance(obj, list):
            return [self.redact(v) for v in obj]
        return obj

    def write(self, kind, **fields):
        self._n += 1
        rec = {
            "seq": self._n,
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            **self.redact(fields),
        }
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
        return rec


# ── Probe ────────────────────────────────────────────────────────────

class Probe:
    def __init__(self, client, evidence, lan_host=None):
        self.c = client
        self.ev = evidence
        self.lan_host = lan_host
        self._wrap_mqtt()

    def _wrap_mqtt(self):
        """Record every sendMqtt exchange, including failures."""
        original = self.c._mqtt_send

        async def recording(payload):
            try:
                req = json.loads(payload) if isinstance(payload, str) else payload
            except (json.JSONDecodeError, TypeError):
                req = {"unparsed": str(payload)[:400]}
            t0 = time.monotonic()
            try:
                res = await original(payload)
            except Exception as e:
                self.ev.write(
                    "mqtt",
                    cmd=req.get("cmdType"),
                    request=req.get("dataArea"),
                    error=f"{type(e).__name__}: {e}",
                    code=getattr(e, "code", None),
                    elapsed_ms=round((time.monotonic() - t0) * 1000),
                )
                raise
            area = (res.get("result") or {}).get("dataArea")
            try:
                parsed = json.loads(area) if isinstance(area, str) else area
            except (json.JSONDecodeError, TypeError):
                parsed = area
            self.ev.write(
                "mqtt",
                cmd=req.get("cmdType"),
                resp_cmd=(res.get("result") or {}).get("cmdType"),
                request=req.get("dataArea"),
                response=parsed,
                elapsed_ms=round((time.monotonic() - t0) * 1000),
            )
            return res

        self.c._mqtt_send = recording

    # ── raw command access ───────────────────────────────────────────

    async def raw(self, cmd, data_area):
        """Issue a cmdType directly and return the parsed dataArea."""
        payload = self.c._build_payload(cmd, data_area)
        res = await self.c._mqtt_send(payload)
        area = (res.get("result") or {}).get("dataArea")
        return json.loads(area) if isinstance(area, str) else area

    # ── out-of-band verification ─────────────────────────────────────

    def lan_reachable(self, port=502, timeout=2.0):
        """Check the aGate from the LAN, independent of the cloud path.

        Modbus TCP 502 is open on the aGate (see
        docs/troubleshooting/2026-03-21_wifi_dhcp_failure.md). If the cloud path
        goes quiet mid-switch, this still answers "is the device alive?".
        """
        if not self.lan_host:
            return None
        try:
            with socket.create_connection((self.lan_host, port), timeout=timeout):
                return True
        except OSError:
            return False

    # ── preflight ────────────────────────────────────────────────────

    async def preflight(self, target, allow_no_fallback=False):
        """Refuse a write unless a transport other than `target` has a link."""
        state = await self.c.get_network_state()
        survivors = sorted(set(state["linked_transports"]) - {target})
        ok = bool(survivors) or allow_no_fallback
        lan = self.lan_reachable()
        self.ev.write(
            "preflight",
            target=target,
            active=state["active"]["key"],
            linked=state["linked_transports"],
            survivors=survivors,
            lan_reachable=lan,
            passed=ok,
            overridden=bool(not survivors and allow_no_fallback),
        )
        print(f"  active            : {state['active']['label']} ({state['active']['selection']})")
        print(f"  linked transports : {state['linked_transports']}")
        print(f"  survives write    : {survivors or 'NOTHING'}")
        if lan is not None:
            print(f"  LAN {self.lan_host}:502  : {'reachable' if lan else 'unreachable'}")
        if not ok:
            print("\n  PREFLIGHT FAILED — writing to the only linked transport could")
            print("  strand the gateway. Override with --allow-no-fallback only with")
            print("  physical access to the aGate.")
        return ok, state

    # ── verification ─────────────────────────────────────────────────

    async def verify(self, predicate, label, timeout_s=180, interval_s=5.0, stable=2):
        """Poll until `predicate(state)` holds on `stable` consecutive reads.

        Tolerates the connectivity blackout that accompanies a transport change:
        entries 3167/3168/3172/3187 of the 2026-03-20 capture returned no body
        at all while the aGate re-homed its MQTT session.
        """
        deadline = time.monotonic() + timeout_s
        hits = unreachable = polls = 0
        last = None
        print(f"\n  verifying: {label}  (timeout {timeout_s}s, need {stable} consecutive)")
        while time.monotonic() < deadline:
            await asyncio.sleep(interval_s)
            polls += 1
            try:
                last = await self.c.get_network_state()
            except TRANSPORT_TIMEOUT_ERRORS as e:
                unreachable += 1
                hits = 0
                print(f"    [{polls:>3}] unreachable ({type(e).__name__}) — expected mid-switch")
                continue
            except FranklinWHError as e:
                unreachable += 1
                hits = 0
                print(f"    [{polls:>3}] rejected code={e.code} — {e.message}")
                continue
            if predicate(last):
                hits += 1
                print(f"    [{polls:>3}] match {hits}/{stable}  active={last['active']['key']}")
                if hits >= stable:
                    elapsed = round(timeout_s - (deadline - time.monotonic()))
                    self.ev.write("verify", label=label, outcome="confirmed",
                                  polls=polls, unreachable=unreachable, elapsed_s=elapsed)
                    print(f"  CONFIRMED after {polls} polls ({unreachable} unreachable)")
                    return True, last
            else:
                hits = 0
                print(f"    [{polls:>3}] no match   active={last['active']['key']} "
                      f"linked={last['linked_transports']}")
        self.ev.write("verify", label=label, outcome="timeout",
                      polls=polls, unreachable=unreachable, last=last)
        print(f"  TIMEOUT after {polls} polls ({unreachable} unreachable)")
        return False, last


# ── recovery runbook ─────────────────────────────────────────────────

def print_runbook(ap_ssid=None, ap_pw=None, lan_host=None):
    print("\n" + "=" * 68)
    print("  RECOVERY RUNBOOK — the gateway did not come back")
    print("=" * 68)
    print("""
  1. Wait. A transport change can take several minutes; the cloud MQTT
     session re-homes after the interface settles.

  2. Check the aGate from the LAN, bypassing the cloud entirely:""")
    if lan_host:
        print(f"       nc -vz {lan_host} 502        # Modbus TCP")
        print(f"       ping {lan_host}")
    else:
        print("       (no --lan-host given; re-run with it to enable this check)")
    print("""
  3. Join the aGate's own access point directly. It broadcasts even when
     all uplinks are down:""")
    if ap_ssid:
        print(f"       SSID     : {ap_ssid}")
        print(f"       password : {ap_pw if ap_pw else '<see get_wifi_config()>'}")
    else:
        print("       SSID     : AP_<last 9 of gateway serial>")
        print("       password : A02<last 9 of gateway serial>  (pattern; verify)")
    print("""
  4. Reconfigure WiFi from the FranklinWH mobile app's WiFi Configuration
     wizard. This is the documented recovery path and is what resolved the
     2026-03-21 incident (docs/troubleshooting/).

  5. Last resort — power-cycle the aGate, or issue cmdType 315
     {"opt":1,"paraType":1,"reboot":1} if any path still reaches it.
     NEVER populate the `reset` field in that payload: it is almost
     certainly a factory reset.
""")
    print("=" * 68)


# ── subcommands ──────────────────────────────────────────────────────

async def cmd_status(p, args):
    """Report cloud-side state, falling back to the LAN when the cloud is blind.

    The cloud reports the gateway offline whenever the aGate's MQTT session is
    down — which is exactly when an out-of-band answer matters most.
    """
    try:
        state = await p.c.get_network_state()
    except (FranklinWHError, *TRANSPORT_TIMEOUT_ERRORS) as e:
        print(f"Cloud path unavailable: {type(e).__name__}: {e}")
        p.ev.write("status", outcome="cloud_unavailable", error=str(e))
        lan = p.lan_reachable()
        if lan is None:
            print("No --lan-host given, so no independent check is possible.")
            print("Re-run with --lan-host <aGate IP> to distinguish 'aGate down'")
            print("from 'aGate up but cloud link down'.")
        else:
            p.ev.write("lan_check", host=p.lan_host, reachable=lan)
            print(f"LAN {p.lan_host}:502 -> {'REACHABLE' if lan else 'unreachable'}")
            print("  => aGate is alive on the LAN; only its cloud link is down."
                  if lan else "  => aGate is not answering on the LAN either.")
        return 4

    print(json.dumps(state, indent=2))
    p.ev.write("status", state=state)
    lan = p.lan_reachable()
    if lan is not None:
        p.ev.write("lan_check", host=p.lan_host, reachable=lan)
        print(f"\nLAN {p.lan_host}:502 -> {'reachable' if lan else 'unreachable'}")
    return 0


async def cmd_scan(p, args):
    res = await p.c.scan_wifi_networks_ranked(scan_time=args.scan_time)
    p.ev.write("scan", result=res)
    print(f"\n  {'signal':>7}  {'bars':<5} {'sec':<5} {'seen':<5} ssid")
    for n in res["networks"]:
        ssid = n["ssid"] if args.keep_ssids else f"<len {len(n['ssid'])}>"
        print(f"  {n['signal_pct']:>6}%  {'*' * n['signal_bars']:<5} "
              f"{'yes' if n['secured'] else 'OPEN':<5} x{n['seen_count']:<4} {ssid}"
              f"{'' if n['usable'] else '   (weak)'}")
    for w in res["warnings"]:
        print(f"  ! {w}")
    return 0


async def cmd_observe(p, args):
    """U1 — does the aGate change transport on its own?"""
    print(f"Observing for {args.minutes} min at {args.interval}s intervals.")
    print("No writes are issued. Watching for autonomous transport changes.\n")
    deadline = time.monotonic() + args.minutes * 60
    prev = None
    changes = polls = errors = 0
    consecutive = 0
    MAX_CONSECUTIVE = 15  # ~15 min at the default interval before giving up

    while time.monotonic() < deadline:
        polls += 1
        stamp = datetime.now().strftime("%H:%M:%S")
        try:
            state = await p.c.get_network_state()
            cur = (state["active"]["key"], tuple(state["linked_transports"]))
            consecutive = 0
            if prev is None:
                print(f"  {stamp}  baseline: active={cur[0]} linked={list(cur[1])}",
                      flush=True)
                p.ev.write("observe_poll", active=cur[0], linked=list(cur[1]),
                           baseline=True, state=state)
            else:
                p.ev.write("observe_poll", active=cur[0], linked=list(cur[1]))
                if cur != prev:
                    changes += 1
                    print(f"  {stamp}  CHANGE #{changes}: {prev[0]} -> {cur[0]}  "
                          f"linked={list(cur[1])}   (no command was issued)", flush=True)
                    p.ev.write("autonomous_change", frm=prev[0], to=cur[0],
                               linked=list(cur[1]), state=state)
                else:
                    print(f"  {stamp}  active={cur[0]} linked={list(cur[1])}", flush=True)
            prev = cur
        except Exception as e:
            # A long observation MUST survive transient upstream failures. The
            # FranklinWH cloud sits behind CloudFront, which returns HTML error
            # pages (504/502/503) that surface as JSONDecodeError rather than any
            # library exception — one of those previously killed a 60-minute run
            # on its second poll. Catch broadly on purpose; the whole point of
            # this command is to keep watching.
            errors += 1
            consecutive += 1
            print(f"  {stamp}  poll failed ({type(e).__name__}: "
                  f"{str(e)[:90]}) [{consecutive}/{MAX_CONSECUTIVE}]", flush=True)
            p.ev.write("observe_error", error_type=type(e).__name__,
                       error=str(e)[:400], consecutive=consecutive)
            if consecutive >= MAX_CONSECUTIVE:
                print(f"\n  Aborting: {MAX_CONSECUTIVE} consecutive failures — "
                      f"the endpoint or gateway looks genuinely down.", flush=True)
                p.ev.write("observe_summary", minutes=args.minutes, polls=polls,
                           changes=changes, errors=errors, outcome="aborted")
                return 4
        await asyncio.sleep(args.interval)

    print(f"\nObserved {changes} autonomous transport change(s) with zero commands issued.")
    print(f"  polls: {polls}   failed polls: {errors}")
    p.ev.write("observe_summary", minutes=args.minutes, polls=polls,
               changes=changes, errors=errors, outcome="completed")
    return 0


async def cmd_noop(p, args):
    """U3/U4 — validate an unproven write shape without changing anything.

    Reads the current values, writes back exactly what was read, re-reads and
    diffs. A clean result proves the payload shape is accepted by the firmware
    while leaving connectivity untouched.
    """
    cmd = args.cmd
    if cmd == 341:
        target, read_area, wire = "wifi", {"opt": 0}, 341
    elif cmd == 317:
        target, read_area, wire = "wifi", {"optType": 0, "paraType": 6}, 317
    else:
        print(f"No no-op probe defined for cmdType {cmd}")
        return 2

    print(f"NO-OP SHAPE PROBE — cmdType {cmd}")
    print("Writes back exactly what was read. Nothing should change.\n")

    ok, _ = await p.preflight(target, args.allow_no_fallback)
    if not ok:
        return 2
    if not confirm(args, f"issue a NO-OP cmdType {cmd} write"):
        return 2

    before = await p.raw(wire, read_area)

    if cmd == 341:
        write_area = build_341_noop(before)
        body = {k: v for k, v in write_area.items() if k != "opt"}
    else:
        write_area = build_317_noop(before)
        body = write_area["commSetPara"]
        print(f"  commSetPara keys: {len(body)}  -> num={write_area['num']}")

    try:
        ack = await p.raw(wire, write_area)
        print(f"  write ACCEPTED: result={ack.get('result')} reason={ack.get('reason')}")
        p.ev.write("noop_write", cmd=cmd, outcome="accepted", ack=ack)
    except FranklinWHError as e:
        print(f"  write REJECTED: code={e.code} — {e.message}")
        p.ev.write("noop_write", cmd=cmd, outcome="rejected", code=e.code, error=str(e))
        return 1
    except Exception as e:
        print(f"  write FAILED: {type(e).__name__}: {e}")
        p.ev.write("noop_write", cmd=cmd, outcome="error", error=str(e))
        return 1

    await asyncio.sleep(5)
    after = await p.raw(wire, read_area)
    a = {k: v for k, v in (after.get("commSetPara") or after).items()
         if k not in RESPONSE_ONLY_KEYS}
    changed = {k: (body.get(k), a.get(k)) for k in set(body) | set(a)
               if body.get(k) != a.get(k)}
    p.ev.write("noop_result", cmd=cmd, changed=changed)
    if changed:
        print(f"  ! state CHANGED despite a no-op write: {changed}")
    else:
        print("  state unchanged — shape validated, connectivity untouched")
    return 0


async def cmd_reapply_wifi(p, args):
    """U2 — re-apply the WiFi credentials already stored on the aGate.

    Proven safe: this is exactly what the mobile app did at entry 3160 of
    hars/HTTPToolkit_2026-03-20_05-38.har, which succeeded.
    """
    print("RE-APPLY WIFI — writes back the credentials already stored.\n")
    ok, state = await p.preflight("wifi", args.allow_no_fallback)
    if not ok:
        return 2

    cfg = await p.c.get_wifi_config()
    ssid = cfg.get("wifi_ssid")
    if not ssid:
        print("  aGate has no stored SSID — nothing to re-apply.")
        return 2
    print(f"  stored SSID : {ssid if args.keep_ssids else f'<len {len(ssid)}>'}")
    print(f"  AP SSID     : {cfg.get('ap_ssid')}")

    if not confirm(args, f"re-apply the stored WiFi credentials for that SSID"):
        return 2

    t0 = time.monotonic()
    try:
        ack = await p.raw(337, {
            "opt": 1,
            "wifi_SSID": ssid,
            "wifi_Pw": cfg.get("wifi_password") or "",
            "ap_SSID": cfg.get("ap_ssid"),
            "ap_Pw": cfg.get("ap_password"),
        })
        print(f"  write ACCEPTED: result={ack.get('result')} reason={ack.get('reason')}")
        print("  NOTE: this ack means 'config accepted', NOT 'associated'.")
        p.ev.write("reapply_wifi", outcome="accepted", ack=ack)
    except Exception as e:
        print(f"  write FAILED: {type(e).__name__}: {e}")
        p.ev.write("reapply_wifi", outcome="error", error=str(e))
        return 1

    def on_wifi_with_lease(s):
        wifi = next((i for i in s["interfaces"] if i["key"] == "wifi"), {})
        return s["active"]["key"] == "wifi" and wifi.get("ip")

    ok, last = await p.verify(on_wifi_with_lease, "aGate on WiFi with a DHCP lease",
                              timeout_s=args.timeout)
    print(f"\n  elapsed: {round(time.monotonic() - t0)}s")
    if not ok:
        print_runbook(cfg.get("ap_ssid"), cfg.get("ap_password"), p.lan_host)
        return 3
    return 0


async def cmd_recover(p, args):
    try:
        cfg = await p.c.get_wifi_config()
        print_runbook(cfg.get("ap_ssid"), cfg.get("ap_password"), p.lan_host)
    except Exception as e:
        print(f"(could not read AP credentials: {e})")
        print_runbook(None, None, p.lan_host)
    return 0


# ── plumbing ─────────────────────────────────────────────────────────

def confirm(args, action):
    if args.yes:
        return True
    reply = input(f"\n  Proceed to {action}? [y/N] ").strip().lower()
    return reply == "y"


async def build(args, ev):
    from franklinwh_cloud.cli import load_credentials
    email, password, gateway = load_credentials(config_path=args.config)
    if not email or not password:
        print("No credentials found. Use --config /path/to/franklinwh.ini")
        return None
    client = Client(TokenFetcher(email, password), gateway or args.gateway)
    if not client.gateway:
        # The ini need not carry a serial; resolve it from the account. Sending a
        # null gateway yields a 400 "No vpn gateway vpn!" rejection.
        gws = (await client.get_home_gateway_list()).get("result") or []
        if not gws:
            print("No gateways on this account.")
            return None
        client.gateway = gws[0]["id"]
        print(f"Resolved gateway: {client.gateway}")
    return Probe(client, ev, lan_host=args.lan_host)


def main():
    ap = argparse.ArgumentParser(
        description="aGate network probe — evidence gathering for "
                    "docs/NETWORK_CONNECTIVITY_DESIGN.md")
    ap.add_argument("--config", help="path to franklinwh.ini")
    ap.add_argument("--gateway", help="gateway serial (else auto-resolved)")
    ap.add_argument("--lan-host", help="aGate LAN IP for out-of-band checks, e.g. 192.168.0.110")
    ap.add_argument("--evidence", help="evidence JSONL path")
    ap.add_argument("--keep-ssids", action="store_true",
                    help="do not redact SSIDs in output and evidence")
    ap.add_argument("--yes", action="store_true", help="skip confirmation prompts")
    ap.add_argument("--i-understand-writes", dest="writes_ok", action="store_true",
                    help="required for every subcommand that writes to the aGate")
    ap.add_argument("--allow-no-fallback", action="store_true",
                    help="override the preflight. Physical access only.")
    ap.add_argument("--timeout", type=int, default=180, help="verify timeout (s)")

    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="one-shot network state (read-only)")
    s_scan = sub.add_parser("scan", help="ranked WiFi scan (read-only)")
    s_scan.add_argument("--scan-time", type=int, default=10)
    s_obs = sub.add_parser("observe", help="U1: watch for autonomous transport changes")
    s_obs.add_argument("--minutes", type=int, default=60)
    s_obs.add_argument("--interval", type=int, default=60)
    s_noop = sub.add_parser("noop", help="U3/U4: validate a write shape without changing state")
    s_noop.add_argument("cmd", type=int, choices=[317, 341])
    sub.add_parser("reapply-wifi", help="U2: re-apply the stored WiFi credentials")
    sub.add_parser("recover", help="print the recovery runbook")

    args = ap.parse_args()

    WRITE_COMMANDS = {"noop", "reapply-wifi"}
    if args.command in WRITE_COMMANDS and not args.writes_ok:
        print(f"'{args.command}' writes to the aGate. Re-run with --i-understand-writes.")
        return 2

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = args.evidence or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tests", "results", f"network_probe_{ts}.jsonl")
    ev = Evidence(path, keep_ssids=args.keep_ssids)
    print(f"Evidence log: {path}\n")

    handlers = {
        "status": cmd_status, "scan": cmd_scan, "observe": cmd_observe,
        "noop": cmd_noop, "reapply-wifi": cmd_reapply_wifi, "recover": cmd_recover,
    }

    async def run():
        p = await build(args, ev)
        if p is None:
            return 2
        try:
            return await handlers[args.command](p, args)
        except GatewayOfflineException as e:
            # The single most likely failure for this tool, and the one it must
            # handle most gracefully — a probe that tracebacks when the gateway
            # is unreachable is useless precisely when it is needed.
            print(f"\nGateway is offline (cloud says: {e}).")
            p.ev.write("aborted", reason="gateway_offline", error=str(e))
            lan = p.lan_reachable()
            if lan is not None:
                p.ev.write("lan_check", host=p.lan_host, reachable=lan)
                print(f"LAN {p.lan_host}:502 -> "
                      f"{'REACHABLE — cloud link is down, not the aGate' if lan else 'unreachable'}")
            print("\nNothing was written. Re-run when the aGate is back online,")
            print("or use `recover` for the runbook.")
            return 4
        except (DeviceTimeoutException, FranklinWHError) as e:
            print(f"\nAborted: {type(e).__name__}: {e}")
            p.ev.write("aborted", reason=type(e).__name__, error=str(e),
                       code=getattr(e, "code", None))
            return 4

    try:
        rc = asyncio.run(run())
    except KeyboardInterrupt:
        print("\nInterrupted. Evidence log retained.")
        rc = 130
    print(f"\nEvidence written to {path}")
    if not args.keep_ssids:
        print("Passwords redacted; SSIDs redacted. Run scripts/check_pii.py before committing.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
