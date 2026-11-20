/* Status — the observations the panel states: what needs attention, each
 * wall's state and last report, each Player's state and its outputs', the
 * failed fetches, the image sources, the Watches, the kept pictures and the
 * backup.
 *
 * **One health model** (audit 2026-11-19, audit-5 F4 and audit-6 3): a wall's
 * state is its display state and a Player's its Player state, as the server
 * states them on `GET /api/health` and as Walls and Players draw them, in the
 * contract's words (`core/states.js`). "Needs attention" is the server's
 * `troubles`, the list the top bar and the System badge are made of; nothing on
 * this page judges a reading again, and a setup step (a wall no Player shows, a
 * Player with no token or no report yet) is drawn as a step, never a fault.
 *
 * **It holds no spend record.** `information-architecture.md` said it did, and
 * `services/health.py` deliberately leaves spend off this reading; a Get's cost
 * is on its own page, and the month's spend is the sidebar's (audit
 * 2026-11-19, F12).
 *
 * **Status, under System**, where every *arr app keeps its health checks
 * (`information-architecture.md` § The *arr layout). The top-bar indicator and
 * the System badge in `core/status.js` summarise it on every page and open it.
 * Its address is still `#health`, from before the rename, so a failure's link
 * and a curator's bookmark keep working.
 *
 * **Its words are the household's** (§ Vocabulary): a Player reports for a
 * wall. The server's own sentences, which name the file they read, "the display
 * plane" and the heartbeat, are debug's (ruling 1 of 2026-10-11).
 *
 * **One report panel per wall.** The reading became one per wall because a
 * single observation for an installation with two rooms cannot name the room
 * that went quiet. One wall is the degenerate case of many here as everywhere
 * else on this surface: with one wall this is one panel and reads exactly as the
 * single-wall screen did, and there is no layout for a second display to
 * replace.
 */

import { number } from "../core/counting.js";
import { api } from "../core/api.js";
import { facts } from "../core/badges.js";
import { ago, dated } from "../core/dates.js";
import { GLYPHS } from "../core/glyphs.js";
import { outputCell, screenName } from "../core/outputs.js";
import { museumName, PLUGIN_STATE_WORDS } from "../core/providers.js";
import { el, render } from "../core/render.js";
import { clientLink, wallLink } from "../core/places.js";
import { backRow, link } from "../core/router.js";
import { DEBUG } from "../core/debug.js";
import { displayStateGlyph, displayStateWord, isDisplaySetup, playerStateGlyph, playerStateWord } from "../core/states.js";
import { stepWords } from "../core/status.js";

/* The raw fields behind a panel, closed: what an operator compares against a
 * file or a log, kept off the face of a page a curator reads. Every raw key and
 * machine timestamp on Status is inside one of these, and only there
 * (`tests/browser/test_no_machine_dates.py`). */
function details(...children) {
  const inside = children.filter(Boolean);
  // Only in debug (ruling 1 of 2026-10-11): the page a curator reads ends at
  // what each reading means.
  if (!DEBUG || !inside.length) return null;
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

/* What the wall's Player says about its last error, in words, outside debug.
 * The failure row `observability-strategy.md` gives this page a reader for, and
 * a required field of the heartbeat's schema
 * (`contract/schemas/heartbeat.v1.schema.json`), so naming it here invents no
 * contract. What the screen is doing is the wall's display state, which the
 * server reads (`display_state`), never the superseded `television_reachable`,
 * `television_showing_art` and `has_label_surface`: those say less, and can
 * disagree with it (audit 2026-11-19, audit-5 F4: "Showing art" over a screen
 * that is off). A label panel is an output of its Player, said under Players
 * below with each of the Player's outputs. Everything else the Player reported
 * stays in debug's Details. */
function failureFacts(reported) {
  if (!reported) return [];
  return [["Last error", typeof reported.last_error === "string" && reported.last_error ? reported.last_error : null]];
}

/* The work a wall's display state names, as its title linking to its page, or
 * why it cannot be named. `showing` is `{ id, title }` from `showingTitles`. */
function showingLine(showing) {
  if (!showing) return null;
  if (showing.title) return link({ view: "work", id: showing.id }, { class: "link", text: showing.title });
  return "A work the library could not answer for.";
}

/* The work the wall's display state names: on screen while it shows art, and
 * for a wall that has stopped reporting, the one its last report named. Null
 * where it names none. */
function shownWorkId(shown) {
  if (!shown) return null;
  const said = shown.state === "silent" ? shown.last : shown;
  if (!said || said.state !== "showing_art") return null;
  return typeof said.work_id === "string" && said.work_id ? said.work_id : null;
}

/* Each wall's work, read once per id: the display state names it by id, and a
 * curator reads it by title. A work that cannot be read is said to be one
 * rather than shown as its id. */
async function showingTitles(walls) {
  const ids = [...new Set(walls.map((wall) => shownWorkId(wall.display_state)).filter(Boolean))];
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

/* The wall's display state in a glyph and a word (`core/states.js`, the
 * contract's), as Walls' badge says it. A setup step is drawn as one, with no
 * fault's colour or class. */
function wallStateLine(shown) {
  const stateName = shown ? shown.state : "unreachable";
  return el("p", { class: `wall-state${isDisplaySetup(stateName) ? " setup" : ""}`, "data-state": stateName }, [
    el("span", { class: "glyph", text: displayStateGlyph(stateName), "aria-hidden": true }),
    ` ${displayStateWord(stateName)}`,
  ]);
}

/* What the wall's state means for its report, in a sentence, where the state's
 * word alone does not say it: a wall no Player shows has no report to read, and
 * a wall a Player shows that has never readably reported is waiting on it. */
function stateSentence(shown, reading) {
  if (shown && shown.state === "unassigned") {
    return el("p", {
      class: "muted",
      text: "No Player shows this wall yet, so there is no report to read. Its Player is chosen in its Edit…, on Walls.",
    });
  }
  if (reading && reading.absent) return el("p", { class: "muted", text: "No Player has ever reported for this wall." });
  return null;
}

function heartbeatPanel(wall, titles) {
  // The wall's name opens it on Walls: this panel is what its Player says, and
  // the wall itself is a page away.
  const name = wall.wall_name ? wallLink(wall.wall_id, wall.wall_name) : "An unnamed wall";
  const reading = wall.heartbeat;
  const shown = wall.display_state || null;
  if (!reading && !shown) {
    return el("div", { class: "panel wall-reading" }, [
      el("h2", {}, [name]),
      el("p", { class: "note", text: "This status reading says nothing about this wall." }),
    ]);
  }
  const workId = shownWorkId(shown);
  const unassigned = Boolean(shown && shown.state === "unassigned");
  // `wall-reading` as well as `panel`, and the extra class earns its place twice
  // over: `app.css` has a rule keyed on it that nothing was emitting after the
  // client split, and a test asking "is every wall named, and only walls" needs a
  // selector that means *a wall's panel* rather than *any panel on this screen* —
  // the backup, the sources and the picture store are panels too.
  return el("div", { class: "panel wall-reading" }, [
    // The wall's own name is the heading. "The display plane" was right while
    // there was one of it, and is a sentence that silently becomes wrong.
    el("h2", {}, [name]),
    // The server's state for the wall, the same one Walls draws its badge from.
    wallStateLine(shown),
    // An observation with its age, never a verdict. Said once, in the curator's
    // words: the server's own sentence names the file it read, and is debug's
    // (ruling 1). A wall no Player shows says that alone.
    !unassigned && reading && reading.reported_at ? el("p", { class: "reading-sentence", text: `Last heard from ${dated(reading.reported_at)}.` }) : null,
    DEBUG && reading ? el("p", { class: "muted raw-sentence", text: reading.description }) : null,
    stateSentence(shown, reading),
    unassigned
      ? null
      : facts([
          [shown && shown.state === "silent" ? "Last reported showing" : "Showing", showingLine(workId ? { id: workId, title: titles.get(workId) || null } : null)],
          ["Problem", reading ? reading.problem : null],
          ...failureFacts(reading ? reading.reported : null),
        ]),
    reading
      ? details(
          facts([
            ["Heartbeat file", reading.path],
            ["Reported at", reading.reported_at],
            // The exact figure beside the sentence's plain-language one: what an
            // operator compares against the 60-second interval.
            ["Age", reading.age_seconds === null || reading.age_seconds === undefined ? null : `${reading.age_seconds.toFixed(0)} seconds`],
          ]),
          reading.reported ? el("h3", { text: "What it reported" }) : null,
          reportedFacts(reading.reported),
        )
      : null,
  ]);
}

/* Every wall's report, or the fact that the reading did not carry any.
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
  // The server's own step for a household with no wall (`setup_steps`), said as
  // the top bar says it: this panel holds no judgement of its own about it.
  const none = Array.isArray(health.setup_steps) ? health.setup_steps.find((step) => step.about === "no_wall") : null;
  if (none) {
    return [
      el("div", { class: "panel" }, [
        el("h2", { text: "Walls" }),
        el("p", { class: "muted", text: `${stepWords(none)}, so there is no report to read. A wall is added on Walls.` }),
      ]),
    ];
  }
  return health.walls.map((wall) => heartbeatPanel(wall, titles));
}

/* Where a trouble is mended, by what it is about (`TroubleOut.about`): the
 * wall on Walls, the Player on Players, a display two Players claim on
 * Players, a source on Sources, a Watch on Watches, the failed fetches on
 * Queue. The backup has no page of its own: its panel is below. */
function troubleTarget(trouble) {
  if (trouble.about === "wall" && trouble.subject) return { view: "walls", params: { wall: trouble.subject } };
  if (trouble.about === "player" && trouble.subject) return { view: "clients", params: { client: trouble.subject } };
  if (trouble.about === "display_fault") return { view: "clients" };
  if (trouble.about === "source") return { view: "sources" };
  if (trouble.about === "watch") return { view: "watches" };
  if (trouble.about === "failed_fetches") return { view: "queue" };
  return null;
}

/* What needs attention: the server's troubles, the same list the top bar's
 * words and the System badge's count are made of (`core/status.js`), each
 * linking to where it is mended. Nothing here judges a reading again, so the
 * page and the badge cannot count one fault differently. Setup steps are not
 * here: the server lists none among the troubles, and `setupPanel` states them
 * beside it. */
function troublesPanel(health) {
  const heading = el("h2", { text: "Needs attention" });
  if (!Array.isArray(health.troubles)) {
    return el("div", { class: "panel troubles" }, [
      heading,
      el("p", { class: "note", text: "This health reading carries no list of what is wrong. That is a fault in the reading, not in what it reads." }),
    ]);
  }
  if (!health.troubles.length) {
    return el("div", { class: "panel troubles" }, [heading, el("p", { class: "reading-sentence", text: "Nothing needs attention." })]);
  }
  return el("div", { class: "panel troubles" }, [
    heading,
    el(
      "ul",
      { class: "trouble-list" },
      health.troubles.map((trouble) => {
        const target = troubleTarget(trouble);
        const words = trouble.words || "A fault the reading did not word";
        return el("li", { "data-about": trouble.about }, [
          el("span", { class: "glyph", text: GLYPHS.problem, "aria-hidden": true }),
          " ",
          target ? link(target, { class: "link trouble-words", text: words }) : el("span", { class: "trouble-words", text: words }),
        ]);
      }),
    ),
  ]);
}

/* Where a setup step is taken, by what it is about (`SetupStepOut.about`): the
 * household's first wall on Walls, a wall without a Player on its card, a Player
 * without a token or a report on its own page. */
function stepTarget(step) {
  if (step.about === "no_wall") return { view: "walls" };
  return troubleTarget(step);
}

/* What is still to set up: the server's `setup_steps`, the same list the top
 * bar says after the troubles and the System link's name counts, each linking to
 * where it is taken. Steps, never faults: ○ and no fault's colour, and nothing
 * here is counted as a problem. Left out when nothing is left, so a household
 * that is set up reads no panel about it; a reading with no such list says so,
 * as the troubles' does. */
function setupPanel(health) {
  const heading = el("h2", { text: "Still to set up" });
  if (!Array.isArray(health.setup_steps)) {
    return el("div", { class: "panel setup-steps" }, [
      heading,
      el("p", { class: "note", text: "This health reading carries no list of what is left to set up. That is a fault in the reading, not in what it reads." }),
    ]);
  }
  if (!health.setup_steps.length) return null;
  return el("div", { class: "panel setup-steps" }, [
    heading,
    el(
      "ul",
      { class: "setup-step-list" },
      health.setup_steps.map((step) => {
        const target = stepTarget(step);
        const words = stepWords(step);
        return el("li", { "data-about": step.about }, [
          el("span", { class: "glyph", text: GLYPHS.none, "aria-hidden": true }),
          " ",
          target ? link(target, { class: "link step-words", text: words }) : el("span", { class: "step-words", text: words }),
        ]);
      }),
    ),
  ]);
}

/* Every Player, its state and each of its outputs', as the server states them
 * (`players`, `programming/player_state.py`), in the contract's words: a
 * Player with screens, with label panels, with several of either, or with
 * labels only, reads output by output (the owner's ruling 8 of 2026-11-19). A
 * Player's settings and its walls are on Players, which its name opens. */
function playersPanel(health) {
  const heading = el("h2", { text: "Players" });
  if (!Array.isArray(health.players)) {
    return el("div", { class: "panel players-reading" }, [
      heading,
      el("p", { class: "note", text: "This health reading carries no Players. That is a fault in the reading, not in any Player." }),
    ]);
  }
  if (!health.players.length) {
    return el("div", { class: "panel players-reading" }, [heading, el("p", { class: "muted", text: "No Player is recorded. Players are added in Settings › Players." })]);
  }
  return el("div", { class: "panel players-reading" }, [
    heading,
    el(
      "ul",
      { class: "player-readings" },
      health.players.map((player) => {
        const state = player.state ? player.state.state : null;
        const since = player.state ? player.state.since : null;
        const outputs = player.state && Array.isArray(player.state.outputs) ? player.state.outputs : [];
        return el("li", { "data-player": player.client_id, "data-state": state || "" }, [
          el("p", {}, [
            clientLink(player.client_id, player.name),
            el("span", { class: "player-state", text: ` · ${playerStateGlyph(state)} ${playerStateWord(state, since)}` }),
          ]),
          outputs.length
            ? el(
                "ul",
                { class: "player-outputs" },
                outputs.map((output) =>
                  el("li", { "data-kind": output.kind, "data-output": output.name }, [
                    `${output.kind === "label" ? `Label panel ${output.name}` : screenName(output.name)} · ${outputCell(output, player)}`,
                  ]),
                ),
              )
            : null,
        ]);
      }),
    ),
  ]);
}

/* The works the queue could not fetch a picture for: how many, and when the
 * newest failed, in the server's sentence (`failed_fetches.description`), with
 * the way to Queue, where they are retried. Absent when nothing has failed:
 * there is then no observation, and the server sends none. */
function failedFetchesPanel(health) {
  const failed = health.failed_fetches;
  if (!failed) return null;
  return el("div", { class: "panel failed-fetches" }, [
    el("h2", { text: "Failed fetches" }),
    el("p", { class: "reading-sentence", text: failed.description }),
    el("p", {}, [link({ view: "queue" }, { class: "action quiet", text: "Activity › Queue", "aria-label": "Activity › Queue, where the failed fetches are retried" })]),
  ]);
}

/* The sources table's columns, left to right. `drops` is the order they leave
 * as the panel narrows (1 first), and `app.css` holds the widths, under
 * `.source-table`: Source, State, Offered and Chosen never leave. Median long
 * edge goes first because the owner did not name it; Faults since startup goes
 * last, and when it does the count moves into the State cell, so a fault is on
 * screen at every width (owner, 2026-10-08). The class is what the stylesheet
 * and the width test both key on. `num` marks a column of figures, set
 * right-aligned (`app.css`, `.num`). */
const SOURCE_COLUMNS = [
  { name: "source", heading: "Source" },
  { name: "state", heading: "State" },
  { name: "offered", heading: "Offered", num: true },
  { name: "chosen", heading: "Chosen", num: true },
  { name: "only-here", heading: "Only here", drops: 3, num: true },
  { name: "median", heading: "Median long edge", drops: 1, num: true },
  { name: "faults", heading: "Faults since startup", drops: 4, num: true },
  { name: "last-fault", heading: "Last fault", drops: 2 },
];

/* A loaded plugin's faults in words; one that did not load has none to speak
 * of unless it somehow has some. */
function faultWords(source) {
  if (source.faults) return `${source.faults} ${source.faults === 1 ? "fault" : "faults"}`;
  return source.state === "loaded" ? "no faults" : null;
}

function count(value) {
  return typeof value === "number" ? number(value) : "—";
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
    median: yielded && typeof yielded.median_long_edge === "number" ? `${number(yielded.median_long_edge)} px` : "—",
    faults: source.state === "loaded" || source.faults ? String(source.faults) : "—",
    "last-fault":
      source.last_fault && typeof source.last_fault_age_seconds === "number"
        ? `${ago(source.last_fault_age_seconds)}: ${source.last_fault}`
        : "—",
  };
  // `data-label` is the column's name over each cell once a phone stacks the
  // rows into cards (`app.css`); the Source cell leads its card and needs none.
  return el("tr", {}, SOURCE_COLUMNS.map(({ name, heading, num }) => {
    const value = cells[name];
    const label = name === "source" ? {} : { "data-label": heading };
    return el("td", { class: `col-${name}${num ? " num" : ""}`, ...label }, Array.isArray(value) ? value.filter(Boolean) : [String(value)]);
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
                el("thead", {}, [el("tr", {}, SOURCE_COLUMNS.map(({ name, heading, num }) => el("th", { scope: "col", class: `col-${name}${num ? " num" : ""}`, text: heading })))]),
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
    // The server's sentence carries the count's age, so the facts below do not
    // say it a second time (audit 2026-11-19, finding 20: "counted 226 seconds
    // ago" over "Counted 4 minutes ago"). The sentence stays because it also
    // carries what an unreadable store means; its wording is the server's.
    el("p", { class: "reading-sentence", text: pictures.description }),
    facts([
      ["Files", number(pictures.pictures_files)],
      ["Bytes", number(pictures.pictures_bytes)],
      // Only when the disk refused part of the walk: the count is then short,
      // and saying so is what keeps an unreadable store from reading as an empty one.
      ["Could not be read", pictures.unreadable ? `${number(pictures.unreadable)} entries` : null],
    ]),
  ]);
}

/* The Watches a person needs to know about, since they run with nobody watching:
 * the overdue ones by their words, and a spent allowance holding one. Each is on
 * the status indicator too; this is where it opens to, with the way to the page
 * that changes it. A reading without the part says so. */
function watchesPanel(health) {
  const watches = health.watches;
  if (!watches || !Array.isArray(watches.overdue)) {
    return el("div", { class: "panel" }, [
      el("h2", { text: "Watches" }),
      el("p", { class: "note", text: "This health reading carries no Watches. That is a fault in the reading, not in the Watches." }),
    ]);
  }
  const lines = [
    ...watches.overdue.map((words) =>
      el("p", { class: "reading-sentence fault", text: `“${words}” is overdue: it was due and has not been tried. The scheduler may have stopped.` }),
    ),
    watches.allowance_spent
      ? el("p", { class: "reading-sentence", text: "This month's unattended allowance is spent, so the Watches that are on wait for next month." })
      : null,
  ].filter(Boolean);
  return el("div", { class: "panel watches-reading" }, [
    el("h2", { text: "Watches" }),
    ...(lines.length ? lines : [el("p", { class: "reading-sentence", text: "No Watch is overdue or waiting on the allowance." })]),
    el("p", {}, [link({ view: "watches" }, { class: "action quiet", text: "Settings › Watches" })]),
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
    // Only over more than one wall: over one it is the wall's own panel said a
    // second time, a line above it.
    health.description && (health.walls || []).length > 1 ? el("p", { class: "note", text: health.description }) : null,
    // What the top bar and the System badge say, first, each linking to where
    // it is mended; then the readings they were found in.
    troublesPanel(health),
    setupPanel(health),
    ...heartbeatPanels(health, titles),
    playersPanel(health),
    failedFetchesPanel(health),
    sourcesPanel(health, yields),
    watchesPanel(health),
    picturesPanel(health),
    el("div", { class: "panel" }, [
      el("h2", { text: "Backup" }),
      // The server's sentence names the record's file when there is no backup
      // or it cannot be read, which is plumbing (audit 2026-11-19, finding 8):
      // then the sentence is debug's, and the facts and the note below say it
      // in words. A completed backup's sentence names no file and is said.
      health.backup.absent || health.backup.problem
        ? DEBUG
          ? el("p", { class: "muted raw-sentence", text: health.backup.description })
          : null
        : el("p", { class: "reading-sentence", text: health.backup.description }),
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
