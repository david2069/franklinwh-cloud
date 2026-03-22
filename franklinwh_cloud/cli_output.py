"""CLI output formatting and debug/tracing utilities."""

import json
import logging
import sys


# ANSI colour codes (disabled when not a TTY or --no-color)
_COLORS = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "cyan": "\033[36m",
    "red": "\033[31m",
    "magenta": "\033[35m",
}

_color_enabled = True


def disable_color():
    """Disable ANSI colour output."""
    global _color_enabled
    _color_enabled = False


def c(code: str, text: str) -> str:
    """Wrap text in an ANSI colour code."""
    if not _color_enabled:
        return text
    return f"{_COLORS.get(code, '')}{text}{_COLORS['reset']}"


# ── Section formatting ────────────────────────────────────────────────

def print_header(title: str):
    """Print a prominent header line."""
    width = 60
    print(c("bold", "=" * width))
    print(c("bold", f"  {title}"))
    print(c("bold", "=" * width))


def print_section(icon: str, title: str):
    """Print a section header with icon."""
    print(f"\n{icon} {c('bold', title)}")


def print_kv(key: str, value, indent: int = 3):
    """Print a key-value pair with alignment."""
    pad = " " * indent
    print(f"{pad}{c('dim', key + ':'):>28s} {value}")


def print_table(rows: list[tuple[str, str]], indent: int = 3):
    """Print aligned key-value rows."""
    if not rows:
        return
    pad = " " * indent
    max_key = max(len(k) for k, _ in rows)
    for key, val in rows:
        print(f"{pad}{c('dim', key):>{max_key + 6}s}  {val}")


def print_json_output(data, indent: int = 2):
    """Print data as formatted JSON to stdout."""
    if hasattr(data, "__dict__"):
        # dataclass-like objects
        import dataclasses
        if dataclasses.is_dataclass(data):
            data = dataclasses.asdict(data)
    print(json.dumps(data, indent=indent, default=str))


def print_error(msg: str):
    """Print an error message to stderr."""
    print(f"{c('red', '✘')} {msg}", file=sys.stderr)


def print_success(msg: str):
    """Print a success message."""
    print(f"{c('green', '✓')} {msg}")


def print_warning(msg: str):
    """Print a warning message."""
    print(f"{c('yellow', '⚠')} {msg}")


# ── Debug / Tracing ──────────────────────────────────────────────────

# Module names that can be traced (maps to franklinwh.mixins.<name>)
TRACEABLE_MODULES = ["stats", "modes", "tou", "storm", "power", "devices", "account"]


class ApiTraceHandler(logging.Handler):
    """Logging handler that prints API calls in a compact trace format.

    Output looks like:
        → GET /hes-gateway/terminal/getHomeGatewayList (0.45s)
        → POST /mqtt/request (1.23s)
    """

    def emit(self, record):
        try:
            msg = self.format(record)
            # Only show lines that look like API calls or have timing
            if any(kw in msg.lower() for kw in ["url", "get", "post", "_get", "_post", "request", "response"]):
                print(f"  {c('dim', '→')} {c('cyan', msg)}", file=sys.stderr)
        except Exception:
            pass


def configure_logging(verbosity: int = 0, trace_modules: list[str] | None = None,
                      api_trace: bool = False, log_file: str | None = None):
    """Configure logging based on CLI flags.

    Parameters
    ----------
    verbosity : int
        0 = WARNING (quiet), 1 = INFO, 2 = DEBUG franklinwh + httpx,
        3 = DEBUG on root (everything)
    trace_modules : list[str] | None
        Specific mixin modules to set to DEBUG, e.g. ["tou", "modes"]
    api_trace : bool
        If True, add an ApiTraceHandler to show per-call summaries
    log_file : str | None
        If set, also log to this file
    """
    # Base format
    fmt = "%(asctime)s %(levelname)-5s %(name)s: %(message)s"
    datefmt = "%H:%M:%S"

    # Determine levels
    root_level = logging.WARNING
    franklinwh_level = logging.WARNING
    httpx_level = logging.WARNING

    if verbosity >= 1:
        franklinwh_level = logging.INFO
    if verbosity >= 2:
        franklinwh_level = logging.DEBUG
        httpx_level = logging.DEBUG
    if verbosity >= 3:
        root_level = logging.DEBUG

    # Configure root
    handlers: list[logging.Handler] = []

    if verbosity > 0 or trace_modules or api_trace:
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
        handlers.append(stderr_handler)

    if log_file:
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            log_file, maxBytes=5_000_000, backupCount=3
        )
        file_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
        handlers.append(file_handler)

    logging.basicConfig(level=root_level, handlers=handlers, force=True)

    # Set franklinwh logger level
    fw_logger = logging.getLogger("franklinwh_cloud")
    fw_logger.setLevel(franklinwh_level)

    # Set httpx logger level
    httpx_logger = logging.getLogger("httpx")
    httpx_logger.setLevel(httpx_level)

    # Selective module tracing
    if trace_modules:
        # First quiet everything, then enable specific modules
        fw_logger.setLevel(logging.WARNING)
        for mod in trace_modules:
            mod = mod.strip().lower()
            if mod == "all":
                fw_logger.setLevel(logging.DEBUG)
                break
            elif mod == "client":
                logging.getLogger("franklinwh.client").setLevel(logging.DEBUG)
            elif mod in TRACEABLE_MODULES:
                logging.getLogger(f"franklinwh.mixins.{mod}").setLevel(logging.DEBUG)
            else:
                print_warning(f"Unknown trace module: {mod} (available: {', '.join(TRACEABLE_MODULES)}, client, all)")

    # API trace handler
    if api_trace:
        trace_handler = ApiTraceHandler()
        trace_handler.setFormatter(logging.Formatter("%(message)s"))
        fw_logger.addHandler(trace_handler)
        fw_logger.setLevel(min(fw_logger.level, logging.DEBUG))
