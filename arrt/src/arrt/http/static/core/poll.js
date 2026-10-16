/* Watching something that is still working — the chain a polling screen carries.
 *
 * **In `core/` because it is mechanism, and a polling screen takes it from here
 * rather than copying it.** Claim a generation, re-check it after every await,
 * and schedule the next look only while the thing watched has not stopped.
 * `screens/` modules may not import each other (`architecture.md` § Components &
 * Responsibilities), so mechanism a second screen would need lives here.
 * `screens/run.js` is its caller.
 *
 * **What is shared is the mechanism, not the policy.** Which view is being
 * watched, which id, how often, and what counts as stopped are all the screen's
 * own and are passed in: a run is stopped when the server says `is_terminal`.
 * A caller that finds itself editing this file to hold its own predicate has
 * found the boundary in the wrong place.
 *
 * **Failure counting is deliberately not here.** The run screen ends a watch
 * after consecutive failures because a bookmarked run that no longer exists
 * answers 400 forever. That is the run's own state, so the count stays in
 * `screens/run.js` with the reasoning that produced it.
 *
 * **`core/router.js` bumps the same counter and does not call through here**, and
 * that is a cycle rather than an oversight: this module needs `refresh` to take
 * the next look, so a router that claimed through this module would import the
 * thing importing it. The router's bumps are navigation invalidating whatever was
 * in flight, which is the counter's other job and not a poll chain.
 */

import { refresh } from "./router.js";
import { state } from "./state.js";

/* Claim the current generation for the paint that is starting.
 *
 * Every paint supersedes the ones before it. An earlier paint still in flight
 * must not land over a newer one or schedule a second timer beside its own —
 * pressing a button while a poll is mid-request is enough to have two chains
 * running, and two chains double the request rate on every tick thereafter.
 *
 * Returns the generation so the caller can hold it and re-check it; a paint that
 * discards it is saying only "nothing in flight may land", which is what
 * navigating away means. */
export function claimPoll() {
  state.poll += 1;
  return state.poll;
}

/* Whether the paint holding this generation is still the current one.
 *
 * Checked after every await, not only at the end: a paint that fetches twice can
 * be superseded between the two, and the second request's answer is then about a
 * screen nobody is looking at. */
export function pollIsCurrent(generation) {
  return state.poll === generation;
}

/* The next look at what is being watched, unless it has stopped.
 *
 * The timer's conditions are checked when it *fires* rather than cancelled on
 * navigation: a stale timer that finds the world moved on simply does nothing,
 * which is one mechanism instead of a handle to remember to clear on every path
 * out of a view.
 *
 * **The view and the id are redundant with the generation today, and a mutation
 * sweep survives deleting either.** `go` and `readHash` are the only writers of
 * `state.view` and `state.detailId`, and both bump `state.poll` in the same
 * synchronous block — so navigating anywhere, including to a different run of
 * the same kind, is already caught by the generation alone. They are kept as the
 * statement of what this timer is for: a check that says "still the same screen"
 * is what a reader needs in order to add the next navigation path correctly,
 * where a bare generation number says only "still the same paint". Written down
 * because `core/router.js` had exactly this survivor and recorded it the same
 * way, and because the next sweep will find these again — a survivor here is not
 * proof the line does nothing.
 *
 * `done` is the screen's own reading of whether there is anything left to wait
 * for, evaluated by the screen because what counts as stopped genuinely differs
 * between them. Passing it here rather than wrapping the call in an `if` is what
 * makes "poll only while something is still happening" one decision instead of
 * one per call site. */
export function schedulePollUnlessDone({ view, detailId, generation, intervalMs, done }) {
  if (done) return;
  window.setTimeout(() => {
    if (pollIsCurrent(generation) && state.view === view && state.detailId === detailId) refresh();
  }, intervalMs);
}
