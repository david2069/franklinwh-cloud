"""Shared exception classes for FranklinWH client."""


class TokenExpiredException(Exception):
    """Raised when the token has expired."""


class AccountLockedException(Exception):
    """Raised when the account is locked."""


class InvalidCredentialsException(Exception):
    """Raised when the credentials are invalid."""


class DeviceTimeoutException(Exception):
    """Raised when the device times out."""


class GatewayOfflineException(Exception):
    """Raised when the gateway is offline."""


class FranklinWHError(Exception):
    """Raised when the FranklinWH backend rejects a command outright.

    Used for ``sendMqtt`` responses whose ``code`` is neither 200 (success) nor
    one of the specifically-handled failures — 102 (``DeviceTimeoutException``)
    and 136 (``GatewayOfflineException``).

    Attributes
    ----------
    code : int | None
        The ``code`` field from the API response, e.g. 400.
    message : str | None
        The ``message`` field from the API response, e.g.
        ``"No vpn gateway vpn!"`` — which is what the backend returns when the
        gateway id is missing or not resolvable for the account.

    Note
    ----
    This class was referenced by ``client._mqtt_send`` but never defined, so
    every such rejection raised ``ImportError`` and discarded the backend's
    actual code and message.
    """

    def __init__(self, message=None, code=None):
        self.code = code
        self.message = message
        super().__init__(message)


class InvalidResponseError(FranklinWHError):
    """Raised when the API returns a body that is not JSON.

    The FranklinWH cloud sits behind CloudFront, which serves HTML error pages
    for 502/503/504 and for WAF blocks. Those are not API responses at all, so
    there is no ``code`` field to inspect — the failure is at the transport
    layer, not the application layer.

    Subclasses :class:`FranklinWHError` deliberately: callers already guarding a
    long-running poll with ``except FranklinWHError`` should survive a CDN blip
    without needing to know about HTTP internals.

    Attributes
    ----------
    status_code : int | None
        The HTTP status, e.g. 504.
    body : str | None
        The first 500 characters of the response body, for diagnosis. Truncated
        deliberately — CloudFront error pages run to several KB and the full
        text is noise in a log.
    """

    def __init__(self, message=None, status_code=None, body=None):
        self.status_code = status_code
        self.body = body
        super().__init__(message, code=status_code)


class InvalidOperatingMode(BaseException):
    """Raised when the operating mode requested is invalid."""


class InvalidOperatingModeOption(BaseException):
    """Raised when an operating mode option is invalid or missing."""


class UauthorizedRequest(BaseException):
    """Raised when the FranklinWH backend rejects the request."""


class BadRequestParsingError(BaseException):
    """Raised when the FranklinWH backend fails to parse the request."""


class InvalidTOUScheduleOption(BaseException):
    """Raised when the TOU schedule option is invalid."""


class FranklinWHTimeoutError(Exception):
    """Raised when an API call exceeds the timeout threshold.

    Attributes
    ----------
    url : str
        The URL that timed out.
    timeout_s : int
        The timeout threshold in seconds.
    """

    def __init__(self, url: str, timeout_s: int = 30):
        self.url = url
        self.timeout_s = timeout_s
        super().__init__(f"API request timed out after {timeout_s}s: {url}")


class ForceSessionError(Exception):
    """Base exception for Force Mode errors."""


class ForceVPPLockError(ForceSessionError):
    """Raised when a force mode operation is blocked by an active VPP."""


class ForceSessionActiveError(ForceSessionError):
    """Raised when a force session is already active."""
