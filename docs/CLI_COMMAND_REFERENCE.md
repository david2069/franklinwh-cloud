# CLI Command Reference

Every `franklinwh-cli` command and option on one page. The tables are generated from
the CLI's own definitions (`scripts/gen_cli_reference.py`), so they match the
installed version. Commands with a detailed guide link to it.

Credentials come from `franklinwh.ini` in the current folder, `--config PATH`, or the
`FRANKLIN_USERNAME` / `FRANKLIN_PASSWORD` environment variables. See
[Sandbox Setup](SANDBOX_SETUP.md).

> ⚠️ Some commands **change** the real system: `mode --set`, `tou --set`, `sc --on/--off`,
> `gen --schedule` and `network set-wifi`. Several of them ask for confirmation, but
> `mode --set` doesn't, so check what a command will do before running it.

<!-- BEGIN GENERATED: cli commands -->
## Global options

These go before or after the command (e.g. `franklinwh-cli --json status` or `franklinwh-cli status --json`).

| Option | Value | Default | Description |
|---|---|---|---|
| `--version` | flag | — | show program's version number and exit |
| `--config`, `-c` | `PATH` | — | Path to franklinwh.ini config file |
| `--email`, `-e` | `EMAIL` | — | FranklinWH account email |
| `--password`, `-p` | `PASS` | — | FranklinWH account password |
| `--gateway`, `-g` | `SN` | — | aGate serial number |
| `--installer` | flag | — | Use installer account login (LOGIN_TYPE_INSTALLER). Default: homeowner account |
| `--json`, `-j` | flag | — | Output as JSON |
| `--no-color` | flag | — | Disable ANSI colour output |
| `-v`, `--verbose` | flag | — | Increase verbosity (-v info, -vv debug, -vvv trace) |
| `--trace` | `MODULES` | — | Enable debug for specific modules (comma-sep: stats,modes,tou,storm,power,devices,account,client,all) |
| `--api-trace` | flag | — | Show per-call API trace with timing |
| `--log-file` | `PATH` | — | Write debug output to file |

## Commands

| Command | Aliases | What it does | Guide |
|---|---|---|---|
| [`status`](#status) | `st` | Live system overview (power, SOC, mode, weather, metrics) | — |
| [`discover`](#discover) | `disc` | Gateway, device, warranty, and accessory enumeration | — |
| [`mode`](#mode) | — | Get or set operating mode | — |
| [`tou`](#tou) | — | Time-of-Use schedule inspection and control | [guide](CLI_TOU_COMMAND.md) |
| [`energy`](#energy) | — | Energy (kWh) and 5-minute power (kW) history — table, JSON or CSV | [guide](cli-energy.md) |
| [`raw`](#raw) | — | Direct API method passthrough | [guide](cli-raw.md) |
| [`metrics`](#metrics) | — | Show API call metrics from current session | — |
| [`monitor`](#monitor) | `mon` | Real-time battery dashboard (auto-refresh, Ctrl+C to exit) | — |
| [`accessories`](#accessories) | `acc` | Accessory inventory, status, and device info (Smart Circuits, V2L, Generator) | — |
| [`sc`](#sc) | `smart-circuits` | Detailed Smart Circuit configuration and control | — |
| [`gen`](#gen) | `generator` | Generator module configuration and live metrics | — |
| [`network`](#network) | `net` | Inspect the aGate's connection, or put it back on WiFi | — |
| [`diag`](#diag) | `diagnostic` | Diagnostic report — system, auth, device, power, API health | — |
| [`bms`](#bms) | `battery` | Battery Management System — cell telemetry, pack health, bus topology | — |
| [`support`](#support) | `snapshot` | System snapshot for troubleshooting — export, redact, compare | [guide](CLI_SUPPORT_INFO.md) |
| [`schema`](#schema) | — | Show Current/Totals field schema — Python attr → raw API key mapping | [guide](CLI_SCHEMA_COMMAND.md) |
| [`fetch`](#fetch) | — | Arbitrary GET/POST to any API endpoint | — |

### status

Live system overview (power, SOC, mode, weather, metrics).

```
franklinwh-cli status [options]
```

No options.

### discover

Gateway, device, warranty, and accessory enumeration.

```
franklinwh-cli discover [options]
```

| Option | Value | Default | Description |
|---|---|---|---|
| `-v`, `--verbose` | flag | — | Verbosity: -v (medium), -vv (pedantic) |

### mode

Get or set operating mode.

```
franklinwh-cli mode [options]
```

| Option | Value | Default | Description |
|---|---|---|---|
| `--set` | `MODE` | — | Set mode (tou, self_consumption, emergency_backup, or 1/2/3) |
| `--soc` | `PCT` | — | Set SOC percentage (used with --set) |
| `--duration` | `MINS` | — | Duration in minutes for Emergency Backup mode (0 for indefinite, min 30) |
| `--resume-mode` | `MODE` | — | Mode to switch to after duration expires (tou or self_consumption) |

### tou

Time-of-Use schedule inspection and control.

```
franklinwh-cli tou [options]
```

Detailed guide: [CLI_TOU_COMMAND.md](CLI_TOU_COMMAND.md)

| Option | Value | Default | Description |
|---|---|---|---|
| `--dispatch` | flag | — | Show full dispatch detail including strategies |
| `--set` | `MODE` | — | Set TOU dispatch (GRID_CHARGE, GRID_EXPORT, SELF, HOME, STANDBY, SOLAR, CUSTOM) |
| `--start` | `HH:MM` | — | Start time for --set window (e.g. 11:30) |
| `--end` | `HH:MM` | — | End time for --set window (e.g. 14:30) |
| `--default` | `MODE` | — | Dispatch mode for times outside --start/--end (required with --start/--end) |
| `--active-only` | flag | — | Truncate --price output to only active exchange rates (ideal for scripts) |
| `--file` | `PATH` | — | JSON schedule file for --set CUSTOM |
| `--rates-file` | `PATH` | — | JSON file with pricing rates (peak, off_peak, sell_peak, ...) |
| `--season` | `NAME` | — | Season name for explicit override (e.g. 'Summer'). Use with --months. |
| `--months` | `M,M,...` | — | Comma-separated months for explicit --season override (e.g. '10,11,12,1,2,3') |
| `--month` | `1-12` | — | Target month for --set (default: current month). Updates the season that owns this month, leaving all others untouched. |
| `--day-type` | `everyday\|weekday\|weekend` | — | Day type: everyday (default), weekday, weekend |
| `--next` | flag | — | Show current and next dispatch with remaining time |
| `--price` | flag | — | Show the current TOU pricing tier, wave type, and rates |
| `--all` | flag | — | Show all pricing tiers instead of just the active one |
| `--extended` | flag | — | Always show extended columns (e.g. SoC limits) even if empty |
| `--current` | flag | — | Only show the active season's schedule. |
| `--multi-season` | `FILE` | — | Load and apply a multi-season/multi-day-type schedule from JSON file |
| `--wait` | flag | — | Supervised dispatch: backup current schedule, apply --set, confirm delivery, hold until Ctrl+C, then restore original. |
| `--restore` | flag | — | Manually restore the most recent unrestored TOU backup for this gateway. |

### energy

Energy (kWh) and 5-minute power (kW) history — table, JSON or CSV.

```
franklinwh-cli energy [options]
```

Detailed guide: [cli-energy.md](cli-energy.md)

| Option | Value | Default | Description |
|---|---|---|---|
| `--period` | `day\|week\|month\|year\|ytd\|lifetime` | `day` | Period to fetch (default: day) |
| `--date` | `YYYY-MM-DD` | — | Any date inside the period; snapped to its start (week → Monday, month → 1st, year → Jan 1). Default: today |
| `--format` | `table\|json\|csv` | `table` | Output format (default: table). Global --json means --format json |
| `--output`, `-o` | `PATH` | — | Write to a file instead of stdout |
| `--interval` | `5min` | — | With --period day: 288 five-minute power samples (kW) instead of the daily kWh total |
| `--all-fields` | flag | — | Include every array the API returns (see --describe for names and meanings) |
| `--describe` | flag | — | Print the field dictionary (column, API key, unit, evidence) and exit — no login |

### raw

Direct API method passthrough.

```
franklinwh-cli raw [options]
```

Detailed guide: [cli-raw.md](cli-raw.md)

| Option | Value | Default | Description |
|---|---|---|---|
| `method` (positional) | `METHOD` | `help` | API method name (use 'help' to list all) |
| `values` (positional) | `VALUES` | — | Arguments to pass to the method |
| `--headers`, `-H` | flag | — | Show HTTP response headers |
| `--timings`, `-T` | flag | — | Show request timing and CloudFront edge info |
| `--validate-schema` | flag | — | Cross-reference payload against docs/franklinwh_openapi.json (Diagnostic only) |

### metrics

Show API call metrics from current session.

```
franklinwh-cli metrics [options]
```

No options.

### monitor

Real-time battery dashboard (auto-refresh, Ctrl+C to exit).

```
franklinwh-cli monitor [options]
```

| Option | Value | Default | Description |
|---|---|---|---|
| `-i`, `--interval` | `SECS` | `30` | Refresh interval in seconds (default: 30) |
| `-d`, `--duration` | `MINS` | — | Run for N minutes then stop (default: until Ctrl+C) |
| `--compact` | flag | — | Single-line output per poll (no screen clearing) |

### accessories

Accessory inventory, status, and device info (Smart Circuits, V2L, Generator).

```
franklinwh-cli accessories [options]
```

| Option | Value | Default | Description |
|---|---|---|---|
| `--power` | flag | — | Include live power data for active accessories (extra MQTT call) |

### sc

Detailed Smart Circuit configuration and control.

```
franklinwh-cli sc [options]
```

| Option | Value | Default | Description |
|---|---|---|---|
| `--on` | `CIRCUIT` | — | Turn Circuit 1/2/3 ON |
| `--off` | `CIRCUIT` | — | Turn Circuit 1/2/3 OFF |
| `--schedule` | `CIRCUIT` | — | Write SwNMode=2 ("Schedule mode"). The app does send this value when scheduling, though it has never been seen in a read — the firmware appears to normalise it. Use --set-schedule to write the schedule itself. |
| `--set-schedule` | `CIRCUIT` | — | Write Circuit N's time schedule. Needs --window. |
| `--window` | `START-END` | — | A schedule window in GATEWAY-local time, e.g. 12:00-13:30. Repeat for a second (max two). Use 'off' to disarm without discarding the times. |
| `--cycle-days` | `N` | — | Repeat interval in DAYS for --set-schedule. 0 = once only. Left unchanged if omitted. |
| `--base-date` | `YYYY-MM-DD` | — | Date the schedule counts from (execution date = base + k x cycle). Defaults to each slot's existing date; required if a slot has never been written. |
| `--yes`, `-y` | flag | — | Skip the confirmation prompt for --set-schedule |
| `--cutoff` | `CIRCUIT` | — | Enable SOC auto cut-off for Circuit 1/2/3 |
| `--disable-cutoff` | `CIRCUIT` | — | Disable SOC auto cut-off for Circuit 1/2/3 |
| `--soc` | `PCT` | — | SOC limit (0-100) for --cutoff |
| `--load-limit` | `CIRCUIT` | — | Configure the continuous Load Limit in amps for a specific circuit |
| `--detail` | flag | — | Show configuration, schedule AND live metrics per circuit |
| `--circuit` | `N` | — | With --detail: restrict to one circuit |
| `--amps` | `A` | — | The maximum amperage limit for --load-limit (0 to reset) |

### gen

Generator module configuration and live metrics.

```
franklinwh-cli gen [options]
```

| Option | Value | Default | Description |
|---|---|---|---|
| `--schedule` | `START-END` | — | Set a generator charge window in GATEWAY-local time, e.g. 11:00-23:59. Repeat for up to three. Use 'off' to disable all. |
| `--yes`, `-y` | flag | — | Skip the confirmation prompt |

### network

Inspect the aGate's connection, or put it back on WiFi.

```
franklinwh-cli network [options]
```

No options.

#### network status

What is the aGate connected on?.

| Option | Value | Default | Description |
|---|---|---|---|
| `--watch` | `SECS` | — | Refresh every SECS seconds (default 5) |
| `--probe-local` | flag | — | Also check whether the aGate answers on the LAN (TCP 9000, else 22). Distinguishes 'gateway alive, cloud path broken' from 'gateway down'. Only meaningful from the gateway's own network. |

#### network scan

List visible WiFi networks by signal.

| Option | Value | Default | Description |
|---|---|---|---|
| `--min-rssi` | `PCT` | — | Hide networks below this signal percentage |
| `--scan-time` | `SECS` | `10` | wifi_ScanTime value (default 10) |
| `--all` | flag | — | Include everything, however weak |

#### network set-wifi

Join a WiFi network, or re-assert one the aGate already knows.

| Option | Value | Default | Description |
|---|---|---|---|
| `--ssid` | `SSID` | — | Network to join |
| `--password` | `PASSWORD` | — | Passphrase (visible in shell history) |
| `--use-stored` | flag | — | Reuse the password already on the aGate. Only valid for the SSID it currently stores — which is exactly the case when it has stranded itself on 4G. |
| `--yes`, `-y` | flag | — | Skip the confirmation |
| `--no-verify` | flag | — | Do not poll to confirm the link came up |
| `--timeout` | `SECS` | `180` | Verification deadline (default 180) |
| `--min-rssi` | `PCT` | `30` | Refuse a target weaker than this (default 30) |
| `--allow-no-fallback` | flag | — | DANGEROUS: write even when nothing else could take over if it fails |
| `--allow-weak-signal` | flag | — | Write even if the target is weak or not in the scan |
| `--trust-ethernet` | flag | — | Count an idle Ethernet port as a fallback. Off by default: one aGate port is reserved for FranklinWH-internal use and may hold an address while having no route to the cloud. |

### diag

Diagnostic report — system, auth, device, power, API health.

```
franklinwh-cli diag [options]
```

No options.

### bms

Battery Management System — cell telemetry, pack health, bus topology.

```
franklinwh-cli bms [options]
```

No options.

### support

System snapshot for troubleshooting — export, redact, compare.

```
franklinwh-cli support [options]
```

Detailed guide: [CLI_SUPPORT_INFO.md](CLI_SUPPORT_INFO.md)

| Option | Value | Default | Description |
|---|---|---|---|
| `--info`, `-i` | flag | — | Print full account/site taxonomy tree |
| `--diag`, `-d` | flag | — | With --info: also show full ✅/❌ feature flag diagnostic (implies --info) |
| `--mock`, `-m` | flag | — | Print a simulated max-config --info --diag output (no API calls, demo only) |
| `--save`, `-s` | flag | — | Save snapshot to timestamped JSON file |
| `--redact`, `-r` | `partial\|full` | — | Redact PII (partial=mask, full=remove). Default: partial |
| `--label`, `-l` | `TAG` | — | Label the snapshot (e.g. 'pre-setup', 'post-outage') |
| `--analyze`, `-a` | flag | — | Run connectivity and WiFi health analysis |
| `--compare` | `FILE` | — | Compare current state against a previous snapshot file |
| `--scope` | `all\|network\|software\|power` | `all` | Scope for --compare (default: all) |
| `--nettest`, `-t` | flag | — | Run hop-by-hop network connectivity test |
| `--interval` | `SECS` | — | Repeat nettest every N seconds (0=single run) |
| `--duration` | `SECS` | — | Total duration for interval testing (0=until Ctrl+C) |
| `--record` | `FILE` | — | Save nettest results to JSON file |
| `--fem-url` | `URL` | — | FEM URL for Tier 2 tests (default: auto-discover) |
| `--bms` | flag | — | Include BMS battery test (extra sendMqtt load — opt-in) |

### schema

Show Current/Totals field schema — Python attr → raw API key mapping.

```
franklinwh-cli schema [options]
```

Detailed guide: [CLI_SCHEMA_COMMAND.md](CLI_SCHEMA_COMMAND.md)

| Option | Value | Default | Description |
|---|---|---|---|
| `--live` | flag | — | Fetch live values from get_stats() and show alongside the schema |
| `--filter` | `GROUP` | — | Filter to fields in a group (e.g. 'power', 'electrical', 'relay', '211', 'network'). 'network' shows the connectivity inventory; add --live for current state and a health check |

### fetch

Arbitrary GET/POST to any API endpoint.

```
franklinwh-cli fetch [options]
```

| Option | Value | Default | Description |
|---|---|---|---|
| `http_method` (positional) | `GET\|POST\|get\|post` | — | HTTP method |
| `path` (positional) | `PATH` | — | API path (e.g. /hes-gateway/common/getPowerCapConfigList) |
| `--data`, `-d` | `JSON` | — | Inline JSON POST body |
| `--data-file`, `-f` | `PATH` | — | JSON file for POST body (use '-' for stdin) |
| `--params`, `-P` | `KEY=VAL` | — | Query parameters (key=value pairs) |
| `--output`, `-o` | `PATH` | — | Save response to JSON file |
| `--no-gateway` | flag | — | Don't auto-inject gatewayId into payload |
| `--inject-user` | flag | — | Auto-inject userId into payload |
| `--app-version` | `VER` | — | Override softwareversion header for this call only (e.g. APP2.11.0, APP1.0.0). Default: APP2.4.1 (certified baseline). Use for API version comparison testing. |

<!-- END GENERATED: cli commands -->

## Example Scenarios

### Export last month's energy to a spreadsheet

```bash
franklinwh-cli energy --period month --date 2026-09-01 --format csv -o sep.csv
```

One row per day, with solar, grid import and export, battery charge and discharge,
and home use in kWh. Add `--all-fields` for the source split (home from solar, from
battery and so on). `franklinwh-cli energy --describe` explains every column.

### Year-to-date totals as JSON

```bash
franklinwh-cli energy --period ytd --format json -o ytd.json
```

### A day's 5-minute power profile

```bash
franklinwh-cli energy --period day --date 2026-10-07 --interval 5min --format csv -o day.csv
```

### Get a gateway off 4G and back onto its WiFi

```bash
franklinwh-cli network status                          # what is it on now?
franklinwh-cli network set-wifi --ssid MyHomeWiFi --use-stored
```

`--use-stored` reuses the password the aGate already holds, which is the usual
case when it has dropped to 4G. The command checks a fallback exists before
writing, then confirms the link came up.

### Watch the system live

```bash
franklinwh-cli monitor --interval 10            # full dashboard, Ctrl+C to stop
franklinwh-cli monitor --compact -d 30          # one line per poll for 30 minutes
```

### Capture a support snapshot to share

```bash
franklinwh-cli support --save --redact full --label pre-outage
```

`--redact full` removes emails, serial numbers and IP addresses from the saved file; `--redact` alone masks them.

### Call any library method directly

```bash
franklinwh-cli raw list                         # what's available
franklinwh-cli raw get_power_details 3 2026-09-01 --json
```
