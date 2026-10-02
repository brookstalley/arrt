/* The persistent search affordance.
 *
 * `information-architecture.md` § Navigation Structure keeps search in the top
 * bar on every page, as the *arr apps do, and for this product's own reason: at
 * thousands of works it is the primary way in, and a search you must first
 * navigate to is one more step on the most frequent action.
 *
 * Searching is a **navigation**, not a mode. It writes `?q=` into the fragment
 * and goes to Artworks, which means a search is bookmarkable, sendable, and —
 * because it lands in the history like every other navigation — undone by the
 * browser's own back button rather than by a Clear control the curator has to
 * find.
 */

import { api } from "./api.js";
import { named, stateMark } from "./registry.js";
import { el, fill } from "./render.js";
import { go, openedFrom } from "./router.js";
import { state } from "./state.js";

/* The field shows the search that is currently in the address bar.
 *
 * Skipped while the field has focus. A curator mid-word is the one person whose
 * text must not be replaced by the state a repaint thinks is current, and a
 * repaint happens on every navigation — including the one the typing is about to
 * cause. */
export function paintSearch() {
  const field = document.getElementById("search");
  const current = state.params.q || "";
  if (document.activeElement !== field && field.value !== current) field.value = current;
}

/* How many library matches the dropdown shows. Enough to recognise the one you
 * meant; more is what Enter, which opens every match in Artworks, is for. */
const SUGGESTIONS = 6;

/* How many artists the dropdown offers, above the works. Few, because a name
 * typed in full matches one, and a fragment that matches many is better served
 * by Library › Artists than by a long list here. */
const ARTISTS_SHOWN = 3;

/* Wait this long after the last keystroke before asking, so typing a word asks
 * once rather than once a letter. The registry is asked at the same pause, and
 * remembers each query, so typing back over a word asks it nothing. */
const PAUSE_MS = 200;

/* How many themes the dropdown offers, matched by name. */
const THEMES_SHOWN = 3;

/* Fewer letters than this and the registry is not asked: the server's own floor,
 * repeated here only so the dropdown does not send a request the server would
 * answer with `too_short`. */
const REGISTRY_SHORTEST = 3;

/* Case and accents, ignored, as the library's search ignores them. */
export function fold(text) {
  return text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
}

/* The dropdown under the search box: Sonarr's two groups, in Arrt's words.
 *
 * `information-architecture.md` § The *arr layout records Sonarr's pattern from
 * its source: the box searches the library as you type, and the last row offers
 * the same words as a search of everything. Here that row goes to Ask with
 * the words filled in, and Ask does not start the search, because a search in
 * words is a paid run and nothing may spend on a keystroke.
 *
 * **Enter with nothing highlighted opens Artworks filtered to the query**, as it
 * did before the dropdown existed. That departs from Sonarr, which opens the
 * first match, and the owner ruled it on 2026-09-30: an artist or a movement
 * matches many works where a series title matches one.
 *
 * **One world** (ruling 2): below the library's matches, Wikidata's artists and
 * works, each saying whether it is held. They arrive after the library's rows,
 * which never wait for them; a match the library's rows already show is not
 * shown twice; and their arrival is announced, not focused, so a curator
 * arrowing through the list is not moved.
 *
 * An ARIA combobox: the input keeps focus, arrow keys move
 * `aria-activedescendant` through the options, Escape closes the list, and the
 * groups are named so a screen reader says which one an option is in. */
function installSuggestions(field) {
  // Its own class name: `.suggestions` is a conversation turn's block, and a
  // shared name gave every turn the dropdown's absolute positioning.
  const list = el("ul", { id: "search-suggestions", class: "search-suggestions", role: "listbox", "aria-label": "Suggestions" });
  list.hidden = true;
  // The registry's rows arrive after the list is open: said here, once, rather
  // than by moving focus to them.
  const arrived = el("p", { class: "visually-hidden", "aria-live": "polite" });
  field.after(list, arrived);
  field.setAttribute("role", "combobox");
  field.setAttribute("aria-autocomplete", "list");
  field.setAttribute("aria-controls", "search-suggestions");
  field.setAttribute("aria-expanded", "false");

  let options = [];
  let active = -1;
  let asked = 0;
  let timer = null;

  const close = () => {
    list.hidden = true;
    field.setAttribute("aria-expanded", "false");
    field.removeAttribute("aria-activedescendant");
    options = [];
    active = -1;
  };

  const highlight = (index) => {
    active = index;
    options.forEach((option, at) => option.node.setAttribute("aria-selected", at === index ? "true" : "false"));
    if (index < 0) field.removeAttribute("aria-activedescendant");
    else field.setAttribute("aria-activedescendant", options[index].node.id);
  };

  const choose = (option) => {
    close();
    option.act();
  };

  // `content` is the row's words, or its words and a state badge.
  const option = (id, content, act) => {
    const node =
      typeof content === "string"
        ? el("li", { id, role: "option", "aria-selected": "false", text: content })
        : el("li", { id, role: "option", "aria-selected": "false" }, content);
    // Mousedown rather than click: a click lands after the field's blur, which
    // has already closed the list the click was aimed at.
    node.addEventListener("mousedown", (event) => {
      event.preventDefault();
      choose(entry);
    });
    const entry = { node, act };
    return entry;
  };

  const group = (id, label, entries) =>
    el("li", { role: "presentation" }, [
      el("ul", { role: "group", "aria-labelledby": id }, [
        el("li", { id, role: "presentation", class: "search-suggestions-label", text: label }),
        ...entries.map((entry) => entry.node),
      ]),
    ]);

  const paint = (query, works, artists, themes, registry, failed, { keepHighlight = false } = {}) => {
    // Kept only across the repaint the registry's answer causes, so a curator who
    // has arrowed to a row stays on it. A new query starts with nothing
    // highlighted: row ids are positions, and a highlight carried to a new query
    // lands on whatever now sits there, which Enter would then open instead of
    // searching Artworks.
    const kept = keepHighlight && active >= 0 ? options[active].node.id : null;
    // Artists first, as the IA ranks objects: an artist's name is most often
    // what is typed, and their page is where the rest of the library is.
    const shownArtists = artists.slice(0, ARTISTS_SHOWN);
    const people = shownArtists.map((entry, at) =>
      option(`suggestion-artist-${at}`, `${entry.artist.name} — artist`, () => go("artist", entry.artist.artist_id)),
    );
    const held = works.map((work, at) =>
      option(`suggestion-work-${at}`, work.artist ? `${work.title} — ${work.artist.name}` : work.title, () =>
        go("work", work.artwork_id),
      ),
    );
    const matchedThemes = themes.map((placement, at) =>
      option(`suggestion-theme-${at}`, `${placement.theme.name} — theme`, () => go("theme", placement.theme.theme_id)),
    );
    // What the library's rows already show is not offered again as Wikidata's.
    const shownArtistIds = new Set(shownArtists.map((entry) => entry.artist.artist_id));
    const shownWorkIds = new Set(works.map((work) => work.artwork_id));
    const known = registry && registry.state === "known" ? registry : { artists: [], works: [] };
    const theirPeople = known.artists
      .filter((person) => !shownArtistIds.has(person.artist_id))
      .map((person, at) => option(`suggestion-registry-artist-${at}`, registryPersonRow(person), () => go("artist", person.artist_id || person.qid)));
    const theirWorks = known.works
      .filter((work) => !work.held_artwork_ids.some((id) => shownWorkIds.has(id)))
      .map((work, at) =>
        option(`suggestion-registry-work-${at}`, registryWorkRow(work), () =>
          work.held_artwork_ids.length ? go("work", work.held_artwork_ids[0]) : go("work", work.qid),
        ),
      );
    // Ask, with the words filled in and nothing started: asking for something
    // in words is a paid search, started only from its own page beside its price.
    const ask = option("suggestion-ask", `Ask about “${query}”`, () => go("discover", null, { term: query }));
    // The dropdown's last row: every match on a page of its own. Enter keeps
    // opening Artworks filtered (the owner, 2026-10-01), so this is how the
    // results page is reached.
    const everything = option("suggestion-all-results", `All results for “${query}”`, () => go("search", null, { ...openedFrom("search"), q: query }));
    options = [...people, ...held, ...matchedThemes, ...theirPeople, ...theirWorks, ask, everything];
    // A lookup that failed is not a library with no matches, and must not read as
    // one: the row below it spends money, on a work the curator may already own.
    const unsearched = failed
      ? [
          el("li", {
            role: "presentation",
            class: "search-suggestions-note",
            text: "Your library could not be searched just now.",
          }),
        ]
      : [];
    // Wikidata off or down is said, once, where its rows would be: a library
    // that matched nothing must not read as everything having been searched.
    const registryNote =
      registry && registry.note
        ? [el("li", { role: "presentation", class: "search-suggestions-registry-note", text: registry.note })]
        : [];
    fill(list,
      ...unsearched,
      ...(people.length ? [group("suggestions-artists", "Artists", people)] : []),
      ...(held.length ? [group("suggestions-held", "In your library", held)] : []),
      ...(matchedThemes.length ? [group("suggestions-themes", "Themes", matchedThemes)] : []),
      ...(theirPeople.length ? [group("suggestions-registry-artists", "Wikidata: artists", theirPeople)] : []),
      ...(theirWorks.length ? [group("suggestions-registry-works", "Wikidata: works", theirWorks)] : []),
      ...registryNote,
      // Named for the page the row opens, as Sonarr names its group "Add New
      // Series" for its page. Here that page is Ask (ruling 3).
      group("suggestions-ask", "Ask", [ask]),
      group("suggestions-all-results", "Search", [everything]),
    );
    list.hidden = false;
    field.setAttribute("aria-expanded", "true");
    highlight(options.findIndex((entry) => entry.node.id === kept));
  };

  const ask = async () => {
    const query = field.value.trim();
    const ticket = ++asked;
    if (!query) {
      close();
      return;
    }
    let works = [];
    let artists = [];
    let themes = [];
    let failed = false;
    // Asked now and awaited after the library's rows are drawn: see above.
    const letters = (query.match(/[\p{L}\p{N}]/gu) || []).length;
    const fromRegistry =
      letters >= REGISTRY_SHORTEST
        ? api(`/api/registry/search?q=${encodeURIComponent(query)}&prefix=true`).catch(() => ({
            state: "unavailable",
            note: "Wikidata could not be searched just now.",
          }))
        : null;
    // Settled separately: the artist and theme lookups are extras, and their
    // failure must not cost the work matches. Only the works lookup failing says
    // the library could not be searched, because that one guards a paid search
    // below it.
    const [page, people, placed] = await Promise.allSettled([
      api(`/api/works?q=${encodeURIComponent(query)}&limit=${SUGGESTIONS}`),
      api(`/api/artists?q=${encodeURIComponent(query)}`),
      api("/api/themes"),
    ]);
    if (people.status === "fulfilled") artists = people.value.artists;
    if (placed.status === "fulfilled") {
      const wanted = fold(query);
      themes = placed.value.themes.filter((placement) => fold(placement.theme.name).includes(wanted)).slice(0, THEMES_SHOWN);
    }
    // The dropdown is a shortcut; the search itself still works on Enter. So a
    // failed lookup costs the matches, says so, and keeps the other row.
    if (page.status === "fulfilled") works = page.value.works;
    else failed = true;
    // A slower answer to an earlier keystroke must not replace a later one.
    if (ticket !== asked || document.activeElement !== field) return;
    paint(query, works, artists, themes, null, failed);
    if (!fromRegistry) return;
    const registry = await fromRegistry;
    if (ticket !== asked || document.activeElement !== field) return;
    paint(query, works, artists, themes, registry, failed, { keepHighlight: true });
    const count = registry.state === "known" ? registry.artists.length + registry.works.length : 0;
    arrived.textContent = registry.state === "known" ? `Wikidata: ${count} ${count === 1 ? "match" : "matches"}.` : registry.note || "";
  };

  field.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(ask, PAUSE_MS);
  });
  field.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      if (!list.hidden) {
        event.preventDefault();
        close();
      }
      return;
    }
    if (list.hidden || !options.length) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      highlight((active + 1) % options.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      highlight(active <= 0 ? options.length - 1 : active - 1);
    } else if (event.key === "Enter" && active >= 0) {
      event.preventDefault();
      choose(options[active]);
    }
  });
  field.addEventListener("blur", () => {
    clearTimeout(timer);
    asked += 1;
    close();
  });
  return () => {
    clearTimeout(timer);
    asked += 1;
    close();
  };
}

export function installSearch() {
  const form = document.getElementById("search-form");
  const field = document.getElementById("search");
  const dismiss = installSuggestions(field);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    dismiss();
    const query = field.value.trim();
    // Filters already in the address survive a search made from Artworks, and
    // do not follow one made from anywhere else: narrowing what you are looking
    // at is a different act from starting a search over the whole collection,
    // and carrying a rail's state onto the second would silently hide most of
    // the answers.
    const params = state.view === "collection" ? { ...state.params, q: query } : { q: query };
    go("collection", null, params);
  });
}

/* The way out of a search, offered where the emptiness is. Written here beside
 * the affordance it undoes rather than in the screen, so the two cannot come to
 * disagree about what clearing a search means. */
export function clearSearchLink(text = "Clear the search") {
  return el("button", {
    class: "action quiet",
    type: "button",
    text,
    onclick: () => go("collection", null, { ...state.params, q: "" }),
  });
}

/* A registry artist as a row: the name and the years that tell two apart, and
 * *Held* when the library holds them. */
function registryPersonRow(person) {
  const years = person.born || person.died ? ` (${person.born || "?"}–${person.died || ""})` : "";
  return [
    `${named(person.name, person.qid)}${years} — artist`,
    stateMark({ held: Boolean(person.artist_id) }),
  ];
}

/* A registry work as a row: title, maker, and its state as every badge here
 * carries one, glyph and word and colour (`accessibility-spec.md`). */
function registryWorkRow(work) {
  const maker = work.creator ? ` — ${named(work.creator.name, work.creator.qid)}` : "";
  return [`${named(work.title, work.qid)}${maker}`, stateMark({ held: work.held_artwork_ids.length > 0, image: Boolean(work.image) })];
}
