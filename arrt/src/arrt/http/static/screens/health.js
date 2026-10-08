/* Status — the observations the panel states, and the spend record.
 *
 * **Status, under System**, where every *arr app keeps its health checks
 * (`information-architecture.md` § The *arr layout). The top-bar indicator and
 * the System badge in `core/status.js` summarise it on every page and open it.
 * Its address is still `#health`, from before the rename, so a failure's link
 * and a curator's bookmark keep working.
 *
 * **One heartbeat panel per wall.** The reading became one per wall because a
 * single observation for an installation with two rooms cannot name the room
 * that went quiet. One wall is the degenerate case of many here as everywhere
 * else on this surface: with one wall this is one panel and reads exactly as the
 * single-wall screen did, and there is no layout for a second display to
 * replace.
 */

import { api } from "../core/api.js";
import { facts } from "../core/badges.js";
import { ago, dated } from "../core/dates.js";
import { museumName, PLUGIN_STATE_WORDS } from "../core/providers.js";
import { el, render } from "../core/render.js";
import { backRow, link } from "../core/router.js";

/* The raw fields behind a panel, closed: what an operator compares against a
 * file or a log, kept off the face of a page a curator reads. Every raw key and
 * machine timestamp on Status is inside one of these, and only there
 * (`tests/browser/test_no_machine_dates.py`). */
function details(...children) {
  const inside = children.filter(Boolean);
  if (!inside.length) return null;
  return el("details", { class: "raw-details" }, [el("summary", { text: "Details" }), ...inside]);
}

/* The display plane's own report, whatever it chose to put in it.
 *
 * Rendered generically rather than as named rows, and that is the design rather
 * than laziness: `reported_at` is the only key the observability strategy makes
 * contract, and everything else is explicitly the writer's to shape. Naming TV
 * connectivity and panel state here would invent a second contract that plane
 * never agreed to — and a writer that spelled one differently would drop off the
 * panel in silence, which is the failure the one named key exists to prevent.
 *
 * So whatever arrives is shown. That is what gives the failure table's TV, panel
 * and last-error rows a reader at all. */
function reportedFacts(reported) {
  if (!reported) return null;
  const pairs = Object.entries(reported).map(([key, value]) => [
    key,
    // Objects and arrays would reach `facts` as "[object Object]", which is a
    // field displayed and unreadable — worse than one omitted, because it looks
    // like the panel is working.
    value !== null && typeof value === "object" ? JSON.stringify(value) : value,
  ]);
  return pairs.length ? facts(pairs) : null;
}

/* The work a wall's heartbeat names, as its title linking to its page, or why
 * it cannot be named. `showing` is `{ id, title }` from `showingTitles`. */
function showingLine(showing) {
  if (!showing) return null;
  if (showing.title) return link({ view: "work", id: showing.id }, { class: "link", text: showing.title });
  return "A work the library could not answer for; its id is under Details.";
}

/* Each wall's current work, read once per id: the heartbeat names it by id,
 * and a curator reads it by title. A work that cannot be read is said to be one
 * rather than shown as its id. */
async function showingTitles(walls) {
  const ids = [...new Set(walls.map((wall) => wall.heartbeat && wall.heartbeat.reported && wall.heartbeat.reported.current_work_id).filter((id) => typeof id === "string" && id))];
  const answers = await Promise.all(
    ids.map(async (id) => {
      try {
        return [id, (await api(`/api/works/${encodeURIComponent(id)}`)).work.title];
      } catch {
        return [id, null];
      }
    }),
  );
  return new Map(answers);
}

function heartbeatPanel(wall, titles) {
  const name = wall.wall_name || "An unnamed wall";
  const reading = wall.heartbeat;
  if (!reading) {
    return el("div", { class: "panel wall-reading" }, [
      el("h2", { text: name }),
      el("p", { class: "note", text: "The health reading carries no heartbeat for this wall." }),
    ]);
  }
  // `wall-reading` as well as `panel`, and the extra class earns its place twice
  // over: `app.css` has a rule keyed on it that nothing was emitting after the
  // client split, and a test asking "is every wall named, and only walls" needs a
  // selector that means *a wall's panel* rather than *any panel on this screen* —
  // the backup, the sources and the picture store are panels too.
  return el("div", { class: "panel wall-reading" }, [
    // The wall's own name is the heading. "The display plane" was right while
    // there was one of it, and is a sentence that silently becomes wrong.
    el("h2", { text: name }),
    // An observation with its age, never a verdict. A green dot computed from
    // a file that may simply be young is how a health surface starts lying.
    el("p", { class: "reading-sentence", text: reading.description }),
    facts([
      ["Showing", showingLine(showingOf(reading, titles))],
      ["Last reported", reading.reported_at ? dated(reading.reported_at) : null],
      ["Problem", reading.problem],
    ]),
    reading.absent
      ? el("p", {
          class: "muted",
          // States what absent *means*, not why it is absent. "The display
          // plane has not been built yet" would have been true the day this
          // was written and wrong the day that plane ships, with nothing to
          // catch it — a page asserting a fact about the project rather than
          // reporting one about the file in front of it.
          // "for this wall", not "here". Both chunks in this wave reworded this
          // sentence and the per-wall one is the survivor: with a panel per room
          // "here" has several possible referents and names none of them, which
          // is the exact ambiguity splitting the heartbeat per wall removed.
          text: "Nothing has ever written a heartbeat for this wall. Where no display is pointed at it, that is the correct reading rather than a fault.",
        })
      : null,
    details(
      facts([
        ["Heartbeat file", reading.path],
        ["Reported at", reading.reported_at],
        // The exact figure beside the sentence's plain-language one: what an
        // operator compares against the 60-second interval.
        ["Age", reading.age_seconds === null || reading.age_seconds === undefined ? null : `${reading.age_seconds.toFixed(0)} seconds`],
      ]),
      reading.reported ? el("h3", { text: "What it reported" }) : null,
      reportedFacts(reading.reported),
    ),
  ]);
}

function showingOf(reading, titles) {
  const id = reading.reported && reading.reported.current_work_id;
  if (typeof id !== "string" || !id) return null;
  return { id, title: titles.get(id) || null };
}

/* Every wall's heartbeat, or the fact that the reading did not carry any.
 *
 * **The unreadable case is stated rather than thrown**, and that is the same
 * discipline the rest of this screen follows. This is the product's only
 * alerting surface: a payload it cannot read must produce a fact a curator can
 * act on, not an exception that reaches the error banner reading like the server
 * is down. The two lead to different next moves, and only one of them is true. */
function heartbeatPanels(health, titles) {
  if (!Array.isArray(health.walls)) {
    return [
      el("div", { class: "panel" }, [
        el("h2", { text: "Walls" }),
        el("p", {
          class: "note",
          text: "This health reading carries no walls, so nothing can be said about what is showing them. That is a fault in the reading rather than in any wall.",
        }),
      ]),
    ];
  }
  if (health.walls.length === 0) {
    return [
      el("div", { class: "panel" }, [
        el("h2", { text: "Walls" }),
        el("p", { class: "note", text: "No wall is recorded, so there is no heartbeat to read." }),
      ]),
    ];
  }
  return health.walls.map((wall) => heartbeatPanel(wall, titles));
}

/* The sources table's columns, left to right. `drops` is the order they leave
 * as the panel narrows (1 first), and `app.css` holds the widths, under
 * `.source-table`: Source, State, Offered and Chosen never leave. Median long
 * edge goes first because the owner did not name it; Faults since startup goes
 * last, and when it does the count moves into the State cell, so a fault is on
 * screen at every width (owner, 2026-10-08). The class is what the stylesheet
 * and the width test both key on. */
const SOURCE_COLUMNS = [
  { name: "source", heading: "Source" },
  { name: "state", heading: "State" },
  { name: "offered", heading: "Offered" },
  { name: "chosen", heading: "Chosen" },
  { name: "only-here", heading: "Only here", drops: 3 },
  { name: "median", heading: "Median long edge", drops: 1 },
  { name: "faults", heading: "Faults since startup", drops: 4 },
  { name: "last-fault", heading: "Last fault", drops: 2 },
];

/* A loaded plugin's faults in words; one that did not load has none to speak
 * of unless it somehow has some. */
function faultWords(source) {
  if (source.faults) return `${source.faults} ${source.faults === 1 ? "fault" : "faults"}`;
  return source.state === "loaded" ? "no faults" : null;
}

function count(value) {
  return typeof value === "number" ? value.toLocaleString() : "—";
}

function sourceRow(source, yielded) {
  const faults = faultWords(source);
  const cells = {
    // The museum's name, and for a plugin that is not working here, the reason
    // in its own words, which names the setting that would change it.
    source: [
      el("span", { text: museumName(source.name) }),
      source.state !== "loaded" && source.reason ? el("span", { class: "source-reason muted", text: source.reason }) : null,
    ],
    // A word, never a colour. The fault count beside it is shown only once the
    // Faults column has gone (`app.css`), so it is never said twice.
    state: [
      el("span", { text: PLUGIN_STATE_WORDS[source.state] || source.state }),
      faults ? el("span", { class: "state-faults", text: ` · ${faults}` }) : null,
    ],
    offered: count(yielded && yielded.offered),
    chosen: count(yielded && yielded.chosen),
    "only-here": count(yielded && yielded.only_here),
    median: yielded && typeof yielded.median_long_edge === "number" ? `${yielded.median_long_edge.toLocaleString()} px` : "—",
    faults: source.state === "loaded" || source.faults ? String(source.faults) : "—",
    "last-fault":
      source.last_fault && typeof source.last_fault_age_seconds === "number"
        ? `${ago(source.last_fault_age_seconds)}: ${source.last_fault}`
        : "—",
  };
  // `data-label` is the column's name over each cell once a phone stacks the
  // rows into cards (`app.css`); the Source cell leads its card and needs none.
  return el("tr", {}, SOURCE_COLUMNS.map(({ name, heading }) => {
    const value = cells[name];
    const label = name === "source" ? {} : { "data-label": heading };
    return el("td", { class: `col-${name}`, ...label }, Array.isArray(value) ? value.filter(Boolean) : [String(value)]);
  }));
}

/* Every installed source plugin, in order of preference, one row each.
 *
 * Declined is shown as plainly as loaded: a plugin this deployment has not
 * configured is a choice, and its row says which setting would change it. The
 * counts are the library's own records (`GET /api/sources/yields`); a table
 * that could not read them says so and still shows each source's state. */
function sourcesPanel(health, yields) {
  const sources = Array.isArray(health.sources) ? health.sources : null;
  const byName = new Map((yields.rows || []).map((row) => [row.name, row]));
  return el("div", { class: "panel" }, [
    el("h2", { text: "Image sources" }),
    sources === null
      ? el("p", { class: "note", text: "This health reading carries no image sources. That is a fault in the reading, not in any source." })
      : sources.length === 0
        ? el("p", {
            class: "muted",
            text: "No source plugin is installed, so no image can be found for a work. Arrt ships with built-in plugins, so none listed means the package was installed without its entry points.",
          })
        : el("div", { class: "source-table" }, [
            yields.problem ? el("p", { class: "note", text: `The counts could not be read: ${yields.problem}` }) : null,
            el("div", { class: "table-scroll" }, [
              el("table", {}, [
                el("caption", {
                  text: "Most preferred first. Offered: the images a source has offered. Chosen: the works held by an image from it. Only here: those no other source offered an image for.",
                }),
                el("thead", {}, [el("tr", {}, SOURCE_COLUMNS.map(({ name, heading }) => el("th", { scope: "col", class: `col-${name}`, text: heading })))]),
                el("tbody", {}, sources.map((source) => sourceRow(source, byName.get(source.name)))),
              ]),
            ]),
          ]),
  ]);
}

/* The yields, or why they could not be read. Caught here rather than left to
 * `guard`: counts that will not load are a fact about the table, and the rest
 * of Status, the product's only alerting surface, still has to be read. */
async function sourceYields() {
  try {
    const answer = await api("/api/sources/yields");
    return { rows: Array.isArray(answer.sources) ? answer.sources : [], problem: null };
  } catch (failure) {
    return { rows: [], problem: failure.message };
  }
}

/* How much the picture store keeps: every picture fetched from outside, kept for
 * good, with no ceiling (owner, 2026-10-06). Its growth is watched here rather
 * than bounded, so the panel states the count and its age and calls no size too
 * large. A reading without it says so, as the other panels do. */
function picturesPanel(health) {
  const pictures = health.pictures;
  if (!pictures) {
    return el("div", { class: "panel" }, [
      el("h2", { text: "Kept pictures" }),
      el("p", { class: "note", text: "This health reading carries no count of kept pictures. That is a fault in the reading, not in the store." }),
    ]);
  }
  return el("div", { class: "panel pictures-reading" }, [
    el("h2", { text: "Kept pictures" }),
    el("p", { class: "reading-sentence", text: pictures.description }),
    facts([
      ["Files", pictures.pictures_files.toLocaleString()],
      ["Bytes", pictures.pictures_bytes.toLocaleString()],
      ["Counted", ago(pictures.age_seconds)],
      // Only when the disk refused part of the walk: the count is then short,
      // and saying so is what keeps an unreadable store from reading as an empty one.
      ["Could not be read", pictures.unreadable ? `${pictures.unreadable.toLocaleString()} entries` : null],
    ]),
  ]);
}

export async function viewHealth(generation) {
  const [health, yields] = await Promise.all([api("/api/health"), sourceYields()]);
  const titles = await showingTitles(Array.isArray(health.walls) ? health.walls : []);
  render(
    generation,
    backRow(),
    el("h1", { text: "Status" }),
    // The server's own summary of the readings below it. Shown as prose and
    // used for nothing else: it applies no threshold and reaches no verdict, so
    // deriving a state from it here would be inventing a judgement the plane
    // deliberately declined to make.
    health.description ? el("p", { class: "note", text: health.description }) : null,
    ...heartbeatPanels(health, titles),
    sourcesPanel(health, yields),
    picturesPanel(health),
    el("div", { class: "panel" }, [
      el("h2", { text: "Backup" }),
      el("p", { class: "reading-sentence", text: health.backup.description }),
      facts([
        ["Last completed", health.backup.completed_at ? dated(health.backup.completed_at) : null],
        ["Problem", health.backup.problem],
      ]),
      health.backup.absent
        ? el("p", {
            class: "muted",
            // Says what the catalogue is worth and what an absent record means,
            // and deliberately stops there. "The backup job has not been built
            // yet" would be a claim about the project rather than about the file
            // in front of it, and would be wrong the day that job ships with
            // nothing to catch it — the same trap the heartbeat's note avoids.
            text: "No backup has recorded itself here. The catalogue is the irreplaceable asset — the images can all be fetched again — so this is the reading to watch.",
          })
        : null,
      details(
        facts([
          ["Backup record", health.backup.path],
          ["Completed at", health.backup.completed_at],
          ["Age", health.backup.age_seconds === null ? null : `${health.backup.age_seconds.toFixed(0)} seconds`],
        ]),
        health.backup.reported ? el("h3", { text: "What it recorded" }) : null,
        reportedFacts(health.backup.reported),
      ),
    ]),
  );
}
