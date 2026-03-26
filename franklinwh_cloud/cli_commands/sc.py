"""Smart Circuits command — Deep integration and device control.

Usage:
    franklinwh-cli sc                      # Detailed list of configuration
    franklinwh-cli sc --on 1               # Turn circuit 1 ON
    franklinwh-cli sc --off 2              # Turn circuit 2 OFF
    franklinwh-cli sc --cutoff 1 --soc 20  # Enable SOC Cutoff at 20% for circuit 1
    franklinwh-cli sc --disable-cutoff 1   # Disable SOC Cutoff for circuit 1
"""

from franklinwh_cloud.cli_output import (
    print_header, print_section, print_kv, print_json_output, c,
)

async def run(client, *, json_output: bool = False, 
              turn_on: int = None, turn_off: int = None,
              cutoff: int = None, disable_cutoff: int = None, soc: int = None,
              load_limit: int = None, amps: int = None):
    """Execute the Smart Circuits command."""

    # Handle Setters
    if turn_on is not None:
        await client.set_smart_circuit_state(turn_on, True)
        if not json_output:
            print_kv("Command", f"Sent Turn ON to Circuit {turn_on}")
    
    if turn_off is not None:
        await client.set_smart_circuit_state(turn_off, False)
        if not json_output:
            print_kv("Command", f"Sent Turn OFF to Circuit {turn_off}")

    if cutoff is not None:
        if soc is None:
            soc = 0  # Default to 0% if omitted but requested enable
        await client.set_smart_circuit_soc_cutoff(cutoff, True, soc)
        if not json_output:
            print_kv("Command", f"Sent SOC Cutoff ENABLE ({soc}%) to Circuit {cutoff}")

    if disable_cutoff is not None:
        await client.set_smart_circuit_soc_cutoff(disable_cutoff, False, 0)
        if not json_output:
            print_kv("Command", f"Sent SOC Cutoff DISABLE to Circuit {disable_cutoff}")

    if load_limit is not None:
        if amps is None:
            print_kv("Error", "--load-limit requires an amperage value (e.g. --amps 30)")
            return
        await client.set_smart_circuit_load_limit(load_limit, amps)
        if not json_output:
            print_kv("Command", f"Sent LOAD LIMIT {amps}A to Circuit {load_limit}")

    if turn_on or turn_off or cutoff or disable_cutoff or load_limit:
        return  # Exit after writing, to avoid printing stale data due to MQTT propagation delay

    # ── Render Lists ───────────────────────────────────────────
    try:
        sc_map = await client.get_smart_circuits()
    except Exception as e:
        if not json_output:
            print_kv("Error", f"Failed to retrieve Smart Circuits payload: {e}")
        return

    if json_output:
        # Convert dataclasses to dicts for JSON
        import dataclasses
        print_json_output({cid: dataclasses.asdict(c) for cid, c in sc_map.items()})
        return

    print_header("Smart Circuits Configuration")

    for i in range(1, 4):
        c_detail = sc_map.get(i)
        if not c_detail:
            continue

        # Skip empty circuit 3 defaults
        if i == 3 and not c_detail.name and c_detail.mode == 0 and c_detail.pro_load_type == 0:
            continue

        c_name = c_detail.name or f"Circuit {i}"
        print_section("🔌", f"{c_name} (SW{i})")
        
        status_str = c("green", "ON") if c_detail.is_on else c("dim", "OFF")
        print_kv("Status", status_str)
        
        if c_detail.soc_cutoff_enabled:
            print_kv("SOC Auto Cut-off", f"{c('green', 'Enabled')} at {c_detail.soc_cutoff_limit}%")
        else:
            print_kv("SOC Auto Cut-off", c("dim", "Disabled"))

        if c_detail.pro_load_type > 0:
            print_kv("Power Supply Plan", f"Type {c_detail.pro_load_type}")
        else:
            print_kv("Power Supply Plan", "No plan")

        if c_detail.load_limit is not None:
            print_kv("Load Constraint", f"{c_detail.load_limit}A limit")
            
        # Parse legacy V1 recurring schedules
        if c_detail.open_time is not None and c_detail.open_time != -1:
            o1, c1 = f"{c_detail.open_time//60:02d}:{c_detail.open_time%60:02d}", f"{c_detail.close_time//60:02d}:{c_detail.close_time%60:02d}"
            print_kv("Schedule 1", f"{o1} → {c1}")
        if c_detail.open_time_2 is not None and c_detail.open_time_2 != -1:
            o2, c2 = f"{c_detail.open_time_2//60:02d}:{c_detail.open_time_2%60:02d}", f"{c_detail.close_time_2//60:02d}:{c_detail.close_time_2%60:02d}"
            print_kv("Schedule 2", f"{o2} → {c2}")

    print()
