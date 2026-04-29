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

from franklinwh_cloud.const import (
    dispatchCodeType, DISPATCH_CODES, WaveType, WAVE_TYPES,
    valid_tou_modes, tou_json_schema,
)
from franklinwh_cloud.const.test_fixtures import (
    gap_schedule, export_to_grid_always, export_to_grid_peak2,
    export_to_grid_peakonly, charge_from_grid, standby_schedule,
    power_home_only, charge_from_solar, self_schedule, custom_schedule,
)
from franklinwh_cloud.exceptions import (
    InvalidTOUScheduleOption,
    FranklinWHTimeoutError,
)

logger = logging.getLogger("franklinwh_cloud")


class TouMixin:
    """TOU schedule management — get/set schedules, dispatch, backup.

    Key methods:
        set_tou_schedule() — Set a custom or predefined TOU schedule
        get_tou_info()     — Retrieve current/next TOU schedule items
        save_tou_dispatch() — Submit a TOU dispatch template to the aGate
        backup_tou_schedule() — Write TOU schedule to a backup file
    """

    # ── Backup / Restore ─────────────────────────────────────────────────────

    _BACKUP_DIR = None   # resolved lazily; can be patched in tests

    @classmethod
    def _get_backup_dir(cls):
        """Return (and create) the backup directory path."""
        import os
        from pathlib import Path
        d = cls._BACKUP_DIR or Path(os.path.expanduser("~/.franklinwh/backups"))
        d = Path(d)
        d.mkdir(parents=True, exist_ok=True)
        return d

    async def tou_backup_save(self, strategy_list, cli_args=""):
        """Serialise and save a TOU strategyList backup to disk.

        Writes a JSON file to ~/.franklinwh/backups/ with the full
        strategyList and a SHA-256 checksum for post-restore verification.

        Parameters
        ----------
        strategy_list : list
            The strategyList to back up (from get_tou_dispatch_detail result).
        cli_args : str, optional
            Human-readable description of the command being run (logged in
            the backup metadata for forensic purposes).

        Returns
        -------
        pathlib.Path
            Path to the written backup file.
        """
        import hashlib, json as _json
        from pathlib import Path
        from datetime import datetime, timezone

        payload_str = _json.dumps(strategy_list, sort_keys=True)
        checksum = hashlib.sha256(payload_str.encode()).hexdigest()
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"{self.gateway}_{ts}_{checksum[:8]}.json"
        backup_path = self._get_backup_dir() / filename

        meta = {
            "gateway":       self.gateway,
            "timestamp":     datetime.now(timezone.utc).isoformat(),
            "checksum":      checksum,
            "seasons":       len(strategy_list),
            "cli_args":      cli_args,
            "pid":           __import__("os").getpid(),
        }
        data = {"meta": meta, "strategyList": strategy_list}
        backup_path.write_text(_json.dumps(data, indent=2))
        logger.info(f"tou_backup_save: wrote {backup_path} (seasons={meta['seasons']}, checksum={checksum[:8]})")
        return backup_path

    async def tou_backup_restore(self, backup_path):
        """Restore a TOU strategyList from a backup file.

        Reads the backup, calls set_tou_schedule_multi with the original
        strategyList, and verifies the checksum of what was submitted.

        Parameters
        ----------
        backup_path : str or pathlib.Path
            Path to the backup JSON file.

        Returns
        -------
        dict
            The restored strategyList.

        Raises
        ------
        FileNotFoundError
            If backup_path does not exist.
        ValueError
            If checksum verification fails.
        """
        import hashlib, json as _json
        from pathlib import Path

        backup_path = Path(backup_path)
        if not backup_path.exists():
            raise FileNotFoundError(f"tou_backup_restore: backup not found: {backup_path}")

        data = _json.loads(backup_path.read_text())
        strategy_list = data["strategyList"]
        stored_checksum = data["meta"]["checksum"]

        # Verify checksum of what we're about to restore
        actual_checksum = hashlib.sha256(
            _json.dumps(strategy_list, sort_keys=True).encode()
        ).hexdigest()
        if actual_checksum != stored_checksum:
            raise ValueError(
                f"tou_backup_restore: checksum mismatch — "
                f"stored={stored_checksum[:8]} actual={actual_checksum[:8]}. "
                f"Backup may be corrupted."
            )

        logger.info(f"tou_backup_restore: restoring from {backup_path} (checksum OK)")
        await self.set_tou_schedule_multi(strategy_list)
        logger.info(f"tou_backup_restore: restore complete")
        return strategy_list

    async def tou_backup_list(self, gateway=None):
        """List available TOU backups on disk.

        Parameters
        ----------
        gateway : str, optional
            Filter to a specific gateway ID. Defaults to self.gateway.

        Returns
        -------
        list[dict]
            Sorted list of backup metadata dicts (newest first), each with:
            path, gateway, timestamp, checksum, seasons, age_days, cli_args
        """
        import json as _json
        from datetime import datetime, timezone
        from pathlib import Path

        gw = gateway or getattr(self, "gateway", None)
        backup_dir = self._get_backup_dir()
        results = []

        for f in sorted(backup_dir.glob("*.json"), reverse=True):
            try:
                data = _json.loads(f.read_text())
                meta = data.get("meta", {})
                ts = datetime.fromisoformat(meta.get("timestamp", "1970-01-01T00:00:00+00:00"))
                age_days = (datetime.now(timezone.utc) - ts).days
                entry = {
                    "path":      f,
                    "gateway":   meta.get("gateway", ""),
                    "timestamp": meta.get("timestamp", ""),
                    "checksum":  meta.get("checksum", ""),
                    "seasons":   meta.get("seasons", 0),
                    "cli_args":  meta.get("cli_args", ""),
                    "pid":       meta.get("pid"),
                    "age_days":  age_days,
                }
                if gw is None or entry["gateway"] == gw:
                    results.append(entry)
            except Exception as e:
                logger.warning(f"tou_backup_list: could not parse {f}: {e}")

        return results

    async def tou_backup_delete(self, backup_path):
        """Delete a TOU backup file.

        Parameters
        ----------
        backup_path : str or pathlib.Path
            Path to the backup file to delete.
        """
        from pathlib import Path
        p = Path(backup_path)
        if p.exists():
            p.unlink()
            logger.info(f"tou_backup_delete: deleted {p}")
        else:
            logger.warning(f"tou_backup_delete: file not found (already deleted?): {p}")

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
        data = await self._post(url, {}, params=params)
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
        url = self.url_base + "hes-gateway/terminal/tou/saveTouDispatch"
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
        url = self.url_base + "hes-gateway/terminal/tou/getTouDispatchDetail"
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
        logger.debug(f"get_tou_info: option = {option}")
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

            logger.debug(f"get_tou_info: returning current={current_block is not None}, "
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
        month: int = None,
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
            Explicit full season override. Each entry:
                {"name": "Summer", "months": "10,11,12,1,2,3"}
            When provided, the full strategyList is replaced with exactly
            these seasons. No existing-config read is performed.
            Use this for full schedule creation/restore only.

        month : int, optional (keyword-only)
            Target month (1-12) for the schedule update.
            When ``seasons`` is not provided, the library reads the existing
            strategyList, resolves which season owns this month, and updates
            ONLY that season's blocks — all other seasons are left untouched.
            Defaults to ``datetime.now().month`` (today's month).
            Ignored when ``seasons`` is provided.

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
        validate_tou_mode = str(touMode).upper().replace(' ', '_').replace('-', '_')
        logger.info(f"set_tou_schedule: Validating TOU mode '{validate_tou_mode}' for aGate {self.gateway}")

        if validate_tou_mode in valid_tou_modes:
            logger.info(f"set_mode: Validated requested TOU mode: {touMode}")
        else:
            try:
                numeric_tou = int(touMode)
            except ValueError:
                numeric_tou = None

            matched = False
            if numeric_tou is not None:
                for mode_str in valid_tou_modes:
                    if DISPATCH_CODES.get(mode_str) == numeric_tou:
                        touMode = mode_str
                        matched = True
                        logger.info(f"set_mode: Mapped numeric dispatch ID {numeric_tou} to canonical string mode: {touMode}")
                        break
            
            if not matched:
                raise InvalidTOUScheduleOption(f"Invalid TOU mode requested: {touMode}")

        logger.info(f"set_tou_schedule: Preparing to set TOU schedule mode '{touMode}' for aGate {self.gateway}")
        res = await self.get_tou_dispatch_detail()
        template = res.get("result", {}).get("template", None)

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
            account = null
            try:
                gw_res = await self.get_home_gateway_list()
                for gw in gw_res.get("result", []):
                    if gw.get("id") == self.gateway:
                        account = gw.get("account")
                        break
            except Exception:
                pass

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
                "account": account,
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
                if touSchedule is not None:
                    detailVoList = touSchedule
                # else: leave detailVoList = [] (predefined modes: SELF, HOME, STANDBY, etc.)
                logger.info(f"set_tou_schedule: predefined/simple mode '{touMode}' — detailVoList={detailVoList}")

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

        if detailVoList:
            # ── Schedule processing, gap-repair, 1440-minute validation ─────
            # Only runs for CUSTOM / schedule-bearing modes. Predefined modes
            # (SELF, HOME, STANDBY, etc.) have an empty detailVoList and skip
            # this entire section, going straight to the strategyList build.
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
        else:
            # Predefined mode (SELF, HOME, STANDBY, SOLAR, GRID_CHARGE, GRID_EXPORT)
            # called without a touSchedule. Synthesise a full 24-hour single block
            # so the strategyList is valid. Each mode maps to a distinct dispatchId,
            # so SELF → 6 (self-consumption) and GRID_CHARGE → 8 (charge from grid)
            # produce different and correct schedules.
            mode_key = str(touMode).upper()
            dispatch_id = DISPATCH_CODES.get(mode_key)
            if dispatch_id is None:
                raise InvalidTOUScheduleOption(
                    f"Unknown predefined mode '{touMode}'. "
                    f"Valid: SELF, HOME, STANDBY, SOLAR, GRID_CHARGE, GRID_EXPORT, CUSTOM"
                )
            mode_name = WAVE_TYPES.get(dispatch_id, mode_key)
            detailVoList = [{
                "startHourTime": "00:00",
                "endHourTime":   "24:00",
                "waveType":      WaveType.OFF_PEAK.value,
                "name":          mode_name,
                "dispatchId":    dispatch_id,
            }]
            logger.info(
                f"set_tou_schedule: predefined mode '{touMode}' → "
                f"synthesised full-day block dispatchId={dispatch_id} ({mode_name})"
            )


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
        # Priority:
        #   1. explicit seasons= arg     → full caller-controlled replacement
        #   2. no seasons= arg           → transparent season resolution:
        #        read existing config, find the season that owns today's month
        #        (or the month= arg), replace ONLY that season's blocks,
        #        leave all other seasons untouched.
        #   3. no existing config at all → fresh single all-months season
        false = 'false'
        if seasons:
            # ── Path 1: Explicit caller override ─────────────────────────────
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
            # ── Path 2: Transparent season resolution ─────────────────────────
            # Find the season that owns today's month (or the requested month).
            # Update ONLY that season's blocks — all other seasons are untouched.
            from datetime import datetime as _dt
            target_month = str(month if month is not None else _dt.now().month)

            target_idx = None
            for i, s in enumerate(existing_seasons):
                owned = [m.strip() for m in s.get("month", "").split(",") if m.strip()]
                if target_month in owned:
                    target_idx = i
                    break

            if target_idx is None:
                # Month not found in any season — fall back to first season.
                target_idx = 0
                logger.warning(
                    f"set_tou_schedule: month {target_month} not found in any "
                    f"existing season — updating season[0] as fallback"
                )
            else:
                logger.info(
                    f"set_tou_schedule: month {target_month} → season[{target_idx}] "
                    f"'{existing_seasons[target_idx].get('seasonName', '?')}'"
                )

            strategyList = []
            for i, existing_s in enumerate(existing_seasons):
                if i == target_idx:
                    # Replace this season's blocks with the new schedule.
                    strategyList.append({
                        "id": null,
                        "seasonName": existing_s.get("seasonName", "Season 1"),
                        "month": existing_s.get("month", "1,2,3,4,5,6,7,8,9,10,11,12"),
                        "templateId": null,
                        "dayTypeVoList": built_day_types,
                    })
                else:
                    # Preserve all other seasons exactly as they are.
                    strategyList.append({
                        "id": null,
                        "seasonName": existing_s.get("seasonName", f"Season {i+1}"),
                        "month": existing_s.get("month", ""),
                        "templateId": null,
                        "dayTypeVoList": existing_s.get("dayTypeVoList", built_day_types),
                    })
        else:
            # ── Path 3: No existing config — fresh single all-months season ───
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
        dispatchIdList = list(dict.fromkeys(
            d[key] for d in (detailVoList or []) if key in d
        ))

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

    # ────────────────────────────────────────────────────────────────
    # Tariff management endpoints (discovered from HTTPToolKit HAR)
    # ────────────────────────────────────────────────────────────────

    async def get_utility_companies(self, country_id: int = 3,
                                     province_id: int = 87,
                                     page_num: int = 1,
                                     page_size: int = 20,
                                     latitude: float | None = None,
                                     longitude: float | None = None):
        """Search utility companies by region.

        Parameters
        ----------
        country_id : int
            Country (e.g. 3 = Australia, 1 = USA)
        province_id : int
            Province/state ID (e.g. 87 = NSW)
        page_num, page_size : int
            Pagination
        latitude, longitude : float, optional
            GPS coordinates for proximity matching

        Returns
        -------
        dict
            {dataList: [{id, companyName, ...}], postCodeHave: bool}
        """
        url = self.url_base + "hes-gateway/terminal/tou/getTouCompanyListPageV2"
        params = {
            "countryId": str(country_id),
            "pageNum": str(page_num),
            "pageSize": str(page_size),
            "provinceId": str(province_id),
            "gatewayId": self.gateway,
        }
        if latitude is not None:
            params["latitude"] = str(latitude)
        if longitude is not None:
            params["longitude"] = str(longitude)
        data = await self._post(url, "", params=params)
        return data

    async def get_tariff_list(self, company_id: int,
                               page_num: int = 1, page_size: int = 10,
                               latitude: float | None = None,
                               longitude: float | None = None,
                               search_key: str = ""):
        """List tariff plans for a specific utility company.

        Parameters
        ----------
        company_id : int
            Utility company ID (from get_utility_companies)
        search_key : str
            Optional search filter for tariff names

        Returns
        -------
        dict
            {dataList: [{id, name, electricityType, ...}], postCodeHave: bool}
        """
        url = self.url_base + "hes-gateway/terminal/tou/getTariffListByCompanyId"
        params = {
            "eletricCompanyId": str(company_id),
            "gatewayId": self.gateway,
            "pageNum": str(page_num),
            "pageSize": str(page_size),
            "searchKey": search_key,
            "ptoDate": "",
        }
        if latitude is not None:
            params["latitude"] = str(latitude)
        if longitude is not None:
            params["longitude"] = str(longitude)
        data = await self._get(url, params=params)
        return data

    async def get_tariff_detail(self, tariff_id: int):
        """Get the full tariff template detail by ID.

        Returns the complete tariff structure including seasons,
        day types, rates, dispatch blocks, and advanced settings.

        Parameters
        ----------
        tariff_id : int
            Tariff template ID (from get_tariff_list)

        Returns
        -------
        dict
            {template, extraDTO, strategyList, advancedSettings,
             bbDefaultVo, detailDefaultVo, alertMessage, sendStatus,
             batteryRatedCapacity, tariffSettingFlag, ...}
        """
        url = self.url_base + "hes-gateway/terminal/tou/getTariffDetailByIdV2"
        params = {"tariffId": str(tariff_id)}
        data = await self._get(url, params=params)
        return data

    async def get_tou_detail_by_id(self, tou_id: int, from_type: int = 0):
        """Get a specific TOU configuration by its ID.

        Similar to get_tariff_detail but for applied/saved TOU configs.

        Parameters
        ----------
        tou_id : int
            TOU configuration ID
        from_type : int
            Source type (0 = default)

        Returns
        -------
        dict
            Same shape as get_tariff_detail
        """
        url = self.url_base + "hes-gateway/terminal/tou/getIotTouDetailById"
        params = {
            "gatewayId": self.gateway,
            "id": str(tou_id),
            "fromType": str(from_type),
        }
        data = await self._post(url, "", params=params)
        return data

    async def get_custom_dispatch_list(self, strategy_list: list):
        """Get available dispatch options for a custom schedule.

        Given time blocks with wave types, returns valid dispatch
        codes and strategy configurations.

        Parameters
        ----------
        strategy_list : list
            Time blocks, e.g.:
            [{"startHourTime": "0:00", "endHourTime": "24:00", "waveType": 1}]

        Returns
        -------
        dict
            {dispatchList: [...], strategyList: [...]}
        """
        url = self.url_base + "hes-gateway/terminal/tou/getCustomEnergyDispatchList"
        payload = {
            "gatewayId": self.gateway,
            "strategyList": strategy_list,
        }
        data = await self._post(url, payload)
        return data

    async def get_bonus_info(self):
        """Get TOU bonus/incentive information for this gateway.

        Returns
        -------
        dict
            {bonusEnable, touEleCompanyFullName, extraDTO, bbDefaultVo,
             batteryRatedCapacity, alertMessage, sendStatus,
             switchBonusFlag, pcsVo, apowerCount}
        """
        url = self.url_base + "hes-gateway/terminal/tou/getBonusInfo"
        params = {"gatewayId": self.gateway}
        data = await self._get(url, params=params)
        return data

    async def get_vpp_tip(self):
        """Get VPP (Virtual Power Plant) tips for TOU schedule updates.

        Returns
        -------
        dict
            VPP participation tips and recommendations
        """
        url = self.url_base + "hes-gateway/terminal/tou/getVppTipForUpdateTou"
        params = {"gatewayId": self.gateway}
        data = await self._get(url, params=params)
        return data

    async def get_recommend_dispatch_list(self, strategy_list: list):
        """Get AI-recommended dispatch options for a schedule.

        Parameters
        ----------
        strategy_list : list
            Season/day type structure with rates and blocks

        Returns
        -------
        dict
            {strategyList: [...]} with recommended dispatch codes
        """
        url = self.url_base + "hes-gateway/terminal/tou/getRecommendEnergyDispatchList"
        payload = {
            "gatewayId": self.gateway,
            "strategyList": strategy_list,
        }
        data = await self._post(url, payload)
        return data

    async def calculate_expected_earnings(self, template: dict):
        """Calculate expected savings/earnings for a tariff template.

        Parameters
        ----------
        template : dict
            Full template payload (same shape as saveTouDispatch body)

        Returns
        -------
        dict
            {historyRealSavings, estimatedSavings, estimatedSavings30,
             estimatedSavings365, ...}
        """
        url = self.url_base + "hes-gateway/terminal/tou/calculate/expected/earnings"
        data = await self._post(url, template)
        return data

    async def apply_tariff_template(self, template_id: int, name: str,
                                     work_mode: int = 1,
                                     electricity_type: int = 8,
                                     strategy_detail_custom: list | None = None):
        """Apply a pre-built utility tariff template with optional overrides.

        This is a WRITE operation — it will change the active TOU schedule.

        Parameters
        ----------
        template_id : int
            Tariff template ID (from get_tariff_detail)
        name : str
            Schedule name (e.g. "Grid Charge")
        work_mode : int
            Work mode (1 = TOU)
        electricity_type : int
            Electricity type (8 = grid charge pattern)
        strategy_detail_custom : list, optional
            Custom overrides per strategy, e.g.:
            [{"startHourTime": "00:00", "endHourTime": "05:00", "gridMax": 1000.0}]

        Returns
        -------
        dict
            {id: touId} on success
        """
        url = self.url_base + "hes-gateway/terminal/tou/saveTouDispatchUseTemplate"
        payload = {
            "gatewayId": self.gateway,
            "templateId": template_id,
            "name": name,
            "workMode": work_mode,
            "electricityType": electricity_type,
        }
        if strategy_detail_custom is not None:
            payload["strategyList"] = strategy_detail_custom
        data = await self._post(url, payload)
        return data

    # ────────────────────────────────────────────────────────────────
    # Multi-season scheduling (FEAT-TOU-MULTISEASON)
    # ────────────────────────────────────────────────────────────────

    @staticmethod
    def _validate_strategy_months(strategy_list: list) -> None:
        """Validate that all 12 months are covered exactly once across seasons.

        Parameters
        ----------
        strategy_list : list
            List of season dicts, each with a 'month' key (CSV string like '1,2,3').

        Raises
        ------
        InvalidTOUScheduleOption
            If months are missing, duplicated, or out of range.
        """
        seen: set[int] = set()
        for i, season in enumerate(strategy_list):
            month_str = season.get("month", "")
            if not month_str:
                raise InvalidTOUScheduleOption(
                    f"Season {i+1} ('{season.get('seasonName', '?')}') has no 'month' key."
                )
            months = [m.strip() for m in str(month_str).split(",")]
            for m in months:
                if not m.isdigit() or not 1 <= int(m) <= 12:
                    raise InvalidTOUScheduleOption(
                        f"Season '{season.get('seasonName', '?')}' has invalid month: '{m}'"
                    )
                m_int = int(m)
                if m_int in seen:
                    raise InvalidTOUScheduleOption(
                        f"Month {m_int} appears in more than one season."
                    )
                seen.add(m_int)
        missing = set(range(1, 13)) - seen
        if missing:
            raise InvalidTOUScheduleOption(
                f"Not all 12 months are covered. Missing: {sorted(missing)}"
            )

    async def set_tou_schedule_multi(
        self,
        strategy_list: list,
        *,
        nem_type: int = 0,
        cover_content: bool = False,
    ) -> dict:
        """Set a full multi-season, multi-day-type TOU schedule.

        .. deprecated::
            For targeted single-season dispatch updates, prefer
            ``set_tou_schedule(touMode, touSchedule=[...], month=N)`` which
            transparently resolves the correct season by date and preserves
            all other seasons. ``set_tou_schedule_multi`` remains the correct
            path for full schedule creation, template restore, or when you need
            independent per-season weekday/weekend splits with distinct rates.

        Unlike set_tou_schedule(), which applies a single detailVoList to all
        seasons and day types, this method accepts a fully-specified strategyList
        where each season and each day type inside it has its own independent
        schedule blocks and pricing rates.

        This maps directly to the saveTouDispatch API payload — designed from
        the captured HAR fixture in tests/fixtures/tou_save_multi_season.json.

        Parameters
        ----------
        strategy_list : list
            List of season strategy dicts. Each entry must contain:
                seasonName : str   — e.g. 'Summer'
                month      : str   — comma-separated months e.g. '10,11,12,1,2,3'
                dayTypeVoList : list — list of day type dicts, each with:
                    dayName     : str   — 'weekday' / 'weekend' / 'everyday'
                    dayType     : int   — 1=weekday, 2=weekend, 3=everyday
                    detailVoList: list  — time blocks (startHourTime, endHourTime,
                                         waveType, name, dispatchId)
                    [optional rate fields]: eleticRatePeak, eleticRateShoulder,
                    eleticRateValley, eleticSellPeak, eleticSellShoulder, ...

        nem_type : int, optional
            NEM type (0=NEM 2.0, 1=NEM 3.0). Default 0. AU systems ignore this.

        cover_content : bool, optional
            Whether to overwrite the tariff template content. Default False.

        Returns
        -------
        dict
            API response from saveTouDispatch (includes touId on success).

        Raises
        ------
        InvalidTOUScheduleOption
            If months are missing, duplicated, or out of range across seasons.
        ValidationError
            If the API call fails.

        Example
        -------
        Use tests/fixtures/tou_save_multi_season.json as a template:
        ::

            with open("tou_save_multi_season.json") as f:
                fixture = json.load(f)
            # Adjust strategy_list entries for your own tariff, then:
            await client.set_tou_schedule_multi(fixture["strategyList"])

        See also: docs/TOU_SCHEDULE_GUIDE.md, docs/API_COOKBOOK.md
        """
        logger.info(
            f"set_tou_schedule_multi: {len(strategy_list)} seasons for aGate {self.gateway}"
        )

        # Validate months cover all 12
        self._validate_strategy_months(strategy_list)

        # Read existing template for metadata
        null = None
        res = await self.get_tou_dispatch_detail()
        template = res.get("result", {}).get("template", {})

        # Build account info
        account = null
        try:
            gw_res = await self.get_home_gateway_list()
            for gw in gw_res.get("result", []):
                account = gw.get("account", null)
                break
        except Exception:
            logger.warning("set_tou_schedule_multi: Could not fetch account from gateway list")

        if template:
            save_template = {
                "id": template.get("id"),
                "gatewayId": self.gateway,
                "electricCompany": template.get("electricCompany") or "Unknown",
                "eletricCompanyId": template.get("eletricCompanyId", -1),
                "sdcpCompanyFlag": null,
                "name": template.get("name") or "Custom",
                "electricityType": template.get("electricityType", 1),
                "workMode": template.get("workMode", 1),
                "countryId": template.get("countryId"),
                "provinceId": template.get("provinceId"),
                "account": account,
                "accountId": -1,
                "accountType": 0,
                "countryEn": template.get("countryEn") or "Australia",
                "countryZh": template.get("countryZh") or "澳大利亚",
                "eleCompanyFullName": template.get("eleCompanyFullName") or "Unknown",
                "tariffName": template.get("name") or "Custom",
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
            # No existing template — build minimal stub
            save_template = {
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
                "account": account,
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

        # Normalise strategy_list — strip persisted IDs so the API treats as new
        normalised = []
        for s in strategy_list:
            day_types = []
            for dt in s.get("dayTypeVoList", []):
                day_types.append({
                    "dayName": dt.get("dayName", "weekday"),
                    "dayType": dt.get("dayType", 3),
                    "eleticRatePeak": dt.get("eleticRatePeak"),
                    "eleticRateSharp": dt.get("eleticRateSharp"),
                    "eleticRateShoulder": dt.get("eleticRateShoulder"),
                    "eleticRateValley": dt.get("eleticRateValley"),
                    "eleticRateSuperOffPeak": dt.get("eleticRateSuperOffPeak"),
                    "eleticSellPeak": dt.get("eleticSellPeak"),
                    "eleticSellSharp": dt.get("eleticSellSharp"),
                    "eleticSellShoulder": dt.get("eleticSellShoulder"),
                    "eleticSellValley": dt.get("eleticSellValley"),
                    "eleticSellSuperOffPeak": dt.get("eleticSellSuperOffPeak"),
                    "detailVoList": [
                        {
                            "startHourTime": blk.get("startHourTime"),
                            "endHourTime": blk.get("endHourTime"),
                            "waveType": blk.get("waveType"),
                            "name": blk.get("name", ""),
                            "dispatchId": blk.get("dispatchId"),
                        }
                        for blk in dt.get("detailVoList", [])
                    ],
                })
            normalised.append({
                "id": null,
                "seasonName": s.get("seasonName", f"Season {len(normalised) + 1}"),
                "month": s.get("month", ""),
                "templateId": null,
                "dayTypeVoList": day_types,
            })

        payload = {
            "template": save_template,
            "strategyList": normalised,
            "nemType": nem_type,
            "coverContentFlag": cover_content,
        }

        logger.info(
            f"set_tou_schedule_multi: submitting {len(normalised)} seasons to saveTouDispatch"
        )
        res = await self.save_tou_dispatch(payload)
        if res.get("code") == 200:
            tou_id = res.get("result", {}).get("id")
            logger.info(f"set_tou_schedule_multi: success — touId={tou_id}")
        else:
            msg = f"set_tou_schedule_multi: saveTouDispatch failed: {res}"
            logger.error(msg)
            raise ValueError(msg)
        return res

    # ────────────────────────────────────────────────────────────────
    # Real-time TOU price query (FEAT-TOU-CURRENT-PRICE)
    # ────────────────────────────────────────────────────────────────

    async def get_current_tou_price(self, *, now: datetime | None = None, option: int = 0) -> dict:
        """Return the current TOU pricing tier and block details.

        Fetches the active TOU dispatch schedule, determines which day type
        applies (weekday vs weekend), finds the active time block for the
        current time, and returns pricing rates + time remaining in the block.

        Parameters
        ----------
        now : datetime, optional
            Override the current time (useful for testing / dry-run). If None,
            uses datetime.now() (local time, matching aGate system assumption).
        option : int, optional
            0 = Return full comprehensive pricing metadata dictionary.
            1 = Return only the active buy/sell exchange rates for the current tier.

        Returns
        -------
        dict
            {
                "season_name"      : str,        # e.g. 'Summer'
                "day_type"         : int,         # 1=weekday, 2=weekend, 3=everyday
                "day_type_name"    : str,         # 'Weekday' / 'Weekend'
                "block_name"       : str,         # e.g. 'On-peak'
                "wave_type"        : int,         # 0=off-peak, 1=mid, 2=on-peak
                "wave_type_name"   : str,         # 'Off-Peak' / 'Mid-Peak' / 'On-Peak'
                "dispatch_id"      : int,         # dispatch strategy code
                "block_start"      : str,         # 'HH:MM'
                "block_end"        : str,         # 'HH:MM'
                "minutes_remaining": int,         # minutes until block ends
                "buy_rates"        : dict,        # peak/shoulder/valley/off_peak rates
                "sell_rates"       : dict,        # sell_peak/sell_shoulder/... rates
            }
            Returns empty dict if no schedule is configured.

        Raises
        ------
        FranklinWHTimeoutError
            If the API call times out.
        """
        WAVE_TYPE_NAMES = {0: "Off-Peak", 1: "Mid-Peak", 2: "On-Peak", 3: "Super-Peak", 4: "Super-Off-Peak"}
        DAY_TYPE_NAMES  = {1: "Weekday", 2: "Weekend", 3: "Everyday"}

        if now is None:
            now = datetime.now()

        res = await self.get_tou_dispatch_detail()
        result = res.get("result", {})
        strategy_list = result.get("strategyList", [])
        if not strategy_list:
            logger.info("get_current_tou_price: no strategyList in response")
            return {}

        # Determine active season by current month
        current_month = now.month
        active_season = None
        for season in strategy_list:
            months = [int(m.strip()) for m in str(season.get("month", "")).split(",") if m.strip().isdigit()]
            if current_month in months:
                active_season = season
                break

        if active_season is None:
            logger.warning(f"get_current_tou_price: month {current_month} not in any season")
            return {}

        # Determine day type: 1=weekday, 2=weekend
        is_weekend = now.weekday() >= 5  # Saturday=5, Sunday=6
        preferred_dt = 2 if is_weekend else 1

        # Find best matching dayTypeVoList entry
        day_types = active_season.get("dayTypeVoList", [])
        active_dt = None
        for dt in day_types:
            if dt.get("dayType") == preferred_dt:
                active_dt = dt
                break
        if active_dt is None and day_types:
            # Fallback: everyday (3) or first entry
            for dt in day_types:
                if dt.get("dayType") == 3:
                    active_dt = dt
                    break
            if active_dt is None:
                active_dt = day_types[0]

        if active_dt is None:
            return {}

        # Find active time block
        current_hhmm = now.strftime("%H:%M")
        current_minutes = now.hour * 60 + now.minute
        detail_list = active_dt.get("detailVoList", [])
        active_block = None

        for block in detail_list:
            start_str = block.get("startHourTime", "00:00")
            end_str   = block.get("endHourTime", "24:00")
            end_cmp   = "23:59" if end_str == "24:00" else end_str
            start_m   = int(start_str[:2]) * 60 + int(start_str[3:])
            end_m     = int(end_cmp[:2]) * 60 + int(end_cmp[3:])
            if end_str == "24:00":
                end_m += 1  # midnight inclusive
            if start_m <= current_minutes < end_m:
                active_block = block
                break

        if active_block is None:
            logger.warning(f"get_current_tou_price: no block found for {current_hhmm}")
            return {}

        # Calculate minutes remaining in block
        end_str = active_block.get("endHourTime", "24:00")
        if end_str == "24:00":
            end_total = 24 * 60
        else:
            end_total = int(end_str[:2]) * 60 + int(end_str[3:])
        minutes_remaining = end_total - current_minutes

        wave_type = active_block.get("waveType", 0)
        day_type  = active_dt.get("dayType", 3)

        buy_rates = {
            "peak":          active_dt.get("eleticRatePeak"),
            "shoulder":      active_dt.get("eleticRateShoulder"),
            "valley":        active_dt.get("eleticRateValley"),
            "sharp":         active_dt.get("eleticRateSharp"),
            "super_off_peak":active_dt.get("eleticRateSuperOffPeak"),
        }
        sell_rates = {
            "peak":          active_dt.get("eleticSellPeak"),
            "shoulder":      active_dt.get("eleticSellShoulder"),
            "valley":        active_dt.get("eleticSellValley"),
            "sharp":         active_dt.get("eleticSellSharp"),
            "super_off_peak":active_dt.get("eleticSellSuperOffPeak"),
        }

        # Map waveType enum to price dictionary index
        wave_map = {0: "valley", 1: "shoulder", 2: "peak", 3: "sharp", 4: "super_off_peak"}
        active_key = wave_map.get(wave_type, "peak")

        current_buy_rate = buy_rates.get(active_key)
        current_sell_rate = sell_rates.get(active_key)

        if option == 1:
            return {
                "buy_rate": current_buy_rate,
                "sell_rate": current_sell_rate
            }

        return {
            "season_name":       active_season.get("seasonName", ""),
            "day_type":          day_type,
            "day_type_name":     DAY_TYPE_NAMES.get(day_type, "Unknown"),
            "block_name":        active_block.get("name", ""),
            "wave_type":         wave_type,
            "wave_type_name":    WAVE_TYPE_NAMES.get(wave_type, "Unknown"),
            "dispatch_id":       active_block.get("dispatchId"),
            "block_start":       active_block.get("startHourTime"),
            "block_end":         active_block.get("endHourTime"),
            "minutes_remaining": max(0, minutes_remaining),
            "current_buy_rate":  current_buy_rate,
            "current_sell_rate": current_sell_rate,
            "buy_rates":         buy_rates,
            "sell_rates":        sell_rates,
        }

    # ── TOU Health Check ──────────────────────────────────────────────────────

    # dispatchId → expected gateway action for health cross-reference
    _DISPATCH_TO_ACTION = {
        8: "GRID_CHARGE",    # FORCE_CHARGE / GRID_IMPORT
        7: "GRID_EXPORT",    # FORCE_DISCHARGE / GRID_DISCHARGE
        6: "SELF_CONSUME",   # SELF_CONSUMPTION
        3: "SELF_CONSUME",   # SOLAR_CHARGE — battery charges from solar, not forced grid action
        2: "STANDBY",        # explicit standby block
        1: "SELF_CONSUME",   # HOME_LOADS — self-consume mode
        0: "UNKNOWN",        # custom/predefined, no expected run_status
    }

    # run_status int → human label (mirrors franklinwh_cloud/const/modes.py RUN_STATUS)
    _RUN_STATUS_LABELS = {
        0: "Standby",
        1: "Charging",
        2: "Discharging",
        3: "Unknown (3)",
        4: "Unknown (4)",
        5: "Off-Grid Standby",
        6: "Off-Grid Charging",
        7: "Off-Grid Discharging",
        8: "Debug Mode",
        9: "VPP Mode",
    }

    async def get_tou_health(
        self,
        *,
        live_stats: dict = None,
        strict: bool = False,
    ) -> dict:
        """TOU Execution Health Check.

        Cross-references three data sources to determine whether the gateway
        is executing the current TOU schedule block as expected:

          1. get_gateway_tou_list()  — active mode, cloud sync status, stopMode
          2. get_tou_info(1)         — active schedule block + expected dispatch action
          3. get_stats()             — live run_status + grid power (skipped if live_stats passed)

        Parameters
        ----------
        live_stats : dict, optional
            Pre-fetched normalised stats dict (FHAI last_data).
            Must contain 'run_status' (int) and optionally 'grid_kw' (float).
            If provided, avoids an extra get_stats() API call.
        strict : bool, optional
            If True, run_status=Standby during a GRID_CHARGE or GRID_EXPORT block
            is always FAULT. If False (default), it is DEGRADED — acknowledging that
            SOC guards (maxChargeSoc / minDischargeSoc) can legitimately suppress
            forced dispatch.

        Returns
        -------
        dict
            ok                 : bool
            health_status      : 'HEALTHY' | 'DEGRADED' | 'FAULT' | 'UNKNOWN'
            active_mode        : 'Time-of-Use' | 'Self-Consumption' | 'Emergency Backup'
            is_tou_mode        : bool
            sync_status        : 'SYNC_OK' | 'SYNC_PENDING' | 'SYNC_ALERT' | 'UNKNOWN'
            sync_message       : str  (touAlertMessage or '')
            active_block       : dict (from get_tou_info active prefix keys)
            expected_action    : str
            actual_run_status  : int
            actual_run_label   : str
            grid_kw            : float
            fault_reasons      : list[str]
            stop_mode          : int
            grid_charge_en     : int
            tariff_setting_flag: bool
        """
        import asyncio

        fault_reasons = []
        health_status = "UNKNOWN"

        # ── Step 1: mode list (getGatewayTouListV2) ──────────────────────────
        try:
            mode_resp = await self.get_gateway_tou_list()
            result = mode_resp.get("result", {})
        except Exception as exc:
            return {
                "ok": False,
                "health_status": "UNKNOWN",
                "error": f"get_gateway_tou_list failed: {exc}",
                "fault_reasons": [f"Could not fetch mode list: {exc}"],
            }

        current_id = result.get("currendId")
        mode_list  = result.get("list", [])
        stop_mode  = result.get("stopMode", 0) or 0
        grid_charge_en = result.get("gridChargeEn", 0) or 0
        tariff_setting_flag = bool(result.get("tariffSettingFlag", True))

        # Resolve active workMode and label from currendId
        _WORK_MODE_LABELS = {1: "Time-of-Use", 2: "Self-Consumption", 3: "Emergency Backup"}
        active_work_mode = None
        for m in mode_list:
            if m.get("id") == current_id:
                active_work_mode = m.get("workMode")
                break
        active_mode = _WORK_MODE_LABELS.get(active_work_mode, f"Mode {active_work_mode}")
        is_tou_mode = (active_work_mode == 1)

        # Derive sync_status from touSendStatus / touAlertMessage.
        #
        # All observed values confirmed from HTTP Toolkit HAR corpus (1,253 samples):
        #
        #   null  (1141×) → idle, no pending sync               → SYNC_OK
        #   2      (25×)  → "Package settings are taking effect" → SYNC_PENDING
        #                   Schedule sent, gateway currently applying it.
        #                   Cleared to null once gateway ACK received.
        #   3      (87×)  → "Package settings synchronization of failed,
        #                    please check after setting again"   → SYNC_ALERT
        #                   Cloud did not receive gateway ACK.
        #                   FALSE POSITIVE RISK: gateway may have applied the
        #                   schedule to its local DB without the response
        #                   reaching the cloud platform (e.g. brief disconnect).
        #                   Mobile app shows a modal dialog with the alert message;
        #                   user can tap "Apply Again" to retry.
        tou_send_status   = result.get("touSendStatus")
        tou_alert_message = result.get("touAlertMessage") or ""
        if tou_send_status is None:
            sync_status = "SYNC_OK"
        elif tou_send_status in (3, "3"):
            # Confirmed sync failure sentinel — mobile app surfaces touAlertMessage as modal
            sync_status = "SYNC_ALERT"
        else:
            # Any other non-null value: schedule sent, awaiting gateway ACK
            sync_status = "SYNC_PENDING"

        # ── Step 2: active schedule block ────────────────────────────────────
        active_block = {}
        expected_action = "UNKNOWN"
        try:
            tou_info = await self.get_tou_info(1)
            if tou_info:
                active_block = {k: v for k, v in tou_info.items() if k.startswith("active")}
                dispatch_id = tou_info.get("activeTOUdispatchId", 0)
                expected_action = self._DISPATCH_TO_ACTION.get(dispatch_id, "UNKNOWN")
            else:
                # No schedule block found for today — not a fault
                health_status = "UNKNOWN"
        except Exception as exc:
            fault_reasons.append(f"Could not fetch TOU schedule block: {exc}")
            health_status = "UNKNOWN"

        # ── Step 3: live run_status ───────────────────────────────────────────
        actual_run_status = None
        grid_kw = 0.0
        if live_stats and "run_status" in live_stats:
            actual_run_status = int(live_stats.get("run_status", 0) or 0)
            grid_kw = float(live_stats.get("grid_kw") or live_stats.get("grid_use") or 0.0)
        else:
            try:
                stats = await self.get_stats()
                # get_stats() returns a Stats dataclass or dict
                if hasattr(stats, "run_status"):
                    actual_run_status = int(stats.run_status or 0)
                elif isinstance(stats, dict):
                    actual_run_status = int(stats.get("run_status", 0) or 0)
                    grid_kw = float(stats.get("grid_kw") or stats.get("grid_use") or 0.0)
            except Exception as exc:
                fault_reasons.append(f"Could not fetch live run_status: {exc}")

        actual_run_label = self._RUN_STATUS_LABELS.get(actual_run_status, f"Unknown ({actual_run_status})")

        # ── Step 4: synthesise health verdict ────────────────────────────────
        if not is_tou_mode:
            # Gateway is not in TOU mode — health check is not applicable
            health_status = "UNKNOWN"

        elif stop_mode != 0:
            # Manually stopped by user or firmware override
            health_status = "DEGRADED"
            fault_reasons.append(
                f"Gateway is in stopMode={stop_mode} — TOU schedule execution paused."
            )

        elif expected_action == "UNKNOWN" or actual_run_status is None:
            health_status = "UNKNOWN"

        elif expected_action == "GRID_CHARGE":
            if actual_run_status == 1 and grid_kw > 0:
                health_status = "HEALTHY"
            elif actual_run_status == 1 and grid_kw <= 0:
                # Charging but from solar, not grid — schedule says grid charge
                health_status = "DEGRADED"
                fault_reasons.append(
                    f"Schedule requires GRID_CHARGE but gateway is charging from solar "
                    f"(grid_kw={grid_kw:.2f} kW ≤ 0). gridChargeEn={grid_charge_en}."
                )
            elif actual_run_status == 0:
                health_status = "FAULT" if strict else "DEGRADED"
                fault_reasons.append(
                    f"Schedule block {active_block.get('activeStartTime','?')}–"
                    f"{active_block.get('activeEndTime','?')} requires GRID_CHARGE "
                    f"(dispatchId={dispatch_id}) but run_status is Standby (0). "
                    f"gridChargeEn={grid_charge_en}. SOC guard may be suppressing dispatch."
                )
            else:
                health_status = "FAULT"
                fault_reasons.append(
                    f"Schedule requires GRID_CHARGE but run_status={actual_run_status} "
                    f"({actual_run_label}) with grid_kw={grid_kw:.2f} kW."
                )

        elif expected_action == "GRID_EXPORT":
            if actual_run_status == 2 and grid_kw < 0:
                health_status = "HEALTHY"
            elif actual_run_status == 2 and grid_kw >= 0:
                # Discharging to home, not exporting — partial execution
                health_status = "DEGRADED"
                fault_reasons.append(
                    f"Schedule requires GRID_EXPORT but gateway is discharging to home only "
                    f"(grid_kw={grid_kw:.2f} kW ≥ 0). Grid export may be capped."
                )
            elif actual_run_status == 0:
                health_status = "FAULT" if strict else "DEGRADED"
                fault_reasons.append(
                    f"Schedule block {active_block.get('activeStartTime','?')}–"
                    f"{active_block.get('activeEndTime','?')} requires GRID_EXPORT "
                    f"(dispatchId={dispatch_id}) but run_status is Standby (0). "
                    f"minDischargeSoc guard may be suppressing dispatch."
                )
            else:
                health_status = "FAULT"
                fault_reasons.append(
                    f"Schedule requires GRID_EXPORT but run_status={actual_run_status} "
                    f"({actual_run_label}) with grid_kw={grid_kw:.2f} kW."
                )

        elif expected_action == "SELF_CONSUME":
            # Any of Standby/Charging/Discharging is valid for self-consumption
            if actual_run_status in (0, 1, 2):
                health_status = "HEALTHY"
            elif actual_run_status in (5, 6, 7):
                # Off-grid states during on-grid self-consume — unexpected
                health_status = "DEGRADED"
                fault_reasons.append(
                    f"Schedule is SELF_CONSUME but run_status is {actual_run_label} — "
                    f"gateway appears to be in an off-grid state."
                )
            else:
                health_status = "HEALTHY"  # VPP/Debug/other — not a TOU fault

        elif expected_action == "STANDBY":
            if actual_run_status == 0:
                health_status = "HEALTHY"
            else:
                # Active dispatch during a scheduled standby block — unusual but not necessarily broken
                health_status = "DEGRADED"
                fault_reasons.append(
                    f"Schedule block is STANDBY (dispatchId={dispatch_id}) but gateway "
                    f"run_status is {actual_run_label} ({actual_run_status}). "
                    f"Solar-driven activity may be legitimate."
                )

        else:
            health_status = "HEALTHY"

        # ── touSendStatus != null: independently cap the health verdict ───────
        #
        # When touSendStatus is non-null, the cloud↔gateway schedule sync is
        # either in flight or has failed. We cannot fully trust that the gateway
        # is executing the correct schedule — regardless of what run_status shows.
        #
        # SYNC_ALERT (touSendStatus=3):
        #   The cloud platform confirmed the sync failed. The gateway local DB
        #   may be stale. Cap verdict to DEGRADED even if run_status matched.
        #   False positives exist (gateway may have applied silently), so we do
        #   not escalate to FAULT — but HEALTHY would be misleading.
        #   Surface the touAlertMessage in fault_reasons in all cases.
        #
        # SYNC_PENDING (any other non-null):
        #   Schedule was sent but gateway ACK not yet received. Transition state.
        #   Downgrade HEALTHY → DEGRADED only. FAULT/DEGRADED stay unchanged.
        if sync_status == "SYNC_ALERT":
            if health_status == "HEALTHY":
                health_status = "DEGRADED"
            fault_reasons.insert(0, (
                f"Cloud sync alert (touSendStatus=3): gateway schedule sync failed. "
                f"Message: '{tou_alert_message}'. "
                f"Run 'Reset TOU Mode' to re-apply and re-test. "
                f"Note: false positives occur — gateway may have applied successfully "
                f"without ACK reaching the cloud platform."
            ))
        elif sync_status == "SYNC_PENDING":
            if health_status == "HEALTHY":
                health_status = "DEGRADED"
            fault_reasons.insert(0, (
                f"Schedule sync pending (touSendStatus={tou_send_status}): "
                f"gateway has not yet acknowledged the updated TOU schedule. "
                f"Run status cannot be definitively correlated until sync clears."
            ))

        ok = health_status == "HEALTHY"
        return {
            "ok":                   ok,
            "health_status":        health_status,
            "active_mode":          active_mode,
            "is_tou_mode":          is_tou_mode,
            "sync_status":          sync_status,
            "sync_message":         tou_alert_message,
            "active_block":         active_block,
            "expected_action":      expected_action,
            "actual_run_status":    actual_run_status,
            "actual_run_label":     actual_run_label,
            "grid_kw":              grid_kw,
            "fault_reasons":        fault_reasons,
            "stop_mode":            stop_mode,
            "grid_charge_en":       grid_charge_en,
            "tariff_setting_flag":  tariff_setting_flag,
        }
