"""Steps B and C — unified Smart Circuit and Generator views.

Config (cmdType 311) and live metrics (353/354) had always been separate
methods behind separate CLI commands, and the generator had no command at all.
"""

import contextlib
import io
import json

import pytest
from unittest.mock import AsyncMock

from franklinwh_cloud.mixins.devices import DevicesMixin
from franklinwh_cloud.models import SmartCircuitDetail

CFG_PAYLOAD = {
    "Sw1Mode": 1, "Sw1Name": "Fridge", "Sw1ProLoad": 1, "Sw1SocLowSet": 20,
    "Sw1MsgType": 0,
    "Sw1Time": ["2000-01-01 06:30", "2000-01-01 09:00",
                "2000-01-01 17:00", "2000-01-01 21:30"],
    "Sw1TimeEn": [1, 1, 0, 0], "Sw1TimeSet": [1, 0, 1, 0],
    "Sw2Mode": 0, "Sw2Name": "Pool", "Sw2ProLoad": 0, "Sw2SocLowSet": 100,
    "Sw2MsgType": 0,
}
METRICS = {"smart_circuits": [
    {"id": 1, "current": 5, "voltage": 2400, "power": 120, "energy": 900},
]}
GEN_CFG = {"genStat": 1, "genEn": 1, "genStartSoc": 20, "genStopSoc": 80}
GEN_METRICS = {"generator": {"power": 0, "voltage": 2, "current": 0, "frequency": 500}}


class _Client(DevicesMixin):
    def __init__(self, cfg=CFG_PAYLOAD, metrics=METRICS, gen_cfg=GEN_CFG,
                 gen_metrics=GEN_METRICS, metrics_error=None, gen_cfg_error=None):
        self._cfg, self._metrics = cfg, metrics
        self._gen_cfg, self._gen_metrics = gen_cfg, gen_metrics
        self._metrics_error, self._gen_cfg_error = metrics_error, gen_cfg_error

    async def get_smart_circuits(self):
        return {i: SmartCircuitDetail.from_api_payload(self._cfg, i)
                for i in (1, 2) if f"Sw{i}Mode" in self._cfg}

    async def get_accessories_power_info(self, option=1):
        if self._metrics_error:
            raise self._metrics_error
        return self._metrics if str(option) == "1" else self._gen_metrics

    async def get_generator_info(self):
        if self._gen_cfg_error:
            raise self._gen_cfg_error
        return self._gen_cfg


# ── step B: smart circuit detail ─────────────────────────────────────

async def test_config_and_metrics_arrive_together():
    d = await _Client().get_smart_circuit_detail()
    one = d["circuits"][0]
    assert one["config"]["is_on"] is True
    assert one["metrics"]["power"] == 120


async def test_a_circuit_without_metrics_is_none_not_zeroed():
    """"Not reported" must stay distinguishable from "reading zero"."""
    d = await _Client().get_smart_circuit_detail()
    assert d["circuits"][1]["metrics"] is None


async def test_restricting_to_one_circuit():
    d = await _Client().get_smart_circuit_detail(1)
    assert [c["id"] for c in d["circuits"]] == [1]


async def test_metrics_failure_still_returns_configuration():
    d = await _Client(metrics_error=RuntimeError("mqtt")).get_smart_circuit_detail()
    assert d["source"]["metrics_available"] is False
    assert d["circuits"][0]["config"]["mode"] == 1
    assert d["circuits"][0]["metrics"] is None


async def test_schedule_pairing_is_declared_unverified():
    """AP-14 — four entries may be two windows or four slots; unestablished."""
    d = await _Client().get_smart_circuit_detail(1)
    assert d["circuits"][0]["schedule"]["pairing"] == "unverified"


async def test_time_set_is_passed_through_undeciphered():
    d = await _Client().get_smart_circuit_detail(1)
    assert d["circuits"][0]["schedule"]["raw_time_set"] == [1, 0, 1, 0]


async def test_metrics_are_not_scaled():
    d = await _Client().get_smart_circuit_detail(1)
    m = d["circuits"][0]["metrics"]
    assert m["voltage"] == 2400, "must not be divided"
    assert "raw" in m["scale"]


# ── step C: generator detail ─────────────────────────────────────────

async def test_generator_config_and_metrics_together():
    d = await _Client().get_generator_detail()
    assert d["config"]["genStartSoc"] == 20
    assert d["metrics"]["power"] == 0


async def test_generator_frequency_is_converted_and_raw_is_kept():
    """freq is the ONE established divisor: tenths, 500 = 50.0 Hz."""
    d = await _Client().get_generator_detail()
    assert d["metrics"]["frequency_hz"] == 50.0
    assert d["metrics"]["frequency"] == 500


async def test_generator_attribution_is_marked_inferred():
    """The 354 generator fields are unprefixed and attributed by position."""
    d = await _Client().get_generator_detail()
    assert "INFERRED" in d["metrics"]["attribution"]


async def test_generator_survives_missing_config():
    d = await _Client(gen_cfg_error=RuntimeError("nope")).get_generator_detail()
    assert d["config"] == {}
    assert d["metrics"] is not None


# ── CLI ──────────────────────────────────────────────────────────────

async def _cli(mod, client, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        await mod.run(client, **kw)
    return buf.getvalue()


async def test_sc_detail_shows_metrics_and_schedule():
    from franklinwh_cloud.cli_commands import sc

    out = await _cli(sc, _Client(), json_output=False, detail=True)
    assert "Fridge" in out
    assert "06:30" in out
    assert "120" in out


async def test_sc_detail_says_not_reported_rather_than_zero():
    from franklinwh_cloud.cli_commands import sc

    out = await _cli(sc, _Client(), json_output=False, detail=True)
    assert "not reported" in out


async def test_sc_without_detail_is_unchanged():
    """The default view must not become the detail view."""
    from franklinwh_cloud.cli_commands import sc

    out = await _cli(sc, _Client(), json_output=False)
    assert "Smart Circuits — Detail" not in out


async def test_gen_renders_config_and_frequency():
    from franklinwh_cloud.cli_commands import gen

    out = await _cli(gen, _Client(), json_output=False)
    assert "50.0 Hz" in out
    assert "raw 500" in out


async def test_gen_surfaces_the_attribution_caveat():
    from franklinwh_cloud.cli_commands import gen

    out = await _cli(gen, _Client(), json_output=False)
    assert "INFERRED" in out


async def test_gen_json_is_machine_readable():
    from franklinwh_cloud.cli_commands import gen

    out = await _cli(gen, _Client(), json_output=True)
    assert json.loads(out)["config"]["genStat"] == 1


def test_gen_is_registered_on_the_cli():
    from franklinwh_cloud.cli import build_parser

    p = build_parser()
    assert p.parse_args(["gen"]).command == "gen"
    assert p.parse_args(["generator"]).command == "generator"


def test_sc_detail_flags_are_registered():
    from franklinwh_cloud.cli import build_parser

    ns = build_parser().parse_args(["sc", "--detail", "--circuit", "2"])
    assert ns.detail is True and ns.circuit == 2


def test_no_write_path_is_exposed_by_gen():
    """Step C is read-only; --mode is step D and needs sign-off."""
    from franklinwh_cloud.cli import build_parser

    with pytest.raises(SystemExit):
        build_parser().parse_args(["gen", "--mode", "1"])
