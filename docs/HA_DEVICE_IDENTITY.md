# Home Assistant Device Identity

For anyone building a Home Assistant integration on `franklinwh-cloud`.

`franklinwh-cloud` is a library and CLI. It creates no Home Assistant devices, entities,
`unique_id`s or MQTT topics itself. This page states the rule that integrations built on
it follow.

## The rule

**One Home Assistant device per integration per aGate. Never a merged device.**

A site can run several FranklinWH integrations at once: Cloud, Direct Connect (local)
and Modbus. Each one creates its **own** device for the same aGate, and the integration
word appears in both the device name and its identifier.

| Integration | Device name | Device identifier |
|---|---|---|
| **Cloud** (built on this library) | `FranklinWH Cloud <short8>` | `<prefix>_cloud_<FULL_SERIAL>` |
| Direct Connect | `FranklinWH Direct <short8>` | `<prefix>_direct_<FULL_SERIAL>` |
| Modbus | `FranklinWH Modbus <short8>` | `<prefix>_modbus_<FULL_SERIAL>` |

- `<short8>` is the **last 8 characters** of the aGate serial number.
- `<FULL_SERIAL>` is the whole serial number.
- The `unique_id` prefix, MQTT topic root and MQTT client ID must also be distinct for
  each integration.

## Source of truth

The full write-up, with rationale and examples, is maintained in the Modbus Bridge
repository: `docs/ha-device-identity.md` in **franklinwh-modbus-bridge** (from v0.2.4).
This page summarises it; if the two ever disagree, the bridge document wins.
