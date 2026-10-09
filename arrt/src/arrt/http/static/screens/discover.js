/* Ask — asking for something in words.
 *
 * One thread with Ask's agent (`core/asking.js`), which searches as it answers
 * and offers what it found (the owner, 2026-10-08). Get is a press on what it
 * offers; the Gets that starts are listed under Activity, in Queue while they
 * work and History once they end.
 *
 * Where Radarr's Add New stood, under Artworks, at the address `#discover` it
 * has had since before the *arr labels; ruling 3 of `ia-proposal.md` dissolved
 * Add New into Get, an action on a selection, and this page. */

import { askPanel } from "../core/asking.js";
import { el, render } from "../core/render.js";
import { state } from "../core/state.js";

export async function viewDiscover(generation) {
  // Words handed over from the top bar's "Ask about …" row, as Sonarr hands
  // its term to Add New: filled in and never sent.
  const thread = await askPanel({ term: state.params.term || "" });
  render(generation, el("h1", { text: "Ask" }), thread);
}
