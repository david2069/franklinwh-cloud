"""Accessories command — Smart Circuits, V2L, Generator status and device inventory.

Shows installed accessories with cross-referenced model/SKU/compatibility,
device hardware info (aGate/aPower), and optional live power data.

Sections are conditionally displayed based on what hardware is actually
installed — accessoryType 4 = Smart Circuits, 3 = Generator.
V2L is a system-level flag, not an accessory.

Usage:
    franklinwh-cli accessories             # inventory + status
    franklinwh-cli accessories --power     # include live power data
    franklinwh-cli accessories --json      # machine-readable output
"""

from franklinwh_cloud.cli_output import (
    print_header, print_section, print_kv, print_json_output,
    print_warning, c,
)
from franklinwh_cloud.const import (
    FRANKLINWH_MODELS, FRANKLINWH_ACCESSORIES,
)


# ── Smart Circuit switch mode labels ─────────────────────────────────

SC_SWITCH_MODES = {
    0: "Off",
    1: "Always On",
}

# ── Accessory type IDs (from FranklinWH API) ─────────────────────────

ACCY_TYPE_SMART_CIRCUIT = 4
ACCY_TYPE_GENERATOR = 3


# ── Helper: cross-reference accessory type to constants ──────────────

def _resolve_accessory(accessory_type, accessory_name=None, agate_hw_ver=None):
    """Look up accessory constants and check aGate compatibility.

    The API returns a raw accessoryType (e.g. 4) which may not directly
    match FRANKLINWH_ACCESSORIES keys (composite IDs like 302).
    Strategy: direct lookup → name-based search → None.

    Returns (model_info, is_compatible) where model_info is a dict
    from FRANKLINWH_ACCESSORIES or None.
    """
    # Try direct key lookup first
    model_info = FRANKLINWH_ACCESSORIES.get(accessory_type)

    # If no direct match, search by name similarity
    if not model_info and accessory_name:
        name_lower = accessory_name.lower().strip()
        for _key, info in FRANKLINWH_ACCESSORIES.items():
            if info.get("name", "").lower() in name_lower or name_lower in info.get("name", "").lower():
                model_info = info
                break

    if not model_info:
        return None, None

    if agate_hw_ver is None:
        return model_info, None

    compatible_str = model_info.get("compatiable", "")
    if compatible_str == "ALL":
        return model_info, True

    compatible_ids = [int(x.strip()) for x in compatible_str.split("|") if x.strip()]
    return model_info, (agate_hw_ver in compatible_ids)


# ── Main command ─────────────────────────────────────────────────────

async def run(client, *, json_output: bool = False, show_power: bool = False):
    """Execute the accessories command."""

    output = {} if json_output else None

    # ── Gather base data ─────────────────────────────────────────
    # Gateway info (for aGate model cross-ref)
    try:
        gw_res = await client.get_home_gateway_list()
        gateways = gw_res.get("result", [])
        gw = gateways[0] if gateways else {}
    except Exception:
        gw = {}

    agate_hw_ver = int(gw.get("sysHdVersion", -1))
    agate_model = FRANKLINWH_MODELS.get(agate_hw_ver, {})

    # Device info (aPower list, V2L flags)
    try:
        dev_res = await client.get_device_info()
        dev_result = dev_res.get("result", {})
    except Exception:
        dev_result = {}

    # Device composite info (three-phase solar PV)
    try:
        comp_res = await client.get_device_composite_info()
        comp_result = comp_res.get("result", {}) if isinstance(comp_res, dict) else {}
        solar_vo = comp_result.get("solarHaveVo", {}) if comp_result else {}
    except Exception:
        solar_vo = {}

    # Warranty info
    try:
        warranty_res = await client.get_warranty_info()
        warranty = warranty_res.get("result", {})
    except Exception:
        warranty = {}

    # Accessory list
    try:
        acc_res = await client.get_accessories(2)
        accessories = acc_res.get("result", [])
    except Exception:
        accessories = []

    # Power Cap Config (aPower hardware model mapping)
    try:
        cap_res = await client.get_power_cap_config_list()
        power_caps = cap_res.get("result", [])
    except Exception:
        power_caps = []
    
    apower_models_by_hw = {c.get("peHwVersion"): c for c in power_caps}

    # ── Derive installed hardware flags from accessories ──────────
    has_smart_circuits = any(
        a.get("accessoryType") == ACCY_TYPE_SMART_CIRCUIT for a in accessories
    )
    has_generator = any(
        a.get("accessoryType") == ACCY_TYPE_GENERATOR for a in accessories
    )
    v2l_enabled = bool(dev_result.get("v2lModeEnable", 0))
    generator_enabled = bool(dev_result.get("genEn", 0))
    three_phase_solar = str(solar_vo.get("isThreePhaseInstall", "0")) == "1"

    # Smart Circuit config (MQTT 311) — only if SC hardware is installed
    sc_info = {}
    if has_smart_circuits:
        try:
            sc_info = await client.get_smart_circuits_info()
        except Exception:
            sc_info = {}

    # Generator info (REST) — only if generator hardware is installed
    gen_info = None
    if has_generator or generator_enabled:
        try:
            gen_info = await client.get_generator_info()
        except Exception:
            gen_info = None

    # Live power data (MQTT 353) — only with --power
    power_raw = None
    if show_power:
        try:
            power_raw = await client.get_accessories_power_info("0")
        except Exception:
            power_raw = {}

    # ── JSON output ──────────────────────────────────────────────
    if json_output:
        output["agate"] = {
            "serial": gw.get("id", "?"),
            "name": gw.get("name"),
            "firmware": gw.get("version"),
            "hardware_version": agate_hw_ver if agate_hw_ver >= 0 else None,
            "model": agate_model.get("model"),
            "sku": agate_model.get("sku"),
        }

        apower_list = dev_result.get("apowerList", [])
        pe_hw_ver_list = dev_result.get("peHwVerList", [])
        warranty_devices = {
            d.get("sn"): d for d in warranty.get("deviceExpirationList", [])
        }
        output["apower"] = []
        for i, ap in enumerate(apower_list):
            ap_sn = ap.get("id", "?")
            hw_ver = pe_hw_ver_list[i] if i < len(pe_hw_ver_list) else None
            ap_model = apower_models_by_hw.get(hw_ver, {})
            w = warranty_devices.get(ap_sn, {})
            output["apower"].append({
                "serial": ap_sn,
                "rated_power_w": ap.get("ratedPwr", 0),
                "capacity_wh": ap.get("rateBatCap", 0),
                "hardware_version": hw_ver,
                "model_name": ap_model.get("modelName"),
                "warranty_expires": w.get("expirationTime"),
            })

        output["accessories"] = []
        for accy in accessories:
            a_type = accy.get("accessoryType")
            a_name = accy.get("accessoryName", "")
            model_info, is_compat = _resolve_accessory(
                a_type, accessory_name=a_name,
                agate_hw_ver=agate_hw_ver if agate_hw_ver >= 0 else None,
            )
            entry = {
                "name": accy.get("accessoryName", "?"),
                "serial": accy.get("snSerialNumber", "?"),
                "type_id": a_type,
            }
            if model_info:
                entry["model"] = model_info.get("model")
                entry["sku"] = model_info.get("sku")
                entry["compatible_agate_ids"] = model_info.get("compatiable")
                entry["compatible_with_current"] = is_compat
            output["accessories"].append(entry)

        output["hardware_flags"] = {
            "has_smart_circuits": has_smart_circuits,
            "has_generator": has_generator,
            "generator_enabled": generator_enabled,
            "v2l_enabled": v2l_enabled,
            "three_phase_solar": three_phase_solar,
        }

        if has_smart_circuits:
            output["smart_circuits"] = _sc_json(sc_info)
        if v2l_enabled:
            output["v2l"] = {
                "enabled": True,
                "run_state": dev_result.get("v2lRunState", 0),
            }
        if has_generator or generator_enabled:
            output["generator"] = _gen_json(gen_info)

        if power_raw:
            power_data = {}
            if has_smart_circuits:
                power_data["smart_circuits"] = [
                    {"id": 1, "power_w": power_raw.get("SW1ExpPower", 0),
                     "energy_wh": power_raw.get("SW1ExpEnergy", 0)},
                    {"id": 2, "power_w": power_raw.get("SW2ExpPower", 0),
                     "energy_wh": power_raw.get("SW2ExpEnergy", 0)},
                ]
            if v2l_enabled:
                power_data["v2l"] = {
                    "power_w": power_raw.get("CarSWPower", 0),
                    "exp_energy_wh": power_raw.get("CarSWExpEnergy", 0),
                    "imp_energy_wh": power_raw.get("CarSWImpEnergy", 0),
                }
            if has_generator or generator_enabled:
                power_data["generator"] = {
                    "power_w": power_raw.get("genpowerGen", 0),
                    "voltage_v": power_raw.get("volt", 0),
                    "current_a": power_raw.get("curr", 0),
                    "frequency_hz": power_raw.get("freq", 0),
                }
            if power_data:
                output["power"] = power_data

        print_json_output(output)
        return

    # ── Rich text output ─────────────────────────────────────────

    print_header("FranklinWH Accessories & Devices")

    # ── Section 1: Installed Hardware ────────────────────────────

    # aGate
    print_section("🏠", "aGate Gateway")
    print_kv("Serial", gw.get("id", "?"))
    if agate_model:
        print_kv("Model", agate_model.get("model", "?"))
        print_kv("SKU", agate_model.get("sku", "?"))
    else:
        print_kv("Hardware Version", str(agate_hw_ver) if agate_hw_ver >= 0 else "?")
    print_kv("Firmware", gw.get("version", "?"))
    sw_ver = gw.get("softwareVersion", gw.get("swVersion"))
    if sw_ver:
        print_kv("Software", sw_ver)

    # Warranty summary
    w_expiry = warranty.get("expirationTime")
    if w_expiry:
        throughput = (warranty.get("throughput", 0) or 0) * 1000
        remain = warranty.get("remainThroughput", 0) or 0
        print_kv("Warranty Expires", w_expiry)
        if throughput > 0:
            used = throughput - remain
            pct = round((used / throughput) * 100)
            print_kv("Throughput Used", f"{used:.0f} / {throughput:.0f} kWh ({pct}%)")

    # aPower batteries
    apower_list = dev_result.get("apowerList", [])
    pe_hw_ver_list = dev_result.get("peHwVerList", [])
    total_cap = dev_result.get("totalCap", 0)
    warranty_devices = {d.get("sn"): d for d in warranty.get("deviceExpirationList", [])}

    if apower_list:
        print_section("🔋", f"aPower Batteries ({len(apower_list)} units, {total_cap} kWh)")
        for i, ap in enumerate(apower_list):
            ap_sn = ap.get("id", "?")
            hw_ver = pe_hw_ver_list[i] if isinstance(pe_hw_ver_list, list) and i < len(pe_hw_ver_list) else None
            ap_model = apower_models_by_hw.get(hw_ver, {})
            model_name = ap_model.get("modelName")
            rated = ap.get("ratedPwr", 0)
            cap = ap.get("rateBatCap", 0)
            sn_short = ap_sn[-6:] if len(str(ap_sn)) > 6 else ap_sn
            
            w = warranty_devices.get(ap_sn, {})
            w_exp = w.get("expirationTime", "")
            
            model_str = f"  Model: {model_name}" if model_name else ""
            w_str = f"  Warranty: {w_exp}" if w_exp else ""
            
            print_kv(f"aPower {sn_short}",
                     f"Rated: {rated}W  Capacity: {cap}Wh{model_str}{w_str}")

    # Accessories inventory
    if accessories:
        print_section("🔌", f"Installed Accessories ({len(accessories)})")
        for accy in accessories:
            name = accy.get("accessoryName", "?")
            sn = accy.get("snSerialNumber", "?")
            a_type = accy.get("accessoryType")
            model_info, is_compat = _resolve_accessory(
                a_type, accessory_name=name,
                agate_hw_ver=agate_hw_ver if agate_hw_ver >= 0 else None,
            )

            detail_parts = [f"SN: {sn}"]
            if model_info:
                detail_parts.append(f"Model: {model_info.get('model', '?')}")
                sku = model_info.get("sku", "").strip()
                if sku:
                    detail_parts.append(f"SKU: {sku}")
                if is_compat is not None:
                    compat_str = c("green", "✓ compatible") if is_compat else c("red", "✗ incompatible")
                    detail_parts.append(compat_str)
            else:
                detail_parts.append(f"Type: {a_type}")

            print_kv(name, "  ".join(detail_parts))
    else:
        print_section("🔌", "Installed Accessories")
        print_kv("Status", c("dim", "No accessories found"))

    # ── Section 2: Accessory Status (conditional) ────────────────

    # Smart Circuits — only if SC hardware installed
    if has_smart_circuits:
        print_section("⚡", "Smart Circuits")
        if sc_info:
            for i in range(1, 4):
                name_key = f"Sw{i}Name"
                mode_key = f"Sw{i}Mode"
                pro_key = f"Sw{i}ProLoad"
                name = sc_info.get(name_key, f"Circuit {i}")
                mode_val = sc_info.get(mode_key, 0)
                pro_load = sc_info.get(pro_key, 0)

                if not name and mode_val == 0 and pro_load == 0 and i == 3:
                    continue  # skip empty circuit 3

                enabled = mode_val > 0 or pro_load > 0
                status_str = c("green", "Enabled") if enabled else c("dim", "Disabled")
                mode_label = SC_SWITCH_MODES.get(mode_val, f"Mode {mode_val}")
                print_kv(name or f"Circuit {i}", f"{status_str}  ({mode_label})")
        else:
            print_kv("Status", c("dim", "Could not retrieve config"))

    # V2L — only if V2L mode is enabled (system flag, not an accessory)
    if v2l_enabled:
        print_section("🚗", "V2L (Vehicle-to-Load)")
        v2l_state = dev_result.get("v2lRunState", 0)
        state_str = c("green", "Running") if v2l_state >= 1 else c("yellow", "Standby")
        print_kv("Status", f"{c('green', 'Enabled')}  State: {state_str}")

    # Generator — only if generator hardware installed
    if has_generator or generator_enabled:
        print_section("⛽", "Generator")
        if gen_info:
            gen_enabled = gen_info.get("status", gen_info.get("manuSw", 0))
            gen_mode = gen_info.get("manuSw", 0)
            if gen_mode == 2:
                mode_str = "Manual"
            elif gen_mode == 1:
                mode_str = "Auto-Schedule"
            elif gen_mode == 0:
                mode_str = "Not configured"
            else:
                mode_str = f"Mode {gen_mode}"
            print_kv("Status", c("green", "Active") if gen_enabled else c("dim", "Inactive"))
            print_kv("Mode", mode_str)
            # SoC thresholds if present
            start_soc = gen_info.get("startSoc")
            stop_soc = gen_info.get("stopSoc")
            if start_soc is not None:
                print_kv("Start SoC", f"{start_soc}%")
            if stop_soc is not None:
                print_kv("Stop SoC", f"{stop_soc}%")
        else:
            print_kv("Status", c("dim", "Could not retrieve config"))

    # ── Section 3: Live Power (--power) ──────────────────────────

    if show_power and power_raw:
        print_section("📊", "Live Power")
        has_data = False

        # Smart Circuit power
        if has_smart_circuits:
            sw1_pwr = power_raw.get("SW1ExpPower", 0)
            sw2_pwr = power_raw.get("SW2ExpPower", 0)
            sw1_energy = power_raw.get("SW1ExpEnergy", 0)
            sw2_energy = power_raw.get("SW2ExpEnergy", 0)

            sc1_name = sc_info.get("Sw1Name", "Circuit 1") if sc_info else "Circuit 1"
            sc2_name = sc_info.get("Sw2Name", "Circuit 2") if sc_info else "Circuit 2"

            if sw1_pwr or sw1_energy:
                print_kv(sc1_name or "Circuit 1", f"{sw1_pwr:>8.1f} W   Energy: {sw1_energy:.1f} Wh")
                has_data = True
            if sw2_pwr or sw2_energy:
                print_kv(sc2_name or "Circuit 2", f"{sw2_pwr:>8.1f} W   Energy: {sw2_energy:.1f} Wh")
                has_data = True

        # V2L power
        if v2l_enabled:
            car_pwr = power_raw.get("CarSWPower", 0)
            car_exp = power_raw.get("CarSWExpEnergy", 0)
            car_imp = power_raw.get("CarSWImpEnergy", 0)
            if car_pwr or car_exp or car_imp:
                print_kv("V2L", f"{car_pwr:>8.1f} W   Export: {car_exp:.1f} Wh  Import: {car_imp:.1f} Wh")
                has_data = True

        # Generator power
        if has_generator or generator_enabled:
            gen_pwr = power_raw.get("genpowerGen", 0)
            gen_vol = power_raw.get("volt", 0)
            gen_freq = power_raw.get("freq", 0)
            if gen_pwr or gen_vol:
                print_kv("Generator", f"{gen_pwr:>8.1f} W   {gen_vol:.1f} V  {gen_freq:.1f} Hz")
                has_data = True

        if not has_data:
            print_kv("Status", c("dim", "No active accessory power"))

    elif show_power and not power_raw:
        print_section("📊", "Live Power")
        print_warning("Could not retrieve power data (MQTT call failed)")

    print()


# ── JSON helpers ─────────────────────────────────────────────────────

def _sc_json(sc_info):
    """Build Smart Circuits JSON from the 311 response."""
    if not sc_info:
        return []
    circuits = []
    for i in range(1, 4):
        name = sc_info.get(f"Sw{i}Name")
        mode_val = sc_info.get(f"Sw{i}Mode", 0)
        pro_load = sc_info.get(f"Sw{i}ProLoad", 0)
        soc_low = sc_info.get(f"Sw{i}SocLowSet", 0)
        if name is None and mode_val == 0 and pro_load == 0 and i == 3:
            continue
        circuits.append({
            "id": i,
            "name": name or f"Circuit {i}",
            "enabled": mode_val > 0 or pro_load > 0,
            "mode": mode_val,
            "protected_load": bool(pro_load),
            "soc_low_threshold": soc_low,
        })
    return circuits


def _gen_json(gen_info):
    """Build Generator JSON from the REST response."""
    if not gen_info:
        return {"installed": False}
    gen_mode = gen_info.get("manuSw", 0)
    if gen_mode == 2:
        mode_desc = "Manual"
    elif gen_mode == 1:
        mode_desc = "Auto-Schedule"
    else:
        mode_desc = "Not configured"
    return {
        "installed": True,
        "mode": gen_mode,
        "mode_desc": mode_desc,
        "status": gen_info.get("status", 0),
        "start_soc": gen_info.get("startSoc"),
        "stop_soc": gen_info.get("stopSoc"),
    }
