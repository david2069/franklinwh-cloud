"""DEF-DIAG-SIGNAL-SOURCE and DEF-DIAG-RSSI-DBM.

`diag` reported `WiFi Signal: 0.0%` and `4G/Mobile Signal: 0.0%` on a gateway
where cmdType 339 reported 72% WiFi and 317 reported operatorRSSI 22 with the
SIM active. Both came from runtimeData (203), which is unpopulated on this
firmware. It also printed operatorRSSI with a `dBm` unit; it is a 0-52 vendor
scale (gotcha G3).
"""

import types

import pytest

from franklinwh_cloud.mixins.devices import _connectivity_signals


def _stats(wifi=0.0, mobile=0.0):
    return types.SimpleNamespace(
        current=types.SimpleNamespace(wifi_signal=wifi, mobile_signal=mobile)
    )


# 339 extended, as returned by the live gateway
CONN_EXTENDED = {"WifiSignalStrength": 72, "4GConnectBSStatus": 0}
CONN_SHORT = {"routerStatus": 0, "netStatus": 0, "awsStatus": 0}
NET_INFO = {"operator": {"rssi": 22}}


# ── the reported defect ──────────────────────────────────────────────

def test_wifi_signal_prefers_the_339_extended_payload():
    """The live case: runtimeData says 0.0, 339 says 72."""
    sig = _connectivity_signals(CONN_EXTENDED, NET_INFO, _stats(wifi=0.0))
    assert sig["wifi_signal"] == 72
    assert sig["wifi_signal_source"] == "339"


def test_wifi_falls_back_to_runtimedata_without_the_extended_payload():
    sig = _connectivity_signals(CONN_SHORT, NET_INFO, _stats(wifi=61))
    assert sig["wifi_signal"] == 61
    assert sig["wifi_signal_source"] == "203/runtimeData"


def test_cellular_raw_reading_is_exposed():
    sig = _connectivity_signals(CONN_EXTENDED, NET_INFO, _stats())
    assert sig["mobile_signal_raw"] == 22
    assert sig["mobile_signal_scale"] == "0-52"


# ── the unit trap this fix must not fall into ────────────────────────

def test_the_0_52_reading_never_overwrites_the_percentage_key():
    """operatorRSSI is NOT a percentage.

    Writing 22 into `mobile_signal` would repeat the dBm-mislabelling class
    of defect rather than fix it, and would silently change the unit of a
    public key that downstream consumers read as 0-100.
    """
    sig = _connectivity_signals(CONN_EXTENDED, NET_INFO, _stats(mobile=45))
    assert sig["mobile_signal"] == 45, "the % key keeps its % source"
    assert sig["mobile_signal"] != sig["mobile_signal_raw"]


def test_existing_public_keys_are_preserved():
    """Additive only — no downstream consumer may break."""
    sig = _connectivity_signals(CONN_EXTENDED, NET_INFO, _stats())
    assert "wifi_signal" in sig and "mobile_signal" in sig


def test_missing_operator_block_does_not_crash():
    sig = _connectivity_signals(CONN_EXTENDED, {}, _stats())
    assert sig["mobile_signal_raw"] is None


def test_null_operator_block_does_not_crash():
    """Same present-but-null trap as DEF-DIAG-GATEWAY-NONE-GUARD."""
    sig = _connectivity_signals(CONN_EXTENDED, {"operator": None}, _stats())
    assert sig["mobile_signal_raw"] is None


def test_zero_wifi_from_339_is_honoured_not_treated_as_missing():
    """0% is a real reading; only an absent key triggers the fallback."""
    sig = _connectivity_signals({"WifiSignalStrength": 0}, NET_INFO,
                                _stats(wifi=61))
    assert sig["wifi_signal"] == 0
    assert sig["wifi_signal_source"] == "339"


# ── render: no dBm, no fake percentage ───────────────────────────────

from franklinwh_cloud.cli_commands import diag
from tests.test_diag_gateway_nulls import _NullClient, FULL_COMPOSITE


class _SignalClient(_NullClient):
    async def get_connectivity_overview(self, deep_scan=False):
        return {
            "primary": {"id": 3, "name": "WiFi", "ip": "192.168.0.110"},
            "backups": [],
            "signals": _connectivity_signals(CONN_EXTENDED, NET_INFO, _stats()),
        }

    async def get_network_info(self):
        return {"operator": {"mac": "AA:BB:CC:DD:EE:FF", "rssi": 22,
                             "dns": "8.8.8.8"},
                "currentNetType": 3, "wifi": {}, "eth0": {}, "eth1": {}}


async def _diag_out(capsys):
    await diag.run(_SignalClient(FULL_COMPOSITE), json_output=False)
    return capsys.readouterr().out


async def test_diag_no_longer_prints_a_dbm_unit_for_cellular(capsys):
    out = await _diag_out(capsys)
    assert "dBm" not in out, "operatorRSSI is a 0-52 vendor scale (G3)"


async def test_diag_shows_the_real_wifi_percentage(capsys):
    out = await _diag_out(capsys)
    assert "72%" in out
    assert "WiFi Signal" in out


async def test_diag_shows_cellular_on_its_own_scale_not_as_a_percentage(capsys):
    out = await _diag_out(capsys)
    assert "22/52" in out
    assert "4G/Mobile Signal:" in out.replace("\x1b[2m", "").replace("\x1b[0m", "") \
        or "4G/Mobile Signal" in out


async def test_diag_no_longer_reports_zero_signal_on_a_live_link(capsys):
    """The reported symptom: 0.0% beside a working WiFi link."""
    out = await _diag_out(capsys)
    assert "0.0%" not in out
