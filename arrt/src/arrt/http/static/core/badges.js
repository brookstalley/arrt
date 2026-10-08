/* The pieces more than one screen draws: badges, fact lists, tables, notes.
 *
 * The rule for what belongs here is exactly "two screens use it". A presenter
 * with one caller stays in that caller's module, because a `core/` that collects
 * everything shared-looking becomes the single file the split exists to end.
 *
 * **A badge always carries a glyph and a word beside its colour**, so every
 * state survives greyscale, colour blindness, and a dimmed room —
 * `accessibility-spec.md`'s rule that colour is never the sole carrier.
 */

import { agree } from "./counting.js";
import { el } from "./render.js";

const FIT_GLYPHS = {
  native: "●", // filled circle
  matted_small: "◇", // open diamond
  below_floor: "▲", // triangle
};

const FIT_WORDS = {
  native: "native",
  matted_small: "matted small",
  below_floor: "below floor",
};

/* A picture's own size, in pixels, as the curator judges it: a scan on a
 * review card, a registry work's picture on its page.
 *
 * **Pixels, and no inches** (the owner's ruling, 2026-10-02). The size on the
 * wall depends on which panel the work hangs on, and the one figure this server
 * could give — the long edge on the single panel it is configured for, after
 * the mat — read as a fact about the picture to somebody who did not know that.
 * A per-wall fit comes back with per-wall geometry (re-architecture wave 4).
 * `null` when either dimension is unknown. */
const PIXELS = new Intl.NumberFormat("en-US");

export function pixelSize(width, height) {
  if (width === null || width === undefined || height === null || height === undefined) return null;
  return `${PIXELS.format(width)} × ${PIXELS.format(height)} px`;
}

/* How this would meet the panel — native, matted small, below the floor — or why that cannot be said.
 *
 * One function for a held work, a candidate scan and a registry work's picture. Both carry the same
 * `fit`/`fit_note` pair and the same rule — a thing whose dimensions nobody
 * recorded must not read like a thing known to be small — so the only real
 * difference is what to call the absence, and that is the argument. Two copies
 * were written first, and their comment claimed "same rule, different shape"
 * when the shapes were identical; the size wording then lived in two places on
 * the one surface whose whole justification is stating it. */
export function fitBadge(sized, absentWord = "no size known") {
  if (!sized.fit) {
    return el("span", { class: "badge badge-unknown", title: sized.fit_note || "" }, [
      el("span", { class: "glyph", text: "—", "aria-hidden": true }),
      el("span", { text: absentWord }),
    ]);
  }
  const verdict = sized.fit.verdict;
  return el("span", { class: `badge badge-${verdict}` }, [
    el("span", { class: "glyph", text: FIT_GLYPHS[verdict] || "●", "aria-hidden": true }),
    // The verdict word alone. It carried "would show at 28.2″" until the owner
    // ruled it out (2026-10-02): that is the long edge on the one panel this
    // server is configured for, after the mat, and read beside a picture it
    // looked like a fact about the picture. Where a size is wanted it is the
    // scan's own pixels, which the review card states; a size on a wall comes
    // back with per-wall geometry (re-architecture wave 4).
    el("span", { text: FIT_WORDS[verdict] || verdict }),
  ]);
}

/* A tile's fit mark: only where the fit is news.
 *
 * On a library tile "native" is what nearly every work says, so it says nothing
 * (`ux-review-2026-10.md` finding 27): a mark on every tile is noise that hides
 * the tile that needs one. A work that would hang small, below the floor, or at
 * a size nobody can state keeps its badge. The Work page, a review card and a
 * theme's rows still say "native", where the fit is what is being judged. */
export function tileFitBadge(work) {
  if (work.fit && work.fit.verdict === "native") return null;
  return fitBadge(work);
}

/* Which image the Work page's picture is: the wall render, or the master where
 * no wall render exists yet. Not drawn on a tile, which is always the work
 * itself (ruling 7 of 2026-10-07), so the word would say nothing there. */
export function sourceBadge(work) {
  if (!work.image.available) return null;
  const rendered = work.image.source_kind === "tv_display";
  return el("span", { class: "badge" }, [
    el("span", { class: "glyph", text: rendered ? "▣" : "□", "aria-hidden": true }),
    el("span", { text: rendered ? "wall render" : "master image" }),
  ]);
}

/* Shown only when a work is out of circulation. An archived work is still
 * listed — the catalogue lists accepted and archived together, because that is
 * what "everything we hold" means — and with no badge it looks exactly like a
 * work that is on the wall. */
export function statusBadge(work) {
  if (work.status === "accepted") return null;
  // Its own class, not `below_floor`'s: catalogue status and display fit are
  // unrelated axes, and sharing a class would make an archived work and a
  // too-small work paint identically.
  return el("span", { class: "badge badge-archived" }, [
    el("span", { class: "glyph", text: "⊘", "aria-hidden": true }),
    el("span", { text: work.status }),
  ]);
}

/* A held work's accessible name where several works are listed: its title, and
 * who made it and when, so two works sharing a title ("Untitled", "Water
 * Lilies") are two different things to somebody moving through the links one at
 * a time. It starts with the visible title, so a voice command that says what
 * it sees still finds the control. */
export function workName(work) {
  const artist = work.artist ? work.artist.name : null;
  return [work.title, artist, work.date_created].filter(Boolean).join(", ");
}

export function absentImage(note) {
  return el("div", { class: "card-image-absent", text: note || "No image held." });
}

export function facts(pairs) {
  const list = el("dl", { class: "facts" });
  for (const [term, value] of pairs) {
    if (value === null || value === undefined || value === "") continue;
    // A node is placed as it is, so a value can be a link; anything else is text.
    list.append(el("dt", { text: term }), value instanceof Node ? el("dd", {}, [value]) : el("dd", { text: String(value) }));
  }
  return list;
}

/* A table that scrolls sideways inside its panel rather than widening the page.
 * Its cells hold file paths and museum URLs with no break in them, which on a
 * phone made the whole Work page wider than the screen.
 *
 * `stacked`: below 40rem each row becomes a card of its own, every cell under
 * its column's heading (`data-label`), for a list a phone reads one row at a
 * time rather than scans across — Activity's (`ux-review-2026-10.md` finding
 * 14). A cell link marked `row-link` then covers its whole card, so the row is
 * the link (`app.css`). */
export function table(caption, headers, rows, { stacked = false } = {}) {
  const cell = (c, index) => {
    const label = headers[index] ? { "data-label": headers[index] } : {};
    return c instanceof Node ? el("td", label, [c]) : el("td", { ...label, text: c === null || c === undefined ? "—" : String(c) });
  };
  return el("div", { class: "table-scroll" }, [el("table", { class: stacked ? "stacked" : null }, [
    el("caption", { text: caption }),
    el("thead", {}, [el("tr", {}, headers.map((h) => el("th", { scope: "col", text: h })))]),
    el("tbody", {}, rows.map((cells) => el("tr", {}, cells.map(cell)))),
  ])]);
}

/* Only ever shown when the runaway guard actually bit. Named rather than
 * silent: a list that stops short without saying so is indistinguishable from a
 * catalogue that holds no more. */
export function shortfallNote(page) {
  if (page.works.length >= page.total) return null;
  // A sixth surface of #113, on a page the issue never named: a shortfall of
  // exactly one read "1 more are held". Only the two verbs move — "more" is
  // already count-neutral, so there is no noun here to pluralise and the
  // sentence a curator sees above one is byte-identical to what it was.
  //
  // Both verbs, because "1 more is held and are not on this page" is what
  // fixing the first one alone produces, and it is the shape this defect has
  // survived twice: the second agreement is further from the number and reads
  // as belonging to a different clause.
  const withheld = page.total - page.works.length;
  return el("p", {
    class: "note",
    text: `Showing ${page.works.length} of ${page.total}; ${withheld} more ${agree(withheld, "is", "are")} held and ${agree(withheld, "is", "are")} not on this page.`,
  });
}

/* Which kind of nothing an unresolved work came back with, in words a curator
 * acts on. The enum values are diagnostic labels; only one of them ("not held")
 * suggests the work may not exist, and a screen showing the raw value leaves
 * that distinction to be guessed.
 *
 * Every member of UnresolvedReason must appear here — a test reads this map and
 * the enum and fails when they disagree, so a sixth reason arrives as a failure
 * rather than as a raw token on a card. */
export const REASON_SENTENCES = {
  not_held: "No wired collection holds it — this is the one reason that suggests the work may not exist.",
  identity_refused: "Something was found under this title, but its artist did not match, so it was refused.",
  size_unknown: "A scan was found, but nothing said how large it is, so it could not be judged.",
  below_floor: "Every scan found is too small to show on this wall at a size worth looking at.",
  all_rejected: "You have turned down everything that was found for it.",
};

const REASON_WORDS = {
  not_held: "not held",
  identity_refused: "wrong artist",
  size_unknown: "size unknown",
  below_floor: "too small",
  all_rejected: "all turned down",
};

export function reasonBadge(work) {
  if (!work.unresolved_reason) return null;
  const value = work.unresolved_reason;
  return el("span", { class: "badge badge-unknown", title: REASON_SENTENCES[value] || "" }, [
    el("span", { class: "glyph", text: "▲", "aria-hidden": true }),
    el("span", { text: REASON_WORDS[value] || value }),
  ]);
}

const RESOLUTION_GLYPHS = { resolved: "●", unresolved: "▲", pending: "◌" };

/* What `resolution_status` says, in the tense it actually holds.
 *
 * **The column describes the RUN's outcome, not the card's current state**, and
 * these words now say so. That is the answer to "does this badge describe the run
 * or the card", and it is written here rather than only in a decision record
 * because the words are the whole of the fix.
 *
 * They used to read "has an image" — present tense, a claim about the work right
 * now — beside a card that could also read "You have turned down everything that
 * was found for it." Each true, together contradictory: only a resolution
 * *attempt* recomputes this column, so turning down the last surviving instance
 * leaves it reading `resolved` until the next re-search.
 *
 * The rejection model is deliberate and settled — `discovery.reject_image` does
 * not rewrite `resolution_status`, and `_accept` asks the images rather than this
 * column for exactly that reason. So the column was right and the wording was
 * wrong, and rewording is what makes the two parts of that card consistent.
 *
 * **Chosen over deriving the badge from surviving instances**, which was the
 * other real option. That would have made the badge mean *the card's* state on
 * the review grid while the run table — whose rows carry no instance data — went
 * on meaning the run's, so one badge would have said two things on two screens.
 * These words mean the same on the grid, in the run table, and beside the raw
 * `resolution_status` an agent reads over MCP. */
const RESOLUTION_WORDS = {
  resolved: "the Get found an image",
  unresolved: "the Get found none",
  pending: "not looked up",
};

export function resolutionBadge(work) {
  const status = work.resolution_status;
  return el("span", { class: `badge badge-${status}` }, [
    el("span", { class: "glyph", text: RESOLUTION_GLYPHS[status] || "●", "aria-hidden": true }),
    el("span", { text: RESOLUTION_WORDS[status] || status }),
  ]);
}
