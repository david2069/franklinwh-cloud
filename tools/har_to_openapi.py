#!/usr/bin/env python3
import json
import os
import sys
from urllib.parse import urlparse
from collections import defaultdict

def extract_schema(value):
    """Infers the OpenAPI schema type for a given python scalar or structure."""
    if isinstance(value, dict):
        props = {}
        for k, v in value.items():
            props[k] = extract_schema(v)
        return {"type": "object", "properties": props}
    elif isinstance(value, list):
        if len(value) > 0:
            return {"type": "array", "items": extract_schema(value[0])}
        return {"type": "array", "items": {}}
    elif isinstance(value, str):
        return {"type": "string"}
    elif isinstance(value, bool):
        return {"type": "boolean"}
    elif isinstance(value, int):
        return {"type": "integer"}
    elif isinstance(value, float):
        return {"type": "number", "format": "float"}
    elif value is None:
        return {"nullable": True}
    return {}

def merge_schemas(s1, s2):
    """Deep merges two OpenAPI schema dictionaries."""
    if not s1: return s2
    if not s2: return s1
    
    if s1.get("type") == "object" and s2.get("type") == "object":
        new_props = dict(s1.get("properties", {}))
        for k, v in s2.get("properties", {}).items():
            if k in new_props:
                new_props[k] = merge_schemas(new_props[k], v)
            else:
                new_props[k] = v
        return {"type": "object", "properties": new_props}
    return s1

def build_openapi(har_paths):
    openapi = {
        "openapi": "3.0.3",
        "info": {"title": "FranklinWH Cloud API", "version": "1.0.0"},
        "servers": [{"url": "https://energy.franklinwh.com"}],
        "paths": defaultdict(lambda: defaultdict(dict)),
        "components": {"securitySchemes": {"BearerAuth": {"type": "http", "scheme": "bearer"}}}
    }

    for har_path in har_paths:
        print(f"Parsing: {har_path}...")
        try:
            with open(har_path, 'r', encoding='utf8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"Failed to load {har_path}: {e}")
            continue

        for entry in data.get('log', {}).get('entries', []):
            req = entry.get('request', {})
            res = entry.get('response', {})
            url = req.get('url', '')
            
            if 'energy.franklinwh.com' not in url:
                continue
                
            parsed = urlparse(url)
            path = parsed.path
            method = req.get('method', 'GET').lower()

            endpoint_def = openapi['paths'][path][method]
            if not endpoint_def:
                endpoint_def.update({
                    "summary": f"Generated {method.upper()} {path}",
                    "security": [{"BearerAuth": []}],
                    "responses": {"200": {"description": "Successful operation", "content": {"application/json": {}}}}
                })

            # Process Request Body
            post_data = req.get('postData', {})
            if post_data.get('mimeType', '').startswith('application/json'):
                try:
                    payload = json.loads(post_data.get('text', '{}'))
                    schema = extract_schema(payload)
                    req_content = endpoint_def.get("requestBody", {}).get("content", {})
                    if "application/json" not in req_content:
                        endpoint_def["requestBody"] = {
                            "content": {"application/json": {"schema": schema}}
                        }
                    else:
                        existing = req_content["application/json"]["schema"]
                        req_content["application/json"]["schema"] = merge_schemas(existing, schema)
                except json.JSONDecodeError:
                    pass

            # Process Response Body
            res_content = res.get('content', {})
            if res_content.get('mimeType', '').startswith('application/json'):
                try:
                    payload = json.loads(res_content.get('text', '{}'))
                    schema = extract_schema(payload)
                    res_schema = endpoint_def["responses"]["200"]["content"]["application/json"].get("schema", {})
                    endpoint_def["responses"]["200"]["content"]["application/json"]["schema"] = merge_schemas(res_schema, schema)
                except json.JSONDecodeError:
                    pass

    return openapi

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python har_to_openapi.py <har_file1> <har_file2> ...")
        sys.exit(1)
        
    openapi_doc = build_openapi(sys.argv[1:])
    
    with open('openapi.json', 'w', encoding='utf8') as f:
        json.dump(openapi_doc, f, indent=2)
    print(f"Successfully generated openapi.json (Contains {len(openapi_doc['paths'])} endpoints)!")
