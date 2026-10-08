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
  // Opened from a screen that is itself a place to return to: the sidebar lights
  // whatever that screen belongs to.
  const opener = returnTarget(from);
  if (opener) return pageFor(opener.view, {}, opener.id);
  return entry.page ? view : entry.opensFrom || null;
}

/* A contextual screen a curator can be returned to, named in `?from=` with its id.
 *
 * `information-architecture.md` § Navigation Structure: "a Work opened from
 * Review returns to Review". A sidebar page is returned to by its name alone; a
 * screen about one thing needs the thing too, so `from` carries `view/id`. Only a
 * screen whose table entry declares `returnLabel` is one, which keeps the
 * address from recording an opener for every hop between contextual screens —
 * and only for the screens its `returnFor` names, because Review also opens Run,
 * and Run has its own way back. */
function returnTarget(from) {
  if (!from || !from.includes("/")) return null;
  const slash = from.indexOf("/");
  const view = from.slice(0, slash);
  const id = from.slice(slash + 1);
  return table[view] && table[view].returnLabel && id ? { view, id } : null;
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
  const opener = returnTarget(state.params && state.params.from);
  if (opener) return returning(opener.view, opener.id, `← ${table[opener.view].returnLabel}`);
  const page = pageFor();
  if (!page) return null;
  if (page === state.view && !state.detailId) return null;
  return returning(page, null, `← ${table[page].page}`);
}

/* A way back that is the browser's Back when that is where it goes.
 *
 * When the entry before this one is the screen the link names, the click goes
 * back to it — the same list, with its filters and its sort, scrolled where it
 * was and with the card that was opened in focus (`rememberPlace`). A new entry
 * at the same address would start at the top. Otherwise — a bookmark, a link
 * from somewhere else — it is the plain link to the screen. Captured so it is
 * decided before `link`'s own click handler, which then stands aside. */
function returning(view, id, text) {
  const node = link({ view, id }, { class: "action quiet", text });
  node.addEventListener(
    "click",
    (event) => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const came = window.history.state && window.history.state.came;
      if (!came) return;
      const before = parseRoute(came, table, { fallback: home });
      if (before.view !== view || (before.id || null) !== (id || null)) return;
      event.preventDefault();
      window.history.back();
    },
    { capture: true },
  );
  return node;
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
 * search made in Artworks is not a search Ask is running, and inheriting it
 * would put a filter on a screen that never offered one.
 *
 * **Omitted when it is the screen's own default**, which is the ordinary case:
 * a Work opened from Artworks, a Run opened from Queue. A parameter that
 * says what its absence already says is noise in a URL a curator copies, and it
 * changes nothing — `pageFor` resolves a missing `from` to exactly the
 * default this would have written. The parameter appears when it carries
 * information: this Work was opened from somewhere else. */
function inherited(view, detailId) {
  const entry = table[view];
  if (!entry || (entry.page && !detailId)) return {};
  const here = table[state.view];
  if (here && here.returnLabel && state.detailId && (here.returnFor || []).includes(view)) {
    return { from: `${state.view}/${state.detailId}` };
  }
  const from = pageFor();
  return from && from !== defaultReturn(view) ? { from } : {};
}

/* What a contextual screen opened with parameters of its own must still carry:
 * its opener. `go` with parameters uses exactly those, so a caller that has a
 * query to pass and a return path to keep merges this in. */
export function openedFrom(view, detailId = null) {
  return inherited(view, detailId);
}

/* The address `go` would write for this navigation, for a link to carry. */
export function hrefFor(view, detailId = null, params = null) {
  const entry = table[view];
  const next = params === null ? inherited(view, detailId) : params;
  return formatRoute(view, entry && entry.detail ? detailId : null, next);
}

/* A navigation, as `information-architecture.md` § Direction requires one:
 * an `<a href="#…">`, so it opens in a new tab, copies as an address, previews
 * in the status bar and is announced as a link.
 *
 * `target` is `{ view, id, params }`, read as `go` reads its arguments: a
 * missing `params` inherits the opener, as every `go` without them does.
 *
 * **A plain click still goes through `go`.** Following a link to the address
 * already showing fires no `hashchange`, and the click is also where the place
 * being left is remembered, with the link itself as the thing Back refocuses —
 * a pointer press does not focus a link in every browser, so the active
 * element cannot be trusted to name it. A click with a modifier, or any other
 * button, is the browser's: a new tab or window, or a download. */
export function link(target, attrs = {}, children = []) {
  const { view, id = null, params = null } = target;
  return el(
    "a",
    {
      href: hrefFor(view, id, params),
      ...attrs,
      onclick: (event) => {
        if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        navigate(view, id, params, event.currentTarget);
      },
    },
    children,
  );
}

/* Remember, on the history entry being left, where its page was scrolled and
 * which link left it — so Back can put the curator where they were, on the card
 * they opened, rather than at the top of a list sixty-eight Tabs from it.
 *
 * Kept in `history.state` because that is the entry's own: it survives Back and
 * Forward and goes when the entry does, which a table keyed by address would
 * not — two entries can share an address and mean two different scrolls.
 *
 * The link is recorded as its address and which of the links carrying that
 * address it was, because a card can reach one work by its picture and its
 * title, and the one opened is the one Back refocuses. */
function rememberPlace(opener) {
  const view = document.getElementById("view");
  const candidate = opener || document.activeElement;
  const left = candidate && candidate.matches && candidate.matches("a[href]") && view.contains(candidate) ? candidate : null;
  let opened = null;
  if (left) {
    const href = left.getAttribute("href");
    const same = [...view.querySelectorAll("a[href]")].filter((node) => node.getAttribute("href") === href);
    opened = { href, index: same.indexOf(left) };
  }
  window.history.replaceState({ ...(window.history.state || {}), scrollY: window.scrollY, opened }, "");
}

/* The address this client is navigating away from, until the new entry has
 * arrived and been told it (`came`, which `returning` reads). */
let leaving = null;

export function go(view, detailId = null, params = null) {
  navigate(view, detailId, params, null);
}

function navigate(view, detailId, params, opener) {
  const entry = table[view];
  const next = params === null ? inherited(view, detailId) : params;
  rememberPlace(opener);
  const from = formatRoute(state.view, state.detailId, state.params);
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
    leaving = from;
    window.location.hash = hash;
    return; // hashchange re-enters here
  }
  // The screen already showing, asked for again: a fresh arrival, at the top.
  shown = null;
  refresh(true);
}

/* Replace the screen being drawn with another, in place: the address is
 * rewritten rather than added to, so Back skips the one that only forwarded.
 *
 * For a page that learns, once it has asked, that it is the wrong page: a work
 * reached by its Wikidata id that the library holds belongs on the library's own
 * Work page. `go` would leave the forwarding address in the history, and Back
 * would land on it and be sent forward again. The opener (`?from=`) is kept, so
 * the page that replaces it returns where this one would have. */
export function redirect(view, detailId) {
  const entry = table[view];
  window.history.replaceState(null, "", formatRoute(view, entry && entry.detail ? detailId : null, state.params));
  readHash();
  return refresh(true);
}

/* Change some of the addressable state of the screen that is showing.
 *
 * `go(state.view, state.detailId, { ...state.params, ...changes })`, named
 * because the Artworks toolbar has four callers of it — View, Sort, Filter, and
 * the note that brings hidden filters back. An empty value removes a key, as
 * `formatRoute` omits it. The top-bar search still writes its own, because the
 * rule about which state survives a search belongs beside it. */
export function goWithParams(changes) {
  go(state.view, state.detailId, { ...state.params, ...changes });
}

/* What the last paint showed, as `view/id`, so a refresh can tell arriving at
 * a screen from repainting the one already there. */
let shown = null;

/* The product's name, after the page's in every title, as the *arr apps write
 * theirs: the page is what a tab strip, a bookmark and a history list need to
 * tell apart, and every one of them used to read "Arrt". */
const PRODUCT = "Arrt";

function titled(name) {
  return `${name} - ${PRODUCT}`;
}

/* A screen's title before it knows what it is showing: its sidebar label, or
 * the `title` a contextual route declares. */
function routeTitle(entry) {
  return entry.title || entry.page;
}

/* Name the page after the thing a detail screen shows, once it knows it — the
 * work's title, the artist's name. `generation` is the paint's own, as
 * `render` takes it, so a paint that lost its view cannot retitle the one that
 * replaced it. */
export function setTitle(generation, name) {
  if (generation !== state.nav || !name) return;
  document.title = titled(name);
}

export function refresh(moveFocus = false, { arrival = null } = {}) {
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
  const here = `${state.view}/${state.detailId || ""}`;
  const arrived = here !== shown;
  shown = here;
  if (arrived) document.title = titled(routeTitle(entry));
  const restoring = moveFocus && arrival && typeof arrival.scrollY === "number";
  // A new screen starts at its top. Without this the page kept the scroll of
  // the one it replaced, so a work opened from low on a list opened at its
  // sources table. Done now rather than after the paint, so the new screen is
  // never seen part-way down. A change of state on the same screen — a sort,
  // a filter — keeps the curator where they were, as any act on a page does.
  if (moveFocus && arrived && !restoring) window.scrollTo(0, 0);
  // A change of state on the same screen — a facet, a theme in the rail —
  // repaints the control that made it, and focus would fall to the view's top,
  // a Tab sequence away from where the curator was. The control's key is what
  // finds it again in the new paint.
  const keep = moveFocus && !arrived ? focusKey(document.activeElement) : null;
  const done = guard(
    entry.detail ? () => entry.render(state.detailId, generation) : () => entry.render(generation),
  );
  if (moveFocus) {
    // Navigating replaces the whole view, which destroys the control that was
    // focused — leaving focus on <body>, so the next Tab starts from the top of
    // the page. Sending it to the new view is what makes the surface navigable
    // by keyboard at all. Not done on first paint: stealing focus from a
    // freshly loaded page is its own bug.
    //
    // `preventScroll`, because focusing a view taller than the window scrolls
    // it, and where the page sits is decided above, not by the focus.
    done.then(() => {
      if (generation !== state.nav) return;
      const kept = keep && keyed(keep);
      if (kept) {
        kept.focus({ preventScroll: true });
        return;
      }
      if (restoring) {
        window.scrollTo(0, arrival.scrollY);
        const opened = openedLink(arrival.opened);
        if (opened) {
          opened.focus({ preventScroll: true });
          return;
        }
      }
      document.getElementById("view").focus({ preventScroll: true });
    });
  }
  return done;
}

/* A control that keeps the keyboard across a repaint of its own screen says so
 * with `data-focus-key`, unique on the page: a facet option by its kind and
 * value, a theme option by its id. Its text cannot be the key, since the count
 * in it is what the repaint changes. */
function focusKey(node) {
  const view = document.getElementById("view");
  if (!node || !view || !view.contains(node)) return null;
  return node.dataset ? node.dataset.focusKey || null : null;
}

function keyed(key) {
  const view = document.getElementById("view");
  return [...view.querySelectorAll("[data-focus-key]")].find((node) => node.dataset.focusKey === key && !node.disabled) || null;
}

/* The link a remembered entry was left by, on the page Back has repainted. */
function openedLink(opened) {
  if (!opened || !opened.href) return null;
  const view = document.getElementById("view");
  const same = [...view.querySelectorAll("a[href]")].filter((node) => node.getAttribute("href") === opened.href);
  return same[opened.index] || same[0] || null;
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
    if (window.location.hash !== canonical) window.history.replaceState(window.history.state, "", canonical);
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
  // The scroll a history entry is returned to is this module's to decide
  // (`rememberPlace`): the browser's own restoration runs before the screen has
  // repainted, against a page that is not yet the one it remembers.
  window.history.scrollRestoration = "manual";
  window.addEventListener("hashchange", () => {
    // A new entry this client made records the address it came from, which is
    // how a way back knows the entry behind it is where it leads.
    if (leaving !== null && !window.history.state) window.history.replaceState({ came: leaving }, "");
    leaving = null;
    readHash();
    // The entry arrived at: one this client left, by Back or Forward, carries
    // where it was; a new one carries nothing and starts at the top.
    refresh(true, { arrival: window.history.state });
  });
  readHash();
  refresh();
}
