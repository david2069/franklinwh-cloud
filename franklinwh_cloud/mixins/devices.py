"""Device and accessory information API methods."""

import json
import logging

from franklinwh_cloud.exceptions import BadRequestParsingError

logger = logging.getLogger("franklinwh_cloud")


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

        Parameters
        ----------
        apower_serial_no : str
            Serial number of the aPower battery.
        """
        payload = {"fhpSn": f"{apower_serial_no}", "type": 2}
        wire_payload = self._build_payload(211, payload)
        data2 = (await self._mqtt_send(wire_payload))["result"]["dataArea"]

        payload = {"fhpSn": f"{apower_serial_no}", "type": 3}
        logger.info(f"get_bms_info: cmdType: 211 Type 3 on aGate {self.gateway} - aPower battery {apower_serial_no}")
        wire_payload = self._build_payload(211, payload)
        data3 = (await self._mqtt_send(wire_payload))["result"]["dataArea"]
        logger.info(f"get_bms_info: send request type 3 {data3}")

        if data2:
            result = data2
        else:
            result = data3
        return json.loads(result)

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

    async def set_smart_switch_state(self, state: tuple):
        """Set the state of the smart circuits.

        Setting a value in the state tuple to True will turn on that circuit,
        False will turn off, None will leave unchanged.
        """
        def set_value(keys, value):
            for key in keys:
                payload[key] = int(value)

        payload = {}
        if state[0] is not None:
            set_value(["Sw1SocLowSet", "Sw1Mode", "Sw1ProLoad"], state[0])

        if len(state) > 1 and state[1] is not None:
            set_value(["Sw2SocLowSet", "Sw2Mode", "Sw2ProLoad"], state[1])

        if len(state) > 2 and state[2] is not None:
            set_value(["Sw3SocLowSet", "Sw3Mode", "Sw3ProLoad"], state[2])

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

        Parameters
        ----------
        requestType : str
            1 = Network Settings, 2 = Connectivity status, 3 = WiFi Settings
        """
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
        return json.loads(data)

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
        parsed = json.loads(raw)

        # Extract the commSetPara from the nested result
        comm = parsed.get("result", {}).get("commSetPara", parsed)

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
