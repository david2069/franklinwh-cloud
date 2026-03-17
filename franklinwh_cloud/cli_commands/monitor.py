"""Monitor command — real-time battery dashboard with auto-refresh.

Usage:
    franklinwh-cli monitor              # refresh every 30s, run until Ctrl+C
    franklinwh-cli monitor -i 10        # refresh every 10s
    franklinwh-cli monitor -d 5         # run for 5 minutes then stop
    franklinwh-cli monitor --compact    # single-line power summary
    franklinwh-cli monitor --json       # JSON output per interval
"""

import asyncio
import dataclasses
import signal
import sys
import time
from datetime import datetime

from franklinwh_cloud.cli_output import (
    print_header, print_kv, print_json_output,
    c,
)


# ── ANSI helpers ─────────────────────────────────────────────────────

CLEAR_SCREEN = "\033[2J\033[H"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BLUE = "\033[34m"


def _power_bar(watts: float, max_watts: float = 8000, width: int = 20) -> str:
    """Render a horizontal bar for power level."""
    if max_watts <= 0:
        return ""
    filled = int(min(abs(watts) / max_watts, 1.0) * width)
    bar = "█" * filled + "░" * (width - filled)
    if watts > 0:
        return f"{GREEN}{bar}{RESET}"
    elif watts < 0:
        return f"{CYAN}{bar}{RESET}"
    return f"{DIM}{bar}{RESET}"


def _soc_color(soc: float) -> str:
    """Color SoC based on level."""
    if soc >= 80:
        return f"{GREEN}{soc:.0f}%{RESET}"
    elif soc >= 30:
        return f"{YELLOW}{soc:.0f}%{RESET}"
    else:
        return f"{RED}{soc:.0f}%{RESET}"


def _direction(watts: float, pos_label: str = "export", neg_label: str = "import") -> str:
    """Describe power flow direction."""
    if watts > 50:
        return pos_label
    elif watts < -50:
        return neg_label
    return "idle"


def _grid_status_display(status_name: str) -> str:
    """Colorize grid status."""
    if status_name == "NORMAL":
        return f"{GREEN}● CONNECTED{RESET}"
    elif status_name == "DOWN":
        return f"{RED}● DISCONNECTED{RESET}"
    elif status_name == "OFF":
        return f"{YELLOW}● OFF-GRID{RESET}"
    return status_name


# ── Display Renderers ────────────────────────────────────────────────

def render_full(stats, mode_desc: str, elapsed: float, interval: int,
                iteration: int, api_calls: int, edge_pop: str | None) -> str:
    """Render full dashboard view."""
    cur = stats.current
    tot = stats.totals
    now = datetime.now().strftime("%H:%M:%S")

    lines = []
    lines.append(f"{CLEAR_SCREEN}")
    lines.append(f"{BOLD}╔══════════════════════════════════════════════════════════╗{RESET}")
    lines.append(f"{BOLD}║  ☀️  FranklinWH Battery Monitor         {DIM}{now}{RESET}{BOLD}  ║{RESET}")
    lines.append(f"{BOLD}╚══════════════════════════════════════════════════════════╝{RESET}")
    lines.append("")

    # Power Flow
    lines.append(f"  {BOLD}⚡ Power Flow{RESET}")
    lines.append(f"  ┌─────────────────────────────────────────────────────┐")
    lines.append(f"  │  Solar       {cur.solar_production:>7.0f} W  {_power_bar(cur.solar_production)}  │")
    lines.append(f"  │  Battery     {cur.battery_use:>7.0f} W  {_power_bar(cur.battery_use)}  {_direction(cur.battery_use, 'discharge', 'charge'):<10}│")
    lines.append(f"  │  Grid        {cur.grid_use:>7.0f} W  {_power_bar(cur.grid_use)}  {_direction(cur.grid_use, 'export', 'import'):<10}│")
    lines.append(f"  │  Home Load   {cur.home_load:>7.0f} W  {_power_bar(cur.home_load)}  │")
    if cur.generator_production:
        lines.append(f"  │  Generator   {cur.generator_production:>7.0f} W  {_power_bar(cur.generator_production)}  │")
    lines.append(f"  └─────────────────────────────────────────────────────┘")
    lines.append("")

    # Battery & Mode status line
    lines.append(f"  {BOLD}🔋 Battery{RESET}   SoC: {_soc_color(cur.battery_soc)}   Grid: {_grid_status_display(cur.grid_status.name)}")
    lines.append(f"  {BOLD}⚙️  Mode{RESET}      {mode_desc}   Status: {cur.run_status_dec}")
    lines.append("")

    # Daily energy
    lines.append(f"  {BOLD}📅 Today{RESET}")
    lines.append(f"  │  Solar: {tot.solar:>6.1f} kWh   Grid↓: {tot.grid_import:>5.1f} kWh   Grid↑: {tot.grid_export:>5.1f} kWh")
    lines.append(f"  │  Home:  {tot.home_use:>6.1f} kWh   Bat↓:  {tot.battery_charge:>5.1f} kWh   Bat↑:  {tot.battery_discharge:>5.1f} kWh")
    lines.append("")

    # Smart circuits (if any active)
    if cur.switch_1_load or cur.switch_2_load or cur.v2l_use:
        lines.append(f"  {BOLD}🔌 Smart Circuits{RESET}")
        if cur.switch_1_load:
            lines.append(f"  │  Circuit 1: {cur.switch_1_load:>6.0f} W")
        if cur.switch_2_load:
            lines.append(f"  │  Circuit 2: {cur.switch_2_load:>6.0f} W")
        if cur.v2l_use:
            lines.append(f"  │  V2L:       {cur.v2l_use:>6.0f} W")
        lines.append("")

    # Footer
    mins = int(elapsed // 60)
    secs = int(elapsed % 60)
    edge_str = f"  Edge: {edge_pop}" if edge_pop else ""
    lines.append(f"  {DIM}Refresh: {interval}s │ Uptime: {mins}m{secs:02d}s │ Polls: {iteration} │ API: {api_calls}{edge_str}{RESET}")
    lines.append(f"  {DIM}Press Ctrl+C to exit{RESET}")

    return "\n".join(lines)


def render_compact(stats, iteration: int) -> str:
    """Render single-line compact view."""
    cur = stats.current
    now = datetime.now().strftime("%H:%M:%S")
    grid_sym = "●" if cur.grid_status.name == "NORMAL" else "✗"
    batt_dir = "↑" if cur.battery_use > 50 else "↓" if cur.battery_use < -50 else "─"
    return (
        f"[{now}] "
        f"☀ {cur.solar_production:>5.0f}W  "
        f"🔋 {cur.battery_soc:>3.0f}% {batt_dir}{abs(cur.battery_use):>5.0f}W  "
        f"⚡ {grid_sym} {cur.grid_use:>+6.0f}W  "
        f"🏠 {cur.home_load:>5.0f}W  "
        f"│ {cur.work_mode_desc}"
    )


# ── Main Loop ────────────────────────────────────────────────────────

async def run(client, *, json_output: bool = False, interval: int = 30,
              duration: int | None = None, compact: bool = False):
    """Execute the monitor command — continuous polling loop.

    Args:
        client: Authenticated FranklinWH Client
        json_output: Emit JSON per poll interval
        interval: Seconds between refreshes (default 30)
        duration: Total minutes to run (None = until Ctrl+C)
        compact: Single-line output mode (no screen clear)
    """
    start_time = time.time()
    end_time = start_time + (duration * 60) if duration else None
    iteration = 0

    # Hide cursor for full mode
    if not compact and not json_output:
        sys.stdout.write(HIDE_CURSOR)
        sys.stdout.flush()

    # Restore cursor on exit
    def restore_cursor(signum=None, frame=None):
        if not compact and not json_output:
            sys.stdout.write(SHOW_CURSOR)
            sys.stdout.flush()
        if signum:
            sys.exit(130)

    signal.signal(signal.SIGINT, restore_cursor)

    try:
        while True:
            iteration += 1
            elapsed = time.time() - start_time

            # Check duration limit
            if end_time and time.time() >= end_time:
                break

            # Fetch data
            try:
                stats = await client.get_stats()
            except Exception as e:
                if compact:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠ Error: {e}")
                else:
                    sys.stdout.write(f"\r  ⚠ Poll failed: {e}  ")
                    sys.stdout.flush()
                await asyncio.sleep(interval)
                continue

            # Get mode description
            mode_desc = getattr(stats.current, 'work_mode_desc', 'Unknown')

            # Get metrics for footer
            metrics = client.get_metrics()
            api_calls = metrics.get("total_api_calls", 0)

            # Edge tracker
            edge_pop = None
            if hasattr(client, 'edge_tracker') and client.edge_tracker and client.edge_tracker.total_requests > 0:
                edge_pop = client.edge_tracker.current_pop

            # Render
            if json_output:
                output = {
                    "timestamp": datetime.now().isoformat(),
                    "iteration": iteration,
                    "current": dataclasses.asdict(stats.current),
                    "totals": dataclasses.asdict(stats.totals),
                    "metrics": metrics,
                }
                if edge_pop:
                    output["edge_pop"] = edge_pop
                print_json_output(output)

            elif compact:
                print(render_compact(stats, iteration))

            else:
                output = render_full(
                    stats, mode_desc, elapsed, interval,
                    iteration, api_calls, edge_pop
                )
                sys.stdout.write(output)
                sys.stdout.flush()

            # Wait for next interval
            await asyncio.sleep(interval)

    finally:
        restore_cursor()
        if not json_output and not compact:
            print(f"\n\n  Monitor stopped after {iteration} polls ({int(elapsed)}s)")
            # Show final metrics
            metrics = client.get_metrics()
            print(f"  Total API calls: {metrics['total_api_calls']}")
            print(f"  Avg response: {metrics['avg_response_time_s']:.3f}s")
            if hasattr(client, 'edge_tracker') and client.edge_tracker:
                et = client.edge_tracker.snapshot()
                if et["edge_transitions"] > 0:
                    print(f"  ⚠ Edge transitions: {et['edge_transitions']}")
            print()
