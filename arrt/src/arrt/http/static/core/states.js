/* The household's words for a wall's display states and a Player's states, and the glyph each is drawn with.
 *
 * **The words are the contract's**, quoted from `contract/vocabulary.json`
 * (`display_states` and `player_states`), which Arrt and every Arrt Player say
 * alike. The browser cannot read the package (it is a development dependency
 * the image does not install, and the page loads no data file for it), so the
 * words are written here once and `arrt/tests/unit/test_wall_state_words.py`
 * holds them to the package in both directions: a word that differs, a state
 * the package has and this lacks, and a state this has and the package does not
 * each turn it red. No screen words a state anywhere else.
 *
 * **`setup` is the package's too**: a state that is a step not yet taken (a
 * wall no Player shows, a Player with no token or no report yet) is drawn as a
 * step, never coloured or counted as a fault. Whether something is a fault is
 * the server's to say, in `GET /api/health`'s `troubles` (`core/status.js`);
 * nothing here judges one.
 *
 * **A state with no word reads as unreachable's word, "Not known"**, as the
 * package's `_about` tells every reader to: never another state's word, and
 * never blank. The glyph is `core/glyphs.js`'s, named by meaning, and a word is
 * always beside it, so colour and glyph are never the only carriers of a state.
 */

import { dated } from "./dates.js";
import { GLYPHS } from "./glyphs.js";

/* A wall's display state (`programming/display_state.py` `ScreenState`): the
 * controller's five, then the server's two. */
export const DISPLAY_STATES = Object.freeze({
  showing_art: { word: "Showing", setup: false, glyph: "good" },
  in_use: { word: "In use", setup: false, glyph: "waiting" },
  dark: { word: "Screen off", setup: false, glyph: "none" },
  no_screen: { word: "No screen", setup: false, glyph: "problem" },
  unreachable: { word: "Not known", setup: false, glyph: "unknown" },
  unassigned: { word: "No Player yet", setup: true, glyph: "none" },
  silent: { word: "Not reporting", setup: false, glyph: "problem" },
});

/* A Player's state, and each of its outputs' (`programming/player_state.py`
 * `PlayerState`). `{date}` is the last report's, filled by `playerStateWord`. */
export const PLAYER_STATES = Object.freeze({
  no_token: { word: "No token yet", setup: true, glyph: "none" },
  awaiting_report: { word: "Waiting for its first report", setup: true, glyph: "waiting" },
  reporting: { word: "Reporting", setup: false, glyph: "good" },
  not_heard_from: { word: "Not heard from since {date}", setup: false, glyph: "problem" },
  report_unreadable: { word: "Report unreadable", setup: false, glyph: "problem" },
});

/* The state no word was found for is said as this one's word. */
const NOT_KNOWN = "unreachable";

/* A display state's entry, or unreachable's for a state this client has no word for. */
function displayEntry(state) {
  return Object.hasOwn(DISPLAY_STATES, state) ? DISPLAY_STATES[state] : DISPLAY_STATES[NOT_KNOWN];
}

/* The word for a wall's display state: "Showing", "No Player yet", or "Not known". */
export function displayStateWord(state) {
  return displayEntry(state).word;
}

/* The glyph for a wall's display state, as a character. */
export function displayStateGlyph(state) {
  return GLYPHS[displayEntry(state).glyph];
}

/* Whether a wall's display state is a step of setting up rather than anything else. */
export function isDisplaySetup(state) {
  return Object.hasOwn(DISPLAY_STATES, state) && DISPLAY_STATES[state].setup;
}

/* The word for a Player's (or an output's) state, `{date}` filled with `since`
 * in this client's one way of writing a moment. A state with no word is said as
 * not known, as a wall's is. */
export function playerStateWord(state, since = null) {
  if (!Object.hasOwn(PLAYER_STATES, state)) return DISPLAY_STATES[NOT_KNOWN].word;
  return PLAYER_STATES[state].word.replace("{date}", dated(since));
}

/* The glyph for a Player's state, as a character; unknown's for a state with no word. */
export function playerStateGlyph(state) {
  return Object.hasOwn(PLAYER_STATES, state) ? GLYPHS[PLAYER_STATES[state].glyph] : GLYPHS.unknown;
}

/* Whether a Player's state is a step of setting up: no token yet, or no report yet. */
export function isPlayerSetup(state) {
  return Object.hasOwn(PLAYER_STATES, state) && PLAYER_STATES[state].setup;
}
