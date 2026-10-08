/* What spending costs, said before it is done: a tier on every spending
 * control, and what is left of this month's budget in the sidebar.
 *
 * **The tier is the server's** (`GET /api/estimate`'s `tier`, `spending.cost_tier`):
 * free at zero, then `$`, `$$` or `$$$`. This client never prices anything; an
 * action whose cost nothing estimates is free by construction (a Get, a
 * re-search), and says so with the same mark.
 *
 * **The budget is display only** (`api-contract.md` § `GET /api/budget`): the
 * provider's own figure lags by minutes and nothing gates on it, so the line
 * says what is known and, where the server says why it cannot say more, that.
 */

import { api } from "./api.js";
import { el, fill } from "./render.js";

/* Each tier as a control shows it, and what a reader hears before it. Keyed on
 * `CostTier`, held to it by the vocabulary test, so a fifth tier fails there
 * rather than drawing as its raw token. */
export const TIER_WORDS = {
  free: "Free",
  "$": "$",
  "$$": "$$",
  "$$$": "$$$",
};

/* The mark beside a spending control: glyph-free, the word "Cost" and the
 * tier, as text rather than a badge's box, so it is not mistaken for an act. A tier the
 * client has no word for is drawn as the server spells it rather than dropped,
 * because an unpriced control reads as a free one. */
export function tierMark(tier) {
  const words = TIER_WORDS[tier] || String(tier || "unpriced");
  return el("span", { class: `badge-tier tier-${tier === "free" ? "free" : "spends"}` }, [
    el("span", { text: "Cost: " }),
    el("span", { class: "tier-value", text: words }),
  ]);
}

/* A figure the server sends as a decimal string, to the cent: every cost and
 * estimate the client shows goes through here, so none reads to nine places.
 * A cost above nothing and below half a cent says so rather than reading as
 * free. */
export function dollars(value) {
  const number = Number(value);
  if (value === null || value === undefined || !Number.isFinite(number)) return `$${value}`;
  if (number > 0 && number < 0.005) return "under $0.01";
  return `$${number.toFixed(2)}`;
}

/* What a Get from words costs, as its order of magnitude: "About $0.01",
 * "About $0.10", "About $1". The owner asked for this rather than the bound
 * (2026-10-08): the curator is deciding whether an act is cents, dimes or
 * dollars, and an exact figure reads as a promise the bound is not. Rounded to
 * the nearest power of ten, never below a cent; nothing at all reads "Free". */
export function aboutCost(value) {
  const number = Number(value);
  if (value === null || value === undefined || !Number.isFinite(number)) return `About $${value}`;
  if (number <= 0) return "Free";
  const scale = 10 ** Math.max(-2, Math.round(Math.log10(number)));
  return `About $${scale < 1 ? scale.toFixed(2) : String(scale)}`;
}

/* The caption under Get: its order of magnitude, or that it is not known. An
 * unreadable estimate is said rather than left blank, which would read as free. */
export function getCaption(estimate) {
  return estimate ? aboutCost(estimate.estimated_cost_usd) : "Cost unknown just now";
}

/* The budget's line and, where the server says something more, its note. */
export function budgetWords(budget) {
  switch (budget.state) {
    case "known":
      return { line: `${dollars(budget.remaining_usd)} left this month`, note: null };
    case "configured":
      // A figure the deployment chose and nothing enforces: the note says so.
      return { line: `${dollars(budget.remaining_usd)} left this month`, note: budget.note };
    case "uncapped":
      return {
        line: budget.spent_usd === null ? "No budget set" : `${dollars(budget.spent_usd)} spent this month`,
        note: budget.note,
      };
    case "not_configured":
      return { line: "Nothing spends", note: budget.note };
    default:
      return { line: "Budget unknown", note: budget.note };
  }
}

/* How long a read stands before a navigation asks again. The server keeps its
 * answer a minute too, so asking more often only reads the same figure. */
const FRESH_MS = 60_000;

let readAt = 0;
let reading = null;

/* Paint what is left this month into the sidebar's budget slot. `force` reads
 * again whatever the last read's age, as after an act that spent. */
export async function paintBudget({ force = false } = {}) {
  const slot = document.getElementById("budget");
  if (!slot) return;
  if (!force && (reading || Date.now() - readAt < FRESH_MS)) return;
  readAt = Date.now();
  reading = api("/api/budget").catch(() => {
    // Not kept: the next navigation asks again rather than standing on a failure.
    readAt = 0;
    return { state: "unavailable", note: "What is left of this month's budget could not be read just now." };
  });
  const budget = await reading;
  reading = null;
  const { line, note } = budgetWords(budget);
  fill(slot, el("p", { class: "budget-line", text: line }), note ? el("p", { class: "budget-note", text: note }) : null);
  slot.dataset.state = budget.state;
}
