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

import { api } from "../core/api.js";
import { table } from "../core/badges.js";
import { el, render } from "../core/render.js";
import { go } from "../core/router.js";
import { KIND_WORDS } from "../core/runs.js";

/* The runs as rows. A re-search and a Get are runs too. A Get has no intent of
 * its own: the curator chose its works, which is what its row says. */
function runTable(caption, runs) {
  return table(
    caption,
    ["Asked for", "Kind", "State", "Started", "Open"],
    runs.map((run) => [
      run.intent || (run.kind === "get" ? "Works you chose" : "—"),
      KIND_WORDS[run.kind] || run.kind,
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

export async function viewQueue(generation) {
  const runs = await api("/api/runs");
  const active = runs.runs.filter((run) => !run.is_terminal);
  const panels = [el("h2", { text: "Queue" })];
  if (!active.length) {
    // Only as sure as the listing: when the cap left older searches out, one of
    // them may still be at the approval gate, so the page says what it checked
    // rather than that nothing is in flight.
    const nothing = runs.truncated
      ? `Nothing is in flight among the ${runs.count} most recent searches.`
      : "Nothing is in flight.";
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
