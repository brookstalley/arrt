/* What a registry says, as every page shows it.
 *
 * Shared by the Artist page and the Work page, which both show works Wikidata
 * lists, so a work's mark (`workState`; `information-architecture.md` § A work's
 * mark) and the words for an item with
 * no readable name are the same wherever it appears.
 *
 * **Every string from the registry is untrusted text** (`security-model.md` §
 * Direction): it reaches the page through `el`'s `text`, and the only registry
 * value used as a URL is an image the server has already checked is a Commons
 * file. Links out are built here from a QID, never from a URL the registry gave. */

import { el } from "./render.js";
import { go } from "./router.js";

/* A Wikidata item id, as the server checks it: the address of a page about
 * something the library may not hold. A library id is a uuid and never this. */
const QID = /^Q[1-9][0-9]*$/;

export function isQid(id) {
  return QID.test(String(id || ""));
}

/* A link out to Wikidata. The QID is the server's, checked against `Q` and
 * digits, so the address cannot be bent into anything else. */
export function wikidataLink(qid, text) {
  return el("a", { href: `https://www.wikidata.org/wiki/${encodeURIComponent(qid)}`, rel: "noopener noreferrer", target: "_blank", text });
}

/* A registry name, or what to say when it has none we can read. Wikidata's
 * label service answers with the bare QID for an item with no English or
 * language-neutral label (measured on 2026-10-01: a fifth of Rothko's fifty), and
 * an identifier printed where a title belongs reads as a title. */
export function named(label, qid) {
  return label && label !== qid ? label : `No English title (${qid})`;
}

export function lifeDates(person) {
  if (person.born || person.died) return `${person.born || "?"}–${person.died || ""}`;
  return person.lifespan_text || null;
}

/* A registry work's title, opening its page here: the library's own when the
 * library holds it, the registry's otherwise. */
export function workLink(work) {
  const held = work.held_artwork_ids || [];
  return el("button", {
    class: "row-title",
    type: "button",
    text: named(work.title, work.qid),
    onclick: () => (held.length ? go("work", held[0]) : go("work", work.qid)),
  });
}

/* A registry person's name, opening their page here: the library's artist when
 * it holds them, the registry's otherwise. */
export function personLink(person) {
  return el("button", {
    class: "link",
    type: "button",
    text: named(person.name, person.qid),
    onclick: () => go("artist", person.artist_id || person.qid),
  });
}

/* A work's mark wherever registry works are listed — the search typeahead,
 * the results page, the Topic, Artist and Work pages: its picture, in the
 * image style of its state, then glyph and word.
 *
 *   ● *Held*: the library's own thumbnail, and a button to the work.
 *   ◑ *Wanted*: Wikidata's picture, where it has one (the Wanted section).
 *   ◐ *Not held · Image found*: Wikidata's picture.
 *   ○ *Not held* (or `noImage`'s words): no picture.
 *
 * **The image styles are one block in `app.css`** (`.work-pic-held`,
 * `.work-pic-wanted`, `.work-pic-not-held`): the owner's ruling on #172 is to
 * style the three states as images and iterate on what reads clearest, so
 * they sit side by side to be tuned together. The glyph and the word carry
 * the state whatever the picture does — one that fails to load, or none,
 * leaves every state readable (`accessibility-spec.md`).
 *
 * Held wins over wanted: a work wanted and since acquired is held. */
export function workState(work, { noImage = "Not held", opens = true } = {}) {
  const held = work.held_artwork_ids || [];
  if (held.length) {
    // Two held works naming one item is a duplicate the curator should see,
    // not a mark that quietly picks one; it opens the first.
    const words = held.length === 1 ? "Held" : `Held ×${held.length}`;
    const parts = [
      workPicture("held", `/api/works/${encodeURIComponent(held[0])}/thumbnail`),
      el("span", { class: "glyph", text: "●", "aria-hidden": true }),
      el("span", { text: words }),
    ];
    // Not a button where the row it sits in already opens the work: a button
    // inside a search suggestion is a control inside an option, which ARIA
    // forbids and which Tab would land on, and a results row would carry two
    // ways to the same page.
    if (!opens) return el("span", { class: "badge badge-held state-mark" }, parts);
    return el("button", { class: "badge badge-held state-mark", type: "button", onclick: () => go("work", held[0]) }, parts);
  }
  const found = work.image ? `${work.image}?width=96` : null;
  if (work.wanted) return stateBadge("badge-wanted", "◑", "Wanted", found && workPicture("wanted", found));
  if (found) return stateBadge("badge-image-found", "◐", "Not held · Image found", workPicture("not-held", found));
  return stateBadge("badge-not-held", "○", noImage);
}

/* A picture in the image style of a state. In a frame, because the not-held
 * style draws hatching over the picture and an `<img>` cannot carry an
 * overlay of its own. Decorative: the title beside it names the work.
 *
 * A picture that fails to load takes its frame with it, so a held work with
 * no master yet, or a Commons outage, leaves glyph and word rather than a
 * broken-image icon in a styled box. */
function workPicture(kind, src) {
  const picture = el("img", { src, alt: "", loading: "lazy", referrerpolicy: "no-referrer" });
  const frame = el("span", { class: `work-pic work-pic-${kind}`, "aria-hidden": true }, [picture]);
  picture.addEventListener("error", () => frame.remove());
  return frame;
}

/* What the library holds of an artist, or of a work whose page this is, as one
 * mark with one wording wherever it appears: ● *In your library*, ◑ *Wanted*,
 * ◐ *Not held · Image found*, or ○ *Not held*. Glyph, word and the badge's
 * colour, in that order, as every state mark here carries one
 * (`accessibility-spec.md`). A work in a list takes `workState`, which adds
 * its picture. */
export function stateMark({ held = false, wanted = false, image = false } = {}) {
  if (held) return stateBadge("badge-held", "●", "In your library");
  if (wanted) return stateBadge("badge-wanted", "◑", "Wanted");
  if (image) return stateBadge("badge-image-found", "◐", "Not held · Image found");
  return stateBadge("badge-not-held", "○", "Not held");
}

function stateBadge(kind, glyph, words, picture = null) {
  return el("span", { class: `badge ${kind} state-mark` }, [
    picture,
    el("span", { class: "glyph", text: glyph, "aria-hidden": true }),
    el("span", { text: words }),
  ]);
}

/* A topic's name, or what to say when Wikidata has none in English: the label
 * service answers with the bare QID, as it does for a work (`named` above). */
export function topicName(label, qid) {
  return label && label !== qid ? label : `No English name (${qid})`;
}

/* A topic's kinds as a curator reads them, one and many, in the order the
 * server gives them: `GET /api/topics` lists the four kinds period first. */
export const TOPIC_KINDS = {
  period: ["period", "Periods"],
  movement: ["movement", "Movements"],
  subject: ["subject", "Subjects"],
  medium: ["medium", "Media"],
};

/* The kinds a topic is, in words: "movement and period" for Baroque. A kind
 * the client has no word for is shown as the server spells it rather than
 * dropped, so a fifth kind reads oddly instead of vanishing. */
export function topicKinds(kinds) {
  return (kinds || []).map((kind) => (TOPIC_KINDS[kind] ? TOPIC_KINDS[kind][0] : kind)).join(" and ");
}

/* A year as a caption reads it: Wikidata numbers the years before the common
 * era as negatives, and "-500" reads as a typo. */
function year(value) {
  return value < 0 ? `${-value} BCE` : String(value);
}

/* A period's years, "1501–1600", or null when either end is unrecorded. */
export function topicYears(topic) {
  if (topic.start === null || topic.start === undefined || topic.end === null || topic.end === undefined) return null;
  return `${year(topic.start)}–${year(topic.end)}`;
}
