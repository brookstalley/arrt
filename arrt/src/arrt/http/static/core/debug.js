/* Whether this page was opened with `?debug`: the owner's ruling of
 * 2026-10-11 that engineering detail (file paths, content hashes, renditions,
 * a mat's hex, raw keys, plugin ids) is shown only to whoever asks for it.
 *
 * The page's own query, never the route's: every in-app link changes only the
 * hash, so the flag stays for as long as the address carries it, and it shows
 * in the address bar rather than hiding in the browser's storage. Read once,
 * when the client loads, since nothing in the app changes `location.search`.
 * Imports nothing. */

export const DEBUG = new URLSearchParams(window.location.search).has("debug");
