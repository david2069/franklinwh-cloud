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

## ~~sendMqtt Command Type Mapping~~ (COMPLETED)

*This task has been fully executed. A strict `MqttCmd(IntEnum)` abstraction layer has been merged into `models.py` tracking all physical numeric relays, and `docs/MQTT_CMD_CATALOG.md` has been rewritten with strict anchoring indexes to the core Python mixins.*
