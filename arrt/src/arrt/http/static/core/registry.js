/* What a registry says, as every page shows it.
 *
 * Shared by the Artist page and the Work page, which both show works Wikidata
 * lists, so a work's mark (*Held*, *Image found*) and the words for an item with
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

/* Glyph, word and the badge colour, the order every badge here uses. */
export function workState(work) {
  const held = work.held_artwork_ids;
  if (held.length) {
    // Two held works naming one item is a duplicate the curator should see,
    // not a mark that quietly picks one; it opens the first.
    const words = held.length === 1 ? "Held" : `Held ×${held.length}`;
    return el("button", { class: "badge badge-held", type: "button", onclick: () => go("work", held[0]) }, [
      el("span", { class: "glyph", text: "●", "aria-hidden": true }),
      el("span", { text: words }),
    ]);
  }
  if (work.image) {
    return el("span", { class: "badge badge-image-found" }, [
      el("img", { src: `${work.image}?width=96`, alt: "", loading: "lazy", referrerpolicy: "no-referrer", class: "badge-thumb" }),
      el("span", { class: "glyph", text: "◐", "aria-hidden": true }),
      el("span", { text: "Image found" }),
    ]);
  }
  return el("span", { class: "muted", text: "—" });
}
