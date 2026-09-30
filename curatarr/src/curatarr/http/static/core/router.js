/* Navigation: which screen is showing, which sidebar page is lit, and where back goes.
 *
 * **Pages in the *arr sidebar, and everything else contextual.**
 * `information-architecture.md` § Direction is the norm this implements: the
 * surface is laid out like the *arr apps, and `core/sidebar.js` draws the
 * sections this module lights.
 *
 * The route table itself lives in `app.js`, which is the only module that knows
 * every screen. This file holds the mechanism and no policy: it is handed the
 * table at boot and reads it thereafter. That is what lets a screen module be
 * added by editing two files — its own, and the table — with nothing sideways
 * between screens (`architecture.md` § Components & Responsibilities).
 *
 * A table entry is one of two shapes:
 *
 *   { render, section: "<key>", page: "<label>", detail? }  a sidebar page in that section
 *   { render, opensFrom: "<view>", detail? }                contextual; that is where it returns by default
 *
 * `detail` means the screen addresses one thing and carries its id in the
 * fragment. Held as data rather than as a chain of comparisons about which
 * screen is which: the dispatch, the fragment and the highlight all read it, and
 * three hand-written conditions are three chances for them to disagree.
 *
 * **`detail` has three values, not two, and the third is easy to miss from
 * here.** `true` means the id is required — the screen is not entered without
 * one. `OPTIONAL_ID`, exported by `core/route.js`, means the screen is an index
 * *and* an addressable detail: `#theme` and `#theme/<id>` are both it. Nothing
 * in this file distinguishes them, because everything here asks only whether
 * `detail` is truthy — which is what let the third mode arrive with no change to
 * this module, and is also why its shape list would otherwise go on describing
 * two. A new index-and-detail screen written from the list above with
 * `detail: true` gets its index address falling through to the product's home,
 * three files from the entry that caused it. `core/route.js` holds the grammar
 * and the reasoning.
 */

import { state } from "./state.js";
import { el, guard } from "./render.js";
import { formatRoute, parseRoute } from "./route.js";
import { installDrawer, lightSidebar, paintSidebar } from "./sidebar.js";

let table = {};
let home = null;
let announce = () => {};
let closeDrawer = () => {};

/* Which sidebar page a screen belongs to, for the highlight and for back.
 *
 * **A contextual screen returns to the page it was opened from, not to a fixed
 * parent.** That is the requirement — a Work opened from Review returns to
 * Review's page, the same Work opened from Artworks returns to Artworks — and
 * `params.from` is how it survives being bookmarked, reloaded
 * and sent to somebody else. A fixed parent is what this replaced: the old table
 * hard-coded `work → works` and `run → discovery`, so every route out of a
 * detail screen led to the same place however you had arrived.
 *
 * `opensFrom` is the fallback for a deep link that carries no opener, which is
 * every link an agent or a bookmark produces. It is a default, not a parent.
 *
 * **A sidebar page showing one of its things is contextual too.** `#theme` is
 * the Themes page; `#theme/<id>` is one theme, reached from a wall as often as
 * from the index, and it returns to whichever it was opened from. Its default
 * is its own index. */
export function pageFor(view = state.view, params = state.params, detailId = state.detailId) {
  const entry = table[view];
  if (!entry) return null;
  if (entry.page && !detailId) return view;
  const from = params && params.from;
  if (from && table[from] && table[from].page) return from;
  return entry.page ? view : entry.opensFrom || null;
}

/* Where a screen returns to when nothing says otherwise. */
function defaultReturn(view) {
  const entry = table[view];
  return entry.page ? view : entry.opensFrom;
}

/* The way back out of a contextual screen, named for where it goes.
 *
 * Named rather than a bare "Back" for the reason every wall control is named:
 * a control whose target the reader has to infer is one they can only check by
 * pressing it.
 *
 * **A sidebar page has no way back, because it is not inside anything** — its
 * way out is the sidebar. The exception is a page showing one of its things,
 * `#theme/<id>`, whose way back is its own index. */
export function backLink() {
  const page = pageFor();
  if (!page) return null;
  if (page === state.view && !state.detailId) return null;
  return el("button", {
    class: "action quiet",
    type: "button",
    text: `← ${table[page].page}`,
    onclick: () => go(page),
  });
}

/* The back link in the paragraph every screen sets it in, or nothing when the
 * screen is a sidebar page with nowhere to go back to. */
export function backRow() {
  const back = backLink();
  return back ? el("p", {}, [back]) : null;
}

/* The state a navigation carries over when the caller did not say.
 *
 * Opening a contextual screen records the page it was opened from, and that is
 * the whole of the return path. Arriving at a page carries nothing over: a
 * search made in Artworks is not a search Add New is running, and inheriting it
 * would put a filter on a screen that never offered one.
 *
 * **Omitted when it is the screen's own default**, which is the ordinary case:
 * a Work opened from Artworks, a Review opened from Add New. A parameter that
 * says what its absence already says is noise in a URL a curator copies, and it
 * changes nothing — `pageFor` resolves a missing `from` to exactly the
 * default this would have written. The parameter appears when it carries
 * information: this Work was opened from somewhere else. */
function inherited(view, detailId) {
  const entry = table[view];
  if (!entry || (entry.page && !detailId)) return {};
  const from = pageFor();
  return from && from !== defaultReturn(view) ? { from } : {};
}

export function go(view, detailId = null, params = null) {
  const entry = table[view];
  const next = params === null ? inherited(view, detailId) : params;
  state.view = view;
  state.detailId = detailId;
  state.params = next;
  // Leaving a view invalidates any refresh it had scheduled, so a run page left
  // open does not keep repainting behind whatever replaced it — and discards
  // what was painted, since the DOM that record describes is about to go.
  //
  // The `nav` bump here is load-bearing only on the path that does NOT change
  // the hash — navigating to the screen already displayed, which is what
  // clicking the current page does. Every other path writes the fragment
  // and re-enters through `readHash`, which bumps it again. Written down because
  // a mutation sweep survives its removal: the cross-screen case is covered, and
  // this is the narrow one that is not, so the next reader should not take the
  // survivor for proof that the line does nothing.
  state.nav += 1;
  state.poll += 1;
  state.painted = null;
  const hash = formatRoute(view, entry && entry.detail ? detailId : null, next);
  if (window.location.hash !== hash) {
    window.location.hash = hash;
    return; // hashchange re-enters here
  }
  refresh(true);
}

/* A `goWithParams(changes)` helper stood here and was called by nothing — a
 * mutation sweep survived gutting it, which is what an exported convenience with
 * no caller looks like from the outside. Changing one piece of the addressable
 * state is `go(state.view, state.detailId, { ...state.params, ...changes })`,
 * and the one caller that does it — the masthead search — writes it out, where
 * the rule about which state survives a search is written beside it. The helper
 * belongs to whichever chunk builds the second caller. */

export function refresh(moveFocus = false) {
  const entry = table[state.view];
  lightSidebar(pageFor());
  // The top bar's status indicator and search box, repainted on every
  // navigation. Registered by `app.js` rather than imported, because the
  // indicator navigates and the router would then import the thing that imports
  // it. It is called before the screen's own paint so the chrome is never a
  // navigation behind what it sits above.
  announce();
  // Captured here, before the view starts, so it is the navigation that
  // commissioned this paint rather than whatever is current when it finishes.
  const generation = state.nav;
  const done = guard(
    entry.detail ? () => entry.render(state.detailId, generation) : () => entry.render(generation),
  );
  if (moveFocus) {
    // Navigating replaces the whole view, which destroys the control that was
    // focused — leaving focus on <body>, so the next Tab starts from the top of
    // the page. Sending it to the new view is what makes the surface navigable
    // by keyboard at all. Not done on first paint: stealing focus from a
    // freshly loaded page is its own bug.
    done.then(() => document.getElementById("view").focus());
  }
  return done;
}

export function readHash() {
  const route = parseRoute(window.location.hash, table, { path: window.location.pathname, fallback: home });
  state.view = route.view;
  state.detailId = route.id;
  state.params = route.params;
  // An address that meant something else — `#works`, `#manifest` — is rewritten
  // to what it resolved to, so the URL a curator copies from the bar is the one
  // this surface would produce. `replaceState` rather than assigning the hash:
  // assigning would fire `hashchange` and re-enter here, and it would put the
  // old spelling in the history so Back landed on it and bounced forward again.
  // Only when there is a fragment to correct — a path deep link has no hash and
  // acquiring one is not a correction.
  if (window.location.hash) {
    const canonical = formatRoute(route.view, route.id, route.params);
    if (window.location.hash !== canonical) window.history.replaceState(null, "", canonical);
  }
  // A fragment change is a navigation like any other, and the screen being left
  // may have had a refresh scheduled over a page it is about to lose.
  state.nav += 1;
  state.poll += 1;
  state.painted = null;
}

/* The skip link moves focus past the sidebar and leaves the address alone.
 *
 * Every `#…` is an address to this router, so a plain `href="#view"` would be a
 * link to a page called "view" — which does not exist, and falls back to the
 * home page. The link keeps its `href` for anything that reads it, and the
 * click does the skip instead. */
function installSkipLink() {
  document.querySelector(".skip-link").addEventListener("click", (event) => {
    event.preventDefault();
    document.getElementById("view").focus();
  });
}

/* `sections` is the sidebar's list, in order; see `core/sidebar.js`.
 *
 * **The home page is the first sidebar page in the table**, and is the one
 * place it is decided: an address that names nothing lands there. As in every
 * *arr app, that is the library. */
export function install(routes, { sections, onNavigate } = {}) {
  table = routes;
  home = Object.keys(table).find((view) => table[view].page);
  if (onNavigate) announce = onNavigate;
  paintSidebar(table, sections, (view) => {
    closeDrawer();
    go(view);
  });
  closeDrawer = installDrawer();
  installSkipLink();
  window.addEventListener("hashchange", () => {
    readHash();
    refresh(true);
  });
  readHash();
  refresh();
}
