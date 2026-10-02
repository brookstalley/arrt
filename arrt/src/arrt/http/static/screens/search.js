/* Search results — everything a few words find, the library's and Wikidata's.
 *
 * Ruling 2 (one world): one page lists what the library holds and what the
 * registry knows, each with its state, artists first. *All*, *In your library*
 * and *Not held* narrow it. If the words name exactly one artist, that artist
 * leads the page, one step from their hub.
 *
 * **Reached from the dropdown's last row**, *All results for "…"*. Enter still
 * opens Artworks filtered to the query, as the owner ruled on 2026-09-30 and kept
 * on 2026-10-01. Contextual, so it returns to the page it was opened from.
 *
 * **The library half is drawn first and never waits** on the registry's, which
 * fills its own sections when it answers and says why when it cannot. Nothing on
 * this page spends: *Search museums* fills in Add New and does not start it.
 *
 * Every string from the registry is untrusted text, shown as text. */

import { api } from "../core/api.js";
import { lifeDates, named, stateMark } from "../core/registry.js";
import { el, render } from "../core/render.js";
import { backLink, go } from "../core/router.js";
import { fold } from "../core/search.js";
import { state } from "../core/state.js";

/* How many of the library's works the page lists. Artworks, one click away,
 * holds the rest and the tools to act on them. */
const WORKS_SHOWN = 50;

const VIEWS = [
  ["all", "All"],
  ["library", "In your library"],
  ["not_held", "Not held"],
];

export async function viewSearch(generation) {
  const query = (state.params.q || "").trim();
  const view = VIEWS.some(([key]) => key === state.params.view) ? state.params.view : "all";
  if (!query) {
    render(generation, el("p", {}, [backLink()]), el("h2", { text: "Search" }), el("p", { class: "note", text: "Type in the search box above to search." }));
    return;
  }
  // Asked now, beside the library, and awaited after the library's half is
  // drawn. Not asked at all for *In your library*, which shows none of it.
  const fromRegistry =
    view === "library"
      ? null
      : api(`/api/registry/search?q=${encodeURIComponent(query)}&wide=true`).catch(() => ({
          state: "unavailable",
          note: "Wikidata could not be searched just now.",
          artists: [],
          works: [],
        }));
  const [page, people] = await Promise.all([
    api(`/api/works?q=${encodeURIComponent(query)}&limit=${WORKS_SHOWN}`),
    api(`/api/artists?q=${encodeURIComponent(query)}`),
  ]);

  const top = el("div");
  const artists = el("section", { class: "panel", "aria-labelledby": "results-artists" });
  const works = el("section", { class: "panel", "aria-labelledby": "results-works" });
  const registryNote = el("p", { class: "muted", "aria-live": "polite", text: view === "library" ? "" : "Asking Wikidata…" });
  render(
    generation,
    el("p", {}, [backLink()]),
    el("h2", { text: `Results for “${query}”` }),
    viewSwitch(query, view),
    top,
    registryNote,
    artists,
    works,
  );

  const library = { artists: people.artists, works: page.works, total: page.total };
  const paint = (registry) => {
    paintArtists(artists, query, view, library, registry);
    paintWorks(works, query, view, library, registry);
    paintTop(top, query, view, library, registry);
  };
  paint(null);
  if (!fromRegistry) return;
  const registry = await fromRegistry;
  if (!registryNote.isConnected) return;
  paint(registry);
  registryNote.textContent = registryWords(query, registry);
  if (registry.state === "known" && !registry.artists.length && !registry.works.length) {
    registryNote.after(
      el("div", { class: "row" }, [
        el("button", { class: "action", type: "button", text: `Search museums for “${query}”`, onclick: () => go("discover", null, { term: query }) }),
      ]),
    );
  }
}

/* *All*, *In your library*, *Not held*: buttons that say which is showing. */
function viewSwitch(query, view) {
  return el(
    "div",
    { class: "row", role: "group", "aria-label": "Show" },
    VIEWS.map(([key, label]) =>
      el("button", {
        class: key === view ? "action" : "action quiet",
        type: "button",
        text: label,
        // As a string: `el` drops a false value, and an unpressed toggle must
        // say "false", not leave a reader unsure whether it is a toggle at all.
        "aria-pressed": String(key === view),
        onclick: () => go("search", null, { ...state.params, q: query, view: key === "all" ? "" : key }),
      }),
    ),
  );
}

function registryWords(query, registry) {
  if (registry.state === "too_short") return "Wikidata is searched from three letters.";
  if (registry.state !== "known") return registry.note || "";
  const found = registry.artists.length + registry.works.length;
  return found ? `Wikidata found ${found} for “${query}”.` : `Wikidata has nothing for “${query}”.`;
}

/* The artists: the library's, then Wikidata's that the library's rows do not
 * already show, each marked held or not. */
function artistRows(view, library, registry) {
  const shown = new Set();
  const rows = [];
  if (view !== "not_held") {
    for (const { artist } of library.artists) {
      shown.add(artist.artist_id);
      rows.push({ name: artist.name, life: lifeDates(artist), held: true, open: () => go("artist", artist.artist_id) });
    }
  }
  if (registry && registry.state === "known" && view !== "library") {
    for (const person of registry.artists) {
      if (person.artist_id && (shown.has(person.artist_id) || view === "not_held")) continue;
      rows.push({
        name: named(person.name, person.qid),
        life: lifeDates(person),
        held: Boolean(person.artist_id),
        open: () => go("artist", person.artist_id || person.qid),
      });
    }
  }
  return rows;
}

function paintArtists(section, query, view, library, registry) {
  const rows = artistRows(view, library, registry);
  section.replaceChildren(
    el("h3", { id: "results-artists", text: "Artists" }),
    rows.length
      ? el("ul", { class: "results-list" }, rows.map((row) =>
          el("li", {}, [
            el("button", { class: "row-title", type: "button", text: row.name, onclick: row.open }),
            row.life ? el("span", { class: "muted", text: ` ${row.life}` }) : null,
            stateMark({ held: row.held }),
          ]),
        ))
      : el("p", { class: "muted", text: "No artists." }),
  );
}

/* The works: the library's first, then Wikidata's that are not among them. */
function paintWorks(section, query, view, library, registry) {
  const shownIds = new Set(view === "not_held" ? [] : library.works.map((work) => work.artwork_id));
  const rows = [];
  if (view !== "not_held") {
    for (const work of library.works) {
      rows.push({ title: work.title, by: work.artist ? work.artist.name : null, held: true, image: false, open: () => go("work", work.artwork_id) });
    }
  }
  if (registry && registry.state === "known" && view !== "library") {
    for (const work of registry.works) {
      const held = work.held_artwork_ids.length > 0;
      if (held && (view === "not_held" || work.held_artwork_ids.some((id) => shownIds.has(id)))) continue;
      rows.push({
        title: named(work.title, work.qid),
        by: work.creator ? named(work.creator.name, work.creator.qid) : null,
        held,
        image: Boolean(work.image),
        open: () => (held ? go("work", work.held_artwork_ids[0]) : go("work", work.qid)),
      });
    }
  }
  const more = view !== "not_held" && library.total > library.works.length;
  section.replaceChildren(
    el("h3", { id: "results-works", text: "Works" }),
    rows.length
      ? el("ul", { class: "results-list" }, rows.map((row) =>
          el("li", {}, [
            el("button", { class: "row-title", type: "button", text: row.title, onclick: row.open }),
            row.by ? el("span", { class: "muted", text: ` — ${row.by}` }) : null,
            stateMark({ held: row.held, image: row.image }),
          ]),
        ))
      : el("p", { class: "muted", text: "No works." }),
    view !== "not_held" && library.works.length
      ? el("p", { class: "muted" }, [
          more ? `Your library has ${library.total} matching works; the first ${library.works.length} are here. ` : "",
          el("button", { class: "link", type: "button", text: "Open them in Artworks", onclick: () => go("collection", null, { q: query }) }),
        ])
      : null,
  );
}


/* The words name one artist when exactly one artist found carries every word
 * of them in their name, accents and case ignored. That artist leads the page. */
function paintTop(section, query, view, library, registry) {
  const words = fold(query).split(/\s+/).filter(Boolean);
  const naming = artistRows(view, library, registry).filter((row) => words.every((word) => fold(row.name).includes(word)));
  if (naming.length !== 1) {
    section.replaceChildren();
    return;
  }
  const [artist] = naming;
  section.replaceChildren(
    el("section", { class: "panel", "aria-labelledby": "results-top" }, [
      el("h3", { id: "results-top", text: "Top result" }),
      el("p", {}, [
        el("button", { class: "row-title", type: "button", text: artist.name, onclick: artist.open }),
        artist.life ? el("span", { class: "muted", text: ` ${artist.life}` }) : null,
        stateMark({ held: artist.held }),
      ]),
    ]),
  );
}
