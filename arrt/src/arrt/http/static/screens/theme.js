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
 * own page: renaming, deleting, ordering and hanging are each about one
 * theme, and an index that expanded every theme with all of its acts and its
 * whole membership grew by a table row per work in every theme. The index
 * creates a theme, because a theme not yet made has no page to be created on.
 *
 * **Works are added where the works are, and taken out here.** Putting works
 * into a theme is organising against the works being organised, so it is
 * Artworks' *Add to theme…* on a selection; a theme's page links there (the
 * owner's ruling of 2026-10-29, `ia-proposal.md`). Taking one out is this
 * page's: a curator looking at this theme's order, deciding some do not belong,
 * selects them and removes them here.
 *
 * **Every write repaints from the answer it was given.** `POST`/`DELETE` on a
 * theme's works return the resulting order, so nothing here guesses where a
 * work landed and then asks. A delete leaves the page pointing at nothing, so it
 * goes to the index, which reads the themes that remain.
 */

import { attempt } from "../core/acting.js";
import { api } from "../core/api.js";
import { fitBadge, noPicture } from "../core/badges.js";
import { confirmAct } from "../core/confirm.js";
import { GLYPHS } from "../core/glyphs.js";
import { openPanel } from "../core/editing.js";
import { hangOnWalls } from "../core/hanging.js";
import { el, emptyState, fill, render } from "../core/render.js";
import { wallLinks } from "../core/places.js";
import { backLink, backRow, go, link, notFound, refresh, setTitle } from "../core/router.js";
import { selectionMode } from "../core/selecting.js";
import { toolbar } from "../core/toolbar.js";

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
function noDefaultNote(placements, { quiet = false } = {}) {
  if (!placements.length || placements.some((entry) => entry.theme.is_default)) return null;
  return el("p", {
    class: quiet ? "muted no-default" : "note no-default",
    text: "No theme is the default, so works you accept join no theme. Make one the default to have them land there.",
  });
}

/* -- the index -------------------------------------------------------------- */

/* The index opens as every page does (`design-direction.md` § Component
 * Patterns, "How a page reads"; ruling 9 of 2026-10-27): its name, one line of
 * facts, and a toolbar whose act is *New theme…*, the one act the index has,
 * since a theme not yet made has no page to be made on. Every other act on a
 * theme is on that theme's page. */
async function themeIndex(generation) {
  // The listing alone: each entry carries its count, its first pictures and its
  // walls, so ten themes are one read rather than ten reads of their works.
  const themes = await api("/api/themes");

  render(
    generation,
    backRow(),
    el("h1", { text: "Themes" }),
    indexFacts(themes.themes),
    toolbar({ actions: [newThemeOpener()] }),
    themes.themes.length
      ? el("ul", { class: "grid theme-cards" }, themes.themes.map(themeCard))
      : emptyState("No themes yet.", "Make one with New theme…, then add works to it from Artworks."),
    // About where acceptances go rather than about any card, and it does not
    // stop the index's job, so it is a quiet line after what it qualifies.
    noDefaultNote(themes.themes, { quiet: true }),
  );
}

/* How many themes, and which is the default: the one fact about the set that
 * no card says alone. That none is says the quiet line after the cards, which
 * says what follows from it, so it is not said twice. */
function indexFacts(placements) {
  const chosen = placements.find((entry) => entry.theme.is_default);
  const count = placements.length === 1 ? "1 theme" : `${placements.length} themes`;
  const parts = chosen ? [count, `${chosen.theme.name} is the default`] : [count];
  return el("p", { class: "muted page-facts", text: parts.join(" · ") });
}

/* *New theme…*: its name and description, then *Create*, which goes to the
 * new theme's page, where its works are added and it is hung. */
function newThemeOpener() {
  return el("button", {
    class: "action quiet",
    type: "button",
    text: "New theme…",
    "aria-haspopup": "dialog",
    onclick: () => {
      const name = el("input", { type: "text", id: "new-theme-name", autocomplete: "off" });
      const description = el("textarea", { id: "new-theme-description", rows: "3" });
      let panel = null;
      const create = el("button", {
        class: "action",
        type: "button",
        text: "Create",
        onclick: (event) =>
          attempt(
            event.currentTarget,
            name.value.trim() ? `create ${name.value.trim()}` : "create the theme",
            () =>
              api("/api/themes", {
                method: "POST",
                // An empty description is no description, not one of nothing.
                body: JSON.stringify({ name: name.value, description: description.value.trim() || null }),
              }),
            {
              then: (made) => {
                panel.close();
                go("theme", made.theme_id);
              },
            },
          ),
      });
      panel = openPanel({
        title: "New theme",
        closeLabel: "Cancel",
        body: [
          el("div", { class: "field" }, [el("label", { for: "new-theme-name", text: "Name" }), name]),
          el("div", { class: "field" }, [el("label", { for: "new-theme-description", text: "Description" }), description]),
        ],
        actions: [create],
      });
      name.focus();
    },
  });
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
    el("span", {}, ["on ", ...wallLinks(walls)]),
  ]);

/* -- one theme -------------------------------------------------------------- */

/* One theme, addressed by `#theme/<id>`, built to the page rules (ruling 9 of
 * 2026-10-27): the way back, its name, one line of facts, and a toolbar whose
 * acts are *Hang…* (the filled one), *Edit…*, *Add works* and *Select*, with the
 * acts on a selection after it. Then its description, and its works in order.
 *
 * **A theme that is not in the listing is an ordinary state, not an error.** The
 * address outlives the theme — a bookmark, a link in a note, an agent's message
 * — and a curator who deleted it a week ago is owed a sentence rather than the
 * product's home with no explanation of why they are there. */
async function oneTheme(themeId, generation) {
  // The walls come along because hanging is an act against named walls: the
  // dialog cannot offer "put this up" without saying where.
  const [themes, walls] = await Promise.all([api("/api/themes"), api("/api/walls")]);
  const placement = themes.themes.find((entry) => entry.theme.theme_id === themeId);
  if (!placement) {
    render(generation, ...notFound(null, "Nothing in the collection has this address. It was most likely deleted."));
    return;
  }
  const theme = placement.theme;
  const detail = await api(`/api/themes/${encodeURIComponent(themeId)}`);

  setTitle(generation, theme.name);
  const count = el("span");
  const facts = el("p", { class: "muted page-facts theme-facts" }, [
    count,
    ...(theme.is_default ? [" · ", el("span", { text: "Default: works you accept join it" })] : []),
    ...(placement.hanging_on.length ? [" · Hanging on ", ...wallLinks(placement.hanging_on)] : []),
  ]);
  const list = el("div", { class: "theme-members" });
  // What a move or a removal leaves said, for a listener: the table repaints
  // under the keyboard, and the change would otherwise pass in silence.
  const said = el("p", { class: "visually-hidden", "aria-live": "polite" });

  const selection = selectionMode({
    held: {
      themes: themes.themes.map((entry) => entry.theme),
      shownTheme: { theme_id: theme.theme_id, name: theme.name },
      filter: null,
      total: detail.works.length,
      onAdded: () => {},
      onArchived: () => refresh(),
      onRemoved: () => {},
      // Repainted from the server's order once the works have gone, so the count
      // and the positions are what the catalogue now holds.
      afterRemoval: async () => paint(await api(`/api/themes/${encodeURIComponent(themeId)}`)),
    },
  });

  const paint = (members) => {
    count.textContent = members.works.length === 1 ? "1 work" : `${members.works.length} works`;
    selection.setTotal(members.works.length);
    fill(list, memberList(theme, members, { paint, selection, said }));
  };
  paint(detail);

  render(
    generation,
    el("p", {}, [backLink()]),
    el("h1", { text: theme.name }),
    facts,
    toolbar({
      actions: [
        hangOpener(placement, walls.walls),
        editOpener(theme),
        // Adding is done where the works are, with their pictures and filters
        // beside them (the owner's ruling of 2026-10-29, `ia-proposal.md`).
        link({ view: "collection" }, { class: "action quiet page-act", text: "Add works" }),
        // *Select* and the acts on what is selected, where every list puts them
        // (`core/selecting.js`): a phone hides the toolbar's right side while
        // selecting, which would take *Stop selecting* with it.
        selection.toggle,
        selection.bar,
      ],
    }),
    theme.description ? el("p", { class: "theme-description", text: theme.description }) : null,
    list,
    said,
    noDefaultNote(themes.themes, { quiet: true }),
  );
}

/* *Hang…*: every wall, ticked where the theme hangs now. *Hang* asks once,
 * through `core/hanging.js`, for the walls whose tick changed, and sends
 * nothing when none did. With no wall at all, the dialog says so. */
function hangOpener(placement, walls) {
  const theme = placement.theme;
  const opener = el("button", {
    class: "action page-act",
    type: "button",
    text: "Hang…",
    "aria-haspopup": "dialog",
    "aria-label": `Hang ${theme.name}…`,
    onclick: () => {
      const hanging = new Set(placement.hanging_on.map((wall) => wall.wall_id));
      const boxes = walls.map((wall) => {
        const id = `hang-on-${wall.wall_id}`;
        const box = el("input", { type: "checkbox", id, checked: hanging.has(wall.wall_id) });
        return { wall, box, row: el("div", { class: "check-row" }, [box, el("label", { for: id, text: wall.name })]) };
      });
      let panel = null;
      const act = el("button", {
        class: "action",
        type: "button",
        text: "Hang",
        onclick: async () => {
          const hangOn = boxes.filter(({ wall, box }) => box.checked && !hanging.has(wall.wall_id)).map(({ wall }) => wall);
          const takeDownFrom = boxes.filter(({ wall, box }) => !box.checked && hanging.has(wall.wall_id)).map(({ wall }) => wall);
          panel.close();
          if (!hangOn.length && !takeDownFrom.length) return;
          await hangOnWalls({ control: opener, themeId: theme.theme_id, themeName: theme.name, hangOn, takeDownFrom, then: () => refresh() });
        },
      });
      panel = openPanel({
        title: `Hang ${theme.name}`,
        lead: walls.length ? "Tick the walls it should hang on. A wall left unticked has it taken down." : null,
        closeLabel: "Cancel",
        body: walls.length
          ? [el("fieldset", { class: "hang-walls" }, [el("legend", { class: "visually-hidden", text: "Walls" }), ...boxes.map(({ row }) => row)])]
          : [el("p", { class: "muted", text: "There are no walls, so nothing can be hung. A wall is created when the plane first opens the catalogue." })],
        actions: walls.length ? [act] : [],
      });
    },
  });
  return opener;
}

/* *Edit…*: its name and description, saved together; making it the default
 * (absent on the default, whose mark moves only by making another one the
 * default); and deleting it, last. */
function editOpener(theme) {
  const opener = el("button", {
    class: "action quiet page-act",
    type: "button",
    text: "Edit…",
    "aria-haspopup": "dialog",
    "aria-label": `Edit ${theme.name}…`,
    onclick: () => {
      const nameId = `theme-name-${theme.theme_id}`;
      const descriptionId = `theme-description-${theme.theme_id}`;
      const name = el("input", { type: "text", id: nameId, value: theme.name, autocomplete: "off" });
      const description = el("textarea", { id: descriptionId, rows: "3" });
      description.value = theme.description || "";
      let panel = null;
      let wrote = false;
      const save = el("button", {
        class: "action",
        type: "button",
        text: "Save",
        "aria-label": `Save ${theme.name}`,
        onclick: (event) =>
          attempt(
            event.currentTarget,
            `save ${theme.name}`,
            () =>
              api(`/api/themes/${encodeURIComponent(theme.theme_id)}`, {
                method: "POST",
                // An empty description is no description, not one of nothing.
                body: JSON.stringify({ name: name.value, description: description.value.trim() || null }),
              }),
            {
              then: () => {
                wrote = true;
                panel.close();
              },
            },
          ),
      });
      /* **Unconfirmed**: it moves a mark, changes no wall and touches no work
       * already in any theme, and its undo is the same act on the theme that
       * had it. */
      const makeDefault = theme.is_default
        ? null
        : el("button", {
            class: "action quiet",
            type: "button",
            text: "Make this the default",
            "aria-label": `Make ${theme.name} the default`,
            onclick: (event) =>
              attempt(event.currentTarget, `make ${theme.name} the default`, () => api(`/api/themes/${encodeURIComponent(theme.theme_id)}/default`, { method: "POST" }), {
                then: () => {
                  wrote = true;
                  panel.close();
                },
              }),
          });
      const remover = el("button", {
        class: "action quiet",
        type: "button",
        text: "Delete…",
        "aria-label": `Delete ${theme.name}…`,
        // Asked with this dialog closed, so the question is the only one on the
        // page; a refusal is said beside the page's own *Edit…*.
        onclick: () => {
          panel.close();
          remove(opener, theme.theme_id, theme.name);
        },
      });
      panel = openPanel({
        title: `Edit ${theme.name}`,
        body: [
          el("div", { class: "panel" }, [
            el("div", { class: "field" }, [el("label", { for: nameId, text: "Name" }), name]),
            el("div", { class: "field" }, [el("label", { for: descriptionId, text: "Description" }), description]),
            el("div", { class: "row" }, [save]),
          ]),
          el("div", { class: "panel" }, [
            el("h3", { text: "Default" }),
            el("p", {
              class: "muted",
              text: theme.is_default ? "Works you accept join this theme, at the end." : "Works you accept join the default theme. Making this one the default moves the mark here.",
            }),
            makeDefault ? el("div", { class: "row" }, [makeDefault]) : null,
          ]),
          el("div", { class: "panel" }, [el("h3", { text: "Delete" }), el("div", { class: "row" }, [remover])]),
        ],
        onClose: () => {
          if (wrote) refresh();
        },
      });
    },
  });
  return opener;
}

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

/* A theme has an order and is never shuffled (ruling 2 of 2026-10-11), so the
 * caption says only that. Whether a wall plays it in this order is the wall's
 * setting, said on Walls; claiming here that position decides what a wall
 * shows first would be false of a wall that shuffles. */
const ORDER_CAPTION = "In curated order.";

/* The theme's works in order: a row each, its drag handle, its tick while
 * *Select* is on, its picture, title and artist (links) and its size. No act per
 * row (the page rules: a list acts on a selection, and order is a drag handle).
 *
 * **The handle moves a work by pointer and by keyboard.** A drag alone has no
 * keyboard path, which is why the order was a number field per row until ruling
 * 9 of 2026-10-27 asked for a handle: so the handle is a `button` named *Move
 * {title}*, whose arrow keys move the work one place, Home and End to either end,
 * and whose drag (pointer events, so a finger on a phone too) drops it where the
 * pointer leaves it. Every move repaints from the server's answer, which is the
 * order the catalogue now holds, says where the work landed, and puts the
 * keyboard back on its handle. */
function memberList(theme, { works, too_small_for: tooSmallFor = {} }, { paint, selection, said }) {
  if (!works.length) {
    return el("p", { class: "muted", text: "This theme holds no works yet. Add works from Artworks." });
  }
  // The Size column only where some work has something to say in it: a column
  // empty on every row was a heading over nothing.
  const sized = works.map((work) => sizeCell(work, tooSmallFor[work.artwork_id]));
  const anySized = sized.some((cell) => cell !== "");

  const move = (work, position) => {
    const handle = handles.get(work.artwork_id);
    return attempt(
      handle,
      `move ${work.title} to position ${position + 1}`,
      () =>
        api(`/api/themes/${encodeURIComponent(theme.theme_id)}/works/${encodeURIComponent(work.artwork_id)}/position`, {
          method: "POST",
          body: JSON.stringify({ position }),
        }),
      {
        then: (detail) => {
          paint(detail);
          const at = detail.works.findIndex((each) => each.artwork_id === work.artwork_id);
          said.textContent = `${work.title} moved to ${at + 1} of ${detail.works.length}.`;
          const moved = document.querySelector(`button.drag-handle[data-work="${CSS.escape(work.artwork_id)}"]`);
          if (moved) moved.focus();
        },
      },
    );
  };

  const handles = new Map();
  const rows = works.map((work, index) => {
    const handle = el("button", {
      class: "drag-handle",
      type: "button",
      "data-work": work.artwork_id,
      "aria-label": `Move ${work.title}`,
      "aria-describedby": "drag-handle-help",
      text: "⠿",
    });
    handles.set(work.artwork_id, handle);
    handle.addEventListener("keydown", (event) => {
      const to = { ArrowUp: index - 1, ArrowDown: index + 1, Home: 0, End: works.length - 1 }[event.key];
      if (to === undefined) return;
      event.preventDefault();
      if (to < 0 || to >= works.length || to === index) return;
      move(work, to);
    });
    handle.addEventListener("pointerdown", (event) => drag(event, work, index));
    const cells = [
      el("td", { class: "member-handle" }, [handle, selection.heldBox(work)]),
      el("td", { "data-label": "Picture" }, [memberPicture(work)]),
      el("td", { "data-label": "Title" }, [link({ view: "work", id: work.artwork_id }, { class: "row-title", text: work.title })]),
      el("td", { "data-label": "Artist" }, [work.artist ? link({ view: "artist", id: work.artist.artist_id }, { class: "link", text: work.artist.name }) : "—"]),
      ...(anySized ? [el("td", { "data-label": "Size" }, sized[index] ? [sized[index]] : [])] : []),
    ];
    return el("tr", { "data-work": work.artwork_id }, cells);
  });

  /* A drag: the row follows nothing (the page does not move under a finger);
   * the row the pointer is over is marked as where the work will land, and
   * letting go there moves it. Captured on the handle, so the drag keeps going
   * when the pointer leaves it, and `touch-action: none` on the handle keeps a
   * phone from scrolling instead (`app.css`). */
  const drag = (event, work, from) => {
    if (event.button !== 0) return;
    event.preventDefault();
    const handle = event.currentTarget;
    handle.setPointerCapture(event.pointerId);
    let to = from;
    // Marked on the side it lands: above the row when it moves up, below when
    // down, since the rows between close up behind it.
    const mark = (index) =>
      rows.forEach((row, at) => {
        row.classList.toggle("drop-target", at === index && index !== from);
        row.classList.toggle("drop-below", at === index && index > from);
      });
    const over = (moved) => {
      const y = moved.clientY;
      const found = rows.findIndex((row) => {
        const box = row.getBoundingClientRect();
        return y >= box.top && y < box.bottom;
      });
      if (found >= 0) to = found;
      else if (rows.length && y < rows[0].getBoundingClientRect().top) to = 0;
      else if (rows.length && y >= rows[rows.length - 1].getBoundingClientRect().bottom) to = rows.length - 1;
      mark(to);
    };
    const end = () => {
      handle.removeEventListener("pointermove", over);
      handle.removeEventListener("pointerup", end);
      handle.removeEventListener("pointercancel", cancel);
      mark(-1);
      if (to !== from) move(work, to);
    };
    const cancel = () => {
      to = from;
      end();
    };
    handle.addEventListener("pointermove", over);
    handle.addEventListener("pointerup", end);
    handle.addEventListener("pointercancel", cancel);
    rows[from].classList.add("dragging");
    handle.addEventListener("lostpointercapture", () => rows[from].classList.remove("dragging"), { once: true });
  };

  return el("div", { class: "table-scroll" }, [
    el("p", { id: "drag-handle-help", class: "visually-hidden", text: "Drag to move it, or use the arrow keys, Home and End." }),
    el("table", { class: "stacked theme-members-table" }, [
      el("caption", { text: ORDER_CAPTION }),
      el("thead", {}, [
        el("tr", {}, [
          el("th", { scope: "col" }, [el("span", { class: "visually-hidden", text: "Order" })]),
          ...["Picture", "Title", "Artist", ...(anySized ? ["Size"] : [])].map((header) => el("th", { scope: "col", text: header })),
        ]),
      ]),
      el("tbody", {}, rows),
    ]),
  ]);
}

/* A member's picture: its thumbnail when it holds a master, else the shared
 * placeholder, which asks for nothing (`noPicture`, `core/badges.js`). */
function memberPicture(work) {
  if (!work.image || !work.image.available) return el("div", { class: "card-image member-picture" }, [noPicture(work.image && work.image.note)]);
  return el("div", { class: "card-image member-picture" }, [
    el("img", { src: `/api/works/${encodeURIComponent(work.artwork_id)}/thumbnail`, alt: "", loading: "lazy" }),
  ]);
}
