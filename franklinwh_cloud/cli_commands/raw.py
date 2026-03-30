"""Raw command — direct API method passthrough."""

import pprint

from franklinwh_cloud.cli_output import (
    print_json_output, print_warning, print_error,
)


# Methods available for raw invocation (read-only by default)
AVAILABLE_METHODS = {
    # Stats mixin
    "get_stats": {"args": 0, "desc": "Current power flows and daily totals"},
    "get_runtime_data": {"args": 0, "desc": "Runtime data log"},
    "get_power_by_day": {"args": 1, "desc": "Power for a day (arg: YYYY-MM-DD)"},
    "get_power_details": {"args": 2, "desc": "Power aggregated (args: type[1-5] date)"},
    # Modes mixin
    "get_mode": {"args": 0, "desc": "Current operating mode"},
    "get_mode_info": {"args": 0, "desc": "Mode configuration details"},
    "get_all_mode_soc": {"args": 0, "desc": "Reserve SoC for all modes (TOU/Self/Emergency)"},
    # Storm mixin
    "get_weather": {"args": 0, "desc": "Current weather conditions"},
    "get_storm_settings": {"args": 0, "desc": "Storm hedge settings"},
    "get_storm_list": {"args": 0, "desc": "Storm event history"},
    # Power mixin
    "get_grid_status": {"args": 0, "desc": "Grid on/off status"},
    "get_power_control_settings": {"args": 0, "desc": "PCS control settings"},
    "get_power_info": {"args": 0, "desc": "Relay and power hardware info"},
    # Devices mixin
    "get_device_composite_info": {"args": 0, "desc": "Full device composite data"},
    "get_agate_info": {"args": 0, "desc": "aGate hardware info"},
    "get_apower_info": {"args": 0, "desc": "aPower battery hardware info"},
    "get_device_info": {"args": 0, "desc": "Device detail info"},
    "get_smart_circuits_info": {"args": 0, "desc": "Smart circuit configuration"},
    "get_bms_info": {"args": 1, "desc": "BMS info for aPower (arg: serial_no)"},
    "get_network_info": {"args": 0, "desc": "aGate network config (WiFi/Eth/4G via MQTT)"},
    "get_wifi_config": {"args": 0, "desc": "WiFi SSID, AP config, security (via MQTT)"},
    "scan_wifi_networks": {"args": 0, "desc": "Scan for available WiFi networks (via MQTT)"},
    "get_connection_status": {"args": 0, "desc": "Router/network/AWS connectivity (via MQTT)"},
    "get_network_switches": {"args": 0, "desc": "Interface on/off switches: WiFi/Eth/4G (via MQTT)"},
    # Account mixin
    "get_home_gateway_list": {"args": 0, "desc": "Home gateway list"},
    "siteinfo": {"args": 0, "desc": "Site / account info"},
    "get_entrance_info": {"args": 0, "desc": "Customer entrance config"},
    "get_unread_count": {"args": 0, "desc": "Unread notification count"},
    "get_notification_settings": {"args": 0, "desc": "Notification settings"},
    "get_warranty_info": {"args": 0, "desc": "Warranty information"},
    "get_alarm_codes_list": {"args": 0, "desc": "Alarm codes history"},
    "get_site_and_device_info": {"args": 0, "desc": "Site and device list"},
    "get_equipment_location": {"args": 0, "desc": "Equipment location"},
    "get_grid_profile_info": {"args": 0, "desc": "Grid compliance profile"},
    "get_programme_info": {"args": 0, "desc": "VPP/utility programmes"},
    "get_benefit_info": {"args": 0, "desc": "Benefit earnings info"},
    "get_gateway_alarm": {"args": 0, "desc": "Active gateway alarms"},
    # TOU mixin
    "get_gateway_tou_list": {"args": 0, "desc": "TOU schedule list"},
    "get_charge_power_details": {"args": 0, "desc": "Charge power details"},
    "get_tou_dispatch_detail": {"args": 0, "desc": "TOU dispatch detail"},
    "get_utility_companies": {"args": 2, "desc": "Search utility companies (args: countryId provinceId)"},
    "get_tariff_list": {"args": 1, "desc": "List tariffs for a utility (arg: companyId)"},
    "get_tariff_detail": {"args": 1, "desc": "Full tariff template detail (arg: tariffId)"},
    "get_tou_detail_by_id": {"args": 1, "desc": "TOU config by ID (arg: touId)"},
    "get_bonus_info": {"args": 0, "desc": "TOU bonus/incentive info"},
    "get_vpp_tip": {"args": 0, "desc": "VPP tips for TOU updates"},
    "calculate_expected_earnings": {"args": 0, "desc": "Projected savings for tariff template (pipe JSON via stdin)"},
    # Billing / Savings
    "get_electric_data": {"args": 2, "desc": "Electricity kWh arrays (args: type[1-3] YYYY-MM-DD)"},
    "get_charge_history": {"args": 0, "desc": "Battery charge/discharge session history"},
    # Device / Site
    "get_site_detail": {"args": 0, "desc": "Site name, address, location"},
    "get_device_detail": {"args": 0, "desc": "Device/gateway address detail"},
    "get_device_overall_info": {"args": 0, "desc": "aPower count and total power"},
    "get_personal_info": {"args": 0, "desc": "User profile info"},
}


def print_available():
    """Print the list of available raw API methods."""
    print("\nAvailable API methods:\n")
    max_name = max(len(n) for n in AVAILABLE_METHODS)
    for name, info in AVAILABLE_METHODS.items():
        args = f"({info['args']} arg{'s' if info['args'] != 1 else ''})" if info["args"] else ""
        print(f"  {name:<{max_name + 2}} {args:>8}  {info['desc']}")
    print()


async def run(client, method: str, values: list[str] | None = None,
              *, json_output: bool = False,
              show_headers: bool = False, show_timings: bool = False,
              validate_schema: bool = False):
    """Execute a raw API method call."""

    if method in ("help", "list", "?"):
        print_available()
        return

    if not hasattr(client, method):
        print_error(f"Unknown method: {method}")
        print_available()
        return

    # Build args — check for JSON payload on stdin
    import sys
    import json as _json
    args = values or []
    stdin_payload = None

    if not sys.stdin.isatty():
        # Data piped via stdin — parse as JSON
        stdin_text = sys.stdin.read().strip()
        if stdin_text:
            try:
                stdin_payload = _json.loads(stdin_text)
            except _json.JSONDecodeError as e:
                print_error(f"Invalid JSON on stdin: {e}")
                return

    info = AVAILABLE_METHODS.get(method, {})
    expected = info.get("args", 0) if info else 0

    if not stdin_payload and expected and len(args) < expected:
        print_warning(f"{method} expects {expected} argument(s), got {len(args)}")
        if info:
            print(f"  Description: {info['desc']}")
        return

    # Call the method (with timing)
    import time
    func = getattr(client, method)
    t0 = time.monotonic()
    try:
        if stdin_payload is not None:
            # Stdin JSON becomes the first argument, positional args follow
            result = await func(stdin_payload, *args)
        elif args:
            result = await func(*args)
        else:
            result = await func()
    except Exception as e:
        print_error(f"{method} failed: {e}")
        return
    elapsed_ms = (time.monotonic() - t0) * 1000

    if validate_schema:
        print("\n[Schema Validator] Analyzing payload against swagger spec...")
        _validate_live_schema(client, result)

    # Output
    if json_output:
        output = result
        if show_timings or show_headers:
            # Wrap result with metadata
            output = {"_result": result}
            if show_timings:
                output["_timing"] = {"elapsed_ms": round(elapsed_ms, 1)}
                if hasattr(client, 'edge_tracker') and client.edge_tracker:
                    et = client.edge_tracker
                    if et._last_response_headers:
                        output["_timing"]["edge_pop"] = et._last_response_headers.get("x-amz-cf-pop")
                        output["_timing"]["cache"] = et._last_response_headers.get("x-cache")
            if show_headers and hasattr(client, 'edge_tracker') and client.edge_tracker:
                output["_headers"] = client.edge_tracker._last_response_headers
        print_json_output(output)
    else:
        # Timings banner
        if show_timings:
            from franklinwh_cloud.cli_output import print_section, print_kv, c
            print_section("⏱", "Timing")
            print_kv("Method", method)
            if hasattr(client, 'edge_tracker') and client.edge_tracker and client.edge_tracker._last_request_url:
                http_method = client.edge_tracker._last_request_method or "?"
                print_kv("URL", f"{http_method} {client.edge_tracker._last_request_url}")
            print_kv("Duration", f"{elapsed_ms:.0f}ms")
            if hasattr(client, 'edge_tracker') and client.edge_tracker:
                h = client.edge_tracker._last_response_headers or {}
                pop = h.get("x-amz-cf-pop")
                cache = h.get("x-cache")
                if pop:
                    print_kv("CloudFront", f"{pop}  {cache or ''}")
                via = h.get("via")
                if via:
                    print_kv("Via", via)
                age = h.get("age")
                if age:
                    print_kv("Cache age", f"{age}s")
            print()

        # Response headers
        if show_headers:
            from franklinwh_cloud.cli_output import print_section, c
            print_section("📨", "Response Headers")
            headers = {}
            if hasattr(client, 'edge_tracker') and client.edge_tracker:
                headers = client.edge_tracker._last_response_headers or {}
            if headers:
                max_key = max(len(k) for k in headers) if headers else 0
                for key, val in headers.items():
                    print(f"  {key:<{max_key + 2}} {val}")
            else:
                print("  (no headers captured — MQTT-based methods don't have HTTP headers)")
            print()

        # Result
        if isinstance(result, dict):
            pprint.pprint(result, indent=4, width=120, sort_dicts=False)
        else:
            print(result)


def _validate_live_schema(client, live_payload: dict):
    import json
    import sys
    from urllib.parse import urlparse
    from pathlib import Path

    et = getattr(client, "edge_tracker", None)
    if not et or not et._last_request_url:
        print_error("Cannot validate schema: no HTTP URL intercepted by edge_tracker.")
        return
        
    url = urlparse(et._last_request_url)
    path = url.path
    method = (et._last_request_method or "get").lower()

    spec_path = Path("docs/franklinwh_openapi.json")
    if not spec_path.exists():
        print_warning(f"Skipping schema drift check. Missing {spec_path} in PWD.")
        return
        
    try:
        with open(spec_path, "r", encoding="utf-8") as f:
            spec = json.load(f)
    except Exception as e:
        print_error(f"Failed to load OpenAPI spec: {e}")
        return
        
    defined_paths = spec.get("paths", {})
    if path not in defined_paths or method not in defined_paths[path]:
        print_warning(f"Undocumented endpoint signature: {method.upper()} {path} is missing from OpenAPI 3.0 spec.")
        return
        
    sys.path.insert(0, str(Path.cwd()))
    try:
        from scripts.openapi_generator import _flatten_payload_keys, _flatten_schema_keys
    except ImportError:
        print_error("Cannot import openapi_generator tooling from ./scripts/openapi_generator.py for deep drift assertions.")
        return
        
    try:
        op_schema = defined_paths[path][method]["responses"]["200"]["content"]["application/json"]["schema"]
    except KeyError:
        print_warning(f"Warning: {method.upper()} {path} exists in openapi.json, but no 200 response JSON schema is mapped.")
        return
        
    official_keys = _flatten_schema_keys(op_schema)
    
    # In franklinwh_cloud, Methods routinely unwrap envelopes automatically. E.g `get_agate_info` returns `result.dataList`.
    # Therefore, reconstructing the entire envelope structure for _flatten_payload_keys requires heuristic padding.
    # To keep simple in CLI raw, we just do a subset check: Do all the keys in the returned dict exist SOMEWHERE in the official spec?
    
    flattened_live = _flatten_payload_keys(live_payload)
    
    drifting_keys = []
    official_flat = " ".join(official_keys).lower()
    
    for lk in flattened_live:
        # Strip array syntax and perform simple existence check due to unwrapped payloads vs enveloped swagger schemas
        lks = lk.split(".")[-1].lower()
        if lks not in official_flat:
            drifting_keys.append(lk)
            
    if drifting_keys:
        print_warning(f"Detected {len(drifting_keys)} unmapped keys in live schema vs docs/franklinwh_openapi.json!")
        for k in drifting_keys:
            print(f"  ? {k}")
    else:
        from franklinwh_cloud.cli_output import c
        print(f"[{c('bright_green')}✓{c('reset')}] Payload structure gracefully aligns with OpenAPI specifications.")
