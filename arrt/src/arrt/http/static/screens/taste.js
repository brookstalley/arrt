/* Taste — what the product has come to believe about the curator, correctable.
 *
 * **A page under Settings, listed last**, where Radarr keeps the profiles that rank what it
 * finds (`information-architecture.md` § The *arr layout). Also reached from a
 * suggestion's "why am I seeing this?".
 *
 * **Every row shows where its judgment came from, and that is the screen's whole
 * reason to exist.** A taste model that cannot say where a judgment came from is
 * one the curator can only argue with, never fix — and it is the *derivation*,
 * not the judgment, that this product will change its mind about as the
 * eliciting prompt improves. So the derivation is never hidden behind a hover or
 * folded into a tooltip: it sits under the row it qualifies, in the same words
 * the tool surface uses, with the model's own rationale beside it where there is
 * one.
 *
 * Unlike the Work screen's facets, **no derivation here is the silent default**.
 * That screen marks only `sourced` because inferred is the norm there and
 * marking every row would train a reader to skip the one label that matters.
 * Here all three are common, they are claims of different strength about the
 * same person, and a row whose provenance the reader has to infer from an
 * absence is exactly the row they cannot correct with confidence.
 *
 * TEXT IS SET WITH textContent, NEVER innerHTML — the rule is at `core/render.js`
 * and an affinity's value is a name a model produced.
 */

import { attempt } from "../core/acting.js";
import { api } from "../core/api.js";
import { confirmAct } from "../core/confirm.js";
import { GLYPHS } from "../core/glyphs.js";
import { el, emptyState, render } from "../core/render.js";
import { backRow, link, refresh } from "../core/router.js";
import { CARD_REACTIONS, REACTIONS, recordReaction } from "../core/taste.js";

/* The six kinds, in the words a curator reads rather than the enum's.
 *
 * The same closed vocabulary a work's facets are filed under — one set of terms
 * for what a work *is* and what the curator *likes*, which is the whole reason
 * the enum is shared. A seventh kind with no entry here would render as its own
 * token, which a unit test reads this map against the enum to prevent. */
const TASTE_KIND_WORDS = {
  artist: "Artists",
  movement: "Movements",
  era: "Eras",
  subject: "Subjects",
  medium: "Media",
  palette: "Palettes",
};

/* How warmly a thing is held, said as the curator would say it.
 *
 * Four values and not a number: warmth is only half of a judgment, and
 * `open_to_more` carries the other half. "Meh on Magritte, but open to learning
 * more" is two facts, and one scalar renders it as a low value indistinguishable
 * from "never show me this again". */
const SENTIMENT_WORDS = {
  loves: "Loves",
  likes: "Likes",
  cool: "Cool on",
  declines: "Declines",
};

/* A shape per sentiment, because colour is never the sole carrier of state.
 *
 * Four distinguishable glyphs rather than four fills: `accessibility-spec.md`
 * binds this whole surface, and a warmth scale is exactly the thing a first
 * draft renders as a colour ramp and a curator with the lights down cannot
 * read. The word is beside the glyph in every case, so neither is load-bearing
 * alone. */
const SENTIMENT_GLYPHS = {
  loves: GLYPHS.picked,
  likes: GLYPHS.liked,
  cool: GLYPHS.cool,
  declines: GLYPHS.no,
};

/* Where a judgment came from, in a sentence rather than a token.
 *
 * Each says what the claim *is*, because that is what a curator deciding whether
 * to overrule it needs. "inferred" alone tells them nothing about whether the
 * product is repeating them or guessing at them. */
const DERIVATION_WORDS = {
  stated: "You said this",
  inferred: "Read out of something you said",
  observed: "Read from what you accepted and rejected",
};

export async function viewTaste(generation) {
  const taste = await api("/api/affinities");
  paint(taste, generation);
}

function paint(taste, generation) {
  const panels = [backRow(), el("h1", { text: "Taste" }), howTasteIsRecorded()];

  if (!taste.count) {
    panels.push(empty());
    render(generation, ...panels);
    return;
  }

  panels.push(
    el("p", {
      class: "muted",
      text:
        "Every judgment here says where it came from. Change one that is wrong, or forget it entirely — " +
        "what the product knows about you is yours to correct.",
    }),
  );
  // Grouped by kind, in vocabulary order rather than in whatever order the
  // groups happened to be populated: the six are a fixed set and a page whose
  // sections move between visits is one a curator has to re-read each time.
  for (const kind of Object.keys(TASTE_KIND_WORDS)) {
    const held = taste.affinities.filter((affinity) => affinity.kind === kind);
    if (held.length) panels.push(group(kind, held));
  }
  render(generation, ...panels);
}

/* Every way a judgment gets here, each named by the words on its control.
 *
 * Said on the empty page and the full one alike, because a curator wondering
 * why a judgment is here, or how to add one, needs the list either way. Each
 * control is named as it reads where it is: Ask's card reactions
 * (`CARD_REACTIONS`) are lower-case, and an artist's page says *More like this*,
 * *Not this* and *Tell me more*. The corrections on this page are listed too, since a correction
 * records a judgment of its own (`core/taste.js`). An assistant writes through
 * `art_taste`, which records what it read out of something the curator said. */
/* "a or b", "a, b or c": the controls a line names, in its order. */
function either(parts) {
  return parts.flatMap((part, index) => (index === 0 ? [part] : [index === parts.length - 1 ? " or " : ", ", part]));
}

function howTasteIsRecorded() {
  const control = (words) => el("em", { text: words });
  return el("div", { class: "taste-help" }, [
    el("p", { class: "muted", text: "What the product has come to think you like. A judgment is recorded when you:" }),
    el("ul", { class: "muted" }, [
      el("li", {}, ["react to an artist or topic Ask offers, with ", ...either(CARD_REACTIONS.map(control)), ";"]),
      el("li", {}, [
        "press ",
        control("More like this"),
        ", ",
        control("Not this"),
        " or ",
        control("Tell me more"),
        " on an artist's page;",
      ]),
      el("li", {}, [
        "correct one here, with ",
        control("More of this"),
        ", ",
        control("Not this"),
        " or ",
        control("Keep showing me"),
        ";",
      ]),
      el("li", {}, ["or tell an assistant connected to Arrt, which records what it read out of what you said."]),
    ]),
  ]);
}

/* Nothing known yet, and what would create some.
 *
 * The IA's rule for this screen's empty state, and it is not the same as "no
 * results": there is nothing to clear and no filter to blame. What there is, is
 * a thing the curator has not done yet, so the state names it and offers the
 * way. */
function empty() {
  return emptyState(
    "Nothing is known about your taste yet.",
    "Any of the ways above records the first judgment; asking in Ask is the quickest.",
    [link({ view: "discover" }, { class: "action", text: "Ask for something" })],
  );
}

function group(kind, affinities) {
  return el("div", { class: "panel" }, [
    el("h2", { text: TASTE_KIND_WORDS[kind] || kind }),
    el(
      "ul",
      { class: "taste-list" },
      affinities.map((affinity) => row(affinity)),
    ),
  ]);
}

function row(affinity) {
  const sentiment = SENTIMENT_WORDS[affinity.sentiment] || affinity.sentiment;
  return el("li", { class: "affinity", "data-affinity": affinity.affinity_id, "data-value": affinity.value }, [
    el("p", { class: "affinity-judgment" }, [
      el("span", { class: "glyph", "aria-hidden": true, text: SENTIMENT_GLYPHS[affinity.sentiment] || "·" }),
      el("span", { text: ` ${sentiment} ` }),
      el("strong", { text: affinity.value }),
    ]),
    el("p", {
      class: "muted",
      // Said as a sentence rather than as a checkbox's state, because the two
      // fields answer different questions and a reader skimming a row has to be
      // able to tell "keep showing me this" from "I like it".
      text: affinity.open_to_more
        ? "Still open to being shown more of this."
        : "Not to be offered again unless you say otherwise.",
    }),
    provenance(affinity),
    el("div", { class: "row" }, [
      ...Object.keys(REACTIONS).map((reaction) =>
        el("button", {
          class: "action quiet",
          type: "button",
          text: correctionLabel(reaction),
          // The value is in the accessible name because the visible label is
          // shared by every row on the page: a screen reader moving through the
          // list would otherwise hear "not this" nine times with no referent.
          "aria-label": `${correctionLabel(reaction)}: ${affinity.value}`,
          onclick: (event) => correct(event.currentTarget, affinity, reaction),
        }),
      ),
      el("button", {
        class: "action quiet",
        type: "button",
        text: "Forget this",
        "aria-label": `Forget what this product knows about ${affinity.value}`,
        onclick: (event) => forget(event.currentTarget, affinity),
      }),
    ]),
  ]);
}

/* The verb a correction control carries.
 *
 * The reactions are phrased for a picture in a thread — "more like this" — and
 * here there is no picture, so the same act is phrased against the name. The
 * mapping is one place rather than a second table of labels, so a fourth
 * reaction cannot arrive on one surface and not the other. */
function correctionLabel(reaction) {
  if (reaction === "more like this") return "More of this";
  if (reaction === "not this") return "Not this";
  return "Keep showing me";
}

/* The derivation, and the model's own account where there is one. An inferred
 * judgment came from a conversation the product no longer keeps, so its
 * rationale is the evidence there is, and it is what this says. */
function provenance(affinity) {
  return el("div", { class: "affinity-provenance" }, [
    el("p", { class: "muted", text: DERIVATION_WORDS[affinity.derivation] || affinity.derivation }),
    affinity.rationale ? el("p", { class: "muted", text: `“${affinity.rationale}”` }) : null,
  ]);
}

/* Correct a judgment. The same act a reaction in Ask performs.
 *
 * Through the shared writer rather than a POST of this screen's own, so a
 * correction here and a reaction there cannot come to mean different things. A
 * correction made on this screen is the curator saying so directly, and the
 * provenance it replaces is exactly what they are overruling.
 *
 * Repainted by re-reading rather than from the response, because a correction
 * can move a row between groups — changing what this whole page shows, not one
 * row of it. */
function correct(control, affinity, reaction) {
  return attempt(control, `record ${reaction} for ${affinity.value}`, () => recordReaction({ kind: affinity.kind, value: affinity.value, reaction }), {
    then: () => refresh(),
  });
}

async function forget(control, affinity) {
  const agreed = await confirmAct({
    title: `Forget ${affinity.value}?`,
    // The consequence, not the row count, and the distinction is the one this
    // screen exists to make: after this the product knows *nothing* about the
    // thing, which is a different state from being told to leave it alone.
    consequence:
      `This product will stop knowing anything about ${affinity.value} — it will neither offer it nor avoid ` +
      "it, and nothing brings the judgment back. To keep it and simply not be shown more, use “Not this” instead.",
    confirmLabel: "Forget it",
  });
  if (!agreed) return;
  await attempt(control, `forget ${affinity.value}`, () => api(`/api/affinities/${encodeURIComponent(affinity.affinity_id)}`, { method: "DELETE" }), {
    then: () => refresh(),
  });
}
