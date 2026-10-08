"""DEF-ENERGY-PERIOD-PARAM — getFhpElectricData reads the date from a type-dependent key.

Day (type 1) reads ``dayTime``; week/month/year/total (2-5) read ``startDate`` and
return empty arrays when sent ``dayTime``. Evidence:
tests/results/2026-10-08_DEF-ENERGY-PERIOD-PARAM_live_probe.txt and the hars/ corpus.
"""

import pytest

from franklinwh_cloud.client import Client
from franklinwh_cloud.mixins.stats import electric_date_key


@pytest.fixture
def client():
    c = Client.__new__(Client)
    c.gateway = "TEST-GW-001"
    c.url_base = "https://energy.franklinwh.com/"
    c.calls = []

    async def _get(url, params=None):
        c.calls.append((url, params))
        return {"code": 200, "result": {"deviceTimeArray": []}}

    c._get = _get
    return c


@pytest.mark.parametrize("data_type, key", [
    (1, "dayTime"), (2, "startDate"), (3, "startDate"), (4, "startDate"), (5, "startDate"),
    ("1", "dayTime"), ("3", "startDate"),
])
def test_electric_date_key(data_type, key):
    assert electric_date_key(data_type) == key


@pytest.mark.parametrize("data_type, key", [(1, "dayTime"), (2, "startDate"),
                                            (3, "startDate"), (4, "startDate"),
                                            (5, "startDate")])
async def test_get_power_details_sends_type_dependent_key(client, data_type, key):
    await client.get_power_details(type=data_type, timeperiod="2026-09-07")
    url, params = client.calls[-1]
    assert url.endswith("api-energy/electric/getFhpElectricData")
    assert params == {"gatewayId": "TEST-GW-001", "type": data_type, key: "2026-09-07"}


@pytest.mark.parametrize("data_type, key", [(1, "dayTime"), (2, "startDate"),
                                            (3, "startDate"), (4, "startDate"),
                                            (5, "startDate")])
async def test_get_electric_data_sends_type_dependent_key(client, data_type, key):
    await client.get_electric_data(data_type=data_type, day_time="2026-09-07")
    url, params = client.calls[-1]
    assert url.endswith("api-energy/electric/getFhpElectricData")
    assert params == {"gatewayId": "TEST-GW-001", "type": str(data_type), key: "2026-09-07"}
