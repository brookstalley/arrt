/* Ask — asking for something in words.
 *
 * Where Radarr's Add New stood, under Artworks, at the address `#discover` it
 * has had since before the *arr labels; ruling 3 of `ia-proposal.md` dissolved
 * Add New into Get, an action on a selection, and this page, where a direction is
 * asked for or talked through. It holds the direct intent box, on top as the
 * owner ruled, and the conversations. The searches they start are listed under
 * Activity — Queue while they work, History once they end. */

import { attempt } from "../core/acting.js";
import { api } from "../core/api.js";
import { table } from "../core/badges.js";
import { el, render } from "../core/render.js";
import { go, link } from "../core/router.js";
import { state } from "../core/state.js";

export async function viewDiscover(generation) {
  // Both in one round trip: the estimate exists to inform the decision being
  // made in the field beside it, so a screen that fetched it afterwards would
  // be showing a receipt.
  const [estimate, conversations] = await Promise.all([api("/api/estimate"), api("/api/conversations")]);

  const intent = el("textarea", { id: "intent", rows: 3, required: true });
  // A search handed over from the top bar's "Ask about …" row, as Sonarr hands
  // its term to Add New. Filled in and never started: a search here
  // is a paid run, and the curator presses the button beside its price.
  intent.value = state.params.term || "";
  const start = el("button", {
    class: "action",
    type: "button",
    text: "Start the search",
    onclick: (event) =>
      attempt(event.currentTarget, "start the search", async () => {
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
    onclick: (event) =>
      attempt(event.currentTarget, "start a conversation", async () => {
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
  const taste = link({ view: "taste" }, { class: "action quiet", text: "See what this product thinks you like" });

  const entry = el("div", { class: "panel" }, [
    el("h2", { text: "Ask for something" }),
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

  const panels = [el("h1", { text: "Ask" }), entry];

  // The conversations, where the searches listed under Activity come from.
  // Every row opens the thread it names — there is no summary line yet, because
  // nothing writes one, and a column that was always empty would read as every
  // conversation having got nowhere.
  if (conversations.count) {
    panels.push(
      el("div", { class: "panel" }, [
        el("h2", { text: `Conversations (${conversations.count})` }),
        table(
          "Every conversation, the most recently spoken in first.",
          ["Last said", "Where it got to", "Open"],
          conversations.conversations.map((conversation) => [
            conversation.last_turn_at,
            conversation.summary || "—",
            link({ view: "conversation", id: conversation.conversation_id }, { class: "action quiet", text: "Open", "aria-label": `Open the conversation last spoken in at ${conversation.last_turn_at}` }),
          ]),
        ),
      ]),
    );
  }

  render(generation, ...panels);
}
