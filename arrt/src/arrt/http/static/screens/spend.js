/* Spend — what was spent, month by month, and what nobody could say the cost of.
 *
 * **A page under System**, listed there as Status is (`information-architecture.md`
 * § Direction: a page belongs to a section and is listed beneath it). It is
 * reached from the sidebar's budget line, from Status, and from its own entry.
 *
 * **Every figure is said in the server's sentence** (`summary`, which is
 * `SpendTotal.words`): "$0.42", or "at least $0.42, and 2 calls whose cost is
 * unknown" when a call was sent and never said what it cost. This page formats
 * no number from `cost_usd` itself, so it cannot say a month cost less than the
 * server knows it did.
 *
 * **Nothing here limits spending, and nothing says it does.** The ceiling is the
 * provider's, set on the key; this page is what was spent and what is not
 * known, and it has no control to set a limit.
 *
 * Each month lists, apart from one another: the calls whose cost is unknown
 * (when, what, which model and which Get, so they can be set against the
 * provider's own activity page), what the month was spent on, and which Gets
 * spent it. A Get's row is its own calls in the month; its whole cost, retries
 * included, is on its page.
 *
 * TEXT IS SET WITH textContent, NEVER innerHTML — the rule is at `core/render.js`.
 * A Get's words are the household's own, and are still only ever text.
 */

import { api } from "../core/api.js";
import { table } from "../core/badges.js";
import { stamp } from "../core/dates.js";
import { el, render } from "../core/render.js";
import { runKind } from "../core/runs.js";
import { link } from "../core/router.js";
import { categoryWords } from "../core/spend.js";

const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

/* The UTC month the server counted by, named: "November 2026". */
function monthName(month) {
  return `${MONTH_NAMES[month.month - 1]} ${month.year}`;
}

function getTitle(get) {
  return get.intent || runKind(get);
}

function getLink(runId, title) {
  return link({ view: "get", id: runId }, { class: "link row-link", text: title });
}

function unknownCalls(month) {
  const titles = new Map(month.gets.map((get) => [get.run_id, getTitle(get)]));
  return el("section", { class: "spend-unknown", "aria-labelledby": `unknown-${month.year}-${month.month}` }, [
    el("h3", { id: `unknown-${month.year}-${month.month}`, text: "Calls whose cost is unknown" }),
    el("p", {
      class: "muted",
      text:
        "These calls were sent and never said what they cost, so the provider may have billed them. " +
        "Arrt cannot settle them, which is why the month's total says \"at least\".",
    }),
    table(
      `The calls in ${monthName(month)} whose cost is unknown, newest first.`,
      ["When", "What", "Model", "Get"],
      month.unknown_calls.map((call) => [
        el("time", stamp(call.occurred_at)),
        categoryWords(call.category),
        call.model_id,
        call.run_id ? getLink(call.run_id, titles.get(call.run_id) || "Get") : "Not part of a Get",
      ]),
      { stacked: true },
    ),
  ]);
}

function categories(month) {
  return el("section", { class: "spend-categories" }, [
    el("h3", { text: "What it was spent on" }),
    table(
      `What each kind of spending cost in ${monthName(month)}.`,
      ["What", "Calls", "Cost"],
      month.categories.map((each) => [categoryWords(each.category), String(each.calls), each.summary]),
      { stacked: true },
    ),
  ]);
}

function gets(month) {
  return el("section", { class: "spend-gets" }, [
    el("h3", { text: "Which Gets spent it" }),
    table(
      `The Gets that spent in ${monthName(month)}, newest first, each with its own calls that month.`,
      ["Get", "Started", "Calls", "Cost"],
      month.gets.map((get) => [getLink(get.run_id, getTitle(get)), el("time", stamp(get.started_at)), String(get.calls), get.summary]),
      { stacked: true },
    ),
  ]);
}

function monthPanel(month, current) {
  const spent = month.categories.length > 0;
  return el("section", { class: "panel spend-month", "data-month": `${month.year}-${String(month.month).padStart(2, "0")}` }, [
    el("h2", { text: monthName(month) }),
    el("p", { class: "spend-total", text: month.summary }),
    spent ? null : el("p", { class: "muted", text: current ? "Nothing has been spent this month." : "Nothing was spent." }),
    month.unknown_calls.length ? unknownCalls(month) : null,
    spent ? categories(month) : null,
    month.gets.length ? gets(month) : null,
  ]);
}

export async function viewSpend(generation) {
  const history = await api("/api/spend");
  const months = Array.isArray(history.months) ? history.months : [];
  const now = months[0];
  render(
    generation,
    el("h1", { text: "Spend" }),
    now ? el("p", { class: "page-facts", text: `${monthName(now)} so far: ${now.summary}.` }) : null,
    el("p", {
      class: "muted",
      text:
        "What the provider reported each call cost, kept for the record, by calendar month in UTC, the month the provider's own " +
        "limit resets on. Arrt sets no limit and enforces none: a limit is the provider's, set on the key.",
    }),
    ...months.map((month, index) => monthPanel(month, index === 0)),
    history.older_months > 0
      ? el("p", { class: "muted spend-older", text: `${history.older_months} earlier ${history.older_months === 1 ? "month" : "months"} that spent something ${history.older_months === 1 ? "is" : "are"} not listed.` })
      : null,
  );
}
