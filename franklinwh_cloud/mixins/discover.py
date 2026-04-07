"""Discovery mixin — client.discover() API.

Provides a structured DeviceSnapshot by querying static/config APIs.
Three tiers control how many APIs are called:
  Tier 1 (~6 calls): site, aGate, batteries, feature flags, operating state
  Tier 2 (~12 calls): + per-battery firmware, accessories, warranty, programmes
  Tier 3 (~20 calls): + network, full firmware, TOU, alarms, billing

Feature: FEAT-CLI-DISCOVER-VERBOSE
"""

import json
import logging
from datetime import datetime
from importlib.resources import files as pkg_files

from franklinwh_cloud.exceptions import FranklinWHTimeoutError


from franklinwh_cloud.discovery import (
    DeviceSnapshot, SiteInfo, AgateInfo, APowerUnit, BatteryInfo,
    AccessoryItem, SmartCircuitConfig, AccessoriesInfo, FeatureFlags,
    GridInfo, WarrantyDevice, WarrantyInfo, ElectricalInfo, ProgrammeInfo,
)
from franklinwh_cloud.const.states import (
    APBOX_IO_STATE, SMART_CIRCUIT_MODE, GENERATOR_STATE, V2L_RUN_STATE, PCS_STATE, BMS_STATE
)

logger = logging.getLogger(__name__)


def _load_catalog():
    """Load device catalog JSON (cached at module level)."""
    catalog_path = pkg_files("franklinwh_cloud.const").joinpath("device_catalog.json")
    with open(str(catalog_path), "r") as f:
        return json.load(f)


_catalog = None


def get_catalog():
    """Get the device catalog (lazy-loaded, cached)."""
    global _catalog
    if _catalog is None:
        _catalog = _load_catalog()
    return _catalog


def _ts_to_str(ts_ms):
    """Convert millisecond timestamp to date string."""
    if not ts_ms:
        return None
    try:
        return datetime.fromtimestamp(ts_ms / 1000.0).strftime("%Y-%m-%d %H:%M")
    except (FranklinWHTimeoutError, ValueError, OSError):
        return None


class DiscoverMixin:
    """Discovery methods for the Client class."""

    async def discover(self, tier: int = 1) -> DeviceSnapshot:
        """Full device discovery — returns structured DeviceSnapshot.

        Parameters
        ----------
        tier : int
            Verbosity level: 1 (quick), 2 (verbose), 3 (pedantic)

        Returns
        -------
        DeviceSnapshot
            Structured snapshot of all discovered device data.
        """
        snapshot = DeviceSnapshot(
            tier=tier,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        catalog = get_catalog()

        # ── Tier 1: Core identity + flags + state ──────────────────
        await self._discover_tier1(snapshot, catalog)

        if tier >= 2:
            # ── Tier 2: Full inventory + accessories + warranty ────
            await self._discover_tier2(snapshot, catalog)

        if tier >= 3:
            # ── Tier 3: Pedantic — everything ──────────────────────
            await self._discover_tier3(snapshot, catalog)

        # Derive feature flags from collected data
        self._derive_flags(snapshot, catalog)

        return snapshot

    # ── Tier 1 ────────────────────────────────────────────────────

    async def _discover_tier1(self, snap, catalog):
        """Tier 1: Site identity, aGate, battery count, feature flags, state."""

        # 1. Home gateway list → aGate identity
        try:
            res = await self.get_home_gateway_list()
            gateways = res.get("result", [])
            if gateways:
                gw = gateways[0]
                hw_ver = int(gw.get("sysHdVersion", 0))
                model_info = catalog["agate_models"].get(str(hw_ver), {})

                snap.agate.serial = gw.get("id", "")
                snap.agate.hw_version = hw_ver
                snap.agate.hw_version_str = gw.get("realSysHdVersion", "")
                snap.agate.model = model_info.get("model", "")
                snap.agate.model_name = model_info.get("name", "")
                snap.agate.sku = model_info.get("sku", "")
                snap.agate.generation = model_info.get("generation", 0)
                snap.agate.protocol_ver = gw.get("protocolVer", "")
                snap.agate.firmware = gw.get("version", "")
                snap.agate.status = gw.get("status", 0)
                snap.agate.active_status = gw.get("activeStatus", 0)
                snap.agate.device_time = gw.get("deviceTime", "")
                snap.agate.conn_type = gw.get("connType", 0)
                snap.agate.conn_type_name = catalog["network_types"].get(
                    str(gw.get("connType", 0)), "Unknown"
                )
                snap.agate.sim_status = gw.get("simCardStatus", 0)
                snap.agate.sim_status_name = catalog["sim_status"].get(
                    str(gw.get("simCardStatus", 0)), "Unknown"
                )
                # Timestamps
                snap.agate.activated = _ts_to_str(gw.get("activeTime"))
                snap.agate.installed = _ts_to_str(gw.get("installTime"))
                snap.agate.created = _ts_to_str(gw.get("createTime"))
                # Site basics from gateway
                snap.site.timezone = gw.get("zoneInfo", "")
                snap.site.country_id = gw.get("countryId", 0)
                snap.site.province_id = gw.get("provinceId", 0)
                country_info = catalog["countries"].get(
                    str(gw.get("countryId", 0)), {}
                )
                snap.site.country = country_info.get("name", "")
                
                # Attach region and accessory catalog quirks
                snap.region_quirks = catalog.get("region_quirks", {}).get(str(snap.site.country_id), {})
                snap.accessory_quirks = catalog.get("accessory_quirks", {})
        except Exception as e:
            logger.warning(f"discover: get_home_gateway_list failed: {e}")

        # 2. Equipment location → geo/address
        try:
            loc = await self.get_equipment_location()
            if isinstance(loc, dict):
                snap.site.gateway_name = loc.get("gatewayName", "")
                snap.site.address = loc.get("completeAddress", "")
                snap.site.city = loc.get("city", "")
                snap.site.postcode = str(loc.get("postCode", ""))
                snap.site.latitude = float(loc.get("latitude", 0) or 0)
                snap.site.longitude = float(loc.get("longitude", 0) or 0)
                snap.site.utc_offset = float(loc.get("timezone", 0) or 0)
                snap.site.dst_active = bool(loc.get("dst", 0))
                snap.site.alpha_code = loc.get("alphaCode", "")
                if loc.get("country"):
                    snap.site.country = loc["country"]
                if loc.get("province"):
                    snap.site.province = loc["province"]
                if loc.get("zoneInfo"):
                    snap.site.timezone = loc["zoneInfo"]
        except Exception as e:
            logger.warning(f"discover: get_equipment_location failed: {e}")

        # 3. Entrance info → feature flags + grid limits
        try:
            entrance = await self.get_entrance_info()
            if entrance:
                snap.flags.solar = bool(entrance.get("solarFlag", False))
                snap.flags.tariff_configured = bool(entrance.get("tariffSettingFlag", False))
                snap.flags.pcs_enabled = bool(entrance.get("pcsEntrance", 0))
                snap.flags.sgip = bool(entrance.get("sgipEntrance", 0))
                snap.flags.bb = bool(entrance.get("bbEntrance", 0))
                snap.flags.ja12 = bool(entrance.get("ja12Entrance", 0))
                snap.flags.sdcp = bool(entrance.get("sdcpFlag", False))
                snap.flags.ahub_detected = bool(entrance.get("ahubAddressingFlag"))
                snap.flags.charging_power_limited = bool(entrance.get("chargingPowerLimited", False))
                snap.flags.need_ct_test = bool(entrance.get("needCtTest", False))
                # Grid limits
                gl = snap.grid
                gl.pcs_entrance = bool(entrance.get("pcsEntrance", 0))
                gl.connected = bool(entrance.get("gridFlag", True))

                gdm = entrance.get("globalGridDischargeMax")
                gcm = entrance.get("globalGridChargeMax")
                gl.global_discharge_max_kw = gdm if gdm and gdm > 0 else None
                gl.global_charge_max_kw = gcm if gcm and gcm > 0 else None
                gl.feed_max_kw = entrance.get("gridFeedMax")
                gl.import_max_kw = entrance.get("gridMax")
                gl.peak_demand_max_kw = entrance.get("peakDemandGridMax")
                gl.feed_max_flag = entrance.get("gridFeedMaxFlag", 0)
                gl.import_max_flag = entrance.get("gridMaxFlag", 0)
                gl.bb_discharge_power = entrance.get("bbDischargePower")
                gl.backup_solution = entrance.get("backupSolution")
        except Exception as e:
            logger.warning(f"discover: get_entrance_info failed: {e}")

        # 4. Device info → aPower list, off-grid, V2L, MPPT
        try:
            dev = await self.get_device_info()
            result = dev.get("result", {}) if isinstance(dev, dict) else {}
            if result:
                snap.agate.device_time = result.get("deviceTime", snap.agate.device_time)
                snap.agate.device_date = result.get("date", "")
                snap.flags.off_grid = bool(result.get("offGirdFlag", 0))
                snap.flags.off_grid_permanent = bool(result.get("offGirdFlag", 0))
                snap.flags.generator_enabled = bool(result.get("genEn", 0))
                snap.flags.v2l_enabled = bool(result.get("v2lModeEnable"))
                snap.flags.mppt_enabled = bool(result.get("mpptEnFlag", False))
                # MAC-1 / MSA early detection from device info
                if result.get("msaInstallStartDetectTime"):
                    snap.flags.mac1_detected = True
                    snap.accessories.has_mac1 = True
                if result.get("offGirdFlag"):
                    snap.grid.connected = False

                # Battery summary
                apower_list = result.get("apowerList", [])
                snap.batteries.count = len(apower_list)
                snap.batteries.total_capacity_kwh = result.get("totalCap", 0.0)
                snap.batteries.total_rated_power_kw = result.get("fixedPowerTotal", 0.0)
                for ap in apower_list:
                    snap.batteries.units.append(APowerUnit(
                        serial=str(ap.get("id", "")),
                        rated_power_kw=ap.get("ratedPwr", 0) / 1000.0,
                        rated_capacity_kwh=ap.get("rateBatCap", 0) / 1000.0,
                    ))
        except Exception as e:
            logger.warning(f"discover: get_device_info failed: {e}")

        # 5. Device composite info → solar, electrical, relays, off-grid
        try:
            from franklinwh_cloud.const import OPERATING_MODES, RUN_STATUS, AGATE_STATE

            comp = await self.get_device_composite_info()
            result = comp.get("result", {}) if isinstance(comp, dict) else {}
            solar_vo = result.get("solarHaveVo", {}) if result else {}
            runtime = result.get("runtimeData", {}) if result else {}

            if solar_vo:
                pv1 = str(solar_vo.get("installPv1Port", "0")) == "1"
                pv2 = str(solar_vo.get("installPv2Port", "0")) == "1"
                snap.flags.three_phase = str(solar_vo.get("isThreePhaseInstall", "0")) == "1"
                snap.flags.ct_split_grid = bool(int(solar_vo.get("gridSplitCtEn", 0) or 0))
                snap.flags.ct_split_pv = bool(int(solar_vo.get("pvSplitCtEn", 0) or 0))
                snap.flags.remote_solar = bool(int(solar_vo.get("remoteSolarEn", 0) or 0))
                if not snap.flags.mppt_enabled:
                    snap.flags.mppt_enabled = str(solar_vo.get("mpptEnFlag", "0")) == "1"
                # Solar detail string
                if pv1 and pv2:
                    snap.flags.solar_detail = "PV1 + PV2"
                elif pv1:
                    snap.flags.solar_detail = "PV1 only"
                elif pv2:
                    snap.flags.solar_detail = "PV2 only"
                elif snap.flags.solar:
                    snap.flags.solar_detail = "Configured"
                # Off-grid from composite
                off_flag = solar_vo.get("offGridFlag", runtime.get("offGridFlag", 0))
                if off_flag:
                    snap.flags.off_grid = True
                    snap.flags.off_grid_reason = int(
                        solar_vo.get("offGridReason", runtime.get("offgridreason", 0)) or 0
                    )
                    snap.grid.connected = False

            if runtime:
                # Operating state
                mode = result.get("currentWorkMode", 0)
                run_st = int(runtime.get("run_status", 0))
                dev_st = int(result.get("deviceStatus", 0))
                snap.electrical.operating_mode = mode
                snap.electrical.operating_mode_name = OPERATING_MODES.get(mode, f"Unknown ({mode})")
                snap.electrical.run_status = run_st
                snap.electrical.run_status_name = RUN_STATUS.get(run_st, f"Unknown ({run_st})")
                snap.electrical.device_status = dev_st
                snap.electrical.soc = runtime.get("soc", 0)
                # Grid electrical
                snap.electrical.v_l1 = runtime.get("gridV1", runtime.get("v_l1"))
                snap.electrical.v_l2 = runtime.get("gridV2", runtime.get("v_l2"))
                snap.electrical.i_l1 = runtime.get("gridA1", runtime.get("i_l1"))
                snap.electrical.i_l2 = runtime.get("gridA2", runtime.get("i_l2"))
                snap.electrical.frequency = runtime.get("gridFreq", runtime.get("frequency"))
                # Relays — main_sw: [Grid 1, Generator, Solar PV 1] — encoding: 1=OPEN, 0=CLOSED
                main_sw = runtime.get("main_sw", [])
                relay_names = ["grid_1", "generator", "solar_pv_1"]
                for i in range(len(relay_names)):
                    val = main_sw[i] if i < len(main_sw) else 0
                    snap.electrical.relays[relay_names[i]] = not bool(val)  # 1=OPEN → store False
                # aPBox digital I/O
                di = runtime.get("di")
                do_st = runtime.get("doStatus")
                if isinstance(di, list):
                    snap.accessories.apbox_di = [APBOX_IO_STATE.get(v, str(v)) for v in di]
                    if any(v != 0 for v in di): snap.accessories.has_apbox = True
                if isinstance(do_st, list):
                    snap.accessories.apbox_do_status = [APBOX_IO_STATE.get(v, str(v)) for v in do_st]
                    if any(v != 0 for v in do_st): snap.accessories.has_apbox = True

                # Generator and V2L States
                gen_stat = runtime.get("genStat")
                if gen_stat is not None:
                    snap.accessories.generator_state = GENERATOR_STATE.get(gen_stat, str(gen_stat))
                v2l_stat = runtime.get("v2lRunState")
                if v2l_stat is not None:
                    snap.accessories.v2l_state = V2L_RUN_STATE.get(v2l_stat, str(v2l_stat))

                # BMS and PCS Operational Arrays
                bms_work = runtime.get("bms_work", [])
                pe_stat = runtime.get("pe_stat", [])
                for i, unit in enumerate(snap.batteries.units):
                    if i < len(bms_work):
                        unit.bms_state = BMS_STATE.get(bms_work[i], str(bms_work[i]))
                    if i < len(pe_stat):
                        unit.pcs_state = PCS_STATE.get(pe_stat[i], str(pe_stat[i]))
        except Exception as e:
            logger.warning(f"discover: get_device_composite_info failed: {e}")

        # 6. Grid status → simulated off-grid (user-opened contactor)
        try:
            gs = await self.get_grid_status()
            result = gs.get("result", {}) if isinstance(gs, dict) else {}
            if result:
                if result.get("offgridSet"):
                    snap.flags.off_grid = True
                    snap.flags.off_grid_simulated = True
                    snap.grid.connected = False
        except Exception as e:
            logger.warning(f"discover: get_grid_status failed: {e}")

    # ── Tier 2 ────────────────────────────────────────────────────

    async def _discover_tier2(self, snap, catalog):
        """Tier 2: Per-battery firmware, accessories, warranty, programmes."""

        # 6. aPower info → per-unit firmware
        try:
            apinfo = await self.get_apower_info()
            ap_list = apinfo.get("result", []) if isinstance(apinfo, dict) else []
            ap_by_serial = {u.serial: u for u in snap.batteries.units}
            for ap in ap_list:
                sn = ap.get("apowerSn", "")
                unit = ap_by_serial.get(sn)
                if unit:
                    unit.soc = ap.get("soc", 0.0)
                    unit.remaining_kwh = ap.get("remainingPower", 0.0)
                    unit.rated_power_kw = ap.get("ratedPower", unit.rated_power_kw)
                    unit.rated_capacity_kwh = ap.get("ratedCapacity", unit.rated_capacity_kwh)
                    unit.fpga_ver = ap.get("fpgaVer", "")
                    unit.dcdc_ver = ap.get("dcdcVer", "")
                    unit.inv_ver = ap.get("invVer", "")
                    unit.bms_ver = ap.get("bmsVer", "")
                    unit.bl_ver = ap.get("blVer", "")
                    unit.th_ver = ap.get("thVer", "")
                    unit.pe_hw_ver = str(ap.get("peHwVer", ""))
                    unit.mppt_app_ver = ap.get("mpptAppVer", "")
                else:
                    snap.batteries.units.append(APowerUnit(
                        serial=sn,
                        rated_power_kw=ap.get("ratedPower", 0.0),
                        rated_capacity_kwh=ap.get("ratedCapacity", 0.0),
                        soc=ap.get("soc", 0.0),
                        remaining_kwh=ap.get("remainingPower", 0.0),
                        fpga_ver=ap.get("fpgaVer", ""),
                        dcdc_ver=ap.get("dcdcVer", ""),
                        inv_ver=ap.get("invVer", ""),
                        bms_ver=ap.get("bmsVer", ""),
                        bl_ver=ap.get("blVer", ""),
                        th_ver=ap.get("thVer", ""),
                        pe_hw_ver=str(ap.get("peHwVer", "")),
                        mppt_app_ver=ap.get("mpptAppVer", ""),
                    ))
            snap.batteries.count = max(snap.batteries.count, len(snap.batteries.units))
        except Exception as e:
            logger.warning(f"discover: get_apower_info failed: {e}")

        # 7. Accessories
        try:
            accy = await self.get_accessories(0)  # Common accessory list (includes AU SC)
            accy_list = accy.get("result", []) if isinstance(accy, dict) else []
            for item in accy_list:
                atype = item.get("accessoryType", 0)
                type_name = catalog.get("accessory_api_types", {}).get(str(atype), f"type_{atype}")
                acc = AccessoryItem(
                    serial=item.get("snSerialNumber", "") or item.get("sn", ""),
                    accessory_type=atype,
                    type_name=type_name,
                    name=item.get("accessoryName", ""),
                    create_time=item.get("createTime", ""),
                )
                snap.accessories.items.append(acc)
                if type_name == "smart_circuits":
                    snap.accessories.has_smart_circuits = True
                elif type_name == "generator":
                    snap.accessories.has_generator = True
        except Exception as e:
            logger.warning(f"discover: get_accessories failed: {e}")

        # 8. Smart circuits detail
        if snap.accessories.has_smart_circuits:
            try:
                sc_info = await self.get_smart_circuits_info()
                if isinstance(sc_info, dict):
                    sw_merged = sc_info.get("SwMerge", 0) == 1

                    if sw_merged:
                        # US V2 V2L merge topology: physical SC1+SC2 → logical SC1 (240V),
                        # physical SC3 → logical SC2. The firmware always returns all 3 Sw
                        # slots; only Sw1 and Sw3 are meaningful to consumers when merged.
                        # We preserve user-set names (Sw1Name, Sw3Name) — renaming is not
                        # supported and would discard user intent. The merged=True flag on
                        # SmartCircuitConfig signals to consumers that circuit[0] is the
                        # merged 240V pair and circuit[1] is the standalone circuit.
                        names = [
                            (sc_info.get("Sw1Name", "") or "").strip(),
                            (sc_info.get("Sw3Name", "") or "").strip(),
                        ]
                        modes = [
                            SMART_CIRCUIT_MODE.get(sc_info.get("Sw1Mode", 0), str(sc_info.get("Sw1Mode", 0))),
                            SMART_CIRCUIT_MODE.get(sc_info.get("Sw3Mode", 0), str(sc_info.get("Sw3Mode", 0))),
                        ]
                        count = 2  # logical — always 2 when merged regardless of hw
                    else:
                        # Standard topology: Sw1, Sw2, [Sw3] — firmware always returns all
                        # 3 slots; trim to actual hardware circuit count from catalog.
                        names = []
                        modes = []
                        for key, mode_key in [("Sw1Name", "Sw1Mode"), ("Sw2Name", "Sw2Mode"), ("Sw3Name", "Sw3Mode")]:
                            name = sc_info.get(key, "") or ""
                            names.append(name.strip() if name else "")
                            m = sc_info.get(mode_key, 0)
                            modes.append(SMART_CIRCUIT_MODE.get(m, str(m)))
                        # Determine hardware circuit count from catalog
                        # AU SC (302) = 2 circuits, US V1 SC (202) = 2, US V2 SC (204) = 3
                        count = 2  # default
                        for acc_id, acc_info in catalog.get("accessories", {}).items():
                            if (acc_info.get("type") == "smart_circuits"
                                    and acc_info.get("country_id") == snap.site.country_id):
                                count = acc_info.get("circuit_count", 2)
                                break
                        # Trim to actual hardware count (firmware always returns 3 slots)
                        names = names[:count]
                        modes = modes[:count]

                    # Determine SC version from aGate generation
                    sc_version = 2 if snap.agate.generation == 2 else 1
                    snap.accessories.smart_circuits = SmartCircuitConfig(
                        count=count,
                        version=sc_version,
                        merged=sw_merged,
                        names=names,
                        modes=modes,
                        v2l_port=bool(sc_info.get("CarSwConsSupEnable")),
                        v2l_enabled=snap.flags.v2l_enabled,
                    )
            except Exception as e:
                logger.warning(f"discover: get_smart_circuits_info failed: {e}")


        # 9. Grid profile
        try:
            gp = await self.get_grid_profile_info()
            if isinstance(gp, dict):
                profiles = gp.get("list", [])
                current_id = gp.get("currentId", 0)
                for p in profiles:
                    if p.get("id") == current_id:
                        snap.site.grid_profile = p.get("name", "")
                        break
        except Exception as e:
            logger.warning(f"discover: get_grid_profile_info failed: {e}")

        # 10. Programme info
        try:
            prog = await self.get_programme_info()
            if isinstance(prog, dict):
                snap.programmes.enrolled = bool(prog.get("flag", 0))
                snap.programmes.program_name = prog.get("programName")
                snap.programmes.partner_name = prog.get("partnerName")
                if snap.programmes.enrolled:
                    snap.flags.vpp_enrolled = True
        except Exception as e:
            logger.warning(f"discover: get_programme_info failed: {e}")

        # 11. Warranty
        try:
            wr = await self.get_warranty_info()
            result = wr.get("result", {}) if isinstance(wr, dict) else {}
            if result:
                snap.warranty.expiry = result.get("expirationTime", "")
                snap.warranty.throughput_mwh = result.get("throughput", 0)
                snap.warranty.remaining_kwh = result.get("remainThroughput", 0)
                snap.warranty.installer_company = result.get("installerCompany", "")
                snap.warranty.installer_phone = result.get("installerCompanyPhone", "")
                snap.warranty.installer_email = result.get("installerCompanyEmail", "")
                snap.warranty.support_phone = result.get("equipmentSupplierPhone", "")
                snap.warranty.warranty_link = result.get("warrantyLink", "")
                for dev in result.get("deviceExpirationList", []):
                    snap.warranty.devices.append(WarrantyDevice(
                        serial=dev.get("sn", ""),
                        model=dev.get("model", ""),
                        device_type=dev.get("type", 0),
                        expiry=dev.get("expirationTime", ""),
                        sub_module_expiry=dev.get("subModuleExpirationTime"),
                    ))
        except Exception as e:
            logger.warning(f"discover: get_warranty_info failed: {e}")

        # 12. Extended relays from get_stats (powerInfo)
        try:
            stats = await self.get_stats()
            if hasattr(stats.current, 'grid_relay2'):
                snap.electrical.relays["grid_2"] = not bool(stats.current.grid_relay2)
                snap.electrical.relays["black_start"] = not bool(stats.current.black_start_relay)
                snap.electrical.relays["solar_pv_2"] = not bool(stats.current.pv_relay2)
                snap.electrical.relays["apbox"] = not bool(stats.current.bfpv_apbox_relay)
        except Exception as e:
            logger.warning(f"discover: get_stats (extended relays) failed: {e}")

        # 13. TOU dispatch status — flags backend issues
        try:
            tou = await self.get_gateway_tou_list()
            result = tou.get("result", {}) if isinstance(tou, dict) else {}
            if result:
                snap.electrical.tou_status = result.get("status", 0)
                dispatch = result.get("dispatchList", [])
                snap.electrical.tou_dispatch_count = len(dispatch)
        except Exception as e:
            logger.warning(f"discover: get_gateway_tou_list (Tier 2) failed: {e}")

        # 14. Real-time Grid Limits (PCS constraints)
        try:
            pcs = await self.get_power_control_settings()
            res = pcs.get("result", {}) if isinstance(pcs, dict) else {}
            if res:
                # Prioritize real PCS settings over entrance cache
                gdm = res.get("globalGridDischargeMax")
                gcm = res.get("globalGridChargeMax")
                if gdm is not None:
                    snap.grid.global_discharge_max_kw = float(gdm) if gdm > 0 else None
                if gcm is not None:
                    snap.grid.global_charge_max_kw = float(gcm) if gcm > 0 else None
                
                feed_max = res.get("gridFeedMax")
                if feed_max is not None:
                    snap.grid.feed_max_kw = float(feed_max)
                imp_max = res.get("gridMax")
                if imp_max is not None:
                    snap.grid.import_max_kw = float(imp_max)
                peak_max = res.get("peakDemandGridMax")
                if peak_max is not None:
                    snap.grid.peak_demand_max_kw = float(peak_max)
        except Exception as e:
            logger.warning(f"discover: get_power_control_settings failed: {e}")


    # ── Tier 3 ────────────────────────────────────────────────────

    async def _discover_tier3(self, snap, catalog):
        """Tier 3: Network, full firmware, TOU, site detail, programmes deep."""

        # 12. aGate firmware detail
        try:
            agate = await self.get_agate_info()
            result = agate.get("result", {}) if isinstance(agate, dict) else {}
            if result:
                snap.agate.ibg_version = result.get("ibgVersion", "")
                snap.agate.sl_version = result.get("slVersion", "")
                snap.agate.aws_version = result.get("awsVersion", "")
                snap.agate.app_version = result.get("appVersion", "")
                snap.agate.meter_version = result.get("meterVersion", "")
                snap.agate.msa_model = result.get("msaModel")
                snap.agate.msa_serial = result.get("msaSn")
                if snap.agate.msa_model or snap.agate.msa_serial:
                    snap.flags.mac1_detected = True
                    snap.accessories.has_mac1 = True
        except Exception as e:
            logger.warning(f"discover: get_agate_info failed: {e}")

        # 13. Site and device info
        try:
            site_data = await self.get_site_and_device_info()
            sites = site_data.get("result", []) if isinstance(site_data, dict) else []
            if sites:
                site = sites[0]
                snap.site.site_id = site.get("siteId", 0)
                snap.site.site_name = site.get("siteName", "")
                if not snap.site.address:
                    snap.site.address = site.get("completeAddress", "")
        except Exception as e:
            logger.warning(f"discover: get_site_and_device_info failed: {e}")

        # 14. TOU → NEM type, electric company, PTO date
        try:
            tou = await self.get_gateway_tou_list()
            result = tou.get("result", {}) if isinstance(tou, dict) else {}
            if result:
                template = result.get("template", {})
                if template:
                    snap.site.electric_company = template.get("electricCompany", "")
                    snap.site.tariff_name = template.get("name", "")
                    der = template.get("derSchdule", "")
                    snap.site.der_schedule = der or snap.site.der_schedule
                    # NEM type
                    nem_type = result.get("nemType", 0)
                    snap.flags.nem_type = catalog.get("nem_types", {}).get(
                        str(nem_type), f"Unknown ({nem_type})"
                    )
                pto = result.get("ptoDate", "") or result.get("template", {}).get("ptoDate", "")
                if pto:
                    snap.site.pto_date = pto
                # VPP from TOU
                vpp_soc = result.get("vppSocVo", {})
                if vpp_soc:
                    snap.programmes.vpp_soc = vpp_soc.get("vppSoc", 20.0)
                    snap.programmes.vpp_min_soc = vpp_soc.get("vppMinSoc", 5.0)
                    snap.programmes.vpp_max_soc = vpp_soc.get("vppMaxSoc", 100.0)
                vpp_vo = result.get("todayVppVo", {})
                if vpp_vo and vpp_vo.get("vppFlag", 0) != 0:
                    snap.flags.vpp_enrolled = True
                    snap.programmes.enrolled = True
        except Exception as e:
            logger.warning(f"discover: get_gateway_tou_list failed: {e}")

    # ── Flag derivation ───────────────────────────────────────────

    def _derive_flags(self, snap, catalog):
        """Derive computed flags from collected data."""
        # V2L eligibility
        country_id = snap.site.country_id
        has_sc = snap.accessories.has_smart_circuits
        has_gen = snap.accessories.has_generator or snap.flags.generator_enabled
        sc = snap.accessories.smart_circuits

        if not has_sc:
            snap.flags.v2l_eligible = False
            snap.flags.v2l_note = "No Smart Circuits installed"
        elif country_id == 3:  # AU
            snap.flags.v2l_eligible = False
            snap.flags.v2l_note = "AU Smart Circuits have no V2L port"
        elif sc and sc.version == 2:
            snap.flags.v2l_eligible = True
            snap.flags.v2l_note = "V2L built-in (V2 Smart Circuits)"
        elif sc and sc.version == 1 and has_gen:
            snap.flags.v2l_eligible = True
            snap.flags.v2l_note = "V2L via CarSW (V1 SC + Generator Module)"
        elif sc and sc.version == 1:
            snap.flags.v2l_eligible = False
            snap.flags.v2l_note = "V1 Smart Circuits requires Generator Module for V2L"
        else:
            snap.flags.v2l_eligible = snap.flags.v2l_enabled
            snap.flags.v2l_note = ""
