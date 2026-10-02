/* Activity — Queue and History, the searches in flight and the ones that ended.
 *
 * Radarr's Activity section (`information-architecture.md` § The *arr layout):
 * Queue is the work in flight and History what has finished. The two pages
 * split one listing, `GET /api/runs`, on the server's own `is_terminal` flag
 * rather than on a list of status names here, because that list is the thing
 * that goes stale: a status added to the enum would otherwise sit in neither
 * page, or in the wrong one, with nothing failing to say so.
 *
 * **Queue is the runs that have not ended**, which includes one stopped at the
 * approval gate, waiting on the curator. A run that finished with candidates
 * nobody has judged yet is *also* waiting on the curator — Radarr shows the
 * like of it in its Queue — but the listing carries no signal for it, so it
 * lands in History with its state. That signal is a recorded gap
 * (`information-architecture.md` § The *arr layout), not an oversight here.
 *
 * One module for both pages because they are one table over one listing, cut
 * two ways; a screen module may hold several views, and must never import
 * another screen.
 */

import { acquisitionBadge, acquisitionSentence, retryButton } from "../core/acquiring.js";
import { api } from "../core/api.js";
import { paintWanted } from "../core/awaiting.js";
import { table } from "../core/badges.js";
import { counted } from "../core/counting.js";
import { destinationOf, destinationWords, readThemes } from "../core/destination.js";
import { el, fill, guard, render } from "../core/render.js";
import { go } from "../core/router.js";
import { KIND_WORDS } from "../core/runs.js";

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
      el("button", {
        class: "action quiet",
        type: "button",
        text: "Open",
        "aria-label": `Open the ${KIND_WORDS[run.kind] || "run"} for ${run.intent || (run.kind === "get" ? "the works you chose" : run.run_id)}`,
        onclick: () => go("run", run.run_id),
      }),
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
  const panels = [el("h2", { text: "To review" })];
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
        el("h3", { text: `${counted(runs.awaiting_works, "work")} to review` }),
        table(
          "Every run with works waiting for your verdict, newest first.",
          ["Asked for", "Kind", "To review", "Started", "Open"],
          runs.runs.map((run) => [
            run.intent || (run.kind === "get" ? "Works you chose" : "—"),
            KIND_WORDS[run.kind] || run.kind,
            String(runs.awaiting[run.run_id] || 0),
            run.started_at,
            el("button", {
              class: "action quiet",
              type: "button",
              text: "Review",
              "aria-label": `Review the ${KIND_WORDS[run.kind] || "run"} for ${run.intent || (run.kind === "get" ? "the works you chose" : run.run_id)}`,
              // A Get is reviewed on its own page; every other run on Review.
              onclick: () => (run.kind === "get" ? go("run", run.run_id) : go("review", run.run_id)),
            }),
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
    el("button", {
      class: "link",
      type: "button",
      text: title,
      onclick: () => go("work", acquisition.artwork_id),
    }),
    acquisitionBadge(acquisition),
    el("div", { class: "stack-tight" }, [
      el("span", { text: acquisitionSentence(acquisition) }),
      retryButton(acquisition, title, repaint),
    ]),
  ]);
  return el("div", { class: "panel acquisitions" }, [
    el("h3", { text: `Fetching images (${listing.works.length})` }),
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
  const panels = [el("h2", { text: "Queue" })];
  if (!active.length) {
    // Only as sure as the listing: when the cap left older searches out, one of
    // them may still be at the approval gate, so the page says what it checked
    // rather than that nothing is in flight. "No search", not "nothing": the
    // fetches below may be.
    const nothing = runs.truncated
      ? `No search is in flight among the ${runs.count} most recent searches.`
      : "No search is in flight.";
    panels.push(
      el("div", { class: "panel empty" }, [
        el("p", {
          text:
            `${nothing} A search you start in Ask, or a Get, shows here while it works, ` +
            "and while it waits for you to approve its price.",
        }),
        el("button", { class: "action", type: "button", text: "Go to Ask", onclick: () => go("discover") }),
      ]),
    );
  } else {
    panels.push(
      el("div", { class: "panel" }, [
        el("h3", { text: `In flight (${active.length})` }),
        runTable("Every search still working or waiting for approval, newest first.", active, themes),
      ]),
    );
  }
  panels.push(truncation(runs, "Checked"));
  panels.push(acquisitionPanel(acquisitions, generation));
  render(generation, ...panels);
}

export async function viewHistory(generation) {
  const [runs, themes] = await Promise.all([api("/api/runs"), readThemes()]);
  const finished = runs.runs.filter((run) => run.is_terminal);
  const panels = [el("h2", { text: "History" })];
  if (!finished.length) {
    panels.push(el("p", { class: "muted empty", text: "No search has finished yet." }));
  } else {
    panels.push(
      el("div", { class: "panel" }, [
        el("h3", { text: `Finished (${finished.length})` }),
        runTable("Every search that has ended, newest first, with how it ended.", finished, themes),
      ]),
    );
  }
  panels.push(truncation(runs, "The finished ones"));
  render(generation, ...panels);
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
  const panels = [el("h2", { text: "Wanted" }), picker];
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
      el("h3", { text: `${counted(works.length, "work")} wanted` }),
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
          onclick: () => searchAll(works),
        }),
        runs.size > 1
          ? el("span", { class: "muted", text: `One re-search for each of the ${runs.size} searches these came from.` })
          : null,
      ]),
      table(
        "Every work you want, newest search first.",
        ["Work", "Why", "Wikidata", "From", ""],
        works.map((work) => [
          el("span", {}, [el("strong", { text: work.title }), work.artist ? ` — ${work.artist}` : ""]),
          work.scans_turned_down
            ? `${counted(work.scans_turned_down, "scan")} turned down`
            : "No scan found",
          work.wikidata_qid
            ? el("button", { class: "link", type: "button", text: work.wikidata_qid, onclick: () => go("work", work.wikidata_qid) })
            : "No item",
          el("button", { class: "link", type: "button", text: "The search", "aria-label": `Open the search ${work.title} came from`, onclick: () => go("run", work.run_id) }),
          el("div", { class: "stack-tight" }, [
            el("button", {
              class: "action quiet",
              type: "button",
              text: "Search again",
              "aria-label": `Search again for ${work.title}`,
              onclick: () => (work.wikidata_qid ? searchFor([work.work_id]) : offerItems(picker, work)),
            }),
            el("button", {
              class: "action quiet",
              type: "button",
              text: "Forget",
              "aria-label": `Forget ${work.title}: stop proposing it`,
              onclick: () =>
                guard(async () => {
                  await api(`/api/candidates/${encodeURIComponent(work.work_id)}/verdict`, {
                    method: "POST",
                    body: JSON.stringify({ verdict: "rejected", reason: null }),
                  });
                  paintWanted();
                  await repaint();
                }),
            }),
          ]),
        ]),
      ),
    ]),
  );
  render(generation, ...panels);
}

/* One re-search over these works, all from one search, then its page. */
function searchFor(workIds) {
  return guard(async () => {
    const run = await api("/api/runs/resolve", { method: "POST", body: JSON.stringify({ work_ids: workIds }) });
    go("run", run.run_id);
  });
}

/* A re-search per originating search, since one covers one search's works; then
 * the run's own page when there is one, and Queue when there are several. */
function searchAll(works) {
  return guard(async () => {
    const byRun = new Map();
    for (const work of works) byRun.set(work.run_id, [...(byRun.get(work.run_id) || []), work.work_id]);
    const started = [];
    for (const workIds of byRun.values()) {
      started.push(await api("/api/runs/resolve", { method: "POST", body: JSON.stringify({ work_ids: workIds }) }));
    }
    if (started.length === 1) go("run", started[0].run_id);
    else go("queue");
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
      onclick: () => searchFor([work.work_id]),
    });
    fill(
      picker,
      el("div", { class: "panel picker", role: "region", "aria-label": `Wikidata's items for ${work.title}` }, [
        // Focusable, and focused once drawn: the picker opens above the table,
        // away from the button that opened it, and a screen reader would
        // otherwise hear nothing happen.
        el("h3", { class: "picker-heading", tabindex: "-1", text: `Which is ${work.title}?` }),
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
                    onclick: () =>
                      guard(async () => {
                        await api(`/api/candidates/${encodeURIComponent(work.work_id)}/wikidata-item`, {
                          method: "PUT",
                          body: JSON.stringify({ qid: match.qid }),
                        });
                        await searchFor([work.work_id]);
                      }),
                  }),
                  " ",
                  el("strong", { text: match.title }),
                  match.creator ? ` — ${match.creator}` : " — maker unrecorded",
                  " · ",
                  el("button", { class: "link", type: "button", text: match.qid, onclick: () => go("work", match.qid) }),
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

