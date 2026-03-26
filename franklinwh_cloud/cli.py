#!/usr/bin/env python3
"""franklinwh-cli — Command-line interface for the FranklinWH Cloud API.

Usage:
    franklinwh-cli status                  # live system overview
    franklinwh-cli monitor                 # real-time dashboard (refreshes every 30s)
    franklinwh-cli monitor -i 10           # refresh every 10 seconds
    franklinwh-cli monitor -d 5 --compact  # compact mode for 5 minutes
    franklinwh-cli diag                    # diagnostic report for support
    franklinwh-cli discover                # device enumeration
    franklinwh-cli mode                    # current operating mode
    franklinwh-cli tou                     # TOU schedule info
    franklinwh-cli raw <method>            # direct API passthrough
    franklinwh-cli metrics                 # API call metrics

Credentials are loaded from franklinwh_cloud.ini (or --email/--password/--gateway).
"""

import argparse
import asyncio
import configparser
import os
import sys

from franklinwh_cloud.client import Client
from franklinwh_cloud.auth import PasswordAuth, LOGIN_TYPE_USER, LOGIN_TYPE_INSTALLER
from franklinwh_cloud.exceptions import FranklinWHTimeoutError
from franklinwh_cloud.cli_output import (
    configure_logging, disable_color, print_error, print_warning,
    print_header, print_kv, print_json_output, print_section,
    TRACEABLE_MODULES,
)


__version__ = "2.0.0"


# ── Credential loading ───────────────────────────────────────────────

def load_credentials(config_path: str | None = None,
                     email: str | None = None,
                     password: str | None = None,
                     gateway: str | None = None):
    """Load credentials with priority: CLI args > franklinwh.ini.

    Returns (email, password, gateway) tuple.
    """
    # CLI args take priority if all provided
    if email and password and gateway:
        return email, password, gateway

    # Try .ini file
    ini_paths = [config_path] if config_path else ["franklinwh.ini", "franklinwh/franklinwh.ini"]
    for ini_path in ini_paths:
        if ini_path and os.path.exists(ini_path):
            config = configparser.ConfigParser()
            config.read(ini_path)
            try:
                ini_email = config.get("energy.franklinwh.com", "email")
                ini_password = config.get("energy.franklinwh.com", "password")
                ini_gateway = config.get("gateways.enabled", "serialno", fallback=None)
                return (email or ini_email, password or ini_password, gateway or ini_gateway)
            except (configparser.NoSectionError, configparser.NoOptionError):
                try:
                    ini_email = config.get("FranklinWH", "email")
                    ini_password = config.get("FranklinWH", "password")
                    ini_gateway = config.get("FranklinWH", "gateway", fallback=None)
                    return (email or ini_email, password or ini_password, gateway or ini_gateway)
                except (configparser.NoSectionError, configparser.NoOptionError):
                    pass

    # Fall back to env vars
    return (
        email or os.environ.get("FRANKLIN_USERNAME", ""),
        password or os.environ.get("FRANKLIN_PASSWORD", ""),
        gateway or os.environ.get("FRANKLIN_GATEWAY", ""),
    )


# ── Argument parsing ─────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="franklinwh-cli",
        description="Command-line interface for the FranklinWH Cloud API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    # Global options
    auth = parser.add_argument_group("credentials")
    auth.add_argument("--config", "-c", metavar="PATH", help="Path to franklinwh.ini config file")
    auth.add_argument("--email", "-e", metavar="EMAIL", help="FranklinWH account email")
    auth.add_argument("--password", "-p", metavar="PASS", help="FranklinWH account password")
    auth.add_argument("--gateway", "-g", metavar="SN", help="aGate serial number")
    auth.add_argument("--installer", action="store_true",
                      help="Use installer account login (LOGIN_TYPE_INSTALLER). Default: homeowner account")

    # Output options
    output = parser.add_argument_group("output")
    output.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    output.add_argument("--no-color", action="store_true", help="Disable ANSI colour output")

    # Debug options
    debug = parser.add_argument_group("debug")
    debug.add_argument("-v", "--verbose", action="count", default=0,
                       help="Increase verbosity (-v info, -vv debug, -vvv trace)")
    debug.add_argument("--trace", metavar="MODULES",
                       help=f"Enable debug for specific modules (comma-sep: {','.join(TRACEABLE_MODULES)},client,all)")
    debug.add_argument("--api-trace", action="store_true",
                       help="Show per-call API trace with timing")
    debug.add_argument("--log-file", metavar="PATH",
                       help="Write debug output to file")

    # Subcommands
    subs = parser.add_subparsers(dest="command", help="Command to execute")

    # status
    sub_status = subs.add_parser("status", aliases=["st"],
                                 help="Live system overview (power, SOC, mode, weather, metrics)")

    # discover
    sub_discover = subs.add_parser("discover", aliases=["disc"],
                                    help="Gateway, device, warranty, and accessory enumeration")
    sub_discover.add_argument("-v", "--verbose", action="count", default=0,
                              help="Verbosity: -v (medium), -vv (pedantic)")

    # mode
    sub_mode = subs.add_parser("mode", help="Get or set operating mode")
    sub_mode.add_argument("--set", dest="set_mode", metavar="MODE",
                          help="Set mode (tou, self_consumption, emergency_backup, or 1/2/3)")
    sub_mode.add_argument("--soc", type=int, metavar="PCT",
                          help="Set SOC percentage (used with --set)")

    # tou
    sub_tou = subs.add_parser("tou", help="Time-of-Use schedule inspection and control")
    sub_tou.add_argument("--dispatch", action="store_true",
                         help="Show full dispatch detail including strategies")
    sub_tou.add_argument("--set", dest="set_mode", metavar="MODE",
                         help="Set TOU dispatch (GRID_CHARGE, GRID_EXPORT, SELF, HOME, STANDBY, SOLAR, CUSTOM)")
    sub_tou.add_argument("--start", metavar="HH:MM",
                         help="Start time for --set window (e.g. 11:30)")
    sub_tou.add_argument("--end", metavar="HH:MM",
                         help="End time for --set window (e.g. 14:30)")
    sub_tou.add_argument("--default", dest="default_mode", metavar="MODE", default=None,
                         help="Dispatch mode for times outside --start/--end (required with --start/--end)")
    sub_tou.add_argument("--active-only", action="store_true",
                         help="Truncate --price output to only active exchange rates (ideal for scripts)")
    sub_tou.add_argument("--file", dest="schedule_file", metavar="PATH",
                         help="JSON schedule file for --set CUSTOM")
    sub_tou.add_argument("--rates-file", dest="rates_file", metavar="PATH",
                         help="JSON file with pricing rates (peak, off_peak, sell_peak, ...)")
    sub_tou.add_argument("--season", metavar="NAME",
                         help="Season name (e.g. 'Summer'). Use with --months.")
    sub_tou.add_argument("--months", metavar="M,M,...",
                         help="Comma-separated months for --season (e.g. '10,11,12,1,2,3')")
    sub_tou.add_argument("--day-type", dest="day_type", metavar="TYPE",
                         choices=["everyday", "weekday", "weekend"],
                         help="Day type: everyday (default), weekday, weekend")
    sub_tou.add_argument("--next", dest="show_next", action="store_true",
                         help="Show current and next dispatch with remaining time")
    sub_tou.add_argument("--price", dest="show_price", action="store_true",
                         help="Show the current TOU pricing tier, wave type, and rates")
    sub_tou.add_argument("--multi-season", dest="multi_season_file", metavar="FILE",
                         help="Load and apply a multi-season/multi-day-type schedule from JSON file")
    sub_tou.add_argument("--wait", dest="wait_confirm", action="store_true",
                         help="After --set, poll until dispatch is confirmed applied (up to 90s)")

    # raw
    sub_raw = subs.add_parser("raw", help="Direct API method passthrough")
    sub_raw.add_argument("method", nargs="?", default="help",
                         help="API method name (use 'help' to list all)")
    sub_raw.add_argument("values", nargs="*",
                         help="Arguments to pass to the method")
    sub_raw.add_argument("--headers", "-H", action="store_true",
                         help="Show HTTP response headers")
    sub_raw.add_argument("--timings", "-T", action="store_true",
                         help="Show request timing and CloudFront edge info")

    # metrics
    subs.add_parser("metrics", help="Show API call metrics from current session")

    # monitor
    sub_monitor = subs.add_parser("monitor", aliases=["mon"],
                                   help="Real-time battery dashboard (auto-refresh, Ctrl+C to exit)")
    sub_monitor.add_argument("-i", "--interval", type=int, default=30, metavar="SECS",
                             help="Refresh interval in seconds (default: 30)")
    sub_monitor.add_argument("-d", "--duration", type=int, default=None, metavar="MINS",
                             help="Run for N minutes then stop (default: until Ctrl+C)")
    sub_monitor.add_argument("--compact", action="store_true",
                             help="Single-line output per poll (no screen clearing)")

    # accessories
    sub_acc = subs.add_parser("accessories", aliases=["acc"],
                              help="Accessory inventory, status, and device info (Smart Circuits, V2L, Generator)")
    sub_acc.add_argument("--power", action="store_true",
                         help="Include live power data for active accessories (extra MQTT call)")

    # smart circuits
    sub_sc = subs.add_parser("sc", aliases=["smart-circuits"],
                             help="Detailed Smart Circuit configuration and control")
    sub_sc.add_argument("--on", type=int, metavar="CIRCUIT", help="Turn Circuit 1/2/3 ON")
    sub_sc.add_argument("--off", type=int, metavar="CIRCUIT", help="Turn Circuit 1/2/3 OFF")
    sub_sc.add_argument("--cutoff", type=int, metavar="CIRCUIT", help="Enable SOC auto cut-off for Circuit 1/2/3")
    sub_sc.add_argument("--disable-cutoff", type=int, metavar="CIRCUIT", help="Disable SOC auto cut-off for Circuit 1/2/3")
    sub_sc.add_argument("--soc", type=int, metavar="PCT", help="SOC limit (0-100) for --cutoff")
    sub_sc.add_argument("--load-limit", type=int, metavar="CIRCUIT",
                        help="Configure the continuous Load Limit in amps for a specific circuit")
    sub_sc.add_argument("--amps", type=int, metavar="A",
                        help="The maximum amperage limit for --load-limit (0 to reset)")

    # diag
    subs.add_parser("diag", aliases=["diagnostic"],
                    help="Diagnostic report — system, auth, device, power, API health")

    # bms
    subs.add_parser("bms", aliases=["battery"],
                    help="Battery Management System — cell telemetry, pack health, bus topology")

    # support
    sub_support = subs.add_parser("support", aliases=["snapshot"],
                                  help="System snapshot for troubleshooting — export, redact, compare")
    sub_support.add_argument("--save", "-s", action="store_true",
                             help="Save snapshot to timestamped JSON file")
    sub_support.add_argument("--redact", "-r", nargs="?", const="partial", choices=["partial", "full"],
                             help="Redact PII (partial=mask, full=remove). Default: partial")
    sub_support.add_argument("--label", "-l", metavar="TAG",
                             help="Label the snapshot (e.g. 'pre-setup', 'post-outage')")
    sub_support.add_argument("--analyze", "-a", action="store_true",
                             help="Run connectivity and WiFi health analysis")
    sub_support.add_argument("--compare", dest="compare_file", metavar="FILE",
                             help="Compare current state against a previous snapshot file")
    sub_support.add_argument("--scope", choices=["all", "network", "software", "power"],
                             default="all", help="Scope for --compare (default: all)")
    sub_support.add_argument("--nettest", "-t", action="store_true",
                             help="Run hop-by-hop network connectivity test")
    sub_support.add_argument("--interval", type=int, default=0, metavar="SECS",
                             help="Repeat nettest every N seconds (0=single run)")
    sub_support.add_argument("--duration", type=int, default=0, metavar="SECS",
                             help="Total duration for interval testing (0=until Ctrl+C)")
    sub_support.add_argument("--record", metavar="FILE",
                             help="Save nettest results to JSON file")
    sub_support.add_argument("--fem-url", metavar="URL",
                             help="FEM URL for Tier 2 tests (default: auto-discover)")
    sub_support.add_argument("--bms", action="store_true",
                             help="Include BMS battery test (extra sendMqtt load — opt-in)")


    # fetch (arbitrary endpoint)
    sub_fetch = subs.add_parser("fetch", help="Arbitrary GET/POST to any API endpoint")
    sub_fetch.add_argument("http_method", choices=["GET", "POST", "get", "post"],
                           help="HTTP method")
    sub_fetch.add_argument("path", help="API path (e.g. /hes-gateway/common/getPowerCapConfigList)")
    sub_fetch.add_argument("--data", "-d", metavar="JSON",
                           help="Inline JSON POST body")
    sub_fetch.add_argument("--data-file", "-f", metavar="PATH",
                           help="JSON file for POST body (use '-' for stdin)")
    sub_fetch.add_argument("--params", "-P", nargs="*", metavar="KEY=VAL",
                           help="Query parameters (key=value pairs)")
    sub_fetch.add_argument("--output", "-o", metavar="PATH",
                           help="Save response to JSON file")
    sub_fetch.add_argument("--no-gateway", action="store_true",
                           help="Don't auto-inject gatewayId into payload")
    sub_fetch.add_argument("--inject-user", action="store_true",
                           help="Auto-inject userId into payload")

    return parser


# ── Main ─────────────────────────────────────────────────────────────

async def async_main():
    """Async entrypoint."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Output config
    if args.no_color:
        disable_color()

    # Debug config
    trace_modules = args.trace.split(",") if args.trace else None
    configure_logging(
        verbosity=args.verbose,
        trace_modules=trace_modules,
        api_trace=args.api_trace,
        log_file=args.log_file,
    )

    # Load credentials
    email, password, gateway = load_credentials(
        config_path=args.config,
        email=args.email,
        password=args.password,
        gateway=args.gateway,
    )

    if not email or not password:
        print_error("No credentials found. Provide --email/--password, set up franklinwh.ini, or set FRANKLIN_USERNAME/FRANKLIN_PASSWORD env vars.")
        sys.exit(1)

    # Connect
    try:
        login_type = LOGIN_TYPE_INSTALLER if getattr(args, 'installer', False) else LOGIN_TYPE_USER
        fetcher = PasswordAuth(email, password, login_type=login_type)
        await fetcher.get_token()
    except Exception as e:
        print_error(f"Login failed: {e}")
        sys.exit(1)

    # Gateway discovery if not specified
    if not gateway:
        info = fetcher.info or {}
        gateway_list = info.get("gatewayList", [])
        if not gateway_list:
            # Try get_home_gateway_list via a temporary client
            temp_client = Client(fetcher, "")
            try:
                res = await temp_client.get_home_gateway_list()
                gateway_list = res.get("result", [])
            except Exception:
                pass
        if gateway_list:
            gateway = gateway_list[0].get("sn", gateway_list[0].get("id", ""))
            print_warning(f"No gateway specified, using: {gateway}")
        else:
            print_error("No gateway found. Specify --gateway or add serialno to franklinwh.ini")
            sys.exit(1)

    client = Client(fetcher, gateway)

    # Dispatch to command
    try:
        match args.command:
            case "status" | "st":
                from franklinwh_cloud.cli_commands import status
                await status.run(client, json_output=args.json)

            case "discover" | "disc":
                from franklinwh_cloud.cli_commands import discover
                tier = min(args.verbose + 1, 3)  # 0→1, 1→2, 2+→3
                await discover.run(client, json_output=args.json, tier=tier)

            case "mode":
                from franklinwh_cloud.cli_commands import mode
                await mode.run(client, json_output=args.json,
                               set_mode=args.set_mode, soc=args.soc)

            case "tou":
                from franklinwh_cloud.cli_commands import tou
                await tou.run(client, json_output=args.json,
                              show_dispatch=args.dispatch,
                              set_mode=getattr(args, 'set_mode', None),
                              start=getattr(args, 'start', None),
                              end=getattr(args, 'end', None),
                              default_mode=getattr(args, 'default_mode', None),
                              schedule_file=getattr(args, 'schedule_file', None),
                              rates_file=getattr(args, 'rates_file', None),
                              season_name=getattr(args, 'season', None),
                              season_months=getattr(args, 'months', None),
                              day_type_str=getattr(args, 'day_type', None),
                              wait_confirm=getattr(args, 'wait_confirm', False),
                              show_next=getattr(args, 'show_next', False),
                              show_price=getattr(args, 'show_price', False),
                              multi_season_file=getattr(args, 'multi_season_file', None),
                              active_only=getattr(args, 'active_only', False))

            case "raw":
                from franklinwh_cloud.cli_commands import raw
                await raw.run(client, args.method, args.values,
                              json_output=args.json,
                              show_headers=getattr(args, 'headers', False),
                              show_timings=getattr(args, 'timings', False))

            case "metrics":
                from franklinwh_cloud.cli_commands import metrics
                await metrics.run(client, json_output=args.json)

            case "monitor" | "mon":
                from franklinwh_cloud.cli_commands import monitor
                await monitor.run(client, json_output=args.json,
                                  interval=args.interval,
                                  duration=args.duration,
                                  compact=args.compact)

            case "accessories" | "acc":
                from franklinwh_cloud.cli_commands import accessories
                await accessories.run(client, json_output=args.json,
                                      show_power=args.power)

            case "sc" | "smart-circuits":
                from franklinwh_cloud.cli_commands import sc
                await sc.run(client, json_output=args.json,
                             turn_on=getattr(args, 'on', None),
                             turn_off=getattr(args, 'off', None),
                             cutoff=getattr(args, 'cutoff', None),
                             disable_cutoff=getattr(args, 'disable_cutoff', None),
                             soc=getattr(args, 'soc', None),
                             load_limit=getattr(args, 'load_limit', None),
                             amps=getattr(args, 'amps', None))

            case "diag" | "diagnostic":
                from franklinwh_cloud.cli_commands import diag
                await diag.run(client, json_output=args.json)

            case "bms" | "battery":
                from franklinwh_cloud.cli_commands import bms
                await bms.run(client, json_output=args.json)

            case "support" | "snapshot":
                from franklinwh_cloud.cli_commands import support
                if getattr(args, 'nettest', False):
                    await support.run_nettest(client, json_output=args.json,
                                             interval=getattr(args, 'interval', 0),
                                             duration=getattr(args, 'duration', 0),
                                             record_file=getattr(args, 'record', None),
                                             fem_url=getattr(args, 'fem_url', None),
                                             include_bms=getattr(args, 'bms', False))
                else:
                    await support.run(client, json_output=args.json,
                                      save=args.save,
                                      redact=getattr(args, 'redact', None),
                                      label=getattr(args, 'label', None),
                                      analyze=getattr(args, 'analyze', False),
                                      compare_file=getattr(args, 'compare_file', None),
                                      scope=getattr(args, 'scope', 'all'))

            case "fetch":
                from franklinwh_cloud.cli_commands import fetch
                await fetch.run(client, args.http_method, args.path,
                                data=args.data,
                                data_file=args.data_file,
                                params=args.params,
                                output_file=args.output,
                                json_output=args.json,
                                inject_gateway=not args.no_gateway,
                                inject_user=args.inject_user)

    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
    except FranklinWHTimeoutError as e:
        print_error(f"⚠ API timeout after {e.timeout_s}s — check your network connection and try again.")
        print_error(f"  URL: {e.url}")
        if args.verbose >= 2:
            import traceback
            traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print_error(f"Command failed: {e}")
        if args.verbose >= 2:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def main():
    """Synchronous entrypoint for console_scripts."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
