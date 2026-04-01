import json
import logging
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Basic configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("emulator")

app = FastAPI(
    title="FranklinWH Cloud API Emulator",
    description="A local proxy emulator for synthetic multi-node testing of the franklinwh-cloud library.",
    version="1.0.0"
)

# Hardcoded fixture paths or mock responses for initial foundations.
# In future, these can load entirely from tests/results directories or be manipulated via endpoints.

MOCK_LOGIN_RESPONSE = {
    "code": 200,
    "result": {
        "accessToken": "local-emulator-mock-token",
        "userInfo": {
            "userId": "12345",
            "email": "user@example.com",
            "roles": [],
            "currentType": 0
        }
    }
}

MOCK_GW_LIST_RESPONSE = {
    "code": 200,
    "result": [
        {
            "id": "10060006A00000000000",
            "netStatus": 1,
            "versionCode": "1.2.3",
            "productType": 1
        }
    ]
}

MOCK_STATS_RESPONSE = {
    "code": 200,
    "result": {
        "deviceTime": "2026-04-01 12:00:00",
        "powerPvo": 5000,
        "powerGrid": -1000,
        "powerBattery": -4000,
        "powerLoad": 0,
        "soc": 100,
        "gridStatus": 1,
        "solarStatus": 1,
        "batteryStatus": 1,
        "loadStatus": 1
    }
}


@app.middleware("http")
async def schema_validation_middleware(request: Request, call_next):
    """
    Middleware simulating @NotNull Java constraints.
    In the future, this will dynamically load `docs/franklinwh_openapi.json`
    and strictly drop requests that violate the spec.
    """
    # Simply log for now as foundations
    logger.info(f"[Emulator] Intercepting {request.method} {request.url.path}")
    response = await call_next(request)
    return response


@app.post("/newApi/api-user/app/login/v2")
async def login(request: Request):
    """Fallback mock for auth endpoint."""
    return JSONResponse(status_code=200, content=MOCK_LOGIN_RESPONSE)


@app.post("/hes-gateway/terminal/getHomeGatewayList")
async def home_gateway_list(request: Request):
    """Mock for gateway list."""
    return JSONResponse(status_code=200, content=MOCK_GW_LIST_RESPONSE)


@app.post("/api-energy/monitor/system/getAppHomeIndex")
async def get_app_home_index(request: Request):
    """Mock for stats payload."""
    return JSONResponse(status_code=200, content=MOCK_STATS_RESPONSE)


@app.get("/health")
async def health():
    return {"status": "emulator_online"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
