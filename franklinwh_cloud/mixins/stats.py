"""Stats and runtime data API methods."""

import json
import logging
from datetime import datetime, timedelta

from franklinwh_cloud.models import Stats, Current, Totals, GridStatus, empty_stats
from franklinwh_cloud.const import OPERATING_MODES, RUN_STATUS

logger = logging.getLogger("franklinwh_cloud")


class StatsMixin:
    """Runtime stats, power data, and status methods."""

    async def _status(self):
        """Send a 203 — high-level device status query."""
        payload = self._build_payload(203, {"opt": 1, "refreshData": 1})
        data = (await self._mqtt_send(payload))["result"]["dataArea"]
        return json.loads(data)

    async def _switch_status(self):
        """Send a 311 — more specific switch command."""
        payload = self._build_payload(311, {"opt": 0, "order": self.gateway})
        data = (await self._mqtt_send(payload))["result"]["dataArea"]
        return json.loads(data)

    async def _switch_usage(self):
        """Send a 353 — real-time smart-circuit load information."""
        payload = self._build_payload(353, {"opt": 0, "order": self.gateway})
        data = (await self._mqtt_send(payload))["result"]["dataArea"]
        return json.loads(data)

    async def get_stats(self) -> Stats:
        """Get current statistics for the FranklinWH gateway.

        This includes instantaneous measurements for current power
        (solar, battery, grid, home load) as well as totals for today
        (in local time). Returns empty_stats() if the API call fails.

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

        workMode_desc = OPERATING_MODES.get(workMode, "Unknown")
        solarHaveVo = data_v2.get("solarHaveVo") or {}
        runtimedata_v2 = data_v2.get("runtimeData") or {}

        run_status = int(runtimedata_v2.get("run_status", 0) or 0)
        run_desc = RUN_STATUS.get(run_status, "Unknown")
        offGridFlag = solarHaveVo.get("offGridFlag", runtimedata_v2.get("offGridFlag", 0))
        offgridreason = runtimedata_v2.get("offgridreason", solarHaveVo.get("offGridReason", 0))
        offGridReason = solarHaveVo.get("offGridReason", runtimedata_v2.get("offgridreason", 0))
        offgridState = 1 if offGridFlag else 0
        logger.debug(f"get_stats: offGridFlag={offGridFlag}, offGridReason={offGridReason}, offgridState={offgridState}")
        grid_status: GridStatus = GridStatus.NORMAL
        if "offgridreason" in runtimedata_v2 or "offGridReason" in solarHaveVo:
            reason_val = int(offgridreason) if offgridreason is not None else 0
            if reason_val > 0:
                grid_status = GridStatus(min(2, int(reason_val)))
            else:
                grid_status = GridStatus.NORMAL

        v2lModeEnable = runtimedata_v2.get("v2lModeEnable", 0) or 0
        v2lRunState = runtimedata_v2.get("v2lRunState", 0) or 0
        genEnable = runtimedata_v2.get("genEn", 0) or 0
        genStatus = runtimedata_v2.get("genStat", 0) or 0
        smart_circuits = runtimedata_v2.get("pro_load", [0, 0, 0]) or [0, 0, 0]
        if any(smart_circuits):
            sw_data = await self._switch_usage()
        else:
            sw_data = None
        if (v2lRunState or 0) >= 1 or (genEnable or 0) >= 1:
            power_info = await self.get_power_info()
        else:
            power_info = None

        unreadMsgCount = 0
        alarmsCount = 0

        if not sw_data:
            sw_data = {}

        sw1_pwr = sw_data.get("SW1ExpPower", 0.0)
        sw2_pwr = sw_data.get("SW2ExpPower", 0.0)
        car_sw_pwr = sw_data.get("CarSWPower", 0.0)

        if not power_info:
            power_info = {}

        grid_relay1 = power_info.get("gridRelayStat", 0)
        oil_relay = power_info.get("oilRelayStat", 0)
        solar_relay1 = power_info.get("solarRelayStat", 0)
        grid_relay2 = power_info.get("gridRelay2", 0)
        black_start_relay = power_info.get("blackStartRelay", 0)
        pv_relay2 = power_info.get("pvRelay2", 0)
        bfpv_apbox_relay = power_info.get("BFPVApboxRelay", 0)
        grid_vol1 = power_info.get("gridVol1", 0.0)
        grid_vol2 = power_info.get("gridVol2", 0.0)
        grid_cur1 = power_info.get("gridCur1", 0.0)
        grid_cur2 = power_info.get("gridCur2", 0.0)
        grid_freq = power_info.get("gridFreq", 0.0)
        grid_set_freq = power_info.get("gridSetFreq", 0.0)
        grid_line_vol = power_info.get("gridLineVol", 0.0)
        gen_vol = power_info.get("genVol", 0.0)

        return Stats(
            Current(
                runtimedata_v2.get("p_sun", 0.0),
                runtimedata_v2.get("p_gen", 0.0),
                runtimedata_v2.get("p_fhp", 0.0),
                runtimedata_v2.get("p_uti", 0.0),
                runtimedata_v2.get("p_load", 0.0),
                runtimedata_v2.get("soc", 0.0),
                sw1_pwr, sw2_pwr, car_sw_pwr,
                grid_status,
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
        url = self.url_base + "/hes-gateway/api-energy/power/getFhpPowerByDay"
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
        url = self.url_base + "/hes-gateway/api-energy/electic/getFhpPowerData"
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
