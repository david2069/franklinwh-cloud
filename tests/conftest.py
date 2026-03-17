"""Shared test fixtures for franklinwh tests.

Provides mock clients, sample API responses, and common test helpers.
"""

import json
import pathlib

import pytest


FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_composite_info():
    """Load sample getDeviceCompositeInfo response."""
    with open(FIXTURES_DIR / "composite_info.json") as f:
        return json.load(f)


@pytest.fixture
def sample_switch_usage():
    """Load sample MQTT 353 switch usage response."""
    with open(FIXTURES_DIR / "switch_usage.json") as f:
        return json.load(f)


@pytest.fixture
def sample_login_response():
    """Load sample login API response."""
    with open(FIXTURES_DIR / "login_response.json") as f:
        return json.load(f)


@pytest.fixture
def minimal_client():
    """Create a minimal Client instance without real credentials.

    Uses Client.__new__ to bypass __init__ and sets only the attributes
    needed for unit-testable methods like _build_payload, next_snno, etc.
    """
    from franklinwh_cloud.client import Client
    from franklinwh_cloud.metrics import ClientMetrics

    c = Client.__new__(Client)
    c.gateway = "TEST-GW-001"
    c.snno = 0
    c.url_base = "https://energy.franklinwh.com/"
    c.token = "test-token-abc123"
    c.metrics = ClientMetrics()
    return c
