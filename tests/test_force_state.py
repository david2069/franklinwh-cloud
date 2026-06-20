import json
import pytest
import time
from pathlib import Path
from franklinwh_cloud.force_state import ForceStateStore, ForceAuditLog, ForceSession, ForceStateSnapshot, VPPDetection

def test_force_state_store(tmp_path):
    store = ForceStateStore(tmp_path)
    gateway_id = "GW123"
    
    session = ForceSession(
        session_id="uuid1",
        gateway_id=gateway_id,
        action="force_charge",
        state="ACTIVE",
        started_at=time.time(),
        duration_s=3600,
        max_soc=90,
        min_soc=None,
        power_kw=5.0,
        ramp_time=None,
        grid_charge_max=None,
        grid_discharge_max=None,
        fingerprint="FWC_FORCE:uuid1"
    )
    
    snapshot = ForceStateSnapshot(
        prior_work_mode=2,
        prior_soc=20,
        prior_backup_forever_flag=None,
        prior_next_work_mode=None,
        prior_duration_minutes=None,
        prior_tou_strategy_list=[],
        prior_tou_checksum=None,
        raw_tou_list_result={"list": []},
        raw_composite_result={"result": {}},
        captured_at=time.time()
    )
    
    # Save it
    saved_path = store.save(gateway_id, session, snapshot)
    assert saved_path.exists()
    assert store.has_active(gateway_id)
    
    # Load it
    loaded = store.load(gateway_id)
    assert loaded is not None
    loaded_session, loaded_snapshot = loaded
    
    assert loaded_session.session_id == "uuid1"
    assert loaded_session.action == "force_charge"
    assert loaded_snapshot.prior_work_mode == 2
    
    # List active
    active = store.list_active()
    assert len(active) == 1
    assert active[0][0] == gateway_id
    
    # Clear
    assert store.clear(gateway_id)
    assert not store.has_active(gateway_id)
    assert store.load(gateway_id) is None


def test_force_audit_log(tmp_path):
    audit = ForceAuditLog(tmp_path)
    gateway_id = "GW123"
    
    audit.log(gateway_id, "SESSION_STARTED", "uuid1", {"action": "force_charge"})
    audit.log(gateway_id, "SESSION_SUSPENDED", "uuid1", {"reason": "VPP"})
    
    log_file = tmp_path / f"{gateway_id}_force_audit.jsonl"
    assert log_file.exists()
    
    lines = log_file.read_text().strip().split("\n")
    assert len(lines) == 2
    
    entry1 = json.loads(lines[0])
    assert entry1["event"] == "SESSION_STARTED"
    assert entry1["detail"]["action"] == "force_charge"
    
    entry2 = json.loads(lines[1])
    assert entry2["event"] == "SESSION_SUSPENDED"
    assert entry2["detail"]["reason"] == "VPP"


def test_vpp_detection():
    # Enrolled but not active
    vpp = VPPDetection(
        firmware_vpp_active=False,
        cloud_vpp_enrolled=True,
        cloud_vpp_dispatching=False,
        cloud_vpp_scheduled=False,
        vpp_reserve_soc=20,
        vpp_min_soc=5
    )
    assert not vpp.is_locked
    
    # Firmware Modbus locked
    vpp2 = VPPDetection(
        firmware_vpp_active=True,
        cloud_vpp_enrolled=False,
        cloud_vpp_dispatching=False,
        cloud_vpp_scheduled=False,
        vpp_reserve_soc=None,
        vpp_min_soc=None
    )
    assert vpp2.is_locked
    
    # Cloud VPP actively dispatching
    vpp3 = VPPDetection(
        firmware_vpp_active=False,
        cloud_vpp_enrolled=True,
        cloud_vpp_dispatching=True,
        cloud_vpp_scheduled=False,
        vpp_reserve_soc=20,
        vpp_min_soc=5
    )
    assert vpp3.is_locked
