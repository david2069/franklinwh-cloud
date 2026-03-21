# CLI Future TODO

> Feature ideas and analysis items — not currently in scope.

---

## `support --info` — Account & Site Hierarchy

Show the full FranklinWH account tree: user → site → aGate group → aGates → accessories.

```
john.doe@anymail.com (UserId: 99999)
  │
  └── Smallsville (SiteId: 1203)
        │
        ├── Group: "Main House" (GroupId: 501)
        │     │
        │     ├── FHP1 (aGate: 10060006AXXXXXXXXX)
        │     │     ├── aPower1 (Serial: 10050013AXXXXXXXXX)
        │     │     ├── Solar PV: 6.6kW
        │     │     └── Smart Circuit × 2
        │     │
        │     └── FHP2 (aGate: 10060006A02F24170092)
        │           └── aPower1 (Serial: ...)
        │
        └── Group: (ungrouped)
              └── ...
```

### Data Sources

| Level | API | Key Fields |
|-------|-----|------------|
| User | Login response | `userId`, `email` |
| Site | `get_home_gateway_list` | `name`, `groupId`, `groupName` |
| aGate | `get_home_gateway_list` | `id`, `connType`, `status` |
| Accessories | `get_accessory_list` | type, serial, status |
| aPower | `runtimeData.fhpSn` | serial numbers |
| Solar | `runtimeData` | `solarVo`, PV config |

### CLI Concept

```bash
franklinwh-cli support --info          # show account tree
franklinwh-cli support --info --json   # JSON export
```

---

## Generic Command Scheduling

Extend `--schedule` to run any CLI command, not just nettest:

```bash
franklinwh-cli support --schedule daily --command "diag"
franklinwh-cli support --schedule "0:30" --command "control --charge"
```

---

## Event-Driven Watch Daemon

Poll runtimeData, trigger CLI actions on thresholds:

```bash
franklinwh-cli watch --rules rules.yml
```

See design doc: `automation_platform_design.md` (session artifacts).

---

## HA Entity Import

Import entity schema from FEM or HA for use in rules:

```bash
franklinwh-cli watch --import-entities --fem-url http://192.168.0.247:9091
franklinwh-cli watch --import-entities --ha-url ws://homeassistant.local:8123
```

Cached to `~/.franklinwh/entities.json` — portable, editable, offline.

---

## LaunchDaemon / System-Level Scheduling

Current scheduler is user-level (LaunchAgent / user crontab).
For always-on operation, support system-level scheduling:
- **macOS**: LaunchDaemon in `/Library/LaunchDaemons/` (requires admin)
- **Linux**: System crontab or systemd timer (requires root)

---

## C.A.F.E. / HA YAML Compatibility

Make rules format compatible with [C.A.F.E.](https://github.com/FezVrasta/cafe-hass) visual automation editor.
See design doc: `automation_platform_design.md`.

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

### sendMqtt Command Type Mapping

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

