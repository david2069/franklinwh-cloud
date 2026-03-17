"""Mode command — get/set operating mode."""

from franklinwh_cloud.cli_output import (
    print_header, print_section, print_kv, print_json_output, print_warning,
    c,
)
from franklinwh_cloud.const import OPERATING_MODES, MODE_MAP


async def run(client, *, json_output: bool = False, set_mode: str | None = None,
              soc: int | None = None):
    """Execute the mode command."""

    if set_mode:
        # Setting a mode
        mode_val = None
        # Try by name
        for k, v in MODE_MAP.items():
            if set_mode.lower() in k.lower():
                mode_val = v
                break
        # Try by number
        if mode_val is None:
            try:
                mode_val = int(set_mode)
            except ValueError:
                print_warning(f"Unknown mode: {set_mode}")
                print(f"  Available modes: {', '.join(MODE_MAP.keys())}")
                return

        kwargs = {"mode": mode_val}
        if soc is not None:
            kwargs["soc"] = soc

        print(f"Setting mode to {OPERATING_MODES.get(mode_val, set_mode)}...")
        result = await client.set_mode(**kwargs)
        if json_output:
            print_json_output(result)
        else:
            from franklinwh_cloud.cli_output import print_success
            print_success(f"Mode set to {OPERATING_MODES.get(mode_val, set_mode)}")
        return

    # Getting current mode
    mode = await client.get_mode()

    if json_output:
        print_json_output(mode)
        return

    print_header("Operating Mode")

    if isinstance(mode, dict):
        for key, val in mode.items():
            if key.startswith("_"):
                continue
            print_kv(key, val)
    else:
        print_kv("Mode", str(mode))

    # Also show mode info
    print_section("ℹ️ ", "Mode Details")
    try:
        info = await client.get_mode_info()
        if isinstance(info, dict):
            for key, val in info.items():
                if key.startswith("_"):
                    continue
                if isinstance(val, (list, dict)):
                    continue  # skip nested for clean display
                print_kv(key, val)
        elif isinstance(info, list):
            for item in info:
                if isinstance(item, dict):
                    desc = item.get("name", item.get("mode", "?"))
                    print_kv(f"Mode {item.get('workMode', '?')}", desc)
    except Exception as e:
        print_warning(f"Could not retrieve mode details: {e}")

    print()
