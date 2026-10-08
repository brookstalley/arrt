/* The fetch plumbing: one request helper and the two loops that page to the end.
 *
 * Everything that talks to `/api/*` goes through here, which is what keeps the
 * refusal-versus-fault distinction below written once rather than per screen.
 */

export async function api(path, options) {
  let response;
  try {
    response = await fetch(path, {
      headers: { "content-type": "application/json" },
      ...options,
    });
  } catch (failure) {
    // No answer at all: the server is down or the network dropped. Marked,
    // because the browser's words for it ("Failed to fetch", "Load failed")
    // differ per browser and say nothing a curator can act on, and because a
    // write that got no answer may or may not have happened (`core/acting.js`).
    failure.unanswered = true;
    throw failure;
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    // The service layer writes its refusals to be shown; anything else is a
    // fault, and saying which is which beats one apologetic sentence for both.
    const message =
      body && body.error
        ? body.error
        : `The server answered ${response.status} for ${path}.`;
    const failure = new Error(message);
    // Carried so a screen can tell a refusal it expects (an address naming
    // nothing) from a fault, which belongs in the error banner.
    failure.status = response.status;
    throw failure;
  }
  return body;
}

/* The theme picker and an artist's held works page through to the end rather
 * than showing the first page. The picker is the one that made this necessary: a
 * truncated picker means a curator simply cannot put work 101 in a theme, and is
 * told nothing about why.
 *
 * **Artworks no longer does.** `nonfunctional-requirements.md` moved the design
 * target to **thousands** on 2026-08-10 and calls fetching the whole catalogue
 * "indefensible at 4,000", and `PAGE_CEILING` stopped the grid at 1,250 works.
 * Artworks now loads a page at a time as the curator scrolls (`fetchWorksPage`,
 * `build-plan-lists-settings-and-scale.md` Chunk 07), so every work is reachable
 * and the ceiling does not apply to it. What follows describes the callers that
 * still walk to the end.
 *
 * **No `limit` is sent**, which is the same rule `fetchAllCandidates` states
 * below and for the same reason. This asked for `limit=100` — a copy of the
 * service's `MAX_LIST_LIMIT` — until 2026-08-05, and that copy was a live break
 * waiting on an unrelated edit: `list_artworks` *refuses* a limit above its cap,
 * the refusal arrives as a 400, and `api()` throws. So the day anyone lowered
 * the catalogue's cap, the Artworks grid — the default landing view at the
 * time — and the theme picker would have failed outright while the review grid,
 * which asks for nothing, kept paging.
 *
 * The cost is paid knowingly: the server's default page is smaller than its cap,
 * so this makes more round trips than asking for the maximum would. They are
 * against a loopback server on the same box.
 *
 * `PAGE_CEILING` is a runaway guard, not a policy. If it is ever hit the caller
 * reports how many were left out, because a cap nobody mentions is the silent
 * omission this product exists to refuse. */
export const PAGE_CEILING = 50;

/* The chosen facet values, as `GET /api/works` spells them.
 *
 * **One repeated parameter per kind, never comma-joined.** That is the route's
 * own rule and its reason is the data: a facet value may itself contain a comma,
 * and a separator a value can hold is a parser that goes wrong on the catalogue
 * rather than on the request. A kind with nothing chosen contributes nothing, so
 * an unfiltered grid sends the request it always sent. */
function facetQuery(chosen) {
  let query = "";
  for (const kind of Object.keys(chosen || {})) {
    for (const value of chosen[kind] || []) {
      query += `&${encodeURIComponent(kind)}=${encodeURIComponent(value)}`;
    }
  }
  return query;
}

/* The narrowing and order `GET /api/works` is asked for, as its query string.
 *
 * Sent to the server rather than filtered here. `GET /api/works` takes `q` and
 * searches the work's own text and its artist's name word-wise, over the whole
 * catalogue — where a client-side filter can only ever search what this screen
 * happened to load, and reports its count as though it had searched
 * everything. The facets are sent for the same reason, and for one more: the
 * counts beside the grid are computed by the service against exactly this
 * filter, and a client that narrowed locally would print them beside a
 * different set of works.
 *
 * The order is the server's to apply, for the reason the search is: paging a
 * set the client sorted would sort only what had arrived. One artist's works,
 * and only those in circulation, are the Artist page's *In your library*; one
 * theme's works are Artworks' Theme filter. All narrow on the server, which
 * composes them. */
function worksFilter(query, chosen, sort, { artistId = null, status = null, theme = null, notOnWall = false } = {}) {
  return (
    (query ? `&q=${encodeURIComponent(query)}` : "") +
    facetQuery(chosen) +
    (sort ? `&sort=${encodeURIComponent(sort)}` : "") +
    (artistId ? `&artist_id=${encodeURIComponent(artistId)}` : "") +
    (status ? `&status=${encodeURIComponent(status)}` : "") +
    (theme ? `&theme=${encodeURIComponent(theme)}` : "") +
    (notOnWall ? "&not_on_wall=true" : "")
  );
}

/* The same narrowing as a body, for an act on every work it matches: the
 * `filter` the selection routes take (`POST /api/works/archive`, a theme's
 * `works/bulk` and `works/remove`). One function beside `worksFilter` so the
 * grid and *Select all* cannot come to mean different works. */
export function worksFilterBody(query, chosen, sort, { artistId = null, status = null, theme = null, notOnWall = false } = {}) {
  const body = {};
  if (query) body.q = query;
  for (const kind of Object.keys(chosen || {})) {
    if ((chosen[kind] || []).length) body[kind] = [...chosen[kind]];
  }
  if (sort) body.sort = sort;
  if (artistId) body.artist_id = artistId;
  if (status) body.status = status;
  if (theme) body.theme = theme;
  if (notOnWall) body.not_on_wall = true;
  return body;
}

/* The facet and theme controls for a filter, without its works: one page of
 * one work, since the counts come with every page. For a screen that changed
 * the works under its rail in place and must recount it. */
export async function fetchFilterCounts(query = "", chosen = null, { theme = null, notOnWall = false } = {}) {
  const body = await api(`/api/works?limit=1${worksFilter(query, chosen, null, { theme, notOnWall })}`);
  return { total: body.total, facets: body.facets || [], themes: body.themes || [], fits: body.fits || [], not_on_wall: body.not_on_wall || null };
}

/* One page of works at `offset`, with the counts that come with every page.
 *
 * For Artworks, which pages from the server as the curator scrolls rather than
 * walking to `PAGE_CEILING` (`build-plan-lists-settings-and-scale.md` Chunk 07,
 * #131): every work is reachable, however many there are. No `limit` is sent,
 * for the reason `fetchAllWorks` sends none; the page size is read back from
 * the answer's own `limit`. */
export async function fetchWorksPage(query = "", chosen = null, sort = null, options = {}, offset = 0) {
  return api(`/api/works?offset=${offset}${worksFilter(query, chosen, sort, options)}`);
}

/* The works from `from` up to `upTo`, `pageSize` at a time, a few pages at once.
 *
 * For Back to Artworks, which reloads as many works as were on screen when it
 * was left, so card 900 is still card 900 and the scroll lands on it. The pages
 * are asked for together, a few at a time, since their offsets are known from
 * the first; they are kept in offset order, and the first page that comes back
 * short or saying there is no more ends it (`exhausted`). */
export async function fetchWorksFrom(query, chosen, sort, options, from, upTo, pageSize) {
  const works = [];
  const step = Math.max(1, pageSize || 1);
  const offsets = [];
  for (let offset = from; offset < upTo; offset += step) offsets.push(offset);
  const AT_ONCE = 4;
  for (let start = 0; start < offsets.length; start += AT_ONCE) {
    const pages = await Promise.all(offsets.slice(start, start + AT_ONCE).map((offset) => fetchWorksPage(query, chosen, sort, options, offset)));
    for (const body of pages) {
      works.push(...body.works);
      if (!body.truncated || body.works.length < step) return { works, exhausted: true };
    }
  }
  return { works, exhausted: false };
}

/* `onFirstPage(body)` is called once, with the first page, before the loop asks
 * for a second — so a caller can act on `total` and `truncated` while the rest is
 * still arriving. The grid's loading placeholder needs exactly that: its geometry
 * depends on how much there is, which nothing knows until this page lands, and a
 * placeholder painted before it can only guess. Optional, and the two other
 * callers pass nothing. */
export async function fetchAllWorks(query = "", chosen = null, onFirstPage = null, sort = null, { artistId = null, status = null, theme = null, notOnWall = false } = {}) {
  const works = [];
  let total = 0;
  let truncated = false;
  // The facet groups come from the first page only. Every page recomputes them
  // identically — `list_artworks` answers the works and their counts in one read
  // scope precisely so the two cannot disagree — so keeping a later page's copy
  // would be the same numbers arrived at more slowly.
  let facets = [];
  // The theme options, from the first page for the reason the facets are.
  let themes = [];
  // The clean-up facets, from the first page for the same reason.
  let fits = [];
  let notOnWallOption = null;
  const filter = worksFilter(query, chosen, sort, { artistId, status, theme, notOnWall });
  for (let page = 0; page < PAGE_CEILING; page += 1) {
    const body = await api(`/api/works?offset=${works.length}${filter}`);
    total = body.total;
    if (page === 0) {
      facets = body.facets || [];
      themes = body.themes || [];
      fits = body.fits || [];
      notOnWallOption = body.not_on_wall || null;
      if (onFirstPage) onFirstPage(body);
    }
    works.push(...body.works);
    // The stopping condition is what actually arrived, not what the server says
    // is left. A page that reports more while carrying nothing makes no
    // progress — the offset is derived from what came back, so asking again
    // sends the identical request. `PAGE_CEILING` would stop it either way, so
    // what this saves is forty-nine pointless round trips rather than a hang.
    if (!body.truncated || body.works.length === 0) return { works, total, truncated, facets, themes, fits, not_on_wall: notOnWallOption };
    truncated = true;
  }
  return { works, total, truncated: works.length < total, facets, themes, fits, not_on_wall: notOnWallOption };
}

/* Every work a run holds, paged through to the end.
 *
 * No `limit` is sent, so the server's own default and cap govern and the client
 * holds no copy of either. Asking for the cap explicitly would put the number in
 * two places, and the day the service lowered it the grid would ask for more
 * than it allows and be refused outright. */
export async function fetchAllCandidates(runId) {
  const works = [];
  let run = null;
  let total = 0;
  for (let page = 0; page < PAGE_CEILING; page += 1) {
    const body = await api(`/api/runs/${encodeURIComponent(runId)}/candidates?offset=${works.length}`);
    run = body.run;
    total = body.total;
    works.push(...body.works);
    // Same stopping condition as `fetchAllWorks`, and the same reason: a page
    // reporting more while carrying nothing makes no progress, so asking again
    // sends the identical request. The ceiling bounds it regardless; this is
    // what keeps a misbehaving page from costing fifty round trips.
    if (!body.truncated || body.works.length === 0) break;
  }
  return { run, works, total };
}
