# OpenAPI Generator Tool (`scripts/openapi_generator.py`)

## What is it?
The `openapi_generator.py` is an offline diagnostic script designed to identify **schema drift**. It parses raw HTTP archive payloads (HAR files) and aggressively cross-references them against the library's formal footprint (`docs/franklinwh_openapi.json`). 

## Why does it exist?
In the FranklinWH ecosystem, the API surface frequently drifts without warning. The Cloud API will occasionally append new metrics (like Smart Circuits V2 variables) or deprecate old flags. 

We designate `docs/franklinwh_openapi.json` as the immutable **Source of Truth** for the entire `franklinwh-cloud` library structure. The generator ensures that our source of truth remains 100% physically accurate to what the official FranklinWH App is exchanging via the internet, allowing us to prevent regressions before they hit downstream clients.

## How does it work?
The script fundamentally operates by executing structural diffs between physical payloads and OpenAPI abstractions. It operates in two explicit modes:

### 1. Fast Mode (Endpoint Discovery)
```bash
python3 scripts/openapi_generator.py --mode fast
```
**Function**: Rapidly loops through every captured `.har` file, extracting exclusively the `request.url` and `request.method`. It checks whether this `(METHOD, PATH)` signature explicitly exists inside the `franklinwh_openapi.json`. 
**Output**: Safely dumps any entirely undocumented API route strings into `unmapped_endpoints.json`.

### 2. Pedantic Mode (Deep Schema Validation)
```bash
python3 scripts/openapi_generator.py --mode pedantic
```
**Function**: High-intensity inspection. For every HTTP 200 payload inside every HAR capture, it attempts to load the JSON output. It maps every deeply nested key inside the response object and performs a strict subset-match against the existing OpenAPI properties.
**Output**: Dumps `new_keys` to `unmapped_endpoints.json`, mapping specific API routes to the precise new metrics (e.g. `result.runtimeData.newFeatureX`) that the official JSON spec does not structurally account for.

## When should it be used?
* **Routine Verification**: After importing new `.har` captures from HTTP Toolkit into the `hars/` directory, immediately run the planner.
* **Release Qualification**: Run Pedantic mode prior to tagging major semantic versions of `franklinwh-cloud` to guarantee zero structural regressions against the hardware.
* **Test Failure Debugs**: If an integration test throws a *Schema Drift Detected* AssertionError, run the generator to prove if the live hardware has legitimately deviated from the OpenAPI standard.
