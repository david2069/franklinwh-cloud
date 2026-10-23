"""Masking for log output: secrets and personal data become ``***``, serials keep their last 4 (#25, #27, #29)."""

import json
import re
from urllib.parse import parse_qsl, urlsplit, urlunsplit

# Field names whose values must never reach a log: wifi_Pw, ap_Pw, password,
# token, secret, ... Matched case-insensitively on the end of the key.
_SECRET_KEY_RE = re.compile(r"(pw|pwd|pass|password|passwd|psk|secret|token)$", re.IGNORECASE)


# Field names that hold a gateway or device serial; logged as the last 4 only.
_SERIAL_KEY_RE = re.compile(r"^(gatewayid|gateway_id|equipno|sn|serialno|serial_no|serial)$", re.IGNORECASE)
# Field names holding personal data: people, contact details, addresses, coordinates,
# and user-chosen site, device and network names. Exact names (case-insensitive) ...
_PII_KEYS = frozenset(k.lower() for k in (
    "email", "loginName", "userName", "firstName", "lastName", "nickName", "account",
    "contactNumber", "userPhoneNumber", "phone", "mobile",
    "address", "address1", "address2", "completeAddress", "userAddress", "deviceAddress",
    "addressFinish", "addressSecondLast", "flat", "city", "postCode", "postcode", "zipCode",
    "lat", "lon", "latitude", "longitude",
    "name", "siteName", "gatewayName", "Sw1Name", "Sw2Name", "Sw3Name",
    "ssid", "mac", "ip",
))
# ... plus these endings: installerCompanyEmail, cityLat, wifi_SSID, ...
_PII_KEY_RE = re.compile(r"(email|phone|phonenumber|address|latitude|longitude|lat|lon|ssid)$", re.IGNORECASE)
# Any e-mail address left in free text.
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
# Header names that carry credentials (loginToken, Authorization, Cookie, ...).
_SECRET_HEADER_RE = re.compile(r"(token|authorization|cookie|password|passwd|secret)", re.IGNORECASE)


def _mask_serial(value) -> str:
    """Show only the last 4 characters of a serial: ``***0042``."""
    s = str(value)
    return "***" + s[-4:] if len(s) > 4 else "***"


def _is_pii_key(key: str) -> bool:
    return key.lower() in _PII_KEYS or bool(_PII_KEY_RE.search(key))


def _redact_secrets(value):
    """Return a copy of ``value`` with secret-looking fields masked, for logging.

    Secrets and personal data (e-mail, names, addresses, coordinates, site and
    device names) become ``***``; serial fields (``gatewayId``, ``equipNo``, ``sn``, ...)
    keep their last 4 characters. Walks dicts and lists, and also JSON held in
    strings (gateway commands carry their body as a JSON string in ``dataArea``).
    Non-JSON strings pass through.
    """
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if isinstance(k, str) and v not in (None, "") and (
                    _SECRET_KEY_RE.search(k) or (not isinstance(v, (dict, list)) and _is_pii_key(k))):
                out[k] = "***"
            elif isinstance(k, str) and isinstance(v, (str, int)) and v != "" and _SERIAL_KEY_RE.match(k):
                out[k] = _mask_serial(v)
            else:
                out[k] = _redact_secrets(v)
        return out
    if isinstance(value, (list, tuple)):
        return [_redact_secrets(v) for v in value]
    if isinstance(value, str) and value[:1] in ("{", "["):
        try:
            return json.dumps(_redact_secrets(json.loads(value)))
        except ValueError:
            return value
    return value


def _redact_url(url) -> str:
    """Return ``url`` as a string with secret and serial query values masked."""
    parts = urlsplit(str(url))
    if not parts.query:
        return str(url)
    query = "&".join(f"{k}={v}" for k, v in _redact_secrets(dict(parse_qsl(parts.query, keep_blank_values=True))).items())
    return urlunsplit(parts._replace(query=query))


def _redact_headers(headers) -> dict:
    """Return ``headers`` as a dict with credential headers masked."""
    return {k: ("***" if _SECRET_HEADER_RE.search(k) else v) for k, v in dict(headers).items()}


def _scrub_serial(text: str, serials) -> str:
    """Mask any remaining occurrence of the given serial(s), and any e-mail address, in ``text``."""
    text = _EMAIL_RE.sub("***@***", text)
    if isinstance(serials, (str, int)) or serials is None:
        serials = [serials]
    for serial in serials:
        if serial and len(str(serial)) > 4:
            text = text.replace(str(serial), _mask_serial(serial))
    return text
