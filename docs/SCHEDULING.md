# Scheduling Nettest — HOWTO

The CLI provides `franklinwh-cli support --nettest` as an atomic, single-run command.
Scheduling is left to your platform — here are copy-paste examples.

## The Building Block

```bash
franklinwh-cli --config /path/to/franklinwh.ini \
  support --nettest --bms \
  --record ~/nettest-logs/nettest-$(date +%Y-%m-%dT%H-%M-%S).json
```

| Flag | Purpose |
|------|---------|
| `--config` | Absolute path to `franklinwh.ini` (required for headless) |
| `--nettest` | Run network diagnostics |
| `--bms` | Include BMS battery test (opt-in, adds ~10s) |
| `--record FILE` | Save results to JSON file |

---

## macOS — launchd

Create `~/Library/LaunchAgents/com.franklinwh.nettest.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.franklinwh.nettest</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>
            source /path/to/venv/bin/activate &amp;&amp;
            franklinwh-cli --config /path/to/franklinwh.ini
              support --nettest --bms
              --record ~/nettest-logs/nettest-$(date +%Y-%m-%dT%H-%M-%S).json
        </string>
    </array>
    <key>StartInterval</key>
    <integer>3600</integer>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
```

```bash
# Load
launchctl load ~/Library/LaunchAgents/com.franklinwh.nettest.plist

# Unload
launchctl unload ~/Library/LaunchAgents/com.franklinwh.nettest.plist
```

> **Note**: LaunchAgents run when you're logged in. For boot-time
> execution, use `/Library/LaunchDaemons/` (requires `sudo`).

---

## Linux — cron

```bash
crontab -e
```

Add:
```
# Hourly nettest
0 * * * * /path/to/venv/bin/franklinwh-cli --config /path/to/franklinwh.ini support --nettest --bms --record ~/nettest-logs/nettest-$(date +\%Y-\%m-\%dT\%H-\%M-\%S).json 2>> ~/nettest-logs/stderr-$(date +\%Y-\%m-\%d).log
```

---

## Linux — systemd timer

```bash
# ~/.config/systemd/user/franklinwh-nettest.service
[Unit]
Description=FranklinWH Network Test

[Service]
Type=oneshot
ExecStart=/path/to/venv/bin/franklinwh-cli --config /path/to/franklinwh.ini support --nettest --bms --record %%h/nettest-logs/nettest-%%t.json
```

```bash
# ~/.config/systemd/user/franklinwh-nettest.timer
[Unit]
Description=Hourly FranklinWH Network Test

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl --user enable --now franklinwh-nettest.timer
```

---

## Docker / Container

```dockerfile
# In Dockerfile or docker-compose healthcheck
HEALTHCHECK --interval=1h --timeout=30s \
  CMD franklinwh-cli --config /app/franklinwh.ini support --nettest --bms
```

Or with cron inside the container:
```bash
echo "0 * * * * /app/venv/bin/franklinwh-cli --config /app/franklinwh.ini support --nettest --bms --record /data/nettest-\$(date +\%Y-\%m-\%dT\%H-\%M-\%S).json" | crontab -
```

---

## Log Maintenance

Auto-prune logs older than 30 days:
```bash
find ~/nettest-logs -name "nettest-*.json" -mtime +30 -delete
```

Add to your scheduling mechanism or run as a separate cron job.
