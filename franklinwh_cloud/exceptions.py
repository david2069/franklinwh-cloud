"""Shared exception classes for FranklinWH client."""


class TokenExpiredException(Exception):
    """Raised when the token has expired."""


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


class LoginError(FranklinWHError):
    """Raised when the login endpoint does not return a token.

    Base class for every login failure, so ``except LoginError`` catches them
    all. Raised directly for a response code the library does not recognise,
    or a response with no ``result`` — instead of the ``TypeError`` older
    versions raised there (``DEF-AUTH-LOGIN-NULL-RESULT``).

    Attributes
    ----------
    code : int | None
        The ``code`` field from the login response.
    message : str | None
        The ``message`` field from the login response.
    """


class InvalidCredentialsException(LoginError):
    """Raised when the credentials are invalid (login code 401)."""


class AccountLockedException(LoginError):
    """Raised for login code 400.

    Despite the name, code 400 is also sent **before** the account locks, as a
    warning: one live sample (2026-10-17) was a wrong password answered with
    ``"Incorrect password, you still have 2 chances to enter."``

    Attributes
    ----------
    attempts_left : int | None
        The ``N`` parsed from "you still have N chances" in the message, or
        ``None`` when the message does not say. INFERRED from that one English
        sample (the library always requests ``lang=en_US``). ``None`` does not
        prove the account is locked — no locked-account message has been
        captured. Callers should not retry while this is not ``None`` and small,
        and should not retry blindly at all.
    """

    def __init__(self, message=None, code=400, attempts_left=None):
        super().__init__(message, code=code)
        if attempts_left is None and message:
            import re
            m = re.search(r"still have (\d+) chances?", str(message), re.IGNORECASE)
            if m:
                attempts_left = int(m.group(1))
        self.attempts_left = attempts_left


class RateLimitedError(FranklinWHError):
    """Raised when the cloud answers HTTP 429, or a body with ``code`` 429,
    on a call that has no other way to report it (currently: login).

    Not a :class:`LoginError` on purpose: being rate limited says nothing about
    the credentials, so a caller counting failed logins toward a lockout must
    not count this one.

    Attributes
    ----------
    retry_after : int
        Seconds from the ``Retry-After`` header, or 30 when it is absent.
    """

    def __init__(self, message=None, code=429, retry_after=30):
        super().__init__(message, code=code)
        self.retry_after = retry_after


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
        from franklinwh_cloud.log_redaction import _redact_url
        super().__init__(f"API request timed out after {timeout_s}s: {_redact_url(url)}")


class ForceSessionError(Exception):
    """Base exception for Force Mode errors."""


class ForceVPPLockError(ForceSessionError):
    """Raised when a force mode operation is blocked by an active VPP."""


class ForceSessionActiveError(ForceSessionError):
    """Raised when a force session is already active."""


class GatewaySelectionError(FranklinWHError):
    """Raised by :func:`franklinwh_cloud.resolve_gateway` when it cannot pick
    exactly one aGate without guessing.

    Attributes
    ----------
    serials : list[str]
        Every gateway serial the account returned (empty if none).
    """

    def __init__(self, message=None, serials=None):
        super().__init__(message)
        self.serials = list(serials or [])
