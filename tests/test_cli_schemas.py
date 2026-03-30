"""Tests for CLI JSON output structure and schema validity."""
import jsonschema
from franklinwh_cloud.cli_output import _strip_nulls
from franklinwh_cloud.discovery import DeviceSnapshot, ElectricalInfo, AccessoriesInfo

def test_cli_output_strip_nulls():
    """Verify that the CLI json exporter successfully strips explicit nulls from empty arrays/fields."""
    
    # Simulate a snapshot with numerous missing/'null' parameters (like V2L absent, single phase)
    snap = DeviceSnapshot()
    snap.electrical = ElectricalInfo(v_l1=240.0, v_l2=None, frequency=None)  # None should be stripped
    snap.accessories = AccessoriesInfo(items=[], smart_circuits=None) # Empty list stays, None removed
    
    raw_dict = snap.to_dict()
    assert "v_l2" in raw_dict["electrical"]
    assert raw_dict["electrical"]["v_l2"] is None
    assert "smart_circuits" in raw_dict["accessories"]
    assert raw_dict["accessories"]["smart_circuits"] is None

    # Apply the new print formatter function
    clean = _strip_nulls(raw_dict)
    
    # Verify explicitly that JSON glitches (null) are evicted
    assert "v_l1" in clean["electrical"]
    assert "v_l2" not in clean["electrical"], "Null glitch v_l2 was not stripped!"
    assert "frequency" not in clean["electrical"]
    
    # Verify empty arrays gracefully remain
    assert "items" in clean["accessories"]
    assert clean["accessories"]["items"] == [], "Empty lists should be preserved, not converted to null!"
    assert "smart_circuits" not in clean["accessories"]
    
    # Define a strict schema requiring these structures to exist WITHOUT null
    schema = {
        "type": "object",
        "properties": {
            "electrical": {
                "type": "object",
                "properties": {
                    "v_l1": {"type": "number"},
                    "v_l2": {"type": "number"}
                },
                "required": ["v_l1"] # Only v_l1 is strictly required
            },
            "accessories": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {"type": "object"}
                    }
                },
                "required": ["items"]
            }
        }
    }
    
    # Prove the stripped dictionary is strictly valid against the JSON Schema
    jsonschema.validate(instance=clean, schema=schema)
