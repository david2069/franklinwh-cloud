"""Power control and grid status API methods."""

import json
import logging

from franklinwh_cloud.models import GridStatus
from franklinwh_cloud.api import DEFAULT_URL_BASE

logger = logging.getLogger("franklinwh_cloud")


class PowerMixin:
    """Grid status, power control, and PCS settings."""

    async def set_grid_status(self, status: GridStatus, soc: int = 5):
        """Set the grid status of the FranklinWH gateway.

        Parameters
        ----------
        status : GridStatus
            The desired grid status to set.
        """
        url = self.url_base + "hes-gateway/terminal/updateOffgrid"
        payload = {
            "gatewayId": self.gateway,
            "offgridSet": int(status != GridStatus.NORMAL),
            "offgridSoc": soc,
        }
        await self._post(url, json.dumps(payload))

    async def get_grid_status(self):
        """Get the offgrid reason codes.

        Returns
        -------
        dict
            offgridSet: 1 = Go Off-Grid requested, 0 = No Off-Grid request
            offGridState: 1 = Simulated Off-Grid, 0 = Grid Connected
        """
        url = self.url_base + "hes-gateway/terminal/selectOffgrid"
        params = {"gatewayId": self.gateway, "type": 0}
        data = await self._get(url, params)
        return data

    async def get_power_control_settings(self):
        """Get PCS Battery Grid Import, Grid Export and Solar PV settings.

        https://www.franklinwh.com/support/overview/grid-charge--export/
        """
        url = self.url_base + f"hes-gateway/terminal/tou/getPowerControlSetting?gatewayId={self.gateway}&lang=EN_US"
        data = await self._get(url, None)
        return data

    async def set_power_control_settings(self, globalGridDischargeMax, globalGridChargeMax):
        """Set PCS Battery Global Grid Import, Grid Export and Solar PV settings.

        https://www.franklinwh.com/support/overview/grid-charge--export/

        Parameters
        ----------
        globalGridDischargeMax : float
            -1 = Unlimited, 0 = Disabled, >= 0.1 = kW limit
        globalGridChargeMax : float
            -1 = Unlimited, 0 = Disabled, >= 0.1 = kW limit
        """
        logger.info(f"set_power_control_settings: globalGridChargeMax    = {globalGridChargeMax}")
        match globalGridChargeMax:
            case -1:
                option = "Unlimited grid charging set"
            case 0:
                option = "DISABLED: No Grid discharging/export"
            case _:
                option = "Invalid value supplied - must be -1,0 or in the range of >= 0.1 to 100000 only"
                if float(globalGridChargeMax):
                    globalGridChargeMax = float(globalGridChargeMax)
                    if globalGridChargeMax < 0.1 or globalGridChargeMax > 100000:
                        option = "value specified be >= 0.1 kw to 100000.0 kW"
                    else:
                        option = "Grid charging permitted"

        logger.info(f"set_power_control_settings: globalGridDischargeMax = {option}")

        logger.info(f"set_power_control_settings: globalGridChargeMax    = {globalGridDischargeMax}")
        match globalGridDischargeMax:
            case -1:
                option = "Unlimited grid discharging set"
            case 0:
                option = "Solar only (and no battery) export"
            case _:
                option = "Invalid value supplied - must be -1,0 or in the range of >= 0.1 to 100000 only"
                if float(globalGridDischargeMax):
                    globalGridDischargeMax = float(globalGridDischargeMax)
                    if globalGridDischargeMax < 0.1 or globalGridDischargeMax > 100000:
                        option = "value specified be >= 0.1 kw to 100000.0 kW"
                    else:
                        option = "Exporting is limited to {globalGridDischargeMax}"

        logger.info(f"set_power_control_settings: globalGridChargeMax = {option}")

        url = DEFAULT_URL_BASE + f"hes-gateway/terminal/tou/setPowerControl?gatewayId={self.gateway}"
        payload = {
            "gatewayId": self.gateway,
            "globalGridDischargeMax": globalGridDischargeMax,
            "globalGridChargeMax": globalGridChargeMax,
        }
        logger.info(f"setPowerControlSetting: Sending request to set PCS Power Control settings URL: {url} with payload: {payload}")
        data = await self._post(url, payload)
        return data

    async def get_pcs_hintinfo(self, dispatchIdList):
        """Get PCS Hint Information.

        Retrieves the desired power settings associated with the TOU dispatch
        codes in the current schedule.

        Parameters
        ----------
        dispatchIdList : list[int]
            TOU dispatch code IDs to query (e.g. [6, 8])

        Returns
        -------
        dict
            PCS capability hints for the specified dispatch IDs
        """
        url = self.url_base + "hes-gateway/terminal/tou/getPcsHintInfo"
        params = {}
        payload = {
            "gatewayId": self.gateway,
            "dispatchIdList": [dispatchIdList],
        }
        res = await self._post(url, payload=payload, params=params)
        return res
