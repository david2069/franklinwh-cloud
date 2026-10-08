"""Generator command — configuration and live metrics.

Step C of docs/SMART_CIRCUITS_GENERATOR_DESIGN.md. The generator had SDK
methods and a share of the `accessories` summary, but no command of its own.

Usage:
    franklinwh-cli gen              # config + live metrics
    franklinwh-cli --json gen       # machine-readable

    franklinwh-cli gen --schedule 11:00-23:59
    franklinwh-cli gen --schedule 06:00-09:00 --schedule 17:00-21:00
    franklinwh-cli gen --schedule off          # disable all windows

`--schedule` writes the generator charge windows. Times are **gateway-local
wall clock** — a gateway in another time zone runs them at ITS local time.

`set_generator_mode()` is deliberately NOT exposed: it posts `manuSw`, which
the corpus shows is a manual start/stop command rather than a mode setter
(DEF-GEN-MODE-WRITES-MANUSW).
"""

from franklinwh_cloud.cli_output import (
    c, print_header, print_json_output, print_kv, print_section, print_warning,
)


def _parse_window(spec):
    """``"06:00-09:00"`` -> ``{"start": ..., "end": ..., "enabled": True}``."""
    if "-" not in spec:
        raise ValueError(f"expected START-END, got {spec!r}")
    start, _, end = spec.partition("-")
    return {"start": start.strip(), "end": end.strip(), "enabled": True}


async def _set_schedule(client, specs, json_output, assume_yes):
    """Write the generator charge windows."""
    disable_all = len(specs) == 1 and specs[0].strip().lower() in ("off", "none")
    windows = [] if disable_all else [_parse_window(s) for s in specs]

    if not json_output:
        print_header("Generator — set charge schedule")
        if windows:
            for i, w in enumerate(windows, 1):
                print_kv(f"Window {i}", f'{w["start"]} - {w["end"]}')
        else:
            print_kv("Windows", "all disabled")
        # The single most likely way to get this wrong from another timezone.
        print_warning("Times are the GATEWAY's local wall clock, not yours. "
                      "See docs/TIME_AND_TIMEZONES.md")
        print_warning("This determines when the generator runs.")
        if not assume_yes:
            if input("Proceed? [y/N] ").strip().lower() != "y":
                print("Aborted.")
                return 2

    result = await client.set_generator_charge_schedule(windows, confirm=True)
    if json_output:
        print_json_output({"requested": windows, "result": result})
    else:
        print_kv("Result", str(result))
    return 0


async def run(client, *, json_output: bool = False, schedule=None,
              assume_yes: bool = False):
    """Execute the generator command."""
    if schedule:
        return await _set_schedule(client, schedule, json_output, assume_yes)

    data = await client.get_generator_detail()

    if json_output:
        print_json_output(data)
        return

    print_header("Generator")

    cfg = data.get("config") or {}
    if not cfg:
        print_warning("No generator configuration returned — module may not be "
                      "installed, or the gateway did not answer.")
    else:
        # Field names are as the gateway sends them. The SoC thresholds are
        # genStartElec / genCloseElec — NOT genStartSoc / genStopSoc, which do
        # not exist in the selectIotGenerator response.
        _LABELLED = (
            ("State", "genStat"),
            ("Enabled", "genEn"),
            ("Start below SoC", "genStartElec"),
            ("Stop above SoC", "genCloseElec"),
            ("Rated power", "genRatedPower"),
            ("Model", "genModel"),
            ("Start delay", "startDelTime"),
            ("Alarm", "generatorAlarmFlag"),
        )
        print_section("⚙️", "Configuration")
        for label, key in _LABELLED:
            if key in cfg and cfg[key] not in (None, ""):
                print_kv(label, str(cfg[key]))

        # Charge schedule — three windows, plainly structured. Read-only here;
        # writing them is FEAT-GEN-CHARGE-SCHEDULE.
        windows = []
        for i in (1, 2, 3):
            en = cfg.get(f"charge{i}En")
            if en is None:
                continue
            start = cfg.get(f"charge{i}StartTime", "—")
            end = cfg.get(f"charge{i}EndTime", "—")
            windows.append(f'{i}: {start}-{end} ({"on" if en else "off"})')
        if windows:
            print_section("🕑", "Charge schedule")
            for w in windows:
                print_kv("", w)
            if not any(cfg.get(f"charge{i}En") for i in (1, 2, 3)):
                print_kv("", c("dim", "no window enabled — schedule inactive"))

        # Anything else the gateway returned, rather than silently dropping it.
        _known = {k for _, k in _LABELLED} | {
            f"charge{i}{s}" for i in (1, 2, 3)
            for s in ("En", "StartTime", "EndTime")} | {"result", "opt"}
        extra = {k: v for k, v in cfg.items() if k not in _known}
        if extra:
            print_section("📄", "Other reported fields")
            for k, v in sorted(extra.items()):
                print_kv(k, str(v))

    met = data.get("metrics")
    print_section("📊", "Live metrics")
    if met is None:
        print_warning("Not reported. That is not the same as reading zero — the "
                      "gateway returned no generator block.")
        return

    if met.get("frequency_hz") is not None:
        print_kv("Frequency", f'{met["frequency_hz"]} Hz   (raw {met["frequency"]})')
    print_kv("Power", str(met.get("power")))
    print_kv("Voltage", str(met.get("voltage")))
    print_kv("Current", str(met.get("current")))
    print_kv("", c("dim", met.get("scale", "")))
    # The reader must know these are attributed by position, not by name.
    print_kv("", c("dim", met.get("attribution", "")))
