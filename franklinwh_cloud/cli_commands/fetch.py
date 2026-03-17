"""Fetch command — arbitrary GET/POST to any FranklinWH API endpoint.

Allows hitting endpoints not yet wrapped in the library, with inline JSON
or file-based input/output for POST data. Also captures HTTP response headers
for diagnostic purposes (app version, AWS LB info).

Examples:
    franklinwh-cli fetch GET /hes-gateway/common/getPowerCapConfigList
    franklinwh-cli fetch POST /api-smart/terminal/askQuestion --data '{"action":1,"content":"How much solar?"}'
    franklinwh-cli fetch POST /api-smart/terminal/askQuestion --data-file request.json
    franklinwh-cli fetch GET /api-smart/terminal/recommendQuestion --params type=1
    franklinwh-cli fetch POST /hes-gateway/common/selectDeviceRunLogList --data-file req.json -o response.json
"""

import json
import sys

from franklinwh_cloud.cli_output import (
    print_header, print_section, print_kv, print_json_output,
    print_error, print_success, print_warning, c,
)

# Headers worth capturing for diagnostics / breaking-change detection
DIAGNOSTIC_HEADERS = [
    "server", "x-amzn-requestid", "x-amz-apigw-id", "x-amzn-trace-id",
    "x-powered-by", "x-request-id", "via", "x-cache",
    "x-amz-cf-pop",  # CloudFront edge location (e.g. SYD62-P1 = Sydney)
    "x-amz-cf-id",   # CloudFront request trace ID
    "content-type", "date",
]


async def run(client, method: str, path: str, *,
              data: str | None = None,
              data_file: str | None = None,
              params: list[str] | None = None,
              output_file: str | None = None,
              json_output: bool = False,
              inject_gateway: bool = True,
              inject_user: bool = False):
    """Execute an arbitrary API call."""
    method = method.upper()
    if method not in ("GET", "POST"):
        print_error(f"Unsupported method: {method}. Use GET or POST.")
        return

    # Build the full URL
    base_url = client.url_base.rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    url = base_url + path

    # Parse query parameters
    query_params = {}
    if params:
        for p in params:
            if "=" in p:
                k, v = p.split("=", 1)
                query_params[k] = v
            else:
                print_warning(f"Ignoring invalid param (no '='): {p}")

    # Build POST payload
    payload = None
    if method == "POST":
        if data_file:
            try:
                if data_file == "-":
                    print_warning("Reading POST body from stdin (paste JSON, then Ctrl-D):")
                    raw = sys.stdin.read()
                else:
                    with open(data_file) as f:
                        raw = f.read()
                payload = json.loads(raw)
            except FileNotFoundError:
                print_error(f"File not found: {data_file}")
                return
            except json.JSONDecodeError as e:
                print_error(f"Invalid JSON in {data_file}: {e}")
                return
        elif data:
            try:
                payload = json.loads(data)
            except json.JSONDecodeError as e:
                print_error(f"Invalid JSON: {e}")
                return
        else:
            payload = {}

        # Auto-inject common fields
        if inject_gateway and "gatewayId" not in payload:
            payload["gatewayId"] = client.gateway
        if inject_gateway and "deviceId" not in payload:
            payload["deviceId"] = client.gateway
        if inject_user and "userId" not in payload:
            user_id = ""
            if client.info:
                user_id = str(client.info.get("userId", ""))
            payload["userId"] = user_id

    # Show what we're about to do
    if not json_output:
        print_section("🌐", f"{method} {path}")
        if query_params:
            print_kv("Params", str(query_params))
        if payload:
            preview = json.dumps(payload, indent=2)
            if len(preview) > 200:
                preview = preview[:200] + "..."
            print_kv("Payload", preview)

    # Make the request using client.session (the authenticated httpx.AsyncClient)
    try:
        headers = {"loginToken": client.token}

        if method == "GET":
            response = await client.session.get(
                url,
                params=query_params or None,
                headers=headers,
            )
        else:
            headers["Content-Type"] = "application/json"
            response = await client.session.post(
                url,
                json=payload,
                params=query_params or None,
                headers=headers,
            )

        # Parse response
        try:
            result = response.json()
        except Exception:
            result = {"raw_text": response.text, "status_code": response.status_code}

        # Capture diagnostic headers
        diag_headers = {}
        for h in DIAGNOSTIC_HEADERS:
            val = response.headers.get(h)
            if val:
                diag_headers[h] = val
        # Also capture any 'softwareversion' or custom FranklinWH headers
        for h, v in response.headers.items():
            hl = h.lower()
            if "version" in hl or "franklin" in hl or "software" in hl:
                diag_headers[h] = v

        # Save to file if requested
        if output_file:
            output_data = {
                "request": {
                    "method": method,
                    "url": str(response.url),
                    "payload": payload,
                },
                "response": {
                    "status_code": response.status_code,
                    "headers": diag_headers,
                    "body": result,
                },
            }
            with open(output_file, "w") as f:
                json.dump(output_data, f, indent=2, default=str)
            print_success(f"Response saved to {output_file}")

        # JSON output mode
        if json_output:
            if not output_file:
                output_data = {
                    "status_code": response.status_code,
                    "headers": diag_headers,
                    "body": result,
                }
                print_json_output(output_data)
            return

        # Pretty print
        print_section("📥", f"Response ({response.status_code})")

        # Show diagnostic headers
        if diag_headers:
            print_section("🔍", "Server Info")
            for h, v in diag_headers.items():
                print_kv(h, v)

        if isinstance(result, dict):
            code = result.get("code", "?")
            msg = result.get("msg", "")
            success = result.get("success", None)
            status_color = "green" if (code == 200 or success) else "red"
            print_kv("API Status", f'{c(status_color, str(code))} {msg}')

            # Show data section
            data_section = result.get("data", result.get("result"))
            if data_section is not None:
                if isinstance(data_section, (dict, list)):
                    formatted = json.dumps(data_section, indent=2, default=str)
                    lines = formatted.split("\n")
                    if len(lines) > 60:
                        print(f"\n{chr(10).join(lines[:60])}")
                        print(f"\n  ... ({len(lines) - 60} more lines)")
                        print(f"  Use --output file.json to save full response")
                    else:
                        print(f"\n{formatted}")
                else:
                    print_kv("Data", str(data_section))
            elif "raw_text" in result:
                print(result["raw_text"][:500])
        else:
            print(str(result)[:500])

        print()

    except Exception as e:
        print_error(f"{method} {path} failed: {e}")
        import traceback
        traceback.print_exc()
