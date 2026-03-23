# Device Catalog Architecture — Hybrid A+B

> **Decision:** 2026-03-23 | **Feature:** FEAT-CLI-DISCOVER-VERBOSE

## Approach

**Hybrid JSON catalog + Python logic** — the hardware catalog (data) is extracted
to a bundled JSON file; compatibility rules and flag logic stay in Python.

### What goes in JSON (`const/device_catalog.json`)

- **Model registry** — aGate IDs (100-104), aPower IDs (0-6), accessory IDs (201-302)
- **Per-model metadata** — name, SKU, country, generation, type
- **Compatibility matrix** — which accessories work with which aGates
- **Programme/entrance flag definitions** — key → display name, category, description
- **API field annotations** — what each static API field means and its category

### What stays in Python (`const/devices.py`)

- **V2L eligibility logic** — V1 SC + Gen Module = eligible; V2 SC = built-in; AU = never
- **Generation detection** — hw_version → gen1/gen2 mapping
- **Lookup functions** — `get_model_info(hw_ver)`, `is_v2l_eligible(...)`, etc.
- **Flag analysis** — _what's missing_ diagnostic logic

### Why this split

| Concern | JSON | Python |
|---------|------|--------|
| Adding a new aGate model | ✅ Edit one JSON entry | ❌ Would need code change |
| Adding a new accessory | ✅ Edit one JSON entry | ❌ Would need code change |
| Changing V2L eligibility rules | ❌ Not pure data | ✅ Logic belongs in code |
| Community contributions | ✅ JSON editable by anyone | ❌ Requires Python knowledge |
| Type safety | ❌ No checking | ✅ IDE autocomplete |
| Versioned with package | ✅ Bundled in wheel/sdist | ✅ Same |

### Integrity

- **No hash/signature needed** — the JSON ships bundled with the package (not downloaded)
- **Validated at import** — Python loader validates required keys on startup
- **Version field** — JSON includes a `catalog_version` for tracking changes

## Related Documents

- API field registry: `docs/API_FIELD_REGISTRY.md`
- FEM device model reference: `franklinwh-energy-manager/docs/device_model_reference.md`
- Current constants: `franklinwh_cloud/const/devices.py`
