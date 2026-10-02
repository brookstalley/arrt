/* Review — judging one run's candidates, at `#review/<run>`.
 *
 * Contextual, opened from a discovery run or a re-search. A Get's works are
 * judged on the Get's own page instead, and this address still answers for a
 * Get, because addresses outlive the links that made them. The cards are
 * `core/reviewing.js`'s, which both screens draw.
 */

import { fetchAllCandidates } from "../core/api.js";
import { destinationOf, destinationSentence, readThemes } from "../core/destination.js";
import { el, render } from "../core/render.js";
import { reviewSection } from "../core/reviewing.js";
import { go } from "../core/router.js";
import { runTitle } from "../core/runs.js";

export async function viewReview(runId, generation) {
  const [page, themes] = await Promise.all([fetchAllCandidates(runId), readThemes()]);
  render(
    generation,
    // Back to the run rather than to a sidebar page: Review is opened from one
    // particular search and the way out is that search, which is a screen and
    // not a place in the navigation.
    el("p", {}, [
      el("button", { class: "action quiet", type: "button", text: page.run.kind === "get" ? "← The Get" : "← The search", onclick: () => go("run", runId) }),
    ]),
    el("h2", { text: runTitle(page.run) }),
    // Where an Accept sends the work, said before the first one is pressed.
    el("p", { class: "muted run-destination", text: destinationSentence(destinationOf(page.run, themes)) }),
    ...reviewSection(page),
  );
}
