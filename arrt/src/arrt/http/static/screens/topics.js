/* Topics — the periods, movements, subjects and media your works are in, and one topic's page.
 *
 * **Library › Topics** (`#topics`, the owner's ruling of 2026-10-02 in
 * `build-plan-topics-and-destinations.md`) lists every topic the library's works
 * are in, by kind, each with how many, and searches Wikidata for any other.
 * Beside them it offers the centuries from the 13th to the 21st and a short list
 * of movements whether or not a work is in them (the server's `OFFERED_TOPICS`),
 * so a curator need not know a period's name to open it.
 * **A Topic page** (`#topic/<qid>`) is browsed like a genre: what the topic is,
 * your works in it, the works it is known for with their states, and its
 * artists. Ticked works are got into a theme named after the topic by default,
 * the start of S12 (`ia-proposal.md` § Topic).
 *
 * **The library's half is drawn first and never waits.** `GET /api/topics` and
 * `GET /api/topics/<qid>` read the facet rows and ask no registry. Wikidata's
 * half is three separate requests, asked after the page is drawn, each filling
 * its own section and saying why when it cannot: a period's works took 7 to 26
 * seconds to ask for (`wikidata-findings.md` § Topics), and the Artist page's
 * *Their work* set the pattern (`screens/artists.js`). The works are streamed,
 * so they are drawn when their ranking lands rather than after their makers.
 *
 * **Every string from the registry is untrusted text.** Labels, descriptions,
 * titles and names reach the page through `el`'s `text`; the only link out is
 * built from a QID checked against `Q` and digits, never from a URL. */

import { api, apiLines } from "../core/api.js";
import { absentImage, facts, workName } from "../core/badges.js";
import { counted } from "../core/counting.js";
import { selectionMode } from "../core/selecting.js";
import { toolbar } from "../core/toolbar.js";
import {
  gettable,
  isQid,
  lifeDates,
  named,
  personLink,
  stateMark,
  TOPIC_KINDS,
  topicKinds,
  topicName,
  topicYears,
  byCell,
  listHeadings,
  wikidataLink,
  workCell,
  workState,
  yearCell,
} from "../core/registry.js";
import { el, emptyState, fill, render } from "../core/render.js";
import { backLink, go, link, setTitle } from "../core/router.js";
import { state } from "../core/state.js";

/* What a section says when its request failed outright, rather than answering
 * with a state of its own. The server's own sentence for an outage, so the
 * page reads the same whichever of the two it was. */
const UNAVAILABLE = "Wikidata could not be asked just now. Try again later.";

/* -- Library › Topics ------------------------------------------------------- */

export async function viewTopics(generation) {
  // `find`, not `q`: the top bar's box shows `q` on every page, and this is
  // not a search of the artworks it would claim.
  const query = (state.params.find || "").trim();
  const listing = await api("/api/topics");
  const configured = listing.state === "known";
  const found = el("section", { class: "panel", "aria-labelledby": "topic-search" });
  const held = listing.kinds.some((group) => group.topics.length);
  // With nothing held, only the kinds the server offers topics of: the empty
  // state says once that no work is in a topic, rather than once per kind.
  const groups = held
    ? listing.kinds.map((group) => kindSection(group))
    : listing.kinds.filter((group) => offeredOf(group).length).map((group) => kindSection(group, { libraryEmpty: true }));
  render(
    generation,
    el("h1", { text: "Topics" }),
    // Said first, and only when it is so: without a registry the groups hold
    // what an earlier configuration recorded, and nothing renews them.
    configured ? null : el("p", { class: "note", text: listing.note }),
    // A search that can only answer "not configured" is a dead end, so it is
    // not offered then (`information-architecture.md` § A control never
    // offers a dead end).
    configured ? searchForm(query) : null,
    configured && query ? found : null,
    held
      ? null
      : emptyState(
          "None of your works is in a topic yet.",
          "A work's topics are read from Wikidata once it, or its artist, is matched to a Wikidata item.",
        ),
    ...groups,
  );
  if (configured && query) await paintFound(found, query);
}

/* One kind's topics, each opening its page, with how many of your works are in
 * it: in columns, by name, so a kind of thirty fits in a few rows at desktop
 * width and still reads as one column on a phone (the owner's ruling on #175). */
function kindSection(group, { libraryEmpty = false } = {}) {
  const words = TOPIC_KINDS[group.kind] || [group.kind, group.kind];
  const id = `topics-${group.kind}`;
  const offers = offeredOf(group);
  return el("section", { class: "panel", "aria-labelledby": id }, [
    el("h2", { id, text: words[1] }),
    group.topics.length
      ? el("ul", { class: "results-list topic-columns topic-held" }, group.topics.map((topic) =>
          el("li", {}, [
            link({ view: "topic", id: topic.qid }, { class: "row-title", text: topicName(topic.label, topic.qid) }),
            el("span", { class: "muted", text: ` · ${counted(topic.works, "work")}` }),
          ]),
        ))
      : libraryEmpty
        ? null
        : el("p", { class: "muted", text: `None of your works is in a ${words[0]}.` }),
    offers.length ? el("h3", { text: offeredHeading(group) }) : null,
    offers.length
      ? el("ul", { class: "results-list topic-columns topic-offered" }, offers.map((offer) =>
          el("li", {}, [link({ view: "topic", id: offer.qid }, { class: "row-title", text: topicName(offer.label, offer.qid) })]),
        ))
      : null,
  ]);
}

/* The topics the server offers of a kind whether or not a work is in them:
 * the centuries from the 13th to the 21st and a short list of movements, so S12
 * can open the 16th century without its name being typed. The server leaves out
 * any already listed above with a count, and offers none without Wikidata. */
function offeredOf(group) {
  return group.offered || [];
}

/* What the offered list is headed: "Centuries", or "Other centuries" under the
 * ones your works are in. */
const OFFERED_WORDS = { period: "centuries", movement: "major movements" };

function offeredHeading(group) {
  const words = OFFERED_WORDS[group.kind] || (TOPIC_KINDS[group.kind] || [group.kind, group.kind])[1].toLowerCase();
  return group.topics.length ? `Other ${words}` : words.charAt(0).toUpperCase() + words.slice(1);
}

/* *Find a topic*: any period, movement, subject or medium Wikidata knows, not
 * only those your works are in. A navigation, so the search is in the address
 * and Back undoes it, as the top bar's is. */
function searchForm(query) {
  // Text, as every other field on a page here is, so it takes their styling.
  const field = el("input", { type: "text", id: "topic-search-words", autocomplete: "off", value: query });
  const form = el("form", { class: "row", role: "search", "aria-label": "Topics Wikidata knows" }, [
    el("div", { class: "field" }, [el("label", { for: "topic-search-words", text: "Find a topic" }), field]),
    el("button", { class: "action", type: "submit", text: "Find" }),
  ]);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    go("topics", null, { find: field.value.trim() });
  });
  return el("div", { class: "panel" }, [form]);
}

async function paintFound(section, query) {
  const heading = el("h2", { id: "topic-search", text: `Topics Wikidata finds for “${query}”` });
  fill(section, heading, el("p", { class: "muted", "aria-live": "polite", text: "Asking Wikidata…" }));
  let answer;
  try {
    answer = await api(`/api/registry/topics?q=${encodeURIComponent(query)}`);
  } catch (failure) {
    answer = { state: "unavailable", note: UNAVAILABLE, topics: [] };
  }
  if (!section.isConnected) return;
  if (answer.state !== "known") {
    fill(section, heading, el("p", { class: "note", text: answer.note }));
    return;
  }
  fill(section,
    heading,
    answer.topics.length
      ? el("ul", { class: "results-list" }, answer.topics.map((topic) =>
          el("li", {}, [
            link({ view: "topic", id: topic.qid }, { class: "row-title", text: topicName(topic.label, topic.qid) }),
            el("span", { class: "muted", text: ` — ${[topicKinds(topic.kinds), topicYears(topic)].filter(Boolean).join(", ")}` }),
            // What tells six *Impressionism*s apart: the music one, the Greek one.
            topic.description ? el("p", { class: "muted", text: topic.description }) : null,
          ]),
        ))
      : el("p", { class: "muted", text: `Wikidata has no period, movement, subject or medium called “${query}”.` }),
  );
}

/* -- one topic -------------------------------------------------------------- */

export async function viewTopic(qid, generation) {
  let page;
  try {
    page = await api(`/api/topics/${encodeURIComponent(qid)}`);
  } catch (failure) {
    // Only the refusal says the address is wrong; a fault is the error banner's.
    if (failure.status !== 400) throw failure;
    render(
      generation,
      el("p", {}, [backLink()]),
      el("h1", { text: "That is not a topic's address" }),
      el("p", { class: "note", text: "A topic is addressed by its Wikidata item, a Q and digits. The topics your works are in are listed together." }),
      el("div", { class: "row" }, [link({ view: "topics" }, { class: "action", text: "All topics" })]),
    );
    return;
  }
  // The server's QID, which it has checked; checked again here because it is
  // about to become part of an address out.
  const item = isQid(page.qid) ? page.qid : null;
  const title = page.label ? topicName(page.label, page.qid) : `Wikidata ${page.qid}`;
  setTitle(generation, title);
  const name = el("h1", { text: title });
  const kinds = el("div");
  const about = el("div", { class: "stack" });
  const showKinds = (list) => fill(kinds, facts([["Kind", topicKinds(list)]]));
  showKinds(page.kinds);
  const head = el("div", { class: "panel" }, [
    name,
    kinds,
    about,
    item ? el("p", { class: "muted" }, [wikidataLink(item, `Wikidata ${item}`)]) : null,
  ]);
  const worksSection = asking("representative-works", "Representative works");
  const artistsSection = asking("topic-artists", "Artists");
  // Where the selection's toggle and bar go once the works to tick have arrived
  // (`paintWorks`), since a Get from them is named after the topic.
  const toggleSlot = el("span");
  const barSlot = el("span");
  render(generation, el("p", {}, [backLink()]), head, toggleSlot, heldSection(page.works), worksSection, artistsSection, barSlot);

  // After the page is drawn, all three at once, each into its own section. The
  // works wait for the head as well: a period's are headed with its years, and
  // a Get from them is named after the topic.
  const ask = (path, empty) =>
    api(path).catch(() => ({ state: "unavailable", note: UNAVAILABLE, ...empty }));
  const base = `/api/topics/${encodeURIComponent(page.qid)}`;
  const headAsked = ask(`${base}/registry`, {});
  const artistsAsked = ask(`${base}/artists`, { artists: [] });
  // The works are streamed, a line as each of Wikidata's answers lands: the
  // ranked works first, their makers after (`get_topic_works`). Each line is
  // the whole section so far and is painted as it comes, once the head is
  // known; the last says it is complete, and a stream that ends short of that
  // is an outage, said as one.
  let known = null;
  let works = null;
  const showWorks = () => {
    if (known && works && worksSection.isConnected) {
      paintWorks(worksSection, known, works, defaultName(page, known), { toggleSlot, barSlot });
    }
  };
  const unavailable = { state: "unavailable", note: UNAVAILABLE, works: [], complete: true };
  const worksAsked = apiLines(`${base}/works`, (line) => {
    works = line;
    showWorks();
  })
    .then(() => {
      if (!works || !works.complete) throw new Error("the works' answer ended before its last line");
    })
    .catch(() => {
      works = unavailable;
      showWorks();
    });
  await Promise.all([
    (async () => {
      known = await headAsked;
      if (!head.isConnected) return;
      if (known.state === "known") {
        name.textContent = topicName(known.label, page.qid);
        showKinds(known.kinds);
        fill(about, known.description ? el("p", { text: known.description }) : null);
      } else {
        fill(about, el("p", { class: "note", text: known.note }));
      }
      showWorks();
      await worksAsked;
    })(),
    (async () => {
      const people = await artistsAsked;
      if (!artistsSection.isConnected) return;
      paintArtists(artistsSection, people);
    })(),
  ]);
}

/* The theme a Get from this page goes into unless the curator picks another:
 * one named after the topic (the owner's ruling, 2026-10-02). Wikidata's name
 * first, then the one the facets recorded; none when neither is readable, so
 * a QID never becomes a theme's name. */
function defaultName(page, known) {
  if (known.state === "known" && known.label && known.label !== page.qid) return known.label;
  if (page.label && page.label !== page.qid) return page.label;
  return null;
}

function asking(id, title) {
  return el("section", { class: "panel", "aria-labelledby": id }, [
    el("h2", { id, text: title }),
    el("p", { class: "muted", "aria-live": "polite", text: "Asking Wikidata…" }),
  ]);
}

/* *In your library*: your works in circulation in the topic, each opening its page. */
function heldSection(works) {
  return el("section", { class: "panel", "aria-labelledby": "in-your-library" }, [
    el("h2", { id: "in-your-library", text: `In your library (${works.length})` }),
    works.length
      ? el("ul", { class: "grid" }, works.map(heldCard))
      : el("p", { class: "muted", text: "None of your works in circulation is in this topic." }),
  ]);
}

function heldCard(work) {
  const picture = work.image.available
    ? el("img", { src: `/api/works/${encodeURIComponent(work.artwork_id)}/thumbnail`, alt: "", loading: "lazy" })
    : absentImage(work.image.note);
  return el("li", { class: "card", "data-artwork": work.artwork_id }, [
    el("div", { class: "card-image" }, [picture]),
    el("div", { class: "card-body" }, [
      el("h3", { class: "card-title" }, [link({ view: "work", id: work.artwork_id }, { text: work.title, "aria-label": workName(work) })]),
      el("p", { class: "card-meta", text: [work.artist ? work.artist.name : null, work.date_created].filter(Boolean).join(", ") || " " }),
    ]),
  ]);
}

/* *Representative works*: the most renowned first, each with its state as glyph
 * and word, and every one the library does not hold tickable to get.
 *
 * **A period's are headed with its years**, "Works from 1501–1600": a period's
 * works are matched by when they were made and nothing else, so *Las Meninas*
 * is a Dutch Golden Age work here, and the heading claims no more than that
 * (the owner's answer of 2026-10-02). Only when the period is the kind its works
 * were found by, which is the first the registry gives. */
function paintWorks(section, known, view, name, { toggleSlot, barSlot }) {
  const years = known.state === "known" && known.kinds[0] === "period" ? topicYears(known) : null;
  const heading = el("h2", { id: "representative-works", text: years ? `Works from ${years}` : "Representative works" });
  if (view.state !== "known") {
    fill(section, heading, el("p", { class: "note", text: view.note }));
    return;
  }
  if (!view.works.length) {
    fill(section, heading, el("p", { class: "muted", text: "Wikidata lists no works in this topic." }));
    return;
  }
  // No ticks while the works are still arriving: a repaint would lose them.
  if (!view.complete) return paintArriving(section, heading, view);
  // The page's one selection (`core/selecting.js`), its Get named after the topic.
  const selection = selectionMode({ notHeld: { defaultName: name } });
  if (toggleSlot.isConnected) toggleSlot.replaceWith(toolbar({ actions: [selection.toggle] }));
  if (barSlot.isConnected) barSlot.replaceWith(selection.bar);
  const rows = view.works.map((work) =>
    el("tr", {}, [
      el("td", {}, [gettable(work) ? selection.registryBox(work.qid, named(work.title, work.qid)) : null]),
      workCell(work, { by: makers(work) }),
      byCell(makers(work)),
      yearCell(work),
      el("td", {}, [stateOf(work)]),
    ]),
  );
  fill(section,
    heading,
    el("div", { class: "artist-works" }, [el("table", { class: "select-column" }, [
      el("caption", { text: "The most renowned works Wikidata lists in it, by how many Wikipedias cover them, each marked where the library holds it" }),
      el("thead", {}, [listHeadings(["Get", "Work", "By", "Year", "State"])]),
      el("tbody", {}, rows),
    ])]),
  );
}

/* The works as their ranking lands, before Wikidata has said who made them,
 * so the section is never blank for the length of that question. Each with its
 * picture, year and state, and "Still asking" where its makers will be: an
 * empty cell would read as nobody. No tick boxes yet, so nothing ticked is lost
 * when the whole list replaces this one; a Get is offered once it is whole. */
function paintArriving(section, heading, view) {
  const asking = () => [el("span", { class: "muted", text: "Still asking…" })];
  const rows = view.works.map((work) =>
    el("tr", {}, [
      el("td"),
      workCell(work, { by: asking() }),
      byCell(asking()),
      yearCell(work),
      el("td", {}, [stateOf(work)]),
    ]),
  );
  fill(section,
    heading,
    el("p", { class: "muted", "aria-live": "polite", text: "Still asking Wikidata who made them…" }),
    el("div", { class: "artist-works" }, [el("table", { class: "select-column" }, [
      el("caption", { text: "The most renowned works Wikidata lists in it, by how many Wikipedias cover them, each marked where the library holds it" }),
      el("thead", {}, [listHeadings(["Get", "Work", "By", "Year", "State"])]),
      el("tbody", {}, rows),
    ])]),
  );
}

/* Who made it: each named maker opening their page, and "unknown" where
 * Wikidata records that somebody made it and nobody knows who. */
function makers(work) {
  const people = work.creators.map((person) => personLink(person));
  const parts = [];
  people.forEach((link, at) => {
    if (at) parts.push(", ");
    parts.push(link);
  });
  if (work.creator_unknown) parts.push(people.length ? ", and an unknown maker" : "Unknown maker");
  return parts.length ? parts : ["—"];
}

/* A work's mark as the Artist page draws it; and for a work with no picture
 * that is neither held nor wanted, ○ *No image known*, in words rather than a
 * dash, since a Get may still find one at a museum Wikidata has no picture
 * from. */
function stateOf(work) {
  return workState(work, { noImage: "No image known" });
}

/* *Artists*: those whose works in the topic are best known, each opening their page, the
 * library's own where it holds them. */
function paintArtists(section, view) {
  const heading = el("h2", { id: "topic-artists", text: "Artists" });
  if (view.state !== "known") {
    fill(section, heading, el("p", { class: "note", text: view.note }));
    return;
  }
  fill(section,
    heading,
    view.artists.length
      ? el("ul", { class: "results-list" }, view.artists.map((person) =>
          el("li", {}, [
            personLink(person),
            lifeDates(person) ? el("span", { class: "muted", text: ` ${lifeDates(person)}` }) : null,
            el("span", { class: "muted", text: ` · ${counted(person.images, "work")} with an image` }),
            stateMark({ held: Boolean(person.artist_id) }),
          ]),
        ))
      : el("p", { class: "muted", text: "Wikidata lists no artists for this topic." }),
  );
}
