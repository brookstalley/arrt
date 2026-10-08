/* A verdict held a few seconds with Undo beside it, before it is sent.
 *
 * **Undo is the client's, because the server's cannot be**: accepting creates
 * the artwork and wakes the acquisition queue, and rejecting (or forgetting)
 * suppresses the work from every later Get. So a verdict is held here and only
 * then sent; Undo inside that window means nothing was ever asked.
 *
 * Shared by the review cards (`core/reviewing.js`) and Wanted's Forget
 * (`screens/activity.js`), keyed by the candidate's id, because both are the
 * same verdict on the same record and one work cannot be held twice.
 *
 * **A hold belongs to the work, not to the controls drawn for it.** A page can
 * redraw while a verdict is held — a Get's page as it finds works, Wanted after
 * another row's Forget lands — and the controls it draws for a held work must
 * show the hold, Undo and the seconds left, rather than offer a verdict that is
 * already on its way. `showHold` is what a redraw calls for that.
 *
 * **A held verdict is never dropped.** Leaving the page — another address, a
 * reload, closing the tab — sends every held verdict at once, with `keepalive`
 * so the request outlives the page that made it. A send whose controls are no
 * longer on the page has nowhere beside them to fail, so its failure is said at
 * page level (`reportElsewhere`), naming the act and the work.
 */

import { attempt, failedSentence, reportElsewhere } from "./acting.js";
import { el, guard } from "./render.js";

export const VERDICT_HOLD_MS = 5000;

/* What a held verdict is called while it waits, by the act the curator pressed. */
const HOLDING_WORDS = { accept: "Accepting", reject: "Rejecting", forget: "Forgetting" };

/* Every verdict waiting out its hold, by work. */
const HELD = new Map();

function sendHeld() {
  for (const record of [...HELD.values()]) send(record, { leaving: true });
}

window.addEventListener("hashchange", sendHeld);
window.addEventListener("pagehide", sendHeld);

/* The hold on this work, or null: what a redraw asks before drawing controls. */
export function heldFor(key) {
  return HELD.get(key) || null;
}

/* Hold a verdict.
 *
 * `act` is the verb as a failure names it ("accept"), `title` the work's.
 * `controls` is the element the hold stands in for and `pressed` the button
 * pressed in it, which takes the keyboard back on Undo and has a failure said
 * beside it. `write({ keepalive })` sends the verdict; `then(answer)` follows a
 * sent one; `restored()` is called when the controls come back. */
export function hold({ key, act, title, controls, pressed, write, then = null }) {
  if (HELD.has(key)) return;
  const record = { key, act, title, write, then, deadline: Date.now() + VERDICT_HOLD_MS, timer: null, view: null };
  HELD.set(key, record);
  record.timer = setTimeout(() => send(record), VERDICT_HOLD_MS);
  showHold(record, controls, pressed, { focus: true });
}

function restore(view) {
  view.holding.remove();
  view.controls.hidden = false;
}

/* Draw the hold in place of `controls`: what is about to happen, the seconds
 * left, and Undo. Called by `hold`, and by a redraw for a work still held, so
 * redrawn controls never offer a verdict that is already waiting to be sent. */
export function showHold(record, controls, pressed, { focus = false } = {}) {
  const words = `${HOLDING_WORDS[record.act] || record.act} ${record.title}`;
  const undo = el("button", {
    class: "action quiet",
    type: "button",
    text: "Undo",
    "aria-label": `Undo: don't ${record.act} ${record.title}`,
  });
  const said = el("span", { role: "status" });
  // The seconds left, for the eye. Kept out of the live region, which would
  // otherwise read a number aloud every second.
  const left = el("span", { class: "muted verdict-countdown", "aria-hidden": "true" });
  const holding = el("div", { class: "row verdict-held" }, [said, left, undo]);
  const view = { controls, pressed, holding, said, undo };
  record.view = view;

  // A redraw builds the hold before its card is on the page, so the countdown
  // stops only once the hold has been shown and left the page, or has ended.
  let shown = false;
  const tick = () => {
    if (holding.isConnected) shown = true;
    if (HELD.get(record.key) !== record || (shown && !holding.isConnected)) {
      clearInterval(ticking);
      return;
    }
    const seconds = Math.max(0, Math.ceil((record.deadline - Date.now()) / 1000));
    left.textContent = `${seconds} s`;
  };
  const ticking = setInterval(tick, 250);

  undo.addEventListener("click", () => {
    clearTimeout(record.timer);
    clearInterval(ticking);
    HELD.delete(record.key);
    restore(view);
    if (pressed && pressed.isConnected) pressed.focus();
  });
  controls.hidden = true;
  controls.after(holding);
  tick();
  // Filled a task after the region is on the page, which is when a live
  // region announces (`accessibility-spec.md` § Announcement and semantics).
  setTimeout(() => {
    if (HELD.get(record.key) === record) said.textContent = `${words} in a few seconds.`;
  }, 0);
  if (focus) undo.focus();
}

async function send(record, { leaving = false } = {}) {
  clearTimeout(record.timer);
  if (HELD.get(record.key) !== record) return;
  HELD.delete(record.key);
  const view = record.view;
  const act = `${record.act} ${record.title}`;
  if (view) {
    view.undo.remove();
    view.said.textContent = `${HOLDING_WORDS[record.act] || record.act} ${record.title}…`;
  }
  // Leaving: the page these controls are on is going, so a failure is said at
  // page level whatever is still connected at the moment it arrives.
  if (leaving || !view || !view.pressed || !view.pressed.isConnected) {
    try {
      const answer = await record.write({ keepalive: leaving });
      if (record.then) await guard(() => record.then(answer));
    } catch (failure) {
      reportElsewhere(failedSentence(act, failure));
    }
    return;
  }
  const sent = await attempt(view.pressed, act, () => record.write({ keepalive: false }), {
    then: record.then,
    elsewhere: reportElsewhere,
  });
  // The controls drawn last for this work come back, wherever a redraw put them.
  if (!sent && record.view && record.view.holding.isConnected) restore(record.view);
}
