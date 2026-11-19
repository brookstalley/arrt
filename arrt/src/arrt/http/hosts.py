"""Which names this server answers to, which pages may call it, and which may frame it.

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

**What `Sec-Fetch-Site` adds, which `Origin` cannot.** A browser sends `Origin` on
every cross-origin request that is not a plain `GET` or `HEAD`, and none on those:
an `<img src>` or a no-cors `fetch` of another page's `/api/...` URL arrives with
the server's own address in `Host`, no `Origin`, and the household's browser's
network position. `GET /api/registry/works/<qid>/look` starts a look, which asks
every image source and keeps what it fetches, so such a request has an effect
though its page can never read the answer. Every current browser also sends
`Sec-Fetch-Site`, naming the relation between the page and the target:
`same-origin`, `same-site`, `cross-site` or `none` (typed or bookmarked).
**`/api` and `/mcp` refuse `cross-site`.** The interface's own requests say
`same-origin`; an MCP client, `curl` and a Player send no such header and are not
asked for one, because a refusal of the absent header would refuse every client
that is not a browser. The pages and `/static` are not refused: a link to the
interface from a chat or a bookmark is a `cross-site` navigation, and the page it
loads can do nothing the guard above would not already stop. `same-site` (another
port on the same host) is not refused either: where it carries an `Origin` the
rule above refuses it, and the header names a relation, not a fault.

**No page may frame the interface.** A page that framed it would show the
household Arrt's own buttons under its own pictures, and each click would be a
same-origin request the checks above rightly pass: a paid Get, a theme hung on a
wall, a Player's token rotated. Every HTML response, the shell, `/docs` and any
page a static file is, carries `Content-Security-Policy: frame-ancestors 'none'`
and `X-Frame-Options: DENY`, the second for a browser that predates the first.
It is added here, to the response, rather than at each route that builds a page,
so a page added later is covered the day it is mounted.

**The Player's routes are not checked.** Each one already requires the wall's
token, which a rebinding page cannot read. And a Player configured with a name
the server was never told about would otherwise lose its feed. Which routes those
are is read from the router that serves them, never from a list of paths kept
here, so a route the contract adds is exempt the day it is mounted.
"""

import ipaddress
import logging
from collections.abc import Collection, MutableMapping, Sequence
from typing import Any, Final

from starlette.routing import BaseRoute, Match
from starlette.types import ASGIApp, Receive, Scope, Send

log = logging.getLogger(__name__)

#: The setting a refusal names, so the operator who reaches the server by a new
#: name is told what to change rather than left with a bare status code.
ALLOWED_HOSTS_SETTING: Final[str] = "CURATION_ALLOWED_HOSTS"

#: The surfaces a page elsewhere may not call, whatever method it uses: the JSON
#: API and the MCP mount (`app.MCP_PATH`). Matched as a path or a path's parent, so
#: `/apiary` is not `/api`.
CROSS_SITE_REFUSED_UNDER: Final[tuple[str, ...]] = ("/api", "/mcp")

#: What forbids a page to be shown inside another: the standard header, and the
#: older one for a browser that does not read it. Added to every HTML response.
FRAME_HEADERS: Final[tuple[tuple[bytes, bytes], ...]] = (
    (b"content-security-policy", b"frame-ancestors 'none'"),
    (b"x-frame-options", b"DENY"),
)

#: The value a browser sends in `Sec-Fetch-Site` for a request from a page of another site.
CROSS_SITE: Final[str] = "cross-site"

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
        if scope["type"] == "http":
            send = _unframed(send)
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
        if scope["type"] == "http" and _is_under(scope["path"], CROSS_SITE_REFUSED_UNDER):
            site = headers.get("sec-fetch-site", "").strip().lower()
            if site == CROSS_SITE:
                log.warning("refused a cross-site request on %s", scope["path"])
                await _refuse(
                    scope,
                    send,
                    ORIGIN_REFUSED,
                    "A page of another site may not call this server's API or MCP surface.",
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


def _is_under(path: str, prefixes: Sequence[str]) -> bool:
    """Whether `path` is one of `prefixes` or below it, never merely starting with the same letters."""
    return any(path == prefix or path.startswith(prefix + "/") for prefix in prefixes)


def _unframed(send: Send) -> Send:
    """`send`, with `FRAME_HEADERS` added to the start of a response whose content type is HTML."""

    async def wrapped(message: MutableMapping[str, Any]) -> None:
        if message["type"] == "http.response.start":
            held = list(message.get("headers", ()))
            if any(name.lower() == b"content-type" and value.lower().startswith(b"text/html") for name, value in held):
                present = {name.lower() for name, _ in held}
                held.extend(
                    header for header in FRAME_HEADERS if header[0] == b"content-security-policy" or header[0] not in present
                )
                message = {**message, "headers": held}
        await send(message)

    return wrapped


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
