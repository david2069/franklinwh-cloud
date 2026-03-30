#!/usr/bin/env python3
"""OpenAPI HAR Parser and Generator

Parses structural network footprints from HTTP Toolkit (*.har) dumps to identify
purely novel endpoints (--fast) or deeply unmapped structural JSON keys inside 
existing endpoints (--pedantic).
"""

import argparse
import json
import logging
from pathlib import Path
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def _flatten_schema_keys(schema_node: dict, prefix=""):
    """
    Recursively extract flatten keys (e.g., 'result.runtimeData.mode')
    from an OpenAPI 3 schema block representing a JSON response.
    """
    keys = set()
    if not isinstance(schema_node, dict):
        return keys
        
    props = schema_node.get("properties", {})
    if props:
        for k, v in props.items():
            full = f"{prefix}{k}" if prefix else k
            keys.add(full)
            keys.update(_flatten_schema_keys(v, prefix=f"{full}."))
    
    # Check if this node is an Array of Objects
    if schema_node.get("type") == "array" and "items" in schema_node:
        item_schema = schema_node["items"]
        if item_schema.get("type") == "object":
            # For arrays, we use `[]` notation
            np = f"{prefix}[]" if prefix else "[]"
            keys.update(_flatten_schema_keys(item_schema, prefix=f"{np}."))
            
    return keys


def _flatten_payload_keys(payload: dict | list, prefix=""):
    """Extract flattened keys from actual raw python dicts."""
    keys = set()
    if isinstance(payload, dict):
        for k, v in payload.items():
            full = f"{prefix}{k}" if prefix else k
            keys.add(full)
            keys.update(_flatten_payload_keys(v, prefix=f"{full}."))
    elif isinstance(payload, list):
        if len(payload) > 0 and isinstance(payload[0], (dict, list)):
            np = f"{prefix}[]" if prefix else "[]"
            # Just sample the first item for strict mapping to OpenAPI `items`
            keys.update(_flatten_payload_keys(payload[0], prefix=f"{np}."))
    return keys


def load_openapi_spec(spec_path: Path):
    with open(spec_path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="FranklinWH OpenAPI HAR Processor")
    parser.add_argument("--hars", default="hars", help="Directory containing .har captures")
    parser.add_argument("--spec", default="docs/franklinwh_openapi.json", help="Current OpenAPI JSON spec")
    parser.add_argument("--mode", choices=["fast", "pedantic"], default="fast", help="Parsing mode")
    parser.add_argument("--out", default="unmapped_endpoints.json", help="Output dump sandbox file")
    args = parser.parse_args()

    har_dir = Path(args.hars)
    spec_path = Path(args.spec)
    
    if not har_dir.is_dir():
        logging.error(f"HAR dir not found: {har_dir}")
        return
        
    if not spec_path.is_file():
        logging.error(f"Spec file not found: {spec_path}")
        return

    logging.info(f"Loading official OpenAPI spec: {spec_path}")
    spec = load_openapi_spec(spec_path)
    defined_paths = spec.get("paths", {})

    logging.info(f"Scanning `{har_dir}`... Mode: {args.mode.upper()}")
    
    unmapped_operations = {}     # For --fast (totally missing URLs)
    unmapped_schemas = {}        # For --pedantic (missing keys in known URLs)
    
    analyzed_hars = 0
    extracted_responses = 0

    for har_file in har_dir.glob("*.har"):
        analyzed_hars += 1
        with open(har_file, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                logging.warning(f"Corrupt HAR: {har_file.name}")
                continue
                
        entries = data.get("log", {}).get("entries", [])
        for e in entries:
            req = e.get("request", {})
            res = e.get("response", {})
            
            method = req.get("method", "").lower()
            url_str = req.get("url", "")
            if "franklinwh.com" not in url_str or method == "options":
                continue
                
            status = res.get("status")
            if status != 200:
                continue
                
            parsed_url = urlparse(url_str)
            path = parsed_url.path
            
            # Explicitly drop static assets and web redirects
            if "hes-gateway" not in path and "app-mobile" not in path and "newApi" not in path:
                continue
            
            # FAST MODE: Just check if the (Path, Method) is officially known
            if args.mode in ("fast", "pedantic"):
                if path not in defined_paths or method not in defined_paths[path]:
                    signature = f"{method.upper()} {path}"
                    if signature not in unmapped_operations:
                        unmapped_operations[signature] = {"examples": []}
                    unmapped_operations[signature]["examples"].append(url_str)
                    continue
                    
            # PEDANTIC MODE: Check nested json payload keys against the spec
            if args.mode == "pedantic":
                mime = res.get("content", {}).get("mimeType", "")
                if "application/json" not in mime:
                    continue
                    
                text_content = res.get("content", {}).get("text", "")
                if not text_content:
                    continue
                    
                try:
                    payload = json.loads(text_content)
                except json.JSONDecodeError:
                    continue
                    
                extracted_responses += 1
                
                # Fetch official schema for this endpoint
                try:
                    op_schema = defined_paths[path][method]["responses"]["200"]["content"]["application/json"]["schema"]
                    official_keys = _flatten_schema_keys(op_schema)
                except KeyError:
                    official_keys = set()
                    
                payload_keys = _flatten_payload_keys(payload)
                
                missing = payload_keys - official_keys
                if missing:
                    sig = f"{method.upper()} {path}"
                    if sig not in unmapped_schemas:
                        unmapped_schemas[sig] = set()
                    unmapped_schemas[sig].update(missing)

    logging.info(f"Processed {analyzed_hars} HAR captures.")
    
    output_dump = {}
    if unmapped_operations:
        logging.warning(f"FAST: Found {len(unmapped_operations)} totally undocumented API endpoint structures!")
        output_dump["new_endpoints"] = list(unmapped_operations.keys())
    
    if unmapped_schemas and args.mode == "pedantic":
        logging.warning(f"PEDANTIC: Analyzed {extracted_responses} successful JSON responses.")
        diffs = {k: list(v) for k, v in unmapped_schemas.items()}
        output_dump["new_keys"] = diffs
        logging.warning(f"PEDANTIC: Found {len(unmapped_schemas)} endpoints containing nested schema drift!")
        
    if not output_dump:
        logging.info("No scheme drift detected! Official openapi spec matches physical captures.")
    else:
        out_path = Path(args.out)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output_dump, f, indent=4)
        logging.info(f"Dumped unmapped footprints to sandbox: {out_path}")


if __name__ == "__main__":
    main()
