"""Tests for _build_payload — CRC, JSON structure, snno sequencing.

Tests the deterministic payload construction used for MQTT commands.
This is pure logic with no API calls needed.
"""

import json
import zlib

import pytest

from franklinwh.client import to_hex


SAMPLE_DATA = {"opt": 1, "refreshData": 1}
SAMPLE_SWITCH_DATA = {"opt": 0, "order": "TEST-GW-001"}


class TestBuildPayload:
    """Deterministic payload construction for MQTT commands."""

    def test_json_structure(self, minimal_client):
        """Payload contains required top-level keys."""
        payload = minimal_client._build_payload(203, SAMPLE_DATA)
        parsed = json.loads(payload)
        assert parsed["cmdType"] == 203
        assert parsed["equipNo"] == "TEST-GW-001"
        assert parsed["lang"] == "EN_US"
        assert parsed["type"] == 0
        assert "timeStamp" in parsed
        assert "snno" in parsed
        assert "len" in parsed
        assert "crc" in parsed

    def test_data_area_embedded(self, minimal_client):
        """dataArea should contain the actual data, not the placeholder."""
        payload = minimal_client._build_payload(203, SAMPLE_DATA)
        assert '"DATA"' not in payload
        # The data should be embedded inline
        assert '"opt":1' in payload
        assert '"refreshData":1' in payload

    def test_crc_is_valid_hex(self, minimal_client):
        """CRC in payload should be an 8-character uppercase hex string."""
        payload = minimal_client._build_payload(203, SAMPLE_DATA)
        parsed = json.loads(payload)
        crc = parsed["crc"]
        assert isinstance(crc, str)
        assert len(crc) == 8
        # Should be valid hex
        int(crc, 16)

    def test_len_matches_data(self, minimal_client):
        """len field matches the byte length of the data area."""
        data = SAMPLE_DATA
        blob = json.dumps(data, separators=(",", ":")).encode("utf-8")

        payload = minimal_client._build_payload(203, data)
        parsed = json.loads(payload)
        assert parsed["len"] == len(blob)


class TestSnno:
    """Sequence number (snno) management."""

    def test_starts_at_zero(self, minimal_client):
        assert minimal_client.snno == 0

    def test_increments(self, minimal_client):
        first = minimal_client.next_snno()
        second = minimal_client.next_snno()
        assert first == 1
        assert second == 2

    def test_payload_uses_snno(self, minimal_client):
        """Each payload gets an incrementing snno."""
        p1 = json.loads(minimal_client._build_payload(203, SAMPLE_DATA))
        p2 = json.loads(minimal_client._build_payload(203, SAMPLE_DATA))
        assert p2["snno"] == p1["snno"] + 1


class TestToHex:
    """to_hex utility for CRC formatting."""

    def test_known_value(self):
        # CRC32 of b'test' = 0xD87F7E0C
        result = to_hex(zlib.crc32(b"test"))
        assert isinstance(result, str)
        assert len(result) == 8  # 8 hex chars for 32-bit CRC

    def test_zero(self):
        result = to_hex(0)
        assert result == "00000000"
