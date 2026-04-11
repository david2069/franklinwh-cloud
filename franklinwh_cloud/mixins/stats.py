"""Stats and runtime data API methods."""

import json
import logging
from datetime import datetime, timedelta

from franklinwh_cloud.models import Stats, Current, Totals, GridStatus, GridConnectionState, empty_stats, MqttCmd
from franklinwh_cloud.const import OPERATING_MODES, RUN_STATUS

logger = logging.getLogger("franklinwh_cloud")


class StatsMixin:
    """Runtime stats, power data, and status methods."""

    async def _status(self):
        """Send a 203 — high-level device status query."""
        payload = self._build_payload(MqttCmd.STATUS, {"opt": 1, "refreshData": 1})  # cmdType 203
        data = (await self._mqtt_send(payload))["result"]["dataArea"]
        return json.loads(data)

    async def _switch_status(self):
        """Send a 311 — more specific switch command."""
        payload = self._build_payload(MqttCmd.SMART_CIRCUIT_INFO, {"opt": 0, "order": self.gateway})  # cmdType 311
        data = (await self._mqtt_send(payload))["result"]["dataArea"]
        return json.loads(data)

    async def _switch_usage(self):
        """Send a 353 — real-time smart-circuit load information."""
        payload = self._build_payload(MqttCmd.ACCESSORY_LOADS, {"opt": 0, "order": self.gateway})  # cmdType 353
        data = (await self._mqtt_send(payload))["result"]["dataArea"]
        return json.loads(data)

    async def get_stats(self, *, include_electrical: bool = False) -> Stats:
        """Get current statistics for the FranklinWH gateway.

        This includes instantaneous measurements for current power
        (solar, battery, grid, home load) as well as totals for today
        (in local time). Returns empty_stats() if the API call fails.

        Parameters
        ----------
        include_electrical : bool, optional
            When True, also calls get_power_info() (cmdType 211) to populate
            voltage, current, frequency, and extended relay fields in Current.
            This adds one extra MQTT round-trip. Use on a slow cadence (e.g.
            every 5th poll) rather than on every tick. Default False.

        Returns
        -------
        Stats
            Stats object with current power readings and daily totals.
        """
        res = await self.get_device_composite_info()
        data_v2 = res.get("result")
        if not data_v2:
            return empty_stats()

        workMode = data_v2.get("currentWorkMode", 1)
        if workMode is None:
            workMode = 1

        workMode_desc = await self.get_operating_mode_name(workMode)
        solarHaveVo = data_v2.get("solarHaveVo") or {}
        runtimedata_v2 = data_v2.get("runtimeData") or {}

        run_status = int(runtimedata_v2.get("run_status", 0) or 0)
        run_desc = RUN_STATUS.get(run_status, "Unknown")
        offGridFlag = solarHaveVo.get("offGridFlag", runtimedata_v2.get("offGridFlag", 0))
        offgridreason = runtimedata_v2.get("offgridreason", solarHaveVo.get("offGridReason", 0))
        offGridReason = solarHaveVo.get("offGridReason", runtimedata_v2.get("offgridreason", 0))
        logger.debug(f"get_stats: offGridFlag={offGridFlag}, offGridReason={offGridReason}")

        # Grid connection state — four-state enum, no ambiguity.
        # Live-confirmed encoding (2026-04-10):
        #   main_sw[0]=1=CLOSED=connected, 0=OPEN=disconnected
        #   offgridreason=1 during SIMULATED_OFF_GRID (set before main_sw updates — API lag)
        #   offGridFlag=1 = firmware-authoritative actual outage
        #
        # Dual-gate: trigger get_grid_status() when EITHER signal is present, because the
        # API may report offgridreason before updating main_sw (observed live 2026-04-10).
        main_sw_early = runtimedata_v2.get("main_sw", [])
        grid_relay_raw = main_sw_early[0] if main_sw_early else 1  # 1=CLOSED=connected default
        offgridreason_val = offgridreason if offgridreason is not None else 0

        # Grid topology — integrator sets self._not_grid_tied at Client construction from DB.
        # No get_entrance_info() call here. Zero overhead on every poll.
        if self._not_grid_tied:
            grid_connection_state = GridConnectionState.NOT_GRID_TIED
        elif bool(offGridFlag):
            # Firmware-authoritative: grid was lost (offGridFlag set by aGate, not user)
            grid_connection_state = GridConnectionState.OUTAGE
        elif grid_relay_raw == 0 or offgridreason_val:
            # Dual-gate: relay OPEN OR offgridreason set (handles API reporting lag where
            # offgridreason=1 arrives before main_sw updates — confirmed live 2026-04-10)
            try:
                gs = await self.get_grid_status()
                gs_result = gs.get("result", gs) if isinstance(gs, dict) else {}
                if gs_result.get("offgridState", 0) == 1:
                    grid_connection_state = GridConnectionState.SIMULATED_OFF_GRID
                else:
                    # Relay open but not user-simulated — treat as outage
                    grid_connection_state = GridConnectionState.OUTAGE
            except Exception as e:
                logger.warning(f"get_stats: get_grid_status() failed during gate check: {e}")
                grid_connection_state = GridConnectionState.OUTAGE  # safe fallback
        else:
            grid_connection_state = GridConnectionState.CONNECTED

        v2lModeEnable = runtimedata_v2.get("v2lModeEnable", 0) or 0
        v2lRunState = runtimedata_v2.get("v2lRunState", 0) or 0
        genEnable = runtimedata_v2.get("genEn", 0) or 0
        genStatus = runtimedata_v2.get("genStat", 0) or 0
        smart_circuits = runtimedata_v2.get("pro_load", [0, 0, 0]) or [0, 0, 0]
        if any(smart_circuits):
            sw_data = await self._switch_usage()
        else:
            sw_data = None

        alarmsCount = 0

        if not sw_data:
            sw_data = {}

        sw1_pwr = sw_data.get("SW1ExpPower", 0.0)
        sw2_pwr = sw_data.get("SW2ExpPower", 0.0)
        car_sw_pwr = sw_data.get("CarSWPower", 0.0)

        # Primary relays — always from runtimeData.main_sw[]
        # FW convention: main_sw is [Grid, Generator, Solar/load]
        # get_power_info() (cmdType 211) is NOT called here — it duplicates these fields
        # under different names and adds unnecessary MQTT overhead on every poll.
        # Call get_power_info() explicitly when electrical metrics or extended relays
        # (gridRelay2, blackStartRelay, pvRelay2, BFPVApboxRelay) are required.
        main_sw = runtimedata_v2.get("main_sw", [])
        grid_relay1  = main_sw[0] if len(main_sw) > 0 else 0
        oil_relay    = main_sw[1] if len(main_sw) > 1 else 0
        solar_relay1 = main_sw[2] if len(main_sw) > 2 else 0

        # Extended relays and electrical metrics from get_power_info() (cmdType 211).
        # Only populated when include_electrical=True to avoid an extra MQTT round-trip
        # on every poll. Callers should use this on a slow cadence (e.g. every 5th poll).
        grid_relay2 = 0
        black_start_relay = 0
        pv_relay2 = 0
        bfpv_apbox_relay = 0
        grid_vol1 = 0.0
        grid_vol2 = 0.0
        grid_cur1 = 0.0
        grid_cur2 = 0.0
        grid_freq = 0.0
        grid_set_freq = 0.0
        grid_line_vol = 0.0
        gen_vol = 0.0

        if include_electrical:
            try:
                pi = await self.get_power_info()
                # gridLineVol is a raw integer in tenths of a volt (e.g. 2440 = 244.0V)
                raw_line = pi.get("gridLineVol", 0)
                grid_line_vol = round(float(raw_line) / 10, 1) if raw_line else 0.0
                grid_vol1      = float(pi.get("gridVol1", 0.0) or 0.0)
                grid_vol2      = float(pi.get("gridVol2", 0.0) or 0.0)
                grid_cur1      = float(pi.get("gridCurr1", 0.0) or 0.0)
                grid_cur2      = float(pi.get("gridCurr2", 0.0) or 0.0)
                grid_freq      = float(pi.get("gridFreq", 0.0) or 0.0)
                grid_set_freq  = float(pi.get("dspSetFreq", 0.0) or 0.0)
                gen_vol        = float(pi.get("genVoltage", 0.0) or 0.0)
                # Extended relays — raw firmware values (1=OPEN, 0=CLOSED)
                grid_relay2       = int(pi.get("gridRelay2", 0) or 0)
                black_start_relay = int(pi.get("blackStartRelay", 0) or 0)
                pv_relay2         = int(pi.get("pvRelay2", 0) or 0)
                bfpv_apbox_relay  = int(pi.get("BFPVApboxRelay", 0) or 0)
                # Load & EV relays (APBox / smart circuit contactors)
                load_relay1       = int(pi.get("loadRelay1Stat", 0) or 0)
                load_relay2       = int(pi.get("loadRelay2Stat", 0) or 0)
                v2l_relay         = int(pi.get("evRelayStat", 0) or 0)
                load_solar_relay1 = int(pi.get("loadSolarRelay1Stat", 0) or 0)
                load_solar_relay2 = int(pi.get("loadSolarRelay2Stat", 0) or 0)
            except Exception as e:
                logger.warning(f"get_stats: get_power_info() failed, electrical fields zeroed: {e}")

        return Stats(
            Current(
                runtimedata_v2.get("p_sun", 0.0),
                runtimedata_v2.get("p_gen", 0.0),
                runtimedata_v2.get("p_fhp", 0.0),
                runtimedata_v2.get("p_uti", 0.0),
                runtimedata_v2.get("p_load", 0.0),
                runtimedata_v2.get("soc", 0.0),
                sw1_pwr, sw2_pwr, car_sw_pwr,
                grid_connection_state,
                workMode,
                workMode_desc,
                data_v2.get("deviceStatus", 0),
                runtimedata_v2.get("mode", 0),
                runtimedata_v2.get("name", "Unknown"),
                runtimedata_v2.get("run_status", 0),
                run_desc,
                runtimedata_v2.get("fhpSn", []),
                runtimedata_v2.get("fhpSoc", []),
                runtimedata_v2.get("fhpPower", []),
                runtimedata_v2.get("bms_work", []),
                runtimedata_v2.get("t_amb", 0.0),
                grid_relay1,
                oil_relay,
                solar_relay1,
                runtimedata_v2.get("signal", 0.0),
                runtimedata_v2.get("wifiSignal", 0.0),
                runtimedata_v2.get("connType", 0),
                runtimedata_v2.get("v2lModeEnable", 0),
                runtimedata_v2.get("v2lRunState", 0),
                runtimedata_v2.get("genEn", 0),
                runtimedata_v2.get("genStat", 0),
                runtimedata_v2.get("gridChBat", 0.0),
                runtimedata_v2.get("soOutGrid", 0.0),
                runtimedata_v2.get("soChBat", 0.0),
                runtimedata_v2.get("batOutGrid", 0.0),
                runtimedata_v2.get("apbox20Pv", 0.0),
                runtimedata_v2.get("remoteSolarEn", 0),
                runtimedata_v2.get("mpptSta", 0),
                runtimedata_v2.get("mpptAllPower", 0.0),
                runtimedata_v2.get("mpptActPower", 0.0),
                runtimedata_v2.get("mPanPv1Power", 0.0),
                runtimedata_v2.get("mPanPv2Power", 0.0),
                runtimedata_v2.get("remoteSolar1Power", 0.0),
                runtimedata_v2.get("remoteSolar2Power", 0.0),
                alarmsCount,
                grid_relay2,
                black_start_relay,
                pv_relay2,
                bfpv_apbox_relay,
                grid_vol1, grid_vol2,
                grid_cur1, grid_cur2,
                grid_freq, grid_set_freq,
                grid_line_vol,
                gen_vol,
                switch_1_state=smart_circuits[0] if len(smart_circuits) > 0 else 0,
                switch_2_state=smart_circuits[1] if len(smart_circuits) > 1 else 0,
                switch_3_state=smart_circuits[2] if len(smart_circuits) > 2 else 0,
                # APBox / MPPT config flags
                mppt_en_flag=bool(runtimedata_v2.get("mpptEnFlag", False)),
                mppt_export_en=int(runtimedata_v2.get("mpptExportEn", 0) or 0),
                install_pv1_port=int(runtimedata_v2.get("installPv1Port", 0) or 0),
                install_pv2_port=int(runtimedata_v2.get("installPv2Port", 0) or 0),
                remote_solar_mode=int(solarHaveVo.get("remoteSolarMode", 0) or 0),
                # Hardware install config (static site topology)
                pv_split_ct_en=int(runtimedata_v2.get("pvSplitCtEn", 0) or 0),
                grid_split_ct_en=int(runtimedata_v2.get("gridSplitCtEn", 0) or 0),
                install_proximal_solar=int(runtimedata_v2.get("installProximalsolar", 0) or 0),
                is_three_phase_install=int(runtimedata_v2.get("isThreePhaseInstall", 0) or 0),
                # Load & V2L relays (only populated when include_electrical=True)
                load_relay1=locals().get("load_relay1", 0),
                load_relay2=locals().get("load_relay2", 0),
                v2l_relay=locals().get("v2l_relay", 0),
                load_solar_relay1=locals().get("load_solar_relay1", 0),
                load_solar_relay2=locals().get("load_solar_relay2", 0),
            ),
            Totals(
                runtimedata_v2.get("kwh_fhp_chg", 0.0),
                runtimedata_v2.get("kwh_fhp_di", 0.0),
                runtimedata_v2.get("kwh_uti_in", 0.0),
                runtimedata_v2.get("kwh_uti_out", 0.0),
                runtimedata_v2.get("kwh_sun", 0.0),
                runtimedata_v2.get("kwh_gen", 0.0),
                runtimedata_v2.get("kwh_load", 0.0),
                sw_data.get("SW1ExpEnergy", 0.0),
                sw_data.get("SW2ExpEnergy", 0.0),
                sw_data.get("CarSWExpEnergy", 0.0),
                sw_data.get("CarSWImpEnergy", 0.0),
                runtimedata_v2.get("kwhSolarLoad", 0.0),
                runtimedata_v2.get("kwhGridLoad", 0.0),
                runtimedata_v2.get("kwhFhpLoad", 0.0),
                runtimedata_v2.get("kwhGenLoad", 0.0),
                runtimedata_v2.get("mpanPv1Wh", 0.0),
                runtimedata_v2.get("mpanPv2Wh", 0.0),
            ),
        )

    async def get_runtime_data(self):
        """Get runtime data — similar to getDeviceCompositeInfo with extra relays.

        Has similar info as get_device_composite_info but also includes relays
        not listed there: gridRelay2, pvRelay2, BlackStartRelay,
        sinLTemp, sinHTemp, t_amb.

        Returns
        -------
        dict
            Runtime data including relay states and temperature readings
        """
        url = self.url_base + "hes-gateway/terminal/selectIotUserRuntimeDataLog"
        params = {"gatewayId": self.gateway, "type": 1, "lang": "EN_US"}
        data = await self._get(url, params=params)
        return data["result"]

    async def get_power_by_day(self, dayTime):
        """Get power details for a specified day.

        Parameters
        ----------
        dayTime : str
            Requested day in YYYY-MM-DD format

        Returns
        -------
        dict
            Power details for the specified day
        """
        url = self.url_base + "hes-gateway/api-energy/power/getFhpPowerByDay"
        params = {"gatewayId": self.gateway, "dayTime": f"{dayTime}"}
        data = await self._get(url, params=params)
        return data.get("result", data)

    async def get_power_details(self, type, timeperiod):
        """Get power details aggregated by day, week, month, or year.

        Parameters
        ----------
        type : int
            1=Day, 2=Week, 3=Month, 4=Year, 5=Total
        timeperiod : str
            Target date of the date range
        """
        url = self.url_base + "hes-gateway/api-energy/electic/getFhpPowerData"
        params = {"gatewayId": self.gateway, "type": type, "dayTime": f"{timeperiod}"}
        data = await self._get(url, params=params)
        return data.get("result", data)

    def calculate_remaining_time(start_time_str, end_time_str):
        """Calculate remaining time between two HH:MM time strings.

        Parameters
        ----------
        start_time_str : str
            Start time in HH:MM format
        end_time_str : str
            End time in HH:MM format (wraps past midnight if needed)

        Returns
        -------
        str
            Human-readable duration, e.g. '7 hours and 30 minutes'
        """
        fmt = "%H:%M"
        start_time = datetime.strptime(start_time_str, fmt)
        end_time = datetime.strptime(end_time_str, fmt)
        if end_time <= start_time:
            end_time += timedelta(days=1)
        time_diff = end_time - start_time
        hours = time_diff.seconds // 3600
        minutes = (time_diff.seconds % 3600) // 60
        return f"{hours} hours and {minutes} minutes"
