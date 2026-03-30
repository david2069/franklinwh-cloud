"""Authentication strategies for interacting with the FranklinWH API.

Provides support for standard username/password login and raw static token injection.
"""
from abc import ABC, abstractmethod
import hashlib
import httpx
import logging

from franklinwh_cloud.api import DEFAULT_URL_BASE
from franklinwh_cloud.exceptions import InvalidCredentialsException, AccountLockedException

logger = logging.getLogger(__name__)

# Login account types for appUserOrInstallerLogin endpoint
LOGIN_TYPE_USER = 0         # Homeowner / app user
LOGIN_TYPE_INSTALLER = 1    # Installer / professional

class BaseAuth(ABC):
    """Abstract base class for FranklinWH authentication strategies."""
    
    def __init__(self):
        self.info: dict | None = None
        
    @abstractmethod
    async def get_token(self, force_refresh=False) -> str:
        """Return a valid authentication token.
        
        Parameters
        ----------
        force_refresh : bool
            If True, aggressively discard any cached token and fetch fresh.
        """
        pass
        
    @property
    def access_token(self) -> str:
        """Synchronous property to get the access token.
        
        Falls back to asyncio event loop runner if necessary.
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        if loop.is_running():
            if self.info and self.info.get("token"):
                return self.info["token"]
            return loop.run_until_complete(self.get_token())
        else:
            return loop.run_until_complete(self.get_token())

class PasswordAuth(BaseAuth):
    """Authenticates using email and password against the Cloud API."""
    
    def __init__(self, username: str, password: str, login_type: int = LOGIN_TYPE_USER, emulate_app_version: str = "APP2.4.1") -> None:
        """Initialize the PasswordAuth fetcher.

        Parameters
        ----------
        login_type : int
            0 = App user (homeowner), 1 = Installer.
        """
        super().__init__()
        self.username = username
        self.password = password
        self.login_type = login_type
        self.emulate_app_version = emulate_app_version
        
    async def get_token(self, force_refresh=False) -> str:
        """Fetch a new authentication token using the stored credentials."""
        if self.info and self.info.get("token") and not force_refresh:
            return self.info["token"]
            
        result = await self._login(self.username, self.password, self.login_type, self.emulate_app_version)
        if not result or "token" not in result:
             raise InvalidCredentialsException("Login failed: No token returned in response")
             
        self.info = result
        return self.info["token"]

    @staticmethod
    async def login(username: str, password: str, login_type: int = 0, emulate_app_version: str = "APP2.4.1"):
        """Log in to the FranklinWH API and retrieve an authentication token."""
        return (await PasswordAuth._login(username, password, login_type, emulate_app_version))["token"]

    @staticmethod
    async def _login(username: str, password: str, login_type: int = 0, emulate_app_version: str = "APP2.4.1") -> dict:
        """Log in to the FranklinWH API and retrieve account information."""
        url = DEFAULT_URL_BASE + "hes-gateway/terminal/initialize/appUserOrInstallerLogin"
        form = {
            "account": username,
            "password": hashlib.md5(bytes(password, "ascii")).hexdigest(),
            "lang": "en_US",
            "type": login_type,
        }
        async with httpx.AsyncClient(http2=True) as client:
            res = await client.post(url, data=form, headers={"softwareversion": emulate_app_version}, timeout=30)
        res.raise_for_status()
        js = res.json()

        if js["code"] == 401:
            raise InvalidCredentialsException(js["message"])

        if js["code"] == 400:
            raise AccountLockedException(js["message"])

        # Capture natively echoed backend version for Telemetry
        js["result"]["_emulated_version"] = emulate_app_version
        js["result"]["_backend_software_version"] = js["result"].get("softwareVersion") or res.headers.get("softwareversion")

        return js["result"]

# Backwards compatibility alias for older scripts and <= 0.3.0
TokenFetcher = PasswordAuth

class TokenAuth(BaseAuth):
    """Authentication strategy for scripts injecting pre-fetched tokens.
    
    Ideal for bypassing username/password requirements. Does not perform 
    network-bound logins or token refreshing.
    """
    
    def __init__(self, token: str):
        super().__init__()
        self.info = {"token": str(token)}
        
    async def get_token(self, force_refresh=False) -> str:
        """Return the pre-injected token. Never refreshes on network."""
        return self.info["token"]
