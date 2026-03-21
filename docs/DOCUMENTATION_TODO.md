# Documentation Future TODO

> API documentation and reference material — not currently in scope.

---

## API Endpoint Inventory & OpenAPI Spec

Inventory all FranklinWH Energy Cloud API endpoints from HAR captures and map to `client.py` usage.

### Steps

1. **HAR inventory** — Extract all REST endpoints from captured HAR files
2. **Map to `client.py`** — Cross-reference which endpoints we already use vs. undiscovered
3. **OpenAPI spec** — Create a formal OpenAPI 3.0 spec for each endpoint with:
   - Request/response schemas
   - Redacted sample payloads
   - Authentication requirements
4. **GitHub Wiki** — Publish as `FranklinWH Energy Cloud API` wiki pages

---

## sendMqtt Command Type Mapping

Inventory all `sendMqtt` requests and create an equivalent mapping:

| cmdType | Function | Description |
|---------|----------|-------------|
| 1 | `get_network_info` | Network configuration |
| 3 | `get_wifi_config` | WiFi AP/station config |
| 211 | `get_bms_info` | Battery management (type 2 + 3) |
| ... | ... | ... |

- Create `CmdType` enum with descriptions
- Document which `type` sub-values each cmdType supports
- Map to existing `client.py` method names

### Deliverables

- `docs/api_reference.md` — REST endpoint reference
- `docs/mqtt_commands.md` — sendMqtt cmdType reference
- GitHub Wiki pages with redacted samples
