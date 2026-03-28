# Telemetry & Privacy Policy

The `franklinwh-cloud` library and CLI prioritize user privacy. Because this integration handles smart home appliances, battery gateways, and cloud credentials, strict privacy boundaries are mathematically enforced across all community telemetry tools.

## What is Tracked?
We use two explicit telemetry services to understand exactly how the open-source community leverages the library.

### 1. Scarf (Passive Installation Tracking)
We use [Scarf](https://scarf.sh/) to track package downloads, Home Assistant integration pulls, and PyPI installations.
- **Data Collected**: Package version, Operating System family (e.g. Linux vs MacOS), abstract geographic region.
- **Privacy Model**: All raw IPs are aggressively masked and anonymized by Scarf before the maintainers ever see the analytics dashboard. Scarf strips identifying information to strictly maintain GDPR/CCPA compliance.

### 2. PostHog (Active Feature Usage)
For deeper CLI usage (e.g., figuring out if users genuinely use the `--extended` table views or which operating modes are dispatched the most), we leverage [PostHog](https://posthog.com/).
- **Data Collected**: The name of the Python commands invoked, execution latency, and success/failure flags. 
- **Privacy Model**: PostHog telemetry is **100% Opt-In**. If enabled, your terminal is assigned a localized, randomized, anonymous UUID (e.g. `c7b2-4d1a...`). We mathematically never collect, serialize, or transmit your FranklinWH emails, passwords, serials numbers, gateway hardware identifiers, or localized battery capacities.

## How to Opt Out
If you operate `franklinwh-cloud` via the Python library natively, PostHog telemetry is inherently disabled unless explicitly initialized into the root dispatcher.

If you operate via `franklinwh-cli`, the client strictly enforces the `telemetry.enabled` configuration key located in your runtime `franklinwh.ini` configurations. If you decline the setup wizard or strip the key, your footprint remains absolutely invisible.

### Home Assistant Integration Compliance
If you consume `franklinwh-cloud` heavily via a downstream Home Assistant (HACS) wrap, tracking falls strictly onto the Custom Integration's specific UI configuration wizard in line with the Home Assistant Analytics protocol. No ghost analytics are actively bypassed by our Python library under the hood.

*For any questions regarding runtime privacy, please raise an issue strictly on the project GitHub.*

---

## Developer Guide: Implementing PostHog Telemetry

If you are building a custom CLI wrapper (e.g., `franklinwh_cli.py`) or a Home Assistant component using `franklinwh-cloud` and you want to opt-in / securely hook your application into our metrics system, you can use the natively bundled PostHog dispatcher. 

The dispatcher uses a highly isolated zero-dependency **synchronous daemon thread** running built-in `urllib` to ensure your main script/CLI tears down instantly without waiting for HTTP connections, mathematically guaranteeing zero application lag.

### Worked Example

Here is exactly how you connect the tracking pipeline into your own script's `main()` lifecycle:

```python
import configparser
import os
import sys

# 1. Import your main client components
from franklinwh_cloud.client import Client

# 2. Import the isolated tracking daemon
from franklinwh_cloud.telemetry import dispatch_cli_event

def main():
    # Example: you parse the incoming CLI command (e.g. 'status', 'tou --set')
    command_executed = sys.argv[1] if len(sys.argv) > 1 else "unknown"

    # 3. Read the user's explicit Opt-In consent config
    telemetry_enabled = False
    telemetry_uuid = "anonymous"
    
    ini_path = "franklinwh.ini"
    if os.path.exists(ini_path):
        config = configparser.ConfigParser()
        config.read(ini_path)
        try:
            if config.getboolean("telemetry", "enabled", fallback=False):
                telemetry_enabled = True
                telemetry_uuid = config.get("telemetry", "uuid", fallback="anonymous")
        except Exception:
            pass

    # 4. Fire the dispatcher!
    # If telemetry_enabled == False, this silently returns and does absolutely nothing.
    # If True, it launches a detached daemon thread to PostHog and instantly returns control back to your script.
    dispatch_cli_event(
        command=command_executed, 
        is_opted_in=telemetry_enabled, 
        execution_uuid=telemetry_uuid
    )

    # 5. Continue executing your normal sync/async workload...
    # asyncio.run(my_async_business_logic())

if __name__ == "__main__":
    main()
```
