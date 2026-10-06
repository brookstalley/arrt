/* The persistent search affordance.
 *
 * `information-architecture.md` § Navigation Structure keeps search in the top
 * bar on every page, as the *arr apps do, and for this product's own reason: at
 * thousands of works it is the primary way in, and a search you must first
 * navigate to is one more step on the most frequent action.
 *
 * Searching is a **navigation**, not a mode. It writes `?q=` into the fragment
 * and goes to the Search results page, which means a search is bookmarkable,
 * sendable, and — because it lands in the history like every other navigation —
 * undone by the browser's own back button rather than by a Clear control the
 * curator has to find.
 */

import { api } from "./api.js";
import { named, topicKinds, topicName, workState } from "./registry.js";
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
 * meant; more is what Enter, which opens every match on the results page, is for. */
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

/* How many of the library's topics the dropdown offers, matched by name, and
 * how many of Wikidata's. Library › Topics lists them all. */
const TOPICS_SHOWN = 3;

/* Fewer letters than this and the registry is not asked: the server's own floor,
 * repeated here only so the dropdown does not send a request the server would
 * answer with `too_short`. */
const REGISTRY_SHORTEST = 3;

/* Whether the words are long enough for Wikidata to be asked: letters and
 * digits counted, as the server counts them. */
export function asksWikidata(query) {
  return (query.match(/[\p{L}\p{N}]/gu) || []).length >= REGISTRY_SHORTEST;
}

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
 * **Enter with nothing highlighted opens the Search results page** for the
 * query (the owner, 2026-10-06). Not the first match, as Sonarr does, because an
 * artist or a movement matches many works where a series title matches one; and
 * no longer Artworks filtered to the query, as ruled on 2026-09-30, because
 * Artworks lists only what is held, so a search for a work not held found
 * nothing there and offered no way on.
 *
 * **Held, then Not held**, as the results page groups them. Held is the
 * library's artists, works, topics and themes, and any of Wikidata's matches the
 * library holds that its own rows do not show; Not held is the rest of
 * Wikidata's (ruling 2, one world). Wikidata's rows arrive after the library's,
 * which never wait for them, and the artists and works never wait for the
 * topics either, each search painting when it answers, with *Asking Wikidata…*
 * below while either is out; and their arrival is announced, not focused, so a
 * curator arrowing through the list is not moved. A half with nothing in it is
 * one line, not a heading over every kind it lacks.
 *
 * An ARIA combobox: the input keeps focus, arrow keys move
 * `aria-activedescendant` through the options, Escape closes the list. A listbox
 * cannot nest groups, so each group's name carries its half ("Held: artists",
 * "Not held: works") and the half's own heading is drawn for the eye only. */
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

  // `half` goes into the group's name, hidden from the eye, which reads it from
  // the half's heading above; the label is styled in capitals, so its own
  // word is written as the name reads.
  const group = (id, label, entries, half = null) =>
    el("li", { role: "presentation" }, [
      el("ul", { role: "group", "aria-labelledby": id }, [
        el("li", { id, role: "presentation", class: "search-suggestions-label" }, [
          half ? el("span", { class: "visually-hidden", text: `${half}: ` }) : null,
          label,
        ]),
        ...entries.map((entry) => entry.node),
      ]),
    ]);
  // A half's heading. Hidden from assistive technology: every group under it
  // already says its half in its name, and a heading inside a listbox is not a
  // thing a screen reader can land on.
  const heading = (text) =>
    el("li", { role: "presentation", "aria-hidden": "true", class: "search-suggestions-half", text });
  // A half with nothing in it, said once. Read, unlike the heading: it is the
  // only thing that says the half was looked in.
  const none = (text) => el("li", { role: "presentation", class: "search-suggestions-none", text });

  // `wikidata` is null when Wikidata is not asked, else its two answers so far:
  // `found`, the artists and works, and `named`, the topics, each null until it
  // arrives. `ourTopicIds` is every topic the library's works are in, matched by
  // name or not, so one of Wikidata's that is among them reads as held.
  const paint = (query, works, artists, topics, ourTopicIds, themes, wikidata, failed, { keepHighlight = false } = {}) => {
    // Kept only across the repaints the registry's answers cause, so a curator who
    // has arrowed to a row stays on it. A new query starts with nothing
    // highlighted: row ids are positions, and a highlight carried to a new query
    // lands on whatever now sits there, which Enter would then open instead of
    // opening the results page.
    const kept = keepHighlight && active >= 0 ? options[active].node.id : null;
    // Artists first, as the IA ranks objects: an artist's name is most often
    // what is typed, and their page is where the rest of the library is.
    const shownArtists = artists.slice(0, ARTISTS_SHOWN);
    // What the library's rows already show is not offered again as Wikidata's.
    const shownArtistIds = new Set(shownArtists.map((entry) => entry.artist.artist_id));
    const shownWorkIds = new Set(works.map((work) => work.artwork_id));
    const shownTopics = new Set(topics.map((topic) => topic.qid));
    const found = wikidata && wikidata.found;
    const named = wikidata && wikidata.named;
    const known = found && found.state === "known" ? found : { artists: [], works: [] };
    const foundTopics = (named && named.state === "known" ? named.topics : []).filter((topic) => !shownTopics.has(topic.qid));
    // Wikidata's matches, each in the half its state puts it in.
    const theirHeldArtists = known.artists.filter((person) => person.artist_id && !shownArtistIds.has(person.artist_id));
    const theirArtists = known.artists.filter((person) => !person.artist_id);
    const theirHeldWorks = known.works.filter(
      (work) => work.held_artwork_ids.length && !work.held_artwork_ids.some((id) => shownWorkIds.has(id)),
    );
    const theirWorks = known.works.filter((work) => !work.held_artwork_ids.length);
    const theirHeldTopics = foundTopics.filter((topic) => ourTopicIds.has(topic.qid)).slice(0, TOPICS_SHOWN);
    const theirTopics = foundTopics.filter((topic) => !ourTopicIds.has(topic.qid)).slice(0, TOPICS_SHOWN);

    const registryArtist = (prefix) => (person, at) =>
      option(`${prefix}-${at}`, registryPersonRow(person), () => go("artist", person.artist_id || person.qid));
    const registryWork = (prefix) => (work, at) =>
      option(`${prefix}-${at}`, registryWorkRow(work), () =>
        work.held_artwork_ids.length ? go("work", work.held_artwork_ids[0]) : go("work", work.qid),
      );
    const registryTopic = (prefix) => (topic, at) =>
      option(`${prefix}-${at}`, registryTopicRow(topic), () => go("topic", topic.qid));

    const heldArtists = [
      ...shownArtists.map((entry, at) =>
        option(`suggestion-artist-${at}`, `${entry.artist.name} — artist`, () => go("artist", entry.artist.artist_id)),
      ),
      ...theirHeldArtists.map(registryArtist("suggestion-held-registry-artist")),
    ];
    const heldWorks = [
      ...works.map((work, at) =>
        option(`suggestion-work-${at}`, work.artist ? `${work.title} — ${work.artist.name}` : work.title, () =>
          go("work", work.artwork_id),
        ),
      ),
      ...theirHeldWorks.map(registryWork("suggestion-held-registry-work")),
    ];
    // Topics after works, as `ia-proposal.md` § Search orders the objects.
    const heldTopics = [
      ...topics.map((topic, at) =>
        option(`suggestion-topic-${at}`, `${topicName(topic.label, topic.qid)} — ${topicKinds([topic.kind])}`, () =>
          go("topic", topic.qid),
        ),
      ),
      ...theirHeldTopics.map(registryTopic("suggestion-held-registry-topic")),
    ];
    const heldThemes = themes.map((placement, at) =>
      option(`suggestion-theme-${at}`, `${placement.theme.name} — theme`, () => go("theme", placement.theme.theme_id)),
    );
    const notHeldArtists = theirArtists.map(registryArtist("suggestion-registry-artist"));
    const notHeldWorks = theirWorks.map(registryWork("suggestion-registry-work"));
    const notHeldTopics = theirTopics.map(registryTopic("suggestion-registry-topic"));
    // Ask, with the words filled in and nothing started: asking for something
    // in words is a paid search, started only from its own page beside its price.
    const ask = option("suggestion-ask", `Ask about “${query}”`, () => go("discover", null, { term: query }));
    // The dropdown's last row: every match on a page of its own, as Enter is.
    const everything = option("suggestion-all-results", `All results for “${query}”`, () => go("search", null, { ...openedFrom("search"), q: query }));
    options = [
      ...heldArtists,
      ...heldWorks,
      ...heldTopics,
      ...heldThemes,
      ...notHeldArtists,
      ...notHeldWorks,
      ...notHeldTopics,
      ask,
      everything,
    ];

    const heldGroups = [
      ...(heldArtists.length ? [group("suggestions-held-artists", "artists", heldArtists, "Held")] : []),
      ...(heldWorks.length ? [group("suggestions-held-works", "works", heldWorks, "Held")] : []),
      ...(heldTopics.length ? [group("suggestions-held-topics", "topics", heldTopics, "Held")] : []),
      ...(heldThemes.length ? [group("suggestions-held-themes", "themes", heldThemes, "Held")] : []),
    ];
    const notHeldGroups = [
      ...(notHeldArtists.length ? [group("suggestions-registry-artists", "artists", notHeldArtists, "Not held")] : []),
      ...(notHeldWorks.length ? [group("suggestions-registry-works", "works", notHeldWorks, "Not held")] : []),
      ...(notHeldTopics.length ? [group("suggestions-registry-topics", "topics", notHeldTopics, "Not held")] : []),
    ];
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
    const nothingHeld = !failed && !heldGroups.length ? [none("Nothing you hold matches.")] : [];
    // Wikidata off or down is said, once, where its rows would be: a library
    // that matched nothing must not read as everything having been searched.
    // One note however many of Wikidata's searches could not be made: the
    // search's own when it has one, else the topic search's.
    const unsaid = (found && found.note) || (named && named.note) || null;
    const registryNote = unsaid
      ? [el("li", { role: "presentation", class: "search-suggestions-registry-note", text: unsaid })]
      : [];
    // Said while either of Wikidata's searches is out, so rows still to come are
    // not read as all there is. Presentation, not an option: nothing to choose,
    // and arrow keys pass over it.
    const waiting = wikidata && (!found || !named);
    const asking = waiting
      ? [el("li", { role: "presentation", class: "search-suggestions-pending", text: "Asking Wikidata…" })]
      : [];
    const nothingMore = wikidata && !waiting && !unsaid && !notHeldGroups.length ? [none("Wikidata has nothing more.")] : [];
    fill(list,
      heading("Held"),
      ...unsearched,
      ...heldGroups,
      ...nothingHeld,
      // Not drawn at all when Wikidata is not asked, below its three letters:
      // there is nothing it could say.
      ...(wikidata ? [heading("Not held"), ...notHeldGroups, ...registryNote, ...asking, ...nothingMore] : []),
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
    let topics = [];
    let ourTopicIds = new Set();
    let failed = false;
    // Asked now and drawn after the library's rows: see above.
    // The topic search beside it, each painted when it arrives: the topic search
    // can take seconds where the other takes under one, and joined, the faster
    // answer waited for the slower with nothing on screen saying so.
    const fromRegistry =
      asksWikidata(query)
        ? {
            found: api(`/api/registry/search?q=${encodeURIComponent(query)}&prefix=true`).catch(() => ({
              state: "unavailable",
              note: "Wikidata could not be searched just now.",
            })),
            named: api(`/api/registry/topics?q=${encodeURIComponent(query)}`).catch(() => ({
              state: "unavailable",
              note: "Wikidata's topics could not be searched just now.",
              topics: [],
            })),
          }
        : null;
    // Settled separately: the artist and theme lookups are extras, and their
    // failure must not cost the work matches. Only the works lookup failing says
    // the library could not be searched, because that one guards a paid search
    // below it.
    const [page, people, placed, held] = await Promise.allSettled([
      api(`/api/works?q=${encodeURIComponent(query)}&limit=${SUGGESTIONS}`),
      api(`/api/artists?q=${encodeURIComponent(query)}`),
      api("/api/themes"),
      api("/api/topics"),
    ]);
    if (people.status === "fulfilled") artists = people.value.artists;
    if (placed.status === "fulfilled") {
      const wanted = fold(query);
      themes = placed.value.themes.filter((placement) => fold(placement.theme.name).includes(wanted)).slice(0, THEMES_SHOWN);
    }
    if (held.status === "fulfilled") {
      const wanted = fold(query);
      const every = held.value.kinds.flatMap((group) => group.topics.map((topic) => ({ ...topic, kind: group.kind })));
      topics = every.filter((topic) => fold(topic.label).includes(wanted)).slice(0, TOPICS_SHOWN);
      ourTopicIds = new Set(every.map((topic) => topic.qid));
    }
    // The dropdown is a shortcut; the results page still opens on Enter. So a
    // failed lookup costs the matches, says so, and keeps the other row.
    if (page.status === "fulfilled") works = page.value.works;
    else failed = true;
    // A slower answer to an earlier keystroke must not replace a later one.
    if (ticket !== asked || document.activeElement !== field) return;
    let wikidata = fromRegistry ? { found: null, named: null } : null;
    paint(query, works, artists, topics, ourTopicIds, themes, wikidata, failed);
    if (!fromRegistry) return;
    // Each answer repaints on its own arrival, under the same two checks as the
    // library's rows; both are drawn after them, since these handlers are
    // attached only now.
    const arrive = (part) => (answer) => {
      if (ticket !== asked || document.activeElement !== field) return;
      wikidata = { ...wikidata, [part]: answer };
      paint(query, works, artists, topics, ourTopicIds, themes, wikidata, failed, { keepHighlight: true });
      if (wikidata.found && wikidata.named) announce(wikidata);
    };
    fromRegistry.found.then(arrive("found"));
    fromRegistry.named.then(arrive("named"));
  };

  // Announced once, when both of Wikidata's searches have answered, with what
  // they found between them. Once rather than once per arrival: two polite
  // updates close together can cut the first off before it is read, and a
  // second count leaves the listener to work out whether it is a total or more.
  // *Asking Wikidata…* on screen is what says the rest is coming.
  const announce = ({ found, named }) => {
    const topicsFound = named.state === "known" ? Math.min(named.topics.length, TOPICS_SHOWN) : 0;
    const count = (found.state === "known" ? found.artists.length + found.works.length : 0) + topicsFound;
    arrived.textContent = found.state === "known" ? `Wikidata: ${count} ${count === 1 ? "match" : "matches"}.` : found.note || "";
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
    // The results page, held and not held, returning to the page the search
    // was made from. Artworks' filters do not follow it: that page lists only
    // what is held, and the results page has no rails to carry them.
    go("search", null, { ...openedFrom("search"), q: query });
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

/* A registry artist as a row: the name and the years that tell two apart. No
 * mark: the group it is in, Held or Not held, already says, as the library's
 * own artist rows beside it never carried one. */
function registryPersonRow(person) {
  const years = person.born || person.died ? ` (${person.born || "?"}–${person.died || ""})` : "";
  return [`${named(person.name, person.qid)}${years} — artist`];
}

/* A registry topic as a row: its name, its kinds, and Wikidata's description,
 * which is what tells six *Impressionism*s apart. */
function registryTopicRow(topic) {
  return [
    `${topicName(topic.label, topic.qid)} — ${topicKinds(topic.kinds)}`,
    topic.description ? el("span", { class: "muted", text: ` · ${topic.description}` }) : null,
  ];
}

/* A registry work as a row: title, maker, and its state as every badge here
 * carries one, glyph and word and colour (`accessibility-spec.md`). */
function registryWorkRow(work) {
  const maker = work.creator ? ` — ${named(work.creator.name, work.creator.qid)}` : "";
  return [`${named(work.title, work.qid)}${maker}`, workState(work, { opens: false, grouped: true })];
}
