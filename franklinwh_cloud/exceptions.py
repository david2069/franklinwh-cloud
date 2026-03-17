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
