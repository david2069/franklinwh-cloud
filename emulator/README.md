# FranklinWH Cloud API Emulator

This directory contains standalone infrastructure to run local integration tests and simulate deterministic failures without directly touching physical `aGate` hardware or communicating with the live internet API. 

## Requirements
Ensure you have installed the test emulator optional dependency group in your `venv`:
```bash
pip install -e ".[emulator]"
```

## Running the Proxy

```bash
cd emulator/
python main.py
```
*(Alternatively, via `uvicorn main:app --port 8080 --reload`)*

## Configuring the Python Client
You can override the client connection route by supplying the base URL during instantiation, or adjusting global defaults.

```python
from franklinwh_cloud import Client, PasswordAuth

# Initialize Auth against Mock
fetcher = PasswordAuth("nobody@example.invalid", "fake-password")

# Provide an overridden base URL pointing to the Local Emulator Proxy
client = Client(fetcher, "10060006A00000000000")
client.url_base = "http://localhost:8080/"

# Testing transparent endpoint execution
response = await client.get_stats()
print(response)
```

# Future Scope
- Topographical Mocking (Simulating 3 chained gateways to a single mock login token).
- Schema Middleware Verification natively utilizing `docs/franklinwh_openapi.json`.
- Advanced Error Injection Controls.

## Testing with the CLI (Structural Failure Experiments)

You can safely trigger failure modes or test offline parsing without hitting physical rate limits. Simply point your `franklinwh-cli` tool at the running local emulator:

1. **Start the Emulator**
   ```bash
   uvicorn emulator.main:app --port 8080
   ```
2. **Execute CLI commands against localhost**
   Set the `FRANKLIN_URL_BASE` environment variable to override the default cloud endpoint:
   ```bash
   FRANKLIN_URL_BASE=http://localhost:8080/ franklinwh-cli raw get_stats
   ```

*Note: The CLI will authenticate using a hardcoded dummy token returned by the local proxy's mock login endpoint, enabling transparent offline testing.*
