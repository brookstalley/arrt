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
import { captioned, el, render } from "../core/render.js";
import { go, link } from "../core/router.js";
import { getCaption } from "../core/spend.js";
import { dated } from "../core/dates.js";
import { state } from "../core/state.js";

export async function viewDiscover(generation) {
  // Both in one round trip: the estimate exists to inform the decision being
  // made in the field beside it, so a screen that fetched it afterwards would
  // be showing a receipt. An estimate that cannot be read leaves the page
  // usable and says so under Get, rather than taking the whole page down.
  const [estimate, conversations] = await Promise.all([
    api("/api/estimate").catch((failure) => {
      console.warn(`The estimate for a Get could not be read: ${failure.message}`);
      return null;
    }),
    api("/api/conversations"),
  ]);

  const intent = el("textarea", { id: "intent", rows: 3, required: true });
  // Words handed over from the top bar's "Ask about …" row, as Sonarr hands
  // its term to Add New. Filled in and never started: a Get here spends, and
  // the curator presses the button beside its price.
  intent.value = state.params.term || "";
  const start = el("button", {
    // The one filled act on the page, with what it costs under it (below):
    // "Get", as every spending request is called (`ia-proposal.md` § Objects).
    class: "action primary",
    type: "button",
    text: "Get",
    "aria-label": "Get what you asked for",
    onclick: (event) =>
      attempt(event.currentTarget, "start the Get", async () => {
        const run = await api("/api/runs", {
          method: "POST",
          body: JSON.stringify({ intent: intent.value }),
        });
        go("get", run.run_id);
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

  const entry = el("div", { class: "panel" }, [
    el("h2", { text: "Ask for something" }),
    el("div", { class: "field" }, [
      el("label", { for: "intent", text: "What are you looking for?" }),
      intent,
    ]),
    // Each act with one line under it: Get, roughly what it costs, as an order
    // of magnitude (the owner's ruling, 2026-10-08); talking, that it is free
    // to start. Only starting is free — every reply is a model call and is
    // priced beside its own button in the thread.
    el("div", { class: "row" }, [
      captioned(start, getCaption(estimate)),
      captioned(talk, "Free to start; each reply shows its cost"),
    ]),
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
            el("time", { datetime: conversation.last_turn_at, text: dated(conversation.last_turn_at) }),
            conversation.summary || "—",
            link({ view: "conversation", id: conversation.conversation_id }, { class: "action quiet", text: "Open", "aria-label": `Open the conversation last spoken in ${dated(conversation.last_turn_at)}` }),
          ]),
        ),
      ]),
    );
  }

  render(generation, ...panels);
}
