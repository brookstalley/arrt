/* Artworks — everything acquired, in one place, with the organising beside it.
 *
 * The home page, as the library is in every *arr app, at the address
 * `#collection` it had before the rename; and the page that has to survive
 * thousands of works. `information-architecture.md` § Information Hierarchy is
 * what this implements: the grid of images is the primary content, the counts
 * and the active filters are secondary, and the rails that narrow it sit beside
 * the works.
 *
 * Four things here are decisions rather than layout, and each is written down at
 * the place it takes effect:
 *
 *   - **Density is a control, not a decision.** Posters, Overview and Table, in
 *     the toolbar's View menu, with the default chosen from how much there is
 *     and the choice held in the address so a reload and a shared link both
 *     land on it.
 *   - **A control never offers a dead end.** Every facet option carries the count
 *     it would select, and an option that would select nothing is disabled rather
 *     than removed — a vocabulary that shrinks as filters are applied reads as
 *     data loss.
 *   - **Three empty states, not one.** Nothing held, nothing matching a filter,
 *     and nothing by one named artist are three different facts leading to three
 *     different next moves.
 *   - **Organising happens against the works being organised.** A theme is one
 *     more filter in the rail, composing with the facets and the search, and a
 *     selection is added to a theme, a new one included, taken out of the theme
 *     being filtered, or archived in *Select* mode — the one selection model
 *     every list shares (`core/selecting.js`) — in place, without leaving the
 *     screen.
 *
 * What is deliberately NOT here: reordering a theme (which is about the theme
 * rather than about the works, and lives on the Theme screen).
 */

import { attempt } from "../core/acting.js";
import { fetchFilterCounts, fetchWorksFrom, fetchWorksPage, worksFilterBody } from "../core/api.js";
import { absentImage, fitBadge, shortfallNote, statusBadge, workName } from "../core/badges.js";
import { el, emptyState, fill, guard, render } from "../core/render.js";
import { goWithParams, link } from "../core/router.js";
import { clearSearchLink } from "../core/search.js";
import { selectionMode } from "../core/selecting.js";
import { state } from "../core/state.js";
import { menuButton, toolbar } from "../core/toolbar.js";

/* The typed vocabulary, in vocabulary order, and the words the rail puts on it.
 *
 * The same six `VocabularyKind` carries on the server, and the order is the
 * enum's: the response returns all six every time, so the rail renders what it is
 * given rather than deciding what exists. */
const FACET_KINDS = ["artist", "movement", "era", "subject", "medium", "palette"];

const FACET_LABELS = {
  artist: "Artist",
  movement: "Movement",
  era: "Era",
  subject: "Subject",
  medium: "Medium",
  palette: "Palette",
};

/* *Size*: the fit bands `GET /api/works` counts (`fit`), in the
 * words a card's fit badge uses (`core/badges.js`), and `unknown` for a work
 * with no master yet. Carried in `chosen` beside the six kinds, under the
 * route's own parameter name, so the query and *Select all*'s filter body both
 * spell it the way the server reads it. */
const FIT = "fit";
const FIT_LABELS = {
  meets_minimum: "Meets minimum",
  below_minimum: "Below minimum",
  unknown: "No size known",
};

/* *Not on any wall*, in the address as `?wall=none`: works no wall plays now,
 * through the theme or selection hanging on it (the owner's ruling of
 * 2026-10-08 on #288). Not "never hung", which nothing records. */
function notOnWall() {
  return state.params.wall === "none";
}

const CONTACT = "contact";
const CATALOGUE = "catalogue";
/* A table of works, one row each: the *arr Table view, for scanning by title,
 * artist and date when the pictures are not what you are looking for. */
const TABLE = "table";

/* The toolbar's View menu, in the *arr apps' words. The values keep the
 * spellings the address had before the labels changed — `?density=contact` is
 * Posters — so a bookmark is never broken over a word. */
const VIEWS = [
  { value: CONTACT, label: "Posters" },
  { value: CATALOGUE, label: "Overview" },
  { value: TABLE, label: "Table" },
];

/* The toolbar's Sort menu: `WorkOrder` on the server, which applies it. Title is
 * the default and is left out of the address, as every default is. */
const SORTS = [
  { value: "title", label: "Title" },
  { value: "artist", label: "Artist" },
  { value: "newest", label: "Recently added" },
];

/* Above this many works the grid opens as a contact sheet.
 *
 * [ASSUMPTION] "A few hundred" is what `information-architecture.md` says and it
 * is explicitly a guess there, to be set from a real thousands-scale corpus. It
 * is one constant with the guess recorded at its site rather than a threshold
 * spread through the grid, so replacing it with a measurement is one edit.
 *
 * The reason for the rule is not the number: per-tile chrome that reads as
 * informative at 41 works reads as noise at 4,000 and competes with the art. */
const CATALOGUE_CEILING = 300;

/* Several values within one facet kind travel in the fragment separated by this.
 *
 * **On the wire there is no separator at all** — `GET /api/works` takes one
 * repeated parameter per kind (`?movement=Baroque&movement=Rococo`) precisely
 * because a facet value may contain a comma, and a separator a value can hold is
 * a parser that goes wrong on the data rather than on the request. The fragment
 * has no repeated keys to use: `state.params` is a flat string map.
 *
 * **So the values are escaped before they are joined**, and unescaped after they
 * are split — which is what makes the pipe safe where the comma was not. A value
 * holding a literal pipe arrives here as `%7C` and survives the split whole; the
 * separator is the only bare pipe the string can contain. Choosing a rarer
 * character instead would have been the same bet the comma lost, just at longer
 * odds, and this needs no bet at all. `formatRoute` escapes the joined string
 * again on the way into the address and `parseRoute` unescapes it once on the way
 * out, so what `splitValues` sees is exactly what `joinValues` wrote. */
const FACET_SEPARATOR = "|";

/* How many skeleton tiles stand in for the grid while it loads. About a
 * screenful at the contact sheet's tile size: fewer leaves the page looking
 * finished and short, more paints a screen of grey the curator scrolls. */
const SKELETON_TILES = 12;

/* -- reading the address ---------------------------------------------------- */

/* One escaped piece, or what was there.
 *
 * `decodeURIComponent` throws `URIError` on a malformed escape, and a hand-typed
 * or hand-truncated address is exactly where one comes from. A piece that will
 * not decode is used verbatim, which is wrong in a way the curator can see rather
 * than fatal in a way they cannot — the same trade `core/route.js` makes for the
 * same reason. Only `URIError` is swallowed. */
function decodeValue(piece) {
  try {
    return decodeURIComponent(piece);
  } catch (failure) {
    if (!(failure instanceof URIError)) throw failure;
    return piece;
  }
}

function splitValues(raw) {
  if (!raw) return [];
  return raw.split(FACET_SEPARATOR).filter(Boolean).map(decodeValue);
}

function joinValues(values) {
  return values.map((value) => encodeURIComponent(value)).join(FACET_SEPARATOR);
}

function facetsFor(params) {
  const chosen = {};
  for (const kind of FACET_KINDS) chosen[kind] = splitValues(params[kind]);
  chosen[FIT] = splitValues(params[FIT]);
  return chosen;
}

/* Whether any rail narrowing is chosen: a facet, a size band, or *Not on
 * any wall*. The theme is asked about separately, since the heading names it. */
function anyFacetChosen(chosen) {
  return FACET_KINDS.some((kind) => chosen[kind].length) || chosen[FIT].length > 0 || notOnWall();
}

/* The change to the address that turns one facet value on or off. The rest of
 * the address stays, a theme in it included: the server composes the two. */
function facetChange(chosen, kind, value) {
  const values = chosen[kind].includes(value)
    ? chosen[kind].filter((held) => held !== value)
    : [...chosen[kind], value];
  return { [kind]: joinValues(values) };
}

/* Which density to draw, given how much there is.
 *
 * The address wins when it names one, which is what "remembered and part of the
 * addressable state" buys: a reload and a link both land where the curator left
 * off, and back undoes a density change like any other navigation. `localStorage`
 * would remember it too and would not be addressable, which is the half that
 * matters — every other consequential state on this surface is in the fragment. */
function resolveDensity(total) {
  const named = state.params.density;
  if (named === CONTACT || named === CATALOGUE || named === TABLE) return named;
  return total > CATALOGUE_CEILING ? CONTACT : CATALOGUE;
}

/* -- the tiles -------------------------------------------------------------- */

/* `inTabOrder` is false on the Overview card, whose title link opens the same
 * page: two Tab stops to one place, one of them a picture that announces the
 * title again, was a third of every card's stops (`ux-review-2026-10.md`
 * finding 30). The picture still opens the work to a pointer. On a Posters
 * tile the picture is the only way in, so it keeps its stop and its name. */
function cardImage(work, { inTabOrder = true } = {}) {
  if (!work.image.available) {
    // Still the way in on a Posters tile, whose picture is its only link: a
    // work whose image has not arrived yet was a tile nothing could open.
    if (inTabOrder) {
      return link({ view: "work", id: work.artwork_id }, { class: "card-image", "aria-label": `Open ${workName(work)}` }, [
        absentImage(work.image.note),
      ]);
    }
    return el("div", { class: "card-image" }, [absentImage(work.image.note)]);
  }
  const image = el("img", {
    src: `/api/works/${encodeURIComponent(work.artwork_id)}/thumbnail`,
    // Empty on purpose. The link around it is already named "Open <title>",
    // and the tile's own text carries artist, date and medium — describing the
    // picture here as well would make every tile announce its title twice.
    alt: "",
    loading: "lazy",
  });
  // Availability was true when the listing was built, and a file can go away
  // between then and the fetch. Without this the tile renders as a blank box —
  // silent, which is the failure mode this whole product exists to refuse.
  image.addEventListener("error", () => {
    image.replaceWith(absentImage("Its image could not be loaded just now."));
  });
  const named = inTabOrder ? { "aria-label": `Open ${workName(work)}` } : { tabindex: "-1", "aria-hidden": true };
  return link({ view: "work", id: work.artwork_id }, { class: "card-image", ...named }, [image]);
}

/* The tick that puts a work in a selection (`core/selecting.js`).
 *
 * Shown in *Select* mode on every tile, at every density, rather than revealed
 * on hover with the rest of the contact sheet's metadata: a control that only
 * exists once you are pointing at it is one a keyboard cannot find. Outside the
 * mode it is hidden, which takes it out of the tab order too. */
function selectBox(work, selection) {
  return selection.heldBox(work, { className: "tile-select" });
}

/* The catalogue tile: the built card, unchanged in shape. */
function workCard(work, selection) {
  return el("li", { class: "card", "data-artwork": work.artwork_id }, [
    selection ? selectBox(work, selection) : null,
    cardImage(work, { inTabOrder: false }),
    el("div", { class: "card-body" }, [
      el("h2", { class: "card-title" }, [
        link({ view: "work", id: work.artwork_id }, { text: work.title, "aria-label": workName(work) }),
      ]),
      el("p", { class: "card-artist" }, [artistName(work)]),
      el("p", {
        class: "card-meta",
        text: [work.date_created, work.medium].filter(Boolean).join(" · ") || " ",
      }),
      el("div", { class: "card-footer" }, [statusBadge(work), fitBadge(work)]),
    ]),
  ]);
}

/* The artist's name, as the way to their page; plain words when unrecorded. */
function artistName(work) {
  if (!work.artist) return el("span", { text: "Artist unrecorded" });
  return link({ view: "artist", id: work.artist.artist_id }, { class: "link", text: work.artist.name });
}

/* The contact-sheet tile: the picture, and the words behind hover and focus.
 *
 * **On focus as well as on hover**, which the CSS does with `:focus-within` — a
 * keyboard has no hover, so metadata that appeared only under a pointer would not
 * exist for half the people using this.
 *
 * The archived badge is the one thing that does NOT hide with the caption. A
 * badge is not metadata about the work, it is a mark on an exception: a work out
 * of circulation that looks identical to one on the wall until you point at it is
 * the silence `statusBadge` was written to end. */
function contactTile(work, selection) {
  const status = statusBadge(work);
  return el("li", { class: "tile", "data-artwork": work.artwork_id }, [
    selection ? selectBox(work, selection) : null,
    status ? el("div", { class: "tile-status" }, [status]) : null,
    cardImage(work),
    el("div", { class: "tile-caption" }, [
      el("span", { class: "tile-title", text: work.title }),
      el("span", { class: "tile-artist", text: work.artist ? work.artist.name : "Artist unrecorded" }),
    ]),
  ]);
}

/* The Table view's row: the same work, the same tick, the same way in.
 *
 * `data-artwork` sits on the row for the reason it sits on a tile: the
 * selection finds and removes a work by it, and counts what is left by the rows
 * in the body it is handed. */
function workRow(work, selection) {
  return el("tr", { "data-artwork": work.artwork_id }, [
    selection ? el("td", { class: "row-select" }, [selectBox(work, selection)]) : null,
    el("td", {}, [link({ view: "work", id: work.artwork_id }, { class: "row-title", text: work.title, "aria-label": workName(work) })]),
    el("td", {}, [artistName(work)]),
    el("td", { text: work.date_created || "—" }),
    el("td", { text: work.medium || "—" }),
    el("td", {}, [statusBadge(work) || "—"]),
  ]);
}

/* The table around a body of rows, with the tick column only when there is a
 * selection to tick. */
function tableAround(body, selection) {
  const head = [
    selection ? el("th", { scope: "col", class: "row-select" }, [el("span", { class: "visually-hidden", text: "Select" })]) : null,
    ...["Title", "Artist", "Date", "Medium", "Status"].map((name) => el("th", { scope: "col", text: name })),
  ];
  return el("table", { class: "work-table" }, [
    el("caption", { class: "visually-hidden", text: "Works, one row each." }),
    el("thead", {}, [el("tr", {}, head)]),
    body,
  ]);
}

/* -- the loading state ------------------------------------------------------ */

/* Tiles at the geometry the real ones will have — which means this is painted
 * only once that geometry is known.
 *
 * **The skeleton never guesses the density**, and an earlier draft of this screen
 * did: it drew a contact sheet whenever the address named nothing, while the
 * default below a few hundred works resolves to the catalogue. Every visit to a
 * small collection then jumped from twelve small tiles to N wide cards — the
 * reflow the rule exists to prevent, on the commonest path.
 *
 * The total is what decides the density and the first page is what carries it, so
 * the placeholder waits for that page. What it costs is that a collection
 * arriving in one round trip gets no skeleton at all, which is right: there is
 * nothing to wait through. What it buys is that the skeleton, whenever it is on
 * screen, is standing at the geometry the grid will occupy. */
function skeletonGrid(density) {
  const tiles = [];
  for (let index = 0; index < SKELETON_TILES; index += 1) {
    tiles.push(
      el("li", { class: density === CONTACT ? "tile skeleton" : "card tile-skeleton skeleton" }, [
        el("div", { class: "card-image" }),
        density === CONTACT ? null : el("div", { class: "card-body" }, [el("p", { class: "skeleton-line" })]),
      ]),
    );
  }
  return el(
    "ul",
    {
      // Not `.grid`, though it lays out identically: a loading placeholder that
      // answers the selector the real grid answers is one every test and every
      // reader has to tell apart by its contents.
      class: density === CONTACT ? "grid-skeleton contact-sheet" : "grid-skeleton",
      "aria-hidden": true,
    },
    tiles,
  );
}

/* The whole screen, with the parts that are not known yet left blank.
 *
 * **The tiles are inside the same two-column layout the grid will be inside**,
 * which is the other half of standing at the final geometry: a placeholder that
 * spans the full page and is then replaced by a grid beside a 13rem rail has
 * tiles of a different size, however faithfully the tiles themselves were drawn.
 * The rail is empty because the vocabulary is a request that has not answered;
 * its column is a fixed width, so its contents arriving move nothing.
 *
 * The density control is real rather than a placeholder — the density is the one
 * thing that *is* known here, and a control that works while the pictures load is
 * better than a grey rectangle the same size. */
function skeletonScreen(density) {
  const railsShown = !railsHidden();
  return [
    el("h1", { text: "Loading the collection…" }),
    el("div", { class: railsShown ? "collection" : "collection rails-hidden" }, [
      railsShown ? el("aside", { class: "rails", "aria-hidden": true }) : null,
      el("div", { class: "collection-main" }, [
        pageToolbar(density, null),
        // A table's rows have no picture whose geometry could jump, and a stand-in
        // drawn at the wrong row height would be the reflow it exists to prevent.
        density === TABLE ? null : skeletonGrid(density),
      ]),
    ]),
  ];
}

/* -- the rails -------------------------------------------------------------- */

function facetRail(groups, chosen) {
  const rails = [];
  for (const kind of FACET_KINDS) {
    const group = groups.find((candidate) => candidate.kind === kind);
    // A kind with no values anywhere in the catalogue has no vocabulary to
    // offer. That is not the disabled-not-hidden rule, which is about an option
    // whose count has fallen to nothing under the current filter — this kind has
    // never had one, and six empty controls would be six dead ends.
    if (!group || !group.options.length) continue;
    rails.push(
      el("div", { class: "rail" }, [
        el("h2", { text: FACET_LABELS[kind] || kind }),
        el(
          "ul",
          { class: "rail-options" },
          group.options.map((option) => el("li", {}, [facetOption(kind, option, chosen)])),
        ),
        // How much the cap left out, rather than a list that ends and implies the
        // vocabulary does too.
        group.truncated
          ? el("p", {
              class: "rail-note",
              text: `Showing ${group.options.length} of ${group.total_values}. Search for a value the list does not reach.`,
            })
          : null,
      ]),
    );
  }
  return rails;
}

function facetOption(kind, option, chosen, label = option.value) {
  // The count is inside the control's own text, not beside it. A disabled control
  // is skipped by the tab sequence, so a count living in adjacent text is a count
  // a screen-reader user never hears — and the count is the whole difference
  // between a filter and a guess.
  return el("button", {
    class: "facet-option",
    type: "button",
    "aria-pressed": option.selected ? "true" : "false",
    // Disabled, never hidden: a vocabulary that shrank as filters were applied
    // would read as the collection having lost values rather than as an empty
    // intersection.
    disabled: option.disabled,
    text: `${label} (${option.count})`,
    // What finds this option again after the repaint its click causes, so the
    // keyboard stays on it (`core/router.js`).
    "data-focus-key": `facet:${kind}:${option.value}`,
    // A toggle on this page's filter, so a button (`aria-pressed`), as Sort
    // and View are: it changes what the page shows, not which page it is.
    onclick: () => goWithParams(facetChange(chosen, kind, option.value)),
  });
}

/* The clean-up facets (#288), counted by the server like the rest.
 *
 * *Size* offers the fit bands, several at once meaning either, as
 * a facet's values do. Drawn only once it can narrow — two bands holding works,
 * or one chosen: a catalogue whose works all fall in one band has nothing to
 * choose between, and a group that selects everything is a control with nothing
 * behind it. */
function fitRail(fits, chosen) {
  const holding = fits.filter((option) => option.count > 0).length;
  if (holding < 2 && !fits.some((option) => option.selected)) return null;
  return el("div", { class: "rail" }, [
    el("h2", { text: "Size" }),
    el(
      "ul",
      { class: "rail-options" },
      fits.map((option) => el("li", {}, [facetOption(FIT, option, chosen, FIT_LABELS[option.value] || option.value)])),
    ),
  ]);
}

/* *Not on any wall*: one toggle, drawn once some work is on a wall (its count
 * is below the works the rest of the filter selects) or it is chosen. Before
 * anything hangs, every work is on no wall and the option would select them all. */
function wallRail(option, total) {
  if (!option || (option.count >= total && !option.selected)) return null;
  return el("div", { class: "rail" }, [
    el("h2", { text: "Walls" }),
    el("ul", { class: "rail-options" }, [
      el("li", {}, [
        el("button", {
          class: "facet-option",
          type: "button",
          "aria-pressed": option.selected ? "true" : "false",
          disabled: option.disabled,
          text: `Not on any wall (${option.count})`,
          "data-focus-key": "wall:none",
          onclick: () => goWithParams({ wall: option.selected ? "" : "none" }),
        }),
      ]),
    ]),
  ]);
}

/* The rail's Theme group: one theme at a time, beside the facets.
 *
 * **A theme is one more filter**, as a tag is in Radarr's: it composes with the
 * facets and the search on the server, and each option carries the count it
 * would select given every other filter, disabled at zero — the facet rule,
 * for the reason the facet rule exists. Themes themselves are reached from
 * Library › Themes, not from here (the owner's ruling on #169). */
function themeRail(themes) {
  if (!themes.length) return null;
  return el("div", { class: "rail" }, [
    el("h2", { text: "Theme" }),
    el("ul", { class: "rail-options" }, themes.map((option) => el("li", {}, [themeOption(option)]))),
  ]);
}

function themeOption(option) {
  const button = el("button", {
    class: "facet-option",
    type: "button",
    "data-theme": option.theme_id,
    "data-focus-key": `theme:${option.theme_id}`,
    "aria-pressed": option.selected ? "true" : "false",
    disabled: option.disabled,
    text: `${option.name} (${option.count})`,
    // One theme at a time: choosing another replaces it, and choosing the
    // chosen one clears it.
    onclick: () => goWithParams({ theme: option.selected ? "" : option.theme_id }),
  });
  button.dataset.count = String(option.count);
  return button;
}

/* A theme option's count after works joined or left it from this screen.
 *
 * Those works are on screen, so every other filter selects them and the count
 * moves by exactly how many went. Changed in place, because nothing here
 * repaints (`core/selecting.js`), and a count left stale beside the rail is
 * the silent lie the counts exist to refuse. */
function moveThemeCount(option, by) {
  const button = document.querySelector(`button.facet-option[data-theme="${CSS.escape(option.theme_id)}"]`);
  if (!button || !by) return;
  const count = Number(button.dataset.count) + by;
  button.dataset.count = String(count);
  button.textContent = `${option.name} (${count})`;
  button.disabled = count === 0 && button.getAttribute("aria-pressed") !== "true";
}

/* -- the toolbar: density, and Select mode ---------------------------------- */

/* How the page is being shown, without anything it is narrowed by: the state a
 * reset of the narrowing keeps. "Show everything" means every work, not every
 * work in a different view, sort and layout from the one the curator chose. */
function viewing() {
  return { density: state.params.density, sort: state.params.sort, filters: state.params.filters };
}

/* The sort in the address, if it is one this client offers. A bookmark naming
 * one it does not — from another version, or typed — falls back to the default
 * order rather than taking the home page down with a refusal, as an unknown
 * density falls back to the default view. */
function offeredSort() {
  return SORTS.some((option) => option.value === state.params.sort) ? state.params.sort : null;
}

/* Whether the curator has put the rails away. Addressable, like the density:
 * `?filters=hidden`, absent by default, because the rails' counts are how a
 * curator finds things at thousands of works (the owner's ruling, recorded in
 * `information-architecture.md` § The *arr layout). */
function railsHidden() {
  return state.params.filters === "hidden";
}

/* The *arr toolbar over the works: *Select* on the left, its action bar at the
 * foot of the window while it is on; View, Sort and Filter on the right
 * (`core/toolbar.js`).
 *
 * A theme filtered here is in the Sort menu's order, as any filter is; its
 * curated order is its own page's. */
function pageToolbar(density, selection) {
  const controls = [
    menuButton({
      label: "View",
      options: VIEWS,
      current: density,
      onChoose: (value) => goWithParams({ density: value }),
    }),
    menuButton({
      label: "Sort",
      options: SORTS,
      current: offeredSort() || "title",
      onChoose: (value) => goWithParams({ sort: value === "title" ? "" : value }),
    }),
    // Its label says what pressing it does, *Show filters* or *Hide filters*,
    // rather than a pressed state on a word that reads the same either way (#288).
    el("button", {
      class: "action quiet filters-toggle",
      type: "button",
      text: railsHidden() ? "Show filters" : "Hide filters",
      onclick: () => goWithParams({ filters: railsHidden() ? "" : "hidden" }),
    }),
  ];
  return toolbar({ actions: selection ? [selection.toggle] : [], controls });
}

/* -- the three empty states -------------------------------------------------- */

/* Which nothing this is.
 *
 * Three branches with three texts, because they are three different facts and
 * they lead to three different next moves. Conflating the first two tells a
 * curator with 3,000 works that they own nothing; conflating the third with the
 * second reports the expected result of following a suggestion as a failed query,
 * and the conversation makes that one common — the artists it surfaces are by
 * definition ones the curator could not have named. */
function nothingShown(query, chosen, shownTheme) {
  const artists = chosen.artist;
  const onlyAnArtist =
    !query &&
    !shownTheme &&
    artists.length === 1 &&
    !FACET_KINDS.filter((kind) => kind !== "artist").some((kind) => chosen[kind].length) &&
    !chosen[FIT].length &&
    !notOnWall();

  if (onlyAnArtist) {
    return emptyState(
      `Nothing by ${artists[0]} yet.`,
      "That is the normal answer, not a failed search: the collection holds what has been acquired, " +
        "not everything that exists. Ask, or Get from a search, is where more comes from.",
      [
        link({ view: "discover" }, { class: "action", text: "Ask for some" }),
        link({ view: "collection", params: viewing() }, { class: "action quiet", text: "Show everything" }),
      ],
    );
  }

  if (!query && !shownTheme && !anyFacetChosen(chosen)) {
    return emptyState(
      "Nothing is held yet.",
      "Artworks fill from Ask and Get: ask for something, or get works you find, judge what comes back, and what you accept lands here.",
      [link({ view: "discover" }, { class: "action", text: "Go to Ask" })],
    );
  }

  // The filter itself, named. "No results" without saying what was asked for
  // leaves a curator guessing which of three narrowings did it.
  return emptyState("Nothing held matches this filter.", `Filtered by ${filterPhrase(query, chosen, shownTheme)}.`, [
      // "Show everything" rather than "Clear the filter", and the wording is a
      // contract rather than a preference: it is what the way out of a search has
      // been called since the search landed, and it says where the control goes
      // rather than what it undoes. It drops every narrowing, which is the only
      // honest reading of the words.
      link({ view: "collection", params: viewing() }, { class: "action", text: "Show everything" }),
      query ? clearSearchLink("Clear only the search") : null,
  ]);
}

function filterPhrase(query, chosen, shownTheme) {
  const parts = [];
  if (query) parts.push(`the search “${query}”`);
  if (shownTheme) parts.push(`the theme “${shownTheme.name}”`);
  for (const kind of FACET_KINDS) {
    if (chosen[kind].length) {
      parts.push(`${FACET_LABELS[kind].toLowerCase()} ${chosen[kind].map((value) => `“${value}”`).join(" or ")}`);
    }
  }
  if (chosen[FIT].length) {
    parts.push(`size ${chosen[FIT].map((value) => `“${FIT_LABELS[value] || value}”`).join(" or ")}`);
  }
  if (notOnWall()) parts.push("not on any wall");
  return parts.join(", and ");
}

/* -- the heading ------------------------------------------------------------- */

/* What the filter holds, in one sentence.
 *
 * `total` is the server's count over everything the filter selects. How many of
 * those are on screen so far is said beside *Show more* instead: the grid pages
 * as the curator scrolls, so "25 of 2,003" in the heading would read as a
 * shortfall when it is only the first page. */
function headingText(total, query, shownTheme) {
  // A theme holding one work read "1 works", which the grid could get away with
  // while the only number it ever printed was a whole catalogue's.
  const noun = total === 1 ? "work" : "works";
  const matching = query ? ` matching “${query}”` : "";
  const within = shownTheme ? ` in “${shownTheme.name}”` : "";
  return `${total} ${noun}${matching}${within}`;
}

/* -- paging ------------------------------------------------------------------ */

/* How far below the window the row under the grid may be when the next page is
 * asked for, in pixels: about a screen, so the next works are drawn before the
 * curator reaches the end of these. */
const NEAR_THE_END = 800;

/* How many works were on screen when this history entry was left, for Back.
 *
 * Kept on the entry itself (`history.state.loaded`, written as pages arrive),
 * beside the scroll and the opened link `core/router.js` remembers, because
 * that is what makes "card 900 is still card 900" true: the router scrolls to
 * where the curator was and focuses the card they opened, and both need the
 * pages that held them. A new entry carries nothing, and starts at one page. */
function loadedWhenLeft() {
  const remembered = window.history.state;
  return remembered && typeof remembered.loaded === "number" ? remembered.loaded : 0;
}

/* -- the screen -------------------------------------------------------------- */

export async function viewCollection(generation) {
  const query = (state.params.q || "").trim();
  const chosen = facetsFor(state.params);

  // Said, not drawn. How much there is decides the density and the density
  // decides the geometry, so a placeholder painted before the first page has
  // answered can only guess — see `skeletonGrid` for what that cost when it did.
  // The heading is the one thing that can be painted now, and it is the same
  // element the real heading replaces, so it holds its own place.
  render(generation, el("h1", { text: "Loading the collection…" }));

  // The search, the facets and the theme go to the server, which is what makes
  // the count in the heading a statement about the catalogue rather than about
  // this screen's first page — and what lets the three compose.
  const sort = offeredSort();
  const narrowing = (theme) => ({ theme, notOnWall: notOnWall() });
  // A bookmark can outlive the theme it names. The server refuses an unknown
  // theme, rightly, since answering with the whole catalogue under its name
  // would be a lie; but passing that refusal on would take the home page down,
  // where a stale sort or density falls back. So the works the address's other
  // filters select are shown, and `staleThemeNote` says the theme is gone. Only
  // when the listing without the theme answers: a refusal that survives dropping
  // the theme was never about it, and is the error.
  let theme = state.params.theme || null;
  let first;
  let themeGone = false;
  try {
    first = await fetchWorksPage(query, chosen, sort, narrowing(theme));
  } catch (failure) {
    if (!theme || failure.status !== 400) throw failure;
    first = await fetchWorksPage(query, chosen, sort, narrowing(null));
    theme = null;
    themeGone = true;
  }
  const staleTheme = themeGone ? staleThemeNote() : null;
  const density = resolveDensity(first.total);

  // **One page, then more as the curator scrolls** (#131): the grid no longer
  // walks the whole catalogue before it paints, so every work is reachable at
  // any size and the first screenful arrives in one round trip. Back to this
  // entry is the exception: it reloads as many works as were on screen when it
  // was left (`loadedWhenLeft`), so the card that was opened is there for the
  // router to scroll to and focus. A skeleton stands in while those load, at
  // the geometry the first page has now decided.
  const works = [...first.works];
  let exhausted = !first.truncated || first.works.length === 0;
  const remembered = loadedWhenLeft();
  if (!exhausted && remembered > works.length) {
    render(generation, ...skeletonScreen(density));
    const rest = await fetchWorksFrom(query, chosen, sort, narrowing(theme), works.length, remembered, first.limit);
    works.push(...rest.works);
    exhausted = rest.exhausted;
  }
  const page = { ...first, works };

  const themes = page.themes;
  const shownTheme = themes.find((option) => option.selected) || null;
  let total = page.total;
  const heading = el("h1", { text: headingText(total, query, shownTheme) });

  if (!page.works.length) {
    render(
      generation,
      heading,
      collectionLayout(page, chosen, shownTheme, density, null, [staleTheme, nothingShown(query, chosen, shownTheme)]),
    );
    return;
  }

  // One element per work: the grid's list, or the table's body.
  const grid = density === TABLE ? el("tbody") : el("ul", { class: density === CONTACT ? "grid contact-sheet" : "grid" });
  const tile = density === TABLE ? workRow : density === CONTACT ? contactTile : workCard;
  let removedSoFar = 0;
  const recountRail = async () => {
    const rail = document.querySelector("aside.rails");
    if (!rail) return;
    const counts = await fetchFilterCounts(query, chosen, { theme, notOnWall: notOnWall() });
    fill(rail, ...railContents(counts, chosen));
  };
  const tileOf = (artworkId) => grid.querySelector(`[data-artwork="${CSS.escape(artworkId)}"]`);
  const shownWorks = new Map(page.works.map((work) => [work.artwork_id, work]));

  // *Select* mode (`core/selecting.js`). **Nothing here repaints the screen**,
  // and that is the rule rather than an optimisation: a curator standing on
  // "Add" who is handed a new page has lost their place and their focus. The
  // outcome is announced in the bar's live region; tiles that leave a theme are
  // taken out, archived ones are redrawn with their badge, and the rail's theme
  // count moves in place after an add.
  const selection = selectionMode({
    held: {
      themes: themes.map((option) => ({ theme_id: option.theme_id, name: option.name })),
      shownTheme,
      filter: worksFilterBody(query, chosen, offeredSort(), { theme, notOnWall: notOnWall() }),
      total: page.total,
      onAdded: (into, added) => moveThemeCount(into, added),
      onArchived: (ids) => {
        for (const artworkId of ids) {
          const work = shownWorks.get(artworkId);
          const node = tileOf(artworkId);
          if (!work || !node) continue;
          work.status = "archived";
          node.replaceWith(tile(work, selection));
        }
      },
      onRemoved: (artworkId) => {
        const node = tileOf(artworkId);
        if (node) node.remove();
      },
      afterRemoval: async ({ removed, complete }) => {
        removedSoFar += removed.length;
        total -= removed.length;
        // The heading counted what was there before the removal, and a count
        // that no longer matches the tiles under it is the silent lie this
        // surface exists to refuse.
        heading.textContent = headingText(total, query, shownTheme);
        remember();
        // A theme whose last member has just gone is empty, and an empty grid
        // with no sentence reads as a broken screen rather than as a theme
        // holding nothing. Taken out only when nothing is left to load: the
        // works not yet on screen are still in the theme.
        if (!grid.children.length && total <= 0) {
          (grid.closest("table") || grid).replaceWith(nothingShown(query, chosen, shownTheme));
          more.remove();
        } else settleMore();
        // The works that left were inside the theme's slice, so every facet
        // count beside it fell, and a value they alone carried now selects
        // nothing — an enabled option leading to an empty grid, the dead end
        // the rail forbids. Recounted after a partial removal too.
        //
        // A recount that fails is a read, so it is the banner's — unless the
        // removal was refused, when the refusal beside Remove is what the
        // curator must read and the banner stays quiet rather than compete.
        if (removed.length && complete) await guard(recountRail);
        else if (removed.length) {
          try {
            await recountRail();
          } catch (failure) {
            // Its own trace, since nothing else says so: the rail's counts are
            // now stale.
            console.warn("The filter rail could not be recounted after the refused removal:", failure);
          }
        }
      },
    },
    onToggle: (on) => {
      const layout = grid.closest(".collection");
      if (layout) layout.classList.toggle("selecting", on);
    },
  });
  for (const work of page.works) grid.append(tile(work, selection));
  const shown = density === TABLE ? tableAround(grid, selection) : grid;

  // -- the next page --------------------------------------------------------
  //
  // Asked for when the row below the grid comes within a screen of the window
  // (an IntersectionObserver), and by *Show more* in that row, which is the
  // way for a keyboard and a screen reader: a list that grows only under a
  // scrolling pointer is one they cannot reach the end of. The offset is what
  // has been taken from the server's order less what was taken out of the
  // filter since, so a removal does not skip the works behind it.
  let taken = works.length;
  const showing = el("p", { class: "muted show-more-count" });
  const showMore = el("button", { class: "action quiet show-more", type: "button", text: "Show more" });
  const more = el("div", { class: "show-more-row" }, [showing, showMore]);
  let watcher = null;

  function remember() {
    // On this history entry, so Back to it loads as many as are on screen.
    if (generation !== state.nav) return;
    window.history.replaceState({ ...(window.history.state || {}), loaded: grid.children.length }, "");
  }

  function settleMore() {
    const onScreen = grid.children.length;
    if (exhausted) {
      if (watcher) watcher.disconnect();
      // Said, not left silent, when the server stopped short of its own total:
      // a list that ends early would read as a catalogue holding no more.
      fill(more, onScreen < total ? shortfallNote({ works: { length: onScreen }, total }) : null);
      return;
    }
    showing.textContent = `Showing ${onScreen.toLocaleString("en-US")} of ${total.toLocaleString("en-US")}.`;
  }

  // The page being fetched, if one is: one at a time, and *Show more* pressed
  // while the scroll has already asked for it waits for that page rather than
  // asking for a second.
  let inflight = null;

  function loadPage() {
    if (inflight) return inflight;
    if (exhausted || generation !== state.nav) return Promise.resolve();
    inflight = (async () => {
      // Placeholders at the grid's own geometry while the page is on its way.
      const standIn = density === TABLE ? null : skeletonGrid(density);
      if (standIn) more.before(standIn);
      try {
        const body = await fetchWorksPage(query, chosen, sort, narrowing(theme), taken - removedSoFar);
        if (generation !== state.nav) return;
        taken += body.works.length;
        exhausted = !body.truncated || body.works.length === 0;
        // A work already on screen is not drawn twice: the server's order can
        // shift under a page boundary when a work joins or leaves the filter.
        for (const work of body.works) {
          if (shownWorks.has(work.artwork_id)) continue;
          shownWorks.set(work.artwork_id, work);
          grid.append(tile(work, selection));
        }
      } finally {
        inflight = null;
        if (standIn) standIn.remove();
      }
      remember();
      settleMore();
    })();
    return inflight;
  }

  // A page short enough to leave the row in view does not move it out and
  // back, so the observer would not fire again; asked here instead.
  async function loadAsScrolled() {
    await loadPage();
    if (exhausted || !more.isConnected || generation !== state.nav) return;
    if (more.getBoundingClientRect().top < window.innerHeight + NEAR_THE_END) await loadAsScrolled();
  }

  // From *Show more*, the keyboard goes to the first work that arrived, so the
  // next Tab continues through the new ones rather than past them.
  showMore.addEventListener("click", () =>
    attempt(showMore, "show more works", async () => {
      const before = grid.children.length;
      await loadPage();
      const arrived = grid.children[before];
      const opener = arrived ? arrived.querySelector("a[href]:not([tabindex='-1'])") : null;
      if (opener) opener.focus();
    }),
  );
  settleMore();

  render(
    generation,
    heading,
    collectionLayout(page, chosen, shownTheme, density, selection, [staleTheme, shown, more, selection.bar]),
  );
  remember();

  if (!exhausted && typeof IntersectionObserver !== "undefined") {
    watcher = new IntersectionObserver(
      (entries) => {
        if (generation !== state.nav || !more.isConnected) {
          watcher.disconnect();
          return;
        }
        if (entries.some((entry) => entry.isIntersecting)) guard(loadAsScrolled);
      },
      { rootMargin: `0px 0px ${NEAR_THE_END}px 0px` },
    );
    watcher.observe(more);
  }
}

/* Said where the works are rather than in the rail, so it is seen with the
 * rails put away too. The theme's id is not repeated: it names nothing now, and
 * the way back to a theme that does exist is the rail beside it. */
function staleThemeNote() {
  return el("p", {
    class: "note stale-theme-note",
    text: "The theme this address names is not in the catalogue — it may have been deleted — so these are the works the other filters select.",
  });
}

/* What the rails hold: the Theme group, then the facets. Said rather than
 * drawn empty when there is neither, since a rail with no group in it reads as
 * a screen that failed to load its filters. */
function railContents(page, chosen) {
  const groups = [
    themeRail(page.themes),
    fitRail(page.fits || [], chosen),
    wallRail(page.not_on_wall, page.total),
    ...facetRail(page.facets, chosen),
  ].filter(Boolean);
  return groups.length
    ? groups
    : [el("p", { class: "rail-note", text: "Nothing to filter by yet. Themes and facets appear here as works gain them." })];
}

/* The rails beside the works, and the toolbar above them. One function so the
 * populated screen and each empty one cannot come to disagree about where the
 * controls live — an empty grid that also loses its filters is an empty state a
 * curator cannot get out of. */
function collectionLayout(page, chosen, shownTheme, density, selection, main) {
  const rails = railContents(page, chosen);
  const shown = !railsHidden();
  // With the rails away, a facet or a theme still narrowing the works would be
  // invisible: the grid would read as the whole collection. So it says so, and
  // offers the rails back, where the narrowing can be seen and undone.
  const narrowedOutOfSight =
    !shown && (shownTheme || anyFacetChosen(chosen))
      ? el("p", { class: "note filters-hidden-note" }, [
          el("span", { text: "Filters are narrowing these works, and the filter rails are put away. " }),
          el("button", {
            class: "action quiet",
            type: "button",
            text: "Show the filters",
            onclick: () => goWithParams({ filters: "" }),
          }),
        ])
      : null;
  const classes = ["collection", shown ? null : "rails-hidden", selection && selection.selecting() ? "selecting" : null];
  return el("div", { class: classes.filter(Boolean).join(" ") }, [
    shown ? el("aside", { class: "rails", "aria-label": "Filters" }, rails) : null,
    el("div", { class: "collection-main" }, [pageToolbar(density, selection), narrowedOutOfSight, ...main]),
  ]);
}
