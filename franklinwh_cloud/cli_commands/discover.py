"""Discover command — renders DeviceSnapshot at 3 verbosity tiers.

Tier 1 (default): Site + aGate + battery count + feature flags + state
Tier 2 (-v):      + per-battery firmware + accessories + warranty + programmes
Tier 3 (-vv):     + network + full firmware + TOU + all entrance flags

Feature: FEAT-CLI-DISCOVER-VERBOSE
"""

import json

from franklinwh_cloud.cli_output import (
    print_header, print_section, print_kv, print_json_output, print_warning,
    c,
)


async def run(client, *, json_output: bool = False, tier: int = 1):
    """Execute the discover command."""

    snapshot = await client.discover(tier=tier)

    if json_output:
        print_json_output(snapshot.to_dict())
        return

    tier_names = {1: "High-Level", 2: "Verbose", 3: "Pedantic"}
    print_header(f"FranklinWH Device Discovery — {tier_names.get(tier, 'Unknown')}")

    # ── Always: Site Identity ─────────────────────────────────────
    _render_site(snapshot)
    _render_agate(snapshot)
    _render_batteries_summary(snapshot)
    _render_flags(snapshot)
    _render_state(snapshot)

    if tier >= 2:
        _render_batteries_detail(snapshot)
        _render_accessories(snapshot)
        _render_grid(snapshot)
        _render_warranty(snapshot)
        _render_programmes(snapshot)
        _render_electrical(snapshot)

    if tier >= 3:
        _render_firmware(snapshot)

    # Always: What's missing
    _render_whats_missing(snapshot)

    print()


# ── Renderers ─────────────────────────────────────────────────────

def _render_site(snap):
    """Render site identity."""
    print_section("📍", "Site")
    s = snap.site
    if s.gateway_name:
        print_kv("Name", s.gateway_name)
    if s.address:
        print_kv("Address", s.address)
    if s.country:
        loc_parts = [s.province, s.country] if s.province else [s.country]
        print_kv("Location", ", ".join(loc_parts))
    if s.postcode:
        print_kv("Postcode", s.postcode)
    if s.latitude and s.longitude:
        print_kv("Coordinates", f"{s.latitude:.6f}, {s.longitude:.6f}")
    if s.timezone:
        print_kv("Timezone", s.timezone)
    if s.pto_date:
        print_kv("PTO Date", s.pto_date)
    if s.electric_company:
        print_kv("Utility", s.electric_company)
    if s.tariff_name:
        print_kv("Tariff", s.tariff_name)


def _render_agate(snap):
    """Render aGate identity."""
    print_section("🏠", "aGate")
    a = snap.agate
    if a.model:
        print_kv("Model", f"{a.model_name} — {a.model}")
    if a.sku:
        print_kv("SKU", a.sku)
    if a.serial:
        print_kv("Serial", a.serial)
    if a.generation:
        print_kv("Generation", f"Gen {a.generation}")
    if a.hw_version_str:
        print_kv("Hardware", a.hw_version_str)
    if a.firmware:
        print_kv("Firmware", a.firmware)
    if a.protocol_ver:
        print_kv("Protocol", a.protocol_ver)
    if a.conn_type_name:
        print_kv("Network", a.conn_type_name)
    if a.sim_status_name and a.sim_status > 0:
        print_kv("SIM Card", a.sim_status_name)
    if a.device_time:
        print_kv("Device Time", a.device_time)
    # Timestamps
    if a.activated:
        print_kv("Activated", a.activated)
    if a.installed:
        print_kv("Installed", a.installed)
    if a.created:
        print_kv("Created", a.created)


def _render_batteries_summary(snap):
    """Render battery summary (Tier 1)."""
    b = snap.batteries
    print_section("🔋", f"aPower ({b.count} unit{'s' if b.count != 1 else ''}, {b.total_capacity_kwh} kWh)")
    print_kv("Total Rated Power", f"{b.total_rated_power_kw} kW")
    for unit in b.units:
        sn_short = unit.serial[-6:] if len(unit.serial) > 6 else unit.serial
        cap = f"{unit.rated_capacity_kwh:.1f} kWh" if unit.rated_capacity_kwh else "?"
        pwr = f"{unit.rated_power_kw:.1f} kW" if unit.rated_power_kw else "?"
        print_kv(f"aPower {sn_short}", f"Capacity: {cap}  Power: {pwr}")


def _render_batteries_detail(snap):
    """Render per-battery firmware detail (Tier 2+)."""
    for unit in snap.batteries.units:
        if not unit.fpga_ver:
            continue
        sn_short = unit.serial[-6:] if len(unit.serial) > 6 else unit.serial
        print_section("🔋", f"aPower {sn_short} Detail")
        print_kv("Serial", unit.serial)
        if unit.soc:
            print_kv("SoC", f"{unit.soc}%")
        if unit.remaining_kwh:
            print_kv("Stored Energy", f"{unit.remaining_kwh} kWh")
        if unit.fpga_ver:
            print_kv("FPGA", unit.fpga_ver)
        if unit.dcdc_ver:
            print_kv("DC-DC", unit.dcdc_ver)
        if unit.inv_ver:
            print_kv("Inverter", unit.inv_ver)
        if unit.bms_ver:
            print_kv("BMS", unit.bms_ver)
        if unit.bl_ver:
            print_kv("Bootloader", unit.bl_ver)
        if unit.th_ver:
            print_kv("Thermal", unit.th_ver)
        if unit.mppt_app_ver:
            print_kv("MPPT App", unit.mppt_app_ver)
        if unit.pe_hw_ver:
            print_kv("PE Hardware", f"v{unit.pe_hw_ver}")


def _render_flags(snap):
    """Render feature flags table."""
    f = snap.flags
    print_section("🏷️", "Feature Flags")

    flags = [
        ("Solar", f.solar, f.solar_detail or ("Installed" if f.solar else "Not detected")),
        ("TOU/Tariff", f.tariff_configured, "Configured" if f.tariff_configured else "Not configured"),
        ("PCS Power Control", f.pcs_enabled, "Enabled" if f.pcs_enabled else "Disabled"),
    ]

    # Off-grid — differentiate 3 sources
    if f.off_grid_simulated:
        og_detail = "Simulated (grid contactor opened)"
    elif f.off_grid_permanent:
        og_detail = "Permanent (no utility service)"
    elif f.off_grid:
        og_detail = f"Grid outage detected (reason: {f.off_grid_reason})"
    else:
        og_detail = "Grid-connected"
    flags.append(("Off-Grid", f.off_grid, og_detail))

    flags.extend([
        ("MPPT (DC-coupled)", f.mppt_enabled, "Enabled" if f.mppt_enabled else "Not available"),
        ("Three Phase", f.three_phase, "Three-phase" if f.three_phase else "Single-phase"),
        ("CT Split — Grid", f.ct_split_grid, "Installed" if f.ct_split_grid else "Not installed"),
        ("CT Split — PV", f.ct_split_pv, "Installed" if f.ct_split_pv else "Not installed"),
    ])

    # Accessory flags
    sc = snap.accessories.smart_circuits
    if sc:
        sc_label = f"V{sc.version}, {sc.count} circuits"
        if sc.names and any(sc.names):
            sc_label += f" ({', '.join(n for n in sc.names if n)})"
        flags.append(("Smart Circuits", True, sc_label))
    else:
        flags.append(("Smart Circuits", snap.accessories.has_smart_circuits,
                       "Installed" if snap.accessories.has_smart_circuits else "Not installed"))

    flags.extend([
        ("V2L", f.v2l_enabled or f.v2l_eligible,
         f.v2l_note if f.v2l_note else ("Enabled" if f.v2l_enabled else "Not enabled")),
        ("Generator Module", f.generator_enabled or snap.accessories.has_generator,
         "Installed" if (f.generator_enabled or snap.accessories.has_generator) else "Not installed"),
        ("Remote Solar (aPBox)", f.remote_solar, "Connected" if f.remote_solar else "Not connected"),
        ("aHub", f.ahub_detected, "Detected" if f.ahub_detected else "Not detected"),
    ])

    # US-only accessory flags
    is_us = snap.site.country_id == 2
    if is_us:
        flags.append(("MAC-1 (MSA)", f.mac1_detected,
                       "Detected" if f.mac1_detected else "Not detected"))

    # Programme flags (region-filtered)
    if is_us:
        flags.extend([
            ("NEM Type", bool(f.nem_type), f.nem_type or "—"),
            ("SGIP (CA)", f.sgip, "Enrolled" if f.sgip else "Not enrolled"),
            ("BB (Hawaii)", f.bb, "Enrolled" if f.bb else "Not enrolled"),
            ("JA12 (CA)", f.ja12, "Enrolled" if f.ja12 else "Not applicable"),
        ])
    flags.append(("VPP Programme", f.vpp_enrolled,
                   "Enrolled" if f.vpp_enrolled else "Not enrolled"))

    for name, enabled, detail in flags:
        icon = c("green", "✅") if enabled else c("dim", "❌")
        print_kv(f"  {icon} {name}", detail)


def _render_state(snap):
    """Render operating state."""
    e = snap.electrical
    print_section("⚡", "Operating State")
    print_kv("Mode", f"{e.operating_mode_name}")
    print_kv("SoC", f"{e.soc}%")
    print_kv("Status", e.run_status_name)
    grid_state = c("green", "Connected") if snap.grid.connected else c("red", "Off-Grid")
    print_kv("Grid", grid_state)
    phase = "Three-phase" if snap.flags.three_phase else "Single-phase"
    print_kv("Phase", phase)


def _render_accessories(snap):
    """Render accessories detail (Tier 2+)."""
    acc = snap.accessories
    if not acc.items and not acc.has_smart_circuits:
        return
    print_section("🔌", f"Accessories ({len(acc.items)} registered)")
    from franklinwh_cloud.mixins.discover import get_catalog
    catalog = get_catalog()
    for item in acc.items:
        # Look up model/SKU from catalog by type
        model_info = ""
        for acc_id, acc_data in catalog.get("accessories", {}).items():
            if acc_data.get("type") == item.type_name and acc_data.get("country_id") == snap.site.country_id:
                model_info = f"  Model: {acc_data.get('name', '')}  SKU: {acc_data.get('sku', '')}"
                break
        print_kv(item.name, f"SN: {item.serial}{model_info}")

    sc = acc.smart_circuits
    if sc:
        print_section("🔌", "Smart Circuits Configuration")
        print_kv("Version", f"V{sc.version}")
        print_kv("Circuits", str(sc.count))
        if sc.merged:
            print_kv("Merged", c("yellow", "SC1+SC2 merged (240V)"))
        for i, name in enumerate(sc.names):
            if name:
                print_kv(f"SC{i+1} Name", name)
        v2l = c("green", "Available") if sc.v2l_port else c("dim", "Not available")
        print_kv("V2L Port", v2l)

    if acc.has_apbox:
        print_section("🔌", "aPBox Digital I/O")
        if acc.apbox_di:
            print_kv("Digital Inputs", str(acc.apbox_di))
        if acc.apbox_do_status:
            print_kv("Digital Outputs", str(acc.apbox_do_status))


def _render_grid(snap):
    """Render grid limits (Tier 2+)."""
    g = snap.grid
    if not g.pcs_entrance:
        return
    print_section("⚡", "Grid Limits")
    if g.global_discharge_max_kw:
        print_kv("Export Limit", f"{g.global_discharge_max_kw} kW")
    if g.global_charge_max_kw:
        print_kv("Import Limit", f"{g.global_charge_max_kw} kW")
    if g.feed_max_kw:
        print_kv("Feed-in Max", f"{g.feed_max_kw} kW")
    if g.import_max_kw:
        print_kv("Import Max", f"{g.import_max_kw} kW")
    if g.peak_demand_max_kw:
        print_kv("Peak Demand", f"{g.peak_demand_max_kw} kW")


def _render_warranty(snap):
    """Render warranty info (Tier 2+)."""
    w = snap.warranty
    if not w.expiry:
        return
    print_section("📋", "Warranty")
    print_kv("Expires", w.expiry)
    if w.throughput_mwh:
        remaining_pct = round((w.remaining_kwh / (w.throughput_mwh * 1000)) * 100) if w.throughput_mwh else 0
        print_kv("Throughput", f"{w.throughput_mwh} MWh warranted")
        print_kv("Remaining", f"{w.remaining_kwh:.0f} kWh ({remaining_pct}%)")
    if w.installer_company:
        print_kv("Installer", w.installer_company)
    if w.installer_phone:
        print_kv("Installer Phone", w.installer_phone)
    for dev in w.devices:
        sn_short = dev.serial[-6:] if len(dev.serial) > 6 else dev.serial
        exp_str = dev.expiry
        if dev.sub_module_expiry:
            exp_str += f"  (sub-module: {dev.sub_module_expiry})"
        print_kv(f"{dev.model} {sn_short}", f"Expires: {exp_str}")


def _render_programmes(snap):
    """Render programme info (Tier 2+)."""
    p = snap.programmes
    if not p.enrolled:
        return
    print_section("📋", "Programmes")
    if p.program_name:
        print_kv("Programme", p.program_name)
    if p.partner_name:
        print_kv("Partner", p.partner_name)
    print_kv("VPP SoC", f"{p.vpp_soc}% (min: {p.vpp_min_soc}%, max: {p.vpp_max_soc}%)")


def _render_electrical(snap):
    """Render electrical measurements (Tier 2+)."""
    e = snap.electrical
    has_voltage = e.v_l1 is not None
    if not has_voltage and not e.relays:
        return
    # AU/NZ aGates are single-phase but API assumes split-phase
    is_single_phase = not snap.flags.three_phase
    is_au = snap.site.country_id == 3
    if has_voltage:
        print_section("🔌", "Electrical")
        if e.v_l1 is not None:
            label = "Voltage" if (is_au and is_single_phase) else "L1 Voltage"
            print_kv(label, f"{e.v_l1} V")
        if e.i_l1 is not None:
            label = "Current" if (is_au and is_single_phase) else "L1 Current"
            print_kv(label, f"{e.i_l1} A")
        # Only show L2 for split-phase (US) systems, not AU single-phase
        if not (is_au and is_single_phase):
            if e.v_l2 is not None and float(e.v_l2) > 0:
                print_kv("L2 Voltage", f"{e.v_l2} V")
            if e.i_l2 is not None and float(e.i_l2) > 0:
                print_kv("L2 Current", f"{e.i_l2} A")
        if e.frequency is not None:
            print_kv("Frequency", f"{e.frequency} Hz")
    # Always show relays
    if e.relays:
        print_section("🔧", "Relays")
        relay_labels = {
            "grid_1": "Grid Relay 1",
            "generator": "Generator Relay",
            "solar_pv_1": "Solar PV Relay 1",
            "grid_2": "Grid Relay 2",
            "black_start": "Black Start Relay",
            "solar_pv_2": "Solar PV Relay 2",
            "apbox": "aPBox Relay",
        }
        for key, state in e.relays.items():
            label = relay_labels.get(key, key)
            icon = c("green", "ON") if state else c("dim", "OFF")
            print_kv(label, icon)


def _render_firmware(snap):
    """Render full firmware detail (Tier 3)."""
    a = snap.agate
    if not a.ibg_version:
        return
    print_section("🔧", "aGate Firmware")
    fw_fields = [
        ("IBG (Inverter)", a.ibg_version),
        ("SL (Safety/Logic)", a.sl_version),
        ("AWS (Cloud Comms)", a.aws_version),
        ("App", a.app_version),
        ("Meter", a.meter_version),
    ]
    for label, ver in fw_fields:
        if ver:
            print_kv(label, ver)
    if a.msa_model:
        print_kv("MAC-1 Model", a.msa_model)
    if a.msa_serial:
        print_kv("MAC-1 Serial", a.msa_serial)


def _render_whats_missing(snap):
    """Render system readiness and diagnostics."""
    e = snap.electrical
    f = snap.flags
    from franklinwh_cloud.const import AGATE_STATE

    # ── System Readiness ──────────────────────────────────────────
    readiness = []

    # aGate status
    agate_ok = e.device_status == 1
    agate_label = AGATE_STATE.get(e.device_status, f"Unknown ({e.device_status})")
    readiness.append(("aGate", agate_ok, agate_label))

    # aPower status
    bat_ok = snap.batteries.count > 0 and e.soc > 0
    bat_label = f"{snap.batteries.count} unit(s), SoC {e.soc}%"
    if e.run_status in (0, 5):
        bat_label += f" — {e.run_status_name}"
    readiness.append(("aPower", bat_ok, bat_label))

    # PCS (power control)
    pcs_label = "Enabled" if f.pcs_enabled else "Not configured"
    readiness.append(("PCS Control", f.pcs_enabled, pcs_label))

    # TOU schedule
    tou_ok = f.tariff_configured
    if e.tou_dispatch_count > 0:
        tou_label = f"Active ({e.tou_dispatch_count} dispatch windows)"
    elif tou_ok:
        tou_label = "Configured (no active dispatches)"
    else:
        tou_label = "Not configured — set up tariff in app"
    if e.tou_status and e.tou_status != 0:
        tou_ok = False
        tou_label += f" ⚠ backend status: {e.tou_status}"
    readiness.append(("TOU Schedule", tou_ok, tou_label))

    # Grid
    grid_label = "Connected" if snap.grid.connected else "Off-Grid"
    if f.off_grid_simulated:
        grid_label = "Simulated off-grid (contactor open)"
    elif f.off_grid_permanent:
        grid_label = "Permanent off-grid (no utility)"
    readiness.append(("Grid", snap.grid.connected, grid_label))

    # Solar
    solar_label = f.solar_detail if f.solar_detail else ("Detected" if f.solar else "Not detected")
    readiness.append(("Solar", f.solar, solar_label))

    print_section("🏥", "System Readiness")
    for name, ok, detail in readiness:
        icon = c("green", "✅") if ok else c("yellow", "⚠")
        print_kv(f"  {icon} {name}", detail)

    # ── Informational notes ───────────────────────────────────────
    notes = []
    if f.off_grid:
        notes.append(("⚠", f"System is OFF-GRID (reason: {f.off_grid_reason})"))
    if f.need_ct_test:
        notes.append(("⚠", "CT calibration test required"))
    if f.charging_power_limited:
        notes.append(("⚠", "Charging power currently limited"))
    if not snap.accessories.has_smart_circuits:
        notes.append(("ⓘ", "No Smart Circuits installed"))
    if not snap.accessories.has_generator and not f.generator_enabled:
        notes.append(("ⓘ", "No Generator Module installed"))
    if not f.vpp_enrolled:
        notes.append(("ⓘ", "Not enrolled in VPP programme"))
    if snap.warranty.expiry == "":
        notes.append(("ⓘ", "Warranty info unavailable"))

    if notes:
        print_section("📌", "Notes")
        for icon, msg in notes:
            print_kv(icon, msg)

