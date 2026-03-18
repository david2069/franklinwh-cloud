"""Discover command — gateway, device, warranty, and accessory enumeration."""

from datetime import datetime

from franklinwh_cloud.cli_output import (
    print_header, print_section, print_kv, print_json_output, print_warning,
    c,
)
from franklinwh_cloud.const import (
    FRANKLINWH_MODELS, NETWORK_TYPES, COUNTRY_ID, OPERATING_MODES,
    RUN_STATUS, AGATE_STATE, SIM_STATUS,
)


async def run(client, *, json_output: bool = False, show_warranty: bool = True,
              show_accessories: bool = True):
    """Execute the discover command."""

    if json_output:
        output = {}
        output["home_gateways"] = await client.get_home_gateway_list()
        output["device_info"] = await client.get_device_info()
        output["composite_info"] = await client.get_device_composite_info()
        if show_warranty:
            output["warranty"] = await client.get_warranty_info()
        print_json_output(output)
        return

    print_header("FranklinWH Device Discovery")

    # ── Home Gateway List ─────────────────────────────────────────
    res = await client.get_home_gateway_list()
    gateways = res.get("result", [])

    for gate in gateways:
        sn = gate.get("id", "?")
        name = gate.get("name", "Unknown")
        status = gate.get("status", 0)
        hw_ver = int(gate.get("sysHdVersion", 0))

        print_section("🏠", f"aGate: {name} ({sn})")

        # Model lookup
        model_info = FRANKLINWH_MODELS.get(hw_ver, {})
        if model_info:
            print_kv("Model", model_info.get("model", "Unknown"))
            print_kv("SKU", model_info.get("sku", "Unknown"))

        print_kv("Status", f'{status}  Active: {gate.get("activeStatus", "?")}')
        print_kv("Protocol", gate.get("protocolVer", "?"))
        print_kv("Firmware", gate.get("version", "?"))
        sw_ver = gate.get("softwareVersion", gate.get("swVersion", ""))
        if sw_ver:
            print_kv("Software", sw_ver)
        print_kv("Hardware", gate.get("sysHdVersion", "?"))

        # Network & Signal
        conn = gate.get("connType", 0)
        sim_status = gate.get('simCardStatus', 0)
        sim_desc = SIM_STATUS.get(int(sim_status), f'Unknown ({sim_status})')
        print_kv("Network", f"{NETWORK_TYPES.get(conn, f'Type {conn}')}")
        print_kv("SIM Card", sim_desc)
        wifi_sig = gate.get("wifiSignal", gate.get("wifiStrength"))
        mobile_sig = gate.get("mobileSignal", gate.get("cellSignal"))
        if wifi_sig is not None:
            print_kv("WiFi Signal", f"{wifi_sig} dBm")
        if mobile_sig is not None:
            print_kv("4G Signal", f"{mobile_sig} dBm")

        # Timestamps
        for label, key in [("Activated", "activeTime"), ("Installed", "installTime"), ("Created", "createTime")]:
            ts = gate.get(key)
            if ts:
                print_kv(label, datetime.fromtimestamp(ts / 1000.0).strftime("%Y-%m-%d %H:%M"))

        # Location
        print_kv("Address", gate.get("address", "N/A"))
        country = gate.get("countryId", 0)
        print_kv("Country", f'{COUNTRY_ID.get(country, "Unknown")} (ID: {country})')
        print_kv("Timezone", gate.get("zoneInfo", "?"))

        # Group info
        if gate.get("groupFlag"):
            print_kv("Group", f'{gate.get("groupName", "?")} (ID: {gate.get("groupId", "?")})')

    # ── Device Detail ─────────────────────────────────────────────
    print_section("📟", "Device Detail")
    try:
        res = await client.get_device_info()
        result = res.get("result", {})

        print_kv("Device Time", result.get("deviceTime", "?"))
        print_kv("Active Status", result.get("activeStatus", "?"))
        print_kv("Solar Flag", result.get("solarFlag", "?"))
        print_kv("Off-Grid", result.get("offGirdFlag", 0))
        print_kv("V2L Mode", f'Enable: {result.get("v2lModeEnable", 0)}  State: {result.get("v2lRunState", 0)}')
        print_kv("MPPT", f'Enable: {result.get("mpptEnFlag", 0)}')

        # aPower list
        apower_list = result.get("apowerList", [])
        total_cap = result.get("totalCap", 0)
        fixed_total = result.get("fixedPowerTotal", 0)

        print_section("🔋", f"aPower Units ({len(apower_list)} batteries, {total_cap} kWh total)")
        print_kv("Fixed Power Total", f"{fixed_total} kW")
        print_kv("Fixed Power Average", f'{result.get("fixedPowerAverage", 0)} kW')

        for ap in apower_list:
            ap_id = ap.get("id", "?")
            rated = ap.get("ratedPwr", "?")
            cap = ap.get("rateBatCap", "?")
            print_kv(f"aPower {ap_id[-6:] if len(str(ap_id)) > 6 else ap_id}",
                     f"Rated: {rated}W  Capacity: {cap}Wh")
    except Exception as e:
        print_warning(f"Could not retrieve device detail: {e}")

    # ── Composite Info (runtime state) ────────────────────────────
    print_section("⚡", "Runtime State")
    try:
        res = await client.get_device_composite_info()
        data = res.get("result", {})
        rt = data.get("runtimeData", {})
        solar = data.get("solarHaveVo", {})

        mode = data.get("currentWorkMode", 0)
        print_kv("Operating Mode", f'{mode} = {OPERATING_MODES.get(mode, "Unknown")}')
        run_st = rt.get("run_status", 0)
        print_kv("Run Status", f'{run_st} = {RUN_STATUS.get(int(run_st), "Unknown")}')
        dev_st = data.get("deviceStatus", 0)
        print_kv("Device Status", f'{dev_st} = {AGATE_STATE.get(int(dev_st), "Unknown")}')
        print_kv("SoC", f'{rt.get("soc", 0)}%')

        # Power flows
        print_kv("Home Load", f'{rt.get("p_load", 0)} kW')
        print_kv("Grid", f'{rt.get("p_uti", 0)} kW')
        print_kv("Solar", f'{rt.get("p_sun", 0)} kW')
        print_kv("Battery", f'{rt.get("p_fhp", 0)} kW')
        print_kv("Generator", f'{rt.get("p_gen", 0)} kW')

        # Solar config
        flags = []
        if solar.get("installProximalsolar"):
            flags.append("Proximal Solar")
        if solar.get("installPv1Port"):
            flags.append("PV1")
        if solar.get("installPv2Port"):
            flags.append("PV2")
        if solar.get("mpptEnFlag"):
            flags.append("MPPT")
        if solar.get("remoteSolarEn"):
            flags.append("Remote Solar")
        if solar.get("installApboxSolar"):
            flags.append("aPower Solar")
        if flags:
            print_kv("Solar Config", ", ".join(flags))

        phase = "Three Phase" if solar.get("isThreePhaseInstall") else "Single Phase"
        print_kv("Phase", phase)

        # Grid voltages/currents (from runtimeData)
        v1 = rt.get("gridV1", rt.get("v_l1"))
        v2 = rt.get("gridV2", rt.get("v_l2"))
        i1 = rt.get("gridA1", rt.get("i_l1"))
        i2 = rt.get("gridA2", rt.get("i_l2"))
        freq = rt.get("gridFreq", rt.get("frequency"))
        if v1 is not None or v2 is not None:
            print_section("🔌", "Grid Electrical")
            if v1 is not None:
                print_kv("L1 Voltage", f"{v1} V")
            if i1 is not None:
                print_kv("L1 Current", f"{i1} A")
            if v2 is not None and float(v2) > 0:
                print_kv("L2 Voltage", f"{v2} V")
            if i2 is not None and float(i2) > 0:
                print_kv("L2 Current", f"{i2} A")
            if freq is not None:
                print_kv("Frequency", f"{freq} Hz")

        # aPower detail
        fhp_sn = rt.get("fhpSn", [])
        fhp_soc = rt.get("fhpSoc", [])
        fhp_power = rt.get("fhpPower", [])
        bms_work = rt.get("bms_work", [])
        if fhp_sn:
            print_section("🔋", "aPower Runtime")
            for i, sn in enumerate(fhp_sn):
                soc = fhp_soc[i] if i < len(fhp_soc) else "?"
                pwr = fhp_power[i] if i < len(fhp_power) else "?"
                bms = bms_work[i] if i < len(bms_work) else 0
                print_kv(sn, f"SoC: {soc}%  Power: {pwr}W  {RUN_STATUS.get(int(bms), '?')}")

        # Relays
        main_sw = rt.get("main_sw", [])
        if main_sw:
            relay_names = ["Grid Relay", "Generator Relay", "Solar PV Relay"]
            print_section("🔧", "Relays")
            for i, sw in enumerate(main_sw):
                name = relay_names[i] if i < len(relay_names) else f"Relay {i}"
                state = c("green", "ON") if sw else c("dim", "OFF")
                print_kv(name, state)

    except Exception as e:
        print_warning(f"Could not retrieve composite info: {e}")

    # ── Warranty ──────────────────────────────────────────────────
    if show_warranty:
        print_section("📋", "Warranty")
        try:
            res = await client.get_warranty_info()
            w = res.get("result", {})
            print_kv("Expires", w.get("expirationTime", "?"))

            throughput = (w.get("throughput", 0) or 0) * 1000  # kWh
            remain = (w.get("remainThroughput", 0) or 0)
            if throughput > 0:
                used = throughput - remain
                pct_used = round((used / throughput) * 100)
                print_kv("Throughput", f"{throughput:.0f} kWh")
                print_kv("Used", f"{used:.0f} kWh ({pct_used}%)")
                print_kv("Remaining", f"{remain:.0f} kWh ({100 - pct_used}%)")

            devices = w.get("deviceExpirationList", [])
            for dev in devices:
                sn = dev.get("sn", "?")
                model = dev.get("model", "?")
                exp = dev.get("expirationTime", "?")
                print_kv(f"{model} {sn[-6:]}", f"Expires: {exp}")
        except Exception as e:
            print_warning(f"Could not retrieve warranty info: {e}")

    # ── Accessories ───────────────────────────────────────────────
    if show_accessories:
        print_section("🔌", "Accessories")
        try:
            res = await client.get_accessories(2)
            accessories = res.get("result", [])
            total = res.get("total", 0)
            print_kv("Total", f"{total} accessories")
            for accy in accessories:
                name = accy.get("accessoryName", "?")
                atype = accy.get("accessoryType", "?")
                sn = accy.get("snSerialNumber", "?")
                print_kv(name, f"Type: {atype}  SN: {sn}")
        except Exception as e:
            print_warning(f"Could not retrieve accessories: {e}")

    print()
