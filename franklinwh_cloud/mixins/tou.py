"""Time-of-Use (TOU) schedule API methods.

Provides get/set TOU schedule, dispatch management, and schedule backup
for the FranklinWH aGate operating mode via the Cloud API.

MANDATORY USER SETUP: Default Time of Use Tariff setup. May not work
if user has defined 'Flat' or 'Tiered' rate plans.

Supports:
- Multiple seasons with month assignments
- Weekday/weekend/everyday day types
- Pricing rates (buy/sell per tariff tier)
- Full overwrite (operation=0) — the only mode the Cloud API supports

CAUTION: The saveTouDispatch API endpoint is destructive — it validates,
saves, AND switches the system to TOU mode. There is no 'update data only'
path. Calling it always forces a TOU mode switch.
"""

import json
import logging
from datetime import datetime, timedelta

from jsonschema import validate, ValidationError

from franklinwh_cloud.api import DEFAULT_URL_BASE
from franklinwh_cloud.const import (
    dispatchCodeType, DISPATCH_CODES, WaveType, WAVE_TYPES,
    valid_tou_modes, tou_json_schema,
)
from franklinwh_cloud.const.test_fixtures import (
    gap_schedule, export_to_grid_always, export_to_grid_peak2,
    export_to_grid_peakonly, charge_from_grid, standby_schedule,
    power_home_only, charge_from_solar, self_schedule, custom_schedule,
)
from franklinwh_cloud.exceptions import InvalidTOUScheduleOption

logger = logging.getLogger("franklinwh_cloud")


class TouMixin:
    """TOU schedule management — get/set schedules, dispatch, backup.

    Key methods:
        set_tou_schedule() — Set a custom or predefined TOU schedule
        get_tou_info()     — Retrieve current/next TOU schedule items
        save_tou_dispatch() — Submit a TOU dispatch template to the aGate
        backup_tou_schedule() — Write TOU schedule to a backup file
    """

    async def get_gateway_tou_list(self):
        """Get TOU Schedule to extract current operating mode and details.

        Returns
        -------
        dict
            Full TOU configuration: currendId, mode list, timers, flags,
            stopMode, stromEn, gridChargeEn, touSendStatus
        """
        url = self.url_base + f"hes-gateway/terminal/tou/getGatewayTouListV2?gatewayId={self.gateway}"
        params = {"showType": "1", "lang": "en_US"}
        data = await self._post(url, "", params=params)
        if data["code"] != 200:
            print(f"data = {data}")
        return data

    async def get_charge_power_details(self):
        """Get charge power details.

        Returns
        -------
        dict
            Charge power configuration and current charge rates
        """
        url = self.url_base + "hes-gateway/terminal/chargePowerDetails"
        params = {"showType": "1", "lang": "en_US"}
        data = await self._get(url, params=params)
        return data

    async def save_tou_dispatch(self, payload):
        """Save the TOU Dispatch Template and send it to the aGate.

        Parameters
        ----------
        payload : dict
            JSON payload containing the TOU Dispatch Template to be saved.
            Must include detailVoList with schedule blocks.

        Returns
        -------
        dict
            API response with result containing the saved touId
        """
        url = DEFAULT_URL_BASE + "hes-gateway/terminal/tou/saveTouDispatch"
        data = await self._post(url, payload, params=None, suppress_params=True)
        return data

    async def get_tou_dispatch_detail(self):
        """Get the TOU Dispatch Template details from the aGate.

        Returns
        -------
        dict
            TOU dispatch template including detailVoList (schedule blocks),
            detailDefaultVo (default mode), and strategyList (tariff config)
        """
        url = DEFAULT_URL_BASE + "hes-gateway/terminal/tou/getTouDispatchDetail"
        params = {"gatewayId": self.gateway, "lang": "EN_US"}
        data = await self._get(url, params=params)
        return data

    async def backup_tou_schedule(self, filename=None, payload=None):
        """Write the TOU Schedule to a backup file.

        Parameters
        ----------
        filename : str, optional
            Output filename
        payload : dict, optional
            TOU schedule payload (fetched if None)
        """
        import tempfile
        import os
        default_tmpdir = tempfile.gettempdir()
        logger.info(f"default_tmpdir = {default_tmpdir}")

        if payload is None:
            payload = await self.get_tou_dispatch_detail()
        if filename is None:
            now = datetime.now()
            formatted_dt = now.strftime("%Y-%m-%d_%H:%M")
            formatted_dt.replace(":", "")
            filename = f"tou_schedule_{self.gateway}_{formatted_dt}.json"

        logger.info(f"backup_tou_schedule: Writing TOU schedule backup to filename: {filename}")

        if isinstance(payload, str):
            template = payload["result"]["template"]
            strategyList = payload["result"]["strategyList"]
            detailDefaultVo = payload["result"]["detailDefaultVo"]
            if filename is not None and not os.path.isabs(filename):
                filename = os.path.join(default_tmpdir, filename)
            logger.info(f"backup_tou_schedule: Using default temp directory for filename: {filename}")
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"# Backup of TOU schedule details {formatted_dt} to filename: {filename}\n")
                json.dump(template, f)
                f.write("\n")
                json.dump(strategyList, f)
                f.write("\n")
                json.dump(detailDefaultVo, f)
                f.write("\n")
                f.write(f"# End of file: {filename}")
                f.close()
                result = True
        else:
            result = False
        return result

    async def get_tou_info(self, option):
        """Get TOU Schedule information from the aGate.

        Parameters
        ----------
        option : int
            0 = Raw payload from get_tou_dispatch_detail
            1 = Current and next scheduled items only (active + upcoming TOU entry)
            2 = Full schedule (past, current and future) in detailVoList format (raw)

        Returns
        -------
        dict or list
            option=0: full result dict from get_tou_dispatch_detail
            option=1: dict with current + next block details (active/next keys)
            option=2: list of detailVoList entries

        Note
        ----
        Intended to return full or only current/future TOU schedule for use in HA.
        This is NOT necessary for switching modes — it is used to learn how the
        API constructs/processes the TOU schedule and to display TOU status in
        dashboards and automations.
        """
        logger.info(f"get_tou_info: option = {option}")
        res = await self.get_tou_dispatch_detail()
        if option == 0:
            return res["result"]

        touDispatchList = res["result"]["detailDefaultVo"]["touDispatchList"]
        strategyList = res["result"]["strategyList"]

        if option == 2:
            # Return full detailVoList from first season, first day type
            day_types = strategyList[0].get("dayTypeVoList", [])
            if day_types:
                return day_types[0].get("detailVoList", [])
            return []

        # ── option=1: Find current and next dispatch blocks ─────────
        now = datetime.now()
        current_month = str(now.month)
        current_weekday = now.weekday()  # 0=Mon ... 6=Sun

        for season in strategyList:
            month_str = season.get("month", "")
            if current_month not in month_str.split(","):
                continue

            logger.debug(f"get_tou_info: matched season '{season.get('seasonName')}' "
                         f"for month {current_month}")

            # ── Find the correct day type ───────────────────────────
            day_type_list = season.get("dayTypeVoList", [])
            matched_day_type = self._match_day_type(day_type_list, current_weekday)
            if matched_day_type is None:
                logger.warning("get_tou_info: no matching day type found")
                continue

            detail_vo_list = matched_day_type.get("detailVoList", [])
            if not detail_vo_list:
                logger.warning("get_tou_info: detailVoList is empty")
                continue

            # ── Sort blocks and find current/next ───────────────────
            sorted_blocks = sorted(
                detail_vo_list,
                key=lambda b: self._time_to_minutes(b.get("startHourTime", "00:00"))
            )

            current_minutes = now.hour * 60 + now.minute
            current_block = None
            next_block = None
            current_idx = None

            for i, block in enumerate(sorted_blocks):
                start_mins = self._time_to_minutes(block.get("startHourTime", "00:00"))
                end_mins = self._time_to_minutes(block.get("endHourTime", "24:00"))
                if start_mins <= current_minutes < end_mins:
                    current_block = block
                    current_idx = i
                    break

            if current_idx is not None:
                if current_idx + 1 < len(sorted_blocks):
                    next_block = sorted_blocks[current_idx + 1]
                elif len(sorted_blocks) > 1:
                    next_block = sorted_blocks[0]  # wraps to first block

            # ── Build result dict ───────────────────────────────────
            results = {}
            if current_block:
                results.update(self._build_block_info(
                    current_block, touDispatchList, now, prefix="active"
                ))
            if next_block:
                results.update(self._build_block_info(
                    next_block, touDispatchList, now, prefix="next"
                ))

            logger.info(f"get_tou_info: returning current={current_block is not None}, "
                        f"next={next_block is not None}")
            return results

        logger.warning("get_tou_info: no matching season found for current month")
        return {}

    @staticmethod
    def _time_to_minutes(time_str: str) -> int:
        """Convert HH:MM to minutes since midnight."""
        if time_str == "24:00":
            return 1440
        parts = time_str.split(":")
        return int(parts[0]) * 60 + int(parts[1])

    @staticmethod
    def _match_day_type(day_type_list: list, current_weekday: int) -> dict | None:
        """Find the correct day type entry for the current weekday.

        Parameters
        ----------
        day_type_list : list
            List of dayTypeVo entries from the API
        current_weekday : int
            Python weekday (0=Mon ... 6=Sun)

        Returns
        -------
        dict or None
            The matched day type entry, or None if no match
        """
        is_weekend = current_weekday >= 5  # Sat=5, Sun=6

        # Priority: exact match first, then everyday, then first available
        for dt in day_type_list:
            dt_code = dt.get("dayType", 0)
            if dt_code == 3:  # everyDay — always matches
                return dt
            if dt_code == 1 and not is_weekend:  # weekday
                return dt
            if dt_code == 2 and is_weekend:  # weekend
                return dt

        # Fallback: return first entry if no match (e.g. custom day type)
        return day_type_list[0] if day_type_list else None

    @staticmethod
    def _build_block_info(block: dict, touDispatchList: list,
                          now: datetime, prefix: str) -> dict:
        """Build a dict of block info with prefixed keys.

        Parameters
        ----------
        block : dict
            A detailVoList entry
        touDispatchList : list
            Available dispatch definitions from detailDefaultVo
        now : datetime
            Current datetime for remaining time calculation
        prefix : str
            'active' or 'next' — determines output key names

        Returns
        -------
        dict
            Block info with prefixed keys
        """
        block_id = str(block.get("id", ""))
        name = block.get("name", "")
        dispatch_id = block.get("dispatchId", 0)
        wave_type = block.get("waveType", 0)
        start_time = block.get("startHourTime", "00:00")
        end_time = block.get("endHourTime", "24:00")

        # Resolve dispatch details from touDispatchList
        dispatch_details = [x for x in touDispatchList if x.get("id") == dispatch_id]
        if dispatch_details:
            dd = dispatch_details[0]
            dispatch_code = dd.get("dispatchCode", "")
            title = dd.get("title", "")
            recommend_scene = dd.get("recommendScene", "")
            content = dd.get("content", "")
            solar_priority = dd.get("solarPriority", "")
            load_priority = dd.get("loadPriority", "")
        else:
            dispatch_code = ""
            title = ""
            recommend_scene = ""
            content = ""
            solar_priority = ""
            load_priority = ""

        grid_desc = DISPATCH_CODES.get(dispatch_code, "Unknown")

        # Calculate remaining time
        end_for_calc = end_time if end_time != "24:00" else "23:59"
        try:
            current_time = now.strftime("%H:%M")
            ct = datetime.strptime(current_time, "%H:%M")
            et = datetime.strptime(end_for_calc, "%H:%M")
            if et <= ct:
                et += timedelta(days=1)
            diff = et - ct
            hours = diff.seconds // 3600
            minutes = (diff.seconds % 3600) // 60
            time_left = f"{hours:02d}:{minutes:02d}"
        except (ValueError, TypeError):
            time_left = "00:00"

        if prefix == "active":
            return {
                "activeTOUid": block_id,
                "activeTOUname": name,
                "activeTOUdispatchId": dispatch_id,
                "activeWaveType": wave_type,
                "activeTOUdispatchCode": dispatch_code,
                "activeTOUtitle": title,
                "activeTOUdispatchDesc": grid_desc,
                "activeTOUrecommendScene": recommend_scene,
                "activeTOUcontent": content,
                "activeTOUsolarPriority": solar_priority,
                "activeTOUloadPriority": load_priority,
                "activeStartTime": start_time,
                "activeEndTime": end_time,
                "activeRemainingTime": time_left,
            }
        else:
            return {
                "nextTOUid": block_id,
                "nextTOUname": name,
                "nextTOUdispatchId": dispatch_id,
                "nextWaveType": wave_type,
                "nextTOUdispatchCode": dispatch_code,
                "nextTOUtitle": title,
                "nextTOUdispatchDesc": grid_desc,
                "nextTOUrecommendScene": recommend_scene,
                "nextTOUcontent": content,
                "nextTOUsolarPriority": solar_priority,
                "nextTOUloadPriority": load_priority,
                "nextStartTime": start_time,
                "nextEndTime": end_time,
                "nextRemainingTime": time_left,
            }

    # ── Rate field mapping (user-friendly key → API field) ────────
    RATE_FIELD_MAP = {
        "peak": "eleticRatePeak",
        "sharp": "eleticRateSharp",
        "shoulder": "eleticRateShoulder",
        "off_peak": "eleticRateValley",
        "super_off_peak": "eleticRateSuperOffPeak",
        "sell_peak": "eleticSellPeak",
        "sell_sharp": "eleticSellSharp",
        "sell_shoulder": "eleticSellShoulder",
        "sell_off_peak": "eleticSellValley",
        "sell_super_off_peak": "eleticSellSuperOffPeak",
        "grid_fee": "eleticRateGridFee",
    }

    # All rate API fields (for read-merge)
    _ALL_RATE_FIELDS = list(RATE_FIELD_MAP.values())

    # Day type constants
    DAY_TYPE_WEEKDAY = 1
    DAY_TYPE_WEEKEND = 2
    DAY_TYPE_EVERYDAY = 3

    async def set_tou_schedule(
        self,
        touMode: str,
        touSchedule: list = None,
        operation: int = 0,
        default_mode: str = "SELF",
        default_tariff: str = "OFF_PEAK",
        *,
        rates: dict = None,
        seasons: list = None,
        day_type: int = 3,
        day_schedules: dict = None,
    ):
        """Set the Custom or Predefined Time-of-Use Work Mode Schedule.

        Once inputs are validated, the schedule is submitted to the aGate.
        It will schedule execution and set touSendStatus=1 to indicate a
        new schedule is pending. Generally applied immediately, but the
        aGate may take a few minutes. touSendStatus=1 may persist as a
        false positive even after the schedule is applied.

        CAUTION: The Cloud API's saveTouDispatch endpoint is destructive.
        It validates, saves, AND switches the system to TOU mode. There
        is no 'update data only' path.

        Parameters
        ----------
        touMode : str
            Can be one of the following strings:
                'CUSTOM'       — User-defined TOU schedule provided as JSON list via touSchedule
                'PREDEFINED'   — Pre-defined schedule name from built-in fixtures
                'HOME'         — Prioritise home loads, then charge battery, then export
                'STANDBY'      — Battery on standby, solar powers home, export excess
                'SELF'         — Prioritise self-consumption: solar → battery → grid
                'SOLAR'        — Charge battery from solar only, grid supports home
                'GRID_EXPORT'  — Force battery to export to grid (if configured)
                'GRID_CHARGE'  — Force battery to import from grid (if configured)

        touSchedule : list or dict, optional
            Schedule entries — required for CUSTOM and PREDEFINED modes.

            For CUSTOM mode: a list of dicts (or single dict) with keys:
                startHourTime, endHourTime, waveType, name, dispatchId
            Schedule must cover exactly 24 hours (1440 min). Gaps are auto-filled
            using default_mode/default_tariff values.

            For PREDEFINED mode: a string name of a built-in fixture, e.g.:
                'charge_from_grid', 'export_to_grid_always',
                'export_to_grid_peakonly', 'standby_schedule',
                'power_home_only', 'charge_from_solar', 'self_schedule'

        operation : int
            Type of operation (currently only 0 is implemented):
                0 = Overwrite all (replace entire schedule)
                1 = Insert entry (not yet implemented)
                2 = Delete entry by id (not yet implemented)
                3 = Update tariff pricing rates (not yet implemented)

        default_mode : str
            TOU dispatch mode for gap-filling when schedule < 24 hours
            (default: 'SELF')
        default_tariff : str
            Default tariff type for gap-filling (default: 'OFF_PEAK')

        rates : dict, optional (keyword-only)
            Pricing rates to set. Keys use friendly names mapped to API fields:
                peak, sharp, shoulder, off_peak, super_off_peak (buy rates)
                sell_peak, sell_sharp, sell_shoulder, sell_off_peak,
                sell_super_off_peak (sell rates)
                grid_fee (grid fee)
            Values are floats (e.g. 0.32 = $0.32/kWh).
            If None, existing rates from the current schedule are preserved.

        seasons : list, optional (keyword-only)
            List of season dicts, each with:
                {"name": "Summer", "months": "10,11,12,1,2,3"}
            If None, defaults to single season covering all 12 months.

        day_type : int, optional (keyword-only)
            Day type for the schedule (default: 3 = everyDay):
                1 = Weekdays (Mon-Fri)
                2 = Weekends (Sat-Sun)
                3 = Every day
            Only used when day_schedules is None.

        day_schedules : dict, optional (keyword-only)
            Separate schedules per day type. Keys are 'weekday' and 'weekend',
            values are detailVoList arrays. Example:
                {"weekday": [...blocks...], "weekend": [...blocks...]}
            When provided, day_type is ignored and two dayTypeVoList entries
            are created.

        Returns
        -------
        dict
            API response from saveTouDispatch.

        Raises
        ------
        InvalidTOUScheduleOption
            If touMode or touSchedule is invalid.
        ValidationError
            If schedule doesn't cover exactly 24 hours or API call fails.

        Note
        ----
        When using CUSTOM mode with set_mode(), the flow is:
            1. set_mode('tou_custom', ...) or set_mode(1, ...)
            2. set_tou_schedule('CUSTOM', touSchedule=[...list of entries...])

        The touSchedule list format matches the FranklinWH saveTouDispatch API.
        See const/test_fixtures.py for example schedule formats.
        """
        logger.info(f"set_tou_schedule:  touMode = '{touMode}' for aGate {self.gateway}")
        validate_tou_mode = touMode.upper().replace(' ', '_').replace('-', '_')
        logger.info(f"set_tou_schedule: Validating TOU mode '{validate_tou_mode}' for aGate {self.gateway}")

        if validate_tou_mode in valid_tou_modes:
            logger.info(f"set_mode: Validated requested TOU mode: {touMode}")
        else:
            valid_dispatch = DISPATCH_CODES.get(touMode)
            if valid_dispatch:
                logger.info(f"set_mode: Verifying touMode is a integer and looking up: {touMode}")
                touMode = valid_tou_modes[valid_dispatch]
            else:
                raise InvalidTOUScheduleOption(f"Invalid TOU mode requested: {touMode}")

        logger.info(f"set_tou_schedule: Preparing to set TOU schedule mode '{touMode}' for aGate {self.gateway}")
        res = await self.get_tou_dispatch_detail()
        template = res["result"]["template"]

        saveTOUdispatch_template = None
        null = 'null'

        if template:
            account = null
            res = await self.get_home_gateway_list()
            logger.info(f"set_tou_schedule: Retrieved Home Gateway List for aGate {self.gateway}")
            for agate in res["result"]:
                if agate["id"] == self.gateway:
                    account = res["result"][0]["account"]
                    break

            saveTOUdispatch_template = {
                "id": template["id"],
                "gatewayId": self.gateway,
                "electricCompany": template["electricCompany"],
                "eletricCompanyId": template["eletricCompanyId"],
                "sdcpCompanyFlag": null,
                "name": template["name"],
                "electricityType": 1,
                "workMode": template["workMode"],
                "countryId": template["countryId"],
                "provinceId": template["provinceId"],
                "account": account,
                "accountId": -1,
                "accountType": 0,
                "countryEn": template["countryEn"],
                "countryZh": template["countryZh"],
                "eleCompanyFullName": template["eleCompanyFullName"],
                "tariffName": template["name"],
                "env": null,
                "gridType": null,
                "mookRunCount": null,
                "priority": null,
                "provinceEn": "",
                "provinceZh": "",
                "solarChargeMin": null,
                "sourceType": null,
                "status": null,
                "templateFromType": null,
                "templateId": null,
                "updateTime": null,
                "derSchdule": "Other",
            }
        else:
            saveTOUdispatch_template = {
                "id": null,
                "gatewayId": self.gateway,
                "electricCompany": null,
                "eletricCompanyId": -1,
                "sdcpCompanyFlag": null,
                "name": null,
                "electricityType": 1,
                "workMode": 1,
                "countryId": null,
                "provinceId": null,
                "account": null,
                "accountId": -1,
                "accountType": 0,
                "countryEn": null,
                "countryZh": null,
                "eleCompanyFullName": null,
                "tariffName": null,
                "env": null,
                "gridType": null,
                "mookRunCount": null,
                "priority": null,
                "provinceEn": "",
                "provinceZh": "",
                "solarChargeMin": null,
                "sourceType": null,
                "status": null,
                "templateFromType": null,
                "templateId": null,
                "updateTime": null,
                "derSchdule": "Other",
            }

        def parse_datetime(value, date_format="%Y-%m-%d %H:%M"):
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                try:
                    return datetime.strptime(value, date_format)
                except ValueError:
                    logger.info(f"set_tou_schedule: Warning: Invalid date format '{value}'. Skipping.")
                    return None
            return None

        def count_dicts_in_list(data_list):
            if not isinstance(data_list, list):
                raise TypeError("Input must be a list.")
            return sum(1 for item in data_list if isinstance(item, dict))

        tou_predefined_builtin = {
            "charge_from_grid": charge_from_grid,
            "power_home_only": power_home_only,
            "charge_from_solar": charge_from_solar,
            "export_to_grid_always": export_to_grid_always,
            "export_to_grid_peakonly": export_to_grid_peakonly,
            "export_to_grid_peak2": export_to_grid_peak2,
            "standby_schedule": standby_schedule,
            "self_schedule": self_schedule,
            "custom_schedule": custom_schedule,
            "gap_schedule": gap_schedule,
        }

        logger.info(f"default_mode = {default_mode}, default_tariff = {default_tariff}")
        detailVoList = []
        if default_mode is not None:
            default_dispatchId = DISPATCH_CODES[default_mode]
            default_tariff = WAVE_TYPES.get(default_tariff, "Unknown")
            default_name = WAVE_TYPES.get(default_dispatchId, "Unknwown")
        else:
            default_dispatchId = dispatchCodeType.SELF_CONSUMPTION.value
            default_tariff = WaveType.OFF_PEAK.value
            default_name = WAVE_TYPES.get(default_dispatchId, "Unknwown")

        logger.info(f"default_mode = {default_mode}")
        logger.info(f"default_dispatchId = {default_dispatchId}, default_tariff = {default_tariff},  default_name = {default_name}")
        logger.info(f"set_tou_schedule: Setup default values default_dispatchId={default_dispatchId}, default_tariff={default_tariff}, default_name={default_name}")

        match touMode:
            case "PREDEFINED":
                tou_predefined = touSchedule
                if tou_predefined not in tou_predefined_builtin:
                    logger.error(f"set_tou_schedule: tou_predefined specified is invalid: {tou_predefined}")
                    raise InvalidTOUScheduleOption(f"tou_predefined specified is invalid: {tou_predefined}")
                else:
                    logger.info(f"set_mode: Predfined schedule = {tou_predefined}")
                    detailVoList = tou_predefined_builtin.get(tou_predefined)
                    print(tou_predefined_builtin)

            case "CUSTOM":
                def is_valid_json(data):
                    try:
                        json.dumps(data)
                        json.loads(json.dumps(data))
                        return True
                    except (TypeError, json.JSONDecodeError):
                        return False

                def validate_json_object(json_data):
                    try:
                        validate(instance=json_data, schema=tou_json_schema)
                        return True, None
                    except ValidationError as e:
                        msg = f"JSON Validation failed: {e.message}"
                        if e.path:
                            msg += f" at {list(e.path)}"
                        logger.error(f"set_tou_schedule: {msg}")
                        return False, msg

                msg = f"type = {type(touSchedule)}"
                logger.info(f"set_mode: CUSTOM/JSON schedule = {touSchedule} - {msg}")
                if isinstance(touSchedule, dict):
                    detailVoList = [touSchedule]
                else:
                    detailVoList = touSchedule
                    if is_valid_json(touSchedule):
                        logger.info("JSON basic structure validated")
                        is_valid, validation_msg = validate_json_object(detailVoList)
                        if is_valid:
                            logger.info("set_tou_schedule: Success: The JSON data is valid.")
                        else:
                            msg = f"set_tou_schedule: {validation_msg}"
                            logger.error(msg)
                            raise InvalidTOUScheduleOption(msg)
                    else:
                        logger.info(f"set_mode: invalid JSON - exiting with error")
                        logger.info(f"set_mode: JSON ={touSchedule}")
                        raise ValueError("Error: failed to parse JSON string")

            case _:
                detailVoList = touSchedule
                logger.info("set_tou_schedule: fall thew default match case detailVoList copied from touSchedule")

        logger.info(f"set_tou_schedule: Generated detailVoList = {detailVoList}")
        dict_count = False
        SINGLE_ENTRY = False
        if isinstance(detailVoList, dict):
            try:
                dict_count = count_dicts_in_list(detailVoList)
            except TypeError as e:
                logger.info(f"Error: {e}")
        else:
            dict_count = True
            SINGLE_ENTRY = True

        logger.info(f"set_tou_schedule: touMode = {touMode} detailVoList has {dict_count} dict entries = {detailVoList}")
        elapsed_minutes = 0
        add_one_minute = False
        entries = []
        seq = 0

        for key, value in enumerate(detailVoList):
            startTime = value["startHourTime"]
            endTime = value["endHourTime"]
            waveType = value["waveType"]
            name = value["name"]
            dispatchId = value["dispatchId"]
            seq = seq + 1
            duration = 0
            if endTime == "24:00":
                endTime = "23:59"
                add_one_minute = True
            EndTime = datetime.strptime(endTime, "%H:%M")
            StartTime = datetime.strptime(startTime, "%H:%M")
            duration = EndTime - StartTime
            elapsed_minutes = elapsed_minutes + int(duration.total_seconds() / 60)
            if endTime == "23:59":
                endTime = "24:00"
            entries.append({"id": seq, "elapsed_minutes": elapsed_minutes, "duration": str(duration), "startHourTime": str(startTime), "endHourTime": str(endTime), "waveType": waveType, "name": name, "dispatchId": dispatchId})

        logger.info("set_tou_schedule: Inserted duration and elapsed minutes - ready for sorting / parsing...")
        if add_one_minute:
            elapsed_minutes = elapsed_minutes + 1

        logger.info(f"set_tou_schedule: Checking scheduled total elapsed time: {elapsed_minutes} minutes")
        sorted_data = sorted(entries, key=lambda x: parse_datetime(x.get("startHourTime"), date_format="%H:%M") or datetime.max)
        logger.info("set_tou_schedule: Checking for missing time periods in sorted_data...")
        logger.info(f"set_tou_schedule: Sorted data = {sorted_data}")

        repaired_entries = []
        repaired_entries = detailVoList.copy()
        amended = False

        for key, value in enumerate(sorted_data):
            startTime = value["startHourTime"]
            endTime = value["endHourTime"]
            waveType = value["waveType"]
            name = value["name"]
            dispatchId = value["dispatchId"]

            if key == 0:
                if startTime != "00:00":
                    logger.info(f"set_tou_schedule: Validate time entries - first entry does not start at 00:00 - found startHourTime = {startTime}")
                    insert_list = {"startHourTime": "00:00", "endHourTime": str(startTime), "waveType": default_tariff, "name": default_name, "dispatchId": default_dispatchId}
                    repaired_entries.insert(0, insert_list)
                    logger.info(f"set_tou_schedule: Inserting missing time period entry at start: {insert_list} ")
                    amended = True
            else:
                if dict_count > 1:
                    priorEndTime = endTime
                else:
                    priorEndTime = sorted_data[key - 1]["endHourTime"]

                if startTime != priorEndTime:
                    if priorEndTime != "24:00":
                        insert_list = {"startHourTime": str(priorEndTime), "endHourTime": str(startTime), "waveType": default_tariff, "name": default_name, "dispatchId": default_dispatchId}
                        repaired_entries.append(insert_list)
                        amended = True

            if key == (len(sorted_data) - 1):
                if endTime != "24:00":
                    logger.info(f"set_tou_schedule: Last entry does not end at 24:00 - found endHourTime = {endTime}")
                    if SINGLE_ENTRY:
                        priorEndTime = endTime
                    if priorEndTime != "24:00":
                        insert_list = {"startHourTime": str(priorEndTime), "endHourTime": "24:00", "waveType": default_tariff, "name": default_name, "dispatchId": default_dispatchId}
                        repaired_entries.append(insert_list)
                        logger.info(f"set_tou_schedule: Inserting missing time period entry at end: {insert_list} ")
                        amended = True

        if amended:
            logger.info(f"set_tou_schedule: Amended sorted_data with missing time periods: {repaired_entries}")
            detailVoList = repaired_entries

        elapsed_minutes = 0
        for key, value in enumerate(detailVoList):
            startTime = value["startHourTime"]
            endTime = value["endHourTime"]
            waveType = value["waveType"]
            name = value["name"]
            dispatchId = value["dispatchId"]
            duration = 0
            if endTime == "24:00":
                endTime = "23:59"
                add_one_minute = True
            EndTime = datetime.strptime(endTime, "%H:%M")
            StartTime = datetime.strptime(startTime, "%H:%M")
            duration = EndTime - StartTime
            elapsed_minutes = elapsed_minutes + int(duration.total_seconds() / 60)

        if add_one_minute:
            elapsed_minutes = elapsed_minutes + 1
        logger.info(f"DetailVoList Entry {key}: startHourTime={startTime}, endHourTime={endTime}, waveType={waveType}, name={name}, dispatchId={dispatchId}, duration={duration}, elapsed_minutes={elapsed_minutes}")
        if elapsed_minutes != 1440:
            msg = f"set_tou_schedule: Error: Total elapsed minutes not equal to 1440 minutes (24 hours)! elapsed_minutes = {elapsed_minutes}"
            logger.info(msg)
            raise ValidationError(msg)

        detailVoList = sorted(detailVoList.copy(), key=lambda x: parse_datetime(x.get("startHourTime"), date_format="%H:%M") or datetime.max)
        logger.info(f"set_tou_schedule: Final detailVoList ready for submission:\n{detailVoList}\n")

        # ── Read existing config from current schedule ──────────────────────
        # Preserves rates, seasons, day types, and schedule blocks when
        # the user hasn't explicitly overridden them (two-context separation).
        existing_rates = {}
        existing_seasons = None    # list of strategyList entries
        existing_day_types = None  # list of dayTypeVoList entries
        existing_blocks = None     # detailVoList from first day type

        try:
            existing = await self.get_tou_dispatch_detail()
            existing_strategies = existing.get("result", {}).get("strategyList", [])
            if existing_strategies:
                # Preserve full season structure
                existing_seasons = existing_strategies

                # Preserve day types and rates from first season
                existing_dt_list = existing_strategies[0].get("dayTypeVoList", [])
                if existing_dt_list:
                    existing_day_types = existing_dt_list
                    # Extract rates from first day type
                    for field in self._ALL_RATE_FIELDS:
                        existing_rates[field] = existing_dt_list[0].get(field, 0)
                    # Extract existing schedule blocks
                    existing_blocks = existing_dt_list[0].get("detailVoList", [])
        except Exception:
            logger.warning("set_tou_schedule: Could not read existing config — using defaults")

        # ── Build rate values: existing → overridden by user rates ──
        rate_values = {field: existing_rates.get(field, 0) for field in self._ALL_RATE_FIELDS}
        if rates:
            for user_key, value in rates.items():
                api_field = self.RATE_FIELD_MAP.get(user_key)
                if api_field:
                    rate_values[api_field] = value
                else:
                    logger.warning(f"set_tou_schedule: Unknown rate key '{user_key}' — ignoring")

        # ── Day type names and codes ───────────────────────────────
        DAY_TYPE_NAMES = {
            1: ("weekDay", 1),
            2: ("weekendDay", 2),
            3: ("everyDay", 3),
        }

        def _build_day_type_entry(dt_code, schedule_blocks):
            """Build a single dayTypeVoList entry with rates and schedule."""
            dt_name, dt_val = DAY_TYPE_NAMES.get(dt_code, ("everyDay", 3))
            entry = {
                "dayName": dt_name,
                "dayType": dt_val,
                "detailVoList": schedule_blocks,
            }
            entry.update(rate_values)
            return entry

        # ── Build dayTypeVoList ────────────────────────────────────
        # Priority: explicit day_schedules > explicit day_type > existing > default
        if day_schedules:
            # Weekday/weekend split schedules (explicit)
            built_day_types = []
            if "weekday" in day_schedules:
                built_day_types.append(
                    _build_day_type_entry(1, day_schedules["weekday"])
                )
            if "weekend" in day_schedules:
                built_day_types.append(
                    _build_day_type_entry(2, day_schedules["weekend"])
                )
            if not built_day_types:
                built_day_types = [_build_day_type_entry(3, detailVoList)]
        elif day_type != 3 or not existing_day_types:
            # Explicit day_type override or no existing config
            built_day_types = [_build_day_type_entry(day_type, detailVoList)]
        else:
            # Preserve existing day type structure, replacing schedule blocks
            built_day_types = []
            for existing_dt in existing_day_types:
                dt_code = existing_dt.get("dayType", 3)
                built_day_types.append(
                    _build_day_type_entry(dt_code, detailVoList)
                )

        # ── Build strategyList (seasons) ───────────────────────────
        # Priority: explicit seasons > existing > default single season
        false = 'false'
        if seasons:
            # Explicit seasons override
            strategyList = []
            for s in seasons:
                strategyList.append({
                    "id": null,
                    "seasonName": s.get("name", f"Season {len(strategyList) + 1}"),
                    "month": s.get("months", "1,2,3,4,5,6,7,8,9,10,11,12"),
                    "templateId": null,
                    "dayTypeVoList": built_day_types,
                })
        elif existing_seasons:
            # Preserve existing season structure, replacing day types
            strategyList = []
            for existing_s in existing_seasons:
                strategyList.append({
                    "id": null,
                    "seasonName": existing_s.get("seasonName", "Season 1"),
                    "month": existing_s.get("month", "1,2,3,4,5,6,7,8,9,10,11,12"),
                    "templateId": null,
                    "dayTypeVoList": built_day_types,
                })
        else:
            # Default: single season covering all months
            strategyList = [{
                "id": null,
                "seasonName": "Season 1",
                "month": "1,2,3,4,5,6,7,8,9,10,11,12",
                "templateId": null,
                "dayTypeVoList": built_day_types,
            }]

        payload = {"template": saveTOUdispatch_template, "strategyList": strategyList, "nemType": 0, "coverContentFlag": false}
        logger.info("set_tou_schedule: Finalised payload now sending to saveTouDispatch")
        key = "dispatchId"
        dispatchIdList = list(dict.fromkeys(d[key] for d in detailVoList if key in d))

        res = await self.get_pcs_hintinfo(dispatchIdList)
        logger.info(f"set_tou_schedule: JSON: {payload}")
        logger.info("set_tou_schedule: Convert payload to JSON prior to calling saveTouDispatch")

        res = await self.save_tou_dispatch(payload)
        if res["code"] == 200:
            touId = res["result"]["id"]
            logger.info(f"set_tou_schedule: saveTouDispatch successful, touId = {touId}")
        else:
            msg = f"set_tou_schedule: Error: saveTouDispatch failed with response: {res}"
            logger.info(msg)
            raise ValidationError(msg)

        return res
