/* What a run is called, by its kind, wherever a run is shown.
 *
 * Three kinds share one screen: a discovery run is a search the curator asked
 * for in words, a re-search looks again for works an earlier run named, and a Get
 * looks for works the curator chose. Only a discovery run has an intent, so the
 * other two are named by what they are. */

export const KIND_WORDS = { discovery: "search", resolve: "re-search", get: "Get" };

/* A run's heading: its intent, or what kind of run it is when it has none. */
export function runTitle(run) {
  return run.intent || (run.kind === "get" ? "Get" : "Re-search");
}
