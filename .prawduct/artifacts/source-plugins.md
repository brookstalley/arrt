# Source Plugins

Started 2026-10-03. How Arrt finds and reads images through plugins: what a
plugin is, what it may provide, what Arrt keeps for itself, and how the
interface changes over time.

**Who decided what.** The owner ruled that sources are plugins, that a plugin is
a Python package loaded inside Arrt, that the Art Institute and Commons are the
examples, and that plugins are per protocol (`re-architecture.md` § Sources are
plugins). The owner agreed the split between finding and reading below. The
rest, every name, rule and decision marked *mine*, is the agent's (2026-10-03)
and open to challenge as such.

## Finding and reading are different jobs

Getting an image of a work takes two steps, and they depend on different
things:

- **Finding** answers *where is an image of this work?* It depends on the
  **holder**: only MoMA knows what MoMA holds.
- **Reading** answers *given that page, how do I get the pixels?* It depends on
  the **protocol** or the **page's shape**: a IIIF image service, a Google Arts &
  Culture page, an Artlogic gallery page, an Art Institute object, a Commons
  file.

Every finder ends in a URL, and readers claim URLs. So a URL from any route
(a finder, a pasted link, the model's web search) reaches the same readers.

Until 2026-10-03 one protocol, `ImageSearch`, did both: the Art Institute's
client searched *and* resolved its own tiles (`tile_url`), and acquisition picked
a resolver by the provider's name (`RESOLUTION_REQUIRED`, `tile_targets`). This
contract separates them: `Finder` (`library/discovery/images.py`) only finds, and
a `Reader` (`library/sources/reading.py`) only reads.

## Three layers

| Layer | Owner | Input → output | Examples |
|---|---|---|---|
| **Finder** | a plugin, per holder; or the Wikidata finder, for every holder Wikidata records | a work → candidate images, with what the holder calls the work and the size where known; and pages it found and does not read (`FoundPage`) | the Art Institute's search API; an Artlogic site's artist page; Wikidata's holder IDs |
| **Reader** | a plugin, per protocol or page shape | a URL it claims → how to fetch the image (§ Fetch locators) | an Art Institute object (resolved to IIIF); later a IIIF manifest, a Google Arts & Culture asset |
| **Fetcher** | Arrt, never a plugin | a fetch locator → the master, on disk | direct HTTP; tiles through `dezoomify-rs` |

A plugin provides at most one finder, at most one reader (which may read many
URL shapes), and at most one collection to browse (`CollectionBrowse`,
`library/discovery/browse.py`, which the Art Institute offers today). It provides
no fetcher. *Mine:* one finder, because the images it reports are recorded under
the plugin's own name, so a stored row names the plugin that found it; one
reader, because which URLs it reads is declared once, on the plugin (§ Which
plugin reads a URL). *Mine:* plugins that serve the image's
bytes themselves (paid, local, or behind a login) are the planned next
capability, and come with the first plugin that needs one (§ Not in version 1).

### Which plugin reads a URL

A plugin declares `claims(url)`: static, with no I/O and no configuration, so
Arrt can ask it of a plugin that declined as well as one that loaded. Acquisition
routes a stored source by its URL, never by the provider that recorded it:

- **claimed by a loaded plugin:** its reader decides the fetch;
- **claimed by a plugin installed and not loaded:** a deployment fault naming the
  plugin and its own reason (`SourcePluginUnavailable`). This is the Art
  Institute without `ARTIC_USER_AGENT`;
- **claimed by none:** fetched as recorded, as before plugins. This covers the
  2024 seed's Google Arts & Culture rows and Commons' direct image URLs, which
  need no plugin.

**One exception uses the provider.** A plugin that failed before Arrt got a
`SourcePlugin` from it (an import error, an entry point naming something else, a
name two distributions share) has no `claims` to ask. A row recorded under its
name, and claimed by no other plugin, is then a deployment fault naming it.
That is stricter than for a declined plugin, whose `claims` can be asked. A row
recorded under a broken plugin that claims nothing, as Commons claims nothing,
pauses too, though it would fetch as recorded. What a broken plugin claims cannot
be known, and pausing names the fault, records nothing against the source, and
clears once the plugin loads. *Mine,* 2026-10-03, after review found an Art
Institute row going to the tile fetcher, which cannot read an object page, and
being recorded as a failed source.

A source whose provider is not installed at all cannot be told apart from a 2024
seed provider (`google_arts_culture` was never a plugin), so it is fetched as
recorded and journalled (`acquisition.unclaimed`). A claims check must be
narrower than a path: the Art Institute's checks the museum's hosts as well as
`/artworks/<id>`, because another site's `/artworks/91194` must not be sent to
the museum.

### Fetch locators

A reader answers with one of:

- **direct**: an image URL Arrt fetches over HTTP;
- **tiles**: a URL `dezoomify-rs` can read (a IIIF `info.json`, a Google Arts &
  Culture page, and the other formats it supports);
- **none**: the page is the one the reader expected, and it shows no image.

Arrt fetches every locator itself, through the existing guards (`check_fetchable`
in `library/acquisition/urls.py`, the size bounds, the tile cache). So a plugin
author gets the address checks and the read bounds without having to remember
them.

### What a finder or reader must report

The `FoundImage` rules hold unchanged for every plugin:

- `title` and `artist` are **the holder's own words**, because they are the
  evidence the identity check judges. A finder that returns only URLs leaves
  nothing to check.
- An image whose `url` is, exactly, a page the work's Wikidata item records
  (`Registry.pages_about`) passes the title comparison under the holder's own
  title; the artist comparison still runs. Added 2026-10-04 by the owner's ruling,
  for MoMA's *Composition* (`data-model.md`, the phase-2 identity notes). The
  MoMA plugin's page address is the P2014 formatter's, so it needs no change.
- Dimensions are the **master's**, never a preview's.
- Rights are recorded, never a reason to leave an image out.

### Pages a search read

Added 2026-10-05 for gallery works, which have no Wikidata item and so no
holder page a QID gives (`build-plan-ask-pages.md`). Ask's phase 1 searches the
web, and the search cites the pages it read; measured, a search for an artist's
paintings cites the gallery's artist page, not a page per work
(`procurement-corpus.md` § The probe: Artlogic, and what Ask's search cites).

- **The pages are the run's citations, never an address from the model's
  answer.** A structured answer can name an address nobody served, or one an
  injected page asked it to name; a citation is a page the search engine read.
- **Stored with the run** (`data-model.md` § RunCitation), so approval, a
  re-search and a restart all hand the same pages.
- **Every work the run proposed is asked with all of them**, because they are
  about the intent, not one work. A finder reads only pages of a shape it
  recognises and finds the work on them.
- **Arrt checks each page's address before a finder sees it** (`check_fetchable`:
  http(s), a public address, no `.local` name) and drops one it refuses. A
  plugin's own requests are unguarded, so this is the one check these addresses
  get (`security-model.md` § Source plugins).
- **A Get has none.** It searches nothing on the web.

### Three answers, plus a fault

A plugin's call ends in one of three answers, as the pool keeps them today
(`library/discovery/pool.py`):

| Answer | Means | Raised as |
|---|---|---|
| **holds nothing** | asked, and there is nothing | an empty result |
| **could not be asked** | down, refused, or answered with something other than the page expected | `ImageSearchFailure` |
| **cannot answer this kind of work** | this finder cannot look up a work like this one, or this reader does not recognise the URL | `ImageQueryUnanswerable`; a reader returns *not mine* |

**A page that is not the page expected is "could not be asked", never "holds
nothing"** (the procurement corpus's gap 5: gerhard-richter.com answers HTTP 200
with "This site is unavailable"). Every finder and reader checks for the shape it
expects and raises when it is absent.

**A fault is anything else a plugin raises.** *Mine:* Arrt contains it to the one
call, records it as "could not be asked" for that plugin, and logs it at error
with the traceback (`event=source.plugin_fault`, naming the plugin). The health
panel counts each plugin's faults since startup, so a plugin failing every call
is not read as "nobody holds these works". The catch carries the broad-except
waiver with this reason (`project-preferences.md`). Today the
pool lets any other exception propagate, which fails the run. That was right
when every source was Arrt's own code and a fault meant a bug the suite should
see. With plugins, one faulty package would otherwise stop every run. The suites
keep the old strictness by failing any test in which `source.plugin_fault` is
logged.

## The Wikidata finder

For a work with a QID, Arrt itself finds the holders' pages, with no search:

1. Every external-identifier claim on the item whose property carries a
   formatter URL (Wikidata's P1630) gives a page: MoMA's work ID (P2014) and
   `https://www.moma.org/collection/works/$1` give MoMA's page.
2. Every "described at URL" claim (P973) gives a page.

**It offers pages, never images** (`FoundPage`, `library/discovery/images.py`).
A page is known only by its address, and whether it shows the work, how large and
under what title is what phase 2 judges, so a page with none of that cannot be an
image. Arrt gives each page to the installed plugins' `claims`: a page none
claims is a sighting (§ Sightings), and a page a plugin claims is journalled and
left to that plugin, whose own finder is how its images are found. Turning a
claimed page into an image needs a reader that reports the image's size and the
holder's words, which is the paste-URL addition (§ Not in version 1).

**A finder of pages says so, and is never counted as a source that answered.**
Its class carries `offers_images = False` (a `bool`; a finder without one offers
images, so one written before this needs no change). An answer from it says
nothing about whether an image of the work exists, so a work only it answered
for waits, as when no source can be asked (`NoSourceCanAnswer`), instead of
being recorded as held by nobody. **Nor is one that could not be asked counted
as a source that might hold the image:** it holds none either way, so the image
sources' answers stand. **A roster whose only finders find pages gives phase 2
no source** (`SourceRoster.finds_images`). The wiring, the previews setting and
the startup line all read that one property, so such a deployment refuses a
re-search as one with no source does, instead of accepting work it can never
settle. *Mine,* 2026-10-03, after review found the gap: with the Art
Institute unconfigured and Commons not loaded, the Wikidata finder's answer alone
would have recorded works as held by nobody.

**The item's image (P18) stays the Commons finder's**, read as an image with its
size, as before plugins. *The owner's choice, 2026-10-03,* over two others: the
Wikidata finder taking P18, which would put Commons' size rule in two plugins
that may not import each other; and readers reporting size now, which changes
both sides of the interface. So no Commons reader exists, and stored Commons
rows, which are direct image URLs, are fetched as recorded.

*Measured 2026-10-03, on five corpus rows chosen by hand from the museum-page
rows (not a random sample):* all five carry a holder's page. MoMA (P2014) is on
rows 22, 34 and 42, the Pompidou (P6323 and P6355) on row 4, and SFMOMA (P973)
on row 48. Some items also carry pages that are not holders: the Athenaeum
(P4144, now reached only through `web.archive.org`) and HA! (P13023) are
reproduction sites, and items carry encyclopedias, catalogues raisonnés and a
Google search link (P646, from Freebase) too. A reader judges what it recognises;
the finder offers every page. So the sightings count below includes hosts that
hold nothing, and is read with that in mind.

**A page is built and checked by the registry client** (`pages_about`,
`library/registry/wikidata.py`). The identifier is percent-encoded into the
formatter as Wikibase encodes it, and the result is kept only if it is an
`http(s)` URL with a host, with no whitespace or control character and at most
2048 characters. A formatter with no `$1` names no page. That is all the checking
it gets, because it never reaches the browser.

**Pages no reader claims are recorded, not dropped** (§ Sightings).

**These URLs never reach the curator's browser.** A formatter URL is
registry-supplied, and `security-model.md` § Direction allows an outside link
only to a host this repository names or built from a checked identifier. A page
the Wikidata finder builds is kept by the server, and fetched only through a
reader and Arrt's own guarded fetch; the client is shown its host, by name.

## Sightings

A page the Wikidata finder found and no installed reader claimed is a
**sighting**: evidence that the holder has a page for the work, which no plugin
here can read yet.

They are stored because of the questions they answer:

1. **Which reader should be built next?** Count sightings by host, over works
   that are `wanted` or unresolved. That turns the procurement corpus's step 3
   from a hand count into a query.
2. **When a plugin is installed, which works can it reach now?** Re-offer every
   sighting the new reader claims, with no new search. Installing a plugin then
   improves the library at once, which is what the upgrade loop needs.
3. **Where else has this work been seen?** For a work's own page: other holders,
   as upgrade candidates.

The first plan stores sightings and answers question 1. Questions 2 and 3 are
readings the stored rows allow. Acting on question 2 waits for the upgrade loop
(the parked spike on `feature/upgrades`, #177 and #178), and for a reader that
reports an image's size (§ The Wikidata finder).
Anything a sighting stores is decided by those three, and no other column is
added for an imagined consumer.

**What is stored** (`sightings`, `data-model.md` § Sighting): the work's
Wikidata item and the page's URL, once per pair. The host, for question 1, and
whether a plugin installed since claims the page, for question 2, are both read
from the URL. *Mine:* keyed by the item, because the item is the only key the
finder that offers pages has, and a work is one item across every run that
proposed it. A page offered for a work with no item is journalled, not stored.

**Question 1, as built** (`GET /api/sightings/hosts`,
`art_review(action='sighting_hosts')`): each host, with how many open works it
has a page for, most first. *Mine:* open means wanted, or unresolved with the
verdict still pending; a work the catalogue holds is left out, and so is a page
an installed plugin claims now. A sighting is recorded from a search attempt that
answered. Phase 2 raises for one that could not be asked, and that attempt's
pages are lost with it; a later search of the work records them.

## Loading

- **A plugin is a Python distribution** that registers an entry point in the
  `arrt.sources` group. The entry point names a factory: given a
  `SourceContext`, it returns the plugin's finder, reader and collection, or
  declines with a reason (an Art Institute plugin with no `ARTIC_USER_AGENT`
  declines, exactly as the source is left unwired today).
- **The built-in plugins register the same way**, from `arrt/pyproject.toml`.
  Nothing in the wiring imports them by name, so they are proof that the loader
  works, and they are the examples a plugin author copies.
- **What `SourceContext` gives a plugin:** the deployment's user agent
  (`ACQUISITION_USER_AGENT`); the
  preview size ceiling; the registry, when one is configured (the Commons and
  Wikidata finders need it); and the environment, read-only, for
  the plugin's own settings. A plugin documents its own environment variables,
  and the built-ins keep the names deployments already set (`ARTIC_USER_AGENT`,
  `WIKIDATA_USER_AGENT`).
- **Order.** Every finder is asked at once, and order only breaks ties, as the
  pool does today. The built-in order stands (Commons, then the Art Institute,
  the owner's ruling of 2026-10-01). *Mine:* `SOURCE_ORDER`, a comma-separated
  list of plugin names, sets it; plugins it does not name follow, by name.
- **Two readers claiming one URL:** the one first in that order reads it.
- **A plugin that fails to load does not stop Arrt.** *Mine:* an import error, a
  factory that raises, or an incompatible version is logged at error with the
  plugin's name, and Arrt starts without it. A wall that goes dark because a
  plugin broke after an upgrade is worse than a missing source, and the startup
  log already names what loaded. The health panel says so too, because panel-only
  alerting is this product's chosen channel (`observability-strategy.md`), and a
  source missing in silence would look like works nobody holds.
- **A source whose plugin is installed and not loaded** is a deployment fault at
  acquisition, not a failure of that source; one whose plugin is not installed at
  all is fetched as recorded (§ Which plugin reads a URL says why the two differ).
  Rows keep their provider names unchanged, so reinstalling a plugin reaches its
  rows again.

## Trust

**A plugin is trusted code.** It runs inside Arrt with everything Arrt can reach,
and Arrt neither vets nor sandboxes it. The owner chose this over a separate
service, which would have isolated it. What installing one trusts, what Arrt
still keeps for itself, and how a plugin's error text is scrubbed are
`security-model.md` § Source plugins, their one home.

## Versioning and errors

- **`arrt.library.sources.API_VERSION`** is `major.minor`, starting at `1.0`. A plugin
  declares the major it was written for; Arrt refuses to load one whose major
  differs, by name, and loads one written for an older minor. A minor release adds
  optional capabilities only. *Mine.*
- **1.1 (2026-10-05) added `ImageQuery.pages`**, the pages the run's phase-1
  web search read (§ Pages a search read).
- **`arrt.library.sources` is the only import path a plugin may use.** It lives
  under `arrt.library` rather than at the top level because the Library/Programming
  import guard (`tests/preferences/test_seam_imports.py`) walks only `arrt.library`,
  and a plugin importing Programming must be inside what it walks. It re-exports the
  types above. Anything a plugin imports from elsewhere in `arrt` is not part of
  the interface and may break in any release. A test holds the built-in plugins to
  this, because they are what authors copy.
- **The error model** is the three answers and the fault above.

## Deploying a private plugin

On the NAS, Arrt is an image built from a commit (`arrt/Dockerfile`). A private
plugin reaches it through an image built on top of that one: `FROM arrt:<commit>`,
then the plugin installed into `/opt/venv`, constrained to Arrt's locked versions.
The plugin's dependencies must resolve beside Arrt's locked ones, which is the cost
of loading in-process; without the constraint, the installer would change Arrt's
instead. That derived image's recipe lives in the private repository, beside the
plugin. This repository's `deploy/README.md` § A private source plugin shows the
shape, and `docs/source-plugins.md` is the guide for writing one.

## Considered: 3tears scrape (2026-10-03)

The owner asked whether Arrt should use or contribute to `3tears-scrape`, in
core or in a plugin. Read at 3tears `origin/develop` `ffa128c0` (0.60.0); the
agent's verdict, for the owner to overturn: **neither, for now.**

- **It solves a different problem.** It extracts structured *records* from pages
  (its working example tracks WARN Act notices on state labour sites), using a
  model to propose and judge extraction recipes. It has no image extraction at
  all: no `og:image`, `srcset`, IIIF or tiles (searched; no matches).
- **It cannot be taken in part.** Its required dependencies include 3tears core
  (NATS client, asyncpg, SQLAlchemy), `3tears-models`, `3tears-agent-tools`,
  camoufox and Playwright, all pinned to the same 3tears minor version, and it is
  async throughout. That reverses the reasons Arrt declined 3tears core and kept
  `3tears-models` out of the default install (`3tears-integration-findings.md`
  § Consequence for this product). As a private plugin it would put all of that
  into `/opt/venv`, and break with each 3tears minor release.
- **A scrape service behind a thin plugin** would only pay off for a site that
  needs a real browser to get past a bot wall. None of the readers in view
  (Artlogic, IIIF, museum pages, Google Arts & Culture through `dezoomify-rs`)
  needs one. Revisit if a source does.

**Ideas taken from it, not code.** Its `challenge.py` keeps "the page was never
received" apart from "the page changed", which this contract's could-not-be-asked
rule already does; Arrt's check stays a cheap structural one, not a model call.
Its per-target fetch health matches what acquisition outcomes and sightings record
per host.

**What Arrt could contribute back:** scrape checks a URL's address once, then its
drivers follow redirects unchecked. Arrt's direct fetch re-checks every redirect
hop (`library/acquisition/transport.py`, `http_stream`). Offering that upstream is
the owner's call.

## Not in version 1

Each waits for the first plugin that needs it, so that it is built against a real
case:

- **A plugin serving the image's bytes itself**, for paid, local or logged-in
  sources: the `api` fetch method (`AcquisitionMethod.API`, which the code
  records as having no producer).
- **Metered spending.** A plugin that costs money per call would report its cost
  so that Arrt can *record* it. The ceiling stays with the paid service's own
  account limit, never in Arrt or the plugin, because
  `nonfunctional-requirements.md` § Direction holds that spend ceilings are
  enforced by the provider, never by application code. A plugin on a flat
  subscription needs nothing.
- **Pasting a URL.** Readers already claim URLs, so it needs a surface and one
  addition to the reader's answer: the image's size and the holder's own title
  and artist. A source a finder found already carries those; a pasted URL does
  not, and the identity check needs them. *Mine:* added with the paste surface
  (a minor version), not before, since nothing would read them.
- **Watches** following a page (`re-architecture.md` § Procurement).
- **Readers for new protocols**: IIIF in general, Google Arts & Culture,
  Artlogic. Which comes first is what the sightings count. Under the owner's
  ruling, a reader for a site whose terms forbid scraping lives in the private
  repository. A IIIF reader has no such problem, because IIIF is an open
  standard served for reuse, so it can be public.
