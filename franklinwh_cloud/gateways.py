"""Gateway resolution — choose the aGate to talk to without guessing."""

from __future__ import annotations

from franklinwh_cloud.auth import BaseAuth
from franklinwh_cloud.exceptions import GatewaySelectionError


async def list_gateway_serials(auth: BaseAuth) -> list[str]:
    """Return the serials (``id``) of every gateway on the account, in API order.

    Uses ``get_home_gateway_list()`` through a short-lived client that is
    closed before returning.
    """
    from franklinwh_cloud.client import Client

    async with Client(auth, "placeholder") as tmp:
        res = await tmp.get_home_gateway_list()
    return serials_from_gateway_list(res)


def serials_from_gateway_list(res) -> list[str]:
    """Extract gateway serials (``id``) from a ``get_home_gateway_list()`` response."""
    entries = (res.get("result") or []) if isinstance(res, dict) else (res or [])
    return [str(e.get("id")) for e in entries if isinstance(e, dict) and e.get("id")]


async def resolve_gateway(auth: BaseAuth, serial: str | None = None) -> str:
    """Return the one aGate serial to use, or raise rather than guess.

    - ``serial`` given: returned (in the account's own spelling) if the account
      has it; otherwise :class:`GatewaySelectionError`.
    - No ``serial``, one gateway on the account: that gateway.
    - No ``serial``, none or several: :class:`GatewaySelectionError`, with
      ``.serials`` listing what the account has so a caller can ask the user.

    Unlike ``FranklinWHCloud.select_gateway()``, which binds the first gateway
    when no serial is given, this never picks one of several.
    """
    serials = await list_gateway_serials(auth)
    if serial:
        for s in serials:
            if s.upper() == serial.strip().upper():
                return s
        raise GatewaySelectionError(
            f"Gateway {serial} is not on this account (found: {', '.join(serials) or 'none'})",
            serials=serials,
        )
    if len(serials) == 1:
        return serials[0]
    if not serials:
        raise GatewaySelectionError("No gateways found on this account", serials=serials)
    raise GatewaySelectionError(
        f"Account has {len(serials)} gateways; specify one of: {', '.join(serials)}",
        serials=serials,
    )
