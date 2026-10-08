/* Doing something the curator asked for, and saying beside it when it failed.
 *
 * Every write in the client goes through `attempt`. A failed one used to land in
 * the banner at the top of the view as the fetch's own words — "Failed to
 * fetch" — often off-screen from the button pressed, naming neither the act nor
 * what became of it (`ux-review-2026-10.md` finding 11). So the failure is said
 * where the curator is looking, as a sentence: what they asked for, and what
 * happened instead.
 *
 * **The control is left as it was**, enabled and with its label, so trying
 * again is one more press of the same thing. Pressing it again takes the old
 * sentence away first, and succeeding takes it away for good.
 *
 * **What the sentence claims is only what the answer says.** A refusal (a 4xx,
 * in the service's own words) is the server declining before it changed
 * anything, so it says *Nothing was changed.* A fault (a 5xx) or no answer at
 * all cannot say that: the write may have landed before the failure, and a
 * curator told otherwise would repeat an act that had already happened.
 *
 * Reads keep `guard` and its banner (`core/render.js`): a page that could not
 * load is a fact about the page, not about any one control on it.
 */

import { el, guard, showError } from "./render.js";

/* The sentence beside each control that has one, so the next press removes it. */
const said = new WeakMap();

/* What became of the request, for the sentence after "Couldn't …: ". */
export function outcome(failure) {
  if (failure && failure.unanswered) return "the server didn't answer.";
  const reason = String((failure && failure.message) || "something went wrong").trim();
  const ended = /[.!?]$/.test(reason) ? reason : `${reason}.`;
  const status = failure && failure.status;
  if (status >= 400 && status < 500) return `${ended} Nothing was changed.`;
  if (status >= 500) return `the server failed while doing it: ${ended}`;
  return ended;
}

/* The whole sentence: the act, then what became of it. */
export function failedSentence(act, failure) {
  return `Couldn't ${act}: ${outcome(failure)}`;
}

function forget(control) {
  const note = said.get(control);
  if (note) note.remove();
  said.delete(control);
}

/* Say it beside `control`: directly after it, so it reads next to the thing
 * pressed whatever row, cell or card that sits in.
 *
 * The alert is put on the page empty and filled a task later, because a live
 * region created and filled in the same breath announces nothing
 * (`accessibility-spec.md` § Announcement and semantics). */
function sayBeside(control, sentence) {
  forget(control);
  const note = document.createElement("span");
  note.className = "act-failure";
  note.setAttribute("role", "alert");
  control.after(note);
  said.set(control, note);
  setTimeout(() => {
    note.textContent = sentence;
  }, 0);
}

/* Run `write`, the request the curator asked for by pressing `control`; `act`
 * names it as the rest of "Couldn't …", with the thing it was done to ("reject
 * Nighthawks", "hang Winter on the living room").
 *
 * `then` is what follows a success — a repaint, a recount, a navigation — and
 * runs under `guard` rather than here, because a read that fails after the write
 * landed is not the act failing: saying "Couldn't reject" over a rejection the
 * server recorded is the one wrong thing this sentence must never say.
 *
 * Answers whether the write succeeded, and never throws. A control the write
 * took off the page has nowhere to be beside, so its failure goes to the banner
 * rather than nowhere, or to `elsewhere` when the caller names a better place. */
export async function attempt(control, act, write, { then = null, elsewhere = showError } = {}) {
  if (control) forget(control);
  let answer;
  try {
    answer = await write();
  } catch (failure) {
    const sentence = failedSentence(act, failure);
    if (control && control.isConnected) sayBeside(control, sentence);
    else elsewhere(sentence);
    return false;
  }
  if (then) await guard(() => then(answer));
  return true;
}

/* Say a failure at page level, where it outlives the next paint.
 *
 * For an act whose control is gone by the time it fails: a held verdict sent
 * because the curator navigated away. The error banner is cleared by the next
 * page's paint, which can land after the failure, so these lines sit in a
 * region of their own above it and stay until dismissed. Created on first use,
 * inside `main` before the banner, so the page's markup is unchanged until a
 * failure needs it. */
export function reportElsewhere(sentence) {
  let region = document.getElementById("failures-elsewhere");
  if (!region) {
    region = el("div", { id: "failures-elsewhere", class: "note error failures-elsewhere", role: "alert" });
    document.getElementById("error").before(region);
  }
  const line = el("p", {});
  const dismiss = el("button", {
    class: "action quiet",
    type: "button",
    text: "Dismiss",
    onclick: () => {
      line.remove();
      if (!region.querySelector("p")) region.remove();
    },
  });
  line.append(dismiss);
  region.append(line);
  // Filled a task later, so the alert announces what was put into it.
  setTimeout(() => dismiss.before(`${sentence} `), 0);
}
