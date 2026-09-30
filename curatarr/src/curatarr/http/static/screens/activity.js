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
 * (`build-plan-arr-navigation.md` Chunk 03), not an oversight here.
 *
 * One module for both pages because they are one table over one listing, cut
 * two ways; a screen module may hold several views, and must never import
 * another screen.
 */

import { api } from "../core/api.js";
import { table } from "../core/badges.js";
import { el, render } from "../core/render.js";
import { go } from "../core/router.js";

/* The runs as rows. A re-search is a run too, and is listed with its parent. */
function runTable(caption, runs) {
  return table(
    caption,
    ["Asked for", "Kind", "State", "Started", "Open"],
    runs.map((run) => [
      run.intent || "—",
      run.kind === "resolve" ? "re-search" : "search",
      run.status,
      run.started_at,
      el("button", {
        class: "action quiet",
        type: "button",
        text: "Open",
        "aria-label": `Open the search for ${run.intent || run.run_id}`,
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

export async function viewQueue(generation) {
  const runs = await api("/api/runs");
  const active = runs.runs.filter((run) => !run.is_terminal);
  const panels = [el("h2", { text: "Queue" })];
  if (!active.length) {
    panels.push(
      el("div", { class: "panel empty" }, [
        el("p", {
          text:
            "Nothing is in flight. A search you start in Add New shows here while it works, " +
            "and while it waits for you to approve its price.",
        }),
        el("button", { class: "action", type: "button", text: "Go to Add New", onclick: () => go("discover") }),
      ]),
    );
  } else {
    panels.push(
      el("div", { class: "panel" }, [
        el("h3", { text: `In flight (${active.length})` }),
        runTable("Every search still working or waiting for approval, newest first.", active),
      ]),
    );
  }
  panels.push(truncation(runs, "Checked"));
  render(generation, ...panels);
}

export async function viewHistory(generation) {
  const runs = await api("/api/runs");
  const finished = runs.runs.filter((run) => run.is_terminal);
  const panels = [el("h2", { text: "History" })];
  if (!finished.length) {
    panels.push(el("p", { class: "muted empty", text: "No search has finished yet." }));
  } else {
    panels.push(
      el("div", { class: "panel" }, [
        el("h3", { text: `Finished (${finished.length})` }),
        runTable("Every search that has ended, newest first, with how it ended.", finished),
      ]),
    );
  }
  panels.push(truncation(runs, "The finished ones"));
  render(generation, ...panels);
}
