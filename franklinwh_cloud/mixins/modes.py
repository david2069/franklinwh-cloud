"""Operating mode set/get API methods.

Provides set_mode, get_mode, update_soc, and get_mode_info for controlling
the FranklinWH aGate operating mode via the Cloud API.

API URL parameter reference (from richo/franklinwh-python original):
    Time of Use:        currendId=9322&gatewayId=___&lang=EN_US&oldIndex=3&soc=15&stromEn=1&workMode=1
    Self Consumption:   currendId=9323&gatewayId=___&lang=EN_US&oldIndex=2&soc=20&stromEn=1&workMode=2
    Emergency Backup:   currendId=9324&gatewayId=___&lang=EN_US&oldIndex=1&soc=100&stromEn=1&workMode=3
"""

import logging
from datetime import datetime, timedelta

from franklinwh_cloud.api import DEFAULT_URL_BASE
from franklinwh_cloud.const import (
    RUN_STATUS, OPERATING_MODES, workModeType,
    TIME_OF_USE, SELF_CONSUMPTION, EMERGENCY_BACKUP,
    MODE_MAP,
)
from franklinwh_cloud.exceptions import InvalidOperatingMode, InvalidOperatingModeOption

logger = logging.getLogger("franklinwh_cloud")


class ModesMixin:
    """Operating mode control — set_mode, get_mode, update_soc, get_mode_info.

    Controls the FranklinWH aGate operating mode via the Cloud API.
    Three modes are supported:

        1 = Time of Use (TOU)        — schedule-based battery dispatch
        2 = Self Consumption          — maximise solar self-consumption
        3 = Emergency Backup          — reserve battery for grid outages

    Each mode has a currendId (TOU list entry ID), workMode, oldIndex, and SOC setpoint.
    The API endpoint is ``hes-gateway/terminal/tou/updateTouModeV2``.
    """

    async def set_mode(self, requestedOperatingMode, requestedSOC, reqbackupForeverFlag, reqnextWorkMode, reqdurationMinutes):
        """Set the Operating Work Mode.

        Switch from current to requestedOperatingMode value.

        Parameters
        ----------
        requestedOperatingMode : int or str
            The requested operating mode:
                1 = Time of Use
                2 = Self Consumption
                3 = Emergency Backup

            Extended TOU aliases (all map to mode 1 internally):
                'tou_battery_import' — Force battery to import from grid
                'tou_battery_export' — Force battery to export to grid
                'tou_custom'         — Pre-defined custom TOU schedules
                'tou_json'           — User-defined TOU schedule as JSON payload

        TOU and Self-Consumption modes:
        ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        requestedSOC : int, optional
            Change reserved State of Charge percentage (0-100).
            If not specified, the existing SOC value is retained.
            Accepts: int, str digits, str with '%' suffix, None.

        Emergency Backup mode only:
        ~~~~~~~~~~~~~~~~~~~~~~~~~~~
        reqbackupForeverFlag : int (MANDATORY)
            1 = Indefinitely (backup until manually changed)
            2 = Fixed duration (requires reqdurationMinutes)
        reqnextWorkMode : int (MANDATORY)
            The next work mode after Emergency Backup ends:
                1 = Time of Use
                2 = Self Consumption
        reqdurationMinutes : int (MANDATORY if reqbackupForeverFlag=2)
            Duration in minutes for Emergency Backup (30–4320, i.e. 30 min to 3 days)

        Returns
        -------
        bool
            True if mode was switched successfully, False otherwise.

        Note
        ----
        In theory only the target mode is really needed for TOU or
        Self-Consumption. Emergency Backup requires additional params
        to control duration and what happens after backup ends.
        """
        logger.info(f"set_mode: Requested Operating Mode: {requestedOperatingMode}, Reserve SOC: {requestedSOC}, Backup Forever Flag: {reqbackupForeverFlag}, Next Work Mode: {reqnextWorkMode}, Duration Minutes: {reqdurationMinutes}")
        validate_mode = str(requestedOperatingMode).lower().replace(' ', '_').replace('-', '_')
        tou_mode = None

        # These are custom aliases for TOU mode — they all map to the same working mode
        #   tou_battery_import | Force battery to import from grid (if configured)
        #   tou_battery_export | Force battery to export to grid (if configured)
        #   tou_custom         | Pre-defined custom TOU schedules built-in to set_tou_schedule()
        #   tou_json           | User-defined TOU schedule provided as JSON payload
        logger.info(f"set_mode: Validating requested Operating Mode: {validate_mode}")
        match validate_mode:
            case "tou_battery_import" | "tou_battery_export" | "tou_custom" | "tou_json":
                requestedOperatingMode = TIME_OF_USE
                tou_mode = validate_mode
            case "1":
                requestedOperatingMode = TIME_OF_USE
                tou_mode = validate_mode
            case "2":
                requestedOperatingMode = SELF_CONSUMPTION
            case "3":
                requestedOperatingMode = EMERGENCY_BACKUP
                if reqnextWorkMode not in [TIME_OF_USE, SELF_CONSUMPTION]:
                    raise InvalidOperatingMode(f"Emergency Backup Next Working Mode must be TIME_OF_USE or SELF_CONSUMPTION and NOT: {requestedOperatingMode}")
                reqnextWorkMode = int(reqnextWorkMode)
                if reqbackupForeverFlag:
                    if reqbackupForeverFlag not in ["1", "2", 1, 2]:
                        raise InvalidOperatingModeOption(f"Invalid for this mode: backupForeverFlag requested: '{reqbackupForeverFlag}'. Must be '1' (Indefinite) or '2' (Fixed Duration)")
                    reqbackupForeverFlag = int(reqbackupForeverFlag)
                if reqdurationMinutes is not None:
                    reqdurationMinutes = int(reqdurationMinutes)
                # 1 = Indefinite emergency backup, 2 = fixed number of minutes (30 min to 4320 max)
                if reqbackupForeverFlag == "2" and reqdurationMinutes is not None:
                    reqdurationMinutes = int(reqdurationMinutes)
                    if reqdurationMinutes < 30 or reqdurationMinutes > 4320:
                        raise InvalidOperatingModeOption(f"Invalid for this mode: durationMinutes requested: '{reqdurationMinutes}'. Duration must be >= 30 and <= 4320 minutes")
            case _:
                raise InvalidOperatingMode(f"Invalid mode requested: {requestedOperatingMode}")

        if requestedSOC and (requestedOperatingMode != EMERGENCY_BACKUP):
            match requestedSOC:
                case None | 'NONE' | '':
                    requestedSOC = None
                case str() as soc_str if soc_str.endswith('%'):
                    requestedSOC = soc_str.rstrip('%')
                case str() as soc_str if soc_str.isdigit():
                    requestedSOC = soc_str
                case int() as soc_int:
                    requestedSOC = soc_int
                case _:
                    raise InvalidOperatingModeOption(f"Invalid reserve SOC value requested: {requestedSOC}")

        logger.info(f"set_mode: Validated requested Operating Mode: {requestedOperatingMode}, Reserve SOC: {requestedSOC}, Backup Forever Flag: {reqbackupForeverFlag}, Next Work Mode: {reqnextWorkMode}, Duration Minutes: {reqdurationMinutes}")
        logger.info(f"set_mode: calling get_device_composite_info to get TOU details and map target mode: {requestedOperatingMode}")
        logger.info(f"set_mode: lookup MODE_MAP for {requestedOperatingMode} {MODE_MAP[requestedOperatingMode]}")

        res = await self.get_device_composite_info()
        if res['code'] != 200:
            assert res['code'] == 200, f"set_mode: Error: getDeviceCompositeInfo: {res['code']}: {res['message']} "
        logger.info("set_mode: getDeviceCompositeInfo successful response")

        valid = str(res["result"]["valid"])
        currentWorkMode = str(res["result"]["currentWorkMode"])
        logger.info(f"set_mode: currentWorkMode={currentWorkMode}")
        electricityType = 1
        deviceStatus = str(res["result"]["deviceStatus"])
        logger.info(f"set_mode: deviceStatus={deviceStatus}, valid={valid}")

        if int(deviceStatus) != 1:
            logger.info(f"set_mode: Warning: aGate {self.gateway} deviceStatus is not Normal (1) - current deviceStatus={deviceStatus}")

        runMode = str(res["result"]["runtimeData"]["mode"])

        tou_res = await self.get_gateway_tou_list()
        logger.info("set_mode: getGatewayTouListV2 successful response")
        currendId = tou_res["result"]["currendId"]
        modeDetails = tou_res["result"]["list"]
        logger.info(f"set_mode: search for requestedOperatingMode = {requestedOperatingMode} == getGatewayTouListV2() result/list/workMode")
        touList = list(filter(lambda x: x["workMode"] == int(requestedOperatingMode), modeDetails))
        logger.info(f"set_mode: Found target mode {requestedOperatingMode} in workMode in touList = {touList}")
        if touList:
            touId = touList[0]["id"]
            logger.info(f"set_mode: touId={touId}, workMode={touList[0]['workMode']}    - this needs to send to updateTouModeVoc as currendId parameter")
            workMode = touList[0]["workMode"]
            oldIndex = touList[0]["oldIndex"]
            name = touList[0]["name"]
            current_soc = touList[0]["soc"]
            editSocFlag = touList[0]["editSocFlag"]
            electricityType = touList[0]["electricityType"]
            maxSoc = touList[0]["maxSoc"]
            minSoc = touList[0]["minSoc"]
            logger.info(f"set_mode: Retrieved operating mode details for currendId={currendId}: workMode={workMode}, oldIndex={oldIndex}, name={name}, soc={current_soc}, editSocFlag={editSocFlag}, electricityType={electricityType}, maxSoc={maxSoc}, minSoc={minSoc}")
        else:
            mesg = f"set_mode: Error: requestedOperatingMode={requestedOperatingMode} was NOT found in result list"
            raise InvalidOperatingModeOption(mesg)

        backupForeverFlag = str(tou_res["result"]["backupForeverFlag"])
        nextWorkMode = tou_res["result"]["nextWorkMode"]
        tariffSettingFlag = tou_res["result"]["tariffSettingFlag"]
        touSendStatus = tou_res["result"]["touSendStatus"]
        if tariffSettingFlag:
            logger.info(f"set_mode: Warning: aGate {self.gateway} has tariffSettingFlag enabled - current tariffSettingFlag={tariffSettingFlag}")
        if touSendStatus:
            logger.info(f"set_mode: Warning: aGate {self.gateway} has touSendStatus enabled - current touSendStatus={touSendStatus}")
        stopMode = tou_res["result"]["stopMode"]
        if stopMode:
            logger.info(f"set_mode: Warning: aGate {self.gateway} is in Stop Mode - current stopMode={stopMode}")

        url = DEFAULT_URL_BASE + "hes-gateway/terminal/tou/updateTouModeV2"
        url = url + f"?gatewayId={self.gateway}"
        url = url + f"&currendId={touId}"

        logger.info(f"set_mode: Preparing to switch operating mode to {requestedOperatingMode} for aGate {self.gateway}")
        if requestedOperatingMode != EMERGENCY_BACKUP:
            if requestedSOC is None:
                soc = int(current_soc)
            else:
                soc = int(requestedSOC)
            url = url + f"&soc={soc}"

        if requestedOperatingMode == TIME_OF_USE:
            oldIndex = 3
        if requestedOperatingMode == SELF_CONSUMPTION:
            oldIndex = 2
        if requestedOperatingMode == EMERGENCY_BACKUP:
            oldIndex = 1
        url = url + f"&oldIndex={oldIndex}"
        url = url + f"&workMode={requestedOperatingMode}"

        if requestedOperatingMode == EMERGENCY_BACKUP:
            url = url + f"&backupForeverFlag={reqbackupForeverFlag}"
            if reqbackupForeverFlag == 2:
                if reqnextWorkMode not in [SELF_CONSUMPTION, TIME_OF_USE]:
                    nextWorkMode = SELF_CONSUMPTION
                else:
                    nextWorkMode = int(reqnextWorkMode)
            url = url + f"&nextWorkMode={nextWorkMode}"
            if reqdurationMinutes is not None:
                url = url + f"&durationMinute={str(int(reqdurationMinutes))}"
        res = await self.get_storm_settings()
        enableStorm = res["result"]["enableStorm"]
        url = url + f"&stromEn={enableStorm}"
        url = url + f"&electricityType={electricityType}"

        mode_name = MODE_MAP.get(requestedOperatingMode, f"Unknown Mode {requestedOperatingMode}")
        logger.info(f"set_mode: *switching operating work mode to '{mode_name}' currendId={currendId} oldIndex={oldIndex}  for aGate {self.gateway}")
        logger.info(f"set_mode: POST URL = {url}")

        res = await self._post(url, payload=None, suppress_gateway=True, suppress_params=True)
        if res['code'] == 200:
            result = True
            logger.info(f"set_mode: Successfully switched operating mode to '{mode_name}' for aGate {self.gateway}")
        else:
            logger.error(f"set_mode: failed switched operating mode to '{mode_name}' currendId={currendId} oldIndex={oldIndex} for aGate {self.gateway}: {res}")
            result = False

        return result

    async def get_mode(self, requestedMode=None):
        """Return the current or requested operating mode details.

        Calls two required APIs (composite info + TOU list) and one optional
        (unread count).  Returns a flat dict consumed by CLI mode command.

        Parameters
        ----------
        requestedMode : int, optional
            Mode to query. If None, returns current mode details.

        Returns
        -------
        dict
            Mode details including workMode, soc, run_status, deviceStatus, etc.
            On failure returns dict with 'error' key.
        """
        # ── Step 1: Composite info (required) ─────────────────────────
        try:
            composite = await self.get_device_composite_info()
        except Exception as exc:
            logger.error(f"get_mode: get_device_composite_info failed: {exc}")
            return {"error": f"Failed to get composite info: {exc}"}

        composite_result = composite.get("result")
        if not composite_result:
            return {"error": f"Composite info returned no result (code={composite.get('code')})"}

        runtime = composite_result.get("runtimeData", {})
        current_work_mode = int(composite_result.get("currentWorkMode", 0))
        target_mode = int(requestedMode) if requestedMode is not None else current_work_mode

        device_status = composite_result.get("deviceStatus")
        valid = str(composite_result.get("valid", ""))
        run_status = int(runtime.get("run_status", 0) or 0)
        run_desc = RUN_STATUS.get(run_status, f"Unknown run_status value = {run_status}")
        report_type = str(runtime.get("report_type", ""))
        run_mode = str(runtime.get("mode", ""))

        # Alarms — operate on original list, never stringify
        alarm_list = composite_result.get("currentAlarmVOList") or []
        alarms_count = sum(
            1 for obj in alarm_list
            if isinstance(obj, dict) and obj.get("id") is not None
        )

        # Off-grid state
        solar_have_vo = composite_result.get("solarHaveVo", {})
        off_grid_reason = solar_have_vo.get(
            "offGridReason", runtime.get("offgridreason", 0)
        )

        logger.info(
            f"get_mode: aGate {self.gateway} currentWorkMode={current_work_mode} "
            f"({OPERATING_MODES.get(current_work_mode)}), targetMode={target_mode}, "
            f"run_status={run_status} ({run_desc}), deviceStatus={device_status}"
        )

        # ── Step 2: TOU list (required — contains mode SoC details) ──
        try:
            tou_res = await self.get_gateway_tou_list()
        except Exception as exc:
            logger.error(f"get_mode: get_gateway_tou_list failed: {exc}")
            return {"error": f"Failed to get TOU list: {exc}"}

        if not tou_res or tou_res.get("code") != 200:
            return {"error": f"TOU list returned error (code={tou_res.get('code') if tou_res else 'None'})"}

        tou_result = tou_res["result"]
        tou_list = tou_result.get("list", [])

        # Find the matching mode entry
        mode_entry = next(
            (x for x in tou_list if x["workMode"] == target_mode), None
        )
        if not mode_entry:
            logger.error(f"get_mode: target mode {target_mode} not found in TOU list")
            return {"error": f"Mode {target_mode} ({OPERATING_MODES.get(target_mode, '?')}) not found in TOU list"}

        work_mode = mode_entry["workMode"]
        old_index = mode_entry["oldIndex"]
        current_soc = mode_entry["soc"]
        edit_soc_flag = mode_entry["editSocFlag"]
        electricity_type = mode_entry["electricityType"]
        max_soc = mode_entry["maxSoc"]
        min_soc = mode_entry["minSoc"]

        logger.info(
            f"get_mode: matched mode: workMode={work_mode}, oldIndex={old_index}, "
            f"soc={current_soc}, editSocFlag={edit_soc_flag}, "
            f"maxSoc={max_soc}, minSoc={min_soc}"
        )

        # ── Step 3: Unread count (optional — never crash if it fails) ─
        unread_msg_count = None
        try:
            unread_res = await self.get_unread_count()
            unread_msg_count = unread_res.get("result", 0)
        except Exception as exc:
            logger.warning(f"get_mode: get_unread_count failed (non-fatal): {exc}")

        # ── Step 4: Mode-specific data ────────────────────────────────
        mode_specific = {}
        if work_mode == workModeType.TIME_OF_USE.value:
            try:
                tou_schedule = await self.get_tou_info(1)
                mode_specific["touScheduleList"] = tou_schedule
            except Exception as exc:
                logger.warning(f"get_mode: get_tou_info failed (non-fatal): {exc}")
            mode_specific["touAlertMessage"] = str(tou_result.get("touAlertMessage", ""))
            mode_specific["touSendStatus"] = str(tou_result.get("touSendStatus", ""))

        elif work_mode == workModeType.EMERGENCY_BACKUP.value:
            mode_specific["backupForeverFlag"] = str(tou_result.get("backupForeverFlag", ""))
            mode_specific["oldIndex"] = old_index
            mode_specific["nextWorkMode"] = str(tou_result.get("nextWorkMode", ""))
            # Duration calculation
            timer_end = str(tou_result.get("timerEndTime", "00:00:00.000000"))
            timer_start = str(tou_result.get("timerStartTime", "00:00:00.000000"))
            if timer_end != "00:00:00.000000" and timer_start != "00:00:00.000000":
                try:
                    end_dt = datetime.strptime(timer_end.split(".")[0], "%H:%M:%S")
                    start_dt = datetime.strptime(timer_start.split(".")[0], "%H:%M:%S")
                    mode_specific["durationMinute"] = str(end_dt - start_dt)
                except ValueError:
                    mode_specific["durationMinute"] = "0"
            else:
                mode_specific["durationMinute"] = "0"

        # ── Step 5: Build return dict ─────────────────────────────────
        results = {
            "currendId": mode_entry["id"],
            "workMode": work_mode,
            "modeName": MODE_MAP[work_mode],
            "name": OPERATING_MODES[work_mode],
            "soc": current_soc,
            "minSoc": min_soc,
            "maxSoc": max_soc,
            "run_status": run_status,
            "run_desc": run_desc,
            "electricityType": electricity_type,
            "deviceStatus": device_status,
            "valid": valid,
            "unreadMsgCount": unread_msg_count,
            "alarmsCount": alarms_count,
            "currentAlarmVOList": alarm_list if alarm_list else None,
            "report_type": report_type,
            "offgridState": off_grid_reason,
            "editSocFlag": edit_soc_flag,
        }
        results.update(mode_specific)

        logger.info("get_mode: successfully returned results")
        return results

    async def update_soc(self, requestedSOC=0, workMode=0, electricityType=1):
        """Update the State of Charge (SOC) setpoint.

        https://www.franklinwh.com/support/overview/backup-reserve/

        Parameters
        ----------
        requestedSOC : int
            Reserved SOC percentage
        workMode : int
            Operating work mode to apply to
        electricityType : int
            Power source type code
        """
        url = self.url_base + "hes-gateway/terminal/tou/updateSocV2"
        params = {"workMode": workMode, "electricityType": electricityType, "soc": requestedSOC}
        data = await self._post(url, None, params=params)
        return data

    async def get_mode_info(self, requested_work_mode=1):
        """Get mode data for the specified operating working mode.

        Parameters
        ----------
        requested_work_mode : int
            Working mode to query (1=TOU, 2=Self, 3=Emergency)
        """
        data = await self.get_gateway_tou_list()
        active_current_id = data["result"]["currendId"]
        tou_list = data["result"]["list"]
        found = [x for x in tou_list if x["workMode"] == int(requested_work_mode)]
        return found

    async def get_all_mode_soc(self):
        """Return reserve SoC details for all operating modes.

        Calls ``getGatewayTouListV2`` and extracts the SoC configuration
        for each of the three operating modes (TOU, Self-Consumption,
        Emergency Backup).

        Returns
        -------
        list[dict]
            One entry per mode with keys:
            ``workMode``, ``name``, ``soc``, ``minSoc``, ``maxSoc``,
            ``editSocFlag``, ``active``.
        """
        data = await self.get_gateway_tou_list()
        current_id = data["result"]["currendId"]
        tou_list = data["result"].get("list", [])
        results = []
        for entry in tou_list:
            wm = entry.get("workMode")
            results.append({
                "workMode": wm,
                "name": OPERATING_MODES.get(wm, f"Mode {wm}"),
                "soc": entry.get("soc", 0),
                "minSoc": entry.get("minSoc", 0),
                "maxSoc": entry.get("maxSoc", 100),
                "editSocFlag": entry.get("editSocFlag", 0),
                "active": entry.get("id") == int(current_id),
            })
        return results
