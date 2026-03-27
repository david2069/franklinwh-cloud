"""Device and accessory information API methods."""

import asyncio
import json
import logging
import warnings

from franklinwh_cloud.exceptions import BadRequestParsingError, DeviceTimeoutException

logger = logging.getLogger("franklinwh_cloud")


def _parse_mqtt_json(raw, cmd_type: int):
    """Parse JSON from an MQTT dataArea response with error handling.

    Parameters
    ----------
    raw : str
        Raw JSON string from the MQTT response dataArea.
    cmd_type : int
        The cmdType that produced this response (for error messages).

    Returns
    -------
    dict
        Parsed JSON data.

    Raises
    ------
    DeviceTimeoutException
        If the response cannot be parsed as valid JSON.
    """
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        raise DeviceTimeoutException(
            f"Invalid MQTT response for cmdType {cmd_type}: {e}"
        ) from e


class DevicesMixin:
    """Accessory, device, and hardware information methods."""

    async def get_accessories(self, option=1):
        """Get the list of accessories connected to the gateway.

        Parameters
        ----------
        option : int
            1 = Common accessory list (default)
            2 = IoT accessory list
            3 = Equipment list (by gateway)
            4 = IoT accessory list (by gateway)

        Returns
        -------
        dict
            List of connected accessories with details
        """
        params = None
        match option:
            case 2:
                url = self.url_base + "hes-gateway/terminal/getIotAccessoryList"
            case 3:
                url = self.url_base + "hes-gateway/manage/getEquipmentList"
                params = {"gatewayId": self.gateway}
            case 4:
                url = self.url_base + "hes-gateway/terminal/getIotAccessoryList"
                params = {"gatewayId": self.gateway}
            case _:
                url = self.url_base + "hes-gateway/common/getAccessoryList"
        return await self._get(url, params=params)

    async def get_power_cap_config_list(self):
        """Get gateway models and nameplate capabilities.

        Returns
        -------
        dict
            List of models with their rated capacity, charge power, and discharge power.
        """
        url = self.url_base + "hes-gateway/common/getPowerCapConfigList"
        return await self._get(url)

    async def get_device_run_log_list(self):
        """Get historical run logs and raw alarm codes.

        Returns
        -------
        dict
            List of device run logs including alarmCode, logName, and enLogName.
        """
        url = self.url_base + "hes-gateway/common/selectDeviceRunLogList"
        return await self._get(url)

    async def get_device_composite_info(self):
        """Get Gateway Composite Data to extract current runtime info, operating mode and details.

        This is the master data call used by get_stats() — returns runtime data,
        current work mode, solar info, alarms, relay states, and more.

        Returns
        -------
        dict
            Composite device data including runtimeData, solarHaveVo, currentWorkMode
        """
        url = self.url_base + f"hes-gateway/terminal/getDeviceCompositeInfo?gatewayId={self.gateway}"
        params = {"refreshFlag": "1", "lang": "en_US"}
        data = await self._get(url, params=params)
        return data

    async def get_agate_info(self):
        """Get the details of connected FranklinWH Gateway.

        Returns
        -------
        dict
            Protocol, software/firmware releases, connectivity type
        """
        url = self.url_base + "hes-gateway/terminal/obtainAgateInfo"
        data = await self._get(url)
        return data

    async def get_apower_info(self):
        """Get the details of connected FranklinWH aPower batteries.

        Returns
        -------
        dict
            aPowers grouped by serial number: power rating, rated capacity,
            status, remaining capacity, SoC, firmware versions
        """
        url = self.url_base + "hes-gateway/terminal/obtainApowersInfo"
        data = await self._get(url)
        return data

    async def get_bms_info(self, apower_serial_no):
        """Get the Battery Management Info of a specified aPower battery.

        Reverse-engineered from the FranklinWH mobile app. The app sends
        two sendMqtt requests (cmdType 211 with type 2 and type 3). The
        purpose of each type is unknown — both appear to return BMS data.
        In the mobile app, the second response is sometimes not received
        (known issue).

        Requests MUST be sequential — concurrent asyncio.gather causes both
        to fail (the MQTT layer cannot multiplex simultaneous requests).

        If both respond, we log the delta between them and return the richer
        payload. If only one responds, we return that one.

        Parameters
        ----------
        apower_serial_no : str
            Serial number of the aPower battery.
        """
        logger.info(f"get_bms_info: sending type 2 then type 3 for aPower {apower_serial_no}")

        # Type 2 — send first (must be sequential, not concurrent)
        data2 = None
        try:
            payload2 = {"fhpSn": f"{apower_serial_no}", "type": 2}
            wire2 = self._build_payload(211, payload2)
            raw2 = (await self._mqtt_send(wire2))["result"]["dataArea"]
            if raw2:
                data2 = json.loads(raw2)
                logger.debug(f"get_bms_info: type2 raw payload: {raw2}")
        except Exception as e:
            logger.warning(f"get_bms_info: type2 failed: {e}")

        # Type 3 — send second
        data3 = None
        try:
            payload3 = {"fhpSn": f"{apower_serial_no}", "type": 3}
            wire3 = self._build_payload(211, payload3)
            raw3 = (await self._mqtt_send(wire3))["result"]["dataArea"]
            if raw3:
                data3 = json.loads(raw3)
                logger.debug(f"get_bms_info: type3 raw payload: {raw3}")
        except Exception as e:
            logger.warning(f"get_bms_info: type3 failed: {e}")

        # Log response status
        got2 = data2 is not None
        got3 = data3 is not None
        logger.info(f"get_bms_info: type2={'received' if got2 else 'LOST'}, "
                     f"type3={'received' if got3 else 'LOST'}")

        # If both responded, log the delta
        if got2 and got3:
            self._log_bms_delta(data2, data3)

        # Return the richer response (more keys = more data)
        if got2 and got3:
            result = data2 if len(data2) >= len(data3) else data3
        elif got2:
            result = data2
        elif got3:
            result = data3
        else:
            raise DeviceTimeoutException("BMS: both type 2 and type 3 responses lost")

        return result

    @staticmethod
    def _log_bms_delta(data2: dict, data3: dict):
        """Log differences between type 2 and type 3 BMS responses."""
        all_keys = set(data2.keys()) | set(data3.keys())
        only_in_2 = set(data2.keys()) - set(data3.keys())
        only_in_3 = set(data3.keys()) - set(data2.keys())
        shared = set(data2.keys()) & set(data3.keys())

        diffs = {}
        for k in shared:
            if data2[k] != data3[k]:
                diffs[k] = {"type2": data2[k], "type3": data3[k]}

        if only_in_2 or only_in_3 or diffs:
            logger.info(f"get_bms_info delta: "
                        f"only_in_type2={only_in_2 or '{}'}, "
                        f"only_in_type3={only_in_3 or '{}'}, "
                        f"value_diffs={diffs or '{}'}")
        else:
            logger.info("get_bms_info delta: type2 and type3 responses are identical")

    async def led_light_settings(self, mode, dataArea):
        """Get or set the LED strip settings for a specified aPower battery.

        https://www.franklinwh.com/support/overview/apower-led/

        Parameters
        ----------
        mode : str
            0 = Get settings, 1 = Set settings
        dataArea : dict
            Payload data
        """
        print(f"mode = {mode}, payload = {dataArea}")
        if mode == "1":
            dataArea = {"opt": 0}
        elif mode == "2":
            if dataArea is None:
                BadRequestParsingError("Missing payload")

        wire_payload = self._build_payload(327, dataArea)
        data = (await self._mqtt_send(wire_payload))["result"]["dataArea"]
        return json.loads(data)

    async def get_smart_circuits_info(self):
        """Get Smart Circuit detailed info.

        https://www.franklinwh.com/support/overview/smart-circuits
        """
        payload = {"opt": 0}
        logger.info(f"get_smart_circuits_info: cmdType: 311 Type 2 on aGate {self.gateway}")
        wire_payload = self._build_payload(311, payload)
        data = (await self._mqtt_send(wire_payload))["result"]["dataArea"]
        return json.loads(data)

    async def get_smart_circuits(self) -> dict:
        """Get Smart Circuit configuration explicitly mapped to Python structures.
        
        Returns
        -------
        dict[int, SmartCircuitDetail]
            A dictionary mapping Circuit ID (1-3) directly to its SmartCircuitDetail class.
        """
        from franklinwh_cloud.models import SmartCircuitDetail
        
        raw_data = await self.get_smart_circuits_info()
        circuits = {}
        for i in range(1, 4):
            circuits[i] = SmartCircuitDetail.from_api_payload(raw_data, i)
        return circuits

    async def set_smart_circuit_state(self, circuit: int, turn_on: bool):
        """Toggle a Smart Circuit on or off.
        
        Parameters
        ----------
        circuit : int
            Circuit number (1, 2, or 3)
        turn_on : bool
            True to turn on (Mode 1), False to turn off (Mode 0)
        """
        if circuit not in (1, 2, 3):
            raise ValueError("Circuit must be 1, 2, or 3")
        
        # FranklinWH accepts partial updates via MQTT
        payload = {f"Sw{circuit}Mode": 1 if turn_on else 0}
        wire_payload = self._build_payload(310, payload)
        return await self._mqtt_send(wire_payload)

    async def set_smart_circuit_soc_cutoff(self, circuit: int, enable: bool, soc: int = 0):
        """Configure the off-grid SOC Auto Cut-off threshold.
        
        Parameters
        ----------
        circuit : int
            Circuit number (1, 2, or 3)
        enable : bool
            Whether to enable the cutoff threshold
        soc : int
            The battery percentage (0-100) at which to shed the load
        """
        if circuit not in (1, 2, 3):
            raise ValueError("Circuit must be 1, 2, or 3")
        
        payload = {
            f"Sw{circuit}AtuoEn": 1 if enable else 0,
            f"Sw{circuit}SocLowSet": int(soc)
        }
        wire_payload = self._build_payload(310, payload)
        return await self._mqtt_send(wire_payload)

    async def set_smart_circuit_load_limit(self, circuit: int, max_amps: int):
        """Configure the maximum amperage draw for a Smart Circuit.
        
        Parameters
        ----------
        circuit : int
            Circuit number (1, 2, or 3)
        max_amps : int
            The max allowed current (amps) for the circuit breaker constraint.
            Set to 0 to disable or reset to hardware defaults.
        """
        if circuit not in (1, 2, 3):
            raise ValueError("Circuit must be 1, 2, or 3")
            
        payload = {f"Sw{circuit}LoadLimit": int(max_amps)}
        wire_payload = self._build_payload(310, payload)
        return await self._mqtt_send(wire_payload)

    async def get_device_info(self):
        """Get detailed device info for the current gateway.

        Returns
        -------
        dict
            Device Info V2 payload with hardware details
        """
        url = self.url_base + f"hes-gateway/terminal/getDeviceInfoV2?gatewayId={self.gateway}&lang=EN_US"
        data = await self._get(url)
        return data

    async def get_agate_network_info(self, requestType):
        """Get the specific aGate network settings.

        .. deprecated::
            Use the individual methods instead:
            - ``get_network_info()`` (requestType "1" → cmdType 317)
            - ``get_connection_status()`` (requestType "2" → cmdType 339)
            - ``get_wifi_config()`` (requestType "3" → cmdType 337)

        Parameters
        ----------
        requestType : str
            1 = Network Settings, 2 = Connectivity status, 3 = WiFi Settings
        """
        warnings.warn(
            "get_agate_network_info() is deprecated. Use get_network_info(), "
            "get_connection_status(), or get_wifi_config() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        dataArea = {"opt": 0}

        match requestType:
            case "1":
                requestCode = 317
                dataArea = {"opt": 0, "paraType": 6}
            case "2":
                requestCode = 339
            case "3":
                requestCode = 337
            case _:
                raise BadRequestParsingError(f"Missing requestType value or unknown: {requestType}")

        wire_payload = self._build_payload(requestCode, dataArea)
        data = (await self._mqtt_send(wire_payload))["result"]["dataArea"]
        return _parse_mqtt_json(data, requestCode)

    async def get_power_info(self):
        """Get voltages, current, frequencies for grid, loads, genset, relay states.

        Useful for continuous monitoring of power data, relays, and operating mode.

        Returns
        -------
        dict
            Electricity metrics: voltages, currents, frequencies, relay states, modes
        """
        dataArea = {"type": 1}
        wire_payload = self._build_payload(211, dataArea)
        data = (await self._mqtt_send(wire_payload))["result"]["dataArea"]
        return json.loads(data)

    async def get_accessories_power_info(self, option=1):
        """Get accessories power and energy information.

        Parameters
        ----------
        option : str
            0 = raw, 1 = Smart Circuits, 2 = V2L, 3 = Generator
        """
        dataArea = {"opt": 0}
        wire_payload = self._build_payload(353, dataArea)
        data = (await self._mqtt_send(wire_payload))["result"]["dataArea"]
        raw_data = json.loads(data)
        result = {}

        if option == "0":
            return raw_data
        if option == "1":
            result["smart_circuits"] = [
                {"id": 1, "current": raw_data.get("SW1Curr", 0), "voltage": raw_data.get("Sw1Volt", 0),
                 "power": raw_data.get("SW1ExpPower", 0), "energy": raw_data.get("SW1ExpEnergy", 0)},
                {"id": 2, "current": raw_data.get("SW2Curr", 0), "voltage": raw_data.get("Sw2Volt", 0),
                 "power": raw_data.get("SW2ExpPower", 0), "energy": raw_data.get("SW2ExpEnergy", 0)},
            ]
            return result
        if option == "2":
            result["v2l"] = {
                "current": raw_data.get("CarSWCurr", 0), "power": raw_data.get("CarSWPower", 0),
                "imp_energy": raw_data.get("CarSWImpEnergy", 0), "exp_energy": raw_data.get("CarSWExpEnergy", 0),
            }
            return result
        if option == "3":
            result["generator"] = {
                "power": raw_data.get("genpowerGen", 0), "voltage": raw_data.get("volt", 0),
                "current": raw_data.get("curr", 0), "frequency": raw_data.get("freq", 0),
            }
            return result
        return raw_data

    async def get_span_settings(self, requestType):
        """Get SPAN Panel settings associated with this aGate.

        Note: Requires the SPAN panel settings flag to be set in the FranklinWH app.

        Parameters
        ----------
        requestType : int
            Request type for SPAN panel query

        Returns
        -------
        dict
            SPAN panel settings information
        """
        url = self.url_base + "hes-gateway/terminal/span/getSpanSettings"
        params = {"gatewayId": self.gateway}
        data = await self._get(url, params=params)
        return data["result"]

    async def get_span_setting(self):
        """Check if this aGate has a SPAN panel detected/configured.

        Returns
        -------
        dict
            {"spanFlag": 0|1} — 0 = no SPAN panel, 1 = SPAN panel detected
        """
        url = self.url_base + "hes-gateway/terminal/span/getSpanSetting"
        data = await self._get(url)
        return data["result"]

    async def get_generator_info(self):
        """Get generator current state information.

        https://www.franklinwh.com/support/overview/generator/
        """
        url = self.url_base + "hes-gateway/terminal/selectIotGenerator"
        params = {"gatewayId": self.gateway}
        data = await self._get(url, params=params)
        return data["result"]

    async def set_generator_mode(self, mode):
        """Set generator operating mode.

        Parameters
        ----------
        mode : int
            1 = Auto-schedule, 2 = Manual
        """
        payload = {"gatewayId": self.gateway, "manuSw": mode, "opt": 1}
        url = self.url_base + "hes-gateway/terminal/updateIotGenerator"
        params = {"gatewayId": self.gateway}
        data = await self._post(url, params=params, payload=payload)
        return data["result"]

    async def get_network_info(self):
        """Get aGate network configuration via MQTT command.

        Sends cmdType 317 with paraType 6 to retrieve detailed network
        interface information from the aGate.

        Returns
        -------
        dict
            Parsed network configuration with keys:
            - currentNetType: active network type code
            - wifi: {mac, dhcp, ip, dns, gateway}
            - eth0: {mac, dhcp, ip, dns, gateway}
            - eth1: {mac, dhcp, ip, dns, gateway}
            - operator: {mac, dns, rssi}
            - awsStatus: AWS connection status (1 = connected)
        """
        dataArea = {"optType": 0, "paraType": 6}
        wire_payload = self._build_payload(317, dataArea)
        raw = (await self._mqtt_send(wire_payload))["result"]["dataArea"]
        parsed = _parse_mqtt_json(raw, 317)

        # Extract the commSetPara from the nested result — with type safety
        # MQTT response variants seen in the wild:
        #   {"result": {"commSetPara": {...}}}    — commSetPara nested under result dict
        #   {"result": 0, "commSetPara": {...}}   — result is int (success code), commSetPara at top level
        result = parsed.get("result") if isinstance(parsed, dict) else parsed
        if isinstance(result, dict):
            comm = result.get("commSetPara", result)
        elif isinstance(parsed, dict):
            # result is an int/scalar — look for commSetPara at top level
            comm = parsed.get("commSetPara", parsed)
        else:
            comm = {}
        if not isinstance(comm, dict):
            comm = parsed if isinstance(parsed, dict) else {}

        return {
            "currentNetType": comm.get("currentNetType"),
            "wifi": {
                "mac": comm.get("wifiMAC"),
                "dhcp": bool(comm.get("wifiDHCP", 0)),
                "ip": comm.get("wifiStaticIP"),
                "dns": comm.get("wifiDNS"),
                "gateway": comm.get("wifiGateWay"),
            },
            "eth0": {
                "mac": comm.get("eth0MAC"),
                "dhcp": bool(comm.get("eth0DHCP", 0)),
                "ip": comm.get("eth0StaticIP"),
                "dns": comm.get("eth0DNS"),
                "gateway": comm.get("eth0GateWay"),
            },
            "eth1": {
                "mac": comm.get("eth1MAC"),
                "dhcp": bool(comm.get("eth1DHCP", 0)),
                "ip": comm.get("eth1StaticIP"),
                "dns": comm.get("eth1DNS"),
                "gateway": comm.get("eth1GateWay"),
            },
            "operator": {
                "mac": comm.get("operatorMAC"),
                "dns": comm.get("operatorDNS"),
                "rssi": comm.get("operatorRSSI"),
            },
            "awsStatus": comm.get("awsStatus"),
        }

    async def get_wifi_config(self):
        """Get aGate WiFi configuration and access point details via MQTT.

        Sends cmdType 337 with opt 0 to retrieve the current WiFi connection
        and the aGate's own access point (AP) configuration.

        Returns
        -------
        dict
            WiFi configuration with keys:
            - wifi_ssid: SSID of the connected WiFi network
            - wifi_password: password of the connected WiFi network
            - ap_ssid: SSID of the aGate's own access point
            - ap_password: password of the aGate's own access point
            - wifi_safety: security mode (1 = WPA/WPA2)
        """
        dataArea = {"opt": 0}
        wire_payload = self._build_payload(337, dataArea)
        raw = (await self._mqtt_send(wire_payload))["result"]["dataArea"]
        parsed = _parse_mqtt_json(raw, 337)

        return {
            "wifi_ssid": parsed.get("wifi_SSID"),
            "wifi_password": parsed.get("wifi_Pw"),
            "ap_ssid": parsed.get("ap_SSID"),
            "ap_password": parsed.get("ap_Pw"),
            "wifi_safety": parsed.get("wifi_Safety"),
        }

    async def scan_wifi_networks(self):
        """Trigger a WiFi network scan on the aGate via MQTT.

        Sends cmdType 335 with wifi_ScanTime 0 to scan for available WiFi
        networks that the aGate can see. This is the same scan triggered by
        the FranklinWH mobile app's WiFi Configuration wizard (step 2/3).

        Returns
        -------
        dict
            Scan result from the aGate. Keys:
            - result: 0 = scan complete with data, 1 = scan initiated/pending
            - reason: status code (3 = scan in progress)
            - Additional keys with SSID list when scan completes

        Note
        ----
        The scan is asynchronous — the aGate may return result=1 (pending)
        on the first call. The app typically polls until results appear.
        This command talks to the aGate hardware via MQTT relay through the
        cloud. The aGate must be online (even via 4G) for this to work.
        """
        dataArea = {"wifi_ScanTime": 0}
        wire_payload = self._build_payload(335, dataArea)
        raw = (await self._mqtt_send(wire_payload))["result"]["dataArea"]
        return _parse_mqtt_json(raw, 335)

    async def scan_wifi_networks_poll(self, max_attempts=3, delay_s=2.0):
        """Poll for WiFi scan results until complete or max attempts reached.

        Calls scan_wifi_networks() repeatedly, waiting between attempts.
        The aGate WiFi scan is asynchronous — the first call typically
        returns result=1 (pending). Subsequent calls return the SSID list
        once the scan completes (result=0).

        Parameters
        ----------
        max_attempts : int
            Maximum number of scan attempts (default: 3).
        delay_s : float
            Seconds to wait between attempts (default: 2.0).

        Returns
        -------
        dict
            Final scan result from the aGate. If result=0, contains
            the WiFi network list. If result=1, scan did not complete
            within the allowed attempts.
        """
        for attempt in range(max_attempts):
            result = await self.scan_wifi_networks()
            if result.get("result") == 0:
                logger.info(f"WiFi scan complete on attempt {attempt + 1}")
                return result
            if attempt < max_attempts - 1:
                logger.info(f"WiFi scan pending (attempt {attempt + 1}/{max_attempts}), "
                            f"retrying in {delay_s}s...")
                await asyncio.sleep(delay_s)
        logger.warning(f"WiFi scan did not complete after {max_attempts} attempts")
        return result

    async def get_connection_status(self):
        """Get aGate connection status for router, network, and AWS cloud.

        Sends cmdType 339 to check the connectivity state of the aGate.

        Returns
        -------
        dict
            Connection status:
            - routerStatus: 0 = disconnected, 1 = connected
            - netStatus: 0 = no internet, 1 = internet available
            - awsStatus: 0 = offline, 1 = connected to AWS cloud
        """
        dataArea = {"opt": 0}
        wire_payload = self._build_payload(339, dataArea)
        raw = (await self._mqtt_send(wire_payload))["result"]["dataArea"]
        return _parse_mqtt_json(raw, 339)

    async def get_network_switches(self):
        """Get aGate network interface enable/disable switches.

        Sends cmdType 341 to check which network interfaces are enabled.

        Returns
        -------
        dict
            Interface switch states (1 = enabled, 0 = disabled):
            - ethernet0NetSwitch: Ethernet 0 interface
            - ethernet1NetSwitch: Ethernet 1 interface
            - wifiNetSwitch: WiFi interface
            - 4GNetSwitch: Cellular 4G interface
        """
        dataArea = {"opt": 0}
        wire_payload = self._build_payload(341, dataArea)
        raw = (await self._mqtt_send(wire_payload))["result"]["dataArea"]
        return _parse_mqtt_json(raw, 341)

    async def get_site_detail(self, site_id: str = None):
        """Get site details (name, address, location).

        Parameters
        ----------
        site_id : str, optional
            Site ID. If None, auto-resolved from gateway list.

        Returns
        -------
        dict
            {siteName, address1, address2, country, province, city,
             postCode, alphaCode, completeAddress}
        """
        if site_id is None:
            # siteId is not in fetcher.info — it lives in the gateway list response.
            # Match on gateway serial (self.gateway) to get the correct siteId.
            try:
                res = await self.get_home_gateway_list()
                gateways = res.get("result", [])
                # Match by gateway serial number, fall back to first gateway
                matched = next(
                    (gw for gw in gateways if gw.get("id") == self.gateway),
                    gateways[0] if gateways else {}
                )
                site_id = str(matched.get("siteId", ""))
            except Exception as e:
                logger.warning(f"get_site_detail: could not resolve siteId: {e}")
                site_id = ""
        url = self.url_base + "hes-gateway/terminal/site/get/SiteDetail"
        params = {
            "siteId": str(site_id),
            "userId": str(self.fetcher.info.get("userId", "")),
        }
        data = await self._get(url, params=params)
        return data


    async def get_device_detail(self):
        """Get device/gateway detail (name, address, location).

        Returns
        -------
        dict
            {gatewayName, address1, address2, country, province, city,
             postCode, alphaCode, completeAddress}
        """
        url = self.url_base + "hes-gateway/terminal/site/get/DeviceDetail"
        params = {"gatewayId": self.gateway}
        data = await self._get(url, params=params)
        return data

    async def get_device_overall_info(self):
        """Get device overview (aPower count, total power capacity).

        Returns
        -------
        dict
            {apowerCount: int, totalPower: float}
        """
        url = self.url_base + "hes-gateway/terminal/selectDeviceOverallInfo"
        params = {"gatewayId": self.gateway}
        data = await self._get(url, params=params)
        return data

    async def get_personal_info(self):
        """Get user profile information.

        Returns
        -------
        dict
            {userName, contactNumber, userAddress, region, lat, lon,
             firstName, lastName, zipCode, country, province, city, ...}
        """
        url = self.url_base + "hes-gateway/terminal/getPersonalInfo"
        data = await self._get(url, params=None)
        return data

