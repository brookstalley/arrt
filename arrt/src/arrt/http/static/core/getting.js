/* Get: the one acquiring act, on any selection of works the library does not hold.
 *
 * Ruling 3 of `ia-proposal.md` dissolved Add New into this: a curator who has found
 * works on the Artist page or the results page ticks them and gets them, and a work's
 * own page gets that one. Each work is named by its Wikidata item, which is what the
 * server asks the image sources by.
 *
 * **The page stays where it is.** Getting takes minutes, so the control says what
 * started, in its live region, with a link to the run; Queue lists it too. A held
 * row offers no tick box, because the library already has it, so the only skips the
 * curator hears about are the server's: an item already being got, or one Wikidata
 * does not have. */

import { api } from "./api.js";
import { agree, counted } from "./counting.js";
import { el, fill, guard } from "./render.js";
import { go } from "./router.js";

/* Why the server left an item out, as a clause after "N works" or "1 work". The keys
 * are `SkipReason`'s values, held to it by the vocabulary test. */
export const SKIP_WORDS = {
  held: ["is already in your library", "are already in your library"],
  being_got: ["is already being got", "are already being got"],
  not_found: ["is not a work Wikidata has", "are not works Wikidata has"],
};

/* What a Get did, in one or two sentences: what started, and what was left out. */
export function getSentence(asked, outcome) {
  const skipped = outcome.skipped || [];
  const started = asked - skipped.length;
  const lead = outcome.run ? `Getting ${counted(started, "work")}.` : "Nothing was started.";
  const reasons = Object.keys(SKIP_WORDS)
    .map((reason) => [reason, skipped.filter((entry) => entry.reason === reason).length])
    .filter(([, count]) => count > 0)
    .map(([reason, count]) => `${count} ${agree(count, ...SKIP_WORDS[reason])}`);
  return reasons.length ? `${lead} Left out: ${reasons.join("; ")}.` : lead;
}

/* Ask for these items and show what happened in `status`, a live region. */
async function getAndSay(qids, status) {
  const outcome = await api("/api/gets", { method: "POST", body: JSON.stringify({ qids }) });
  fill(
    status,
    el("span", { text: getSentence(qids.length, outcome) }),
    outcome.run ? " " : null,
    outcome.run
      ? el("button", { class: "link", type: "button", text: "Open the Get", onclick: () => go("run", outcome.run.run_id) })
      : null,
  );
  status.focus();
  return outcome;
}

function aStatus() {
  return el("p", { class: "muted get-status", "aria-live": "polite", tabindex: "-1" });
}

/* A selection of registry works and the control that gets them.
 *
 * `box(qid, title)` makes the tick box for one row; `node` is the control, which
 * reads *Get 3 works* and is disabled while nothing is ticked. A Get clears the
 * ticks, since those works are now being got. */
export function getSelection() {
  const chosen = new Map();
  const status = aStatus();
  const button = el("button", { class: "action", type: "button" });
  const settle = () => {
    button.disabled = chosen.size === 0;
    button.textContent = chosen.size ? `Get ${counted(chosen.size, "work")}` : "Get";
  };
  button.addEventListener("click", () =>
    guard(async () => {
      const qids = [...chosen.keys()];
      button.disabled = true;
      try {
        await getAndSay(qids, status);
        for (const box of chosen.values()) box.checked = false;
        chosen.clear();
      } finally {
        settle();
      }
    }),
  );
  settle();
  return {
    node: el("div", { class: "row get-control" }, [button, status]),
    box(qid, title) {
      const box = el("input", { type: "checkbox", "aria-label": `Select ${title} to get` });
      box.addEventListener("change", () => {
        if (box.checked) chosen.set(qid, box);
        else chosen.delete(qid);
        settle();
      });
      return box;
    },
  };
}

/* *Get this work*, for the page of one work the library does not hold. */
export function getOne(qid) {
  const status = aStatus();
  const button = el("button", { class: "action", type: "button", text: "Get this work" });
  button.addEventListener("click", () =>
    guard(async () => {
      button.disabled = true;
      try {
        const outcome = await getAndSay([qid], status);
        // Got once, it stays got: a second press would only be skipped as being got.
        button.disabled = Boolean(outcome.run);
      } catch (failure) {
        button.disabled = false;
        throw failure;
      }
    }),
  );
  return el("div", { class: "row get-control" }, [button, status]);
}
