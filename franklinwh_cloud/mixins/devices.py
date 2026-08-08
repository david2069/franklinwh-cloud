"""Device and accessory information API methods."""

import asyncio
import json
import logging
import warnings

from franklinwh_cloud.exceptions import BadRequestParsingError, DeviceTimeoutException
from franklinwh_cloud.models import MqttCmd

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
        logger.debug(f"get_bms_info: sending type 2 then type 3 for aPower {apower_serial_no}")

        # Type 2 — send first (must be sequential, not concurrent)
        data2 = None
        for attempt in range(3):
            try:
                payload2 = {"fhpSn": f"{apower_serial_no}", "type": 2}
                wire2 = self._build_payload(MqttCmd.POWER_AND_RELAYS, payload2)  # cmdType 211
                raw2 = (await self._mqtt_send(wire2))["result"]["dataArea"]
                if raw2:
                    data2 = json.loads(raw2)
                    logger.debug(f"get_bms_info: type2 raw payload: {raw2}")
                break  # Success
            except Exception as e:
                logger.warning(f"get_bms_info: type2 attempt {attempt + 1}/3 failed: {e}")
                if attempt < 2:
                    await asyncio.sleep(1)

        # Type 3 — send second
        data3 = None
        for attempt in range(3):
            try:
                payload3 = {"fhpSn": f"{apower_serial_no}", "type": 3}
                wire3 = self._build_payload(MqttCmd.POWER_AND_RELAYS, payload3)  # cmdType 211
                raw3 = (await self._mqtt_send(wire3))["result"]["dataArea"]
                if raw3:
                    data3 = json.loads(raw3)
                    logger.debug(f"get_bms_info: type3 raw payload: {raw3}")
                break  # Success
            except Exception as e:
                logger.warning(f"get_bms_info: type3 attempt {attempt + 1}/3 failed: {e}")
                if attempt < 2:
                    await asyncio.sleep(1)

        # Log response status
        got2 = data2 is not None
        got3 = data3 is not None
        logger.debug(f"get_bms_info: type2={'received' if got2 else 'LOST'}, "
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
            logger.debug(f"get_bms_info delta: "
                        f"only_in_type2={only_in_2 or '{}'}, "
                        f"only_in_type3={only_in_3 or '{}'}, "
                        f"value_diffs={diffs or '{}'}")
        else:
            logger.debug("get_bms_info delta: type2 and type3 responses are identical")

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

        wire_payload = self._build_payload(MqttCmd.AESTHETICS, dataArea)  # cmdType 327
        data = (await self._mqtt_send(wire_payload))["result"]["dataArea"]
        return json.loads(data)

    async def get_smart_circuits_info(self):
        """Get Smart Circuit detailed info.

        https://www.franklinwh.com/support/overview/smart-circuits
        """
        payload = {"opt": 0}
        logger.debug(f"get_smart_circuits_info: cmdType: 311 Type 2 on aGate {self.gateway}")
        wire_payload = self._build_payload(MqttCmd.SMART_CIRCUIT_INFO, payload)  # cmdType 311
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

    async def _update_smart_circuit_config(self, circuit: int, updates: dict):
        """Helper to perform a read-modify-write 311 cycle for a specific circuit."""
        payload = await self.get_smart_circuits_info()
        payload["opt"] = 1
        payload.pop("modeChoose", None)
        payload.pop("result", None)

        for i in range(1, 4):
            if f"Sw{i}MsgType" in payload:
                payload[f"Sw{i}MsgType"] = 0

        payload[f"Sw{circuit}MsgType"] = 1
        for k, v in updates.items():
            payload[k] = v

        wire_payload = self._build_payload(MqttCmd.SMART_CIRCUIT_INFO, payload)  # cmdType 311
        import json
        data = (await self._mqtt_send(wire_payload))["result"]["dataArea"]
        return json.loads(data)

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
        
        mode_val = 1 if turn_on else 0
        updates = {
            f"Sw{circuit}Mode": mode_val,
            f"Sw{circuit}ProLoad": mode_val ^ 1
        }
        return await self._update_smart_circuit_config(circuit, updates)

    
    async def set_smart_switch_state(self, circuit: int, state):
        """Configure a Smart Circuit's operating mode (ON, OFF, or Schedule).
        
        Parameters
        ----------
        circuit : int
            Circuit number (1, 2, or 3)
        state : bool or str or int
            True/"ON"/1 to turn on (Manual)
            False/"OFF"/0 to turn off (Manual)
            "Schedule"/2 to set to Schedule mode
        """
        if circuit not in (1, 2, 3):
            raise ValueError("Circuit must be 1, 2, or 3")
            
        mode_val = 0
        if isinstance(state, bool):
            mode_val = 1 if state else 0
        elif isinstance(state, str):
            state_up = state.upper()
            if state_up == "ON":
                mode_val = 1
            elif state_up == "OFF":
                mode_val = 0
            elif state_up == "SCHEDULE":
                mode_val = 2
            else:
                raise ValueError("State string must be 'ON', 'OFF', or 'SCHEDULE'")
        elif isinstance(state, int) and state in (0, 1, 2):
            mode_val = state
        else:
            raise ValueError("Invalid state. Must be bool, 'ON', 'OFF', 'SCHEDULE', or 0/1/2")
            
        updates = {
            f"Sw{circuit}Mode": mode_val,
            f"Sw{circuit}ProLoad": mode_val ^ 1
        }
        return await self._update_smart_circuit_config(circuit, updates)

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
        
        updates = {
            f"Sw{circuit}AtuoEn": 1 if enable else 0,
            f"Sw{circuit}SocLowSet": int(soc)
        }
        return await self._update_smart_circuit_config(circuit, updates)

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
            
        updates = {f"Sw{circuit}LoadLimit": int(max_amps)}
        return await self._update_smart_circuit_config(circuit, updates)

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
                requestCode = MqttCmd.NETWORK_INTERFACES  # cmdType 317
                dataArea = {"opt": 0, "paraType": 6}
            case "2":
                requestCode = MqttCmd.CLOUD_CONNECTIVITY  # cmdType 339
            case "3":
                requestCode = MqttCmd.WIFI_CONFIG  # cmdType 337
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
        wire_payload = self._build_payload(MqttCmd.POWER_AND_RELAYS, dataArea)  # cmdType 211
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
        wire_payload = self._build_payload(MqttCmd.ACCESSORY_LOADS, dataArea)  # cmdType 353
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

    async def set_v2l_mode(self, enable: bool) -> dict:
        """Enable or disable V2L (Vehicle-to-Load) output via the CarSW port.

        .. warning::
            **SPECULATIVE IMPLEMENTATION — not verified against live V2L hardware.**

            Based on analysis of the cmdType 311 Smart Circuit payload structure:

            - On US V1 Smart Circuits + Generator Module, Sw3 is the CarSW (V2L) port.
            - The hypothesis is that toggling V2L maps to ``Sw3Mode = 1 (ON) / 0 (OFF)``
              via the same cmdType 311 write path used for Smart Circuit control.
            - A separate dedicated V2L endpoint (e.g. ``updateV2l``) may exist but has
              not been captured in mobile app traffic.

            **Verification needed:** A user with a V2L-capable US V1 aGate + Generator
            Module should toggle V2L in the FranklinWH app with Charles/mitmproxy running
            and compare the captured payload against this implementation.

            See: ``docs/GENERATOR_V2L_API.md`` — V2L Control section.

        Parameters
        ----------
        enable : bool
            True to enable V2L output (Sw3 ON), False to disable (Sw3 OFF).

        Returns
        -------
        dict
            Raw cmdType 311 response from the aGate.

        Raises
        ------
        RuntimeError
            If the speculative path produces an unexpected response shape.

        Notes
        -----
        Prerequisites (hardware):
          - US V1 Smart Circuits (accessory type 202, SKU ACCY-SCV1-US)
          - Generator Module V1 (accessory type 201, SKU ACCY-GENV1-US)
          - ``v2lModeEnable = 1`` in runtimeData (system-level V2L licence flag)

        Prerequisites (state):
          - System must be in off-grid mode (grid relay OPEN) for V2L to be
            permitted by firmware. On-grid V2L is not supported on any FranklinWH
            hardware variant.

        Example usage::

            # Check V2L eligibility before calling
            snap = await client.discover()
            if not snap.flags.v2l_eligible:
                raise RuntimeError("Hardware not V2L-capable")

            stats = await client.get_stats()
            if not stats.current.v2l_enabled:
                raise RuntimeError("V2L feature not licensed/enabled on this gateway")

            # Enable V2L output
            result = await client.set_v2l_mode(enable=True)

            # Confirm state
            stats = await client.get_stats()
            from franklinwh_cloud.const import V2L_RUN_STATE
            print(V2L_RUN_STATE[stats.current.v2l_status])
            # Expected: "Standby" or "Discharging / Active"
        """
        logger.warning(
            "set_v2l_mode() is a SPECULATIVE implementation — Sw3 (CarSW) toggle via "
            "cmdType 311. Not verified on live V2L hardware. "
            "See docs/GENERATOR_V2L_API.md for details."
        )
        # Speculative: V2L CarSW port = Smart Circuit 3 (Sw3) on US V1 + Generator Module
        # enable=True  → Sw3Mode=1 (Manual ON)
        # enable=False → Sw3Mode=0 (Manual OFF)
        return await self._update_smart_circuit_config(
            circuit=3,
            updates={"Sw3Mode": 1 if enable else 0, "Sw3ProLoad": 0 if enable else 1},
        )


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
        wire_payload = self._build_payload(MqttCmd.NETWORK_INTERFACES, dataArea)  # cmdType 317
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
        wire_payload = self._build_payload(MqttCmd.WIFI_CONFIG, dataArea)  # cmdType 337
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
        wire_payload = self._build_payload(MqttCmd.WIFI_SCAN, dataArea)  # cmdType 335
        raw = (await self._mqtt_send(wire_payload))["result"]["dataArea"]
        return _parse_mqtt_json(raw, 335)

    async def scan_wifi_networks_poll(self, max_attempts=6, delay_s=5.0):
        """Poll for WiFi scan results until complete or max attempts reached.

        Calls scan_wifi_networks() repeatedly, waiting between attempts.
        The aGate WiFi scan is asynchronous — the first call typically
        returns result=1 (pending). Subsequent calls return the SSID list
        once the scan completes (result=0).

        Parameters
        ----------
        max_attempts : int
            Maximum number of scan attempts (default: 6).
        delay_s : float
            Seconds to wait between attempts (default: 5.0).

        Note
        ----
        The previous defaults (3 attempts x 2.0 s = 6 s ceiling) were shorter
        than the hardware needs and reported failure on healthy gateways. In the
        HAR corpus the mobile app waits ~11-12 s between a pending scan and a
        populated result, so the ceiling is now 30 s.

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
                logger.debug(f"WiFi scan complete on attempt {attempt + 1}")
                return result
            if attempt < max_attempts - 1:
                logger.debug(f"WiFi scan pending (attempt {attempt + 1}/{max_attempts}), "
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
            The raw parsed cmdType 340 payload. Always present:

            - routerStatus: local link state. **NOT a boolean** — values 0, 1
              and 4 have all been observed. Semantics unresolved; do not coerce
              to bool. Treat as an opaque code.
            - netStatus: 0 = no internet, 1 = internet available
            - awsStatus: 0 = offline, 1 = connected to AWS cloud

            Newer gateway firmware additionally returns (absent on older units,
            so always use ``.get()``):

            - EthConnectRouterStatus: Ethernet link to router (0/1)
            - wifiConnectRouterStatus: WiFi link to router (0/1)
            - 4GConnectBSStatus: cellular base-station registration (0/1)
            - WifiSignalStrength: 0-100 percentage
            - 4GSignalStrength: vendor scale, observed 0-52 (NOT a percentage)
            - currentNetType: active transport, see ``NETWORK_TYPES``

        Note
        ----
        These extended fields are firmware-dependent, not app-version dependent
        — they appear in captures as early as 2025-05 and are absent from some
        later ones. ``get_network_state()`` handles the fallback for you.
        """
        dataArea = {"opt": 0}
        wire_payload = self._build_payload(MqttCmd.CLOUD_CONNECTIVITY, dataArea)  # cmdType 339
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
        wire_payload = self._build_payload(MqttCmd.NETWORK_SWITCHES, dataArea)  # cmdType 341
        raw = (await self._mqtt_send(wire_payload))["result"]["dataArea"]
        return _parse_mqtt_json(raw, 341)

    async def scan_wifi_networks_ranked(
        self,
        *,
        scan_time: int = 10,
        min_rssi: int = 0,
        dedupe: bool = True,
        max_attempts: int = 6,
        delay_s: float = 5.0,
        usable_rssi: int = 30,
    ):
        """Scan for WiFi networks and return them ranked by signal strength.

        Wraps the asynchronous cmdType 335 scan and normalises the result into a
        sorted, deduplicated list suitable for presenting to a user.

        Parameters
        ----------
        scan_time : int
            Value for ``wifi_ScanTime``. Both 0 and 10 are observed in the
            mobile app; 10 yields more networks (default: 10).
        min_rssi : int
            Drop networks below this signal percentage (default: 0, keep all).
        dedupe : bool
            Collapse repeated SSIDs, keeping the strongest (default: True).
        max_attempts, delay_s
            Passed to the underlying poll.
        usable_rssi : int
            Threshold at or above which a network is marked ``usable``
            (default: 30).

        Returns
        -------
        dict
            ``{"scan_seconds", "networks": [...], "warnings": [...]}`` where each
            network is ``{ssid, signal_pct, signal_bars, secured, seen_count,
            usable}``, sorted by ``signal_pct`` descending.

        Note
        ----
        ``wifi_RSSI`` is a 0-100 quality percentage, not dBm — verified across
        169 samples in the HAR corpus (range 8-100, always even, never
        negative).

        The scan returns no BSSID, band or channel, so individual access points
        in a mesh cannot be distinguished or targeted. Repeated SSIDs are
        therefore collapsed rather than listed separately.
        """
        dataArea = {"wifi_ScanTime": scan_time}
        result = None
        for attempt in range(max_attempts):
            wire_payload = self._build_payload(MqttCmd.WIFI_SCAN, dataArea)  # cmdType 335
            raw = (await self._mqtt_send(wire_payload))["result"]["dataArea"]
            result = _parse_mqtt_json(raw, 335)
            if result.get("result") == 0:
                logger.debug(f"WiFi scan complete on attempt {attempt + 1}")
                break
            if attempt < max_attempts - 1:
                logger.debug(
                    f"WiFi scan pending (attempt {attempt + 1}/{max_attempts}), "
                    f"retrying in {delay_s}s..."
                )
                await asyncio.sleep(delay_s)
        else:
            logger.warning(f"WiFi scan did not complete after {max_attempts} attempts")

        warnings_out = []
        raw_list = (result or {}).get("wifi_Info") or []
        if not isinstance(raw_list, list):
            raw_list = []
        if (result or {}).get("result") != 0:
            warnings_out.append(
                f"Scan did not complete after {max_attempts} attempts "
                f"(last reason={(result or {}).get('reason')})"
            )

        best = {}
        seen_counts = {}
        for entry in raw_list:
            if not isinstance(entry, dict):
                continue
            ssid = entry.get("wifi_SSID")
            if ssid is None:
                continue
            rssi = entry.get("wifi_RSSI") or 0
            seen_counts[ssid] = seen_counts.get(ssid, 0) + 1
            if not dedupe:
                best.setdefault(len(best), (ssid, rssi, entry.get("wifi_Safety")))
            elif ssid not in best or rssi > best[ssid][1]:
                best[ssid] = (ssid, rssi, entry.get("wifi_Safety"))

        collapsed = sum(c - 1 for c in seen_counts.values() if c > 1)
        if dedupe and collapsed:
            warnings_out.append(
                f"{collapsed} duplicate SSID entries collapsed (mesh or dual-band)"
            )

        networks = []
        for ssid, rssi, safety in best.values():
            if rssi < min_rssi:
                continue
            networks.append({
                "ssid": ssid,
                "signal_pct": rssi,
                "signal_bars": min(4, max(0, (rssi + 24) // 25)),
                "secured": bool(safety),
                "seen_count": seen_counts.get(ssid, 1),
                "usable": rssi >= usable_rssi,
            })
        networks.sort(key=lambda n: (-n["signal_pct"], n["ssid"]))

        return {
            "scan_seconds": scan_time,
            "networks": networks,
            "warnings": warnings_out,
        }

    async def get_network_state(self):
        """Unified view of which transport the aGate is using right now.

        Composes three MQTT reads — cmdType 317 (interface detail), 339
        (reachability) and 341 (interface enable switches) — into the single
        answer to "what is this aGate connected on?".

        Returns
        -------
        dict
            See ``docs/NETWORK_CONNECTIVITY_DESIGN.md`` section 5.1 for the full
            contract. Key fields:

            - ``active``: the transport currently in use (id, key, label, ip,
              gateway, dns, dhcp, mac, signal_pct)
            - ``interfaces``: all four, each with enabled/link/ip/is_active
            - ``cloud``: aws_connected, internet, router_status_raw
            - ``linked_transports``: keys of every transport **currently
              carrying traffic**. The aGate parks the ones it is not using, so
              in practice this holds at most one entry.
            - ``available_transports``: keys of every transport that would
              actually carry traffic if the one in use stopped. For 4G that
              means an **active SIM with reception**; for WiFi and Ethernet it
              means **connected and holding an address** (static or DHCP) —
              signal or a plugged cable alone does not qualify. This is the set
              a write-safety preflight must use: check
              ``set(available_transports) - {target}`` is non-empty for the
              interface you are about to modify. Note the *active* transport
              counts as a fallback when you are modifying a different one.
            - ``redundant``: True when more than one transport is available
            - ``source``: which cmdTypes answered, and whether the firmware
              returned the extended 339 payload

        Warning
        -------
        ``active`` is the transport the aGate has **selected for itself**, not a
        user-configured primary. The gateway re-selects autonomously: across the
        HAR corpus, 17 of 19 observed transport changes followed no command at
        all. Present this to users as "active connection", never as "configured
        primary", and never treat a change in it as proof that a write worked.
        """
        from franklinwh_cloud.const.devices import (
            NETWORK_SWITCH_KEYS,
            NETWORK_TYPE_KEYS,
            NETWORK_TYPES,
            UNASSIGNED_IPS,
        )

        from franklinwh_cloud.const import SIM_STATUS

        # The three MQTT reads, plus a best-effort REST lookup for SIM state.
        # simCardStatus lives on the gateway-list object, not in any cmdType, so
        # it costs a REST call rather than sendMqtt budget. Failures are
        # tolerated: without it, 4G availability falls back to signal alone.
        net_info, conn_status, switches, gw_list = await asyncio.gather(
            self.get_network_info(),
            self.get_connection_status(),
            self.get_network_switches(),
            self.get_home_gateway_list(),
            return_exceptions=True,
        )
        for essential in (net_info, conn_status, switches):
            if isinstance(essential, BaseException):
                raise essential

        sim_status = None
        if not isinstance(gw_list, BaseException):
            match = next(
                (g for g in (gw_list.get("result") or [])
                 if isinstance(g, dict) and g.get("id") == self.gateway),
                None,
            )
            if match is not None:
                sim_status = match.get("simCardStatus")
        else:
            logger.debug(f"get_network_state: SIM status unavailable: {gw_list}")

        # Prefer 317's currentNetType; the extended 339 payload carries the same
        # field on newer firmware and is used only as a fallback.
        active_id = net_info.get("currentNetType")
        extended = "currentNetType" in conn_status
        if active_id is None:
            active_id = conn_status.get("currentNetType")

        # Per-transport link state. The extended 339 fields are authoritative
        # when present; otherwise fall back to "has a usable address".
        link_by_id = {
            1: conn_status.get("EthConnectRouterStatus"),
            2: conn_status.get("EthConnectRouterStatus"),
            3: conn_status.get("wifiConnectRouterStatus"),
            4: conn_status.get("4GConnectBSStatus"),
        }

        interfaces = []
        for iface_id, key in NETWORK_TYPE_KEYS.items():
            cfg = net_info.get(key if key != "4g" else "operator", {}) or {}
            ip = cfg.get("ip")
            has_addr = ip not in UNASSIGNED_IPS
            link = link_by_id.get(iface_id)
            if link is None:
                # No extended payload — infer. Cellular has no IP in the 317
                # response at all, so fall back to signal presence for 4G.
                link = bool(cfg.get("rssi")) if iface_id == 4 else has_addr
            entry = {
                "id": iface_id,
                "key": key,
                "label": NETWORK_TYPES.get(iface_id, f"Unknown ({iface_id})"),
                "enabled": switches.get(NETWORK_SWITCH_KEYS[iface_id]) == 1,
                "link": bool(link),
                "ip": ip if has_addr else None,
                "dhcp": cfg.get("dhcp"),
                "mac": cfg.get("mac"),
                "is_active": iface_id == active_id,
            }
            if iface_id == 3:
                entry["signal_pct"] = conn_status.get("WifiSignalStrength")
            if iface_id == 4:
                # Vendor scale (observed 0-52), NOT a percentage — see
                # discovery.py. Reported under a distinct key so a UI cannot
                # accidentally render it as one.
                entry["signal_raw"] = cfg.get("rssi")
                entry["sim_status"] = sim_status
                entry["sim_status_name"] = SIM_STATUS.get(sim_status)
                entry.pop("dhcp", None)

            # "available" = would this transport actually carry traffic if the
            # one in use stopped? Distinct from "link" = carrying it right now.
            # The aGate parks transports it is not using, so at most one is ever
            # linked; judging fallback safety on `link` alone would refuse every
            # write to the active transport.
            #
            # The two families are judged differently, because they fail
            # differently:
            #
            #   4G  — the out-of-the-box fallback. It holds no IP while idle
            #         (cmdType 317 exposes no address for `operator` at all), so
            #         the test is an ACTIVE SIM plus RECEPTION. Observed
            #         2026-08-08: a full hour on WiFi with 4GNetSwitch=1 and
            #         operatorRSSI=21-22 but 4GConnectBSStatus=0 — idle, yet it
            #         had carried the connection that same morning.
            #
            #   WiFi / Ethernet — must be genuinely CONNECTED AND ACTIVE, i.e.
            #         hold an address, static or DHCP. Signal or a plugged cable
            #         is not enough: on 2026-03-21 and again on 2026-08-08 the
            #         aGate sat associated at 76% with 0.0.0.0 and no working
            #         path. That state is a candidate to switch TO (see
            #         scan_wifi_networks_ranked), never a fallback to rely ON.
            if iface_id == 4:
                # sim_status None => REST lookup failed; fall back to signal
                # alone rather than falsely declaring the lifeline dead.
                sim_ok = sim_status is None or sim_status == 2
                capable = bool(cfg.get("rssi")) and sim_ok
            else:
                capable = bool(entry["link"]) and has_addr
            entry["available"] = entry["enabled"] and capable

            interfaces.append(entry)

        by_id = {i["id"]: i for i in interfaces}
        active = by_id.get(active_id)

        # Two different questions, deliberately kept apart:
        #
        #   linked_transports    — what is carrying traffic right now (factual)
        #   available_transports — what COULD carry traffic (write-safety)
        #
        # Preflight must use `available`. The aGate parks unused transports, so
        # `linked` holds at most one entry and subtracting the write target from
        # it would refuse every write to the active transport.
        #
        # Either way the set is relative to the TARGET of the write, not to the
        # active transport: when the aGate is on 4G and you are rewriting the
        # WiFi config, 4G is the fallback even though it is also active.
        # See NETWORK_CONNECTIVITY_DESIGN.md section 3.
        linked = [i["key"] for i in interfaces if i["enabled"] and i["link"]]
        available = [i["key"] for i in interfaces if i["available"]]

        return {
            "gateway_id": self.gateway,
            "active": {
                "id": active_id,
                "key": active["key"] if active else None,
                "label": NETWORK_TYPES.get(active_id, f"Unknown ({active_id})"),
                "ip": active["ip"] if active else None,
                "gateway": (net_info.get(active["key"], {}) or {}).get("gateway")
                           if active and active["key"] != "4g" else None,
                "dns": (net_info.get(active["key"], {}) or {}).get("dns")
                       if active and active["key"] != "4g" else None,
                "selection": "device-managed",
            },
            "interfaces": interfaces,
            "cloud": {
                # routerStatus is NOT a boolean (0, 1 and 4 all observed) — passed
                # through unmapped until its semantics are established.
                "aws_connected": conn_status.get("awsStatus") == 1,
                "internet": conn_status.get("netStatus") == 1,
                "router_status_raw": conn_status.get("routerStatus"),
            },
            "linked_transports": linked,
            "available_transports": available,
            # True when losing the transport currently in use would still leave
            # another one able to take over.
            "redundant": len(available) > 1,
            "source": {"cmds": [317, 339, 341], "extended_339": extended},
        }

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

    async def get_connectivity_overview(self, deep_scan: bool = False):
        """Unified overview of the gateway's network connectivity.
        
        Fetches primary and backup connection statuses, mapped network types,
        and optionally verifies SPAN panel integration and local Modbus availability.
        
        Parameters
        ----------
        deep_scan : bool
            Determine if secondary requests (SPAN / Modbus ping) should be executed.
            Default is False to reduce polling overhead.
            
        Returns
        -------
        dict
            Connectivity overview dictionary containing cloud_connected, primary, primary_ip, and backups.
        """
        import asyncio
        import socket
        from franklinwh_cloud.const.devices import NETWORK_TYPES
        
        # Parallel fetch critical configuration
        net_info, conn_status, net_switches, stats = await asyncio.gather(
            self.get_network_info(),
            self.get_connection_status(),
            self.get_network_switches(),
            self.get_stats()
        )
        
        primary_id = net_info.get("currentNetType")
        primary_name = NETWORK_TYPES.get(primary_id, f"Unknown ({primary_id})")
        
        # Resolve primary IP address based on active connection
        primary_ip = None
        primary_gateway = None
        if primary_id == 1:
            cfg = net_info.get("eth0", {})
        elif primary_id == 2:
            cfg = net_info.get("eth1", {})
        elif primary_id == 3:
            cfg = net_info.get("wifi", {})
        else:
            cfg = {}
            
        primary_ip = cfg.get("ip")
        primary_gateway = cfg.get("gateway")
            
        # Discover backup connections powered on by the hardware switches
        # Map NETWORK_TYPES id → net_info interface key for IP lookup
        backups = []
        if net_switches.get("ethernet0NetSwitch") == 1 and primary_id != 1:
            ip = net_info.get("eth0", {}).get("ip")
            backups.append({"id": 1, "name": NETWORK_TYPES.get(1), "ip": ip})
        if net_switches.get("ethernet1NetSwitch") == 1 and primary_id != 2:
            ip = net_info.get("eth1", {}).get("ip")
            backups.append({"id": 2, "name": NETWORK_TYPES.get(2), "ip": ip})
        if net_switches.get("wifiNetSwitch") == 1 and primary_id != 3:
            ip = net_info.get("wifi", {}).get("ip")
            backups.append({"id": 3, "name": NETWORK_TYPES.get(3), "ip": ip})
        if net_switches.get("4GNetSwitch") == 1 and primary_id != 4:
            rssi = net_info.get("operator", {}).get("rssi")
            backups.append({"id": 4, "name": NETWORK_TYPES.get(4), "rssi": rssi})
            
        overview = {
            "cloud_connected": conn_status.get("awsStatus") == 1,
            # routerStatus is NOT a boolean — 0, 1 and 4 have all been observed
            # on live hardware, so bool() reported 4 as "connected". Compare
            # explicitly against 1 and expose the raw code alongside.
            "router_connected": conn_status.get("routerStatus") == 1,
            "router_status_raw": conn_status.get("routerStatus"),
            "internet_connected": conn_status.get("netStatus") == 1,
            "primary": {
                "id": primary_id,
                "name": primary_name,
                "ip": primary_ip,
                "gateway": primary_gateway
            },
            "backups": backups,
            "signals": {
                "wifi_signal": stats.current.wifi_signal,
                "mobile_signal": stats.current.mobile_signal
            }
        }
        
        if deep_scan:
            # Check SPAN flag
            try:
                span = await self.get_span_setting()
                overview["span_connected"] = bool(span.get("spanFlag"))
            except Exception:
                overview["span_connected"] = False
                
            # Ping Modbus TCP port 502
            modbus_open = False
            if primary_ip and primary_ip != "0.0.0.0":
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(1.5)
                    result = sock.connect_ex((primary_ip, 502))
                    if result == 0:
                        modbus_open = True
                    sock.close()
                except Exception:
                    pass
            overview["modbus_tcp_502_open"] = modbus_open
            
        return overview

    # ── TOU Mode Reset ────────────────────────────────────────────────────────

    async def reset_tou_mode(
        self,
        *,
        min_soc_pct: int = 10,
        max_verify_attempts: int = 4,
        verify_interval_s: int = 15,
    ) -> dict:
        """Force the gateway to re-evaluate its TOU schedule.

        Performs a deliberate operating mode toggle:
            Self-Consumption → (3 s pause) → Time-of-Use

        Then polls getGatewayTouListV2 at verify_interval_s intervals to confirm
        the gateway acknowledged the schedule (touSendStatus returns to null).
        This mirrors the mobile app's post-apply polling behaviour.

        This method MUST only be called after presenting the fault to the user
        and receiving explicit confirmation — it is a write operation that
        temporarily changes the operating mode.

        Parameters
        ----------
        min_soc_pct : int, optional
            Minimum battery SOC percentage required before allowing the reset.
            Default is 10%. Prevents an accidental mode toggle that could trigger
            unexpected discharge on a critically low battery.
        max_verify_attempts : int, optional
            Maximum number of getGatewayTouListV2 polls to check whether
            touSendStatus cleared to null after the mode toggle. Default is 4
            (4 × 15 s = up to 60 s total verification window).
        verify_interval_s : int, optional
            Seconds to wait between each verification poll. Default is 15 s,
            matching the mobile app's observed polling cadence.

        Returns
        -------
        dict
            ok                  : bool      — True if mode toggle succeeded (regardless of sync ACK)
            sync_cleared        : bool      — True if touSendStatus returned to null within retries
            final_send_status   : int|None  — last observed touSendStatus value
            final_alert_message : str       — last observed touAlertMessage (or '')
            steps               : list[str] — log of each step taken
            error               : str|None  — set only if a step failed fatally
        """
        steps = []

        # SOC safety guard — read from last stats rather than calling get_stats()
        # to avoid an extra API call in the reset sequence.
        try:
            live = await self.get_stats()
            soc = None
            if hasattr(live, "battery_soc"):
                soc = live.battery_soc
            elif isinstance(live, dict):
                soc = live.get("battery_soc")
            if soc is not None and int(soc or 0) < min_soc_pct:
                return {
                    "ok": False,
                    "steps": [f"SOC guard: battery at {soc}% < {min_soc_pct}% minimum."],
                    "error": (
                        f"Reset rejected: battery SOC ({soc}%) is below the minimum "
                        f"safe threshold ({min_soc_pct}%). Charge the battery before "
                        f"attempting a TOU mode reset."
                    ),
                }
            steps.append(f"SOC guard passed: battery at {soc}%.")
        except Exception as exc:
            # Non-fatal — proceed with reset, log the warning
            steps.append(f"SOC guard check failed (proceeding anyway): {exc}")

        # Step 1: switch to Self-Consumption
        try:
            res1 = await self.set_mode("self_consumption")
            steps.append(f"Step 1: set_mode(Self-Consumption) → {res1}")
        except Exception as exc:
            return {
                "ok": False,
                "steps": steps,
                "error": f"Step 1 (set Self-Consumption) failed: {exc}",
            }

        # Step 2: brief pause for firmware to process the mode change
        await asyncio.sleep(3)
        steps.append("Step 2: 3 s pause complete.")

        # Step 3: switch back to Time-of-Use
        try:
            res2 = await self.set_mode("time_of_use")
            steps.append(f"Step 3: set_mode(Time-of-Use) → {res2}")
        except Exception as exc:
            return {
                "ok": False,
                "steps": steps,
                "error": (
                    f"Step 3 (restore Time-of-Use) failed: {exc}. "
                    f"Gateway may be stuck in Self-Consumption — manual intervention required."
                ),
            }

        steps.append("Step 3: set_mode(Time-of-Use) sent — polling for gateway ACK.")

        # Step 4: Poll getGatewayTouListV2 to verify sync cleared.
        #
        # Mirrors mobile app behaviour: after updateTouModeV2, the app polls
        # getGatewayTouListV2 repeatedly at ~15 s intervals watching for
        # touSendStatus to return to null (gateway acknowledged the new schedule).
        #
        # touSendStatus=3 may persist as a false positive even after the gateway
        # successfully updated its local DB — if so we still return ok=True but
        # set sync_cleared=False so FHAI can surface the appropriate message.
        sync_cleared = False
        final_send_status = None
        final_alert_message = ""
        _gw = self.gateway  # short label for log lines
        logger.debug(
            f"[{_gw}] reset_tou_mode: starting sync verification "
            f"(max {max_verify_attempts} attempts × {verify_interval_s} s)."
        )
        for attempt in range(1, max_verify_attempts + 1):
            msg = f"[{_gw}] reset_tou_mode: attempt {attempt}/{max_verify_attempts} — waiting {verify_interval_s} s before poll."
            logger.debug(msg)
            steps.append(f"Step 4 attempt {attempt}/{max_verify_attempts}: waiting {verify_interval_s} s…")
            await asyncio.sleep(verify_interval_s)
            try:
                verify_resp = await self.get_gateway_tou_list()
                verify_result = verify_resp.get("result", {})
                final_send_status = verify_result.get("touSendStatus")
                final_alert_message = verify_result.get("touAlertMessage") or ""
                if final_send_status is None:
                    sync_cleared = True
                    msg = (
                        f"[{_gw}] reset_tou_mode: attempt {attempt} — "
                        f"touSendStatus=null. Gateway ACK received, sync confirmed. ✓"
                    )
                    logger.debug(msg)
                    steps.append(
                        f"Step 4 attempt {attempt}: touSendStatus=null — "
                        f"gateway ACK received, sync confirmed."
                    )
                    break
                else:
                    msg = (
                        f"[{_gw}] reset_tou_mode: attempt {attempt} — "
                        f"touSendStatus={final_send_status} (still pending/failed). "
                        f"Alert: '{final_alert_message}'. Retrying…"
                    )
                    logger.warning(msg)
                    steps.append(
                        f"Step 4 attempt {attempt}: touSendStatus={final_send_status} "
                        f"(still pending/failed). Retrying…"
                    )
            except Exception as exc:
                msg = f"[{_gw}] reset_tou_mode: attempt {attempt} — poll failed: {exc}. Retrying…"
                logger.warning(msg)
                steps.append(f"Step 4 attempt {attempt}: poll failed ({exc}). Retrying…")

        if sync_cleared:
            logger.debug(f"[{_gw}] reset_tou_mode: COMPLETE — schedule sync confirmed.")
            steps.append("TOU mode reset complete — schedule sync confirmed.")
        else:
            logger.warning(
                f"[{_gw}] reset_tou_mode: UNCONFIRMED after {max_verify_attempts} attempts. "
                f"final touSendStatus={final_send_status}. "
                f"Possible false positive — gateway may have applied without sending ACK."
            )
            steps.append(
                f"TOU mode reset sent but sync unconfirmed after {max_verify_attempts} attempts "
                f"(touSendStatus={final_send_status}). "
                f"This may be a false positive — the gateway may have applied the schedule "
                f"without the ACK reaching the cloud platform. Monitor run_status to verify."
            )

        return {
            "ok": True,          # mode toggle succeeded regardless of sync ACK
            "sync_cleared": sync_cleared,
            "final_send_status": final_send_status,
            "final_alert_message": final_alert_message,
            "steps": steps,
            "error": None,
        }

    async def get_system_settings(self):
        """Get system setting parameters for the gateway.

        Returns
        -------
        dict
            System settings including pcs settings, grid limits, RSD, etc.
        """
        url = self.url_base + "hes-gateway/terminal/system/getSystemSetting"
        params = {"gatewayId": self.gateway}
        data = await self._get(url, params=params)
        return data.get("result", data)

    async def update_system_settings(self, is_pcs_dischg_en: int | None = None, **kwargs):
        """Update system settings for the gateway.

        Parameters
        ----------
        is_pcs_dischg_en : int, optional
            1 = Enable PCS Discharge, 0 = Disable
        """
        url = self.url_base + "hes-gateway/terminal/system/updateSystemSetting"
        payload = {"gatewayId": self.gateway}
        if is_pcs_dischg_en is not None:
            payload["isPcsDischgEn"] = is_pcs_dischg_en
        for k, v in kwargs.items():
            payload[k] = v
        data = await self._post(url, payload, suppress_params=True, suppress_gateway=True)
        return data

    async def get_page_by_type_list(self, type_list: str):
        """Get help tips/messages by page type lists.

        Parameters
        ----------
        type_list : str
            Comma-separated type lists (e.g. "sdcpSwitchModeTip,modeListPageVppTip")
        """
        url = self.url_base + "hes-gateway/common/getPageByTypeList"
        params = {"typeList": type_list, "gatewayId": self.gateway}
        data = await self._get(url, params=params)
        return data.get("result", data)

