/* Theme — a saved selection over the collection, and the acts that are its own.
 *
 * **Themes, under Artworks**, as Radarr keeps its Collections under Movies
 * (`information-architecture.md` § The *arr layout): a theme is a saved
 * selection over the library, not a parallel noun. What belongs here is what is
 * genuinely about the theme rather than about a work — its name, the order its
 * works reach the wall in, where it hangs, and whether it exists.
 *
 * **An index of cards, and a page per theme, from one module.** `#theme` is
 * every theme as a card — its name, how many works, a few of their pictures and
 * the walls it hangs on — each a link to `#theme/<id>`, as Radarr's Collections
 * index is posters that open a collection. Every act on a theme lives on its
 * own page: renaming, deleting, ordering, adding and hanging are each about one
 * theme, and an index that expanded every theme with all of its acts and its
 * whole membership grew by a table row per work in every theme. The index
 * creates a theme, because a theme not yet made has no page to be created on.
 *
 * **Membership is edited from the grid *and* here, and the duplication is
 * deliberate.** Putting works into a theme is organising, and organising happens
 * against the works being organised, which is why the collection screen carries
 * a selection and an "Add to theme" — that is the path a curator building a
 * theme takes. The picker and the per-row remove below are the other job: a
 * curator already looking at this theme's order, deciding one of these does not
 * belong, should not have to go and find it in a grid of everything to say so.
 *
 * **Every write repaints from the answer it was given.** `POST`/`DELETE` on a
 * theme's works return the resulting order, so nothing here guesses where a
 * work landed and then asks. A delete leaves the page pointing at nothing, so it
 * goes to the index, which reads the themes that remain.
 */

import { attempt } from "../core/acting.js";
import { api, fetchAllWorks } from "../core/api.js";
import { fitBadge, shortfallNote, table } from "../core/badges.js";
import { confirmAct } from "../core/confirm.js";
import { GLYPHS } from "../core/glyphs.js";
import { hangTheme } from "../core/hanging.js";
import { el, emptyState, fill, guard, render } from "../core/render.js";
import { backLink, backRow, go, link, refresh, setTitle } from "../core/router.js";

/* How many pictures a card's strip holds: the server's `THEME_CARD_PICTURES`,
 * which is how many it sends. Every card keeps this many slots, filled or not,
 * so the cards in a row are one height. */
const CARD_PICTURES = 4;

export async function viewTheme(themeId, generation) {
  if (themeId) {
    await oneTheme(themeId, generation);
    return;
  }
  await themeIndex(generation);
}

/* Said on both pages, because it is about where acceptances go rather than
 * about either: a curator on one theme's page who could make it the default
 * should know that nothing is the default now, and so should one looking at
 * the set of them. */
function noDefaultNote(placements) {
  if (!placements.length || placements.some((entry) => entry.theme.is_default)) return null;
  return el("p", {
    class: "note",
    text: "No theme is the default, so works you accept join no theme. Make one the default to have them land there.",
  });
}

/* -- the index -------------------------------------------------------------- */

async function themeIndex(generation) {
  // The listing alone: each entry carries its count, its first pictures and its
  // walls, so ten themes are one read rather than ten reads of their works.
  const themes = await api("/api/themes");

  const name = el("input", { type: "text", id: "new-theme-name", required: true });
  const create = el("div", { class: "row" }, [
    el("div", { class: "field" }, [el("label", { for: "new-theme-name", text: "New theme" }), name]),
    el("button", {
      class: "action",
      type: "button",
      text: "Create",
      onclick: (event) =>
        attempt(
          event.currentTarget,
          name.value.trim() ? `create ${name.value.trim()}` : "create the theme",
          () => api("/api/themes", { method: "POST", body: JSON.stringify({ name: name.value }) }),
          { then: () => refresh() },
        ),
    }),
  ]);

  render(
    generation,
    backRow(),
    el("h1", { text: "Themes" }),
    create,
    noDefaultNote(themes.themes),
    themes.themes.length
      ? el("ul", { class: "grid theme-cards" }, themes.themes.map(themeCard))
      : emptyState("No themes yet.", "Create one, then add works to it from Artworks or from its own page."),
  );
}

/* One theme's card: a link to its page, and what a curator choosing between
 * themes reads first — the name, how many works, what they look like, and
 * whether it is the default or hanging anywhere.
 *
 * **Built as Artists' poster cards are**: the title is the link and the one Tab
 * stop, and the pictures open the same page to a pointer without a second stop
 * that would announce the name again. The pictures are the theme's first four
 * that have one, in its order, uncropped. */
function themeCard({ theme, hanging_on: hangingOn, work_count: count, picture_ids: pictured }) {
  const target = { view: "theme", id: theme.theme_id };
  const slots = [];
  for (let index = 0; index < CARD_PICTURES; index += 1) {
    const workId = pictured[index];
    const slot = el("span", { class: "theme-card-slot" });
    if (workId) {
      const img = el("img", { src: `/api/works/${encodeURIComponent(workId)}/thumbnail`, alt: "", loading: "lazy" });
      // A picture that fails to load leaves its slot empty rather than drawing
      // a broken image; the card's words still say what the theme is.
      img.addEventListener("error", () => img.remove());
      slot.append(img);
    }
    slots.push(slot);
  }
  const badges = [theme.is_default ? defaultBadge() : null, hangingOn.length ? hangingBadge(hangingOn) : null].filter(Boolean);
  return el("li", { class: "card theme-card", "data-theme": theme.theme_id }, [
    link(target, { class: "theme-card-pictures", tabindex: "-1", "aria-hidden": true }, slots),
    el("div", { class: "card-body" }, [
      el("h2", { class: "card-title" }, [link(target, { text: theme.name })]),
      // Said when the theme holds works and none has a picture yet, so an empty
      // strip is not read as an empty theme.
      el("p", { class: "card-meta", text: `${count === 1 ? "1 work" : `${count} works`}${count && !pictured.length ? " · no pictures yet" : ""}` }),
      badges.length ? el("p", { class: "card-badges" }, badges) : null,
    ]),
  ]);
}

// Glyph, word and the accent colour, in that order of importance: the colour is
// the third signal, as on every badge here.
const defaultBadge = () =>
  el("span", { class: "badge badge-default" }, [
    el("span", { class: "glyph", text: GLYPHS.picked, "aria-hidden": true }),
    el("span", { text: "default" }),
  ]);

// Hanging carries a glyph and the words beside any colour — and the words name
// the walls, because "on the wall" reads correctly today only while there is
// one of them.
const hangingBadge = (walls) =>
  el("span", { class: "badge" }, [
    el("span", { class: "glyph", text: GLYPHS.good, "aria-hidden": true }),
    el("span", { text: `on ${walls.map((wall) => wall.name).join(", ")}` }),
  ]);

/* -- one theme -------------------------------------------------------------- */

/* One theme, addressed by `#theme/<id>`, with every act that is its own.
 *
 * **A theme that is not in the listing is an ordinary state, not an error.** The
 * address outlives the theme — a bookmark, a link in a note, an agent's message
 * — and a curator who deleted it a week ago is owed a sentence rather than the
 * product's home with no explanation of why they are there. */
async function oneTheme(themeId, generation) {
  // The walls come along because hanging is an act against a named wall: a
  // theme page cannot offer "put this up" without saying where, and it cannot
  // say where without knowing what the walls are called. Every work comes along
  // for the picker that adds one.
  const [themes, walls, works] = await Promise.all([api("/api/themes"), api("/api/walls"), fetchAllWorks()]);
  const placement = themes.themes.find((entry) => entry.theme.theme_id === themeId);
  if (!placement) {
    render(
      generation,
      el("p", {}, [backLink()]),
      el("h1", { text: "That theme is not here" }),
      el("p", {
        class: "note",
        text: "Nothing in the collection has this address. It was most likely deleted — the themes that do exist are listed together.",
      }),
      el("div", { class: "row" }, [
        link({ view: "theme" }, { class: "action", text: "All themes" }),
      ]),
    );
    return;
  }

  // The standing facts about hanging, which is an act this page offers: it
  // would otherwise offer "Hang on the living room" beside no explanation of
  // why nothing can be hung.
  const notes = [shortfallNote(works), noDefaultNote(themes.themes)];
  if (!walls.walls.length) {
    notes.push(
      el("p", { class: "note", text: "There are no walls, so nothing can be hung. A wall is created when the plane first opens the catalogue." }),
    );
  }

  setTitle(generation, placement.theme.name);
  render(
    generation,
    el("p", {}, [backLink()]),
    ...notes,
    themePanel(placement, walls.walls, works.works, generation),
  );
}

function themePanel(placement, walls, allWorks, generation) {
  const theme = placement.theme;
  const hangingOn = placement.hanging_on;
  // The name is read back from every rename rather than kept as the value that
  // was typed: `update_theme` trims, so a name entered with a trailing space is
  // stored without one, and a heading painted from the input would show a name
  // the catalogue does not hold. It is also what the membership controls say —
  // "Remove from Winter" — so a stale copy would be wrong in two places.
  let currentName = theme.name;

  const heading = el("span", { text: currentName });
  const picker = el("select", { id: `add-${theme.theme_id}` });
  for (const work of allWorks) {
    picker.append(
      el("option", {
        value: work.artwork_id,
        text: work.artist ? `${work.title} — ${work.artist.name}` : work.title,
      }),
    );
  }

  const body = el("div", { class: "stack" }, [el("p", { class: "muted", text: "Loading works…" })]);
  /* **How many works are in here, said in words rather than left to be counted.**
   * `information-architecture.md` § Information Hierarchy makes the count this
   * screen's secondary content, and the numbered column is not it: a curator
   * deciding whether a theme is worth hanging wants the size, and reading the
   * last row's number is arithmetic performed on a table that may not be on
   * screen. Repainted with the list rather than rendered once, because an add
   * and a remove both change it and both answer with the new order. */
  const count = el("span", { class: "muted" });
  // Held rather than only rendered, so a rename can relabel the membership
  // controls without asking the server for an order it has already been given.
  // Every membership answer carries both: the order, and whether the wall
  // follows it.
  let members = { works: [], shuffled: false };
  const paintMembers = (detail) => {
    members = detail;
    count.textContent = members.works.length === 1 ? "1 work" : `${members.works.length} works`;
    fill(body, memberList(theme.theme_id, currentName, members, paintMembers));
  };
  // The one read here that is a read: nothing has answered with this theme's
  // works yet, because the listing this panel was built from does not carry them.
  guard(async () => paintMembers(await api(`/api/themes/${encodeURIComponent(theme.theme_id)}`)));

  const rename = el("input", {
    type: "text",
    id: `rename-${theme.theme_id}`,
    value: currentName,
    "aria-label": `Name of ${currentName}`,
  });
  const renameButton = el("button", {
    class: "action quiet",
    type: "button",
    text: "Rename",
    "aria-label": `Rename ${currentName}`,
    onclick: (event) =>
      attempt(
        event.currentTarget,
        `rename ${currentName}`,
        () =>
          api(`/api/themes/${encodeURIComponent(theme.theme_id)}`, {
            method: "POST",
            body: JSON.stringify({ name: rename.value }),
          }),
        {
          then: (renamed) => {
            currentName = renamed.name;
            heading.textContent = currentName;
            rename.value = currentName;
            // The tab, the history entry and a bookmark name the theme too, and
            // were the one place the old name outlived a rename.
            setTitle(generation, currentName);
            nameTheControls();
            // The membership controls name the theme they remove from, so they
            // are repainted too — a table still offering "Remove from Winter"
            // under a heading that reads "Late night" is one a curator has to
            // work out which of the two to believe.
            paintMembers(members);
          },
        },
      ),
  });
  const deleteButton = el("button", {
    class: "action quiet",
    type: "button",
    text: "Delete",
    "aria-label": `Delete ${currentName}`,
    onclick: (event) => remove(event.currentTarget, theme.theme_id, currentName),
  });
  /* **Unconfirmed, like taking a theme down**: it moves a mark, changes no wall
   * and touches no work already in any theme, and the undo is the same button on
   * the theme that had it. The page repaints, because the act changes two
   * themes — this one, and whichever stopped being the default. Absent on the
   * default itself, whose delete the server refuses with the reason. */
  const defaultButton = theme.is_default
    ? null
    : el("button", {
        class: "action quiet",
        type: "button",
        text: "Make default",
        "aria-label": `Make default: ${currentName}`,
        onclick: (event) =>
          attempt(
            event.currentTarget,
            `make ${currentName} the default`,
            () => api(`/api/themes/${encodeURIComponent(theme.theme_id)}/default`, { method: "POST" }),
            { then: () => refresh() },
          ),
      });
  /* **The controls name the theme they act on.** `accessibility-spec.md` asks a
   * control to name what it acts on, and the membership table in this same panel
   * already does ("Remove Blue Poles from Winter"); somebody moving through the
   * form controls one at a time otherwise hears "Name, edit text", "Rename" and
   * "Delete" with the theme reconstructible only from the heading — on a control
   * that destroys something. Re-applied after a rename for the reason the
   * membership controls are repainted: a label naming a theme by its old name is
   * worse than one naming no theme at all. */
  const nameTheControls = () => {
    rename.setAttribute("aria-label", `Name of ${currentName}`);
    renameButton.setAttribute("aria-label", `Rename ${currentName}`);
    deleteButton.setAttribute("aria-label", `Delete ${currentName}`);
    defaultButton?.setAttribute("aria-label", `Make default: ${currentName}`);
  };
  const renameRow = el("div", { class: "row" }, [
    el("div", { class: "field" }, [
      el("label", { for: `rename-${theme.theme_id}`, text: "Name" }),
      rename,
    ]),
    renameButton,
    defaultButton,
    deleteButton,
  ]);

  return el("div", { class: "panel" }, [
    el("h1", {}, [
      heading,
      theme.is_default ? el("span", { style: "margin-left: 0.5rem" }, [defaultBadge()]) : null,
      hangingOn.length ? el("span", { style: "margin-left: 0.5rem" }, [hangingBadge(hangingOn)]) : null,
    ]),
    // Below the heading rather than inside it: the heading is the theme's name,
    // and a count spliced into it becomes part of the name everywhere a heading
    // is read back.
    el("p", { class: "muted" }, [count]),
    theme.is_default ? el("p", { class: "muted", text: "Works you accept join this theme, at the end." }) : null,
    theme.description ? el("p", { class: "muted", text: theme.description }) : null,
    renameRow,
    el("div", { class: "row" }, [
      el("div", { class: "field" }, [
        el("label", { for: `add-${theme.theme_id}`, text: "Add a work" }),
        picker,
      ]),
      el("button", {
        class: "action quiet",
        type: "button",
        text: "Add",
        onclick: (event) =>
          attempt(
            event.currentTarget,
            `add ${picker.selectedOptions.length ? picker.selectedOptions[0].text : "the work"} to ${currentName}`,
            () =>
              api(`/api/themes/${encodeURIComponent(theme.theme_id)}/works`, {
                method: "POST",
                body: JSON.stringify({ artwork_id: picker.value }),
              }),
            { then: (detail) => paintMembers(detail) },
          ),
      }),
      // One button per wall, named for that wall. There is no single-wall
      // shortcut to replace when a second display arrives, which is the whole
      // point: with one wall this reads "Hang on the living room" and with three
      // it reads as three choices, and neither is a different layout.
      //
      // **The walls this theme is already on are not offered here, and that
      // filter is load-bearing rather than tidiness.** Hanging what is already
      // hanging republishes the manifest, which is the path a curator takes when
      // an archive has left a picture up — and that path lives on the Walls
      // screen, whose picker lists every theme including the one showing. This
      // screen offers the rooms this theme is *not* in; teaching Walls the same
      // filter would delete the only republish route there is.
      ...walls
        .filter((wall) => !hangingOn.some((hung) => hung.wall_id === wall.wall_id))
        .map((wall) =>
          el("button", {
            class: "action",
            type: "button",
            text: `Hang on ${wall.name}`,
            onclick: (event) => hang(event.currentTarget, theme.theme_id, currentName, wall),
          }),
        ),
      // **Unconfirmed, and that is a decision.** Flow 6 makes activation the act
      // that gets a question, because it is the one that changes what other
      // people in the house see. Taking a theme down rewrites no manifest, so
      // the room goes on showing exactly what it was showing; what changes is
      // which theme the catalogue says belongs there, and the undo is the hang
      // button that reappears in its place.
      ...hangingOn.map((wall) =>
        el("button", {
          class: "action quiet",
          type: "button",
          text: `Take down from ${wall.name}`,
          onclick: (event) =>
            attempt(
              event.currentTarget,
              `take ${currentName} down from ${wall.name}`,
              () => api(`/api/walls/${encodeURIComponent(wall.wall_id)}/theme`, { method: "DELETE" }),
              { then: () => refresh() },
            ),
        }),
      ),
    ]),
    body,
  ]);
}

/* Leaves for the Walls screen, which is where the result of this act is. The
 * question, the preview and the request are `core/hanging.js`'s — the Walls
 * screen asks the same one, and one act must not have two wordings. */
const hang = (control, themeId, themeName, wall) =>
  hangTheme({ control, themeId, themeName, wall, then: async () => go("walls") });

/* Deleting a theme — the one act on this screen that destroys something.
 *
 * **Confirmed, unlike taking a theme down, because there is no undo.** A theme
 * is a grouping and its works survive it, which is what the question says: a
 * curator who believes they are about to lose the pictures will hesitate over an
 * act that is cheap, and one who does not know the grouping is gone for good
 * will perform it without reading.
 *
 * **The count is read at the moment the question is asked** rather than taken
 * from whatever this panel last painted, for the same reason the hang preview is
 * fetched: the sentence is a statement about the catalogue now.
 *
 * **The refusal is the server's and is shown as it was written.** A theme
 * hanging anywhere cannot be deleted, and the message names the rooms and both
 * ways out of it, said beside Delete as it was written (`core/acting.js`).
 * Nothing here predicts the refusal from `hanging_on` — a second copy of the
 * rule would be a second thing to keep true, and it would be wrong about a theme
 * somebody hung from another tab a moment ago.
 *
 * Once it is gone the page is an address naming nothing, so it goes to the
 * index, where the themes that remain are. */
async function remove(control, themeId, themeName) {
  const act = `delete ${themeName}`;
  let detail = null;
  const read = await attempt(control, act, async () => {
    detail = await api(`/api/themes/${encodeURIComponent(themeId)}`);
  });
  if (!read) return;
  const held = detail.works.length;
  const confirmed = await confirmAct({
    title: `Delete ${themeName}?`,
    consequence: held
      ? `The ${held} ${held === 1 ? "work it holds stays" : "works it holds stay"} in the collection. Only the grouping goes, and it cannot be brought back.`
      : "It holds no works. The grouping cannot be brought back.",
    confirmLabel: "Delete",
  });
  if (!confirmed) return;
  await attempt(control, act, () => api(`/api/themes/${encodeURIComponent(themeId)}`, { method: "DELETE" }), {
    then: () => go("theme"),
  });
}

/* The Size column: the Library's verdict against its quality minimum, then
 * Programming's for each wall hanging the theme whose screen the work is too
 * small for (`programming/adequacy.py`). Two different questions, so two marks:
 * a scan can meet the minimum and still be a postage stamp on a 4K wall. */
function sizeCell(work, walls) {
  const fit = fitBadge(work);
  // `problem`, the glyph for falling short, beside the words: the meaning has
  // three signals, as every badge here does, so neither colour nor the glyph
  // carries it alone.
  const small =
    walls && walls.length
      ? el("span", { class: "badge badge-below_minimum" }, [
          el("span", { class: "glyph", text: GLYPHS.problem, "aria-hidden": true }),
          el("span", { text: `too small for ${walls.join(", ")}` }),
        ])
      : null;
  if (!fit && !small) return "";
  return el("span", { class: "size-marks" }, [fit, small]);
}

/* The order copy, which depends on whether the wall follows the order.
 *
 * With shuffle off, position is what decides what the wall shows first, and
 * saying so is why the moves are worth making. With it on, saying that would be
 * false, so the caption says what Walls says ("shuffled") instead; the order is
 * still kept, and is what the wall follows once shuffle is turned off. */
function orderCaption(shuffled) {
  return shuffled
    ? "Shown in shuffled order, so position here does not decide what the wall shows first."
    : "In curated order. Position decides what the wall shows first.";
}

function memberList(themeId, themeName, { works, shuffled, too_small_for: tooSmallFor = {} }, paint) {
  if (!works.length) {
    return el("p", { class: "muted", text: "This theme holds no works yet." });
  }
  const last = works.length - 1;
  const rows = works.map((work, index) => {
    // The answer to the move is what the list becomes, so the table is repainted
    // from it. A second read would be the same order arrived at more slowly, and
    // repainting from the *sent* position would be optimism: the service clamps
    // and renumbers, so where a work lands is its answer to give.
    const move = (position, words) => (event) =>
      attempt(
        event.currentTarget,
        `move ${work.title} ${words}`,
        () =>
          api(`/api/themes/${encodeURIComponent(themeId)}/works/${encodeURIComponent(work.artwork_id)}/position`, {
            method: "POST",
            body: JSON.stringify({ position }),
          }),
        { then: (detail) => paint(detail) },
      );
    /* **Four moves, all buttons, none a drag.** A drag has no keyboard
     * equivalent, and in a theme of hundreds ↑ alone is hundreds of presses to
     * bring the last work first. The top and the bottom are the two ends a
     * curator reorders towards; the bottom is sent as the last index, since a
     * null position means "unplaced" rather than "last". Disabled rather than
     * absent at the ends, so the row keeps its shape and the buttons do not
     * shuffle sideways under a cursor as a work reaches an end. */
    const controls = el("div", { class: "row" }, [
      el("button", {
        class: "action quiet",
        type: "button",
        text: "↑",
        "aria-label": `Move ${work.title} earlier`,
        disabled: index === 0,
        onclick: move(index - 1, "earlier"),
      }),
      el("button", {
        class: "action quiet",
        type: "button",
        text: "↓",
        "aria-label": `Move ${work.title} later`,
        disabled: index === last,
        onclick: move(index + 1, "later"),
      }),
      el("button", {
        class: "action quiet",
        type: "button",
        text: "Move to top",
        "aria-label": `Move ${work.title} to the top`,
        disabled: index === 0,
        onclick: move(0, "to the top"),
      }),
      el("button", {
        class: "action quiet",
        type: "button",
        text: "Move to bottom",
        "aria-label": `Move ${work.title} to the bottom`,
        disabled: index === last,
        onclick: move(last, "to the bottom"),
      }),
      // **The label says which collection the work is leaving.** "Remove" alone
      // promises the work is gone, and `information-architecture.md` rules that
      // out for a *work*: there is no delete of one, archive is the word, and a
      // curator who believes removal is destructive hesitates over something
      // cheap. This control removes a work from a *theme* — the work stays
      // catalogued, stays in every other theme, and is put back by adding it —
      // so the honest fix is to name the theme rather than to borrow Archive,
      // which would say something false about the catalogue.
      el("button", {
        class: "action quiet",
        type: "button",
        text: `Remove from ${themeName}`,
        "aria-label": `Remove ${work.title} from ${themeName}`,
        onclick: (event) =>
          attempt(
            event.currentTarget,
            `remove ${work.title} from ${themeName}`,
            () => api(`/api/themes/${encodeURIComponent(themeId)}/works/${encodeURIComponent(work.artwork_id)}`, { method: "DELETE" }),
            { then: (detail) => paint(detail) },
          ),
      }),
    ]);
    return [String(index + 1), work.title, work.artist ? work.artist.name : "—", sizeCell(work, tooSmallFor[work.artwork_id]), controls];
  });
  return table(
    orderCaption(shuffled),
    // The last column is named rather than left blank: an empty `th` is
    // announced as an empty column header, which tells a screen-reader user
    // nothing about the buttons in every row beneath it.
    ["#", "Title", "Artist", "Size", "Order and membership"],
    rows,
  );
}
