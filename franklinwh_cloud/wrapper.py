import configparser
import os
from .client import Client
from .auth import PasswordAuth

class FranklinWHCloud:
    """
    Facade wrapper to provide backward compatibility with legacy scripts
    that expect FranklinWHCloud(email, password) instead of TokenFetcher/Client.
    Acts as an orchestration layer on top of the modern API structs.
    """

    def __init__(self, email: str = None, password: str = None, gateway: str = None,
                 cache: dict | None = None, track_python_methods: bool = False):
        self.email = email
        self.password = password
        self.gateway = gateway
        self._cache = cache
        self._track_python_methods = track_python_methods
        self._auth = None
        self._client = None

    @classmethod
    def from_config(cls, filepath: str = "franklinwh.ini"):
        """Initialize from an INI file or fallback to environment variables."""
        email = None
        password = None
        gateway = None

        if os.path.exists(filepath):
            config = configparser.ConfigParser()
            config.read(filepath)
            # Find email/pass
            for section in ["energy.franklinwh.com", "FranklinWH"]:
                if config.has_section(section):
                    try:
                        email = config.get(section, "email")
                        password = config.get(section, "password")
                        break
                    except (configparser.NoOptionError, KeyError):
                        pass

            # Find gateway serial
            if config.has_section("gateways.enabled"):
                gateway = config.get("gateways.enabled", "serialno", fallback=None)
            elif config.has_section("FranklinWH"):
                gateway = config.get("FranklinWH", "gateway", fallback=None)

        # Environment fallbacks if INI fails
        if not email or not password:
            email = os.environ.get("FRANKLIN_USERNAME")
            password = os.environ.get("FRANKLIN_PASSWORD")
            gateway = gateway or os.environ.get("FRANKLIN_GATEWAY")

        return cls(email=email, password=password, gateway=gateway)

    async def login(self):
        """Authenticates and fetches the JWT token via PasswordAuth."""
        if not self.email or not self.password:
            raise ValueError("Email and password must be provided to login.")

        self._auth = PasswordAuth(self.email, self.password)
        await self._auth.get_token()

    async def select_gateway(self, serial: str = None):
        """Binds the active authentication session to a specific aGate."""
        if not self._auth:
            await self.login()

        target_gateway = serial or self.gateway

        if not target_gateway:
            # Auto-discover the first gateway attached to the account natively
            # The login payload does NOT contain gateway bindings, so we must
            # execute an explicit account-level fetch using a proxy client.
            temp_client = Client(self._auth, "placeholder")
            gateways_raw = await temp_client.get_home_gateway_list()
            
            # Unwrap the API envelope
            gw_list = gateways_raw.get("result", []) if isinstance(gateways_raw, dict) else gateways_raw
            
            if not gw_list:
                raise ValueError("No gateways found via get_home_gateway_list(). Cannot auto-bind Client.")
            
            target_gateway = gw_list[0].get("id", "")

        self._client = Client(self._auth, target_gateway, cache=self._cache,
                               track_python_methods=self._track_python_methods)

    def __getattr__(self, name):
        """Proxy all API method calls directly to the modern Client instance."""
        if self._client is None:
            raise RuntimeError("Client not initialized. You must await .login() and .select_gateway() first.")
        return getattr(self._client, name)
