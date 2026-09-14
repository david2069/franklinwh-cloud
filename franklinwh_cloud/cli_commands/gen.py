"""Generator command — configuration and live metrics.

Step C of docs/SMART_CIRCUITS_GENERATOR_DESIGN.md. The generator had SDK
methods and a share of the `accessories` summary, but no command of its own.

Usage:
    franklinwh-cli gen              # config + live metrics
    franklinwh-cli --json gen       # machine-readable

Read-only. `set_generator_mode()` exists in the SDK but is not exposed here —
that is step D and is API-affecting, so it needs sign-off (CLAUDE.md rule 6).
"""

from franklinwh_cloud.cli_output import (
    c, print_header, print_json_output, print_kv, print_section, print_warning,
)


async def run(client, *, json_output: bool = False):
    """Execute the generator command."""
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
