/* Where a work stands in the acquisition queue, said the same way everywhere.
 *
 * The Work page, a Review card for an accepted work, and Activity › Queue all
 * show the same state from the same field (`acquisition` on a work, or one row
 * of `GET /api/acquisitions`), so they share the words here. Each phase carries a
 * glyph and a word, never colour alone (`accessibility-spec.md`).
 *
 * The queue fetches one work at a time and a tiled fetch can take half an hour,
 * so Retry never fetches in the request: it moves the work to the front and the
 * line repaints from the state the server answers with. */

import { attempt } from "./acting.js";
import { api } from "./api.js";
import { counted } from "./counting.js";
import { dated } from "./dates.js";
import { el } from "./render.js";

const PHASES = {
  queued: { glyph: "◌", word: "queued" },
  fetching: { glyph: "↻", word: "fetching" },
  failed: { glyph: "▲", word: "failed" },
  gave_up: { glyph: "✗", word: "gave up" },
  paused: { glyph: "‖", word: "paused" },
};

//: How many tries the queue makes before it gives up: the first and three
//: retries (`library/acquisition/queue.py`, `GIVE_UP_AFTER`).
const TRIES = 4;

function when(iso) {
  return iso ? dated(iso) : null;
}

export function acquisitionBadge(state) {
  const phase = PHASES[state.phase] || { glyph: "?", word: state.phase };
  return el("span", { class: `badge badge-acquisition badge-acquisition-${state.phase}` }, [
    el("span", { class: "glyph", text: phase.glyph, "aria-hidden": true }),
    el("span", { text: phase.word }),
  ]);
}

/* What the state means, in one or two sentences a curator can act on. */
export function acquisitionSentence(state) {
  switch (state.phase) {
    case "queued":
      return state.failures
        ? `Waiting its turn to be fetched again, after ${counted(state.failures, "failed try", "failed tries")}: ${state.detail}`
        : "Waiting its turn to be fetched. The queue fetches one work at a time, then prepares it for the wall.";
    case "fetching":
      return `Being fetched since ${when(state.since)}, then prepared for the wall. A tiled fetch can take up to half an hour.`;
    case "failed":
      return `Try ${state.failures} of ${TRIES} failed: ${state.detail} It tries again at ${when(state.next_try_at)}.`;
    case "gave_up":
      return `Gave up after ${counted(state.failures, "try", "tries")}: ${state.detail} Nothing tries again until you retry.`;
    case "paused":
      return `Every fetch is paused: ${state.detail} ${state.remedy || "Nothing anticipated this error; the server's journal has it, as acquisition.queue_error."}`;
    default:
      return state.detail || "";
  }
}

/* Retry, where retrying means something: a work that failed or that the queue
 * gave up on. `onRetry` is handed the state the server answers with, so the
 * caller repaints from it. */
export function retryButton(state, title, onRetry) {
  if (state.phase !== "failed" && state.phase !== "gave_up") return null;
  return el("button", {
    class: "action quiet",
    type: "button",
    text: state.phase === "gave_up" ? "Retry" : "Retry now",
    "aria-label": `Retry fetching ${title}`,
    onclick: (event) =>
      attempt(
        event.currentTarget,
        `retry fetching ${title}`,
        () => api(`/api/works/${encodeURIComponent(state.artwork_id)}/acquisition/retry`, { method: "POST" }),
        { then: onRetry },
      ),
  });
}

/* The badge, the sentence, and Retry: the whole line, where a work stands alone. */
export function acquisitionLine(state, title, onRetry) {
  return el("div", { class: "acquisition-line" }, [
    el("p", {}, [acquisitionBadge(state), " ", el("span", { class: "acquisition-sentence", text: acquisitionSentence(state) })]),
    retryButton(state, title, onRetry),
  ]);
}
