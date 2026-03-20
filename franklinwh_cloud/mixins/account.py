"""Account, site, and notification API methods."""

import logging
from datetime import datetime

from franklinwh_cloud.api import DEFAULT_URL_BASE

logger = logging.getLogger("franklinwh_cloud")


class AccountMixin:
    """Site info, notifications, alarms, and account methods."""

    async def get_home_gateway_list(self):
        """Get the list of Home Gateways associated with the account.

        Returns
        -------
        dict
            Home Gateway information: email, location, timezone,
            aGate count, status (online/offline), model, firmware,
            connectivity type (4G/WiFi/Ethernet)
        """
        url = DEFAULT_URL_BASE + "hes-gateway/terminal/getHomeGatewayList"
        data = await self._get(url, suppress_params=True, suppress_gateway=True)
        return data

    async def siteinfo(self):
        """Get site info from the fetcher's login info.

        Returns
        -------
        dict
            User ID, email, version, distributor, installer, roles,
            password update flags, survey status
        """
        info = self.fetcher.info
        return {
            "userId": info["userId"],
            "email": info["email"],
            "version": info.get("version"),
            "distributorId": info.get("distributorId"),
            "installerId": info.get("installerId"),
            "affiliateCompany": info.get("affiliateCompany", []),
            "userTypes": info.get("userTypes", []),
            "currentType": info.get("currentType"),
            "roles": info.get("roles", []),
            "passwordUpdateFlag": info.get("passwordUpdateFlag"),
            "ninetyDaysPwdUpdate": info.get("ninetyDaysPwdUpdate"),
            "surveyFlag": info.get("surveyFlag"),
            "needAgreeTerm": info.get("needAgreeTerm"),
            "failureVersion": info.get("failureVersion"),
            "serviceVoltageFlag": info.get("serviceVoltageFlag"),
        }

    async def get_entrance_info(self):
        """Get customer static setup for aGate configuration.

        Provides details on schemes/restrictions: sgipEntrance, bbEntrance, pcsEntrance,
        grid-tied/connected gridFlag, solarFlag, TOU tariff settings.
        """
        url = self.url_base + "hes-gateway/terminal/tou/getEntranceInfo"
        data = await self._get(url)
        return data.get("result", {})

    async def get_unread_count(self):
        """Get the count of unread push notification messages.

        https://www.franklinwh.com/support/overview/system-alerts-and-notifications/
        """
        url = DEFAULT_URL_BASE + "hes-gateway/terminal/selectTerPushMessageUnreadCount"
        data = await self._get(url, params=None, suppress_params=True)
        return data

    async def get_notifications(self, pageNum=1, pageSize=10):
        """Get push notification messages for the gateway.

        https://www.franklinwh.com/support/overview/system-alerts-and-notifications/
        """
        url = DEFAULT_URL_BASE + "hes-gateway/terminal/selectTerPushMessageListApp"
        params = {"equipNo": self.gateway, "pageNum": pageNum, "pageSize": pageSize, "lang": "en_US"}
        data = await self._get(url, params=params)
        return data["result"]

    async def get_notification_settings(self):
        """Get the notification settings for the gateway.

        Includes on/off and DND mode settings for notification types.

        https://www.franklinwh.com/support/overview/system-alerts-and-notifications/

        Returns
        -------
        dict
            Notification event classifications and their enabled states
        """
        url = DEFAULT_URL_BASE + "hes-gateway/terminal/selectTerPusselectEventClassification"
        params = {"gatewayId": self.gateway, "lang": "en_US"}
        data = await self._get(url, params=params)
        return data.get("result", data)

    async def get_site_and_device_info(self, **kwargs):
        """Get site and device information for the logged-in account.

        Parameters
        ----------
        userId : str, optional
            User ID (auto-detected from login session if omitted)
        email : str, optional
            Email address (auto-detected from login session if omitted)

        Returns
        -------
        dict
            Site and installed devices information
        """
        userId = kwargs.get("userId", None)
        username = kwargs.get("email", None)

        if userId is not None:
            logger.info("FAILED: Not sure to process kwargs: userId = {userId} or username = {username}")
        else:
            res = self.fetcher.info
            userId = res["userId"]
            res = self.fetcher.info
            logger.info(f"res = {res}")
            username = res["email"]

        logger.info("Using current login session")
        url = DEFAULT_URL_BASE + "hes-gateway/terminal/site/list/siteAndDeviceInfo"
        params = {"pageNum": 1, "pageSize": 999, "userAccount": username, "userId": userId}
        data = await self._get(url, params=params, supressGateway=True)
        return data

    async def get_warranty_info(self):
        """Get warranty info for devices associated with this gateway.

        Returns
        -------
        dict
            Warranty information including start/end dates and status
        """
        url = DEFAULT_URL_BASE + "hes-gateway/terminal/v2/warrantyInfo"
        params = {"gatewayId": self.gateway}
        data = await self._get(url, params=params)
        return data

    async def get_equipment_location(self):
        """Get location info for devices associated with this gateway.

        Returns
        -------
        dict
            GPS coordinates and location details for installed equipment
        """
        url = DEFAULT_URL_BASE + "hes-gateway/terminal/getEquipmentLocationDetail"
        params = {"gatewayId": self.gateway}
        data = await self._get(url, params=params)
        return data["result"]

    async def get_user_resources(self):
        """Get resources associated with the current user account.

        Note: This appears to be a forerunner for a new Franklin API.
        May change in future releases.

        Returns
        -------
        dict
            Resource information and permissions
        """
        url = DEFAULT_URL_BASE + "hes-gateway/terminal/newApi/api-user/app/getUserResources/v2"
        params = {"gatewayId": self.gateway}
        data = await self._get(url, params=params)
        return data["result"]

    async def get_alarm_codes_list(self):
        """Get list of all alarms generated by the aGate.

        Returns
        -------
        list
            Complete list of alarm codes with detailed information
        """
        url = DEFAULT_URL_BASE + "hes-gateway/common/selectDeviceRunLogList"
        params = {"gatewayId": self.gateway}
        data = await self._get(url, params=params)
        return data["result"]

    async def get_programme_info(self):
        """Get VPP and/or utility programmes associated with this aGate.

        Returns
        -------
        list
            Programmes enabled and other detailed information
        """
        url = DEFAULT_URL_BASE + "hes-gateway/terminal/selectProgramFlag"
        params = {"gatewayId": self.gateway}
        data = await self._get(url, params=params)
        return data.get("result", [])

    async def get_benefit_info(self):
        """Get benefit earnings information.

        Returns
        -------
        dict
            Benefit earnings data for the account
        """
        url = DEFAULT_URL_BASE + "hes-gateway/bill/selectBenefitInfo"
        params = {"gatewayId": self.gateway}
        data = await self._get(url, params=params)
        return data.get("result", [])

    async def get_gateway_alarm(self):
        """Get active gateway alarms.

        Returns any alarms active at the time this is called.

        Returns
        -------
        dict
            Active gateway alarm details at time of call
        """
        url = DEFAULT_URL_BASE + "hes-gateway/terminal/selectGatewayAlarm"
        params = {"gatewayId": self.gateway}
        data = await self._get(url, params=params)
        return data["result"]

    async def get_grid_profile_info(self, requestType=1):
        """Get utility grid compliance information.

        Parameters
        ----------
        requestType : int
            1 = Compliance list, 2 = Active compliance details
        """
        match requestType:
            case 1:
                url = DEFAULT_URL_BASE + "hes-gateway/terminal/newCompliance/getComplianceNameList"
                params = {"gatewayId": self.gateway}
            case 2:
                url = DEFAULT_URL_BASE + "hes-gateway/terminal/newCompliance/getComplianceDetailById"
                params = {"gatewayId": self.gateway, "systemId": 0}

        try:
            data = await self._get(url, params=params)
            return data.get("result", {})
        except KeyError:
            logger.warning(f"get_grid_profile_info: Response missing expected keys for requestType {requestType}")
            return {}

    async def get_geography_list(self, countryId=None):
        """Get states/provinces for a country or all countries.

        Parameters
        ----------
        countryId : int, optional
            Country ID. Returns states/provinces for that country.
            None returns all countries.

        Returns
        -------
        dict
            List of states, provinces, etc. for the specified country
        """
        url = DEFAULT_URL_BASE + f"hes-gateway/common/obtainGeographyList?countryId={countryId}"
        data = await self._get(url)
        return data

    async def get_backup_history(self, requestType, pageNum=1, pageSize=10):
        """Get backup history.

        Parameters
        ----------
        requestType : str
            1 = Summary, 2 = Full history
        """
        match requestType:
            case "1":
                url = DEFAULT_URL_BASE + "hes-gateway/terminal/backupHistorySummary"
                params = {"gatewayId": self.gateway}
            case "2":
                url = DEFAULT_URL_BASE + "hes-gateway/terminal/backupHistorySummary"
                params = {"gatewayId": self.gateway, "pageNum": pageNum, "pageSize": pageSize}

        data = await self._get(url, params=params)
        return data["result"]

    async def smart_assistant(self, requestType=1, query=""):
        """Invoke the smart assistant.

        Parameters
        ----------
        requestType : int
            1 = Get example queries, 2 = Send query
        """
        match requestType:
            case "1":
                url = DEFAULT_URL_BASE + f"hes-gateway/terminal/smartAssistant?gatewayId={self.gateway}&requestType={requestType}"
                data = await self._get(url)
            case "2":
                payload = {
                    "action": 1,
                    "content": query,
                    "userId": self.fetcher.info.get("userId"),
                    "deviceId": self.gateway,
                    "currentTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "sceneFlag": 1,
                }
                url = DEFAULT_URL_BASE + f"hes-gateway/terminal/smartAssistant?gatewayId={self.gateway}&requestType={requestType}&query={query}"
                data = await self._post(url, payload=payload)

        return data
