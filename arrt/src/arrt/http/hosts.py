"""Which names this server answers to, and which pages may call it.

**DNS rebinding is the attack this refuses.** The server performs no
authentication (`security-model.md` § Trust Boundary): anyone on the household's
LAN is the curator. A web page open in a browser on that LAN is not, but it can
point its own domain name at this server's address after loading, and from then
on its requests reach `/mcp` and `/api` as same-origin requests, which CORS never
stops. That page could then start discovery runs that spend money, or change what
is on the walls. What gives the page away is the name: its requests carry the
attacker's domain in `Host`, and `Origin` when the browser sends one.

**What passes.** A name the deployment lists (`CURATION_ALLOWED_HOSTS`),
`localhost`, or an IP address. An IP address is always allowed because a rebinding
page's requests cannot carry one: its `Host` is the domain it rebound. Allowing IP
addresses costs nothing and keeps a fresh install reachable by address. An
`Origin`, when present, must pass the same test, and `Origin: null`, which
sandboxed and file pages send, never does. A request with no `Origin` passes,
since that is how every non-browser client (an MCP client, a Player, `curl`) calls.

**The Player's routes are not checked.** Each one already requires the wall's
token, which a rebinding page cannot read. And a Player configured with a name
the server was never told about would otherwise lose its feed. Which routes those
are is read from the router that serves them, never from a list of paths kept
here, so a route the contract adds is exempt the day it is mounted.
"""

import ipaddress
import logging
from collections.abc import Collection, Sequence
from typing import Final

from starlette.routing import BaseRoute, Match
from starlette.types import ASGIApp, Receive, Scope, Send

log = logging.getLogger(__name__)

#: The setting a refusal names, so the operator who reaches the server by a new
#: name is told what to change rather than left with a bare status code.
ALLOWED_HOSTS_SETTING: Final[str] = "CURATION_ALLOWED_HOSTS"

#: `421 Misdirected Request` for a name this server does not answer to: the
#: request reached the wrong server as far as this one is concerned.
#: `403` for a page that may not call it, which is a refusal of the caller.
#: These are the codes the MCP SDK's own transport guard uses for the same two cases.
HOST_REFUSED: Final[int] = 421
ORIGIN_REFUSED: Final[int] = 403


def hostname(value: str) -> str:
    """The name in a `Host` header, without its port, lowercased and without a trailing dot.

    An IPv6 address arrives bracketed (`[::1]:8770`), and its colons are part of
    the address, not a port separator.
    """
    value = value.strip()
    if value.startswith("["):
        name = value[1 : value.find("]")] if "]" in value else value[1:]
    elif value.count(":") == 1:
        name = value.partition(":")[0]
    else:
        name = value
    return name.rstrip(".").lower()


def is_allowed(name: str, allowed: Collection[str]) -> bool:
    """Whether `name`, already reduced by `hostname`, is one this server answers to."""
    if not name:
        return False
    if name == "localhost" or name in allowed:
        return True
    try:
        ipaddress.ip_address(name)
    except ValueError:
        return False
    return True


class HostGuard:
    """Refuse a request by a name this server does not answer to, or from a page that may not call it."""

    def __init__(self, app: ASGIApp, *, allowed_hosts: Collection[str], exempt: Sequence[BaseRoute]) -> None:
        self._app = app
        self._allowed = frozenset(allowed_hosts)
        self._exempt = tuple(exempt)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket") or self._is_exempt(scope):
            await self._app(scope, receive, send)
            return
        headers = {key.decode("latin-1"): value.decode("latin-1") for key, value in scope["headers"]}
        host = hostname(headers.get("host", ""))
        if not is_allowed(host, self._allowed):
            log.warning("refused a request for host %r on %s; not in %s", host, scope["path"], ALLOWED_HOSTS_SETTING)
            await _refuse(
                scope,
                send,
                HOST_REFUSED,
                f"This server does not answer to the name {host!r}. If that is how this household reaches "
                f"Arrt, add it to {ALLOWED_HOSTS_SETTING}.",
            )
            return
        origin = headers.get("origin")
        if origin is not None and not is_allowed(_origin_name(origin), self._allowed):
            log.warning("refused a request from origin %r on %s", origin, scope["path"])
            await _refuse(
                scope,
                send,
                ORIGIN_REFUSED,
                f"A page at {origin!r} may not call this server. If that is Arrt's own address, add its name "
                f"to {ALLOWED_HOSTS_SETTING}.",
            )
            return
        await self._app(scope, receive, send)

    def _is_exempt(self, scope: Scope) -> bool:
        # PARTIAL is a path that matches with the wrong method; the route answers
        # it with 405, which is no less the Player's route for being refused.
        return any(route.matches(scope)[0] is not Match.NONE for route in self._exempt)


def _origin_name(origin: str) -> str:
    """The host in an `Origin` (`scheme://host[:port]`), or "" for `null` or anything not of that shape.

    "" fails `is_allowed`, so a malformed `Origin` is refused rather than skipped.
    """
    scheme, separator, authority = origin.strip().partition("://")
    if not separator or not scheme or "/" in authority or "@" in authority:
        return ""
    return hostname(authority)


async def _refuse(scope: Scope, send: Send, status: int, message: str) -> None:
    if scope["type"] == "websocket":
        await send({"type": "websocket.close", "code": 1008, "reason": message[:120]})
        return
    body = message.encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"text/plain; charset=utf-8"), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})
