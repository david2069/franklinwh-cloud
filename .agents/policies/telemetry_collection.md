# Telemetry Collection Policy for Schema Drift

## Context
The FranklinWH Cloud API natively utilizes the `softwareversion` HTTP Request Header to determine which JSON payload schema to return to the client. When new capabilities (e.g., "v2" APIs) are deployed to the official Mobile App, the backend will only return those enriched schemas if the calling client asserts a matching or newer `softwareversion` metric.

## Policy Mandate (AP-14)
To ensure the `franklinwh-cloud` library does not receive legacy, degraded schemas and efficiently tracks API evolution:

1. **Client Spoofing**: The Python client MUST always inject a hardcoded `softwareversion` header corresponding to the most recently verified FranklinWH mobile app version (e.g., `APP2.4.1`). 
2. **Honest Telemetry**: To distinguish the library from malicious actors, the client MUST honestly identify itself via `optsource: 3` (Third-Party) and `optdevicename: python`.
3. **Core Metric Collection**: Whenever a developer captures HAR files, or whenever an offline script (e.g., `openapi_generator.py`) registers Schema Drift (missing or new keys), the exact `softwareversion` and `optsystemversion` from the HTTP request MUST be permanently logged alongside the drift incident.

## Rationale
By formally tracking the mobile application's version telemetry inside our schema verification suites, we permanently bridge the gap between "why did this API endpoint suddenly change its output format?" and "the user updated their FranklinWH Android app to v2.5.0 today". All future integrations or schema documentation updates must cite the `softwareversion` capability flag.
