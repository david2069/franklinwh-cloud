"""Storm and weather API methods."""

import logging

logger = logging.getLogger("franklinwh_cloud")


class StormMixin:
    """Storm Hedge and weather methods.

    https://www.franklinwh.com/support/overview/storm-hedge
    """

    async def get_storm_list(self, pageNum=1, pageSize=10):
        """Get a list of storm notifications."""
        url = self.url_base + "hes-gateway/terminal/weather/getStormList"
        params = {"equipNo": self.gateway, "pageNum": pageNum, "pageSize": pageSize, "lang": "en_US"}
        logger.info(f"get_storm_list: url={url}, params={params}")
        data = await self._get(url, params=params)
        return data

    async def get_progressing_storm_list(self):
        """Get progressing storm list details (if any)."""
        url = self.url_base + "hes-gateway/terminal/weather/getProgressingStormList"
        params = {"equipNo": self.gateway}
        data = await self._get(url, params=params)
        return data

    async def get_weather(self):
        """Get current brief weather details."""
        url = self.url_base + "hes-gateway/terminal/weather/getCurrentBriefWeather"
        params = {"equipNo": self.gateway}
        data = await self._get(url, params=params)
        return data

    async def get_storm_settings(self):
        """Get Storm Hedge settings."""
        url = self.url_base + "hes-gateway/terminal/weather/getStormSetting"
        params = {"equipNo": self.gateway}
        data = await self._get(url, params=params)
        return data

    async def set_storm_settings(self, stormEn=None, setAdvanceBackupTime=None, advanceTime=None, stormNoticeEn=None):
        """Set Storm Hedge settings.

        Parameters
        ----------
        stormEn : int, optional
            1 = Turn-on, 0 = Turn-off
        setAdvanceBackupTime : int, optional
            Advance time in minutes (30-300) to trigger Emergency Backup
        stormNoticeEn : int, optional
            0 = Auto-active enabled, 1 = Ask each time
        advanceTime : int, optional
            Notification sent 5-30 minutes before Emergency Charging
        """
        rc = True

        if stormEn is not None:
            url = self.url_base + "hes-gateway/terminal/weather/switchStorm"
            payload = {"equipNo": self.gateway, "stormEn": stormEn}
            data = await self._post(url, payload, supressParams=True, supressGateway=True)
            if data.get("code") == 200:
                mode = "enabled" if stormEn == 1 else "disabled"
                logger.info(f"Storm Hedge set to: {mode}")
            else:
                rc = False
                logger.error(f"Storm Hedge update to {stormEn} failed: {data.get('code')} {data.get('message')}")

        if setAdvanceBackupTime is not None:
            url = self.url_base + "hes-gateway/terminal/weather/setAdvanceBackupTime"
            payload = {"equipNo": self.gateway, "advanceBackupTime": setAdvanceBackupTime}
            data = await self._post(url, payload, supressParams=True, supressGateway=True)
            if data.get("code") == 200:
                logger.info(f"Advanced backup start set to {setAdvanceBackupTime} minutes")
            else:
                rc = False
                logger.error(f"Advanced backup update failed: {data.get('code')} {data.get('message')}")

        if stormNoticeEn is not None or advanceTime is not None:
            url = self.url_base + "hes-gateway/terminal/weather/setStormNotice"
            payload = {"equipNo": self.gateway}
            if stormNoticeEn is not None:
                payload["stormNoticeEn"] = stormNoticeEn
            if advanceTime is not None:
                payload["advanceTime"] = advanceTime
            data = await self._post(url, payload, supressParams=True, supressGateway=True)
            if data.get("code") == 200:
                logger.info("Storm notification settings updated")
            else:
                rc = False
                logger.error(f"Storm notification update failed: {data.get('code')} {data.get('message')}")

        return rc
