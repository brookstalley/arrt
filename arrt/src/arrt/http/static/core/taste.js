/* The three reactions, and the one call that records any of them.
 *
 * **In `core/` because two screens perform the identical act.** A curator
 * reacting to an artist Ask offers and a curator correcting a row on the Taste
 * screen are writing the same judgment about the same thing, and a copy of this
 * table in each would be two products: a "not this" that means one thing in a
 * thread and something else on the screen listing what was recorded is a taste
 * model nobody can predict. `screens/` modules never import each other
 * (`architecture.md` § Components & Responsibilities), so shared vocabulary
 * lives here or it lives twice.
 *
 * **This is where the two-fields rule is paid for.** "Tell me more" is not a
 * third warmth — it is `cool` with `open_to_more` still true, which is the
 * curator's own "meh on Magritte, but open to learning more". A single warmth
 * score would render that as a low number indistinguishable from "never show me
 * this again", and the honest lukewarm reaction would silently blacklist an
 * artist they explicitly asked to keep hearing about. Declining is the only one
 * of the three that closes the door.
 */

import { attempt } from "./acting.js";
import { api } from "./api.js";
import { el } from "./render.js";

/* Each reaction as the pair of fields it writes.
 *
 * Keyed by the words the interface uses, so the control's label and the judgment
 * it records cannot come apart. A fourth reaction is an entry here and a button
 * wherever the three are drawn — never a fourth spelling of one of these. */
export const REACTIONS = {
  "more like this": { sentiment: "loves", open_to_more: true },
  "not this": { sentiment: "declines", open_to_more: false },
  "tell me more": { sentiment: "cool", open_to_more: true },
};

/* The reactions an Ask card offers: two, where an Artist page and Taste's rows
 * offer all three. A reply can name fifteen artists, and three buttons a card
 * made the grid buttons with names on rather than pictures (the owner,
 * 2026-10-09). Taste's help reads this list, so it names what the cards carry. */
export const CARD_REACTIONS = ["more like this", "not this"];

/* Record one reaction against one thing, as the curator's own words.
 *
 * **Always `stated`, whoever is reacting and whatever the row said before.** A
 * reaction is the curator saying so directly — that is the whole reason the
 * controls exist rather than leaving the model to infer taste from prose — and
 * writing it as anything weaker would let the product go on attributing to a
 * model a judgment the person made by hand.
 *
 * An upsert on (`kind`, `value`), so there is nothing to fetch first and
 * pressing a reaction twice records one judgment. */
export function recordReaction({ kind, value, reaction }) {
  return api("/api/affinities", {
    method: "POST",
    body: JSON.stringify({
      kind,
      value,
      derivation: "stated",
      ...REACTIONS[reaction],
    }),
  });
}

/* The reactions as a row of controls, for an artist or topic Ask offers.
 * `only` offers a subset, in its order: Ask's cards carry `CARD_REACTIONS`, and
 * *tell me more* is on the Artist page and Taste's rows, where there is room.
 *
 * **The three record taste and stay where they are.** They write an `Affinity`
 * with `derivation='stated'` — the curator saying so directly — rather than
 * leaving the model to infer one from prose, and each is a different pair of the
 * two fields taste is held in. "Tell me more" is the one worth reading twice: it
 * is cool *and still open*, which is the sentence the two-field design exists
 * for.
 *
 * The page does not repaint after one. The judgment is recorded elsewhere and
 * nothing in the transcript changes — a thread that redrew itself under a
 * curator who pressed a button beside a picture would move the picture. What
 * confirms it is the control's own state, below. */
export function reactionRow({ kind, value }, { only = Object.keys(REACTIONS) } = {}) {
  return el(
    "div",
    // Announced rather than only shown: the confirmation below is a change of
    // label on a control the curator has just left, and a reader who is not
    // looking at it would otherwise get no acknowledgement at all.
    { class: "reactions", "aria-live": "polite" },
    only.map((reaction) => {
      const control = el("button", {
        class: "action quiet",
        type: "button",
        text: reaction,
        // The value in the accessible name, because the visible label is shared
        // by every card on the page: a screen reader moving through a reply
        // that named three artists would otherwise hear "not this" nine times
        // with nothing saying what "this" is.
        "aria-label": `${reaction}: ${value}`,
        onclick: () =>
          attempt(control, `record ${reaction} for ${value}`, () => recordReaction({ kind, value, reaction }), {
            then: () => {
              // Said, not merely styled, and said in the past tense so it reads
              // as a record rather than as an offer. `aria-live` on the row is
              // what carries it to a reader who is not looking at the button.
              control.textContent = `${reaction} — recorded`;
              control.disabled = true;
            },
          }),
      });
      return control;
    }),
  );
}
