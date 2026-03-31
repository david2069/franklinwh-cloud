"""PostHog Telemetry Dispatcher for franklinwh-cloud.

Provides a completely asynchronous, non-blocking telemetry engine for
capturing CLI usage metrics (strictly for developers who opt-in via franklinwh.ini).

This module uses built-in urllib on a daemon thread to send payload events directly
to PostHog's public capture API. No PII, passwords, emails, or serial numbers are ever recorded.
"""

import json
import logging
import platform
import threading
import urllib.request
import urllib.error

from franklinwh_cloud.metrics import __version__

logger = logging.getLogger(__name__)

# Replace with your actual PostHog Project API Key when ready
# Default placeholder; override by passing api_key to the dispatcher
POSTHOG_API_KEY = "phc_your_actual_project_id_here"
POSTHOG_URL = "https://us.i.posthog.com/capture/"


def _send_telemetry_sync(event_name: str, distinct_id: str, properties: dict, api_key: str = None) -> None:
    """Synchronous worker that executes the physical HTTP POST."""
    if not distinct_id:
        return
        
    payload = {
        "api_key": api_key or POSTHOG_API_KEY,
        "event": event_name,
        "properties": {
            "distinct_id": distinct_id,
            "franklin_version": __version__,
            "python_version": platform.python_version(),
            "os": platform.system(),
            "os_release": platform.release(),
            **properties
        }
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            POSTHOG_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        # 1-second timeout to guarantee it never stalls the background thread forever
        with urllib.request.urlopen(req, timeout=1.0) as response:
            if response.status >= 400:
                logger.debug(f"Telemetry failed to dispatch (HTTP {response.status})")
    except Exception as e:
        logger.debug(f"Telemetry dispatch swallowed exception: {e}")


def dispatch_cli_event(command: str, is_opted_in: bool, execution_uuid: str, api_key: str = None) -> None:
    """Hook for the CLI to schedule a telemetry task globally.
    
    Spawns a highly isolated daemon worker thread. This ensures the 
    HTTP call survives the main asyncio loop tearing down (which happens 
    in milliseconds when the CLI `system.exit()` fires).
    """
    if not is_opted_in:
        return

    # Fire and forget on a daemon thread so it never prevents the app from exiting
    worker = threading.Thread(
        target=_send_telemetry_sync,
        args=("cli_command_executed", execution_uuid, {"command": command}, api_key),
        daemon=True
    )
    worker.start()
