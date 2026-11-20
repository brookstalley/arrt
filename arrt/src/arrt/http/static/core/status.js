/* The top bar's status indicator, and the System badge beside it in the sidebar.
 *
 * **The indicator is always present and never silent.** It reads "Well" or names
 * what is wrong, on every page and at every width, and opens System › Status.
 * `information-architecture.md` § The *arr layout keeps it beside Sonarr's
 * badge rather than replacing it with one: the badge is a number, and a state
 * shown by a number alone has no word, which `accessibility-spec.md` counts as a
 * bug at every viewport. The drawer also hides the badge on a phone, where the
 * indicator is the only status on screen.
 *
 * **The badge is Sonarr's**: a count of the problems on the System link, shown
 * only when there is one, with the link's name saying the count in words — or
 * "all well", so that the badge's absence is a statement and not a gap. Both
 * are painted from one reading, so they cannot disagree.
 *
 * **It states no verdict of its own: it says the server's.** `GET /api/health`
 * carries `troubles`, every fault the server's one health model finds
 * (`services/health.py` `HealthReading.troubles`: a wall a Player shows that has
 * stopped reporting, a Player not heard from, a display two Players claim, the
 * backup, a source, a Watch, the failed fetches), each in the household's words.
 * The indicator joins those words and the badge counts them; nothing here
 * derives a fault again from the readings beside them, so the badge, the
 * indicator and Status's list (`screens/health.js`) cannot count one fault
 * differently. Nor does anything here depend on how many troubles one cause
 * produces: that is the server's to decide, and it may change.
 *
 * **A setup step is never a fault, and never well** (`vocabulary.json`'s
 * `setup` flags): a wall no Player shows, a Player with no token or no report
 * yet, and a household with no wall at all. The server states them itself, in
 * `GET /api/health`'s `setup_steps` (`services/health.py`
 * `HealthReading.setup_steps`), each in the household's words, and leaves them
 * out of `troubles`. The indicator therefore has three readings: troubles
 * (counted, in the server's words, ▲), setup to finish (not counted, ○, "Setting
 * up" on a phone, in the server's words, in the indicator's own `--text`: a step
 * to take is no fault's colour), and well (●). A household whose only open items
 * are setup steps is not well, and a household with no wall never is: the server
 * always states that step. When there are troubles and steps both, the
 * indicator says the troubles and the steps after them, apart, and the badge
 * counts the troubles alone.
 *
 * **`description` is not read here, deliberately.** It is a summary sentence of
 * the readings, never a signal; a client deriving a state from prose would be
 * inventing a judgement out of it.
 *
 * **It does not poll**, and that is the same decision the health panel already
 * made: this surface is the product's only alerting mechanism and its mean time
 * to detection is bounded by how often the curator opens the page. Repainting on
 * every navigation is what that bound already costs; a background timer would
 * add load to a Pi without changing it.
 *
 * A reading it cannot find is never treated as a reading that was fine. A green
 * dot computed from nothing is precisely the failure this product exists to
 * refuse, and it is the failure mode a shape change produces — so an answer
 * missing a part this reads (`troubles`, `walls`) makes the indicator say so
 * out loud.
 */

import { api } from "./api.js";
import { counted } from "./counting.js";
import { GLYPHS } from "./glyphs.js";
import { el, fill } from "./render.js";
import { go } from "./router.js";

/* The indicator's reading: `state` is `well`, `unwell` or `setup`; `count` is
 * how many troubles the badge shows; `words` what the indicator says of them
 * (or, in `setup`, of the steps); `steps` the words of every setup step, which
 * the indicator, the badge's name and Status all state from the same list. */
export function statusReading(health) {
  if (!health) return unwell(1, "The health reading could not be fetched");
  if (!Array.isArray(health.troubles)) return unwell(1, "The health reading carries no list of what is wrong");
  if (!Array.isArray(health.setup_steps)) return unwell(1, "The health reading carries no list of what is left to set up");
  if (!Array.isArray(health.walls)) return unwell(1, "The health reading carries no walls");
  const troubles = health.troubles;
  const steps = health.setup_steps.map(stepWords);
  if (troubles.length) {
    // A trouble the server sent without words is still one, and is said as one
    // rather than dropped from the sentence the badge counts it in.
    return { ...unwell(troubles.length, troubles.map((trouble) => trouble.words || "A fault the reading did not word").join(" · ")), steps };
  }
  if (steps.length) return { state: "setup", well: false, count: 0, words: steps.join(" · "), steps };
  return { state: "well", well: true, count: 0, words: "Well", steps };
}

/* A setup step's words: the server's, or a stated lack of them, so a step sent
 * without words is still one. Status words its list through this too. */
export function stepWords(step) {
  return step.words || "A step the reading did not word";
}

function unwell(count, words) {
  return { state: "unwell", well: false, count, words, steps: [] };
}

/* The indicator's glyph, and its state in one word for a phone's top bar. A
 * setup step is drawn as one (○: there is none yet), never as a fault, and is
 * given no colour of its own: the indicator's own `--text`. */
const SHOWN = {
  well: { glyph: GLYPHS.good, short: "Well" },
  unwell: { glyph: GLYPHS.problem, short: "Unwell" },
  setup: { glyph: GLYPHS.none, short: "Setting up" },
};

/* The setup steps the indicator says beside troubles: none when there are no
 * troubles (the steps are then its words) and none when there are no steps. */
function stepsAfter(reading) {
  return reading.state === "unwell" ? reading.steps.join(" · ") : "";
}

/* Glyph as well as colour, and the word as well as the glyph — the same rule
 * every badge on this surface follows, on the one element that is on every
 * screen. `data-state` is what the stylesheet colours from, so the colour is a
 * third carrier rather than the only one. */
function paint(reading) {
  const indicator = document.getElementById("status");
  const state = reading.state;
  // The indicator is a live region, and every navigation reads the panel
  // again: rewritten with the words it already holds, it re-announced "Well"
  // on every page (`accessibility-spec.md`: a live region is not rewritten
  // with content it already holds). Only a change is written.
  const said = stepsAfter(reading);
  if (indicator.dataset.state === state && indicator.dataset.words === reading.words && indicator.dataset.setup === said) {
    paintBadge(reading);
    return;
  }
  indicator.dataset.state = state;
  indicator.dataset.words = reading.words;
  indicator.dataset.setup = said;
  // Two wordings: the whole sentence, and its state in one word for a phone's
  // top bar, which has room for a word and not for "The hall has not
  // reported". The stylesheet shows one; a screen reader always reads the
  // sentence (`app.css`, `.status-short`).
  fill(indicator,
    el("span", { class: "glyph", text: SHOWN[state].glyph, "aria-hidden": true }),
    el("span", { class: "status-words", text: reading.words }),
    // The steps still to take, said after the troubles they sit beside and apart
    // from them: in `setup` they are the words above, so none is said twice.
    said ? el("span", { class: "status-setup", text: said }) : null,
    el("span", { class: "status-short", text: SHOWN[state].short, "aria-hidden": true }),
  );
  paintBadge(reading);
}

function paintBadge(reading) {
  const slot = document.querySelector("[data-status-slot]");
  if (!slot) return;
  const count = reading.count;
  const link = slot.closest("a");
  // The section's own label, read rather than written again here, so the name
  // keeps containing the visible word if the section is ever renamed.
  const label = link.querySelector(".label").textContent;
  // A setup step is neither "all well" nor a problem, and is counted apart from
  // the problems the number shows: the link's name says both.
  const problems = count ? counted(count, "problem") : "";
  const steps = reading.steps.length ? `${counted(reading.steps.length, "step")} to finish` : "";
  const words = [problems, steps].filter(Boolean).join(", and ") || "all well";
  link.setAttribute("aria-label", `${label}: ${words}`);
  fill(slot, count ? el("span", { class: "status-count", text: String(count), "aria-hidden": true }) : "");
}

/* Read the panel and say what it said.
 *
 * The failure is caught here rather than left to `guard`, and the difference
 * matters: `guard` writes to the page's error banner, and a health check that
 * could not run is not a refusal of whatever the curator just did. It is a fact
 * about the indicator, and it belongs in the indicator. */
export async function paintStatus() {
  let health = null;
  try {
    health = await api("/api/health");
  } catch (failure) {
    paint(unwell(1, `The health reading could not be fetched: ${failure.message}`));
    return;
  }
  paint(statusReading(health));
}

/* A plain click goes through the router, as the sidebar's links do, so the
 * indicator still opens Status from Status itself; a click with a modifier is
 * the browser's, a new tab. */
export function installStatus() {
  document.getElementById("status").addEventListener("click", (event) => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    go("health");
  });
}
