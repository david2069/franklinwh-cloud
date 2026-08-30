import asyncio
import logging
import uuid
import time
from typing import Optional

from franklinwh_cloud.const import OPERATING_MODES, TIME_OF_USE
from franklinwh_cloud.force_state import ForceSession, ForceStateSnapshot, VPPDetection, ForceInfo
from franklinwh_cloud.exceptions import ForceVPPLockError, ForceSessionActiveError

logger = logging.getLogger(__name__)

class ForceMixin:
    """Orchestrates force operations by manipulating TOU mode and maintaining a watchdog."""
    
    async def _force_preflight(self, action: str, min_soc: Optional[int] = None) -> VPPDetection:
        """Evaluate VPP locks and SoC constraints before launching a force mode."""
        res = await self.get_device_composite_info()
        tou_res = await self.get_gateway_tou_list()
        prog_res = await self.get_programme_info()
        
        runtime = ((res.get("result") or {}).get("runtimeData") or {})
        run_status = int(runtime.get("run_status", 0) or 0)
        mode = int(runtime.get("mode", 0) or 0)
        firmware_vpp_active = (run_status == 9 or mode == 9)
        
        tou_result = (tou_res.get("result") or {})
        vpp_vo = tou_result.get("todayVppVo") or {}
        vpp_soc_vo = tou_result.get("vppSocVo") or {}
        
        cloud_vpp_dispatching = vpp_vo.get("vppStatus") is not None
        cloud_vpp_scheduled = vpp_vo.get("startTime") is not None
        
        prog_flag = prog_res.get("flag", 0) == 1
        prog_id = prog_res.get("programId") is not None
        
        cloud_vpp_enrolled = any([
            vpp_vo.get("vppFlag") == 1,
            vpp_soc_vo.get("vppType", 0) != 0,
            (vpp_soc_vo.get("vppSoc") or 0) > 0,
            prog_flag,
            prog_id
        ])
        
        vpp_reserve_soc = vpp_soc_vo.get("vppSoc")
        vpp_min_soc = vpp_soc_vo.get("vppMinSoc")
        
        vpp_detection = VPPDetection(
            firmware_vpp_active=firmware_vpp_active,
            cloud_vpp_enrolled=cloud_vpp_enrolled,
            cloud_vpp_dispatching=cloud_vpp_dispatching,
            cloud_vpp_scheduled=cloud_vpp_scheduled,
            vpp_reserve_soc=vpp_reserve_soc,
            vpp_min_soc=vpp_min_soc,
        )
        
        if vpp_detection.is_locked:
            raise ForceVPPLockError(f"Force operation '{action}' blocked by active VPP dispatch or Modbus control (run_status=9).")
            
        if action == "force_discharge" and min_soc is not None and cloud_vpp_enrolled and vpp_reserve_soc is not None:
            if min_soc < vpp_reserve_soc:
                logger.warning(
                    f"Clamping force_discharge min_soc from {min_soc}% to {vpp_reserve_soc}% "
                    f"to satisfy VPP Reserved SoC constraint."
                )
        
        return vpp_detection

    async def _force_activate(self, action: str, session: ForceSession) -> bool:
        """Takes a snapshot, pushes the TOU schedule, and spawns the watchdog."""
        if self._force_state.has_active(self.gateway):
            raise ForceSessionActiveError(f"Gateway {self.gateway} already has an active force session.")

        # 1. Take state snapshot
        composite = await self.get_device_composite_info()
        tou_res = await self.get_gateway_tou_list()
        
        comp_res = (composite.get("result") or {})
        tou_result = (tou_res.get("result") or {})
        
        prior_work_mode = comp_res.get("currentWorkMode", 0)
        prior_soc = 0
        prior_tou_strategy = None
        prior_backup_flag = None
        prior_next_work_mode = None
        prior_duration_minutes = None
        prior_checksum = None
        
        if prior_work_mode == TIME_OF_USE:
            # We don't overwrite if we're already in a synthetic Force TOU mode
            pass
            
        # Get prior SoC
        tou_list = (tou_result.get("list") or [])
        for entry in tou_list:
            if entry.get("workMode") == prior_work_mode:
                prior_soc = entry.get("soc", 0)
                break
                
        snapshot = ForceStateSnapshot(
            prior_work_mode=prior_work_mode,
            prior_soc=prior_soc,
            prior_backup_forever_flag=prior_backup_flag,
            prior_next_work_mode=prior_next_work_mode,
            prior_duration_minutes=prior_duration_minutes,
            prior_tou_strategy_list=prior_tou_strategy,
            prior_tou_checksum=prior_checksum,
            raw_tou_list_result=tou_result,
            raw_composite_result=comp_res,
            captured_at=time.time()
        )
        
        # 2. Save state atomically
        self._force_state.save(self.gateway, session, snapshot)
        self._force_audit.log(self.gateway, "SESSION_STARTED", session.session_id, {"action": action})

        # 3. Build TOU schedule
        dispatch_id = 8 if action == "force_charge" else (7 if action == "force_discharge" else 2)
        schedule = [{
            "startHourTime": "00:00",
            "endHourTime": "24:00",
            "waveType": 0,
            "name": f"FWC_FORCE:{session.session_id}",
            "dispatchId": dispatch_id
        }]

        # 4. Apply schedule
        try:
            await self.set_mode("tou_custom")
            await self.set_tou_schedule(
                touMode="CUSTOM", 
                touSchedule=schedule,
                default_mode="SELF",
                default_tariff="OFF_PEAK"
            )
            # Also update the SOC for TOU mode if min/max SOC is set
            if action == "force_charge" and session.max_soc is not None:
                await self.update_soc(requestedSOC=session.max_soc, workMode=1, electricityType=1)
            elif action == "force_discharge" and session.min_soc is not None:
                await self.update_soc(requestedSOC=session.min_soc, workMode=1, electricityType=1)
                
        except Exception as e:
            self._force_state.clear(self.gateway)
            self._force_audit.log(self.gateway, "SESSION_FAILED", session.session_id, {"error": str(e)})
            raise e
            
        # 5. Spawn watchdog
        asyncio.create_task(self._force_watchdog(session.session_id))
        return True
        
    async def _force_watchdog(self, session_id: str):
        """Background task to monitor session duration, VPP pre-emption, and SoC limits."""
        logger.info(f"Watchdog started for session {session_id}")
        poll_interval = 60
        
        while True:
            await asyncio.sleep(poll_interval)
            
            # Load fresh state
            state_data = self._force_state.load(self.gateway)
            if not state_data:
                logger.info(f"Watchdog exiting: session {session_id} state file gone.")
                break
                
            session, snapshot = state_data
            if session.session_id != session_id:
                logger.info(f"Watchdog exiting: session ID mismatch.")
                break
                
            # Check Canary for firmware auto-release
            tou_res = await self.get_gateway_tou_list()
            tou_result = (tou_res.get("result") or {})
            for entry in (tou_result.get("list") or []):
                if entry.get("socExceedTimerEndTime") is not None:
                    logger.warning(f"[FWC:{session_id}] Canary Alert: 'socExceedTimerEndTime' is populated! Value: {entry.get('socExceedTimerEndTime')}")
            
            # Check VPP pre-emption
            comp_res = await self.get_device_composite_info()
            runtime = ((comp_res.get("result") or {}).get("runtimeData") or {})
            if runtime.get("run_status", 0) == 9 or (tou_result.get("todayVppVo") or {}).get("vppStatus") is not None:
                if session.state != "SUSPENDED":
                    session.state = "SUSPENDED"
                    self._force_state.save(self.gateway, session, snapshot)
                    self._force_audit.log(self.gateway, "SESSION_SUSPENDED", session_id, {"reason": "VPP Pre-emption"})
                continue
            
            # If we were suspended, but VPP cleared, release back to prior mode
            if session.state == "SUSPENDED":
                logger.info(f"[FWC:{session_id}] VPP cleared. Auto-releasing suspended session.")
                await self.force_release()
                break
                
            # Check duration
            if session.duration_s is not None:
                elapsed = time.time() - session.started_at
                if elapsed >= session.duration_s:
                    logger.info(f"[FWC:{session_id}] Duration {session.duration_s}s elapsed. Auto-releasing.")
                    await self.force_release()
                    break

            # Check SoC targets
            current_soc = runtime.get("soc", 0)
            if session.action == "force_charge" and session.max_soc is not None:
                if current_soc >= session.max_soc:
                    logger.info(f"[FWC:{session_id}] Target Max SoC {session.max_soc}% reached. Auto-releasing.")
                    await self.force_release()
                    break
            elif session.action == "force_discharge" and session.min_soc is not None:
                if current_soc <= session.min_soc:
                    logger.info(f"[FWC:{session_id}] Target Min SoC {session.min_soc}% reached. Auto-releasing.")
                    await self.force_release()
                    break
                    
    async def force_charge(self, *, power_kw: Optional[float] = None, max_soc: Optional[int] = None, duration_minutes: Optional[int] = None) -> ForceSession:
        vpp_detection = await self._force_preflight("force_charge")
        
        session = ForceSession(
            session_id=str(uuid.uuid4()),
            gateway_id=self.gateway,
            action="force_charge",
            state="ACTIVE",
            started_at=time.time(),
            duration_s=duration_minutes * 60 if duration_minutes else None,
            max_soc=max_soc,
            min_soc=None,
            power_kw=power_kw,
            ramp_time=None,
            grid_charge_max=None,
            grid_discharge_max=None,
            fingerprint=""
        )
        session.fingerprint = f"FWC_FORCE:{session.session_id}"
        await self._force_activate("force_charge", session)
        return session
        
    async def force_discharge(self, *, min_soc: Optional[int] = None, power_kw: Optional[float] = None, duration_minutes: Optional[int] = None) -> ForceSession:
        vpp_detection = await self._force_preflight("force_discharge", min_soc)
        
        # Apply VPP Clamp
        if vpp_detection.cloud_vpp_enrolled and vpp_detection.vpp_reserve_soc is not None:
            if min_soc is not None and min_soc < vpp_detection.vpp_reserve_soc:
                min_soc = vpp_detection.vpp_reserve_soc
                
        session = ForceSession(
            session_id=str(uuid.uuid4()),
            gateway_id=self.gateway,
            action="force_discharge",
            state="ACTIVE",
            started_at=time.time(),
            duration_s=duration_minutes * 60 if duration_minutes else None,
            max_soc=None,
            min_soc=min_soc,
            power_kw=power_kw,
            ramp_time=None,
            grid_charge_max=None,
            grid_discharge_max=None,
            fingerprint=""
        )
        session.fingerprint = f"FWC_FORCE:{session.session_id}"
        await self._force_activate("force_discharge", session)
        return session
        
    async def force_standby(self, *, duration_minutes: Optional[int] = None) -> ForceSession:
        vpp_detection = await self._force_preflight("force_standby")
        
        session = ForceSession(
            session_id=str(uuid.uuid4()),
            gateway_id=self.gateway,
            action="force_standby",
            state="ACTIVE",
            started_at=time.time(),
            duration_s=duration_minutes * 60 if duration_minutes else None,
            max_soc=None,
            min_soc=None,
            power_kw=None,
            ramp_time=None,
            grid_charge_max=None,
            grid_discharge_max=None,
            fingerprint=""
        )
        session.fingerprint = f"FWC_FORCE:{session.session_id}"
        await self._force_activate("force_standby", session)
        return session
        
    async def force_release(self) -> bool:
        state_data = self._force_state.load(self.gateway)
        if not state_data:
            return False
            
        session, snapshot = state_data
        
        logger.info(f"[FWC:{session.session_id}] Restoring previous mode {snapshot.prior_work_mode} with SOC {snapshot.prior_soc}")
        
        try:
            await self.set_mode(snapshot.prior_work_mode, requestedSOC=int(snapshot.prior_soc) if snapshot.prior_soc is not None else None)
            # If prior mode was TOU, we should restore strategy list too, but simplistic restore for now
            self._force_state.clear(self.gateway)
            self._force_audit.log(self.gateway, "SESSION_RELEASED", session.session_id, {})
            return True
        except Exception as e:
            logger.error(f"Failed to release force session: {e}")
            return False
            
    async def force_emergency_clear(self) -> bool:
        """Nuclear option to clear locks without restoring prior state."""
        self._force_state.clear(self.gateway)
        self._force_audit.log(self.gateway, "SESSION_EMERGENCY_CLEARED", "unknown", {})
        return True
        
    async def force_info(self, *, cache_ttl_s: float = 5.0) -> ForceInfo:
        state_data = self._force_state.load(self.gateway)
        if not state_data:
            return ForceInfo(state="IDLE", session_id=None, action=None, started_at=None, elapsed_s=None, duration_s=None, remaining_s=None, watchdog_active=False, target_soc=None, current_soc=None, soc_distance=None, power_kw=None, grid_charge_max=None, grid_discharge_max=None, ramp_time=None, prior_work_mode=None, prior_work_mode_name=None, prior_soc=None, prior_has_tou_backup=False, prior_tou_checksum=None, live_work_mode=None, live_work_mode_name=None, live_run_status=None, live_soc=None, live_fingerprint=None, fingerprint_matches=None, vpp=None, suggested_action=None, suggested_reason=None)
            
        session, snapshot = state_data
        
        elapsed = time.time() - session.started_at
        remaining = max(0, session.duration_s - elapsed) if session.duration_s else None
        
        # In a real implementation we'd populate the live values via API calls
        return ForceInfo(
            state=session.state,
            session_id=session.session_id,
            action=session.action,
            started_at=session.started_at,
            elapsed_s=elapsed,
            duration_s=session.duration_s,
            remaining_s=remaining,
            watchdog_active=True,
            target_soc=session.max_soc if session.action == "force_charge" else session.min_soc,
            current_soc=None,
            soc_distance=None,
            power_kw=session.power_kw,
            grid_charge_max=None,
            grid_discharge_max=None,
            ramp_time=None,
            prior_work_mode=snapshot.prior_work_mode,
            prior_work_mode_name=str(snapshot.prior_work_mode),
            prior_soc=snapshot.prior_soc,
            prior_has_tou_backup=False,
            prior_tou_checksum=None,
            live_work_mode=None,
            live_work_mode_name=None,
            live_run_status=None,
            live_soc=None,
            live_fingerprint=None,
            fingerprint_matches=None,
            vpp=None,
            suggested_action=None,
            suggested_reason=None
        )
