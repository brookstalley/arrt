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

Today's `ImageSearch` (`library/discovery/images.py`) does both: the Art
Institute's client searches *and* resolves its own tiles (`tile_url`), and
acquisition picks a resolver by the provider's name (`RESOLUTION_REQUIRED`,
`tile_targets` in `library/acquisition/tiles.py`). This contract separates them.

## Three layers

| Layer | Owner | Input → output | Examples |
|---|---|---|---|
| **Finder** | a plugin, per holder; or the Wikidata finder, for every holder Wikidata records | a work → candidate URLs, with what the holder calls the work and the size where known | the Art Institute's search API; an Artlogic site's artist page; Wikidata's holder IDs |
| **Reader** | a plugin, per protocol or page shape | a URL it recognises → how to fetch the image, its size, and the holder's title and artist | a Commons file page; an Art Institute object (resolved to IIIF); a IIIF manifest; a Google Arts & Culture asset |
| **Fetcher** | Arrt, never a plugin | a fetch locator → the master, on disk | direct HTTP; tiles through `dezoomify-rs` |

A plugin provides any of finders, readers and a collection to browse
(`CollectionBrowse`, `library/discovery/browse.py`, which the Art Institute
offers today). It provides no fetcher. *Mine:* plugins that serve the image's
bytes themselves (paid, local, or behind a login) are the planned next
capability, and come with the first plugin that needs one (§ Not in version 1).

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
- Dimensions are the **master's**, never a preview's.
- Rights are recorded, never a reason to leave an image out.

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
3. The item's image (P18) gives a Commons file page. This is what the Commons
   source does today, which makes it a Wikidata finder result read by the Commons
   reader.

*Measured 2026-10-03, on five corpus rows chosen by hand from the museum-page
rows (not a random sample):* all five carry a holder's page. MoMA (P2014) is on
rows 22, 34 and 42, the Pompidou (P6323 and P6355) on row 4, and SFMOMA (P973)
on row 48. Some items also carry pages that are not holders: the Athenaeum
(P4144) and HA! (P13023) are reproduction sites. A reader judges what it
recognises; the finder offers every page.

**Pages no reader claims are recorded, not dropped** (§ Sightings).

**These URLs never reach the curator's browser.** A formatter URL is
registry-supplied, and `security-model.md` § Direction allows an outside link
only to a host this repository names or built from a checked identifier. A page
the Wikidata finder builds is fetched by the server, and the client is shown a
source by name.

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
readings the stored rows allow; acting on question 2 waits for the upgrade loop
(the parked spike on `feature/upgrades`, #177 and #178).
Anything a sighting stores is decided by those three, and no other column is
added for an imagined consumer.

## Loading

- **A plugin is a Python distribution** that registers an entry point in the
  `arrt.sources` group. The entry point names a factory: given a
  `SourceContext`, it returns the plugin's finders, readers and collection, or
  declines with a reason (an Art Institute plugin with no `ARTIC_USER_AGENT`
  declines, exactly as the source is left unwired today).
- **The built-in plugins register the same way**, from `arrt/pyproject.toml`.
  Nothing in the wiring imports them by name, so they are proof that the loader
  works, and they are the examples a plugin author copies.
- **What `SourceContext` gives a plugin:** the deployment's user agent; the
  preview size ceiling; the registry, when one is configured (the Commons reader
  needs none, but the Wikidata finder does); and the environment, read-only, for
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
- **A source recorded by a plugin that is no longer installed** is a deployment
  fault at acquisition, not a failure of that source: "the plugin `artic` is not
  installed". This generalises today's `RESOLUTION_REQUIRED`: no source is at
  fault, and the remedy is in this deployment. Its rows keep their provider
  names unchanged, so reinstalling the plugin reaches them again.

## Trust

**A plugin is trusted code.** It runs inside Arrt with everything Arrt can reach:
the catalogue, the OpenRouter key, the wall tokens. Arrt neither vets nor
sandboxes it. Installing one is the operator's trust decision, of the same kind
as accepting a PyPI wheel (`security-model.md` § Supply Chain). The owner chose
this over a separate service, which would have isolated it.

What still holds, because Arrt keeps it rather than trusting a plugin to:

- **A plugin's text is outside text.** Titles, artists and descriptions reach the
  page as text (`security-model.md` § Direction) and the model under the existing
  prompt-injection bounds, the same as a museum's.
- **Arrt fetches every locator**, through the address checks and read bounds.
- **Arrt decides** a work's identity, its rights record, duplicates, review,
  quality, spending and storage. A plugin answers "what images exist, and where",
  and writes nothing.

## Versioning and errors

- **`arrt.sources.API_VERSION`** is `major.minor`, starting at `1.0`. A plugin
  declares the major it was written for; Arrt refuses to load one whose major
  differs, by name, and loads one written for an older minor. A minor release adds
  optional capabilities only. *Mine.*
- **`arrt.sources` is the only import path a plugin may use.** It re-exports the
  types above. Anything a plugin imports from elsewhere in `arrt` is not part of
  the interface and may break in any release. A test holds the built-in plugins to
  this, because they are what authors copy.
- **The error model** is the three answers and the fault above.

## Deploying a private plugin

On the NAS, Arrt is an image built from a commit (`arrt/Dockerfile`). A private
plugin reaches it through an image built on top of that one: `FROM arrt:<commit>`,
then the plugin installed into `/opt/venv`. The plugin's dependencies must
resolve beside Arrt's locked ones, which is the cost of loading in-process. That
derived image's recipe lives in the private repository, beside the plugin. This
repository's `deploy/README.md` shows the shape.

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
- **Pasting a URL.** Readers already claim URLs, so it needs a surface, not a
  new contract.
- **Watches** following a page (`re-architecture.md` § Procurement).
- **Readers for new protocols**: IIIF in general, Google Arts & Culture,
  Artlogic. Which comes first is what the sightings count. Under the owner's
  ruling, a reader for a site whose terms forbid scraping lives in the private
  repository. A IIIF reader has no such problem, because IIIF is an open
  standard served for reuse, so it can be public.
