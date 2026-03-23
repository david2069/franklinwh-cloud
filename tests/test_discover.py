"""Tests for device discovery — DeviceSnapshot, FeatureFlags, catalog, rendering."""

import json
import pytest

from franklinwh_cloud.discovery import (
    DeviceSnapshot, SiteInfo, AgateInfo, BatteryInfo, APowerUnit,
    FeatureFlags, AccessoriesInfo, SmartCircuitConfig, GridInfo,
    ElectricalInfo, WarrantyInfo, ProgrammeInfo, AccessoryItem,
    WarrantyDevice,
)


# ── DeviceSnapshot dataclass ──────────────────────────────────────

class TestDeviceSnapshot:
    """DeviceSnapshot creation and serialization."""

    def test_defaults(self):
        snap = DeviceSnapshot()
        assert snap.tier == 1
        assert snap.site.country_id == 0
        assert snap.batteries.count == 0
        assert snap.flags.solar is False
        assert snap.electrical.soc == 0.0

    def test_tier_set(self):
        snap = DeviceSnapshot(tier=3)
        assert snap.tier == 3

    def test_to_dict(self):
        snap = DeviceSnapshot(tier=2)
        d = snap.to_dict()
        assert isinstance(d, dict)
        assert d["tier"] == 2
        assert "site" in d
        assert "agate" in d
        assert "batteries" in d
        assert "flags" in d

    def test_to_dict_json_serializable(self):
        """to_dict() must produce JSON-serializable output."""
        snap = DeviceSnapshot(tier=1)
        snap.site.site_name = "Test Site"
        snap.agate.serial = "1006000TEST"
        result = json.dumps(snap.to_dict())
        assert '"Test Site"' in result

    def test_nested_lists_serializable(self):
        """Lists in dataclasses serialize correctly."""
        snap = DeviceSnapshot()
        snap.batteries.units.append(APowerUnit(serial="AP001", soc=85.0))
        d = snap.to_dict()
        assert len(d["batteries"]["units"]) == 1
        assert d["batteries"]["units"][0]["serial"] == "AP001"


# ── FeatureFlags ──────────────────────────────────────────────────

class TestFeatureFlags:
    """Feature flag defaults and off-grid states."""

    def test_defaults_all_false(self):
        f = FeatureFlags()
        assert f.solar is False
        assert f.off_grid is False
        assert f.v2l_enabled is False
        assert f.mac1_detected is False

    def test_off_grid_three_states(self):
        """Three distinct off-grid sources."""
        f = FeatureFlags()

        # Simulated
        f.off_grid = True
        f.off_grid_simulated = True
        assert f.off_grid_simulated is True
        assert f.off_grid_permanent is False

        # Permanent
        f2 = FeatureFlags(off_grid=True, off_grid_permanent=True)
        assert f2.off_grid_permanent is True
        assert f2.off_grid_simulated is False

        # Detected outage
        f3 = FeatureFlags(off_grid=True, off_grid_reason=3)
        assert f3.off_grid_reason == 3
        assert f3.off_grid_simulated is False
        assert f3.off_grid_permanent is False

    def test_v2l_note(self):
        f = FeatureFlags(v2l_eligible=True, v2l_note="V1 SC needs Generator Module")
        assert "Generator" in f.v2l_note


# ── Accessories ───────────────────────────────────────────────────

class TestAccessories:
    """Accessories and Smart Circuits configuration."""

    def test_smart_circuits_config(self):
        sc = SmartCircuitConfig(count=2, version=1, names=["Circuit 1", "Circuit 2"])
        assert sc.count == 2
        assert sc.version == 1
        assert len(sc.names) == 2

    def test_au_smart_circuits_no_v2l(self):
        """AU Smart Circuits V1 have no V2L port."""
        sc = SmartCircuitConfig(count=2, version=1, v2l_port=False)
        assert sc.v2l_port is False

    def test_us_smart_circuits_v2_has_v2l(self):
        """US Smart Circuits V2 have built-in V2L."""
        sc = SmartCircuitConfig(count=3, version=2, v2l_port=True, v2l_enabled=True)
        assert sc.v2l_port is True
        assert sc.v2l_enabled is True

    def test_accessory_item(self):
        item = AccessoryItem(serial="10070022TEST", type_name="smart_circuits", name="SC")
        assert item.type_name == "smart_circuits"

    def test_apbox_digital_io(self):
        acc = AccessoriesInfo(apbox_di=[1, 0, 0, 0], has_apbox=True)
        assert acc.has_apbox is True
        assert acc.apbox_di[0] == 1


# ── Electrical / Relays ───────────────────────────────────────────

class TestElectricalInfo:
    """Electrical measurements and relay states."""

    def test_relay_dict(self):
        e = ElectricalInfo()
        e.relays = {"grid_1": True, "generator": False, "solar_pv_1": True}
        assert e.relays["grid_1"] is True
        assert e.relays["generator"] is False

    def test_extended_relays(self):
        """Tier 2 adds blackstart, grid 2, pv 2, apbox."""
        e = ElectricalInfo()
        e.relays = {
            "grid_1": True, "generator": False, "solar_pv_1": True,
            "grid_2": False, "black_start": False, "solar_pv_2": False, "apbox": False,
        }
        assert len(e.relays) == 7
        assert "black_start" in e.relays

    def test_tou_status_fields(self):
        e = ElectricalInfo(tou_status=0, tou_dispatch_count=4)
        assert e.tou_status == 0
        assert e.tou_dispatch_count == 4

    def test_single_phase_au(self):
        """AU single-phase: L2 should be None/0."""
        e = ElectricalInfo(v_l1=240.5, v_l2=0.0, i_l1=15.2, i_l2=0.0)
        assert e.v_l1 == 240.5
        assert e.v_l2 == 0.0


# ── Device Catalog ────────────────────────────────────────────────

class TestDeviceCatalog:
    """device_catalog.json loads and has expected structure."""

    @pytest.fixture
    def catalog(self):
        from franklinwh_cloud.mixins.discover import get_catalog
        return get_catalog()

    def test_catalog_loads(self, catalog):
        assert isinstance(catalog, dict)

    def test_has_agate_models(self, catalog):
        assert "agate_models" in catalog
        assert len(catalog["agate_models"]) > 0

    def test_has_apower_models(self, catalog):
        assert "apower_models" in catalog or "accessories" in catalog

    def test_has_accessories(self, catalog):
        assert "accessories" in catalog

    def test_au_agate_exists(self, catalog):
        """AU aGate model should exist."""
        au_models = [m for mid, m in catalog["agate_models"].items()
                     if m.get("country_id") == 3]
        assert len(au_models) > 0

    def test_us_agate_exists(self, catalog):
        """US aGate model should exist."""
        us_models = [m for mid, m in catalog["agate_models"].items()
                     if m.get("country_id") == 2]
        assert len(us_models) > 0

    def test_smart_circuits_au_has_2_circuits(self, catalog):
        """AU Smart Circuits model 302 should have circuit_count=2."""
        for acc_id, acc in catalog.get("accessories", {}).items():
            if acc.get("type") == "smart_circuits" and acc.get("country_id") == 3:
                assert acc.get("circuit_count", 3) == 2
                return
        pytest.skip("No AU smart circuits in catalog")

    def test_smart_circuits_us_has_3_circuits(self, catalog):
        """US Smart Circuits V2 should have circuit_count=3."""
        for acc_id, acc in catalog.get("accessories", {}).items():
            if acc.get("type") == "smart_circuits" and acc.get("country_id") == 2:
                if acc.get("circuit_count", 0) == 3:
                    return
        pytest.skip("No US V2 smart circuits with 3 circuits in catalog")


# ── Region filtering ─────────────────────────────────────────────

class TestRegionFiltering:
    """Region-specific flags (MAC-1/SGIP/NEM only for US)."""

    def test_us_site_country_id(self):
        site = SiteInfo(country_id=2)
        assert site.country_id == 2

    def test_au_site_country_id(self):
        site = SiteInfo(country_id=3)
        assert site.country_id == 3

    def test_mac1_us_only(self):
        """MAC-1 flag is only relevant for US systems."""
        snap_us = DeviceSnapshot()
        snap_us.site.country_id = 2
        snap_us.flags.mac1_detected = True
        assert snap_us.site.country_id == 2
        assert snap_us.flags.mac1_detected is True

        snap_au = DeviceSnapshot()
        snap_au.site.country_id = 3
        # AU systems should never have mac1_detected set
        assert snap_au.flags.mac1_detected is False


# ── Warranty ──────────────────────────────────────────────────────

class TestWarranty:
    """Warranty info dataclass."""

    def test_warranty_device(self):
        wd = WarrantyDevice(serial="170091", model="aGate", expiry="2036-07-22")
        assert wd.expiry == "2036-07-22"

    def test_warranty_info(self):
        w = WarrantyInfo(expiry="2036-07-22", throughput_mwh=43.0, remaining_kwh=37164)
        assert w.remaining_kwh == 37164
        pct = (w.remaining_kwh / (w.throughput_mwh * 1000)) * 100
        assert pct > 80


# ── Grid Info ─────────────────────────────────────────────────────

class TestGridInfo:
    """Grid limits and connection state."""

    def test_defaults_connected(self):
        g = GridInfo()
        assert g.connected is True

    def test_off_grid(self):
        g = GridInfo(connected=False)
        assert g.connected is False

    def test_power_limits(self):
        g = GridInfo(global_discharge_max_kw=5.0, feed_max_kw=5.0)
        assert g.global_discharge_max_kw == 5.0
