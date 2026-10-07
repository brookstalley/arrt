# Met API Findings

Captured 2026-10-06 by probing the Metropolitan Museum of Art's collection API
before writing the `met` source plugin (`arrt/src/arrt/library/sources/met.py`).
Everything below is **measured**, with a generic agent string, except where a line
says it is read from the Met's documentation (`metmuseum.github.io`). The durable
form is `arrt/tests/live/test_met_shapes_are_still_real.py` (`live_museum`), and
the recorded answers the unit suite reads are `arrt/tests/fixtures/met/`.

## Access

- No key and no account. The documentation asks for at most 80 requests a second.
- Base: `https://collectionapi.metmuseum.org/public/collection`. Served through
  Imperva, which set cookies on every answer; none is needed for the next request.

## Search moved on 2026-10-01

- `GET /v1/search` now answers with a message that it was **retired on
  2026-10-01**, naming `/v1.1/search` as the replacement. Anything recalled about
  the Met's search from before then is about the retired endpoint.
- `GET /v1.1/search` takes the old filters (`q`, `title`, `artistOrCulture`,
  `hasImages`, `medium`, `dateBegin`/`dateEnd`, …) plus `offset` and `limit`
  (default 100, maximum 500, per the documentation). It answers
  `{"total": n, "objectIDs": [...]}`, and `{"total": 0, "objectIDs": null}` for no
  match.
- **The order is not relevance for a broad query.** `title=true&q=Window` (886
  objects) came back as 13585, 17523, 194459, 285724, …: ascending ids. A specific
  title is small enough not to matter (`Wheat Field with Cypresses`, 1 object).
- `title=true` restricts to titles: `Cypresses` found 8, among them van Gogh's
  *Cypresses* (437980), Ikeda Koson's *Cypresses* (53426, public domain, with an
  image) and Walker Evans photographs.
- `artistOrCulture=true&q=<artist>` finds an artist's objects: Robert Delaunay 7,
  Vincent van Gogh 38 (both with `hasImages=true`).
- `hasImages=true` includes in-copyright objects whose images the API does not
  give (five Ellsworth Kelly objects, all `primaryImage: ""`).

## The object record

- `GET /v1/objects/<id>`. `/v1.1/objects/<id>` is HTTP 404.
- Fields read: `objectID`, `title`, `artistDisplayName`, `isPublicDomain`,
  `primaryImage` (the original, `…/original/…`), `primaryImageSmall`
  (`…/web-large/…`, 599 × 477 for *Wheat Field with Cypresses*). Also present and
  unread: `additionalImages`, `objectURL` (the web page), `objectWikidata_URL`,
  `measurements`.
- **An in-copyright object has empty image fields** (`isPublicDomain: false`,
  `primaryImage: ""`), though the Met's web page shows its picture.
- An unknown id is HTTP 404 with `{"message": "ObjectID not found"}`.

## The image host

- Images are on `https://images.metmuseum.org/CRDImages/...`.
- **No pixel size is given anywhere in the API.** The host honours `Range`
  (HTTP 206, `accept-ranges: bytes`). *Wheat Field with Cypresses*' original is
  8,291,194 bytes, 4000 × 3184, and its start-of-frame segment begins at byte
  40,798, behind its metadata segments.
- **It answers HTTP 406 to `Accept: application/json`**, the header the API's
  requests carry. An image is asked for with `Accept: image/*`. Found by the live
  test on its first run, after the unit suite had passed.

## The web pages

- `https://www.metmuseum.org/art/collection/search/<id>` answered a plain client
  with HTTP 429 and a "Vercel Security Checkpoint" page. Reading them needs a
  browser, which is a private plugin's job (`source-plugins.md` § One holder, two
  plugins).
- **In a browser the checkpoint passes, and in-copyright works are web-size at
  most** (measured 2026-10-06 in camoufox, with requests to `www.metmuseum.org`
  only; each page took 1–8 s). The page's embedded data lists each image with
  `originalImageUrl`, `iiifSourceImageUrl`, `webImageUrl` and their sizes, plus
  `isOasc`, `isRestricted` and `isThumbnail`. For Kelly's *Blue Green Red*
  (489307, restricted), the named original (3629 × 4000) is HTTP 404, the IIIF
  source is 544 × 600, and `web-large` on the image host (not named for it) is
  567 × 625. Warhol's *Untitled from Marilyn Monroe* (398902) and Sonia Delaunay's
  *Prose on the Trans-Siberian Railway* (822544) are thumbnail-only, at 150 × 148
  and 84 × 150, under every name. An open-access work (436535) names its full
  original. The private reader was built anyway, by the owner's choice, to
  picture wanted works (`build-plan-wanted-pictures.md`).

## Wikidata

- P3634 (The Met object ID) has two formatter URLs: the web page (preferred rank)
  and `https://collectionapi.metmuseum.org/public/collection/v1/objects/$1`
  (normal rank). Its pattern is `[1-9][0-9]{0,8}`.
- `Registry.pages_about` reads `wdt:P1630`, best rank only, so it gives the web
  page. *Wheat Field with Cypresses* is Q18689458, and its Met page is found from
  it (live test).

## What this means for today's library

On 2026-10-06, 36 works were open with no image from any source. Three are held
by the Met (Kelly's *Blue Green Red*, Warhol's *Marilyn*, Sonia Delaunay's *Prose
on the Trans-Siberian Railway*), and all three are in copyright, so this API fills
none of them. Its value is public-domain works that later Asks propose.
