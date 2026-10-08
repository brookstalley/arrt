/* Activity — Queue, To review, History and Wanted.
 *
 * Radarr's Activity section (`information-architecture.md` § The *arr layout):
 * Queue is the work in flight and History what has happened. Queue lists the
 * Gets that have not ended, split from `GET /api/runs` on the server's own
 * `is_terminal` flag rather than on a list of status names here, because that
 * list is the thing that goes stale: a status added to the enum would otherwise
 * sit in the wrong page with nothing failing to say so.
 *
 * **History is the event log** (`GET /api/history`), not the finished runs: a
 * Get ending is one kind of event among the verdicts, archives, restores and
 * hangs, and a finished run is still opened from its own events.
 *
 * One module for these pages because they are Activity's; a screen module may
 * hold several views, and must never import another screen.
 */

import { acquisitionBadge, acquisitionSentence, retryButton } from "../core/acquiring.js";
import { attempt } from "../core/acting.js";
import { stamp } from "../core/dates.js";
import { api } from "../core/api.js";
import { paintWanted } from "../core/awaiting.js";
import { table } from "../core/badges.js";
import { counted } from "../core/counting.js";
import { destinationOf, destinationWords, readThemes } from "../core/destination.js";
import { GLYPHS } from "../core/glyphs.js";
import { hold, heldFor, showHold } from "../core/holding.js";
import { el, emptyState, fill, guard, render } from "../core/render.js";
import { wantedPicture, wantedWhy } from "../core/reviewing.js";
import { go, link } from "../core/router.js";
import { KIND_WORDS, STATE_WORDS } from "../core/runs.js";
import { tierMark } from "../core/spend.js";
import { state } from "../core/state.js";

/* What a Get is for, as its row and its links name it. A Get of chosen works
 * has no intent of its own: the curator chose its works, which is what it says. */
function askedFor(run) {
  return run.intent || (run.kind === "get" ? "Works you chose" : "Works looked for again");
}

/* The Gets as rows. *Into* is the theme its accepted works join, named from
 * `themes`, the theme listing. */
function runTable(caption, runs, themes) {
  return table(
    caption,
    ["Asked for", "Kind", "Into", "State", "Started", "Open"],
    runs.map((run) => [
      askedFor(run),
      KIND_WORDS[run.kind] || run.kind,
      destinationWords(destinationOf(run, themes)),
      STATE_WORDS[run.status] || run.status,
      el("time", stamp(run.started_at)),
      link({ view: "get", id: run.run_id }, { class: "action quiet row-link", text: "Open", "aria-label": `Open the ${KIND_WORDS[run.kind] || "Get"}: ${askedFor(run)}` }),
    ]),
    { stacked: true },
  );
}


/* What the listing's cap left out, said where it matters.
 *
 * The server caps this listing, newest first, and says so with `truncated` and
 * `total`. A page that split it without saying so would present a silently
 * short list as a complete one — which is how a curator concludes their older
 * searches are gone. There is no paging, so the note must not imply one: an
 * older run is reached at its own address. */
function truncation(runs, which) {
  if (!runs.truncated) return null;
  return el("p", {
    class: "note",
    text:
      `${which} among the ${runs.count} most recent of ${runs.total} Gets. ` +
      "Older ones are still here and still open at their own address; this list does not page.",
  });
}

/* *To review*: every Get holding works that found an image and wait for a
 * verdict, newest first, each opening Review. The one queue under Activity that
 * needs the curator rather than the machine. */
export async function viewToReview(generation) {
  const runs = await api("/api/runs?awaiting=true");
  const panels = [el("h1", { text: "To review" })];
  if (!runs.runs.length) {
    panels.push(
      emptyState("Nothing waits for you.", "When a Get finds images, its works wait here until you accept or reject them."),
    );
  } else {
    panels.push(
      el("div", { class: "panel" }, [
        el("h2", { text: `${counted(runs.awaiting_works, "work")} to review` }),
        table(
          "Every Get with works waiting for your verdict, newest first.",
          ["Asked for", "Kind", "To review", "Started", "Open"],
          runs.runs.map((run) => [
            askedFor(run),
            KIND_WORDS[run.kind] || run.kind,
            String(runs.awaiting[run.run_id] || 0),
            el("time", stamp(run.started_at)),
            // A Get of chosen works is reviewed on its own page; every other Get on Review.
            link(
              { view: run.kind === "get" ? "get" : "review", id: run.run_id },
              {
                class: "action quiet row-link",
                text: "Review",
                "aria-label": `Review the ${KIND_WORDS[run.kind] || "Get"}: ${askedFor(run)}`,
              },
            ),
          ]),
          { stacked: true },
        ),
      ]),
    );
  }
  panels.push(truncation(runs, "Checked"));
  render(generation, ...panels);
}

/* The images being fetched: Radarr's Queue holds downloads, and this is ours.
 *
 * Two lists, because thousands of works failing for one reason are one
 * problem: the works that failed, one row per cause with its count and Retry
 * all, and the works still in line, in the order the queue will try them. The
 * server groups and pages both, so the page never holds more than a page of
 * either. The pause comes first when there is one, since it holds every work
 * in line. Not counted on Activity's link: that count is To review's, the one
 * queue that needs the curator, and a fetch needs only time. */
function acquisitionPanel(listing, causes, opened, generation) {
  const owed = listing.total + listing.failing;
  return el("div", { class: "panel acquisitions" }, [
    el("h2", { text: `Fetching images (${owed})` }),
    retryAllSaid ? el("p", { class: "note retry-all-said", role: "status", text: takeRetryAllSaid() }) : null,
    listing.pause
      ? el("p", { class: "note acquisition-pause" }, [
          el("span", { class: "glyph", text: GLYPHS.paused, "aria-hidden": true }),
          ` Every fetch is paused: ${listing.pause.detail} ${listing.pause.remedy || "Nothing anticipated this error; the server's journal has it, as acquisition.queue_error."}`,
        ])
      : null,
    owed
      ? null
      : el("p", { class: "muted", text: "Every accepted work holds its image. A work you accept is fetched here, one at a time, then prepared for the wall." }),
    listing.failing ? failurePanel(listing, causes, opened, generation) : null,
    listing.total ? inLinePanel(listing, generation) : null,
  ]);
}

/* What Retry all last did, said once on the repaint it caused and then gone. */
let retryAllSaid = null;

function takeRetryAllSaid() {
  const sentence = retryAllSaid;
  retryAllSaid = null;
  return sentence;
}

function retryAllSentence(result) {
  const parts = [result.retried ? `${counted(result.retried, "work")} put back in line.` : "No work was put back in line."];
  for (const each of result.refused) parts.push(`${counted(each.works, "work")} not: ${each.reason}`);
  return parts.join(" ");
}

/* The works that failed, one row per cause. A cause opens into its works at its
 * own address (`#queue?cause=…`), which is navigation and so a link; Retry all
 * is an act and so a button, retrying the whole group in one request. */
function failurePanel(listing, causes, opened, generation) {
  const repaint = () => viewQueue(generation);
  const params = state.params;
  const rows = causes.causes.map((group) => {
    const isOpen = opened && opened.cause === group.cause;
    const split = group.gave_up && group.failed ? ` (${group.failed} failed, ${group.gave_up} gave up)` : "";
    return el("li", { class: "failure-cause" }, [
      el("div", { class: "failure-cause-head" }, [
        el("p", { class: "failure-cause-why" }, [
          el("span", { class: "glyph", text: GLYPHS.problem, "aria-hidden": true }),
          " ",
          el("span", { text: group.cause }),
        ]),
        el("p", { class: "muted failure-cause-count", text: `${counted(group.works, "work")}${split}` }),
        el("div", { class: "row" }, [
          link(
            { view: "queue", params: { ...params, cause: isOpen ? "" : group.cause, cause_offset: "" } },
            {
              class: "action quiet",
              text: isOpen ? "Hide the works" : "Show the works",
              "aria-expanded": isOpen ? "true" : "false",
              "aria-label": `${isOpen ? "Hide" : "Show"} the ${counted(group.works, "work")} that failed: ${group.cause}`,
            },
          ),
          el("button", {
            class: "action",
            type: "button",
            text: "Retry all",
            "aria-label": `Retry all ${counted(group.works, "work")} that failed: ${group.cause}`,
            onclick: (event) =>
              attempt(
                event.currentTarget,
                `retry the ${counted(group.works, "work")} that failed`,
                () => api("/api/acquisitions/causes/retry", { method: "POST", body: JSON.stringify({ cause: group.cause }) }),
                {
                  then: (result) => {
                    retryAllSaid = retryAllSentence(result);
                    return repaint();
                  },
                },
              ),
          }),
        ]),
      ]),
      isOpen ? causeWorks(opened, repaint) : null,
    ]);
  });
  return el("section", { class: "failures", "aria-label": "Failed" }, [
    el("h3", { text: `Failed (${listing.failing})` }),
    el("p", { class: "muted", text: "Grouped by why the last try failed. Retry all puts every work of a group back in line." }),
    el("ul", { class: "failure-causes" }, rows),
    pager(causes, "causes_offset", causes.causes.length, "causes"),
  ]);
}

/* One cause's works, a page at a time, each named by its title and opening its
 * Work page, with its own Retry. The cause is the group's heading, so each
 * row's sentence leaves it out. */
function causeWorks(page, repaint) {
  if (!page.works.length) {
    return el("p", { class: "muted", text: "None of them is waiting for this reason any more: the queue tried them again." });
  }
  const rows = page.works.map(({ title, acquisition }) => [
    link({ view: "work", id: acquisition.artwork_id }, { class: "link", text: title }),
    acquisitionBadge(acquisition),
    el("div", { class: "stack-tight" }, [
      el("span", { text: acquisitionSentence(acquisition, { cause: false }) }),
      retryButton(acquisition, title, repaint),
    ]),
  ]);
  return el("div", { class: "failure-cause-works" }, [
    table(`Failed works: ${page.cause}`, ["Work", "State", "What happened"], rows, { stacked: true }),
    pager(page, "cause_offset", page.works.length, "works"),
  ]);
}

/* The works still in line, a page at a time, in the order the queue will try them. */
function inLinePanel(listing, generation) {
  const repaint = () => viewQueue(generation);
  const rows = listing.works.map(({ title, acquisition }) => [
    link({ view: "work", id: acquisition.artwork_id }, { class: "link", text: title }),
    acquisitionBadge(acquisition),
    el("div", { class: "stack-tight" }, [
      el("span", { text: acquisitionSentence(acquisition) }),
      retryButton(acquisition, title, repaint),
    ]),
  ]);
  return el("section", { class: "in-line", "aria-label": "In line" }, [
    el("h3", { text: `In line (${listing.total})` }),
    table("Every accepted work still owed its image or its preparation, in the order the queue will try them.", ["Work", "State", "What happened"], rows, { stacked: true }),
    pager(listing, "offset", listing.works.length, "works"),
  ]);
}

/* Previous and next pages of one of Queue's lists, as links, so a page is an
 * address; `key` is the parameter that list's offset travels in. */
function pager(page, key, shown, things) {
  const later = page.offset + shown < page.total;
  const earlier = page.offset > 0;
  if (!later && !earlier) return null;
  const at = (offset) => ({ view: "queue", params: { ...state.params, [key]: offset ? String(offset) : "" } });
  return el("div", { class: "row queue-paging" }, [
    earlier ? link(at(Math.max(0, page.offset - page.limit)), { class: "action quiet", text: "Previous", "aria-label": `Previous ${things}` }) : null,
    later ? link(at(page.offset + page.limit), { class: "action quiet", text: "Next", "aria-label": `Next ${things}` }) : null,
    el("span", { class: "muted", text: `${page.offset + 1}–${page.offset + shown} of ${page.total}` }),
  ]);
}

/* A page offset from the address, or the first page. */
function offsetParam(name) {
  return Math.max(0, Number.parseInt(state.params[name] || "0", 10) || 0);
}

/* A listing's address with its offset, leaving the first page's bare. */
function paged(path, offset, extra = {}) {
  const query = new URLSearchParams(extra);
  if (offset) query.set("offset", String(offset));
  const text = query.toString();
  return text ? `${path}?${text}` : path;
}

export async function viewQueue(generation) {
  const cause = state.params.cause || null;
  const [runs, themes, acquisitions, causes, opened] = await Promise.all([
    api("/api/runs"),
    readThemes(),
    api(paged("/api/acquisitions", offsetParam("offset"))),
    api(paged("/api/acquisitions/causes", offsetParam("causes_offset"))),
    cause ? api(paged("/api/acquisitions/causes/works", offsetParam("cause_offset"), { cause })) : null,
  ]);
  const active = runs.runs.filter((run) => !run.is_terminal);
  const panels = [el("h1", { text: "Queue" })];
  if (!active.length) {
    // Only as sure as the listing: when the cap left older Gets out, one of
    // them may still be working, so the page says what it checked
    // rather than that nothing is in flight. "No Get", not "nothing": the
    // fetches below may be.
    const nothing = runs.truncated
      ? `No Get is in flight among the ${runs.count} most recent Gets.`
      : "No Get is in flight.";
    panels.push(
      emptyState(nothing, "A Get you start in Ask, or on works you chose, shows here while it works.", [
        link({ view: "discover" }, { class: "action", text: "Go to Ask" }),
      ]),
    );
  } else {
    panels.push(
      el("div", { class: "panel" }, [
        el("h2", { text: `In flight (${active.length})` }),
        runTable("Every Get not yet ended, newest first.", active, themes),
      ]),
    );
  }
  panels.push(truncation(runs, "Checked"));
  panels.push(acquisitionPanel(acquisitions, causes, opened, generation));
  render(generation, ...panels);
}

/* History: what happened, newest first, from the event log (`GET /api/history`).
 *
 * Every act the log records — a Get starting and ending, a verdict, an archive
 * or a restore, and every hang and *Not this one again* — as one sentence with
 * how long ago it was, the readable date a hover away. Filtered by kind with
 * links, so a filtered history is an address a curator can keep; `?wall=` is one
 * wall's history, which its card on Walls opens.
 *
 * **Every id in an event may no longer resolve**, so the sentence is built from
 * the words the event carries (`detail`), and only where those are missing from
 * the reads that can still answer: the walls listing for a wall's name, and a
 * work's own record for its title. A work the library no longer answers for is
 * said to be one, never left as a bare id. */
export async function viewHistory(generation) {
  const params = state.params;
  const group = HISTORY_GROUPS.find((each) => each.key === (params.kind || "")) || null;
  const offset = Math.max(0, Number.parseInt(params.offset || "0", 10) || 0);
  const query = new URLSearchParams({ limit: String(HISTORY_PAGE), offset: String(offset) });
  for (const kind of group ? group.kinds : []) query.append("kind", kind);
  if (params.wall) query.set("wall_id", params.wall);
  const [page, walls] = await Promise.all([api(`/api/history?${query}`), api("/api/walls")]);
  const wallNames = new Map(walls.walls.map((wall) => [wall.wall_id, wall.name]));
  const titles = await titlesFor(page.events);

  const wallName = params.wall ? wallNames.get(params.wall) || "a wall no longer recorded" : null;
  const panels = [el("h1", { text: wallName ? `History of ${wallName}` : "History" })];
  if (wallName) {
    panels.push(
      el("p", { class: "muted" }, [
        "What was hung on it, and what was kept off from it. ",
        link({ view: "history", params: { kind: params.kind || "" } }, { text: "Every wall's history" }),
      ]),
    );
  }
  panels.push(kindFilter(group, params));
  if (!group && params.kind) {
    panels.push(el("p", { class: "note", text: `The history has no kind called “${params.kind}”, so every kind is shown.` }));
  }
  if (!page.events.length) {
    panels.push(
      offset
        ? emptyState("Nothing older than this.")
        : group || wallName
          ? emptyState("Nothing of this kind has happened yet.")
          : emptyState(
              "Nothing has happened yet.",
              "Gets, verdicts, archives, restores and hangs are recorded here as they happen; nothing from before the history began is.",
            ),
    );
  } else {
    panels.push(
      el(
        "ol",
        { class: "history-events", "aria-label": "What happened, newest first" },
        page.events.map((event) => el("li", { "data-kind": event.kind }, [when(event.occurred_at), el("span", {}, sentence(event, wallNames, titles))])),
      ),
    );
  }
  panels.push(paging(page, params));
  render(generation, ...panels);
}

/* How many events a page shows. The server allows up to 100. */
const HISTORY_PAGE = 50;

/* The kinds, as a curator filters them: the event kinds grouped by what they
 * are about. Each group's `kinds` are `EventKind`'s values, which the server
 * refuses by name if one is misspelled, so a typo here fails loudly. */
const HISTORY_GROUPS = [
  { key: "gets", label: "Gets", kinds: ["get.started", "get.finished"] },
  { key: "verdicts", label: "Verdicts", kinds: ["work.accepted", "work.rejected"] },
  { key: "archive", label: "Archive", kinds: ["work.archived", "work.restored"] },
  { key: "walls", label: "Walls", kinds: ["wall.hung", "work.left_theme", "work.excluded", "work.allowed"] },
];

function kindFilter(group, params) {
  const target = (key) => ({ view: "history", params: { wall: params.wall || "", kind: key } });
  const item = (key, label, current) =>
    el("li", {}, [link(target(key), { class: "link", text: label, "aria-current": current ? "page" : null })]);
  return el("ul", { class: "history-kinds", "aria-label": "Show" }, [
    item("", "Everything", !group),
    ...HISTORY_GROUPS.map((each) => item(each.key, each.label, group === each)),
  ]);
}

/* Newer and older pages, as links, so a page of the history is an address. */
function paging(page, params) {
  const older = page.offset + page.events.length < page.total;
  const newer = page.offset > 0;
  if (!older && !newer) return null;
  const at = (offset) => ({ view: "history", params: { ...params, offset: offset ? String(offset) : "" } });
  return el("div", { class: "row history-paging" }, [
    newer ? link(at(Math.max(0, page.offset - page.limit)), { class: "action quiet", text: "Newer" }) : null,
    older ? link(at(page.offset + page.limit), { class: "action quiet", text: "Older" }) : null,
    el("span", { class: "muted", text: `${page.offset + 1}–${page.offset + page.events.length} of ${page.total}` }),
  ]);
}

/* When it happened, as every date on the surface is written (`core/dates.js`),
 * with the instant in the element's `datetime`. */
function when(iso) {
  return el("time", stamp(iso));
}

/* A title for every event that names a work and carries no title of its own
 * (*Not this one again* and its undo are recorded by the walls, which do not
 * hold works' titles), each work asked for once. */
async function titlesFor(events) {
  const wanted = [...new Set(events.filter((event) => event.artwork_id && !event.detail.title).map((event) => event.artwork_id))];
  const answers = await Promise.all(
    wanted.map(async (id) => {
      try {
        return [id, (await api(`/api/works/${encodeURIComponent(id)}`)).work.title];
      } catch {
        return [id, null];
      }
    }),
  );
  return new Map(answers);
}

/* How a Get ended, in words, by `RunStatus`. A status added there and not here
 * is shown as itself rather than guessed at. */
const ENDINGS = {
  completed: "finished",
  failed: "failed",
  declined: "was declined",
  cancelled: "was cancelled",
  halted_by_budget: "stopped at the spending cap",
  interrupted: "was interrupted",
};

/* One event as a sentence: text, with links to what can still be opened. */
function sentence(event, wallNames, titles) {
  const detail = event.detail || {};
  const title = detail.title || titles.get(event.artwork_id) || "a work no longer in the library";
  const work = () => (event.artwork_id ? link({ view: "work", id: event.artwork_id }, { class: "link", text: title }) : title);
  const wall = detail.wall_name || wallNames.get(event.wall_id) || "a wall no longer recorded";
  const run = (text) => (event.run_id ? link({ view: "get", id: event.run_id }, { class: "link", text }) : text);
  switch (event.kind) {
    case "get.started":
      if (detail.intent) return ["Asked for ", run(`“${detail.intent}”`)];
      return [
        detail.run_kind === "resolve" ? "Started a Get again" : "Started a Get",
        detail.works ? ` for ${counted(detail.works, "work")}` : "",
        ": ",
        run("open the Get"),
      ];
    case "get.finished":
      return [
        run("A Get"),
        ` ${ENDINGS[detail.status] || detail.status || "ended"}`,
        detail.reason ? `: ${detail.reason}` : "",
      ];
    case "work.accepted":
      return ["Accepted ", work()];
    case "work.rejected":
      return ["Turned down ", detail.title || "a work", event.run_id ? [" from ", run("its Get")] : ""].flat();
    case "work.archived":
      return ["Archived ", work()];
    case "work.restored":
      return ["Restored ", work()];
    case "wall.hung":
      if (detail.selection) {
        return [`Hung a selection${typeof detail.works === "number" ? ` of ${counted(detail.works, "work")}` : ""} on ${wall}`];
      }
      return [
        "Hung ",
        event.theme_id ? link({ view: "theme", id: event.theme_id }, { class: "link", text: detail.theme_name || "a theme" }) : detail.theme_name || "a theme",
        ` on ${wall}`,
      ];
    case "work.left_theme":
      return ["Took ", work(), ` out of ${detail.selection ? "the selection" : detail.theme_name || "its theme"} on ${wall}`];
    case "work.excluded":
      return ["Kept ", work(), " off every wall", event.wall_id ? ` (from ${wall})` : ""];
    case "work.allowed":
      return ["Let ", work(), " back on the walls"];
    default:
      return [`Something the history records as ${event.kind}`];
  }
}

/* *Wanted*: the works the curator wants and holds no acceptable scan of.
 *
 * Lidarr's Wanted › Missing, and `ia-proposal.md` § Activity: "Wanted holds works
 * marked Want (no image known, or a Get that found nothing)". One state whether
 * a work never had a scan or had its scan turned down (#168's convergence), so
 * one list, each row saying which.
 *
 * **Getting again is manual and free.** It asks museum and Commons APIs,
 * which cost nothing (`phase2_estimate_usd`), and its tier says so beside the
 * button; a scheduled one waits for Watches. Commons is asked only by Wikidata
 * item, so Get again on a work with no item first offers Wikidata's matches to
 * pick from — the curator's pick, never a match by title (`data-model.md`
 * § Registry identity). Two calls the client makes, the pick then the Get,
 * rather than one route that branches.
 *
 * **Forget is held for Undo**, as a review card's verdict is (`core/holding.js`):
 * it is the same verdict, rejecting the work for good. A row drawn again while
 * its Forget is held — after another row's lands and the page repaints — shows
 * the hold rather than offering Forget a second time. */
export async function viewWanted(generation) {
  const listing = await api("/api/wanted");
  const works = listing.works;
  const picker = el("div", { class: "wanted-picker" });
  const panels = [el("h1", { text: "Wanted" }), picker];
  if (!works.length) {
    panels.push(
      emptyState(
        "Nothing is wanted.",
        // The two controls that put a work here, by the words they carry: a
        // review card's Want, offered where a Get found no scan of the work,
        // and Turn it down on the scan a card offers, under Scans.
        "A work comes here when a Get finds no scan of it and you press Want on its review " +
          "card, or when you turn down the scan its card offers (Scans, then Turn it down). It waits here until " +
          "you get it again.",
        [link({ view: "to_review" }, { class: "action quiet", text: "Open To review" })],
      ),
    );
    render(generation, ...panels);
    return;
  }
  const runs = new Set(works.map((work) => work.run_id));
  const repaint = () => viewWanted(generation);
  panels.push(
    el("div", { class: "panel wanted" }, [
      el("h2", { text: `${counted(works.length, "work")} wanted` }),
      el("p", {
        class: "muted",
        text:
          "Getting again asks the museums and Commons, and spends nothing. Commons is asked only for a work's " +
          "Wikidata item, so a work with none offers Wikidata's matches to pick from first.",
      }),
      el("div", { class: "row" }, [
        el("button", {
          class: "action",
          type: "button",
          text: "Get all again",
          "aria-label": `Get all ${counted(works.length, "wanted work")} again`,
          onclick: (event) => getAll(event.currentTarget, works, picker),
        }),
        tierMark("free"),
        runs.size > 1
          ? el("span", { class: "muted", text: `One Get for each of the ${runs.size} Gets these came from.` })
          : null,
      ]),
      table(
        "Every work you want, newest Get first.",
        ["Picture", "Work", "Why", "Wikidata", "From", ""],
        works.map((work) => wantedRow(work, picker, repaint)),
        // Cards on a phone, as Activity's other tables are. No row link: a
        // row holds several acts, and a link over the card would cover them.
        { stacked: true },
      ),
    ]),
  );
  render(generation, ...panels);
}

/* One wanted work's row. */
function wantedRow(work, picker, repaint) {
  const forget = el("button", {
    class: "action quiet",
    type: "button",
    text: "Forget",
    "aria-label": `Forget ${work.title}: stop proposing it`,
    onclick: (event) =>
      hold({
        key: work.work_id,
        act: "forget",
        title: work.title,
        controls,
        pressed: event.currentTarget,
        write: ({ keepalive }) =>
          api(`/api/candidates/${encodeURIComponent(work.work_id)}/verdict`, {
            method: "POST",
            body: JSON.stringify({ verdict: "rejected", reason: null }),
            keepalive,
          }),
        then: async () => {
          paintWanted();
          await repaint();
        },
      }),
  });
  const controls = el("div", { class: "stack-tight" }, [
    el("button", {
      class: "action quiet",
      type: "button",
      text: "Get again",
      "aria-label": `Get ${work.title} again`,
      onclick: (event) => (work.wikidata_qid ? getAgain(event.currentTarget, work) : offerItems(picker, work)),
    }),
    tierMark("free"),
    forget,
  ]);
  // In a cell of its own, so the hold has a place beside the controls.
  const cell = el("div", {}, [controls]);
  const held = heldFor(work.work_id);
  if (held) showHold(held, controls, forget);
  return [
    wantedPicture(work),
    el("span", {}, [el("strong", { text: work.title }), work.artist ? ` — ${work.artist}` : ""]),
    wantedWhy(work),
    work.wikidata_qid ? link({ view: "work", id: work.wikidata_qid }, { class: "link", text: work.wikidata_qid }) : "No item",
    link({ view: "get", id: work.run_id }, { class: "link", text: "Get", "aria-label": `Open the Get ${work.title} came from` }),
    cell,
  ];
}

/* One Get again for this work, then its page. */
function getAgain(control, work) {
  return attempt(
    control,
    `get ${work.title} again`,
    () => api("/api/runs/resolve", { method: "POST", body: JSON.stringify({ work_ids: [work.work_id] }) }),
    { then: (run) => go("get", run.run_id) },
  );
}

/* A Get again per originating Get, since one covers one Get's works; then the
 * new Get's own page when there is one, and Queue when there are several.
 *
 * **A refused Get does not stop the rest.** The server refuses works a Get is
 * already looking for again, which is the ordinary state just after *Get
 * again* on one row; stopping there would leave every Get after it unstarted,
 * and pressing again would fail the same way. So each is tried, and when any
 * was refused the page stays and says which started and why the others did not. */
function getAll(control, works, slot) {
  return attempt(control, "get these again", async () => {
    const byRun = new Map();
    for (const work of works) byRun.set(work.run_id, [...(byRun.get(work.run_id) || []), work.work_id]);
    const started = [];
    const refused = [];
    for (const workIds of byRun.values()) {
      try {
        started.push(await api("/api/runs/resolve", { method: "POST", body: JSON.stringify({ work_ids: workIds }) }));
      } catch (failure) {
        // A refusal is the server's sentence for the curator; anything else
        // (the network, a fault) is not ours to swallow.
        if (failure.status !== 400) throw failure;
        refused.push(failure.message);
      }
    }
    if (!refused.length) {
      if (started.length === 1) go("get", started[0].run_id);
      else go("queue");
      return;
    }
    fill(
      slot,
      el("div", { class: "panel note search-all-outcome", role: "status" }, [
        el("p", {
          text: started.length
            ? `Started ${counted(started.length, "Get")}. ${counted(refused.length, "other", "others")} could not start:`
            : "No Get could start:",
        }),
        el("ul", {}, refused.map((message) => el("li", { text: message }))),
        started.length
          ? link({ view: "queue" }, { class: "action quiet", text: "Open Queue" })
          : null,
      ]),
    );
  });
}

/* Wikidata's items for a work with none, to pick from before getting it again. */
function offerItems(picker, work) {
  return guard(async () => {
    const found = await api(`/api/candidates/${encodeURIComponent(work.work_id)}/wikidata-matches`);
    const searchWithout = el("button", {
      class: "action quiet",
      type: "button",
      text: found.matches.length ? "None of these — get it without an item" : "Get without an item",
      onclick: (event) => getAgain(event.currentTarget, work),
    });
    fill(
      picker,
      el("div", { class: "panel picker", role: "region", "aria-label": `Wikidata's items for ${work.title}` }, [
        // Focusable, and focused once drawn: the picker opens above the table,
        // away from the button that opened it, and a screen reader would
        // otherwise hear nothing happen.
        el("h2", { class: "picker-heading", tabindex: "-1", text: `Which is ${work.title}?` }),
        el("p", {
          class: "muted",
          text:
            found.state === "known"
              ? found.matches.length
                ? "Wikidata's works with this title, by the same artist first. Pick the one you mean; it becomes the work's item, and Commons is asked by it."
                : "Wikidata has no work with this title. Getting it without an item still asks the museums."
              : found.note,
        }),
        found.matches.length
          ? el(
              "ul",
              { class: "picker-matches" },
              found.matches.map((match) =>
                el("li", {}, [
                  el("button", {
                    class: "action",
                    type: "button",
                    text: "This one",
                    "aria-label": `Pick ${match.qid}, ${match.title}${match.creator ? ` by ${match.creator}` : ""}`,
                    onclick: async (event) => {
                      const control = event.currentTarget;
                      const picked = await attempt(control, `pick ${match.qid} for ${work.title}`, () =>
                        api(`/api/candidates/${encodeURIComponent(work.work_id)}/wikidata-item`, {
                          method: "PUT",
                          body: JSON.stringify({ qid: match.qid }),
                        }),
                      );
                      if (picked) await getAgain(control, work);
                    },
                  }),
                  " ",
                  el("strong", { text: match.title }),
                  match.creator ? ` — ${match.creator}` : " — maker unrecorded",
                  " · ",
                  link({ view: "work", id: match.qid }, { class: "link", text: match.qid }),
                  match.has_image ? " · has a picture" : " · no picture on Wikidata",
                ]),
              ),
            )
          : null,
        el("div", { class: "row" }, [searchWithout]),
      ]),
    );
    picker.querySelector(".picker-heading").focus();
  });
}

