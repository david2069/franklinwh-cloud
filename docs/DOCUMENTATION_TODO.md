# Documentation Future TODO

> API documentation and reference material — not currently in scope.

---

## ~~API Endpoint Inventory & OpenAPI Spec~~ (COMPLETED)

*This task has been fully executed. A complete audit of the June 2026 HTTPToolkit HAR capture has been performed, mapping all new endpoints (including system settings, AI dispatch, VPP eligibility, and JA12 compliance) directly to client mixin methods and documenting them in `API_ENDPOINTS_MAPPING.md`.*

---

## ~~sendMqtt Command Type Mapping~~ (COMPLETED)

*This task has been fully executed. A strict `MqttCmd(IntEnum)` abstraction layer has been merged into `models.py` tracking all physical numeric relays, and `docs/MQTT_CMD_CATALOG.md` has been rewritten with strict anchoring indexes to the core Python mixins.*

