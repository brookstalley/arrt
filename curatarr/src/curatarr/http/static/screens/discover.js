/* Add New — asking for something new.
 *
 * Radarr's Add New, under Artworks (`information-architecture.md` § The *arr
 * layout), at the address `#discover` it had before the rename. It holds the
 * direct intent box and the conversations. The searches they start are listed
 * under Activity — Queue while they work, History once they end — as Radarr
 * lists its downloads there rather than on Add New.
 */

import { api } from "../core/api.js";
import { table } from "../core/badges.js";
import { el, guard, render } from "../core/render.js";
import { go } from "../core/router.js";

export async function viewDiscover(generation) {
  // Both in one round trip: the estimate exists to inform the decision being
  // made in the field beside it, so a screen that fetched it afterwards would
  // be showing a receipt.
  const [estimate, conversations] = await Promise.all([api("/api/estimate"), api("/api/conversations")]);

  const intent = el("textarea", { id: "intent", rows: 3, required: true });
  const start = el("button", {
    class: "action",
    type: "button",
    text: "Start the search",
    onclick: () =>
      guard(async () => {
        const run = await api("/api/runs", {
          method: "POST",
          body: JSON.stringify({ intent: intent.value }),
        });
        go("run", run.run_id);
      }),
  });

  /* The other way in, beside the box rather than instead of it. A curator who
   * already knows what they want types it and searches; one who does not talks
   * first. The direct box does not go away, and this button spends nothing —
   * starting a conversation writes a row and asks no model. */
  const talk = el("button", {
    class: "action quiet",
    type: "button",
    text: "Talk it through first",
    onclick: () =>
      guard(async () => {
        const conversation = await api("/api/conversations", { method: "POST" });
        go("conversation", conversation.conversation.conversation_id);
      }),
  });

  /* The way into what the product has come to believe about the curator.
   *
   * Taste's page is under Settings, and this is a second way in: it sits beside
   * the two ways of asking for something because it is the thing that shapes
   * what comes back — a curator wondering why they keep being offered pale grids
   * looks for the answer where they do the asking. */
  const taste = el("button", {
    class: "action quiet",
    type: "button",
    text: "See what this product thinks you like",
    onclick: () => go("taste"),
  });

  const entry = el("div", { class: "panel" }, [
    el("h3", { text: "Ask for something" }),
    el("div", { class: "field" }, [
      el("label", { for: "intent", text: "What are you looking for?" }),
      intent,
    ]),
    el("p", {
      class: "note",
      // The price before the decision, and what it buys. Stated as a bound
      // rather than a typical figure, because a run may freely use the whole
      // allowance and an estimate it can exceed is not an estimate.
      text: `Asking costs at most $${estimate.estimated_cost_usd}. ${estimate.basis}`,
    }),
    el("div", { class: "row" }, [start, talk, taste]),
  ]);

  const panels = [el("h2", { text: "Add New" }), entry];

  // The conversations, above the searches they seed rather than below them: a
  // thread is where a search comes from, and the list reads in that order.
  // Every row opens the thread it names — there is no summary line yet, because
  // nothing writes one, and a column that was always empty would read as every
  // conversation having got nowhere.
  if (conversations.count) {
    panels.push(
      el("div", { class: "panel" }, [
        el("h3", { text: `Conversations (${conversations.count})` }),
        table(
          "Every conversation, the most recently spoken in first.",
          ["Last said", "Where it got to", "Open"],
          conversations.conversations.map((conversation) => [
            conversation.last_turn_at,
            conversation.summary || "—",
            el("button", {
              class: "action quiet",
              type: "button",
              text: "Open",
              "aria-label": `Open the conversation last spoken in at ${conversation.last_turn_at}`,
              onclick: () => go("conversation", conversation.conversation_id),
            }),
          ]),
        ),
      ]),
    );
  }

  render(generation, ...panels);
}
