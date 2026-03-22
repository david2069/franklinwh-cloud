# CLI — Raw API Methods

The `franklinwh-cli raw` command provides direct passthrough to all 48+ API methods.

## Usage

```bash
# List all available methods
franklinwh-cli raw list

# Call a method (no args)
franklinwh-cli raw get_stats

# Call with positional arguments
franklinwh-cli raw get_tariff_detail 4329

# JSON output
franklinwh-cli raw get_stats --json

# Pipe JSON payload via stdin
echo '[{"startHourTime":"0:00","endHourTime":"24:00","waveType":1}]' \
  | franklinwh-cli raw get_custom_dispatch_list

# Show timing info
franklinwh-cli raw get_stats --timings

# Show response headers
franklinwh-cli raw get_stats --headers
```

## Available Methods

### Power & Stats

| Method | Args | Description |
|--------|------|-------------|
| `get_stats` | — | Current power flows and daily totals |
| `get_runtime_data` | — | Runtime data log |
| `get_power_by_day` | `YYYY-MM-DD` | Power for a specific day |
| `get_power_details` | `type date` | Power aggregated (type 1-5) |

### Operating Modes

| Method | Args | Description |
|--------|------|-------------|
| `get_mode` | — | Current operating mode |
| `get_mode_info` | — | Mode configuration details |

### Weather & Storm

| Method | Args | Description |
|--------|------|-------------|
| `get_weather` | — | Current weather conditions |
| `get_storm_settings` | — | Storm hedge settings |
| `get_storm_list` | — | Storm event history |

### Power Control

| Method | Args | Description |
|--------|------|-------------|
| `get_grid_status` | — | Grid on/off status |
| `get_power_control_settings` | — | PCS control settings |
| `get_power_info` | — | Relay and power hardware info |

### Devices & Network

| Method | Args | Description |
|--------|------|-------------|
| `get_device_composite_info` | — | Full device composite data |
| `get_agate_info` | — | aGate hardware info |
| `get_apower_info` | — | aPower battery hardware info |
| `get_device_info` | — | Device detail info |
| `get_smart_circuits_info` | — | Smart circuit configuration |
| `get_bms_info` | `serial_no` | BMS info for a specific aPower |
| `get_network_info` | — | aGate network config (via MQTT) |
| `get_wifi_config` | — | WiFi SSID, AP config (via MQTT) |
| `scan_wifi_networks` | — | Scan WiFi networks (via MQTT) |
| `get_connection_status` | — | Router/AWS connectivity (via MQTT) |
| `get_network_switches` | — | Interface on/off: WiFi/Eth/4G (via MQTT) |

### Account & Site

| Method | Args | Description |
|--------|------|-------------|
| `get_home_gateway_list` | — | Home gateway list |
| `siteinfo` | — | Site / account info |
| `get_entrance_info` | — | Customer entrance config |
| `get_unread_count` | — | Unread notification count |
| `get_notification_settings` | — | Notification settings |
| `get_warranty_info` | — | Warranty information |
| `get_alarm_codes_list` | — | Alarm codes history |
| `get_site_and_device_info` | — | Site and device list |
| `get_equipment_location` | — | Equipment location |
| `get_grid_profile_info` | — | Grid compliance profile |
| `get_programme_info` | — | VPP/utility programmes |
| `get_benefit_info` | — | Benefit/savings earnings |
| `get_gateway_alarm` | — | Active gateway alarms |
| `get_site_detail` | — | Site name, address, location |
| `get_device_detail` | — | Device/gateway address |
| `get_device_overall_info` | — | aPower count, total power |
| `get_personal_info` | — | User profile info |

### TOU / Tariff

| Method | Args | Description |
|--------|------|-------------|
| `get_gateway_tou_list` | — | TOU schedule list |
| `get_charge_power_details` | — | Charge power details |
| `get_tou_dispatch_detail` | — | TOU dispatch detail |
| `get_utility_companies` | `countryId provinceId` | Search utility companies |
| `get_tariff_list` | `companyId` | List tariffs for a utility |
| `get_tariff_detail` | `tariffId` | Full tariff template detail |
| `get_tou_detail_by_id` | `touId` | TOU config by ID |
| `get_bonus_info` | — | TOU bonus/incentive info |
| `get_vpp_tip` | — | VPP tips for TOU updates |

### Billing & Savings

| Method | Args | Description |
|--------|------|-------------|
| `get_electric_data` | `type date` | Electricity kWh arrays |
| `get_charge_history` | — | Battery charge/discharge history |

## Stdin JSON Input

Methods that need structured payloads accept JSON via stdin:

```bash
# Custom dispatch list
echo '[{"startHourTime":"0:00","endHourTime":"24:00","waveType":1}]' \
  | franklinwh-cli raw get_custom_dispatch_list --json

# Expected earnings calculator
cat template.json | franklinwh-cli raw calculate_expected_earnings --json
```
