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
