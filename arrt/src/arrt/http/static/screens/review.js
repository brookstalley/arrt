/* Review — judging one Get's candidates, at `#review/<id>`.
 *
 * Contextual, opened from a Get from Ask or a Get again. A Get of chosen
 * works is judged on the Get's own page instead, and this address still answers for a
 * Get, because addresses outlive the links that made them. The cards are
 * `core/reviewing.js`'s, which both screens draw.
 */

import { fetchAllCandidates } from "../core/api.js";
import { destinationOf, destinationSentence, readThemes } from "../core/destination.js";
import { el, render } from "../core/render.js";
import { reviewSection } from "../core/reviewing.js";
import { link, setTitle } from "../core/router.js";
import { runTitle } from "../core/runs.js";

export async function viewReview(runId, generation) {
  const [page, themes] = await Promise.all([fetchAllCandidates(runId), readThemes()]);
  setTitle(generation, `Review: ${runTitle(page.run)}`);
  render(
    generation,
    // Back to the Get rather than to a sidebar page: Review is opened from one
    // particular Get and the way out is that Get, which is a screen and not a
    // place in the navigation.
    el("p", {}, [link({ view: "get", id: runId }, { class: "action quiet", text: "← Get" })]),
    el("h1", { text: runTitle(page.run) }),
    // Where an Accept sends the work, said before the first one is pressed.
    el("p", { class: "muted run-destination", text: destinationSentence(destinationOf(page.run, themes)) }),
    ...reviewSection(page),
  );
}
