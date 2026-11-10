"""Which names this server answers to, and which pages may call it.

**DNS rebinding is the attack this refuses.** The server performs no
authentication (`security-model.md` § Trust Boundary): anyone on the household's
LAN is the curator. A web page open in a browser on that LAN is not, but it can
point its own domain name at this server's address after loading, and from then
on its requests reach `/mcp` and `/api` as same-origin requests, which CORS never
stops. That page could then start discovery runs that spend money, or change what
is on the walls. What gives the page away is the name: its requests carry the
attacker's domain in `Host`, and `Origin` when the browser sends one.

**What passes as a Host.** A name the deployment lists (`CURATION_ALLOWED_HOSTS`),
`localhost`, or an IP address. An IP address is always allowed because a rebinding
page's requests cannot carry one: its `Host` is the domain it rebound. Allowing IP
addresses costs nothing and keeps a fresh install reachable by address.

**What passes as an Origin, which is stricter.** A browser sends `Origin` with
every cross-origin request, so it is what tells Arrt's own page apart from any
other page that calls it: one served from another LAN device, or from another
port on this machine. A listed name passes whatever its scheme or port, because
a reverse proxy changes both. Anything else must be the request's own address:
the same name and port as its `Host`, a missing port being the scheme's default.
So the browser interface opened by address calls itself, and no other page does.
`Origin: null`, which sandboxed and file pages send, and a malformed `Origin`
never pass. A request with no `Origin` passes, since that is how every
non-browser client (an MCP client, a Player, `curl`) calls.

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
    the address, not a port separator. The names a deployment lists are reduced
    by this too, so a listed name and a request's name are compared in one form.
    """
    return _authority(value)[0]


def _authority(value: str) -> tuple[str, int | None]:
    """`host[:port]` as (name, port), the port None when absent or not a number."""
    value = value.strip()
    if value.startswith("["):
        end = value.find("]")
        name, rest = (value[1:end], value[end + 1 :]) if end >= 0 else (value[1:], "")
        port_text = rest[1:] if rest.startswith(":") else ""
    elif value.count(":") == 1:
        name, _, port_text = value.partition(":")
    else:
        name, port_text = value, ""
    port = int(port_text) if port_text.isdigit() else None
    return name.rstrip(".").lower(), port


#: The port an `Origin` means when it names none.
_DEFAULT_PORTS: Final[dict[str, int]] = {"http": 80, "https": 443}


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
        self._allowed = frozenset(hostname(name) for name in allowed_hosts)
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
        if origin is not None and not self._origin_allowed(origin, headers.get("host", "")):
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

    def _origin_allowed(self, origin: str, host: str) -> bool:
        """A listed name, or the request's own address; see the module's docstring."""
        parsed = _origin(origin)
        if parsed is None:
            return False
        scheme, name, port = parsed
        if name in self._allowed:
            return True
        default = _DEFAULT_PORTS.get(scheme)
        host_name, host_port = _authority(host)
        return name == host_name and (port or default) == (host_port or default) and default is not None

    def _is_exempt(self, scope: Scope) -> bool:
        # PARTIAL is a path that matches with the wrong method; the route answers
        # it with 405, which is no less the Player's route for being refused.
        return any(route.matches(scope)[0] is not Match.NONE for route in self._exempt)


def _origin(origin: str) -> tuple[str, str, int | None] | None:
    """An `Origin` (`scheme://host[:port]`) as (scheme, name, port), or None for `null` or any other shape."""
    scheme, separator, authority = origin.strip().partition("://")
    if not separator or not scheme or not authority or "/" in authority or "@" in authority:
        return None
    name, port = _authority(authority)
    return (scheme.lower(), name, port) if name else None


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
