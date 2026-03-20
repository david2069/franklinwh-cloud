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

        res = await self._post(url, payload=None, supressGateway=True, suppressParams=True)
        if res['code'] == 200:
            result = True
            logger.info(f"set_mode: Successfully switched operating mode to '{mode_name}' for aGate {self.gateway}")
        else:
            logger.error(f"set_mode: failed switched operating mode to '{mode_name}' currendId={currendId} oldIndex={oldIndex} for aGate {self.gateway}: {res}")
            result = False

        return result

    async def get_mode(self, requestedMode=None):
        """Return the current or requested operating mode details.

        Parameters
        ----------
        requestedMode : int, optional
            Mode to query. If None, returns current mode details.
        """
        res = await self.get_device_composite_info()
        runtimeData = res["result"]["runtimeData"]
        solarHaveVo = res["result"]["solarHaveVo"]
        soc = runtimeData["soc"]
        currentWorkMode = str(res["result"]["currentWorkMode"])
        runMode = str(res["result"]["runtimeData"]["mode"])
        if requestedMode is not None:
            logger.info(f"get_mode: requestedMode = {requestedMode}")
            targetMode = requestedMode
        else:
            logger.info(f"get_mode: Retrieving current operating mode for aGate {self.gateway}")
            targetMode = currentWorkMode

        deviceStatus = res["result"]["deviceStatus"]
        valid = str(res["result"]["valid"])
        currentAlarmVOList = str(res["result"]["currentAlarmVOList"])
        run_status = int(res["result"]["runtimeData"]["run_status"])
        if run_status is not None:
            run_desc = RUN_STATUS.get(run_status, f"Unknown run_status value = {run_status}")
        else:
            run_desc = "Unknown"

        report_type = str(res["result"]["runtimeData"]["report_type"])
        if currentAlarmVOList == "[]":
            currentAlarmVOList = None
            alarmsCount = 0
        else:
            alarmsCount = sum(1 for obj in currentAlarmVOList if obj['id'] is not None)

        res = await self.get_unread_count()
        unreadMsgCount = res["result"]
        logger.info(f"get_mode: aGate {self.gateway} targetMode={targetMode}  ({OPERATING_MODES.get(int(currentWorkMode))}), soc={soc}, runMode={runMode},   run_status={run_status} ({run_desc}), deviceStatus={deviceStatus}, alarmsCount={alarmsCount}")

        offGridReason = solarHaveVo.get("offGridReason", runtimeData.get("offgridreason", 0))
        offGridFlag = solarHaveVo.get("offGridFlag", runtimeData.get("offGridFlag", 0))
        main_sw = runtimeData["main_sw"]
        grid_relay1 = main_sw[0]
        generator_relay = main_sw[1]
        solar_relay1 = main_sw[2]
        logger.info(f"offGridReason={offGridReason}, offGridFlag={offGridFlag}, grid_relay1={grid_relay1}, generator_relay={generator_relay}, solar_relay1={solar_relay1} ")

        logger.info(f"get_mode: Retrieving current TOU schedule for aGate {self.gateway} to match runMode with currendId")
        res = await self.get_gateway_tou_list()
        if res["code"] != 200:
            logger.info("get_mode: Error in getGatewayTouListV2: Unable to retrieve TOU List")
        else:
            currendId = res["result"]["currendId"]
            modeDetails = res["result"]["list"]
            touList = [x for x in modeDetails if x["id"] == int(currendId)]
            if touList:
                logger.info(f"get_mode: Success: currendId={currendId} was found")
            else:
                logger.info(f"get_mode: Error: currendId={currendId} was NOT found in result list")

        stopMode = str(res["result"]["stopMode"])
        stromEn = str(res["result"]["stromEn"])
        gridChargeEn = str(res["result"]["gridChargeEn"])
        touSendStatus = str(res["result"]["touSendStatus"])
        touAlertMessage = str(res["result"]["touAlertMessage"])
        nextWorkMode = str(res["result"]["nextWorkMode"])
        backupForeverFlag = str(res["result"]["backupForeverFlag"])
        timerEndTime = str(res["result"]["timerEndTime"])
        timerEndTimeZero = str(res["result"]["timerEndTimeZero"])
        timerStartTime = str(res["result"]["timerStartTime"])
        timerStartTimeZero = str(res["result"]["timerStartTimeZero"])
        if timerEndTime != "00:00:00.000000" and timerStartTime != "00:00:00.000000":
            durationMinute = "0"
        else:
            EndTime = datetime.strptime(timerEndTime, "%H:%M:%S")
            StartTime = datetime.strptime(timerStartTime, "%H:%M:%S")
            durationMinute = EndTime - StartTime
        zoneInfo = str(res["result"]["zoneInfo"])
        stopTime = None

        modeDetails = res["result"]["list"]
        touList = list(filter(lambda x: x["workMode"] == int(targetMode), modeDetails))
        logger.info(f"get_mode: Found currentWorkMode in touList = {touList}")
        if touList:
            touId = touList[0]["id"]
            workMode = touList[0]["workMode"]
            oldIndex = touList[0]["oldIndex"]
            name = touList[0]["name"]
            current_soc = touList[0]["soc"]
            editSocFlag = touList[0]["editSocFlag"]
            electricityType = touList[0]["electricityType"]
            maxSoc = touList[0]["maxSoc"]
            minSoc = touList[0]["minSoc"]
            logger.info(f"get_mode: Retrieved operating mode details for currendId={currendId}: targetMode={targetMode}, workMode={workMode}, oldIndex={oldIndex}, name={name}, soc={current_soc}, editSocFlag={editSocFlag}, electricityType={electricityType}, maxSoc={maxSoc}, minSoc={minSoc}")
            logger.info(f"get_mode: aGate {self.gateway} matched runMode={runMode} with currendId={touId}, workMode={workMode} ({OPERATING_MODES.get(int(workMode), 'Unknown')}), run_status={run_status} ({run_desc}), soc={soc}, oldIndex={oldIndex}")

            mode_specific = {}
            common_list = {}
            currentWorkMode = int(currentWorkMode)
            logger.info(f"get_mode: targetMode={targetMode}, currentWorkMode={currentWorkMode}")

            match currentWorkMode:
                case workModeType.TIME_OF_USE.value:
                    logger.info(f"get_mode: workModeType.TIME_OF_USE.value: = {workModeType.TIME_OF_USE.value}")
                    url = f"&currendId={touId}&soc={current_soc}&oldIndex={oldIndex}&workMode={workMode}&electricityType={electricityType}"
                    OPTION = 1
                    touScheduleList = await self.get_tou_info(OPTION)
                    mode_specific = {
                        "touScheduleList": touScheduleList,
                        "touAlertMessage": touAlertMessage,
                        "touSendStatus": touSendStatus,
                    }
                case workModeType.SELF_CONSUMPTION.value:
                    logger.info(f" workModeType.SELF_CONSUMPTION.value: = {workModeType.SELF_CONSUMPTION.value}")
                    url = f"&currendId={touId}&soc={current_soc}&oldIndex={oldIndex}&workMode={workMode}&electricityType={electricityType}"
                case workModeType.EMERGENCY_BACKUP.value:
                    logger.info(f" workModeType.EMERGENCY_BACKUP.value: = {workModeType.EMERGENCY_BACKUP.value}")
                    url = f"&currendId={touId}&electricityType={electricityType}&oldIndex={oldIndex}&workMode={workMode}&backupForeverFlag={backupForeverFlag}&nextWorkMode={nextWorkMode}&durationMinute={durationMinute}"
                    mode_specific = {
                        "backupForeverFlag": backupForeverFlag,
                        "oldIndex": oldIndex,
                        "nextWorkMode": nextWorkMode,
                        "durationMinute": durationMinute,
                    }

            common_list = {
                "currendId": touId,
                "workMode": workMode,
                "modeName": MODE_MAP[int(workMode)],
                "name": OPERATING_MODES[int(workMode)],
                "soc": current_soc,
                "minSoc": minSoc,
                "maxSoc": maxSoc,
                "run_status": run_status,
                "run_desc": run_desc,
                "electricityType": electricityType,
                "url": url,
                "deviceStatus": deviceStatus,
                "valid": valid,
                "unreadMsgCount": unreadMsgCount,
                "alarmsCount": alarmsCount,
                "currentAlarmVOList": currentAlarmVOList,
                "report_type": report_type,
                "offgridState": offGridReason,
                "editSocFlag": editSocFlag,
            }
            results = common_list
            if mode_specific:
                results.update(mode_specific)
            logger.info("get_mode: successfully returned results")
            return results

        results = {"Failed to find current mode details:  workMode = " + str(currentWorkMode) + ", " +
                   OPERATING_MODES[int(currentWorkMode)] +
                   ", run_status = " + str(run_status) +
                   ", run_desc = " + str(run_desc) +
                   ", runMode = " + str(runMode) +
                   ", currentAlarmVOList = " + str(currentAlarmVOList)
                   }
        logger.error(f"get_mode: Failed to find current mode details {results}")
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
