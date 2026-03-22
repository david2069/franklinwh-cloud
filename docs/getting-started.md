# Getting Started

## Installation

```bash
pip install franklinwh-cloud
```

Or from source:

```bash
git clone https://github.com/david2069/franklinwh-cloud.git
cd franklinwh-cloud
python -m venv venv
source venv/bin/activate
pip install -e .
```

## Configuration

Create `franklinwh.ini` in your project directory:

```ini
[franklinwh]
email = your@email.com
password = your_password
gateway = YOUR-AGATE-SERIAL
```

## First Connection

```python
import asyncio
from franklinwh_cloud.client import Client, TokenFetcher

async def main():
    fetcher = TokenFetcher("your@email.com", "your_password")
    await fetcher.get_token()
    client = Client(fetcher, "YOUR-AGATE-SN")

    stats = await client.get_stats()
    print(f"Solar: {stats.current.solar_to_house} kW")
    print(f"Battery SoC: {stats.current.battery_pct}%")

asyncio.run(main())
```

## CLI Quick Start

```bash
# System overview
franklinwh-cli status

# Live monitoring
franklinwh-cli monitor

# Raw API access (48+ methods)
franklinwh-cli raw list

# JSON output for scripting
franklinwh-cli status --json | jq '.battery_soc'
```

## Prerequisites

- Python 3.12+
- FranklinWH account with aGate access
- Network access to `energy.franklinwh.com`
