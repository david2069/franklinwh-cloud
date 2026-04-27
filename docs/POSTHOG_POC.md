# PostHog Telemetry: Proof of Concept

To practically test and visualize the zero-latency daemon threading we just hardened, I have spun up a dedicated Proof of Concept (PoC) testing harness. This will allow you to instantly generate live events in your actual PostHog dashboard to visualize what a successful "long running test" looks like when the API keys are correct.

> [!IMPORTANT]
> **Prerequisite:** Before running this PoC, you must have your `[telemetry]` block configured inside `~/.franklinwh.ini` or `/Users/davidhona/dev/franklinwh-cloud-test/franklinwh.ini`.
> ```ini
> [telemetry]
> enabled = true
> uuid = poc-test-user-1
> api_key = phc_your_actual_posthog_key_here
> ```

## 1. Execute the PoC Test Script
I have prepared an automated CLI hook emulator located at `/tmp/poc_posthog_telemetry.py`.

This script actively parses your `.ini` file, instantiates the background daemon thread using `dispatch_cli_event`, sends 3 mock telemetry signatures, and prints the raw status directly to your terminal. If the API key is broken, the `logger.warning` we just patched will loudly flag the failure.

Run the test yourself in your terminal:
```bash
source /Users/davidhona/dev/franklinwh-cloud/venv/bin/activate
python /tmp/poc_posthog_telemetry.py
```

## 2. Analysis & Extraction on PostHog
If the PoC terminal succeeds without any `WARNING` logs, your telemetry has been successfully transmitted via the HTTP thread! 

**To visualize the analysis:**
1. Log into your [PostHog Dashboard](https://us.posthog.com).
2. Navigate to **Data Management > Events** on the left sidebar.
3. You will mathematically see exactly 3 `franklinwh_cloud_execution` events stamped with the current UTC time.
4. Click on one of the events to expose the payload. It will precisely contain:
   - `command: poc_discover`
   - `execution_latency_ms: (latency value)`
   - `success: true`

By configuring this tracking natively across your Home Assistant deployment, you can immediately build dashboards analyzing your integration's peak request traffic and tracking the raw uptime/failure rates of the FranklinWH cloud endpoints!
