"""Client for interacting with FranklinWH gateway API.

This module provides classes and functions to authenticate, send commands,
and retrieve statistics from FranklinWH energy gateway devices.
"""

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from jsonschema import validate, ValidationError
import logging
import time
import zlib
from datetime import datetime, timedelta
import httpx


from .api import DEFAULT_URL_BASE
from .models import Stats, Current, Totals, GridStatus, empty_stats
from .exceptions import (
    TokenExpiredException, AccountLockedException, InvalidCredentialsException,
    DeviceTimeoutException, GatewayOfflineException, InvalidOperatingMode,
    InvalidOperatingModeOption, UauthorizedRequest, BadRequestParsingError,
    InvalidTOUScheduleOption, FranklinWHTimeoutError,
)
# Operating Workand Run mode constants
from franklinwh_cloud.const import RUN_STATUS, OPERATING_MODES, workModeType, TIME_OF_USE, SELF_CONSUMPTION, EMERGENCY_BACKUP
from franklinwh_cloud.const import MODE_MAP, MODE_TIME_OF_USE, MODE_SELF_CONSUMPTION, MODE_EMERGENCY_BACKUP, tou_json_schema

# Power Control Settings and Emergency Backup periods
from franklinwh_cloud.const import PCS_CONTROL, EMERGENCY_BACKUP_PERIODS
# TOU Schedule dispatch codes and wave types (tariffs)
from franklinwh_cloud.const import dispatchCodeType, DISPATCH_CODES, WaveType, WAVE_TYPES, valid_tou_modes
# NOTE: TOU Schedule presets (primarily for testing / examples)
from franklinwh_cloud.const.test_fixtures import (
    gap_schedule, export_to_grid_always, export_to_grid_peak2, 
    export_to_grid_peakonly, charge_from_grid, standby_schedule, 
    power_home_only, charge_from_solar, self_schedule, custom_schedule
)

# Mixin modules — each groups related API methods
from franklinwh_cloud.mixins.stats import StatsMixin
from franklinwh_cloud.mixins.modes import ModesMixin
from franklinwh_cloud.mixins.tou import TouMixin
from franklinwh_cloud.mixins.storm import StormMixin
from franklinwh_cloud.mixins.power import PowerMixin
from franklinwh_cloud.mixins.devices import DevicesMixin
from franklinwh_cloud.mixins.account import AccountMixin
from franklinwh_cloud.mixins.discover import DiscoverMixin

logger = logging.getLogger(__name__)
class AccessoryType(Enum):
    """Represents the type of accessory connected to the FranklinWH gateway.

    Attributes:
        SMART_CIRCUIT_MODULE (int): A Smart Circuit module, see https://www.franklinwh.com/document/download/smart-circuits-module-installation-guide-sku-accy-scv2-us
        GENERATOR_MODULE (int): A Generator module, see https://www.franklinwh.com/document/download/generator-module-installation-guide-sku-accy-genv2-us
    """

    GENERATOR_MODULE = 3
    SMART_CIRCUIT_MODULE = 4


def to_hex(inp):
    """Convert an integer to an 8-character uppercase hexadecimal string.

    Parameters
    ----------
    inp : int
        The integer to convert.

    Returns:
    -------
    str
        The hexadecimal string representation of the input.
    """
    return f"{inp:08X}"


class Mode:
    """Represents an operating mode for the FranklinWH gateway.

    Provides static methods to create specific modes (time of use, emergency backup, self consumption)
    and generates payloads for API requests to set the gateway's operating mode.

    Attributes:
    ----------
    soc : int
        The state of charge value for the mode.
    currendId : int | None
        The current mode identifier.
    workMode : int | None
        The work mode value.

    Methods:
    -------
    time_of_use(soc=20)
        Create a time of use mode instance.
    emergency_backup(soc=100)
        Create an emergency backup mode instance.
    self_consumption(soc=20)
        Create a self consumption mode instance.
    payload(gateway)
        Generate the payload dictionary for API requests.
    """

    @staticmethod
    def time_of_use(soc=20):
        """Create a time of use mode instance.

        Parameters
        ----------
        soc : int, optional
            The state of charge value for the mode, defaults to 20.

        Returns:
        -------
        Mode
            An instance of Mode configured for time of use.
        """
        mode = Mode(soc)
        mode.currendId = 9322
        mode.workMode = 1
        mode.oldIndex = 3
        mode.stormEn = 0
        return mode

    @staticmethod
    def emergency_backup(soc=100):
        """Create an emergency backup mode instance.

        Parameters
        ----------
        soc : int, optional
            The state of charge value for the mode, defaults to 100.

        Returns:
        -------
        Mode
            An instance of Mode configured for emergency backup.
        """
        mode = Mode(soc)
        mode.currendId = 9324
        mode.workMode = 3
        mode.oldIndex = 1
        mode.stormEn = 0
        return mode

    @staticmethod
    def self_consumption(soc=20):
        """Create a self consumption mode instance.

        Parameters
        ----------
        soc : int, optional
            The state of charge value for the mode, defaults to 20.

        Returns:
        -------
        Mode
            An instance of Mode configured for self consumption.
        """
        mode = Mode(soc)
        mode.currendId = 9323
        mode.workMode = 2
        mode.oldIndex = 2
        mode.stormEn = 0
        return mode

    def __init__(self, soc: int) -> None:
        """Initialize a Mode instance with the given state of charge.

        Parameters
        ----------
        soc : int
            The state of charge value for the mode.
        """
        self.soc = soc
        self.currendId = None
        self.workMode = None
        self.stormEn = None
        self.oldIndex = None

    def payload(self, gateway) -> dict:
        """Generate the payload dictionary for API requests to set the gateway's operating mode.

        Parameters
        ----------
        gateway : str
            The gateway identifier.

        Returns:
        -------
        dict
            The payload dictionary for the API request.
        """
        return {
            "currendId": str(self.currendId),
            "gatewayId": gateway,
            "lang": "EN_US",
            "oldIndex": str(self.oldIndex),
            "soc": str(self.soc),
            "stromEn": str(self.stormEn),
            "workMode": str(self.workMode),
        }

# Auth Strategies
from franklinwh_cloud.auth import (
    BaseAuth, PasswordAuth, TokenAuth, TokenFetcher, 
    LOGIN_TYPE_USER, LOGIN_TYPE_INSTALLER
)


async def retry(func, filter, refresh_func):
    """Tries calling func, and if filter fails it calls refresh func then tries again."""
    res = await func()
    if filter(res):
        return res
    await refresh_func()
    return await func()


class Client(StatsMixin, ModesMixin, TouMixin, StormMixin, PowerMixin, DevicesMixin, AccountMixin, DiscoverMixin):

    """Client for interacting with FranklinWH gateway API."""

    def __init__(
        self, fetcher: BaseAuth, gateway: str, url_base: str = DEFAULT_URL_BASE,
        client_headers: dict | None | bool = True,
        rate_limiter=None,
        tolerate_stale_data: bool = False,
        stale_cache_ttl: float = 300,
        emulate_app_version: str = "APP2.4.1",
        cache: dict | None = None,
    ) -> None:
        """Initialize the Client with the provided TokenFetcher, gateway ID, and optional URL base.

        Parameters
        ----------
        client_headers : dict | None | bool
            True = send default client identity headers (recommended, good API citizen).
            dict = send custom headers. None/False = send no extra headers (anonymous).
        rate_limiter : RateLimiter | bool | None
            None/False = no proactive throttling (default — 429s still detected reactively).
            True = create default limiter (60/min).
            RateLimiter(...) = custom limits (e.g. daily budget).
        tolerate_stale_data : bool
            If True, return cached responses when the API is unreachable/slow.
            Default False. Inspired by richo/homeassistant-franklinwh.
        stale_cache_ttl : float
            Max age of cached data in seconds. Default 300s (5 minutes).
            Only used when tolerate_stale_data=True.
        cache : dict | None
            Per-method TTL cache configuration. None (default) = no caching.
            Pass ``franklinwh_cloud.cache.DEFAULT_CACHE`` for library-recommended
            TTLs, or a custom ``{method_name: seconds}`` dict to override.
            TTL of 0 for a specific method disables caching for that method.
            Example::

                from franklinwh_cloud.cache import DEFAULT_CACHE
                client = FranklinWHCloud(email, password, cache=DEFAULT_CACHE)
        """
        from franklinwh_cloud.metrics import ClientMetrics, DISCLAIMER, EdgeTracker, RateLimiter, StaleDataCache, get_default_client_headers

        # Log legal disclaimer once per process
        if not getattr(Client, '_disclaimer_logged', False):
            logging.getLogger("franklinwh_cloud").info(DISCLAIMER)
            Client._disclaimer_logged = True

        self.fetcher = fetcher
        self.gateway = gateway
        self.url_base = url_base
        self.token = self.fetcher.info.get("token", "") if self.fetcher.info else ""
        self.snno = 0
        self.info = self.fetcher.info
        self.metrics = ClientMetrics()

        # Rate limiter — proactive client-side throttling (opt-in)
        if rate_limiter is True:
            self.rate_limiter = RateLimiter()  # default: 60/min
        elif isinstance(rate_limiter, RateLimiter):
            self.rate_limiter = rate_limiter
        else:
            self.rate_limiter = None  # disabled by default

        # Stale data cache — graceful degradation when cloud is slow/down
        if tolerate_stale_data:
            self.stale_cache = StaleDataCache(max_age_s=stale_cache_ttl, enabled=True)
        else:
            self.stale_cache = StaleDataCache(max_age_s=stale_cache_ttl, enabled=False)

        # Edge tracker — CloudFront PoP monitoring (always on, zero overhead)
        self.edge_tracker = EdgeTracker()

        self._dynamic_modes_cache: dict[int, str] | None = None
        self._canary_baseline_version = "APP2.11.0"
        self._canary_tripped = False
        self._emulate_app_version = emulate_app_version  # outbound softwareversion header value

        # Method-level TTL cache — opt-in, zero overhead when disabled
        if cache is not None:
            from franklinwh_cloud.cache import MethodCache
            self.method_cache = MethodCache(cache)
            self._apply_method_cache()
        else:
            self.method_cache = None

        # Client identity headers — good API citizenship
        default_headers = {}
        if client_headers is True:
            default_headers = get_default_client_headers()
        elif isinstance(client_headers, dict):
            default_headers = client_headers
        # else: no extra headers (anonymous)

        # httpx event hook to capture CloudFront headers from every response
        async def _on_response(response: httpx.Response):
            self.edge_tracker.record_response(response.headers)
            self.edge_tracker._last_request_url = str(response.url)
            self.edge_tracker._last_request_method = response.request.method

        self.session = httpx.AsyncClient(
            http2=True,
            headers=default_headers,
            event_hooks={"response": [_on_response]},
        )

        logger = logging.getLogger("franklinwh_cloud")
        if logger.isEnabledFor(logging.DEBUG):

            async def debug_request(request: httpx.Request):
                body = request.content
                if body and request.headers.get("Content-Type", "").startswith(
                    "application/json"
                ):
                    body = json.dumps(json.loads(body), ensure_ascii=False)
                self.logger.debug(
                    "Request: %s %s %s %s",
                    request.method,
                    request.url,
                    request.headers,
                    body,
                )
                return request

            async def debug_response(response: httpx.Response):
                await response.aread()
                self.logger.debug(
                    "Response: %s %s %s %s",
                    response.status_code,
                    response.url,
                    response.headers,
                    response.json(),
                )
                return response

            self.logger = logger
            self.session = httpx.AsyncClient(
                http2=True,
                event_hooks={
                    "request": [debug_request],
                    "response": [debug_response],
                },
            )




    async def _post(self, url, payload, params: dict = None, **kwargs):

        logger.debug(f"_post: url={url} params={params} payload={payload} kwargs={kwargs}")

        from urllib.parse import urlparse, parse_qs

        def extract_url_params(url):
            """
            Remove and extract all URL parameters into a dictionary.
            
            Args:
                url: The URL string to process
                
            Returns:
                tuple: (base_url, params_dict)
            """
            parsed = urlparse(url)
            
            # Extract parameters into a dictionary
            params = parse_qs(parsed.query)
            
            # parse_qs returns lists for each value, convert to single values
            # Keep as list if multiple values exist for same key
            params_dict = {
                k: v[0] if len(v) == 1 else v 
                for k, v in params.items()
            }
            
            # Reconstruct base URL without query parameters
            base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            
            # Handle fragment if present
            if parsed.fragment:
                base_url += f"#{parsed.fragment}"
            
            return base_url, params_dict




        headers = {"loginToken": str(self.token)}
        tag = "gatewayId"
        if params is None:
            params = {}
        else:
            params = params.copy()
            if "equipNo" in params:
                tag = "equipNo"
        if "&" in url:
            url, params = extract_url_params(url)
        gateway_params = {tag: str(self.gateway), "lang": "en_US"}
        suppress_params = kwargs.get("suppress_params") in (True, "Y")
        suppress_gateway = kwargs.get("suppress_gateway") in (True, "Y")
        logger.debug(f"suppress_params={suppress_params} suppress_gateway={suppress_gateway} params={params} gateway_params={gateway_params}")
        if suppress_params is True:
            params = {} if suppress_gateway is False else None
            if suppress_gateway is False:
                params = gateway_params
                logger.debug("suppress both params and gateway")

        if suppress_gateway is False and params is not None:
            params.update(gateway_params)

        logger.debug(f"params={params}")

        async def __post():
            headers["loginToken"] = str(self.token)
            try:
                if payload is not None:
                    headers.update({"Content-Type": "application/json", "accept-encoding": "gzip", "lang": "EN_US"})
                    if isinstance(payload, (dict, list)):
                        resp = await self.session.post(url, headers=headers, params=params, json=payload, timeout=30)
                    else:
                        # payload already serialized or primitive
                        resp = await self.session.post(url, headers=headers, params=params, data=str(payload), timeout=30)
                else:
                    headers.update({"Content-Type": "application/json"})
                    resp = await self.session.post(
                        url,
                        params=params,
                        headers=headers,
                        data=payload,
                        timeout=30,
                    )
            except httpx.TimeoutException:
                raise FranklinWHTimeoutError(url, 30)

            if not resp.text.strip():
                # Some API endpoints (e.g. smart circuit toggles) return 200 with an empty body
                json_resp = {"code": 200, "message": "success (empty body)", "result": {"dataArea": "{}"}}
            else:
                try:
                    json_resp = resp.json()
                except Exception as e:
                    print("JSON Decode Error in _post! Status:", resp.status_code, "Body:", repr(resp.text))
                    raise
            self._check_canary_trap(url, json_resp, resp.headers)
            return json_resp

        from franklinwh_cloud.metrics import instrumented_retry, extract_endpoint
        final_res = await instrumented_retry(
            self.metrics, extract_endpoint(url), "POST",
            __post, lambda j: j.get("code") not in [401, 10009], self.refresh_token,
        )
        
        if final_res.get("code") in [401, 10009]:
            raise TokenExpiredException(f"Token expired or completely invalid: Code {final_res.get('code')} - {final_res.get('message', 'Unauthorized')}")
            
        return final_res



    async def _get(self, url, params: dict | None = None, **kwargs):

        headers = {"loginToken": str(self.token)}
        tag = "gatewayId"
        if params is None:
            params = {}
        else:
            params = params.copy()
            if "equipNo" in params:
                tag = "equipNo"
        suppress_params = kwargs.get("suppress_params") in (True, "Y")
        suppress_gateway = kwargs.get("suppress_gateway") in (True, "Y")
        logger.debug(f"suppress_params={suppress_params} suppress_gateway={suppress_gateway}")
        
        if suppress_params:
            params = {}
        if not suppress_gateway:
            if params is None: params = {}
            params.update({tag: self.gateway, "lang": "en_US"})
    
        logger.debug(f"params={params}")

        async def __get():
            try:
                resp = await self.session.get(
                    url, params=params, headers={"loginToken": str(self.token)},
                    timeout=30,
                )
            except httpx.TimeoutException:
                raise FranklinWHTimeoutError(url, 30)
                
            if not resp.text.strip():
                json_resp = {"code": 200, "message": "success (empty body)", "result": {"dataArea": "{}"}}
            else:
                try:
                    json_resp = resp.json()
                except Exception as e:
                    print("JSON Decode Error in _post! Status:", resp.status_code, "Body:", repr(resp.text))
                    raise
            self._check_canary_trap(url, json_resp, resp.headers)
            return json_resp

        from franklinwh_cloud.metrics import instrumented_retry, extract_endpoint
        final_res = await instrumented_retry(
            self.metrics, extract_endpoint(url), "GET",
            __get, lambda j: j.get("code") not in [401, 10009], self.refresh_token,
            rate_limiter=self.rate_limiter,
            stale_cache=self.stale_cache,
        )
        
        if final_res.get("code") in [401, 10009]:
            raise TokenExpiredException(f"Token expired or completely invalid: Code {final_res.get('code')} - {final_res.get('message', 'Unauthorized')}")
            
        return final_res


    async def refresh_token(self):
        """Refresh the authentication token using the TokenFetcher."""
        self.metrics.record_token_refresh()
        self.token = await self.fetcher.get_token(force_refresh=True)
        # Telemetry: capture the backend echoed software version
        if getattr(self.fetcher, "info", None):
            sv = self.fetcher.info.get("_backend_software_version")
            if sv:
                self.metrics._latest_backend_software_version = sv

    def _apply_method_cache(self) -> None:
        """Wrap configured methods with TTL caching at init time.

        Applied once per Client instance. Uses instance-level binding so the
        original class methods are never mutated — safe for multiple Client
        instances with different cache configurations in the same process.
        """
        import functools

        for method_name in self.method_cache._config:
            original_fn = getattr(type(self), method_name, None)
            if original_fn is None:
                continue  # method name not found on this client — skip silently

            # Capture loop variables in closure
            def _make_wrapper(name, fn):
                @functools.wraps(fn)
                async def _cached_wrapper(self_inner, *args, **kwargs):
                    args_hash = hash((args, tuple(sorted(kwargs.items()))))
                    cached = self_inner.method_cache.get(name, args_hash)
                    if cached is not None:
                        return cached
                    result = await fn(self_inner, *args, **kwargs)
                    self_inner.method_cache.set(name, args_hash, result)
                    return result
                return _cached_wrapper

            # Bind the wrapper to this instance only (not the class)
            wrapped = _make_wrapper(method_name, original_fn)
            setattr(self, method_name, wrapped.__get__(self, type(self)))

    def invalidate_cache(self, method: str | None = None) -> None:
        """Invalidate the method-level TTL cache.

        Call this after write operations that change data returned by a cached
        method. For example, after ``set_smart_circuit_state()``, call
        ``client.invalidate_cache('get_smart_circuits_info')``.

        Parameters
        ----------
        method : str | None
            Method name to invalidate, or ``None`` to clear the entire cache.
        """
        if self.method_cache:
            self.method_cache.invalidate(method)

    def get_metrics(self) -> dict:
        """Return a snapshot of all API call metrics.

        Returns
        -------
        dict
            Metrics including uptime, call counts, timing, errors,
            retries, and token refresh counts, as well as CloudFront 
            edge tracking and caching telemetry.

            ``session.emulate_app_version`` — the ``softwareversion`` header
            value sent with every request (our outbound identity).

            ``session.latest_backend_software_version`` — the version string
            the server echoed back on last login/refresh. ``None`` until the
            first token refresh. Used by the canary trap for schema drift
            detection.
        """
        payload = self.metrics.snapshot()
        payload["edge"] = self.edge_tracker.snapshot()
        if hasattr(self, "stale_cache"):
            payload["cache"] = self.stale_cache.snapshot()
        if self.method_cache:
            payload["method_cache"] = self.method_cache.snapshot()
        if self.rate_limiter:
            payload["rate_limits"] = self.rate_limiter.snapshot()
        # Surface both sides of the version handshake in a single block
        payload["session"] = {
            "emulate_app_version": self._emulate_app_version,
            "latest_backend_software_version": self.metrics._latest_backend_software_version,
            "canary_tripped": self._canary_tripped,
        }
        return payload

    def next_snno(self):
        """Get the next sequence number for API requests."""
        self.snno += 1
        return self.snno

    def _check_canary_trap(self, url, json_payload, headers):
        """Monitors incoming API boundaries for silently incremented Firmware/App structures."""
        # Check explicit HTTP response headers (rare, but user-requested fallback)
        sv_header = headers.get("softwareversion") or headers.get("x-franklin-softwareversion")
        
        # Check core JSON body nodes (typical placement for FranklinWH gateways)
        sv_body = None
        if isinstance(json_payload, dict):
            # Nested inside 'result' or 'data' or top-level
            target = json_payload.get("result", json_payload.get("data", json_payload))
            if isinstance(target, dict):
                # Restrict to explicit software headers, avoiding hardware model IDs like '102'
                sv_body = target.get("softwareVersion")
        
        detected_version = sv_header or sv_body
        
        # If the API returns a version identifier formally tracking newer than our APP2.11.0 baseline
        if detected_version and isinstance(detected_version, str) and not self._canary_tripped:
            # Strip standard prefixes to parse numerically if possible, or just strict compare
            if detected_version.startswith("APP") and detected_version != self._canary_baseline_version and "APP2.11" not in detected_version:
                self._canary_tripped = True
                logger.warning(f"🚨 API CANARY TRIPPED: Unrecognized Firmware/Software Version detected '{detected_version}' (Baseline: {self._canary_baseline_version})")
                
                # Automatically dump the alien structure to disk for survey mapping
                dump_name = f"franklinwh_cloud_survey_dump_{int(time.time())}.json"
                try:
                    with open(dump_name, "w", encoding="utf-8") as f:
                        json.dump({"url": url, "version": detected_version, "payload": json_payload}, f, indent=2)
                    logger.warning(f"🚨 Alien layout safely preserved to {dump_name} for OpenAPI inspection.")
                except Exception as e:
                    logger.error(f"Failed to dump Canary payload: {e}")

    def _build_payload(self, ty, data):
        blob = json.dumps(data, separators=(",", ":")).encode("utf-8")
        crc = to_hex(zlib.crc32(blob))
        ts = int(time.time())

        temp = json.dumps(
            {
                "lang": "EN_US",
                "cmdType": ty,
                "equipNo": self.gateway,
                "type": 0,
                "timeStamp": ts,
                "snno": self.next_snno(),
                "len": len(blob),
                "crc": crc,
                "dataArea": "DATA",
            }
        )
        # We do it this way because without a canonical way to generate JSON we can't risk reordering breaking the CRC.
        return temp.replace('"DATA"', blob.decode("utf-8"))

    async def _mqtt_send(self, payload):
        url = self.url_base + "hes-gateway/terminal/sendMqtt"

        res = await self._post(url, payload)
        if res["code"] == 102:
            raise DeviceTimeoutException(res["message"])
        if res["code"] == 136:
            raise GatewayOfflineException(res["message"])
        if res.get("code") != 200:
            from franklinwh_cloud.exceptions import FranklinWHError
            raise FranklinWHError(f"Command failed gracefully with server rejection: {res.get('code')} - {res.get('message')}")
            
        return res






