"""get_accessories() sends the gateway with each per-gateway accessory endpoint."""

import pytest

from franklinwh_cloud.mixins.devices import DevicesMixin

GW = "99900000000000009999"        # mock serial (PII policy)


class _Client(DevicesMixin):
    url_base = "https://example.invalid/"
    gateway = GW

    async def _get(self, url, params=None):
        return {"url": url, "params": params}


async def test_common_list_sends_gateway_and_lang_like_the_app():
    r = await _Client().get_accessories()
    assert r["url"].endswith("hes-gateway/common/getAccessoryList")
    assert r["params"] == {"gatewayId": GW, "lang": "en_US"}


@pytest.mark.parametrize("option, path, params", [
    (2, "hes-gateway/terminal/getIotAccessoryList", None),
    (3, "hes-gateway/manage/getEquipmentList", {"gatewayId": GW}),
    (4, "hes-gateway/terminal/getIotAccessoryList", {"gatewayId": GW}),
])
async def test_other_options_unchanged(option, path, params):
    r = await _Client().get_accessories(option)
    assert r["url"].endswith(path) and r["params"] == params
