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
import { formatRoute } from "./route.js";

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

/* What each kind of spending is called on the Spend page, keyed on
 * `SpendCategory` (`persistence/discovery_records.py`). A kind this client has
 * no word for is shown as the server spells it rather than dropped, as an
 * unpriced control's tier is, because a row left off is money left off the page. */
export const CATEGORY_WORDS = {
  discovery_tokens: "Proposing works",
  web_search: "Searching the web",
  image_research: "Searching again for images",
  mat_color_vision: "Choosing mat colours",
  conversation_tokens: "Earlier conversations, retired",
  ask_tokens: "Ask's replies",
};

export function categoryWords(category) {
  return CATEGORY_WORDS[category] || String(category);
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

/* The budget's line, as the way to where spending is checked: System › Spend,
 * which lists each month's spending, where it went, which Gets spent it, and
 * the calls whose cost nobody was told.
 *
 * A plain anchor, not `link()`: the router imports the sidebar, which imports
 * this module, and the sidebar closes its own drawer when this is followed
 * (`installDrawer`), as it does for its other links. Without a modifier the
 * click is the browser's, which changes the address and so goes through the
 * router's `hashchange` like any typed address; a modifier opens a new tab. */
function budgetLink(line) {
  return el("a", { class: "budget-line", href: formatRoute("spend"), text: line });
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
  fill(slot, budgetLink(line), note ? el("p", { class: "budget-note", text: note }) : null);
  slot.dataset.state = budget.state;
}
