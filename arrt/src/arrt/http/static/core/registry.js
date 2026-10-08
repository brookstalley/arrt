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

import { GLYPHS } from "./glyphs.js";
import { el } from "./render.js";
import { link } from "./router.js";

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
  return link({ view: "work", id: held.length ? held[0] : work.qid }, { class: "row-title", text: named(work.title, work.qid) });
}

/* A listed work's title cell: its link, and under it who made it (where the
 * list has a *By* column) and its year, both shown only on a phone. There the
 * By and Year columns fold away (`byCell`, `yearCell`), so the row keeps room
 * for the work's picture without scrolling sideways (`app.css`). The class is
 * what lets a title longer than a phone is wide break anywhere. */
export function workCell(work, { by = null } = {}) {
  const known = work.year !== null && work.year !== undefined;
  return el("td", { class: "work-title" }, [
    workLink(work),
    by ? el("span", { class: "by-under" }, by) : null,
    known ? el("span", { class: "year-under", text: year(work.year) }) : null,
  ]);
}

/* A listed work's By cell: hidden on a phone, where its makers sit under the title. */
export function byCell(by) {
  return el("td", { class: "by-col" }, by);
}

/* A listed work's Year cell: hidden on a phone, where the year sits under the
 * title instead (`workCell`). */
export function yearCell(work) {
  return el("td", { class: "year-col", text: work.year === null || work.year === undefined ? "—" : year(work.year) });
}

/* The heading row of a list of registry works. The two columns a phone folds
 * away are named here by their headings rather than marked by each caller,
 * because every caller heads them with these words. */
const FOLDED = { By: "by-col", Year: "year-col" };

export function listHeadings(names) {
  return el("tr", {}, names.map((name) => el("th", { scope: "col", class: FOLDED[name] || null, text: name })));
}

/* A registry person's name, opening their page here: the library's artist when
 * it holds them, the registry's otherwise. */
export function personLink(person) {
  return link({ view: "artist", id: person.artist_id || person.qid }, { class: "link", text: named(person.name, person.qid) });
}

/* The Commons rendering a listed work's picture is asked at. Commons serves
 * fixed widths only and answers any other with the next one up; 250 stays
 * sharp at the 5rem a list draws it at on a 3x screen (`app.css`,
 * `.artist-works .work-pic`). The search results and typeahead draw the same
 * picture smaller and share it, so a work shown in both is one download. */
const FOUND_WIDTH = 250;

/* A work's mark wherever registry works are listed — the search typeahead,
 * the results page, the Topic, Artist and Work pages: its picture, in the
 * image style of its state, then glyph and word.
 *
 *   ● *Held*: the library's own thumbnail, and a link to the work.
 *   ◔ *Waiting for review*: a run found it and nobody has judged it yet
 *     (`in_review`); a link to that review, unless `inOption`.
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
 * Held wins over wanted: a work wanted and since acquired is held.
 *
 * **`grouped`, where the list sits under a *Not held* heading** (the search
 * results and the dropdown): the words say only what the heading does not, so
 * ◐ *Image found*, and ○ *No image known* as the Topic page says it. "Not held"
 * on every row of a group headed *Not held* was noise (the owner, 2026-10-06).
 * `noImage`, where given, is the no-picture word whichever.
 *
 * **`inOption`, where the mark sits inside a search suggestion**: nothing in
 * it is a link, since a control inside an option is what ARIA forbids. Waiting
 * for review links to a page other than the row's own, so the row's `opens`
 * does not stand in for it. */
export function workState(work, { noImage = null, opens = true, grouped = false, inOption = false } = {}) {
  const held = work.held_artwork_ids || [];
  if (held.length) {
    // Two held works naming one item is a duplicate the curator should see,
    // not a mark that quietly picks one; it opens the first.
    const words = held.length === 1 ? "Held" : `Held ×${held.length}`;
    const parts = [
      workPicture("held", `/api/works/${encodeURIComponent(held[0])}/thumbnail`),
      el("span", { class: "glyph", text: GLYPHS.good, "aria-hidden": true }),
      el("span", { text: words }),
    ];
    // Not a link where the row it sits in already opens the work: a link
    // inside a search suggestion is a control inside an option, which ARIA
    // forbids and which Tab would land on, and a results row would carry two
    // ways to the same page.
    if (!opens) return el("span", { class: "badge badge-held state-mark" }, parts);
    return link({ view: "work", id: held[0] }, { class: "badge badge-held state-mark" }, parts);
  }
  if (work.in_review) return reviewMark(work.in_review, { inOption });
  const found = work.image ? `${work.image}?width=${FOUND_WIDTH}` : null;
  if (work.wanted) return stateBadge("badge-wanted", GLYPHS.wanted, "Wanted", found && workPicture("wanted", found));
  if (found) return stateBadge("badge-image-found", GLYPHS.imageFound, grouped ? "Image found" : "Not held · Image found", workPicture("not-held", found));
  return stateBadge("badge-not-held", GLYPHS.none, noImage || (grouped ? "No image known" : "Not held"));
}

/* Whether a registry row can be ticked for a Get: not when the library holds
 * it, and not when a run already found it and it waits for a verdict, which a
 * second Get would pay for again (the server skips it too, as `in_review`). */
export function gettable(work) {
  return !(work.held_artwork_ids || []).length && !work.in_review;
}

/* *Waiting for review*, for a registry work or artist a run proposed and
 * nobody has judged: glyph, words, and the way to the review it waits on. */
export function reviewMark(inReview, { inOption = false } = {}) {
  const parts = [el("span", { class: "glyph", text: GLYPHS.forReview, "aria-hidden": true }), el("span", { text: "Waiting for review" })];
  if (inOption) return el("span", { class: "badge badge-in-review state-mark" }, parts);
  return link({ view: "review", id: inReview.run_id }, { class: "badge badge-in-review state-mark" }, parts);
}

/* A picture in the image style of a state. In a frame, which carries the
 * state's outline and keeps the box square while the picture inside it keeps
 * its own aspect. Decorative: the title beside it names the work.
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
  if (held) return stateBadge("badge-held", GLYPHS.good, "In your library");
  if (wanted) return stateBadge("badge-wanted", GLYPHS.wanted, "Wanted");
  if (image) return stateBadge("badge-image-found", GLYPHS.imageFound, "Not held · Image found");
  return stateBadge("badge-not-held", GLYPHS.none, "Not held");
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
export function year(value) {
  return value < 0 ? `${-value} BCE` : String(value);
}

/* A period's years, "1501–1600", or null when either end is unrecorded. */
export function topicYears(topic) {
  if (topic.start === null || topic.start === undefined || topic.end === null || topic.end === undefined) return null;
  return `${year(topic.start)}–${year(topic.end)}`;
}
