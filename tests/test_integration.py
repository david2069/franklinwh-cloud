"""Live integration tests to strictly structurally validate offline mock schemas.

This suite compares live API payloads against offline tests/fixtures/*.json
to proactively detect forward-compatible schema drift or hard failures due 
to missing (hallucinated) keys in the mocked offline suite.
"""

import json
import pytest
from pathlib import Path

from franklinwh_cloud.cli_commands.support import _collect_keys
from tests.test_live import credentials_available, live_client  # noqa: F401
from tests.test_live import FRANKLIN_USERNAME, FRANKLIN_PASSWORD


pytestmark = pytest.mark.live


def load_fixture(filename: str) -> dict:
    """Load a given mock json from the fixture directory."""
    fixture_path = Path(__file__).parent / "fixtures" / filename
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


def assert_schema_matches(live_payload: dict, mock_payload: dict, endpoint_name: str):
    """Assert that 100% of the mock schema keys physically exist in the live payload.

    Provides forward-compatibility (live payload can have *more* keys),
    but halts tests if the mocked fixture contains attributes the live API does not.
    """
    mock_keys = set(_collect_keys(mock_payload))
    live_keys = set(_collect_keys(live_payload))
    
    missing_keys = mock_keys - live_keys
    if missing_keys:
        raise AssertionError(
            f"Schema Drift Detected on {endpoint_name}. "
            f"Live API is missing {len(missing_keys)} expected keys: {sorted(list(missing_keys))}"
        )


@pytest.mark.asyncio
async def test_login_schema_matches(live_client):  # noqa: F811
    """Validate that POST /api/user/login structurally matches the mocked response."""
    if not credentials_available():
        pytest.skip()

    # Note: live_client fixture already performed login.
    # The raw parsed login payload resides in auth.info
    live_payload = live_client.fetcher.info
    mock_payload = load_fixture("login_response.json").get("result", {})
    
    # Run subset schema validation
    assert_schema_matches(live_payload, mock_payload, "POST /api/user/login")


@pytest.mark.asyncio
async def test_composite_info_schema_matches(live_client):  # noqa: F811
    """Validate get_device_composite_info() schema matches composite_info.json."""
    if not credentials_available():
        pytest.skip()
    
    live_payload = await live_client.get_device_composite_info()
    mock_payload = load_fixture("composite_info.json")
    
    assert_schema_matches(live_payload, mock_payload, "get_device_composite_info()")


@pytest.mark.asyncio
async def test_tou_dispatch_detail_schema_matches(live_client):  # noqa: F811
    """Validate get_tou_dispatch_detail() matches tou_dispatch_detail_multi_season.json."""
    if not credentials_available():
        pytest.skip()
        
    live_payload = await live_client.get_tou_dispatch_detail()
    mock_payload = load_fixture("tou_dispatch_detail_multi_season.json")
    
    assert_schema_matches(live_payload, mock_payload, "get_tou_dispatch_detail()")


@pytest.mark.asyncio
async def test_switch_usage_schema_matches(live_client):  # noqa: F811
    """Validate get_smart_circuits_info() matches switch_usage.json."""
    if not credentials_available():
        pytest.skip()
        
    live_payload = await live_client.get_smart_circuits_info()
    result_data = live_payload.get("result", []) if isinstance(live_payload, dict) else live_payload
    if not result_data:  # Skip if live api returns [] due to no smart switches
        pytest.skip("No smart circuits configured on live gateway")
        
    mock_payload = load_fixture("switch_usage.json")
    if isinstance(mock_payload, dict) and "result" in mock_payload:
        mock_payload = mock_payload["result"]
    elif isinstance(mock_payload, list) and len(mock_payload) > 0 and isinstance(mock_payload[0], dict) and "data" in mock_payload[0]:
        # sometimes smart circuits mock is a raw list
        pass
        
    assert_schema_matches(live_payload, mock_payload, "get_smart_circuits_info()")
