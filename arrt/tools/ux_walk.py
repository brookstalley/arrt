"""Walk the browser client and photograph every screen: Pass 1 of `docs/ux-walkthrough.md`.

Every guard the client has asks whether it matches its documents. This asks
nothing; it **shows**. It visits every screen the client declares and every one
a curator can reach by following links, photographs each at phone and desktop
width in light and dark, records what is on it (headings, controls, links out),
runs an accessibility scan, and writes a contact sheet that puts every screen
side by side.

**It cannot write.** Every request that is not `GET` or `HEAD` is aborted before
it leaves the browser and listed in the inventory. That is what makes it safe to
point at the real library, and what lets it click: much of this client
navigates by buttons that call the router rather than by links, so on each page
it clicks a sample of buttons (`--clicks-per-page`) and keeps the ones that
change the address. A write a click attempts is refused and tagged with the
button; a write a page attempts merely by being viewed is listed apart.
A `GET` is not free of effects on the server: a thumbnail is made on first ask,
and a not-held work's page asks the image sources what they offer, which sends
requests out to museums. None of that writes anything a curator owns.

    cd arrt
    uv run python tools/ux_walk.py --synthetic 2000 --out ../.ux-walk/synthetic
    uv run python tools/ux_walk.py --base-url http://<host>:<port> --out ../.ux-walk/real
    uv run python tools/ux_walk.py --base-url … --visit '#search?q=monet'

`--synthetic N` seeds a throwaway `ART_ROOT` with the suite's large corpus
(`tests/conftest.py`'s `build_large_catalogue`), boots the real entry point on
it, and stops it with SIGTERM and removes that `ART_ROOT` when done. That corpus
has no pictures, so every thumbnail is answered with a flat placeholder and the
sheet says so.

Needs the `browser` dependency group and a downloaded Chromium, as the browser
suite does (`docs/testing.md`). The accessibility scan is axe-core, fetched from
cdnjs once and cached under the output directory; offline, the scan is reported
as not run, never as clean.
"""

import argparse
import dataclasses
import hashlib
import html
import importlib.util
import io
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections import deque
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.error import URLError
from urllib.parse import parse_qsl, urlencode

if TYPE_CHECKING:  # the `browser` group is optional; annotations only
    from playwright.sync_api import Browser, BrowserContext, Page

_CURATION = Path(__file__).resolve().parent.parent
APP_JS = _CURATION / "src" / "arrt" / "http" / "static" / "app.js"
ROUTE_JS = _CURATION / "src" / "arrt" / "http" / "static" / "core" / "route.js"

#: Phone is an iPhone 14's CSS viewport; desktop is a common laptop. The pair is
#: the two layouts `design-direction.md` § Spacing & Layout designs for.
VIEWPORTS = {"phone": (390, 844), "desktop": (1440, 900)}
SCHEMES = ("light", "dark")

#: Pinned so two walks scan by the same rules; a new axe release adds rules and
#: would read as the surface getting worse.
AXE_URL = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"
#: The script is run inside pages that hold the operator's library, so what
#: arrives must be the release this was pinned against, cached copy included.
AXE_SHA256 = "b511cd9dec01c76f4b2ad1723b66b6db37d4c2eb4ed199076e1829d9ee7b75e3"

#: How long a screen may take to paint anything into `#view` before it is
#: photographed blank and recorded so, rather than ending the walk: a screen
#: that never paints is exactly what the walk exists to find.
PAINT_MS = 15000

#: How long a page may keep the network busy before it is photographed anyway.
#: Run pages poll every two seconds, so "idle" can be a long time coming; a page
#: that never settled is recorded as such rather than waited on forever.
SETTLE_MS = 6000

#: `?from=` records which page a contextual screen was opened from. It changes
#: the return link and nothing else, so two addresses differing only in it are
#: one page to photograph.
_IGNORED_PARAMS = {"from"}

_WRITE_SAFE_METHODS = {"GET", "HEAD"}


# ── The declared screens ─────────────────────────────────────────────────────


def _without_comments(source: str) -> str:
    """`/* … */` and `//…` gone, newlines kept. The route table's comments name its own keys."""
    source = re.sub(r"/\*.*?\*/", lambda match: "\n" * match.group().count("\n"), source, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", source)


def _object_literal(source: str, opener: str) -> str:
    found = source.find(opener)
    if found < 0:
        raise ValueError(f"no {opener.strip()!r} in the source; the file's shape has changed under this tool")
    start = found + len(opener)
    depth = 0
    for offset in range(start, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start + 1 : offset]
    raise ValueError(f"unbalanced object literal after {opener!r}")


@dataclasses.dataclass(frozen=True)
class Route:
    key: str
    #: absent → takes no id; "required" → not entered without one; "optional" → both.
    detail: str
    section: str | None
    page: str | None


def declared_routes(app_js: str) -> dict[str, Route]:
    """Every entry in `ROUTES`, parsed from the file rather than trusted from a list.

    Depth-1 keys only, so an object nested in an entry is invisible. Parsed, not
    executed: `app.js` installs the router on import and needs a browser to run.
    """
    body = _object_literal(_without_comments(app_js), "const ROUTES = ")
    routes: dict[str, Route] = {}
    depth = 0
    for match in re.finditer(r"[{}]|(\w+)\s*:\s*\{", body):
        if match.group() == "}":
            depth -= 1
            continue
        if depth == 0 and match.group(1):
            entry = _object_literal(body[match.start() :], f"{match.group(1)}:")
            detail = re.search(r"\bdetail\s*:\s*(true|OPTIONAL_ID)", entry)
            section = re.search(r'\bsection\s*:\s*"([^"]+)"', entry)
            page = re.search(r'\bpage\s*:\s*"([^"]+)"', entry)
            routes[match.group(1)] = Route(
                key=match.group(1),
                detail="absent" if not detail else ("required" if detail.group(1) == "true" else "optional"),
                section=section.group(1) if section else None,
                page=page.group(1) if page else None,
            )
        depth += 1
    if not routes:
        raise ValueError("ROUTES parsed to nothing; the table's shape has changed under this tool")
    return routes


def fragment_aliases(route_js: str) -> dict[str, str]:
    body = _object_literal(_without_comments(route_js), "FRAGMENT_ALIASES = ")
    return dict(re.findall(r"(\w+)\s*:\s*\"(\w+)\"", body))


# ── Addresses ────────────────────────────────────────────────────────────────


@dataclasses.dataclass(frozen=True, order=True)
class Address:
    """One photographable page: a route, an id, and the query that matters."""

    route: str
    ident: str = ""
    query: tuple[tuple[str, str], ...] = ()

    @property
    def fragment(self) -> str:
        if not self.route:
            return ""  # the bare shell: whatever the router makes the home page
        path = self.route + (f"/{self.ident}" if self.ident else "")
        return "#" + path + (f"?{urlencode(self.query)}" if self.query else "")

    @property
    def slug(self) -> str:
        return re.sub(r"[^A-Za-z0-9]+", "-", self.fragment.lstrip("#")).strip("-") or "home"


def parse_fragment(fragment: str, aliases: dict[str, str]) -> Address | None:
    """`#view[/id][?k=v…]` → an Address, or None for a fragment that is not a route."""
    if not fragment.startswith("#"):
        return None
    path, _, query = fragment[1:].partition("?")
    head, _, ident = path.partition("/")
    if not re.fullmatch(r"\w+", head):  # also refuses the bare "#"
        return None
    pairs = tuple(sorted((k, v) for k, v in parse_qsl(query, keep_blank_values=True) if k not in _IGNORED_PARAMS))
    return Address(route=aliases.get(head, head), ident=ident, query=pairs)


# ── What a page holds ────────────────────────────────────────────────────────

#: Read in the page: the outline, the controls, and the links out. Text is
#: trimmed so one long card cannot drown the inventory.
_READ_PAGE = """() => {
  const said = (el) => el.innerText || el.getAttribute('aria-label') || el.title || el.value || '';
  const text = (el) => said(el).trim().replace(/\\s+/g, ' ').slice(0, 80);
  const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const all = (sel) => Array.from(document.querySelectorAll(sel)).filter(visible);
  return {
    title: document.title,
    headings: all('h1,h2,h3,h4').map(h => ({level: +h.tagName[1], text: text(h)})),
    controls: all('button,input,select,textarea,[role=button],[role=tab],[role=checkbox],[role=switch]').map(c => ({
      kind: c.getAttribute('role') || c.tagName.toLowerCase() + (c.type && c.tagName === 'INPUT' ? ':' + c.type : ''),
      text: text(c) || c.placeholder || c.name || '',
      disabled: !!c.disabled || c.getAttribute('aria-disabled') === 'true',
    })),
    links: all('a[href]').map(a => {
      const href = a.getAttribute('href') || '';
      // An anchor to an element on this page (the skip link to #view) is not an address.
      const inPage = href.startsWith('#') && !!document.getElementById(href.slice(1));
      return {href, text: text(a), inPage};
    }),
    viewText: (document.querySelector('#view')?.innerText || '').trim().slice(0, 400),
  };
}"""


#: The buttons worth clicking to find where a page leads: visible, enabled,
#: and at most `limit` of each kind (tag and class), so a grid of two thousand
#: cards costs two clicks, not two thousand. Returns their indices in a fixed
#: enumeration, which a reloaded page reproduces.
_PROBE_CANDIDATES = """([perKind, limit]) => {
  const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const all = Array.from(document.querySelectorAll('#view button, #view [role=button]'));
  const seen = {}; const picked = [];
  all.forEach((el, index) => {
    if (!visible(el) || el.disabled || el.getAttribute('aria-disabled') === 'true') return;
    const kind = el.tagName + '.' + (el.getAttribute('class') || '');
    seen[kind] = (seen[kind] || 0) + 1;
    if (seen[kind] <= perKind && picked.length < limit) picked.push(index);
  });
  return picked;
}"""
_PROBE_CLICK = """(index) => {
  const el = Array.from(document.querySelectorAll('#view button, #view [role=button]'))[index];
  if (!el) return null;
  const said = (el.innerText || el.getAttribute('aria-label') || '').trim().replace(/\\s+/g, ' ').slice(0, 60);
  el.click();
  return said;
}"""


@dataclasses.dataclass
class Capture:
    address: Address
    variant: str
    image: str
    #: "idle", "busy" (a poll kept the network going) or "blank" (never painted).
    settled: str
    #: "clean", "violations", or "not run: <why>": three states, never folded.
    #: Scanned per variant because contrast differs between the two schemes.
    accessibility: str = "not run: not attempted"
    violations: list[dict] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class Visit:
    address: Address
    reached_by: str  # "home", "link", "button", "address", "requested"
    depth: int | None
    contents: dict = dataclasses.field(default_factory=dict)
    links_to: list[str] = dataclasses.field(default_factory=list)
    #: Addresses this page reaches only by a button that navigates by script:
    #: `[{"button": its text, "to": fragment}]`. Not a link, so not openable in
    #: a new tab, not copyable, not announced as a link.
    buttons_to: list[dict] = dataclasses.field(default_factory=list)
    captures: list[Capture] = dataclasses.field(default_factory=list)
    console_errors: list[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class Walk:
    base_url: str
    synthetic: int | None
    declared: dict[str, Route]
    visits: dict[Address, Visit] = dataclasses.field(default_factory=dict)
    refused_writes: list[dict] = dataclasses.field(default_factory=list)
    placeholder_pictures: bool = False


# ── The walk ─────────────────────────────────────────────────────────────────


def guard_writes(context: BrowserContext, refused: list[dict], *, placeholder: bytes | None = None) -> None:
    """Abort every request that could change the server, and record it.

    Installed on the context, so it covers every page the walk opens and every
    request a page makes on its own (a poll, a prefetch), not just navigations.
    """

    # Imported at run time, not under TYPE_CHECKING: Playwright reads a route
    # handler's annotations when it registers one, and an unresolved name is a
    # NameError there.
    from playwright.sync_api import Route as Interception

    def handle(route: Interception) -> None:
        request = route.request
        if request.method not in _WRITE_SAFE_METHODS:
            refused.append({"method": request.method, "url": request.url, "page": request.frame.url if request.frame else ""})
            route.abort("blockedbyclient")
            return
        if placeholder is not None and re.search(r"/api/works/[^/]+/thumbnail", request.url):
            route.fulfill(status=200, content_type="image/jpeg", body=placeholder)
            return
        route.fallback()

    context.route("**/*", handle)


def _placeholder_jpeg() -> bytes:
    from PIL import Image  # the plane's own dependency; imported here so `--help` needs nothing

    buffer = io.BytesIO()
    Image.new("RGB", (400, 300), (150, 140, 128)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _settle(page: Page, *, paint_ms: int = PAINT_MS, settle_ms: int = SETTLE_MS) -> str:
    """Wait for the screen to paint and the network to rest: "idle", "busy" or "blank"."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    try:
        page.wait_for_selector("#view *", timeout=paint_ms)
    except PlaywrightTimeout:
        return "blank"
    try:
        page.wait_for_load_state("networkidle", timeout=settle_ms)
    except PlaywrightTimeout:
        return "busy"
    return "idle"


#: Scrolled through once before a full-page photograph, because pictures below
#: the fold are `loading="lazy"` and would otherwise photograph as empty tiles.
_SCROLL_THROUGH = """async () => {
  for (let y = 0; y < document.body.scrollHeight; y += innerHeight) {
    scrollTo(0, y); await new Promise(r => setTimeout(r, 120));
  }
  scrollTo(0, 0);
}"""


def _open(page: Page, base_url: str, address: Address) -> str:
    # A blank page first, so a same-document hash change cannot leave the
    # previous screen's paint standing when the next is photographed.
    page.goto("about:blank")
    page.goto(f"{base_url}/{address.fragment}")
    return _settle(page)


class _Crawler:
    """Breadth-first from the home page by links; then every declared screen not reached.

    `per_screen` caps how many instances of one route are kept (two works, not
    two thousand). A screen reached only by typing its address is visited too,
    so it is photographed, and marked so it reads as the finding it is.
    """

    def __init__(
        self,
        page: Page,
        base_url: str,
        aliases: dict[str, str],
        declared: dict[str, Route],
        per_screen: int,
        clicks_per_page: int,
        refused: list[dict],
    ) -> None:
        self.page, self.base_url, self.aliases, self.declared = page, base_url, aliases, declared
        self.per_screen, self.clicks_per_page, self.refused = per_screen, clicks_per_page, refused
        self.visits: dict[Address, Visit] = {}
        self.kept: dict[str, int] = {}
        self.queue: deque[tuple[Address, str, int | None]] = deque()

    def _admit(self, address: Address, how: str) -> bool:
        if address in self.visits:
            return False
        if how != "requested" and self.kept.get(address.route, 0) >= self.per_screen:
            return False
        self.kept[address.route] = self.kept.get(address.route, 0) + 1
        return True

    def _home(self) -> Address:
        """The home page is wherever the router lands; with no hash, the table's first route."""
        landed = parse_fragment(self.page.evaluate("location.hash") or "", self.aliases)
        return landed or Address(route=next(iter(self.declared)))

    def _visit(self, address: Address, how: str, depth: int | None) -> None:
        from playwright.sync_api import ConsoleMessage  # read at registration, as `guard_writes` says

        errors: list[str] = []

        def listen(message: ConsoleMessage) -> None:
            if message.type == "error":
                errors.append(message.text)

        self.page.on("console", listen)
        _open(self.page, self.base_url, address)
        if not address.route:
            address = self._home()
            if not self._admit(address, how):
                self.page.remove_listener("console", listen)
                return
        visit = Visit(address=address, reached_by=how, depth=depth, contents=self.page.evaluate(_READ_PAGE))
        self.page.remove_listener("console", listen)
        visit.console_errors = errors
        self.visits[address] = visit
        for link in visit.contents["links"]:
            target = parse_fragment(link["href"] or "", self.aliases)
            # Skipped only when it is not also a route, so an element sharing a
            # route's name cannot hide that route's links.
            if link["inPage"] and (target is None or target.route not in self.declared):
                continue
            if target is not None:
                visit.links_to.append(target.fragment)
                self.queue.append((target, "link", None if depth is None else depth + 1))
        self._probe(visit, depth)

    def _probe(self, visit: Visit, depth: int | None) -> None:
        """Click a sample of the page's buttons, one fresh page per click, and keep those that navigate.

        Safe against the real library for the reason the whole tool is: the
        context refuses every write, so a button that would hang a theme or
        archive a work sends a request that never leaves the browser. A native
        dialog is dismissed. The page is reopened before each click, so no click
        sees the state an earlier one left.
        """
        if self.clicks_per_page <= 0:
            return
        candidates = self.page.evaluate(_PROBE_CANDIDATES, [self.per_screen, self.clicks_per_page])
        linked = set(visit.links_to)
        for index in candidates:
            _open(self.page, self.base_url, visit.address)
            before = self.page.evaluate("location.hash")
            already_refused = len(self.refused)
            said = self.page.evaluate(_PROBE_CLICK, index)
            if said is None:
                continue
            self.page.wait_for_timeout(250)
            # A write the click tried is expected (it was refused); tag it so it
            # is never read as a page that writes when it is merely viewed.
            for entry in self.refused[already_refused:]:
                entry["after_click"] = said
            after = self.page.evaluate("location.hash")
            target = parse_fragment(after or "", self.aliases)
            if after == before or target is None or (target.route == visit.address.route and target.ident == visit.address.ident):
                continue
            visit.buttons_to.append({"button": said, "to": target.fragment})
            if target.fragment not in linked:
                self.queue.append((target, "button", None if depth is None else depth + 1))

    def _drain(self) -> None:
        while self.queue:
            address, how, depth = self.queue.popleft()
            if not address.route or self._admit(address, how):
                self._visit(address, how, depth)

    def run(self, requested: Iterable[str]) -> dict[Address, Visit]:
        self.queue.append((Address(route=""), "home", 0))
        self._drain()
        reached = {address.route for address in self.visits}
        for route in self.declared.values():
            if route.key not in reached and route.detail != "required":
                self.queue.append((Address(route=route.key), "address", None))
        for fragment in requested:
            address = parse_fragment(fragment, self.aliases)
            if address is not None:
                self.queue.append((address, "requested", None))
        self._drain()
        return self.visits


def crawl(
    page: Page,
    base_url: str,
    aliases: dict[str, str],
    declared: dict[str, Route],
    *,
    per_screen: int,
    clicks_per_page: int = 0,
    refused: list[dict] | None = None,
    requested: Iterable[str] = (),
) -> dict[Address, Visit]:
    page.on("dialog", lambda dialog: dialog.dismiss())
    crawler = _Crawler(page, base_url, aliases, declared, per_screen, clicks_per_page, [] if refused is None else refused)
    return crawler.run(requested)


def _verified(source: bytes) -> bool:
    return hashlib.sha256(source).hexdigest() == AXE_SHA256


def _fetch_axe(cache: Path) -> tuple[str | None, str]:
    """axe-core, from the cache or cdnjs, and only if it is the pinned release byte for byte."""
    if cache.exists() and _verified(cache.read_bytes()):
        return cache.read_text(encoding="utf-8"), "cached"
    try:
        with urllib.request.urlopen(AXE_URL, timeout=20) as response:
            source = response.read()
    except (URLError, TimeoutError, OSError) as failure:
        return None, f"not run: axe-core could not be fetched ({failure})"
    if not _verified(source):
        return None, "not run: the axe-core fetched is not the pinned release (checksum differs)"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(source)
    return source.decode("utf-8"), "fetched"


def scan(page: Page, axe: str | None, why_not: str) -> tuple[str, list[dict]]:
    if axe is None:
        return why_not, []
    page.add_script_tag(content=axe)
    result = page.evaluate("async () => (await axe.run(document, {resultTypes: ['violations']})).violations")
    violations = [
        {
            "id": v["id"],
            "impact": v["impact"],
            "help": v["help"],
            "nodes": len(v["nodes"]),
            "targets": [" ".join(n["target"]) if isinstance(n["target"], list) else str(n["target"]) for n in v["nodes"][:5]],
        }
        for v in result
    ]
    return ("violations" if violations else "clean"), violations


#: Every (viewport, scheme) pair: the grid `docs/ux-walkthrough.md` asks for.
ALL_VARIANTS = tuple((viewport, scheme) for viewport in VIEWPORTS for scheme in SCHEMES)


def photograph(
    browser: Browser,
    base_url: str,
    walk: Walk,
    out: Path,
    *,
    placeholder: bytes | None,
    axe: tuple[str | None, str],
    variants: Iterable[tuple[str, str]] = ALL_VARIANTS,
) -> None:
    shots = out / "shots"
    shots.mkdir(parents=True, exist_ok=True)
    for viewport, scheme in variants:
        width, height = VIEWPORTS[viewport]
        context = browser.new_context(viewport={"width": width, "height": height}, color_scheme=scheme, bypass_csp=True)
        guard_writes(context, walk.refused_writes, placeholder=placeholder)
        page = context.new_page()
        for visit in walk.visits.values():
            settled = _open(page, base_url, visit.address)
            if settled != "blank":
                page.evaluate(_SCROLL_THROUGH)
                _settle(page, settle_ms=2000)
            name = f"{visit.address.slug}__{viewport}-{scheme}.png"
            page.screenshot(path=str(shots / name), full_page=True)
            capture = Capture(visit.address, f"{viewport}-{scheme}", f"shots/{name}", settled)
            capture.accessibility, capture.violations = scan(page, *axe)
            visit.captures.append(capture)
        context.close()


# ── Reading the walk ─────────────────────────────────────────────────────────


def summarise(walk: Walk) -> dict:
    reached_by_link = {a.route for a, v in walk.visits.items() if v.reached_by in {"home", "link"}}
    reached_by_button = {a.route for a, v in walk.visits.items() if v.reached_by == "button"}
    visited = {a.route for a in walk.visits}
    inbound: dict[str, int] = {}
    for visit in walk.visits.values():
        for target in {fragment.lstrip("#").split("?")[0].split("/")[0] for fragment in visit.links_to}:
            if target != visit.address.route:
                inbound[target] = inbound.get(target, 0) + 1
    return {
        "declared_not_reached_by_link": sorted(set(walk.declared) - reached_by_link),
        "reached_only_by_button": sorted(reached_by_button - reached_by_link),
        "declared_never_visited": sorted(set(walk.declared) - visited),
        "reached_not_declared": sorted(visited - set(walk.declared)),
        "pages_linking_in": dict(sorted(inbound.items())),
        "dead_ends": sorted(v.address.fragment for v in walk.visits.values() if not v.links_to and not v.buttons_to),
        "unsettled": sorted(
            {f"{c.address.fragment} ({c.settled})" for v in walk.visits.values() for c in v.captures if c.settled != "idle"}
        ),
        "refused_on_load": [entry for entry in walk.refused_writes if "after_click" not in entry],
        "refused_after_click": [entry for entry in walk.refused_writes if "after_click" in entry],
    }


def _jsonable(value: object) -> object:
    if isinstance(value, Address):
        return value.fragment
    if dataclasses.is_dataclass(value):
        return {f.name: _jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {(k.fragment if isinstance(k, Address) else k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def write_inventory(walk: Walk, out: Path) -> dict:
    inventory = {"summary": summarise(walk), **_jsonable(walk)}
    (out / "inventory.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")
    return inventory


def _scan_line(capture: Capture) -> str:
    if capture.accessibility != "violations":
        return capture.accessibility
    return "; ".join(f"{v['impact']} {v['id']} ×{v['nodes']}" for v in capture.violations)


def write_sheet(walk: Walk, inventory: dict, out: Path) -> None:
    """The contact sheet: every screen in a row, its four photographs across."""
    e = html.escape
    summary = inventory["summary"]
    rows = []
    for visit in sorted(walk.visits.values(), key=lambda v: (v.address.route, v.address.ident, v.address.query)):
        route = walk.declared.get(visit.address.route)
        name = f"{route.section} › {route.page}" if route and route.page else (visit.address.route or "home")
        a11y = " | ".join(f"{c.variant}: {_scan_line(c)}" for c in visit.captures)
        shots = "".join(
            f'<figure><a href="{e(c.image)}"><img loading="lazy" src="{e(c.image)}" alt="{e(c.variant)}"></a>'
            f"<figcaption>{e(c.variant)}{'' if c.settled == 'idle' else f' · {c.settled}'}</figcaption></figure>"
            for c in visit.captures
        )
        heads = " / ".join(h["text"] for h in visit.contents.get("headings", [])[:6])
        rows.append(
            f"<section><h2><code>{e(visit.address.fragment)}</code> {e(name)}</h2>"
            f"<p>reached by <b>{e(visit.reached_by)}</b>"
            f"{'' if visit.depth is None else f' at depth {visit.depth}'} · "
            f"{len(visit.contents.get('controls', []))} controls · {len(visit.links_to)} links out · "
            f"{len(visit.buttons_to)} navigating buttons · "
            f"headings: {e(heads) or '<i>none</i>'}</p>"
            f"<p>accessibility: {e(a11y)}</p>"
            + (f"<p class=warn>console errors: {e('; '.join(visit.console_errors))}</p>" if visit.console_errors else "")
            + f'<div class="shots">{shots}</div></section>'
        )
    findings = "".join(
        f"<li><b>{e(label)}</b>: {e(', '.join(summary[key]) or 'none')}</li>"
        for label, key in [
            ("Declared, not reached by any link", "declared_not_reached_by_link"),
            ("Reached only by a button, never a link", "reached_only_by_button"),
            ("Declared, never visited (needs an id no link supplied)", "declared_never_visited"),
            ("Reached, not declared", "reached_not_declared"),
            ("Pages with no way out but the sidebar's", "dead_ends"),
            ("Blank, or still busy, when photographed", "unsettled"),
        ]
    )
    on_load, after_click = len(summary["refused_on_load"]), len(summary["refused_after_click"])
    notice = (
        "<p class=warn>Synthetic corpus: every thumbnail is a flat placeholder, and every title is generated.</p>"
        if walk.placeholder_pictures
        else ""
    )
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>UX walk</title>
<style>
:root {{ --bg:#f6f4ef; --fg:#222; --muted:#666; --line:#ddd; --warn:#a33; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#1b1a18; --fg:#eee; --muted:#aaa; --line:#333; --warn:#f88; }} }}
body {{ background:var(--bg); color:var(--fg); font:14px/1.45 system-ui, sans-serif; margin:0 16px 48px; }}
h1 {{ font-size:22px; }} h2 {{ font-size:16px; margin:32px 0 4px; }} p {{ margin:2px 0; color:var(--muted); }}
.warn {{ color:var(--warn); }} section {{ border-top:1px solid var(--line); }}
.shots {{ display:flex; gap:12px; overflow-x:auto; padding:8px 0; align-items:flex-start; }}
figure {{ margin:0; flex:none; }} figure img {{ width:220px; border:1px solid var(--line); }}
figure:nth-child(-n+2) img {{ width:110px; }} figcaption {{ font-size:12px; color:var(--muted); }}
</style></head><body>
<h1>UX walk — {e(walk.base_url)}</h1>{notice}
<p>{len(walk.visits)} pages of {len(walk.declared)} declared routes · writes refused: {on_load} on viewing a page,
{after_click} after a probe click</p>
<ul>{findings}</ul>
{''.join(rows)}
</body></html>"""
    (out / "index.html").write_text(page, encoding="utf-8")


def run_walk(
    browser: Browser,
    base_url: str,
    out: Path,
    *,
    per_screen: int = 2,
    requested: Iterable[str] = (),
    synthetic: int | None = None,
    scan_accessibility: bool = True,
    variants: Iterable[tuple[str, str]] = ALL_VARIANTS,
    clicks_per_page: int = 30,
) -> dict:
    """The whole of Pass 1 against one running server. Returns the inventory it wrote."""
    out.mkdir(parents=True, exist_ok=True)
    declared = declared_routes(APP_JS.read_text(encoding="utf-8"))
    aliases = fragment_aliases(ROUTE_JS.read_text(encoding="utf-8"))
    walk = Walk(base_url=base_url, synthetic=synthetic, declared=declared, placeholder_pictures=synthetic is not None)
    placeholder = _placeholder_jpeg() if synthetic is not None else None

    context = browser.new_context(viewport={"width": 1440, "height": 900}, bypass_csp=True)
    guard_writes(context, walk.refused_writes, placeholder=placeholder)
    walk.visits = crawl(
        context.new_page(),
        base_url,
        aliases,
        declared,
        per_screen=per_screen,
        clicks_per_page=clicks_per_page,
        refused=walk.refused_writes,
        requested=requested,
    )
    context.close()

    axe = _fetch_axe(out / ".cache" / "axe.min.js") if scan_accessibility else (None, "not run: --no-axe")
    photograph(browser, base_url, walk, out, placeholder=placeholder, axe=axe, variants=variants)
    inventory = write_inventory(walk, out)
    write_sheet(walk, inventory, out)
    return inventory


# ── A synthetic server ───────────────────────────────────────────────────────


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def boot_synthetic(size: int) -> tuple[subprocess.Popen, str, Path]:
    """Seed a scratch ART_ROOT with the suite's large corpus and start the real entry point on it."""
    sys.path.insert(0, str(_CURATION / "src"))
    sys.path.insert(0, str(_CURATION / "tests"))  # the suite conftest's own imports (`fakes`, `fault_guard`)
    from arrt.config import CATALOGUE_FILENAME

    # The suite's corpus, never a copy of it. Loaded by path under a name of its
    # own, not `from conftest import`: under pytest, `conftest` in sys.modules is
    # whichever conftest was imported last (tests/browser's, in a full run), so
    # the bare import finds the wrong file depending on what else was collected.
    spec = importlib.util.spec_from_file_location("arrt_suite_conftest", _CURATION / "tests" / "conftest.py")
    suite = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(suite)
    _open_seeded_catalogue = suite._open_seeded_catalogue  # noqa: SLF001 -- the suite helper search_latency.py also uses

    root = Path(tempfile.mkdtemp(prefix="ux-walk-"))
    catalogue_file, _service, _works = _open_seeded_catalogue(root / CATALOGUE_FILENAME, size=size, seed=20260812)
    catalogue_file.close()
    port = _free_port()
    environment = {**os.environ, "ART_ROOT": str(root), "CURATION_HOST": "127.0.0.1", "CURATION_PORT": str(port)}
    server = subprocess.Popen([sys.executable, "-m", "arrt"], cwd=_CURATION, env=environment)
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if server.poll() is not None:
            shutil.rmtree(root, ignore_errors=True)
            raise RuntimeError(f"the synthetic server exited with {server.returncode} before it answered")
        try:
            urllib.request.urlopen(base_url + "/", timeout=1).close()  # noqa: S310 -- our own loopback http server
        except URLError, OSError:
            time.sleep(0.25)
        else:
            return server, base_url, root
    stop_synthetic(server, root)
    raise RuntimeError("the synthetic server did not answer within 60 seconds")


def stop_synthetic(server: subprocess.Popen, root: Path) -> None:
    """SIGTERM, never SIGKILL (CLAUDE.md, for the same server), then remove the scratch library."""
    try:
        server.send_signal(signal.SIGTERM)
        server.wait(timeout=30)
    finally:
        # The scratch library goes whether or not the server honoured SIGTERM;
        # one that did not is left for the caller to see in the raised timeout.
        shutil.rmtree(root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--base-url", help="A running Arrt to walk, e.g. http://localhost:8765")
    target.add_argument("--synthetic", type=int, metavar="N", help="Boot a throwaway Arrt over N synthetic works and walk it")
    parser.add_argument("--out", type=Path, required=True, help="Where the photographs, inventory.json and index.html go")
    parser.add_argument("--per-screen", type=int, default=2, help="How many instances of one route to keep. Default 2.")
    parser.add_argument("--visit", action="append", default=[], help="An extra address to photograph, e.g. '#search?q=monet'")
    parser.add_argument(
        "--clicks-per-page", type=int, default=30, help="Buttons to try per page for script navigation; 0 follows links only"
    )
    parser.add_argument("--no-axe", action="store_true", help="Skip the accessibility scan (reported as not run)")
    arguments = parser.parse_args()

    from playwright.sync_api import sync_playwright  # optional group; `--help` works without it

    server, root = None, None
    base_url = arguments.base_url.rstrip("/") if arguments.base_url else ""
    if arguments.synthetic:
        server, base_url, root = boot_synthetic(arguments.synthetic)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            inventory = run_walk(
                browser,
                base_url,
                arguments.out,
                per_screen=arguments.per_screen,
                requested=arguments.visit,
                synthetic=arguments.synthetic,
                scan_accessibility=not arguments.no_axe,
                clicks_per_page=arguments.clicks_per_page,
            )
            browser.close()
    finally:
        if server is not None and root is not None:
            stop_synthetic(server, root)
    summary = inventory["summary"]
    print(f"{len(inventory['visits'])} pages → {arguments.out / 'index.html'}")
    for key in (
        "declared_not_reached_by_link",
        "reached_only_by_button",
        "declared_never_visited",
        "reached_not_declared",
        "dead_ends",
        "unsettled",
    ):
        print(f"  {key}: {', '.join(summary[key]) or 'none'}")
    print(f"  writes refused on viewing a page: {len(summary['refused_on_load'])}")
    print(f"  writes refused after a probe click: {len(summary['refused_after_click'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
