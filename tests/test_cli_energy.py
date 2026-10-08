"""FEAT-CLI-ENERGY — `franklinwh-cli energy` period resolution and rendering (offline)."""

import argparse
import json
from datetime import date

import pytest

from franklinwh_cloud.cli import build_parser
from franklinwh_cloud.cli_commands import energy
from franklinwh_cloud import cli_output

TODAY = date(2026, 10, 8)  # a Thursday

ELECTRIC_YEAR = {
    "deviceTimeArray": [f"2026-{m:02d}" for m in range(1, 13)],
    "kwhSuArray": [598.443, 450.731, 542.98, 529.88, 363.87, 350.95,
                   527.09, 626.94, 732.17, 197.55, None, None],
    "kwhUtiInArray": [58.74] * 10 + [None, None],
    "kwhGenArray": [0.0] * 10 + [None, None],
    "kwhV2lArray": [0.0] * 12,
}


@pytest.mark.parametrize("period, on, expected", [
    ("day", date(2026, 9, 15), (1, date(2026, 9, 15))),
    ("week", date(2026, 9, 10), (2, date(2026, 9, 7))),     # Thu → Mon
    ("week", date(2026, 9, 7), (2, date(2026, 9, 7))),      # Mon stays
    ("week", date(2026, 9, 13), (2, date(2026, 9, 7))),     # Sun → previous Mon
    ("month", date(2026, 9, 15), (3, date(2026, 9, 1))),
    ("year", date(2025, 6, 30), (4, date(2025, 1, 1))),
    ("ytd", date(2020, 5, 5), (4, date(2026, 1, 1))),       # --date ignored
    ("lifetime", date(2020, 5, 5), (5, TODAY)),
])
def test_resolve_period(period, on, expected):
    assert energy.resolve_period(period, on, TODAY) == expected


def test_build_rows_keeps_nulls_and_aligns_columns():
    names, rows = energy.build_rows(ELECTRIC_YEAR, energy.ENERGY_COLUMNS)
    assert names[0] == "date" and "solar_kwh" in names
    assert len(rows) == 12
    assert rows[0]["solar_kwh"] == 598.443
    assert rows[11]["solar_kwh"] is None
    assert rows[0]["home_kwh"] is None          # field absent from response → None, not 0


def test_build_rows_all_fields_appends_raw_names():
    names, _ = energy.build_rows(ELECTRIC_YEAR, energy.ENERGY_COLUMNS, all_fields=True)
    assert names[-1] == "kwhV2lArray"
    assert "kwhSuArray" not in names            # already mapped, not duplicated


def test_build_rows_empty_result():
    names, rows = energy.build_rows({}, energy.ENERGY_COLUMNS)
    assert rows == [] and names[0] == "date"


def test_trim_ytd_and_totals():
    names, rows = energy.build_rows(ELECTRIC_YEAR, energy.ENERGY_COLUMNS)
    rows = energy.trim_ytd(rows, TODAY)
    assert [r["date"] for r in rows][-1] == "2026-10"
    t = energy.totals(rows, names)
    assert t["solar_kwh"] == round(sum(ELECTRIC_YEAR["kwhSuArray"][:10]), 3)
    assert t["home_kwh"] is None                # no values → None, not 0


def test_render_csv_nulls_are_empty_cells():
    names = ["date", "solar_kwh"]
    text = energy.render_csv(names, [{"date": "2026-11", "solar_kwh": None},
                                     {"date": "2026-10", "solar_kwh": 1.5}])
    assert text == "date,solar_kwh\n2026-11,\n2026-10,1.5\n"


def test_render_table_has_total_row(monkeypatch):
    monkeypatch.setattr(cli_output, "_color_enabled", False)
    names, rows = energy.build_rows(ELECTRIC_YEAR, energy.ENERGY_COLUMNS[:1])
    out = energy.render_table(names, rows, energy.totals(rows, names), "T")
    assert out.splitlines()[1].split() == ["date", "solar"]
    assert out.splitlines()[-1].startswith("total")


def test_power_columns_use_api_spelling():
    names, rows = energy.build_rows(
        {"deviceTimeArray": ["2026-10-07 00:00:00"], "powerSolarGirdArray": [0.2]},
        energy.POWER_COLUMNS, time_column="time")
    assert names[0] == "time"
    assert rows[0]["solar_to_grid_kw"] == 0.2


# ── run() ────────────────────────────────────────────────────────────

class FakeClient:
    def __init__(self):
        self.calls = []

    async def get_power_details(self, type, timeperiod):
        self.calls.append(("details", type, timeperiod))
        return ELECTRIC_YEAR

    async def get_power_by_day(self, dayTime):
        self.calls.append(("by_day", dayTime))
        return {"deviceTimeArray": ["2026-10-07 00:00:00"], "socArray": [50.0]}


def _args(argv):
    return build_parser().parse_args(["energy", *argv])


async def test_run_week_queries_monday(capsys):
    client = FakeClient()
    assert await energy.run(client, _args(["--period", "week", "--date", "2026-09-10",
                                           "--format", "csv"])) == 0
    assert client.calls == [("details", 2, "2026-09-07")]
    assert capsys.readouterr().out.startswith("date,solar_kwh,")


async def test_run_global_json_flag(capsys):
    client = FakeClient()
    args = build_parser().parse_args(["--json", "energy", "--period", "year", "--date", "2026-03-03"])
    assert await energy.run(client, args) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["type"] == 4 and data["query_date"] == "2026-01-01" and data["unit"] == "kWh"
    assert len(data["rows"]) == 12 and "totals" in data


async def test_run_5min_uses_power_by_day(capsys):
    client = FakeClient()
    assert await energy.run(client, _args(["--interval", "5min", "--date", "2026-10-07",
                                           "--format", "csv"])) == 0
    assert client.calls == [("by_day", "2026-10-07")]
    assert capsys.readouterr().out.splitlines()[1].startswith("2026-10-07 00:00:00,50.0")


async def test_run_5min_rejects_other_periods():
    client = FakeClient()
    assert await energy.run(client, _args(["--period", "week", "--interval", "5min"])) == 2
    assert client.calls == []


async def test_run_bad_date():
    assert await energy.run(FakeClient(), _args(["--date", "2026-13-01"])) == 2


async def test_run_writes_output_file(tmp_path):
    out = tmp_path / "y.csv"
    assert await energy.run(FakeClient(), _args(["--period", "year", "--date", "2026-01-01",
                                                 "--format", "csv", "-o", str(out)])) == 0
    assert out.read_text().count("\n") == 13     # header + 12 months
