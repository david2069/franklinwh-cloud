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
    print_warning,
)

async def _render_detail(client, json_output, circuit=None):
    """config + schedule + live metrics, per circuit. Step B."""
    data = await client.get_smart_circuit_detail(circuit)
    if json_output:
        print_json_output(data)
        return

    print_header("Smart Circuits — Detail")
    if not data["source"].get("metrics_available", True):
        print_warning("Live metrics unavailable — showing configuration only.")

    for c_ in data["circuits"]:
        cfg, sch, met = c_["config"], c_["schedule"], c_["metrics"]
        print_section("🔌", f'{c_["name"]}  (circuit {c_["id"]})')
        print_kv("State", c("green", "ON") if cfg["is_on"] else c("dim", "OFF"))
        print_kv("Mode", str(cfg["mode"]))
        if cfg["soc_cutoff_enabled"]:
            print_kv("SoC Cutoff", f'{cfg["soc_cutoff_limit"]}%  (off-grid only)')
        if cfg["load_limit"] is not None:
            print_kv("Load Limit", f'{cfg["load_limit"]} A')

        if met is None:
            # Not reported is not the same as reading zero.
            print_kv("Metrics", c("dim", "not reported for this circuit"))
        else:
            print_kv("Current", f'{met["current"]}')
            print_kv("Voltage", f'{met["voltage"]}')
            print_kv("Power", f'{met["power"]}')
            print_kv("Energy", f'{met["energy"]}')
            print_kv("", c("dim", met["scale"]))

        if sch["slots"]:
            slots = []
            enabled = sch["enabled"] or []
            for idx, raw in enumerate(sch["slots"]):
                # Date retained: '2000-01-01' is the unset sentinel, but a
                # "Once only" schedule carries a real execution date.
                _d, _, _t = str(raw or "").partition(" ")
                hhmm = (_t or "—") if _d in ("", "2000-01-01") else f"{_d} {_t}"
                on = enabled[idx] if idx < len(enabled) else None
                slots.append(f'[{idx}] {hhmm} ({"on" if on else "off"})')
            print_kv("Schedule slots", "  ".join(slots))
            if not any(enabled):
                print_kv("", c("dim", "no slot enabled — schedule inactive"))
            print_kv("", c("dim", "slot pairing unverified; --json for raw values"))
    print()


def _parse_sc_window(spec):
    """``"12:00-12:01"`` -> ``{"start": "12:00", "end": "12:01"}``."""
    text = str(spec).strip()
    sep = "-" if "-" in text else ("–" if "–" in text else None)
    if not sep:
        raise ValueError(f"window must be START-END, e.g. 12:00-13:30 — got {spec!r}")
    start, _, end = text.partition(sep)
    return {"start": start.strip(), "end": end.strip()}


async def _set_schedule(client, circuit, specs, *, cycle_days, base_date,
                        json_output, assume_yes):
    """Write a circuit's time schedule — up to two windows."""
    disable_all = len(specs) == 1 and specs[0].strip().lower() in ("off", "none")
    windows = [] if disable_all else [_parse_sc_window(s) for s in specs]

    if not json_output:
        print_header(f"Smart Circuit {circuit} — set time schedule")
        if windows:
            for i, w in enumerate(windows, 1):
                print_kv(f"Window {i}", f'{w["start"]} - {w["end"]}')
        else:
            print_kv("Windows", "all disarmed (configured times are kept)")
        if cycle_days is not None:
            print_kv("Cycle", "once only" if cycle_days == 0 else f"every {cycle_days} days")
        if base_date:
            print_kv("Base date", base_date)
        # The single most likely way to get this wrong from another timezone.
        print_warning("Times are the GATEWAY's local wall clock, not yours. "
                      "See docs/TIME_AND_TIMEZONES.md")
        print_warning("This determines when the circuit energises.")
        if not assume_yes:
            if input("Proceed? [y/N] ").strip().lower() != "y":
                print("Aborted.")
                return 2

    result = await client.set_smart_circuit_schedule(
        circuit, windows, cycle_days=cycle_days, base_date=base_date,
        confirm=True)

    if json_output:
        print_json_output({"circuit": circuit, "requested": windows,
                           "result": result})
    else:
        # verified is the field that matters; ack only means "accepted".
        verdict = {True: "stored and verified",
                   False: "NOT STORED — the gateway accepted it and discarded it",
                   None: "unverified — could not read back"}[result["verified"]]
        print_kv("Result", verdict)
        for m in result.get("mismatches") or []:
            print_kv("  mismatch", f'{m["field"]}: sent {m["sent"]!r}, '
                                   f'stored {m["stored"]!r}')
    return 0 if result["verified"] is not False else 1


async def run(client, *, json_output: bool = False, 
              turn_on: int = None, turn_off: int = None, schedule: int = None,
              cutoff: int = None, disable_cutoff: int = None, soc: int = None,
              load_limit: int = None, amps: int = None,
              detail: bool = False, detail_circuit: int = None,
              set_schedule: int = None, window=None, cycle_days: int = None,
              base_date: str = None, assume_yes: bool = False):
    """Execute the Smart Circuits command."""

    if set_schedule is not None:
        if not window:
            print_warning("--set-schedule needs at least one --window "
                          "START-END, or --window off to disarm.")
            return 2
        try:
            return await _set_schedule(client, set_schedule, window,
                                       cycle_days=cycle_days, base_date=base_date,
                                       json_output=json_output,
                                       assume_yes=assume_yes)
        except ValueError as e:
            print_warning(str(e))
            return 2

    if detail:
        await _render_detail(client, json_output, detail_circuit)
        return

    # Handle Setters
    if turn_on is not None:
        await client.set_smart_switch_state(turn_on, "ON")
        if not json_output:
            print_kv("Command", f"Sent Turn ON to Circuit {turn_on}")
    
    if turn_off is not None:
        await client.set_smart_switch_state(turn_off, "OFF")
        if not json_output:
            print_kv("Command", f"Sent Turn OFF to Circuit {turn_off}")

    if schedule is not None:
        await client.set_smart_switch_state(schedule, "SCHEDULE")
        if not json_output:
            print_kv("Command", f"Sent SCHEDULE mode to Circuit {schedule}")

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

    if turn_on or turn_off or schedule or cutoff or disable_cutoff or load_limit:
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
            # Off-grid only — it does nothing while grid-tied, so saying only
            # "Enabled" invites the reader to expect action on a healthy grid.
            print_kv("SOC Auto Cut-off",
                     f"{c('green', 'Enabled')} at {c_detail.soc_cutoff_limit}%"
                     f"  {c('dim', '(off-grid only)')}")
        else:
            print_kv("SOC Auto Cut-off", c("dim", "Disabled"))

        if c_detail.pro_load_type > 0:
            print_kv("Power Supply Plan", f"Type {c_detail.pro_load_type}")
        else:
            print_kv("Power Supply Plan", "No plan")

        if c_detail.load_limit is not None:
            print_kv("Load Constraint", f"{c_detail.load_limit}A limit")
            
        # Legacy V1 recurring schedules — minutes-past-midnight integers.
        # Absent on the firmware in the capture corpus, which sends the V2
        # SwNTime arrays below instead.
        if c_detail.open_time is not None and c_detail.open_time != -1:
            o1, c1 = f"{c_detail.open_time//60:02d}:{c_detail.open_time%60:02d}", f"{c_detail.close_time//60:02d}:{c_detail.close_time%60:02d}"
            print_kv("Schedule 1", f"{o1} → {c1}")
        if c_detail.open_time_2 is not None and c_detail.open_time_2 != -1:
            o2, c2 = f"{c_detail.open_time_2//60:02d}:{c_detail.open_time_2%60:02d}", f"{c_detail.close_time_2//60:02d}:{c_detail.close_time_2%60:02d}"
            print_kv("Schedule 2", f"{o2} → {c2}")

        # V2 schedules. Parsed into the model and emitted by --json, but never
        # rendered here — so on firmware that sends these instead of the V1
        # integers, `sc` showed no schedule at all.
        # DEF-SC-SCHEDULE-NOT-RENDERED.
        #
        # AP-14: the ARRAY PAIRING IS NOT ESTABLISHED. SwNTime holds four
        # datetime strings and SwNTimeEn four flags, but whether those are two
        # start/end windows or four independent entries has never been
        # confirmed — every captured sample is the unconfigured default
        # (00:00 / 23:59, all flags 0). So the entries are listed positionally
        # rather than presented as windows we cannot prove they are.
        if c_detail.time_schedules:
            times = c_detail.time_schedules
            enabled = c_detail.time_enabled or []
            # Date part is a placeholder ('2000-01-01') in every sample; the
            # meaningful component is the wall-clock time.
            shown = []
            for idx, raw in enumerate(times):
                # Date retained: '2000-01-01' is the unset sentinel, but a
                # "Once only" schedule carries a real execution date.
                _d, _, _t = str(raw or "").partition(" ")
                hhmm = (_t or "—") if _d in ("", "2000-01-01") else f"{_d} {_t}"
                flag = enabled[idx] if idx < len(enabled) else None
                mark = "on" if flag else "off"
                shown.append(f"[{idx}] {hhmm} ({mark})")
            print_kv("Schedule slots", "  ".join(shown))
            if not any(enabled):
                print_kv("", c("dim", "no slot enabled — schedule inactive"))
            print_kv("", c("dim", "slot pairing unverified; see --json for raw values"))

    print()
