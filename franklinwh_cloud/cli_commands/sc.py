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
              cutoff: int = None, disable_cutoff: int = None, soc: int = None):
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

    if turn_on or turn_off or cutoff or disable_cutoff:
        return  # Exit after writing, to avoid printing stale data due to MQTT propagation delay

    # ── Render Lists ───────────────────────────────────────────
    try:
        sc_info = await client.get_smart_circuits_info()
    except Exception as e:
        if not json_output:
            print_kv("Error", f"Failed to retrieve Smart Circuits payload: {e}")
        return

    if json_output:
        print_json_output(sc_info)
        return

    print_header("Smart Circuits Configuration")

    for i in range(1, 4):
        name = sc_info.get(f"Sw{i}Name")
        mode = sc_info.get(f"Sw{i}Mode", 0)
        cutoff_en = sc_info.get(f"Sw{i}AtuoEn", 0)
        cutoff_soc = sc_info.get(f"Sw{i}SocLowSet", 0)
        pro_load = sc_info.get(f"Sw{i}ProLoad", 0)

        # Skip empty circuit 3
        if i == 3 and not name and mode == 0 and pro_load == 0:
            continue

        c_name = name or f"Circuit {i}"
        print_section("🔌", f"{c_name} (SW{i})")
        
        status_str = c("green", "ON") if mode == 1 else c("dim", "OFF")
        print_kv("Status", status_str)
        
        if cutoff_en == 1:
            print_kv("SOC Auto Cut-off", f"{c('green', 'Enabled')} at {cutoff_soc}%")
        else:
            print_kv("SOC Auto Cut-off", c("dim", "Disabled"))

        if pro_load > 0:
            print_kv("Power Supply Plan", f"Type {pro_load}")
        else:
            print_kv("Power Supply Plan", "No plan")

    print()
