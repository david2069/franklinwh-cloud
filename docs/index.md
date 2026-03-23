# FranklinWH Cloud

Unofficial Python library and CLI for the **FranklinWH** energy management system.

---

## Features

- **Full Cloud API** — 70+ methods across power, modes, TOU, storm, devices, billing
- **CLI tool** — `franklinwh-cli` with rich terminal output and JSON mode
- **Device Discovery** — 3-tier survey with system readiness, feature flags, accessories
- **TOU Schedule Management** — Read, write, verify schedules with gap-fill and validation
- **Tariff Workflow** — Search utilities, browse tariffs, apply templates
- **Network Diagnostics** — WiFi, Ethernet, 4G config via MQTT
- **Billing & Savings** — Electricity data, charge history, benefit tracking

## Quick Start

```bash
pip install franklinwh-cloud
```

```python
from franklinwh_cloud.client import Client, TokenFetcher

fetcher = TokenFetcher("your@email.com", "your_password")
await fetcher.get_token()
client = Client(fetcher, "YOUR-AGATE-SN")

# Get current power flows
stats = await client.get_stats()
print(f"Solar: {stats.current.solar_to_house} kW")
```

## CLI

```bash
franklinwh-cli status              # System overview
franklinwh-cli discover -v         # Device survey (3 tiers)
franklinwh-cli monitor             # Live power flows
franklinwh-cli tou                 # TOU schedule
franklinwh-cli raw get_stats       # Raw API passthrough
franklinwh-cli support --nettest   # Network diagnostics
```

## Architecture

```mermaid
graph LR
    A[Your Code] --> B[Client]

    B --> C["Cloud API<br/>(REST/HTTPS)"]
    C --> CF["CloudFront CDN"]
    CF --> FW["FranklinWH Cloud"]
    FW -->|"FranklinWH Official Client<br/>(sendMqtt format)"| E[aGate]

    M["Modbus TCP<br/>(SunSpec/Raw)"] -.->|"Local network<br/>port 502"| E

    E --> F[aPower Batteries]

    style B fill:#3b82f6,color:#fff
    style E fill:#059669,color:#fff
    style FW fill:#7c3aed,color:#fff
    style M fill:#d97706,color:#fff
```

> **Two distinct transport paths to the aGate:**
>
> - **Cloud API** — REST calls via CloudFront → FranklinWH Cloud → aGate (sendMqtt format). Used by this library and the official FranklinWH app.
> - **Modbus TCP** — Direct LAN connection to aGate port 502. SunSpec-compliant + raw registers. Used by FEM, Home Assistant, and third-party controllers.

## Documentation

| Section | What's covered |
|---------|---------------|
| [Getting Started](getting-started.md) | Installation, credentials, first connection |
| [API Cookbook](API_COOKBOOK.md) | Copy-paste recipes for common tasks |
| [API Reference](API_REFERENCE.md) | All 70+ methods with parameters |
| [TOU Guide](TOU_SCHEDULE_GUIDE.md) | Schedule management with workflow diagrams |
| [CLI Raw Methods](cli-raw.md) | All raw API methods available from CLI |
