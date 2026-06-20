import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ForceSession:
    """Represents an active force mode session."""
    session_id: str
    gateway_id: str
    action: str  # "force_charge" | "force_discharge" | "force_standby"
    state: str  # "ACTIVE" | "SUSPENDED"
    started_at: float
    duration_s: int | None
    max_soc: int | None
    min_soc: int | None
    power_kw: float | None
    ramp_time: int | None
    grid_charge_max: float | None
    grid_discharge_max: float | None
    fingerprint: str  # "FWC_FORCE:{session_id}"

    @classmethod
    def from_dict(cls, data: dict) -> "ForceSession":
        return cls(**data)


@dataclass
class ForceStateSnapshot:
    """Complete capture of prior operating state for restoration."""
    prior_work_mode: int
    prior_soc: int
    prior_backup_forever_flag: int | None
    prior_next_work_mode: int | None
    prior_duration_minutes: int | None
    prior_tou_strategy_list: list | None
    prior_tou_checksum: str | None
    raw_tou_list_result: dict | None
    raw_composite_result: dict | None
    captured_at: float

    @classmethod
    def from_dict(cls, data: dict) -> "ForceStateSnapshot":
        return cls(**data)


@dataclass
class VPPDetection:
    """Result of VPP state analysis from multiple signals."""
    firmware_vpp_active: bool
    cloud_vpp_enrolled: bool
    cloud_vpp_dispatching: bool
    cloud_vpp_scheduled: bool
    vpp_reserve_soc: int | None
    vpp_min_soc: int | None

    @property
    def is_locked(self) -> bool:
        """Determines if force operations should be blocked."""
        return self.cloud_vpp_dispatching or self.firmware_vpp_active


@dataclass
class ForceInfo:
    """Complete force mode state for a gateway."""
    state: str  # "IDLE" | "ACTIVE" | "DESYNCHRONISED" | "STALE_LOCK" | "ORPHAN" | "SUSPENDED"
    session_id: str | None
    action: str | None
    started_at: float | None
    elapsed_s: float | None
    duration_s: int | None
    remaining_s: float | None
    watchdog_active: bool
    target_soc: int | None
    current_soc: int | None
    soc_distance: int | None
    power_kw: float | None
    grid_charge_max: float | None
    grid_discharge_max: float | None
    ramp_time: int | None
    prior_work_mode: int | None
    prior_work_mode_name: str | None
    prior_soc: int | None
    prior_has_tou_backup: bool
    prior_tou_checksum: str | None
    live_work_mode: int | None
    live_work_mode_name: str | None
    live_run_status: int | None
    live_soc: int | None
    live_fingerprint: str | None
    fingerprint_matches: bool | None
    vpp: VPPDetection | None
    suggested_action: str | None
    suggested_reason: str | None


class ForceStateStore:
    """Crash-safe atomic JSON file persistence for force sessions."""

    def __init__(self, state_dir: Path | str):
        self._state_dir = Path(state_dir)
        self._state_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, gateway_id: str) -> Path:
        return self._state_dir / f"{gateway_id}_force_state.json"

    def save(self, gateway_id: str, session: ForceSession, snapshot: ForceStateSnapshot) -> Path:
        """Atomic save of session and snapshot."""
        file_path = self._get_file_path(gateway_id)
        tmp_path = file_path.with_suffix(".json.tmp")

        data = {
            "version": 1,
            "session": asdict(session),
            "snapshot": asdict(snapshot),
        }

        with open(tmp_path, "w") as f:
            json.dump(data, f)
            f.flush()
            os.fsync(f.fileno())

        tmp_path.rename(file_path)
        return file_path

    def load(self, gateway_id: str) -> tuple[ForceSession, ForceStateSnapshot] | None:
        """Load session and snapshot if they exist."""
        file_path = self._get_file_path(gateway_id)
        if not file_path.exists():
            return None

        try:
            with open(file_path, "r") as f:
                data = json.load(f)

            if data.get("version") == 1:
                session = ForceSession.from_dict(data["session"])
                snapshot = ForceStateSnapshot.from_dict(data["snapshot"])
                return session, snapshot
        except Exception as e:
            logger.error(f"Failed to load force state for {gateway_id}: {e}")

        return None

    def clear(self, gateway_id: str) -> bool:
        """Clear the state file."""
        file_path = self._get_file_path(gateway_id)
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    def has_active(self, gateway_id: str) -> bool:
        """Fast existence check."""
        return self._get_file_path(gateway_id).exists()

    def list_active(self) -> list[tuple[str, ForceSession]]:
        """List all active sessions (for orphan detection)."""
        active = []
        for file_path in self._state_dir.glob("*_force_state.json"):
            gateway_id = file_path.name.replace("_force_state.json", "")
            data = self.load(gateway_id)
            if data:
                active.append((gateway_id, data[0]))
        return active


class ForceAuditLog:
    """Append-only JSONL forensic trail."""

    def __init__(self, state_dir: Path | str):
        self._state_dir = Path(state_dir)
        self._state_dir.mkdir(parents=True, exist_ok=True)

    def log(self, gateway_id: str, event: str, session_id: str, detail: dict) -> None:
        """Appends a single JSONL audit entry."""
        log_path = self._state_dir / f"{gateway_id}_force_audit.jsonl"
        entry = {
            "ts": datetime.utcnow().timestamp(),
            "event": event,
            "session_id": session_id,
            "gateway_id": gateway_id,
            "detail": detail,
        }
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
            f.flush()
            os.fsync(f.fileno())

        # Also log to standard logger
        if detail:
            logger.info(f"[FWC:{session_id}] {event}: {detail}")
        else:
            logger.info(f"[FWC:{session_id}] {event}")
