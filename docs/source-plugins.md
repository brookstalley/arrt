# Writing a source plugin

For someone writing a plugin that finds or reads images for Arrt. The contract
the plugin is held to is `.prawduct/artifacts/source-plugins.md`, and what
installing one trusts is `.prawduct/artifacts/security-model.md` § Source
plugins. This page is how to write one against them. Deploying one into the
server's image is `deploy/README.md` § A private source plugin.

## A plugin is a distribution with one entry point

A plugin is an installable Python package that registers one entry point in the
`arrt.sources` group. The entry point's name is the plugin's name, and the
object it names is a `SourcePlugin`:

```toml
[project]
name = "arrt-gallery"
requires-python = ">=3.14"
dependencies = ["httpx"]

[project.entry-points."arrt.sources"]
gallery = "arrt_gallery:PLUGIN"
```

- **Pick a name no other installed plugin uses.** The built-ins are `commons`,
  `artic`, `met`, `navigart`, `smk` and `wikidata`. Two distributions registering one name load neither, so
  a plugin cannot replace a built-in by taking its name.
- **The name is permanent once rows carry it.** Every image the plugin's finder
  reports is stored under it, and acquisition and the health panel name the
  plugin by it.
- **Do not list `arrt` in `[project].dependencies`.** The server's image
  provides Arrt. The name `arrt` was unclaimed on PyPI when this was written
  (2026-10-03), so a resolver that did not find it installed would fetch
  whatever someone had published under it. Put it in a development group instead
  (§ Testing).

`SOURCE_ORDER` (comma-separated plugin names) sets which plugin wins a tie, and
plugins it does not name follow by name.

## The factory

```python
PLUGIN: Final = SourcePlugin(api_major=1, create=_create, claims=claims)
```

Arrt imports the module and calls `create` once at startup with a
`SourceContext`. The factory answers with `SourceParts` (any of a finder, a
reader and a collection), or with `Declined(reason)` when this deployment has not
configured the plugin.

- **Read your settings from `context.environ`**, never `os.environ`, and
  document the variables you read. A test can then build the plugin for a
  deployment that is not the process's own.
- **Decline rather than raise when a setting is missing.** The reason is logged
  at startup. A factory that raises is a load failure: Arrt starts without the
  plugin and names it on the health panel. The Art Institute's plugin declines
  without `ARTIC_USER_AGENT`.
- **The module is imported even when the factory declines**, and `claims` is
  called whether it loaded or not. Keep import free of I/O.
- `context.user_agent` is this deployment's `ACQUISITION_USER_AGENT`.
  `context.preview_max_bytes` bounds a preview read. `context.registry` is
  Wikidata, or `None` when the deployment has not named itself to it.

`api_major` is the interface major the plugin was written for. Today that is
`1` (`API_VERSION` is `(1, 1)`). Arrt refuses a plugin written for another major,
by name, and loads one written for an older minor, because a minor only adds
optional capabilities. 1.1 added `ImageQuery.pages`.

## Import from `arrt.library.sources` and nothing else

Everything a plugin needs is re-exported there: the factory types, `Finder`,
`FoundImage`, `FoundPage`, `ImageQuery`, `Reader`, `FetchLocator`,
`CollectionBrowse`, the exceptions, the registry types and the record enums.
Anything imported from elsewhere in `arrt` is not part of the interface and may
break in any release. Each type's contract is in its own docstring.

## What a plugin provides

At most one of each, in `SourceParts`:

| Part | Answers | Depends on |
|---|---|---|
| **finder** (`Finder`) | where is an image of this work? | the holder |
| **reader** (`Reader`, with `claims`) | given this page, how are its pixels got? | the protocol or page shape |
| **collection** (`CollectionBrowse`) | what does this collection offer to browse? | the holder |

### A finder

- `provider` returns the plugin's name. A plugin whose finder names another is
  not loaded, and an image reported under another name is a fault.
- `find_images(query)` returns `FoundImage`s, and `FoundPage`s for pages it found
  and does not read. `query.qid` is the work's Wikidata item when there is one.
- **`query.pages` (1.1) are the pages the run's web search read**, in its order.
  They are about the run's intent, not this one work: a search for an artist's
  paintings cites their gallery's artist page, so a finder that recognises a
  page looks for the work on it, and ignores every page it does not recognise.
  Arrt has checked each was a public http(s) address, and nothing more: what a
  page says is outside text. Read only pages of a shape you recognise, on that
  page's own host, and treat a page that is not the one expected as could not be
  asked. Empty for a Get.
- **`title` and `artist` are the holder's own words**, because the identity check
  judges them. Dimensions are the master's, never a preview's. Rights are
  recorded, never a reason to leave an image out.
- **An image read from a page the work's Wikidata item records is identified by
  that link**, under whatever title the holder gives it; the artist is still
  checked. It holds only when the image's `url` is the page exactly as the item
  spells it (`Registry.pages_about`), so a finder working from those pages records
  that address, not one of its own spelling. Anything else falls back to the title.
- `fetch_preview(url)` returns the preview's bytes or `None`, and **must stop
  reading at `context.preview_max_bytes`**: the URL and its redirects are a
  foreign service's choice.
- **A finder that offers only pages says so** with a class attribute
  `offers_images = False`. Arrt then never counts its answer as a source having
  answered, so a work only it answered for waits instead of being recorded as
  held by nobody. The Wikidata plugin is the example.

### A reader

- `claims(url)` is on the `SourcePlugin`, not the reader. It must be **static (no
  I/O and no settings) and narrower than a path**: check the host as well,
  because another site's `/objects/42` must not be sent to yours.
- **Claim only the URL shape your finder records.** Arrt sends a stored source to
  the first plugin that claims its URL, whoever found it. If another plugin reads
  the same holder another way (the public `met` reads the Met's API; a private
  plugin would read its web pages), two plugins claiming one shape would send one
  plugin's rows to the other's reader. So each records, and claims, its own
  (`source-plugins.md` § One holder, two plugins).
- `read(url)` returns `FetchLocator.direct(url)` (an image), `.tiles(url)` (a
  URL `dezoomify-rs` reads, such as a IIIF `info.json`), or `.none(reason)` (the
  page is the expected one and shows no image).
- A reader says how to fetch and never fetches the image itself.

## Three answers, and the page that is not the page

| Answer | Finder | Reader |
|---|---|---|
| holds nothing | an empty list | `FetchLocator.none(reason)` |
| could not be asked | raise `ImageSearchFailure` | raise `ImageSearchFailure` |
| cannot answer this kind of work | raise `ImageQueryUnanswerable` | `claims` returns `False` |

**A page that is not the page you expected is "could not be asked", never
"holds nothing."** A site that answers HTTP 200 with "This site is unavailable"
has told you nothing about what it holds. Check for the shape you expect, and
raise `ImageSearchFailure` when it is absent.

**Anything else you raise is a fault.** Arrt contains it to the call, logs it at
error with the traceback (`event=source.plugin_fault`), counts it on the health
panel, and records the call as could-not-be-asked. That keeps one broken plugin
from stopping a run. It is not a way to answer: a plugin that faults on every
call reads as a broken plugin on the panel.

## What Arrt does for you, and what it does not

**Arrt does:**

- fetch every locator a reader returns, after its own address check (http or
  https, a public address, no `.local` name) on the URL in the locator, with the
  size bounds and the tile cache. A direct fetch re-checks every redirect hop.
  A tiled fetch hands the checked URL to `dezoomify-rs`, which fetches the tiles
  that URL names itself;
- check the address of every page in `query.pages` before your finder sees it
  (the same check: http or https, a public address, no `.local` name), and drop
  one it refuses. That is one check, of the address as cited, at that moment;
- decide a work's identity, its rights record, duplicates, review, quality,
  spending and storage, so a plugin writes nothing;
- cut the query string from every URL in its log and on the health panel,
  including in the message of anything your plugin raises.

**Arrt does not check the requests your plugin makes itself**: the search in
`find_images`, the preview in `fetch_preview`, and any page `read` asks for. Your
code runs inside Arrt, with Arrt's network. So:

- ask only the hosts your plugin is about, and in `read`, only hosts `claims`
  accepts. A page in `query.pages` widens that to the page's own host, and no
  further: a redirect from it, and anything you read after it, are your requests
  and unchecked, so keep them on that host and bound them. The host's name can also answer differently when you look it up
  than when Arrt checked it, so a plugin that must never reach the LAN checks
  the address it connects to;
- bound every read;
- send `context.user_agent`, or your own setting where the site asks callers to
  identify themselves;
- put no key in a URL you raise or log. The log cuts query strings, but only
  from a URL that is encoded, as an HTTP client's own error is.

## Testing

**Install Arrt beside your plugin in a development group**, from the commit your
server's image is built from:

```toml
[dependency-groups]
dev = ["arrt", "pytest"]

[tool.uv.sources]
arrt = { git = "https://github.com/brookstalley/arrt", subdirectory = "arrt", rev = "<commit>" }
```

A development group is not part of the wheel's metadata, so the built plugin
still names no `arrt` dependency.

**Test your parts directly, with the HTTP client injected.** Let each part take an
`httpx.Client` and drive it through `httpx.MockTransport`, so the code under test
is the real parser against recorded answers. Cover the gap-5 page, and a URL on
another host that `claims` must refuse. A complete reader, with its tests:

```python
"""A reader for one gallery's object pages, as an Arrt source plugin."""

from typing import Final
from urllib.parse import urlsplit

import httpx

from arrt.library.sources import FetchLocator, ImageSearchFailure, SourceContext, SourceParts, SourcePlugin

_HOST: Final = "gallery.example.org"


def claims(url: str) -> bool:
    """An object page on the gallery's own host. Static: no I/O, no settings."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return (parts.hostname or "").lower() == _HOST and parts.path.startswith("/objects/")


class GalleryReader:
    def __init__(self, *, user_agent: str, client: httpx.Client | None = None) -> None:
        self._http = client or httpx.Client(timeout=20)
        self._headers = {"User-Agent": user_agent}

    def read(self, url: str) -> FetchLocator:
        try:
            response = self._http.get(url, headers=self._headers)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise ImageSearchFailure(f"The gallery could not be asked for {url}: {type(error).__name__}") from error
        page = response.text
        if 'class="object-record"' not in page:
            # Not the page this reader reads: an error page served with 200 is
            # "could not be asked", never "no image".
            raise ImageSearchFailure(f"{url} did not answer with an object record.")
        marker = 'data-iiif="'
        start = page.find(marker)
        if start == -1:
            return FetchLocator.none("The gallery's record shows no image of this object.")
        service = page[start + len(marker) : page.index('"', start + len(marker))]
        return FetchLocator.tiles(f"{service.rstrip('/')}/info.json")


def _create(context: SourceContext) -> SourceParts:
    return SourceParts(reader=GalleryReader(user_agent=context.user_agent))


PLUGIN: Final = SourcePlugin(api_major=1, create=_create, claims=claims)
```

```python
import httpx
import pytest

from arrt.library.sources import FetchLocator, ImageSearchFailure, LocatorKind
from arrt_gallery import PLUGIN, GalleryReader

PAGES = {
    "/objects/1": '<div class="object-record" data-iiif="https://iiif.example.org/1/"></div>',
    "/objects/2": '<div class="object-record"></div>',
    "/objects/3": "<p>This site is unavailable</p>",
}


def reader() -> GalleryReader:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=PAGES[request.url.path]))
    return GalleryReader(user_agent="test", client=httpx.Client(transport=transport))


def test_claims_only_the_gallerys_own_object_pages():
    assert PLUGIN.claims("https://gallery.example.org/objects/1")
    assert not PLUGIN.claims("https://elsewhere.example.com/objects/1")


def test_an_object_with_an_image_service_is_read_as_tiles():
    assert reader().read("https://gallery.example.org/objects/1") == FetchLocator.tiles("https://iiif.example.org/1/info.json")


def test_a_record_with_no_image_says_so():
    assert reader().read("https://gallery.example.org/objects/2").kind is LocatorKind.NONE


def test_a_page_that_is_not_a_record_could_not_be_asked():
    with pytest.raises(ImageSearchFailure):
        reader().read("https://gallery.example.org/objects/3")
```

**Then check that Arrt loads it**, from the entry points your installed package
registers:

```python
from arrt.library.sources import SourceContext
from arrt.library.sources.loading import load_sources

roster = load_sources(SourceContext(environ={}, user_agent="test", preview_max_bytes=1_000_000))
print([(reading.name, str(reading.state), reading.reason) for reading in roster.observe()])
```

Your plugin should read `loaded`, or `declined` with your reason. A typo in the
entry point passes every test of the parts and fails only here. (`loading` is
Arrt's, not the interface, which is why this check belongs in a script rather than
in the plugin.)

**The built-ins are the examples**, written against the same interface and held
to it by a test:

| Plugin | Shows | Its tests (`arrt/tests/unit/`) |
|---|---|---|
| `artic` (`arrt/src/arrt/library/sources/artic.py`) | a finder, a reader and a collection; declining without its setting; `claims` checking host and path | `test_artic_client.py`, `test_artic_browse.py` |
| `met` (`met.py`) | a finder that finds by item when a registry is configured and searches otherwise; a reader; `claims` taking only the URL shape it records; an image's size read from its header | `test_met_source.py` |
| `smk` (`smk.py`) | a finder that reads the item's own pages, of several spellings, and reports each image under the page exactly as the item spells it; `claims` taking those spellings and the API's object URL; rights read from the holder's own statement, in copyright included | `test_smk_source.py` |
| `navigart` (`navigart.py`) | a finder that reads only the item's own pages, of one platform serving many collections, with a static table saying which collection is asked where; a plugin that offers its reader alone when it has no registry to find with; a holder's surname-first name put in reading order for the identity check | `test_navigart_source.py` |
| `commons` (`commons.py`) | a finder that needs the registry and looks works up by item | `test_commons_source.py` |
| `wikidata` (`wikidata.py`) | a finder of pages only, with `offers_images = False` | `test_wikidata_pages.py` |
