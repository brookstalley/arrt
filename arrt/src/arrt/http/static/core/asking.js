/* Ask's thread: the curator's words, the agent's reply as it is written, and
 * what the reply offers.
 *
 * One renderer draws a reply from its stream events (3tears' vocabulary, one a
 * line: `stream_start`, `stream_token`, `tool_call_start`, `tool_call_end`, then
 * `stream_end` or `stream_error`), whether they arrive live or are read back
 * from `GET /api/ask/threads/<id>` when the curator returns to the page. A
 * returning page and a live one cannot then draw a reply differently.
 *
 * The thread lives on the server, in memory, and a restart forgets it (the
 * owner, 2026-10-08). This module remembers which thread is open while the
 * app is, and a thread the server has forgotten is replaced by a new one.
 *
 * In `core/` because a screen never imports another, and Ask's screen is
 * `screens/discover.js`. */

import { attempt } from "./acting.js";
import { api, apiLines } from "./api.js";
import { getOne } from "./getting.js";
import { GLYPHS } from "./glyphs.js";
import { captioned, el, fill } from "./render.js";
import { personLink, topicKinds, topicName, workLink, workState } from "./registry.js";
import { prose } from "./reviewing.js";
import { link, refresh } from "./router.js";
import { dollars } from "./spend.js";
import { reactionRow } from "./taste.js";

/* What an empty Ask offers to start from: an artist's neighbours, a mood for a
 * room, a period and a subject. Pressing one fills the box and sends nothing,
 * as *Ask about* does, so the curator can change the words before they spend. */
export const EXAMPLES = [
  "Who paints like Robert and Sonia Delaunay?",
  "Quiet interiors for a pale room",
  "Winter landscapes from the 1500s",
];

/* The open thread's id, kept while the app is open. */
let openThread = null;

/* What a topic's kind is recorded as when the curator reacts to it. Taste
 * calls a period an era; a kind with no entry gets no reactions rather than
 * one recorded under a kind taste does not have. */
const TASTE_KIND = { period: "era", movement: "movement", subject: "subject", medium: "medium" };

/* A Wikidata item in brackets, as the agent is told to cite one. The card
 * shows the item, so the identifier is dropped from the words. */
const CITED = /\s*\[Q[1-9][0-9]*\]/g;

/* The open thread as the server holds it, or an empty one when none is open
 * or the server has forgotten it. Only reads: opening a page writes nothing,
 * and a thread is opened when the curator first says something (`opened`). */
async function thread() {
  if (openThread) {
    try {
      return await api(`/api/ask/threads/${encodeURIComponent(openThread)}`);
    } catch (failure) {
      if (failure.status !== 404) throw failure;
      openThread = null;
    }
  }
  const status = await api("/api/ask");
  return { thread_id: null, available: status.available, turns: [] };
}

async function opened() {
  if (!openThread) openThread = (await api("/api/ask/threads", { method: "POST" })).thread_id;
  return openThread;
}

/* The Ask panel: the thread so far, and the box to say the next thing in.
 * `term` fills the box and sends nothing, as the top bar's "Ask about …" asks. */
export async function askPanel({ term = "" } = {}) {
  const current = await thread();
  const turns = el("div", { class: "ask-turns" });
  // Announced, not shown: the reply's own ending already says how it ended
  // and what it cost, and the steps show it working.
  const status = el("p", { class: "visually-hidden ask-status", role: "status" });
  for (const turn of current.turns) turns.append(turnView(turn.asked, turn.events).node);

  const words = el("textarea", { id: "ask-words", rows: 3 });
  words.value = term;
  const send = el("button", { class: "action primary", type: "button", text: "Ask" });
  const restart = el("button", {
    class: "action quiet",
    type: "button",
    text: "Start over",
    // Writes nothing: the next thing said opens a new thread, and the server
    // drops the old one in time (`THREADS_KEPT`).
    onclick: () => {
      openThread = null;
      fill(turns);
      fill(status);
      words.focus();
    },
  });

  async function ask() {
    const said = words.value.trim();
    if (!said) {
      words.focus();
      return;
    }
    const view = turnView(said, []);
    turns.append(view.node);
    if (examples) examples.remove();
    words.value = "";
    send.disabled = true;
    status.textContent = "Ask is answering…";
    const sendTo = async () =>
      apiLines(`/api/ask/threads/${encodeURIComponent(await opened())}/replies`, (event) => view.take(event), {
        method: "POST",
        body: JSON.stringify({ words: said }),
      });
    try {
      await attempt(send, "ask", async () => {
        try {
          await sendTo();
        } catch (failure) {
          // The server forgot the thread (it restarted, or let the thread go):
          // what it held is gone either way, so the words go to a new one.
          if (failure.status !== 404) throw failure;
          openThread = null;
          await sendTo();
        }
      });
    } finally {
      send.disabled = false;
      status.textContent = view.summary();
    }
  }
  send.addEventListener("click", ask);
  words.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      // The button is disabled while a reply streams; Enter must wait as it does.
      if (!send.disabled) ask();
    }
  });

  const unavailable = current.available
    ? null
    : el("p", { class: "muted", text: "Ask needs an OpenRouter key on the server (OPENROUTER_API_KEY) to answer." });
  // A reply still running when the page opens (the curator left mid-reply and
  // came back): the server refuses a second send until it ends, so the button
  // waits too, and the page fills in when the reply is done.
  const waiting = current.replying
    ? el("p", { class: "muted ask-waiting", text: "Still answering what you last asked. This fills in when it finishes." })
    : null;
  const examples = current.turns.length || !current.available ? null : startingPoints(words);
  const panel = el("div", { class: "panel ask" }, [
    turns,
    waiting,
    unavailable,
    examples,
    el("div", { class: "field" }, [el("label", { for: "ask-words", text: "What are you looking for?" }), words]),
    el("div", { class: "row" }, [
      // The owner ruled that Ask spends without asking and says afterwards
      // what each reply cost (2026-10-08), so there is no estimate here.
      captioned(send, "Searches as it answers; each reply says what it cost"),
      restart,
    ]),
    status,
  ]);
  if (current.replying) {
    send.disabled = true;
    untilReplied(current.thread_id, panel);
  }
  return panel;
}

/* The examples under an empty thread, each a quiet button that fills the box.
 * Gone once something has been said: they are a way in, not a menu. */
function startingPoints(words) {
  const row = el("p", { class: "ask-examples muted" }, ["Try: "]);
  EXAMPLES.forEach((example, index) => {
    if (index) row.append(" · ");
    row.append(
      el("button", {
        class: "link",
        type: "button",
        text: example,
        onclick: () => {
          words.value = example;
          words.focus();
          row.remove();
        },
      }),
    );
  });
  return row;
}

/* How often a page opened mid-reply asks whether the reply has ended. */
const REPLY_POLL_MS = 2000;

/* Repaint Ask once the thread's running reply has ended, unless the page has
 * gone. A read that fails repaints too: the thread may be gone, and the page
 * then shows what the server has. */
async function untilReplied(threadId, panel) {
  for (;;) {
    await new Promise((resolve) => setTimeout(resolve, REPLY_POLL_MS));
    if (!panel.isConnected) return;
    const now = await api(`/api/ask/threads/${encodeURIComponent(threadId)}`).catch(() => null);
    if (!panel.isConnected) return;
    if (!now || !now.replying) {
      refresh();
      return;
    }
  }
}

/* One turn: what the curator said, and the reply drawn from its events. */
function turnView(asked, events) {
  const answer = el("div", { class: "ask-answer" });
  const steps = el("ul", { class: "ask-steps", "aria-label": "What Ask looked at" });
  const offered = el("div", { class: "ask-cards" });
  const ending = el("p", { class: "ask-ending" });
  let text = "";
  let ended = null;

  function take(event) {
    if (event.type === "stream_token") {
      text += event.token;
      fill(answer, ...paragraphs(text));
    } else if (event.type === "tool_call_start") {
      steps.append(
        el("li", { class: "ask-step pending", "data-tool": event.tool_name }, [
          el("span", { class: "glyph", "aria-hidden": true, text: GLYPHS.waiting }),
          event.arguments_summary,
        ]),
      );
    } else if (event.type === "tool_call_end") {
      const step = [...steps.querySelectorAll(".ask-step.pending")].find((each) => each.dataset.tool === event.tool_name);
      if (step) {
        step.classList.remove("pending");
        step.querySelector(".glyph").textContent = event.success ? GLYPHS.good : GLYPHS.problem;
        if (!event.success) step.append(" — it could not answer");
      }
    } else if (event.type === "stream_end") {
      ended = event;
      fill(answer, ...paragraphs(event.content));
      fill(offered, ...(event.metadata.cards || []).map(card));
      fill(ending, costSentence(event.metadata));
    } else if (event.type === "stream_error") {
      ended = event;
      fill(ending, el("span", { class: "error-text", text: event.message }));
    }
  }
  for (const event of events) take(event);

  const node = el("div", { class: "ask-turn" }, [
    el("p", { class: "ask-asked" }, [el("strong", { text: "You: " }), asked]),
    el("div", { class: "ask-reply" }, [steps, answer, offered, ending]),
  ]);
  return {
    node,
    take,
    summary: () => (ended ? ending.textContent : "The reply stopped before it finished."),
  };
}

/* What a reply cost, the provider's own figure. A reply some step of which
 * carried no cost says so rather than reading as cheaper than it was. */
export function costSentence(metadata) {
  const spent = `This reply cost ${dollars(metadata.cost_usd)}`;
  return metadata.uncosted ? `${spent}, and ${metadata.uncosted} of its steps reported no cost.` : `${spent}.`;
}

/* The answer's words as paragraphs and lists, its Markdown as words and links
 * (`prose`), with the cited Wikidata items dropped: each is a card below. */
export function paragraphs(text) {
  const blocks = [];
  let list = null;
  for (const raw of String(text).replace(CITED, "").split("\n")) {
    const line = raw.trim();
    const bullet = /^[-*•]\s+/.exec(line);
    if (!line) {
      list = null;
    } else if (bullet) {
      if (!list) {
        list = el("ul");
        blocks.push(list);
      }
      list.append(el("li", {}, prose(line.slice(bullet[0].length))));
    } else {
      list = null;
      blocks.push(el("p", {}, prose(line.replace(/^#+\s*/, ""))));
    }
  }
  return blocks;
}

/* One thing the reply offers: a work with its mark and Get, an artist or a
 * topic with the reactions. */
function card(item) {
  if (item.kind === "work") {
    const work = { qid: item.qid, title: item.label, image: item.image, held_artwork_ids: item.held ? [item.held] : [] };
    return el("div", { class: "ask-card" }, [
      workState(work),
      workLink(work),
      item.detail ? el("span", { class: "muted", text: item.detail }) : null,
      item.held ? null : getOne(item.qid),
    ]);
  }
  if (item.kind === "artist") {
    return el("div", { class: "ask-card" }, [
      personLink({ qid: item.qid, name: item.label, artist_id: item.held }),
      item.detail ? el("span", { class: "muted", text: item.detail }) : null,
      el("span", { class: "muted", text: item.held ? "In your library" : "Not held" }),
      reactionRow({ kind: "artist", value: item.label }),
    ]);
  }
  const kind = item.kinds.map((each) => TASTE_KIND[each]).find(Boolean);
  return el("div", { class: "ask-card" }, [
    link({ view: "topic", id: item.qid }, { class: "link", text: topicName(item.label, item.qid) }),
    item.kinds.length ? el("span", { class: "muted", text: topicKinds(item.kinds) }) : null,
    kind ? reactionRow({ kind, value: item.label }) : null,
  ]);
}
