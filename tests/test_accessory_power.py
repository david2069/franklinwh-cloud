"""cmdType 353/354 accessory power — DEF-ACCESSORY-POWER-OPTION-TYPE.

`get_accessories_power_info(option=1)` declared an **int** default while every
branch compared against a **str**, so the default call matched nothing and
returned the raw payload instead of the documented Smart Circuits view. It went
unnoticed because the only in-repo caller passes `"0"`, which works by luck.

The same method hardcoded circuits 1 and 2, so a US three-circuit system was
under-reported.
"""

import json

import pytest
from unittest.mock import AsyncMock

from franklinwh_cloud.mixins.devices import DevicesMixin


# Verbatim cmdType 354 payload from the corpus (AU, two circuits).
PAYLOAD_2CH = {
    "opt": 0, "result": 0,
    "Sw1Volt": 1004, "Sw2Volt": 0,
    "CarSWCurr": 0, "CarSWPower": 2,
    "CarSWExpEnergy": 4698, "CarSWImpEnergy": 178,
    "SW1Curr": 0, "SW2Curr": 0,
    "SW1ExpPower": 0, "SW2ExpPower": 0,
    "SW1ExpEnergy": 0, "SW2ExpEnergy": 0,
    "CarSwConsSupExpEnerge": 0,
    "power": 0, "curr": 0, "volt": 2, "freq": 500, "genpowerGen": 0,
}

# Hypothetical three-circuit shape. NOT from a capture — no three-circuit
# system has been observed. Used only to prove discovery is key-driven.
PAYLOAD_3CH = {
    **PAYLOAD_2CH,
    "SW3Curr": 5, "Sw3Volt": 2400, "SW3ExpPower": 120, "SW3ExpEnergy": 900,
}


class _Client(DevicesMixin):
    def __init__(self, payload=PAYLOAD_2CH):
        self._mqtt_send = AsyncMock(
            return_value={"result": {"dataArea": json.dumps(payload)}})

    def _build_payload(self, cmd, dataArea):
        return {"cmdType": int(cmd), "dataArea": dataArea}


# ── the type defect ──────────────────────────────────────────────────

async def test_the_int_default_now_returns_smart_circuits():
    """Previously fell through to the raw payload."""
    r = await _Client().get_accessories_power_info()
    assert "smart_circuits" in r


@pytest.mark.parametrize("option", [1, "1"])
async def test_int_and_str_behave_identically(option):
    r = await _Client().get_accessories_power_info(option)
    assert "smart_circuits" in r


@pytest.mark.parametrize("option,key", [
    (2, "v2l"), ("2", "v2l"), (3, "generator"), ("3", "generator"),
])
async def test_every_branch_accepts_both_types(option, key):
    r = await _Client().get_accessories_power_info(option)
    assert key in r


@pytest.mark.parametrize("option", [0, "0"])
async def test_raw_still_returns_the_whole_payload(option):
    """The one caller in this repo passes "0" — must not regress."""
    r = await _Client().get_accessories_power_info(option)
    assert r["freq"] == 500
    assert "smart_circuits" not in r


async def test_an_unknown_option_still_falls_back_to_raw():
    r = await _Client().get_accessories_power_info(99)
    assert r["freq"] == 500


# ── circuit discovery ────────────────────────────────────────────────

async def test_two_circuit_gateway_reports_two():
    r = await _Client(PAYLOAD_2CH).get_accessories_power_info(1)
    assert [c["id"] for c in r["smart_circuits"]] == [1, 2]


async def test_a_third_circuit_is_picked_up_when_present():
    """Hardcoding 1 and 2 under-reported a US three-circuit system."""
    r = await _Client(PAYLOAD_3CH).get_accessories_power_info(1)
    assert [c["id"] for c in r["smart_circuits"]] == [1, 2, 3]
    third = r["smart_circuits"][2]
    assert third["current"] == 5 and third["voltage"] == 2400


async def test_absent_circuits_are_omitted_not_zero_filled():
    """A circuit that does not exist must not appear as a zeroed one."""
    payload = {k: v for k, v in PAYLOAD_2CH.items() if not k.startswith(("SW2", "Sw2"))}
    r = await _Client(payload).get_accessories_power_info(1)
    assert [c["id"] for c in r["smart_circuits"]] == [1]


async def test_the_vendor_casing_inconsistency_is_handled():
    """Current is SW1Curr but voltage is Sw1Volt — different capitalisation."""
    r = await _Client(PAYLOAD_2CH).get_accessories_power_info(1)
    assert r["smart_circuits"][0]["voltage"] == 1004


# ── values stay raw ──────────────────────────────────────────────────

async def test_no_scaling_is_applied_to_unestablished_fields():
    """Only `freq` has a confirmed divisor; voltages do not. AP-14."""
    r = await _Client(PAYLOAD_2CH).get_accessories_power_info(1)
    assert r["smart_circuits"][0]["voltage"] == 1004, "must not be divided by 10"


async def test_generator_fields_are_passed_through_raw():
    r = await _Client(PAYLOAD_2CH).get_accessories_power_info(3)
    assert r["generator"]["frequency"] == 500, "raw tenths, not 50.0"
