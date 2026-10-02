/* How many works wait for a verdict, wherever the sidebar shows it.
 *
 * *To review* is the one queue that needs the curator (`ia-proposal.md` § The
 * map), so its count sits on its own link and on Activity's, as Sonarr counts
 * its queue on Activity. A number alone carries no meaning to a screen reader or
 * at a glance, so each count is written with its word beside it, and the link's
 * accessible name says the same.
 *
 * Read again after every navigation and after every verdict, the two moments the
 * count can change from here. */

import { api } from "./api.js";
import { counted } from "./counting.js";
import { el, fill } from "./render.js";

export async function paintAwaiting() {
  const slots = document.querySelectorAll("[data-count-slot='awaiting']");
  if (!slots.length) return;
  let waiting = 0;
  try {
    waiting = (await api("/api/runs?awaiting=true")).awaiting_works || 0;
  } catch (failure) {
    // A count that could not be read shows nothing rather than a wrong number;
    // To review itself reports the failure when the curator opens it. Said in
    // the console, so "could not count" is not silently "nothing waits".
    console.warn(`The To review count could not be read: ${failure.message}`);
    waiting = 0;
  }
  for (const slot of slots) {
    const link = slot.closest("a");
    const label = link.querySelector(".label") || link.firstChild;
    const name = label ? label.textContent : "";
    // The page's own link already says "To review", so it carries the number;
    // Activity's link says the words as well.
    const words = slot.closest("a.section-link") ? `${waiting} to review` : String(waiting);
    fill(slot, waiting ? el("span", { class: "awaiting-count", text: words }) : null);
    if (waiting) link.setAttribute("aria-label", `${name}: ${counted(waiting, "work")} to review`);
    else link.removeAttribute("aria-label");
  }
}
