/* Search results — everything a few words find, grouped by what you hold.
 *
 * Ruling 2 (one world): one page lists what the library holds and what the
 * registry knows. Two groups, **Held** then **Not held**, each listing its
 * artists, works and topics (the owner, 2026-10-06, after a search found
 * nothing held and the page, then narrowed to the library, offered no way on).
 * Held is the library's matches, and any of Wikidata's the library holds but
 * its own rows do not show; Not held is the rest of Wikidata's. A group with
 * nothing in it is one line, never a "No artists." for each kind. If the words
 * name exactly one artist, that artist leads the page, one step from their hub.
 *
 * **Reached by Enter in the search box**, and by the dropdown's last row,
 * *All results for "…"*. Contextual, so it returns to the page it was opened
 * from. A `view=` left in an old address, from when *All*, *In your library*
 * and *Not held* narrowed the page, is ignored: both groups are always shown.
 *
 * **The Held group is drawn first and never waits** on Wikidata, whose two
 * searches each fill their own kinds when they answer and say why when they
 * cannot. Nothing on this page spends: *Ask about* fills in Ask and does not
 * start it, and *Get* is free.
 *
 * Every string from the registry is untrusted text, shown as text. */

import { api } from "../core/api.js";
import { getSelection } from "../core/getting.js";
import { lifeDates, named, stateMark, topicKinds, topicName, workState } from "../core/registry.js";
import { el, fill, render } from "../core/render.js";
import { backLink, link, setTitle } from "../core/router.js";
import { asksWikidata, fold } from "../core/search.js";
import { state } from "../core/state.js";

/* How many of the library's works the page lists. Artworks, one click away,
 * holds the rest and the tools to act on them. */
const WORKS_SHOWN = 50;

const KINDS = [
  ["artists", "Artists"],
  ["works", "Works"],
  ["topics", "Topics"],
];

/* Each kind's heading carries its half, unseen, so a screen reader's list of
 * regions says "Held: Artists" and "Not held: Artists" rather than "Artists"
 * twice: a topic row has no mark of its own to say which half it is in. */
const HALVES = { held: "Held", "not-held": "Not held" };

export async function viewSearch(generation) {
  const query = (state.params.q || "").trim();
  if (!query) {
    render(generation, el("p", {}, [backLink()]), el("h1", { text: "Search" }), el("p", { class: "note", text: "Type in the search box above to search." }));
    return;
  }
  // Asked now, beside the library, and awaited after the Held group is drawn.
  // The topic search is the slower of the two, so each fills its own kinds.
  const fromRegistry = api(`/api/registry/search?q=${encodeURIComponent(query)}&wide=true`).catch(() => ({
    state: "unavailable",
    note: "Wikidata could not be searched just now.",
    artists: [],
    works: [],
  }));
  // Below the registry's floor the artist and work search says so itself; the
  // topic search is simply not asked.
  const fromTopics = asksWikidata(query)
    ? api(`/api/registry/topics?q=${encodeURIComponent(query)}`).catch(() => ({
        state: "unavailable",
        note: "Wikidata's topics could not be searched just now.",
        topics: [],
      }))
    : Promise.resolve({ state: "known", note: null, topics: [] });
  const [page, people, ours] = await Promise.all([
    api(`/api/works?q=${encodeURIComponent(query)}&limit=${WORKS_SHOWN}`),
    api(`/api/artists?q=${encodeURIComponent(query)}`),
    // The library's topics fail on their own: the artists and works above them
    // still stand, and the Held group says the topics could not be listed.
    api("/api/topics").catch(() => null),
  ]);

  const everyTopic = (ours ? ours.kinds : []).flatMap((group) => group.topics.map((topic) => ({ ...topic, kind: group.kind })));
  const wanted = fold(query);
  const library = {
    artists: people.artists.map((entry) => entry.artist),
    works: page.works,
    total: page.total,
    topics: everyTopic.filter((topic) => fold(topic.label).includes(wanted)),
    // Every topic the library's works are in, matched by name or not: one of
    // Wikidata's that is among them is held, not *Not held*.
    topicIds: new Set(everyTopic.map((topic) => topic.qid)),
  };

  const top = el("div");
  const section = (half, kind) => {
    const node = el("section", { class: "results-kind", "aria-labelledby": `results-${half}-${kind}` });
    node.hidden = true;
    return node;
  };
  const sections = {
    held: Object.fromEntries(KINDS.map(([kind]) => [kind, section("held", kind)])),
    "not-held": Object.fromEntries(KINDS.map(([kind]) => [kind, section("not-held", kind)])),
  };
  const nothingHeld = el("p", { class: "muted results-none", text: "Nothing you hold matches." });
  // The Not held group's one line, whatever Wikidata did: asking, found,
  // nothing more, or why it could not be asked.
  const registryNote = el("p", { class: "muted", "aria-live": "polite", text: "Asking Wikidata…" });
  setTitle(generation, `Results for “${query}”`);
  render(
    generation,
    el("p", {}, [backLink()]),
    el("h1", { text: `Results for “${query}”` }),
    top,
    el("section", { class: "panel", "aria-labelledby": "results-held" }, [
      el("h2", { id: "results-held", text: "Held" }),
      nothingHeld,
      ours ? null : el("p", { class: "muted results-topics-failed", text: "Your topics could not be listed just now." }),
      ...KINDS.map(([kind]) => sections.held[kind]),
    ]),
    el("section", { class: "panel", "aria-labelledby": "results-not-held" }, [
      el("h2", { id: "results-not-held", text: "Not held" }),
      registryNote,
      ...KINDS.map(([kind]) => sections["not-held"][kind]),
    ]),
  );

  // One selection for the page, painted once: the works are drawn when the
  // artist and work search answers, and the topic search arriving later does
  // not redraw them, so a box already ticked stays ticked.
  const getting = getSelection();
  const registry = { found: null, named: null };
  const paintFound = () => {
    const artists = artistRows(library, registry.found);
    paintKind(sections.held.artists, "held", "artists", artists.held.map(artistRow));
    paintKind(sections["not-held"].artists, "not-held", "artists", artists.notHeld.map(artistRow));
    const works = workRows(library, registry.found, getting);
    paintKind(sections.held.works, "held", "works", works.held.map(workRow), artworksLink(query, library));
    paintKind(
      sections["not-held"].works,
      "not-held",
      "works",
      works.notHeld.map(workRow),
      works.notHeld.length ? getting.node : null,
    );
    paintTop(top, query, [...artists.held, ...artists.notHeld]);
  };
  const paintNamed = () => {
    const topics = topicRows(library, registry.named);
    paintKind(sections.held.topics, "held", "topics", topics.held.map(topicRow));
    paintKind(sections["not-held"].topics, "not-held", "topics", topics.notHeld.map(topicRow));
  };
  const settle = () => {
    nothingHeld.hidden = KINDS.some(([kind]) => !sections.held[kind].hidden);
  };
  paintFound();
  paintNamed();
  settle();

  const arrive = (part, paint) => (answer) => {
    if (!registryNote.isConnected) return;
    registry[part] = answer;
    paint();
    settle();
    if (registry.found && registry.named) sayWhatWikidataDid(registryNote, query, registry, sections["not-held"]);
  };
  await Promise.all([fromRegistry.then(arrive("found", paintFound)), fromTopics.then(arrive("named", paintNamed))]);
}

/* Said in the Not held group once both of Wikidata's searches have answered.
 * An empty Not held group is this one line: "Wikidata has nothing more." when
 * everything it found is already under Held, and, when it found nothing at all,
 * that, with *Ask about* below it. */
function sayWhatWikidataDid(note, query, { found, named }, notHeld) {
  if (found.state === "too_short") {
    note.textContent = "Wikidata is searched from three letters.";
    return;
  }
  if (found.state !== "known") {
    note.textContent = found.note || "";
    return;
  }
  if (named.state !== "known") {
    note.textContent = named.note || "";
    return;
  }
  const total = found.artists.length + found.works.length + named.topics.length;
  const anyNotHeld = KINDS.some(([kind]) => !notHeld[kind].hidden);
  if (anyNotHeld) {
    note.textContent = `Wikidata found ${total} for “${query}”.`;
    return;
  }
  if (total) {
    note.textContent = "Wikidata has nothing more.";
    return;
  }
  note.textContent = `Wikidata has nothing for “${query}”.`;
  note.after(
    el("div", { class: "row" }, [
      link({ view: "discover", params: { term: query } }, { class: "action", text: `Ask about “${query}”` }),
    ]),
  );
}

/* One kind in one group: its heading and rows, or nothing at all. A kind with
 * no rows is left out rather than saying so, so an empty group is one line. */
function paintKind(section, half, kind, rows, ...after) {
  if (!rows.length) {
    fill(section);
    section.hidden = true;
    return;
  }
  const heading = KINDS.find(([key]) => key === kind)[1];
  fill(
    section,
    el("h3", { id: `results-${half}-${kind}` }, [el("span", { class: "visually-hidden", text: `${HALVES[half]}: ` }), heading]),
    el("ul", { class: "results-list" }, rows),
    ...after,
  );
  section.hidden = false;
}

/* The artists: the library's, and Wikidata's split by whether the library holds
 * them, leaving out any the library's rows already show. */
function artistRows(library, found) {
  const shown = new Set(library.artists.map((artist) => artist.artist_id));
  const held = library.artists.map((artist) => ({
    name: artist.name,
    life: lifeDates(artist),
    held: true,
    open: { view: "artist", id: artist.artist_id },
  }));
  const notHeld = [];
  if (found && found.state === "known") {
    for (const person of found.artists) {
      if (person.artist_id && shown.has(person.artist_id)) continue;
      const row = {
        name: named(person.name, person.qid),
        life: lifeDates(person),
        held: Boolean(person.artist_id),
        open: { view: "artist", id: person.artist_id || person.qid },
      };
      (row.held ? held : notHeld).push(row);
    }
  }
  return { held, notHeld };
}

/* No mark: the group heading the row sits under says whether the library holds
 * them, and a mark beside it said it again (the owner, 2026-10-06). The top
 * result, which sits under no group, keeps its mark. */
function artistRow(row) {
  return el("li", {}, [
    link(row.open, { class: "row-title", text: row.name }),
    row.life ? el("span", { class: "muted", text: ` ${row.life}` }) : null,
  ]);
}

/* The works: the library's first, and Wikidata's split the same way. A work the
 * library does not hold can be ticked and got from here. */
function workRows(library, found, getting) {
  const shown = new Set(library.works.map((work) => work.artwork_id));
  const held = library.works.map((work) => ({
    title: work.title,
    by: work.artist ? work.artist.name : null,
    mark: workState({ held_artwork_ids: [work.artwork_id] }, { opens: false }),
    open: { view: "work", id: work.artwork_id },
  }));
  const notHeld = [];
  if (found && found.state === "known") {
    for (const work of found.works) {
      const isHeld = work.held_artwork_ids.length > 0;
      if (isHeld && work.held_artwork_ids.some((id) => shown.has(id))) continue;
      const row = {
        title: named(work.title, work.qid),
        by: work.creator ? named(work.creator.name, work.creator.qid) : null,
        mark: workState(work, { opens: false, grouped: true }),
        open: { view: "work", id: isHeld ? work.held_artwork_ids[0] : work.qid },
        box: isHeld ? null : getting.box(work.qid, named(work.title, work.qid)),
      };
      (isHeld ? held : notHeld).push(row);
    }
  }
  return { held, notHeld };
}

function workRow(row) {
  return el("li", {}, [
    row.box || null,
    link(row.open, { class: "row-title", text: row.title }),
    row.by ? el("span", { class: "muted", text: ` — ${row.by}` }) : null,
    row.mark,
  ]);
}

/* The way to the library's matches in Artworks, whose grid has the tools to act
 * on them. Offered whenever the library has a match: Artworks has no words
 * filter of its own to reach them by. */
function artworksLink(query, library) {
  if (!library.works.length) return null;
  const more = library.total > library.works.length;
  return el("p", { class: "muted" }, [
    more ? `Your library has ${library.total} matching works; the first ${library.works.length} are here. ` : "",
    link({ view: "collection", params: { q: query } }, { class: "link", text: library.total > 1 ? `All ${library.total} in Artworks` : "Open in Artworks" }),
  ]);
}

/* The topics: the library's whose names hold the words, then Wikidata's, held
 * when the library's works are in it and not already listed. */
function topicRows(library, found) {
  const shown = new Set(library.topics.map((topic) => topic.qid));
  const held = library.topics.map((topic) => ({
    name: `${topicName(topic.label, topic.qid)} — ${topicKinds([topic.kind])}`,
    description: null,
    open: { view: "topic", id: topic.qid },
  }));
  const notHeld = [];
  if (found && found.state === "known") {
    for (const topic of found.topics) {
      if (shown.has(topic.qid)) continue;
      const row = {
        name: `${topicName(topic.label, topic.qid)} — ${topicKinds(topic.kinds)}`,
        // What tells six *Impressionism*s apart.
        description: topic.description,
        open: { view: "topic", id: topic.qid },
      };
      (library.topicIds.has(topic.qid) ? held : notHeld).push(row);
    }
  }
  return { held, notHeld };
}

function topicRow(row) {
  return el("li", {}, [
    link(row.open, { class: "row-title", text: row.name }),
    row.description ? el("span", { class: "muted", text: ` · ${row.description}` }) : null,
  ]);
}

/* The words name one artist when exactly one artist found carries every word
 * of them in their name, accents and case ignored. That artist leads the page. */
function paintTop(section, query, artists) {
  const words = fold(query).split(/\s+/).filter(Boolean);
  const naming = artists.filter((row) => words.every((word) => fold(row.name).includes(word)));
  if (naming.length !== 1) {
    fill(section);
    return;
  }
  const [artist] = naming;
  fill(section,
    el("section", { class: "panel", "aria-labelledby": "results-top" }, [
      el("h2", { id: "results-top", text: "Top result" }),
      el("p", {}, [
        link(artist.open, { class: "row-title", text: artist.name }),
        artist.life ? el("span", { class: "muted", text: ` ${artist.life}` }) : null,
        stateMark({ held: artist.held }),
      ]),
    ]),
  );
}
