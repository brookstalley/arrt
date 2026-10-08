/* Activity — Queue, To review, History and Wanted.
 *
 * Radarr's Activity section (`information-architecture.md` § The *arr layout):
 * Queue is the work in flight and History what has happened. Queue lists the
 * runs that have not ended, split from `GET /api/runs` on the server's own
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
import { agoFrom } from "../core/ages.js";
import { api } from "../core/api.js";
import { paintWanted } from "../core/awaiting.js";
import { table } from "../core/badges.js";
import { counted } from "../core/counting.js";
import { destinationOf, destinationWords, readThemes } from "../core/destination.js";
import { el, fill, guard, render } from "../core/render.js";
import { wantedPicture, wantedWhy } from "../core/reviewing.js";
import { go, link } from "../core/router.js";
import { KIND_WORDS } from "../core/runs.js";
import { state } from "../core/state.js";

/* The runs as rows. A re-search and a Get are runs too. A Get has no intent of
 * its own: the curator chose its works, which is what its row says. *Into* is
 * the theme its accepted works join, named from `themes`, the theme listing. */
function runTable(caption, runs, themes) {
  return table(
    caption,
    ["Asked for", "Kind", "Into", "State", "Started", "Open"],
    runs.map((run) => [
      run.intent || (run.kind === "get" ? "Works you chose" : "—"),
      KIND_WORDS[run.kind] || run.kind,
      destinationWords(destinationOf(run, themes)),
      run.status,
      run.started_at,
      link({ view: "run", id: run.run_id }, { class: "action quiet", text: "Open", "aria-label": `Open the ${KIND_WORDS[run.kind] || "run"} for ${run.intent || (run.kind === "get" ? "the works you chose" : run.run_id)}` }),
    ]),
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
      `${which} among the ${runs.count} most recent of ${runs.total} searches. ` +
      "Older ones are still here and still open at their own address; this list does not page.",
  });
}

/* *To review*: every run holding works that found an image and wait for a
 * verdict, newest first, each opening Review. The one queue under Activity that
 * needs the curator rather than the machine. */
export async function viewToReview(generation) {
  const runs = await api("/api/runs?awaiting=true");
  const panels = [el("h1", { text: "To review" })];
  if (!runs.runs.length) {
    panels.push(
      el("div", { class: "panel empty" }, [
        el("p", {
          text: "Nothing waits for you. When a search or a Get finds images, its works wait here until you accept or reject them.",
        }),
      ]),
    );
  } else {
    panels.push(
      el("div", { class: "panel" }, [
        el("h2", { text: `${counted(runs.awaiting_works, "work")} to review` }),
        table(
          "Every run with works waiting for your verdict, newest first.",
          ["Asked for", "Kind", "To review", "Started", "Open"],
          runs.runs.map((run) => [
            run.intent || (run.kind === "get" ? "Works you chose" : "—"),
            KIND_WORDS[run.kind] || run.kind,
            String(runs.awaiting[run.run_id] || 0),
            run.started_at,
            // A Get is reviewed on its own page; every other run on Review.
            link(
              { view: run.kind === "get" ? "run" : "review", id: run.run_id },
              {
                class: "action quiet",
                text: "Review",
                "aria-label": `Review the ${KIND_WORDS[run.kind] || "run"} for ${run.intent || (run.kind === "get" ? "the works you chose" : run.run_id)}`,
              },
            ),
          ]),
        ),
      ]),
    );
  }
  panels.push(truncation(runs, "Checked"));
  render(generation, ...panels);
}

/* The images being fetched: Radarr's Queue holds downloads, and this is ours.
 *
 * Every work the acquisition queue owes something, in the order it will try
 * them, with the pause first when there is one, since a pause holds every row
 * beneath it. Not counted on Activity's link: that count is To review's, the
 * one queue that needs the curator, and a fetch needs only time. */
function acquisitionPanel(listing, generation) {
  const repaint = () => viewQueue(generation);
  const rows = listing.works.map(({ title, acquisition }) => [
    link({ view: "work", id: acquisition.artwork_id }, { class: "link", text: title }),
    acquisitionBadge(acquisition),
    el("div", { class: "stack-tight" }, [
      el("span", { text: acquisitionSentence(acquisition) }),
      retryButton(acquisition, title, repaint),
    ]),
  ]);
  return el("div", { class: "panel acquisitions" }, [
    el("h2", { text: `Fetching images (${listing.works.length})` }),
    listing.pause
      ? el("p", { class: "note acquisition-pause" }, [
          el("span", { class: "glyph", text: "‖", "aria-hidden": true }),
          ` Every fetch is paused: ${listing.pause.detail} ${listing.pause.remedy || "Nothing anticipated this error; the server's journal has it, as acquisition.queue_error."}`,
        ])
      : null,
    listing.works.length
      ? table("Every accepted work still owed its image or its preparation, in the order the queue will try them.", ["Work", "State", "What happened"], rows)
      : el("p", { class: "muted", text: "Every accepted work holds its image. A work you accept is fetched here, one at a time, then prepared for the wall." }),
  ]);
}

export async function viewQueue(generation) {
  const [runs, themes, acquisitions] = await Promise.all([api("/api/runs"), readThemes(), api("/api/acquisitions")]);
  const active = runs.runs.filter((run) => !run.is_terminal);
  const panels = [el("h1", { text: "Queue" })];
  if (!active.length) {
    // Only as sure as the listing: when the cap left older searches out, one of
    // them may still be working, so the page says what it checked
    // rather than that nothing is in flight. "No search", not "nothing": the
    // fetches below may be.
    const nothing = runs.truncated
      ? `No search is in flight among the ${runs.count} most recent searches.`
      : "No search is in flight.";
    panels.push(
      el("div", { class: "panel empty" }, [
        el("p", {
          text:
            `${nothing} A search you start in Ask, or a Get, shows here while it works.`,
        }),
        link({ view: "discover" }, { class: "action", text: "Go to Ask" }),
      ]),
    );
  } else {
    panels.push(
      el("div", { class: "panel" }, [
        el("h2", { text: `In flight (${active.length})` }),
        runTable("Every search not yet ended, newest first.", active, themes),
      ]),
    );
  }
  panels.push(truncation(runs, "Checked"));
  panels.push(acquisitionPanel(acquisitions, generation));
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
      el("p", {
        class: "muted empty",
        text: offset
          ? "Nothing older than this."
          : group || wallName
            ? "Nothing of this kind has happened yet."
            : "Nothing has happened yet. Gets, verdicts, archives, restores and hangs are recorded here as they happen; nothing from before the history began is.",
      }),
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

/* How long ago, with the readable date and time a hover away and in the
 * element's `datetime`, so the machine instant is never what is read. */
function when(iso) {
  const readable = new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  return el("time", { datetime: iso, title: readable, text: agoFrom(iso) });
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
  const run = (text) => (event.run_id ? link({ view: "run", id: event.run_id }, { class: "link", text }) : text);
  const kindWord = KIND_WORDS[detail.run_kind] || "Get";
  switch (event.kind) {
    case "get.started":
      if (detail.intent) return ["Asked for ", run(`“${detail.intent}”`)];
      return [`Started a ${kindWord}`, detail.works ? ` for ${counted(detail.works, "work")}` : "", ": ", run(`open the ${kindWord}`)];
    case "get.finished":
      return [
        run(`A ${kindWord}`),
        ` ${ENDINGS[detail.status] || detail.status || "ended"}`,
        detail.reason ? `: ${detail.reason}` : "",
      ];
    case "work.accepted":
      return ["Accepted ", work()];
    case "work.rejected":
      return ["Turned down ", detail.title || "a work", event.run_id ? [" from ", run(`its ${kindWord}`)] : ""].flat();
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
 * **Searching is manual and free.** A re-search asks museum and Commons APIs,
 * which cost nothing (`phase2_estimate_usd`); a scheduled re-search waits for
 * Watches. Commons is asked only by Wikidata item, so Search again on a work with
 * no item first offers Wikidata's matches to pick from — the curator's pick, never
 * a match by title (`data-model.md` § Registry identity). Two calls the client
 * makes, the pick then the search, rather than one route that branches. */
export async function viewWanted(generation) {
  const listing = await api("/api/wanted");
  const works = listing.works;
  const picker = el("div", { class: "wanted-picker" });
  const panels = [el("h1", { text: "Wanted" }), picker];
  if (!works.length) {
    panels.push(
      el("div", { class: "panel empty" }, [
        el("p", {
          text:
            "Nothing is wanted. A work you Want on its review card, or whose scan on offer you turn down, waits here " +
            "until you search for it again.",
        }),
      ]),
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
          "Searching again asks the museums and Commons, and spends nothing. Commons is asked only for a work's " +
          "Wikidata item, so a work with none offers Wikidata's matches to pick from first.",
      }),
      el("div", { class: "row" }, [
        el("button", {
          class: "action",
          type: "button",
          text: "Search all",
          "aria-label": `Search again for all ${counted(works.length, "wanted work")}`,
          onclick: (event) => searchAll(event.currentTarget, works, picker),
        }),
        runs.size > 1
          ? el("span", { class: "muted", text: `One re-search for each of the ${runs.size} searches these came from.` })
          : null,
      ]),
      table(
        "Every work you want, newest search first.",
        ["Picture", "Work", "Why", "Wikidata", "From", ""],
        works.map((work) => [
          wantedPicture(work),
          el("span", {}, [el("strong", { text: work.title }), work.artist ? ` — ${work.artist}` : ""]),
          wantedWhy(work),
          work.wikidata_qid
            ? link({ view: "work", id: work.wikidata_qid }, { class: "link", text: work.wikidata_qid })
            : "No item",
          link({ view: "run", id: work.run_id }, { class: "link", text: "The search", "aria-label": `Open the search ${work.title} came from` }),
          el("div", { class: "stack-tight" }, [
            el("button", {
              class: "action quiet",
              type: "button",
              text: "Search again",
              "aria-label": `Search again for ${work.title}`,
              onclick: (event) => (work.wikidata_qid ? searchFor(event.currentTarget, work) : offerItems(picker, work)),
            }),
            el("button", {
              class: "action quiet",
              type: "button",
              text: "Forget",
              "aria-label": `Forget ${work.title}: stop proposing it`,
              onclick: (event) =>
                attempt(
                  event.currentTarget,
                  `forget ${work.title}`,
                  () =>
                    api(`/api/candidates/${encodeURIComponent(work.work_id)}/verdict`, {
                      method: "POST",
                      body: JSON.stringify({ verdict: "rejected", reason: null }),
                    }),
                  {
                    then: async () => {
                      paintWanted();
                      await repaint();
                    },
                  },
                ),
            }),
          ]),
        ]),
      ),
    ]),
  );
  render(generation, ...panels);
}

/* One re-search for this work, then its page. */
function searchFor(control, work) {
  return attempt(
    control,
    `search again for ${work.title}`,
    () => api("/api/runs/resolve", { method: "POST", body: JSON.stringify({ work_ids: [work.work_id] }) }),
    { then: (run) => go("run", run.run_id) },
  );
}

/* A re-search per originating search, since one covers one search's works; then
 * the run's own page when there is one, and Queue when there are several.
 *
 * **A refused search does not stop the rest.** The server refuses works already
 * being re-searched, which is the ordinary state just after *Search again* on
 * one row; stopping there would leave every search after it unstarted, and
 * pressing again would fail the same way. So each is tried, and when any was
 * refused the page stays and says which started and why the others did not. */
function searchAll(control, works, slot) {
  return attempt(control, "search again for these", async () => {
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
      if (started.length === 1) go("run", started[0].run_id);
      else go("queue");
      return;
    }
    fill(
      slot,
      el("div", { class: "panel note search-all-outcome", role: "status" }, [
        el("p", {
          text: started.length
            ? `Started ${counted(started.length, "re-search", "re-searches")}. ${counted(refused.length, "other", "others")} could not start:`
            : "No re-search could start:",
        }),
        el("ul", {}, refused.map((message) => el("li", { text: message }))),
        started.length
          ? link({ view: "queue" }, { class: "action quiet", text: "Open Queue" })
          : null,
      ]),
    );
  });
}

/* Wikidata's items for a work with none, to pick from before searching. */
function offerItems(picker, work) {
  return guard(async () => {
    const found = await api(`/api/candidates/${encodeURIComponent(work.work_id)}/wikidata-matches`);
    const searchWithout = el("button", {
      class: "action quiet",
      type: "button",
      text: found.matches.length ? "None of these — search without an item" : "Search without an item",
      onclick: (event) => searchFor(event.currentTarget, work),
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
                : "Wikidata has no work with this title. Searching without an item still asks the museums."
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
                      if (picked) await searchFor(control, work);
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

