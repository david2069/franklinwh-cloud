"""BMS command — Battery Management System inspection.

Displays per-cell voltage and temperature telemetry, pack health,
grid/bus topology, hardware states, and safety indicators.

Mirrors the FHP Demo Battery Management page layout.

Usage:
    franklinwh-cli bms                # formatted output
    franklinwh-cli bms --json         # machine-readable
"""

from franklinwh_cloud.cli_output import (
    print_header, print_section, print_kv, print_json_output,
    print_warning, print_error, c,
)


async def run(client, *, json_output: bool = False):
    """Execute the BMS inspection command."""

    # ── Get device info to find aPower serials ────────────────────
    try:
        dev_res = await client.get_device_info()
        dev_result = dev_res.get("result", {})
        apower_list = dev_result.get("apowerList", [])
        total_cap = dev_result.get("totalCap", 0)
    except Exception as e:
        if json_output:
            print_json_output({"error": str(e)})
        else:
            print_error(f"Could not retrieve device info: {e}")
        return

    if not apower_list:
        if json_output:
            print_json_output({"error": "No aPower batteries found"})
        else:
            print_error("No aPower batteries found on this gateway.")
        return

    all_bms = []

    if not json_output:
        print_header("Battery Management")

        # ── System Overview ──────────────────────────────────────
        print_section("⚡", "System Overview")
        print_kv("Total Capacity", f"{total_cap} kWh")
        print_kv("Units Online", f"{len(apower_list)}")
        for ap in apower_list:
            rated = ap.get("ratedPwr", 0)
            cap = ap.get("rateBatCap", 0)
            print_kv("Max Throughput", f"↓ {rated/1000:.0f}  ↑ {rated/1000:.0f} kW")

    # ── Query BMS for each aPower ────────────────────────────────
    for ap in apower_list:
        serial = ap.get("id", "?")
        sn_short = serial[-4:] if len(str(serial)) > 4 else serial

        try:
            bms = await client.get_bms_info(serial)
        except Exception as e:
            if json_output:
                all_bms.append({"serial": serial, "error": str(e)})
            else:
                print_warning(f"Could not get BMS for aPower {sn_short}: {e}")
            continue

        if json_output:
            bms["serial"] = serial
            all_bms.append(bms)
            continue

        # ── BMS Inspection Header ────────────────────────────────
        print_section("🔋", f"BMS Inspection — aPower ({sn_short})")
        print_kv("SN", serial)

        # Balancing
        balan = bms.get("balanState", 0)
        balan_str = c("green", "Active") if balan else c("dim", "Inactive")
        print_kv("Balancing", balan_str)

        # ── Pack Health ──────────────────────────────────────────
        print_section("💚", "Pack Health")

        soc = bms.get("batSoc", 0)
        soh = bms.get("batSoh", 0)
        soc_color = "green" if soc > 20 else ("yellow" if soc > 10 else "red")
        soh_color = "green" if soh > 80 else ("yellow" if soh > 60 else "red")
        print_kv("Charge (SoC)", c(soc_color, f"{soc}%"))
        print_kv("Health (SoH)", c(soh_color, f"{soh}%"))

        total_v = bms.get("batTotalVolt", 0)
        bat_curr = bms.get("batCurr", 0)
        curr_label = "Charging" if bat_curr > 0 else "Discharging"
        curr_color = "green" if bat_curr > 0 else "cyan"
        print_kv("Total Voltage", f"{total_v} V")
        print_kv("Current", f"{c(curr_color, f'{bat_curr} A')}  ({curr_label})")

        # Temperatures
        dev_temp = bms.get("devTemp", 0)
        llc_temp = bms.get("llcTemp", 0)
        inv_temp = bms.get("invTemp", 0)
        buck_temp = bms.get("buckBoostTemp", 0)
        print_kv("Device Temp", f"{dev_temp} °C")
        print_kv("Inverter Temp", f"{inv_temp} °C   LLC: {llc_temp} °C   BuckBoost: {buck_temp} °C")

        freq = bms.get("gridFreq", 0)
        print_kv("Grid Frequency", f"{freq} Hz")

        # ── Cell Telemetry ───────────────────────────────────────
        bat_volts = bms.get("batVolt", [])
        bat_temps = bms.get("batTemp", [])
        highest_v = bms.get("singleHighestVolt", 0)
        lowest_v = bms.get("singleLowestVolt", 0)
        highest_t = bms.get("singleHighestTemp", 0)
        lowest_t = bms.get("singleLowestTemp", 0)
        max_v_pos = bms.get("maxVolPos", 0)
        min_v_pos = bms.get("minVolPos", 0)
        max_t_pos = bms.get("maxTempPos", 0)
        min_t_pos = bms.get("minTempPos", 0)

        if bat_volts:
            n_cells = len(bat_volts)
            spread = highest_v - lowest_v
            spread_color = "green" if spread <= 10 else ("yellow" if spread <= 20 else "red")

            print_section("🔬", f"Cell Telemetry ({n_cells} Series)")
            print_kv("Highest", f"{highest_v} mV (cell {max_v_pos})")
            print_kv("Lowest", f"{lowest_v} mV (cell {min_v_pos})")
            print_kv("Spread", c(spread_color, f"{spread} mV"))
            print_kv("Temp Range", f"{lowest_t}°C (cell {min_t_pos}) — {highest_t}°C (cell {max_t_pos})")
            print()

            # Print cells in rows of 8 (like the FHP Demo grid)
            for row_start in range(0, n_cells, 8):
                row_end = min(row_start + 8, n_cells)
                # Cell numbers
                nums = "".join(f"  {c('dim', f'#{i+1}'):>8s}" for i in range(row_start, row_end))
                print(f"   {nums}")

                # Voltages
                volts_line = ""
                for i in range(row_start, row_end):
                    v = bat_volts[i] if i < len(bat_volts) else 0
                    v_str = f"{v/1000:.3f}V"
                    if i + 1 == max_v_pos:
                        v_str = c("green", f"↑{v_str}")
                    elif i + 1 == min_v_pos:
                        v_str = c("yellow", f"↓{v_str}")
                    else:
                        v_str = f" {v_str}"
                    volts_line += f"{v_str:>10s}"
                print(f"   {volts_line}")

                # Temperatures
                temps_line = ""
                for i in range(row_start, row_end):
                    t = bat_temps[i] if i < len(bat_temps) else 0
                    t_str = f"{t}°C"
                    if i + 1 == max_t_pos:
                        t_str = c("red", f"*{t_str}")
                    else:
                        t_str = f" {t_str}"
                    temps_line += f"{t_str:>10s}"
                print(f"   {temps_line}")
                print()

        # ── Grid & Bus Topology ──────────────────────────────────
        print_section("🔌", "Grid & Bus Topology")
        gv1 = bms.get("gridVol1", 0)
        gv2 = bms.get("gridVol2", 0)
        iv1 = bms.get("invVolt1", 0)
        iv2 = bms.get("invVolt2", 0)
        pos_bus = bms.get("positiveBusVolt", 0)
        neg_bus = bms.get("negativeBusVolt", 0)
        pe_bat = bms.get("pebatVolt", 0)
        mid_bus = bms.get("midBusVolt", 0)
        grid_line = bms.get("gridLineVol", 0)
        inv_line = bms.get("invLineVol", 0)

        print_kv("Grid Feed (L1/L2)", f"{gv1} V  |  {gv2} V")
        print_kv("Inv Bus (L1/L2)", f"{iv1} V  |  {iv2} V")
        print_kv("DC Bus (+/−)", f"{pos_bus} V  |  {neg_bus} V")
        print_kv("PE Bat / Mid Bus", f"{pe_bat} V  |  {mid_bus} V")
        print_kv("Grid Line Voltage", f"{grid_line} V")
        print_kv("Inv Line Voltage", f"{inv_line} V")

        # Full grid voltages (AN/BN)
        gv_an = bms.get("gridVoltAN", 0)
        gv_bn = bms.get("gridVoltBN", 0)
        sv_an = bms.get("solarVoltAN", 0)
        sv_bn = bms.get("solarVoltBN", 0)
        if gv_an or gv_bn:
            print_kv("Grid (A-N / B-N)", f"{gv_an} V  |  {gv_bn} V")
        if sv_an or sv_bn:
            print_kv("Solar (A-N / B-N)", f"{sv_an} V  |  {sv_bn} V")

        # ── Hardware States ──────────────────────────────────────
        print_section("🔧", "Hardware States")
        print_kv("BMS Status", str(bms.get("bmsState", "?")))
        print_kv("MOS State", str(bms.get("mosState", "?")))
        print_kv("Inverter Status", str(bms.get("inverterStatus", "?")))
        print_kv("DCDC Status", str(bms.get("DCDCStatus", "?")))
        print_kv("Run Mode", str(bms.get("runMode", "?")))

        # ── Safety Indicators ────────────────────────────────────
        print_section("🛡️", "Safety Indicators")
        alarm = bms.get("alarmLevel", 0)
        alarm_color = "green" if alarm == 0 else "red"
        print_kv("Alarm Level", c(alarm_color, str(alarm)))
        print_kv("Switch State", str(bms.get("switchState", "?")))

        fan = bms.get("fanState", 0)
        fan_str = c("green", "Active") if fan else c("dim", "Idle")
        print_kv("Fan State", fan_str)

        heat = bms.get("heatState", 0)
        heat_str = c("yellow", "On") if heat else c("dim", "Off")
        print_kv("Heating", heat_str)

    if json_output:
        output = {
            "system": {
                "total_capacity_kwh": total_cap,
                "units_online": len(apower_list),
            },
            "batteries": all_bms,
        }
        print_json_output(output)
    else:
        print()
