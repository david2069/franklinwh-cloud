"""Account, site, and notification API methods."""

import logging
from datetime import datetime


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
        url = self.url_base + "hes-gateway/terminal/getHomeGatewayList"
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
            "affiliateCompany": (info.get("affiliateCompany") or []),
            "userTypes": (info.get("userTypes") or []),
            "currentType": info.get("currentType"),
            "roles": (info.get("roles") or []),
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
        return (data.get("result") or {})

    async def get_unread_count(self):
        """Get the count of unread push notification messages.

        https://www.franklinwh.com/support/overview/system-alerts-and-notifications/
        """
        url = self.url_base + "hes-gateway/terminal/selectTerPushMessageUnreadCount"
        data = await self._get(url, params=None, suppress_params=True)
        return data

    async def get_notifications(self, pageNum=1, pageSize=10):
        """Get push notification messages for the gateway.

        https://www.franklinwh.com/support/overview/system-alerts-and-notifications/
        """
        url = self.url_base + "hes-gateway/terminal/selectTerPushMessageListApp"
        params = {"equipNo": self.gateway, "pageNum": pageNum, "pageSize": pageSize, "lang": "en_US"}
        data = await self._get(url, params=params)
        return data["result"]

    async def get_notification_settings(self, lang: str = "EN_US"):
        """Get the notification settings for the gateway.

        Includes on/off and DND mode settings for notification types.

        https://www.franklinwh.com/support/overview/system-alerts-and-notifications/

        Returns
        -------
        dict
            Notification event classifications and their enabled states
        """
        url = self.url_base + "hes-gateway/terminal/selectEventClassification"
        params = {"lang": lang}
        data = await self._get(url, params=params, suppress_gateway=True)
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
            logger.warning(f"get_site_device_info: unexpected kwargs: userId={userId}, email={username}")
        else:
            res = self.fetcher.info
            userId = res["userId"]
            res = self.fetcher.info
            logger.debug(f"get_site_device_info: session info = {res}")
            username = res["email"]

        logger.debug("get_site_device_info: Using current login session")
        url = self.url_base + "hes-gateway/terminal/site/list/siteAndDeviceInfo"
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
        url = self.url_base + "hes-gateway/terminal/v2/warrantyInfo"
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
        url = self.url_base + "hes-gateway/terminal/getEquipmentLocationDetail"
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
        url = self.url_base + "hes-gateway/newApi/api-user/app/resource/getUserResources/v2"
        params = {"gatewayId": self.gateway}
        data = await self._get(url, params=params)
        return data.get("data") if "data" in data else data.get("result", data)

    async def query_terminal_user_info(self):
        """Get the logged-in user terminal account information.

        Returns
        -------
        dict
            User account email and email notification receive flags
        """
        url = self.url_base + "hes-gateway/terminal/v2/queryTerminalUserInfo"
        data = await self._get(url, suppress_params=True, suppress_gateway=True)
        return data.get("result", data)

    async def logout(self, refresh_token: str = ""):
        """Log out the current session.

        Parameters
        ----------
        refresh_token : str, optional
            Refresh token to invalidate
        """
        url = self.url_base + "hes-gateway/terminal/v2/loginOut"
        user_id = self.fetcher.info.get("userId") if self.fetcher.info else None
        account = self.fetcher.info.get("email") if self.fetcher.info else None
        payload = {
            "userId": user_id,
            "account": account,
            "accountType": 0,
            "refreshToken": refresh_token,
        }
        data = await self._post(url, payload, suppress_params=True, suppress_gateway=True)
        return data

    async def update_fcm_token(self, token: str, identity: str, lang: str = "EN_US"):
        """Update the user's Firebase Cloud Messaging (FCM) token.

        Parameters
        ----------
        token : str
            FCM device token
        identity : str
            Unique device identifier (e.g. android/ios uuid)
        lang : str, optional
            Locale language code, defaults to "EN_US"
        """
        url = self.url_base + "hes-gateway/terminal/updateTerUserFcmToken"
        params = {
            "token": token,
            "identity": identity,
            "lang": lang,
        }
        data = await self._post(url, None, params=params, suppress_gateway=True)
        return data

    async def get_messages_by_type(self, event_types: str, page_num: int = 1, page_size: int = 10):
        """Get push notification messages filtered by event types.

        Parameters
        ----------
        event_types : str
            Comma-separated message event types (e.g. "17,43,44")
        page_num : int, optional
            Page number, defaults to 1
        page_size : int, optional
            Results per page, defaults to 10
        """
        url = self.url_base + "hes-gateway/terminal/listDeviceMessagesByType"
        params = {
            "pageNum": page_num,
            "pageSize": page_size,
            "eventTypes": event_types,
            "gatewayId": self.gateway,
        }
        data = await self._get(url, params=params)
        return data.get("result", data)

    async def get_run_log_list(self, country_id: int):
        """Get the system run log configuration/rules by country ID.

        Parameters
        ----------
        country_id : int
            Country identifier (e.g. 1 = US, 3 = AU)
        """
        url = self.url_base + "hes-gateway/common/country/selectRunLogList"
        params = {"countryId": country_id}
        data = await self._get(url, params=params, suppress_gateway=True)
        return data.get("result", data)

    async def get_alarm_codes_list(self):
        """Get list of all alarms generated by the aGate.

        Returns
        -------
        list
            Complete list of alarm codes with detailed information
        """
        url = self.url_base + "hes-gateway/common/selectDeviceRunLogList"
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
        url = self.url_base + "hes-gateway/terminal/selectProgramFlag"
        params = {"gatewayId": self.gateway}
        data = await self._get(url, params=params)
        return (data.get("result") or [])

    async def get_benefit_info(self, data_type: int = 1, day_time: str = None):
        """Get benefit/savings information.

        Returns carbon reduction, EV mileage conversion, tree conversion,
        battery/solar feed-in and load earnings.

        Parameters
        ----------
        data_type : int
            1 = daily, 2 = monthly, 3 = yearly
        day_time : str, optional
            Date string (YYYY-MM-DD). Defaults to today.

        Returns
        -------
        dict
            {fuelConversion, evMileageConversion, treeConversion,
             carbonReduction, batFeedEarnList, solarFeedEarnList, ...}
        """
        if day_time is None:
            from datetime import date
            day_time = date.today().isoformat()
        url = self.url_base + "hes-gateway/terminal/bill/electric/selectBenefitInfo"
        params = {
            "gatewayId": self.gateway,
            "type": str(data_type),
            "dayTime": day_time,
        }
        data = await self._get(url, params=params)
        return (data.get("result") or {})

    async def get_gateway_alarm(self):
        """Get active gateway alarms.

        Returns any alarms active at the time this is called.

        Returns
        -------
        dict
            Active gateway alarm details at time of call
        """
        url = self.url_base + "hes-gateway/terminal/selectGatewayAlarm"
        params = {"gatewayId": self.gateway}
        data = await self._get(url, params=params)
        return data["result"]

    async def get_grid_profile_info(self, requestType=1, systemId=None):
        """Get utility grid compliance information.

        Parameters
        ----------
        requestType : int
            1 = Compliance list, 2 = Active compliance details
        systemId : int, optional
            The ID of the compliance profile to fetch details for.
            If requestType=2 and systemId is not provided, the active profile's currentId is used.
        """
        match int(requestType):
            case 1:
                url = self.url_base + "hes-gateway/terminal/newCompliance/getComplianceNameList"
                params = {"gatewayId": self.gateway}
            case 2:
                if systemId is None:
                    # Fetch the active profile to get its ID
                    list_data = await self.get_grid_profile_info(requestType=1)
                    systemId = list_data.get("currentId", 0)

                url = self.url_base + "hes-gateway/terminal/newCompliance/getComplianceDetailById"
                params = {"gatewayId": self.gateway, "systemId": systemId}

        try:
            data = await self._get(url, params=params)
            return (data.get("result") or {})
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
        url = self.url_base + f"hes-gateway/common/obtainGeographyList?countryId={countryId}"
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
                url = self.url_base + "hes-gateway/terminal/backupHistorySummary"
                params = {"gatewayId": self.gateway}
            case "2":
                url = self.url_base + "hes-gateway/terminal/backupHistorySummary"
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
                url = self.url_base + f"hes-gateway/terminal/smartAssistant?gatewayId={self.gateway}&requestType={requestType}"
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
                url = self.url_base + f"hes-gateway/terminal/smartAssistant?gatewayId={self.gateway}&requestType={requestType}&query={query}"
                data = await self._post(url, payload=payload)

        return data

    async def get_electric_data(self, data_type: int = 1, day_time: str = None):
        """Get electricity usage data (kWh arrays).

        Returns time-series arrays for solar, grid, battery, and load power.

        Parameters
        ----------
        data_type : int
            1 = daily, 2 = monthly, 3 = yearly
        day_time : str, optional
            Date string (YYYY-MM-DD). Defaults to today.

        Returns
        -------
        dict
            {deviceTimeArray, kwhSuArray, kwhGenArray, kwhUtiInArray,
             kwhUtiOutArray, kwhFhpChgArray, kwhFhpDiArray, kwhLoadArray, ...}
        """
        if day_time is None:
            from datetime import date
            day_time = date.today().isoformat()
        url = self.url_base + "api-energy/electric/getFhpElectricData"
        params = {
            "gatewayId": self.gateway,
            "type": str(data_type),
            "dayTime": day_time,
        }
        data = await self._get(url, params=params)
        return data

    async def get_charge_history(self, page_num: int = 1, page_size: int = 15):
        """Get battery charge/discharge session history.

        Returns a paginated list of charge events with SoC, energy,
        and time details.

        Parameters
        ----------
        page_num : int
            Page number (default: 1)
        page_size : int
            Results per page (default: 15)

        Returns
        -------
        dict
            {result: [{id, chargeType, energy, startSoc, endSoc,
             chargeDate, startTime, endTime, ...}], total: int}
        """
        url = self.url_base + "hes-gateway/terminal/iotChargePowers"
        params = {
            "gatewayId": self.gateway,
            "pageNum": str(page_num),
            "pageSize": str(page_size),
        }
        data = await self._get(url, params=params)
        return data
