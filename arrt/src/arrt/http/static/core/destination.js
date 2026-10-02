/* Where a run's accepted works go, in words, wherever a run is shown.
 *
 * A run carries `destination_theme_id`: the theme a Get named, or null for the
 * default theme, which is where every other run's acceptances go. The run holds
 * an id and not a name, because a theme can be renamed or deleted after the Get
 * started, so the name is looked up here, from `GET /api/themes`, by whoever
 * shows it. Queue, the run page and Review all say it the same way through this
 * module, so the three cannot word a deleted theme three ways.
 *
 * **A null destination names whichever theme is the default now.** The server
 * does not record which theme was the default at acceptance, so for a finished
 * run whose default has since moved this names the present one.
 *
 * **A re-search is the exception.** It covers works its parent run holds, and an
 * accepted work goes where its own run sends it (work, candidate, run, in
 * `LibraryFacade.destinations`), so a re-search's own null says nothing: its
 * works go wherever the run it re-searches sends them. */

import { api } from "./api.js";

/* The theme listing, or null when it could not be read.
 *
 * Null rather than a throw, because every caller is a screen whose main job is
 * something else: a run page that lost its watch, or a Review that would not
 * open, because the theme names could not be read would be a worse failure than
 * the one it reports. `destinationWords` says the names could not be read. */
export async function readThemes() {
  try {
    return await api("/api/themes");
  } catch {
    return null;
  }
}

/* Where this run's accepted works go: `{ state, name }`.
 *
 * `state` is `default` (the default theme, named), `theme` (the named theme),
 * `none` (no destination named and no theme is the default, so acceptances join
 * nothing), `deleted` (the named theme is gone, so acceptances join nothing),
 * `parent` (a re-search, whose works go where its parent sends them) or
 * `unknown` (the listing could not be read). */
export function destinationOf(run, listing) {
  if (run.kind === "resolve") return { state: "parent", name: null };
  if (!listing) return { state: "unknown", name: null };
  const themes = listing.themes.map((placement) => placement.theme);
  if (run.destination_theme_id === null || run.destination_theme_id === undefined) {
    const fallback = themes.find((theme) => theme.is_default);
    return fallback ? { state: "default", name: fallback.name } : { state: "none", name: null };
  }
  const named = themes.find((theme) => theme.theme_id === run.destination_theme_id);
  return named ? { state: "theme", name: named.name } : { state: "deleted", name: null };
}

/* The destination as a noun phrase, for a table cell or after "into". */
export function destinationWords(destination) {
  if (destination.name) return destination.name;
  if (destination.state === "deleted") return "a theme that has been deleted";
  if (destination.state === "none") return "no theme";
  if (destination.state === "parent") return "as the run it re-searches";
  return "a theme that could not be looked up just now";
}

/* The destination as a sentence, for the run page and Review. */
export function destinationSentence(destination) {
  if (destination.name) return `Works you accept from this run join ${destination.name}.`;
  if (destination.state === "deleted") {
    return "Works you accept from this run were to join a theme that has been deleted, so they join no theme.";
  }
  if (destination.state === "none") {
    return "Works you accept from this run join no theme, because no theme is the default.";
  }
  if (destination.state === "parent") {
    return "Works you accept from this re-search join the theme the run it re-searches sends its works to.";
  }
  return "Which theme works you accept from this run join could not be looked up just now.";
}
