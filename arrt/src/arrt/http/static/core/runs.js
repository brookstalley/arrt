/* What a Get is called, by its kind, wherever one is shown.
 *
 * Every spending request is a Get (`ia-proposal.md` § Objects, and ruling 4 of
 * 2026-10-07), whichever way it started: from words in Ask, again for works an
 * earlier Get found no scan of, or for works the curator chose. The server
 * keeps the three as `RunKind`; the curator reads one noun, and the kind only
 * where it tells two rows apart. Only a Get from Ask has an intent, so the
 * other two are named by what they are. */

export const KIND_WORDS = { discovery: "Get from Ask", resolve: "Get again", get: "Get of chosen works" };

/* A Get's heading: its intent, or what kind of Get it is when it has none. */
export function runTitle(run) {
  return run.intent || (run.kind === "get" ? "Get" : "Get again");
}

/* A Get's state as a word, by `RunStatus`, for a table cell. A status added there
 * and not here is shown as itself rather than guessed at. */
export const STATE_WORDS = {
  resolving_works: "Choosing works",
  awaiting_approval: "Waiting for you",
  resolving_images: "Looking for images",
  completed: "Finished",
  failed: "Failed",
  declined: "Declined",
  cancelled: "Cancelled",
  halted_by_budget: "Stopped at the spending cap",
  interrupted: "Interrupted",
};
