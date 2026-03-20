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
        # Include SoC summary in JSON output
        try:
            soc_summary = await client.get_all_mode_soc()
        except Exception:
            soc_summary = None
        output = mode if isinstance(mode, dict) else {"mode": mode}
        if soc_summary:
            output["soc_summary"] = soc_summary
        print_json_output(output)
        return

    print_header("Operating Mode")

    if isinstance(mode, dict):
        # Display key fields in a structured, readable format
        print_section("⚡", "Current Mode")
        print_kv("Mode", c("bold", str(mode.get("modeName", mode.get("name", "?")))))
        print_kv("Run Status", mode.get("run_desc", "?"))

        # Reserve SoC for the active mode
        active_soc = mode.get("soc")
        min_soc = mode.get("minSoc")
        max_soc = mode.get("maxSoc")
        if active_soc is not None:
            soc_range = f"  (range: {min_soc}–{max_soc}%)" if min_soc is not None else ""
            print_kv("Reserve SoC", f"{active_soc}%{soc_range}")

        # Device & system health
        print_section("📡", "System")
        device_status = mode.get("deviceStatus")
        if device_status is not None:
            status_text = c("green", "Normal") if str(device_status) == "1" else c("yellow", f"Status {device_status}")
            print_kv("Device Status", status_text)
        if mode.get("alarmsCount"):
            print_kv("Active Alarms", c("red", str(mode["alarmsCount"])))
        else:
            print_kv("Active Alarms", c("green", "0"))
        if mode.get("unreadMsgCount"):
            print_kv("Unread Messages", mode["unreadMsgCount"])
        offgrid = mode.get("offgridState", 0)
        if offgrid:
            print_kv("Off-Grid State", c("yellow", str(offgrid)))

        # TOU-specific info
        if mode.get("touScheduleList"):
            print_section("📅", "Active TOU Schedule")
            sched = mode["touScheduleList"]
            if isinstance(sched, dict):
                current = sched.get("current")
                if current:
                    print_kv("Current Block", f"{current.get('startHourTime', '?')}–{current.get('endHourTime', '?')}  {current.get('dispatchName', '')}")
                next_block = sched.get("next")
                if next_block:
                    remaining = sched.get("remaining", "")
                    print_kv("Next Block", f"{next_block.get('startHourTime', '?')}–{next_block.get('endHourTime', '?')}  {next_block.get('dispatchName', '')}  ({remaining})")

        # Emergency backup info
        if mode.get("backupForeverFlag"):
            print_section("🛡️", "Emergency Backup")
            flag = mode["backupForeverFlag"]
            print_kv("Duration", "Indefinite" if str(flag) == "1" else "Fixed timer")
            if mode.get("nextWorkMode"):
                next_name = OPERATING_MODES.get(int(mode["nextWorkMode"]), f"Mode {mode['nextWorkMode']}")
                print_kv("Next Mode", next_name)
    else:
        print_kv("Mode", str(mode))

    # SoC summary for ALL modes
    print_section("🔋", "Reserve SoC — All Modes")
    try:
        all_soc = await client.get_all_mode_soc()
        for entry in all_soc:
            name = entry["name"]
            soc_val = entry["soc"]
            min_s = entry.get("minSoc", "?")
            max_s = entry.get("maxSoc", "?")
            active = entry.get("active", False)
            marker = c("green", " ← active") if active else ""
            editable = "" if entry.get("editSocFlag") else c("dim", " (fixed)")
            print_kv(name, f"{soc_val}%  (range: {min_s}–{max_s}%){editable}{marker}")
    except Exception as e:
        print_warning(f"Could not retrieve SoC summary: {e}")

    print()
