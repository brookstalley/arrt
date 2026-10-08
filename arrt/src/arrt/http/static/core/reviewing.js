/* The review cards: judging a run's works, wherever a run's works are judged.
 *
 * The product's highest-stakes surface: accepting spends money and acquires,
 * rejecting suppresses a work from future runs. Two screens draw it — Review,
 * at `#review/<run>`, for any run, and a Get's own page, where the cards stand
 * in for the work table because a Get's works were chosen by the curator and a
 * second page to review them on was a page too many (the owner's ruling,
 * 2026-10-02). Shared here rather than imported sideways between the two
 * screens, which `core/badges.js` states as the rule: two screens use it.
 */

import { acquisitionLine } from "./acquiring.js";
import { attempt } from "./acting.js";
import { api } from "./api.js";
import { paintAwaiting, paintWanted } from "./awaiting.js";
import { agree, counted } from "./counting.js";
import {
  absentImage,
  facts,
  fitBadge,
  pixelSize,
  REASON_SENTENCES,
  reasonBadge,
  resolutionBadge,
  shortfallNote,
} from "./badges.js";
import { enlarge } from "./enlarge.js";
import { heldFor, hold, showHold } from "./holding.js";
import { el, fill, guard } from "./render.js";
import { go, link } from "./router.js";
import { tierMark } from "./spend.js";

/* What the curator has decided about a work, in words.
 *
 * `pending` is absent on purpose: an undecided work is the ordinary case and
 * shows no badge, the same way an accepted catalogue work shows no status badge.
 * A badge on every card would make the two decided states harder to pick out,
 * not easier. The vocabulary test knows about the omission. */
const VERDICT_GLYPHS = { accepted: "✓", rejected: "✗", wanted: "◑" };

const VERDICT_WORDS = {
  accepted: "accepted",
  rejected: "rejected",
  wanted: "wanted",
};

/* What a card says once a work becomes wanted, so a curator knows where it went
 * and that nothing is looking for it yet. */
const WANTED_NO_SCAN = "Wanted. It waits in Wanted, where Search again looks for a scan when you ask.";
const WANTED_AFTER_TURNING_DOWN =
  "Turned down, and the work is wanted: it waits in Wanted for a better scan, and nothing looks until you ask there.";

function verdictBadge(work) {
  const glyph = VERDICT_GLYPHS[work.verdict];
  if (!glyph) return null;
  return el("span", { class: `badge badge-${work.verdict}` }, [
    el("span", { class: "glyph", text: glyph, "aria-hidden": true }),
    el("span", { text: VERDICT_WORDS[work.verdict] || work.verdict }),
  ]);
}

/* Where a work came from, in words and as a glyph, one entry per provenance.
 *
 * The curator authorised a work list of a stated size, and a wired collection may
 * add to it; a Get's works the curator chose by hand. Labelled on every row rather
 * than counted only in the summary: an offered work is not what was asked for, and
 * a grid that renders the two alike invites accepting one as though it were. A
 * provenance missing here would be drawn as its raw token, so the vocabulary test
 * holds these keys to the enum. */
const PROVENANCE_GLYPHS = { proposed: "◆", offered: "◈", chosen: "◇" };

const PROVENANCE_WORDS = { proposed: "asked for", offered: "offered", chosen: "you chose" };

function provenanceBadge(work) {
  // `proposed` is the ordinary case and keeps the base badge, as it always has.
  const styled = work.provenance === "proposed" ? "badge" : `badge badge-${work.provenance}`;
  return el("span", { class: styled }, [
    el("span", { class: "glyph", text: PROVENANCE_GLYPHS[work.provenance] || "◆", "aria-hidden": true }),
    el("span", { text: PROVENANCE_WORDS[work.provenance] || work.provenance }),
  ]);
}

/* Whether a source confirms the work exists, one entry per `confirmation`
 * (`data-model.md` § CandidateWork). A model asked for works can name a
 * plausible one that does not exist, so a card never reads as a match the
 * model itself doubted.
 *
 *   `confirmed` draws nothing: a work the search found, the curator chose, or a
 *   collection offered is the ordinary case, and a badge on every card is one a
 *   reader learns to stop looking at.
 *   `unconfirmed`: the model said no source it was given names the work.
 *   `unknown`: nothing was asked or said, so the card claims neither way.
 *
 * The vocabulary test holds the keys to the enum, so a fourth state fails by
 * name rather than drawing as its raw token. */
const CONFIRMATION_MARKS = {
  confirmed: null,
  unconfirmed: ["?", "Not confirmed", "No source the search found names this work by this artist. It may not exist."],
  unknown: ["?", "Unchecked", "Nothing was asked to confirm this work exists."],
};

function confirmationBadge(work) {
  const mark = CONFIRMATION_MARKS[work.confirmation];
  if (mark === null) return null;
  // A state this client has no words for is drawn as itself rather than as
  // confirmed: silence here would be the one claim the badge exists to refuse.
  const [glyph, words] = mark || ["?", work.confirmation || "Unchecked"];
  return el("span", { class: `badge badge-${work.confirmation === "unconfirmed" ? "unconfirmed" : "unchecked"}` }, [
    el("span", { class: "glyph", text: glyph, "aria-hidden": true }),
    el("span", { text: words }),
  ]);
}

/* The sentence under the badge, for the state where the card must say why. */
function confirmationNote(work) {
  const mark = CONFIRMATION_MARKS[work.confirmation];
  return work.confirmation === "unconfirmed" && mark ? el("p", { class: "note not-confirmed", text: mark[2] }) : null;
}

/* The model's Markdown, as words and links on the page.
 *
 * A model writes `[a source](https://…)`, `**emphasis**` and `` `code` ``, and
 * a card printing them raw put brackets and asterisks in front of a curator.
 * Nothing here is parsed as HTML: each piece becomes a text node, an `<em>` or
 * `<strong>` holding text, or a link. **Only an `http:` or `https:` address
 * becomes a link**, opened in a new tab with no referrer, so a model's note
 * cannot point the page at a `javascript:` address; any other link keeps its
 * words and drops its address. */
const MARKDOWN = /\[([^\]\n]+)\]\(([^)\s]+)\)|\*\*([^*\n]+)\*\*|__([^_\n]+)__|\*([^*\n]+)\*|(?<![\w])_([^_\n]+)_(?![\w])|`([^`\n]+)`/g;

export function prose(text) {
  if (!text) return [];
  const pieces = [];
  let at = 0;
  for (const match of String(text).matchAll(MARKDOWN)) {
    if (match.index > at) pieces.push(text.slice(at, match.index));
    const [, label, href, strong, strongToo, em, emToo, code] = match;
    if (label !== undefined) {
      pieces.push(
        /^https?:\/\//i.test(href)
          ? el("a", { href, rel: "noopener noreferrer", target: "_blank", class: "link", text: label })
          : label,
      );
    } else if (strong !== undefined || strongToo !== undefined) {
      pieces.push(el("strong", { text: strong ?? strongToo }));
    } else if (em !== undefined || emToo !== undefined) {
      pieces.push(el("em", { text: em ?? emToo }));
    } else {
      pieces.push(el("code", { text: code }));
    }
    at = match.index + match[0].length;
  }
  if (at < text.length) pieces.push(text.slice(at));
  return pieces;
}

/* The picture for one instance, or what stands in for it.
 *
 * The card knows before it asks — the listing carries `preview_available` — so a
 * work with no kept picture never requests bytes that are not there. The
 * error handler is for the narrow race where the file goes away in between, and
 * for a museum's file that will not decode: the listing reports that one as
 * available, because nothing has read the bytes yet.
 *
 * **A picture that travels is a button, and pressing it enlarges it in place**:
 * the largest preview the server holds, in a dialog over the page, with nothing
 * navigated (`core/enlarge.js`). A button rather than a click handler on the
 * image, so a keyboard reaches it and a screen reader says what it does —
 * `label` is that name, and it names the work, never the scan's id.
 *
 * `alt` is the picture at card size, and `name` the picture enlarged, which
 * names the dialog as well as its image. They differ in the Scans table, where
 * the small picture sits in a row that already says which scan it is and the
 * enlarged one stands alone over the page; the button's own name says what
 * pressing it does, which is not what the picture that opens is. */
function instanceImage(instance, { alt, label, name }) {
  if (!instance.preview_available) {
    return el("div", { class: "card-image" }, [absentImage(instance.preview_note)]);
  }
  const preview = `/api/candidate-images/${encodeURIComponent(instance.image_id)}/preview`;
  const image = el("img", { src: preview, alt: alt || "", loading: "lazy" });
  const frame = el("button", {
    class: "card-image enlargeable",
    type: "button",
    "aria-label": label,
    onclick: () => enlarge({ src: `${preview}?size=large`, alt: name, trigger: frame }),
  }, [image]);
  image.addEventListener("error", () => {
    // Nothing to enlarge once the picture has failed, so the button goes with
    // it rather than opening a dialog onto the same failure.
    frame.replaceWith(el("div", { class: "card-image" }, [absentImage("Its picture could not be loaded just now.")]));
  });
  return frame;
}

/* A wanted work's picture, as Wanted's table carries it: the scan its review
 * card pictures it by (`shown`), enlargeable, with the fit badge that says how
 * small it is — usually below the floor, since nothing the curator would accept
 * is held. A work with no scan standing says why in words, never a blank cell. */
export function wantedPicture(work) {
  if (!work.shown) {
    const why = work.scans_turned_down ? "Every scan found was turned down." : "No scan found.";
    return el("div", { class: "wanted-picture" }, [el("div", { class: "card-image" }, [absentImage(why)])]);
  }
  return el("div", { class: "wanted-picture stack-tight" }, [
    instanceImage(work.shown, {
      alt: pictured(work),
      label: `Enlarge the picture of ${work.title}`,
      name: pictured(work),
    }),
    fitBadge(work.shown, "size unrecorded"),
  ]);
}

/* Why a work is wanted, from what it holds: how many scans were turned down,
 * and what the one standing is — too small for the wall, the selection still on
 * offer (wanted without turning it down), or neither. "On offer" means selected,
 * as `is_on_offer` does on the card, so the row never claims one the card does
 * not. Derived on every read, because a picture beside "No scan found" would
 * contradict it. */
export function wantedWhy(work) {
  const parts = [];
  if (work.scans_turned_down) parts.push(`${counted(work.scans_turned_down, "scan")} turned down`);
  if (work.shown) {
    if (work.shown.fit && work.shown.fit.verdict === "below_floor") parts.push("found only too small");
    else if (work.shown.is_selected) parts.push("one still on offer");
    else parts.push("one found, not on offer");
  }
  if (!parts.length) return "No scan found";
  const said = parts.join("; ");
  return said.charAt(0).toUpperCase() + said.slice(1);
}

/* A scan's own size, in pixels (`pixelSize` in `badges.js`). `null` when the
 * scan's dimensions were never recorded, which the fit badge's "size
 * unrecorded" already says. */
function scanSize(instance) {
  return pixelSize(instance.width, instance.height);
}

function instanceStateBadges(instance) {
  return [
    instance.rejected
      ? el("span", { class: "badge badge-refused" }, [
          el("span", { class: "glyph", text: "⊘", "aria-hidden": true }),
          el("span", { text: "turned down" }),
        ])
      : null,
    instance.is_selected
      ? el("span", { class: "badge badge-on_offer" }, [
          el("span", { class: "glyph", text: "★", "aria-hidden": true }),
          el("span", { text: "on offer" }),
        ])
      : null,
  ];
}

/* One scan as a row of the Scans table, the way an *arr app's interactive
 * search lists releases: what a curator compares across scans in columns — the
 * picture, its pixels and fit, where it came from, its rights, how sure the
 * match is, whether it is the one on offer — and the two things they can do
 * about it at the end of the row.
 *
 * **Why it was chosen and where it lives go on a second row beneath**, spanning
 * the table. They are sentences and addresses, not figures to compare down a
 * column, and set in a column of their own they are what squeezed every other
 * fact into a few characters' width. */
const SCAN_COLUMNS = ["Scan", "Resolution", "Provider", "Rights", "Confidence", "Chosen", "Actions"];

/* A work, as its picture is named: its title, and its artist where known. */
function pictured(work) {
  return work.artist ? `${work.title}, by ${work.artist}` : work.title;
}

/* Which scan a picture is, said without the table around it: the work, then
 * where the scan came from and its size, which is how the row tells it apart
 * from its neighbours. */
function scanName(instance, work) {
  const which = [`the scan from ${instance.provider}`, scanSize(instance)].filter(Boolean).join(", ");
  return `${pictured(work)} — ${which}`;
}

function instanceRows(instance, work, after, decided = false) {
  const title = work.title;
  const act = (control, words, path, message = null) =>
    attempt(control, words, () => api(path, { method: "POST", body: JSON.stringify({}) }), {
      then: async () => {
        // Turning a scan down can leave the work with no image to accept, which
        // takes it off To review; choosing one can put it back. Turning down the
        // scan on offer also makes the work wanted, which Wanted's count shows.
        paintAwaiting();
        paintWanted();
        await after(message);
      },
    });
  const chosen = instanceStateBadges(instance).filter(Boolean);
  const detail = facts([
    ["Why this one", instance.selection_rationale ? el("span", {}, prose(instance.selection_rationale)) : null],
    // Shown as text rather than as a link. The URL comes from a museum this
    // product does not control, and a rendered anchor is one click from
    // navigating a curator's browser to an attacker-chosen address on a page
    // that otherwise touches nothing outside the LAN.
    ["Where it lives", instance.url],
  ]);
  return [
    el("tr", { class: "alternate" }, [
      el("td", { class: "scan-preview" }, [
        instanceImage(instance, { alt: "", label: `Enlarge this scan of ${title}`, name: scanName(instance, work) }),
      ]),
      el("td", { class: "scan-fact" }, [
        el("div", { class: "stack-tight" }, [
          scanSize(instance) ? el("span", { class: "scan-pixels", text: scanSize(instance) }) : null,
          fitBadge(instance, "size unrecorded"),
        ]),
      ]),
      el("td", { class: "scan-fact", text: instance.provider }),
      el("td", { class: "scan-fact", text: instance.rights_status || "—" }),
      el("td", { class: "scan-fact", text: instance.confidence.toFixed(2) }),
      el("td", { class: "scan-fact" }, chosen.length ? [el("div", { class: "stack-tight" }, chosen)] : ["—"]),
      el("td", { class: "scan-actions" }, [
        // One above the other rather than side by side: abreast, two labels
        // that may not wrap made this the table's widest column, and the table
        // overflowed a desktop card on wider fonts. The row is as tall as its
        // preview either way.
        el("div", { class: "stack-tight" }, [
          decided || instance.rejected || instance.is_selected
            ? null
            : el("button", {
                class: "action quiet",
                type: "button",
                text: "Use this one",
                // Named by the work, never by its id. A screen reader announcing
                // "Use this scan for 8f2a-41c3…" names the one thing on the card
                // that identifies nothing, on a row whose whole purpose is
                // choosing between scans of a painting the curator can see.
                "aria-label": `Use this scan for ${title}`,
                onclick: (event) =>
                  act(event.currentTarget, `use this scan for ${title}`, `/api/candidate-images/${encodeURIComponent(instance.image_id)}/select`),
              }),
          decided || instance.rejected
            ? null
            : el("button", {
                class: "action quiet",
                type: "button",
                text: "Turn it down",
                // The scan on offer is the one whose turning down makes the work
                // wanted, so its name says so; an alternate's only turns it down.
                "aria-label": instance.is_selected
                  ? `Turn down this scan for ${title}; the work will wait in Wanted for a better one`
                  : `Turn down this scan for ${title}`,
                onclick: (event) =>
                  act(
                    event.currentTarget,
                    `turn down this scan for ${title}`,
                    `/api/candidate-images/${encodeURIComponent(instance.image_id)}/reject`,
                    instance.is_selected ? WANTED_AFTER_TURNING_DOWN : null,
                  ),
              }),
        ]),
      ]),
    ]),
    el("tr", { class: "alternate-detail" }, [
      el("td", { colspan: String(SCAN_COLUMNS.length) }, [
        detail,
        instance.preview_note ? el("p", { class: "muted", text: instance.preview_note }) : null,
      ]),
    ]),
  ];
}

/* What a capped card is not showing, said out loud.
 *
 * Composed here rather than taken from the MCP surface's notice, which is the
 * same call `runSentence` made and for the same reason: that one names tool
 * calls in backticks and offers a caller an action. The figures are the part
 * that must not be written twice, and they are not — `held` and
 * `shows_every_choosable_instance` are the server's. */
function instancesNote(listing) {
  if (!listing.truncated) return null;
  const omitted = listing.held - listing.instances.length;
  return el("p", {
    class: "note",
    // `omitted` is what agrees in both sentences, and it is one whenever a card
    // is truncated by a single scan. `held` is ≥ 2 here by the truncation guard
    // above, but it goes through the same helper rather than relying on a
    // reader proving that.
    text: listing.shows_every_choosable_instance
      ? `This work holds ${counted(listing.held, "scan")}; ${omitted} already turned down ${agree(omitted, "is", "are")} not shown. Every scan you can still choose is here.`
      : `This work holds ${counted(listing.held, "scan")} and ${omitted} ${agree(omitted, "is", "are")} not shown, including some you could still choose. Turning down what is here is what brings the rest within reach.`,
  });
}

async function alternatesPanel(workId, after) {
  const listing = await api(`/api/candidates/${encodeURIComponent(workId)}/images`);
  if (!listing.instances.length) {
    return el("p", { class: "muted", text: "No scans were found for this work, so there is nothing to choose between." });
  }
  const title = listing.work.title;
  return el("div", { class: "stack" }, [
    instancesNote(listing),
    // Scrolls sideways inside the card on a phone rather than wrapping each
    // fact a word to a line, which is what the stacked layout this replaced did
    // at every width.
    el("div", { class: "table-scroll" }, [
      el("table", { class: "scans" }, [
        el("caption", { text: `The scans found for ${title}.` }),
        el("thead", {}, [el("tr", {}, SCAN_COLUMNS.map((name) => el("th", { scope: "col", text: name })))]),
        el("tbody", {}, listing.instances.flatMap((instance) => instanceRows(instance, listing.work, after, listing.work.decided))),
      ]),
    ]),
  ]);
}

/* Why a card carries no picture — two states the producer distinguishes and this
 * client used to flatten into one sentence.
 *
 * `CandidateCardOut.shown` is null both when nothing was ever found and when the
 * curator turned every scan down, and its own docstring points at the pair that
 * tells them apart. Reading only `shown` told a curator "No scan was found for
 * this work" directly above a disclosure listing the scans they had just
 * rejected, beside a badge still reading "has an image" — because rejecting an
 * image deliberately does not rewrite `resolution_status`. Three parts of one
 * card disagreeing, and the MCP surface said the opposite for the same work.
 *
 * The badge half of that is settled: `RESOLUTION_WORDS` now says "the run found
 * an image", which is what the column always meant and is consistent with the
 * sentence below rather than contradicting it.
 *
 * **It names no way back, because there is none, and an earlier version of this
 * fix invented one.** It read "Restore one from the scans below to judge it
 * again", which was false three times over: every row in that panel renders its
 * controls as null once rejected, no restore endpoint exists, and
 * `discovery.select_image` refuses a rejected instance *on purpose* — its
 * docstring makes the refusal a requirement, so that a rejection survives the
 * next re-search. Inventing an instruction the product forbids is the same
 * defect this function exists to fix, so it is recorded rather than quietly
 * deleted.
 *
 * The sentence is `REASON_SENTENCES.all_rejected` rather than a second string
 * saying the same thing, so this state reads identically wherever a curator
 * meets it. */
function absentScanReason(card) {
  if (card.instances_held > 0 && card.instances_surviving === 0) {
    return REASON_SENTENCES.all_rejected;
  }
  // A work nobody has looked for yet. A Get's page shows its cards while the
  // Get is still looking, and "No scan was found" there, beside the badge
  // saying it was not looked up, is a verdict on a search that has not run.
  if (card.work.resolution_status === "pending") {
    return "This work has not been looked up, so there is no scan to show yet.";
  }
  return "No scan was found for this work.";
}

/* What each card on the page was built from, and where it sends its verdicts.
 *
 * Read by `reviewSection` when it is handed the section it replaces: a card
 * whose work answers exactly as it did is moved into the new section rather
 * than built again, so a half-typed *Why*, an open *Scans* table and whatever
 * the keyboard stood on inside the card all survive the page redrawing around
 * it. A Get's page redraws each time the Get finds another work, and a card
 * built afresh would lose all three to news about a different work.
 *
 * The verdict hook is held here rather than closed over, because a kept card
 * outlives the section that built it: its verdicts must reach the offer to look
 * again on the page it is now on, not one that has left the page. A WeakMap so a
 * card dropped from the page takes its record with it. */
const BUILT = new WeakMap();

/* One proposed work, as the thing a curator decides about.
 *
 * `notice` is carried across a repaint rather than shown from a fresh fetch,
 * because it describes what the verdict just *did* — minting an artist who may
 * duplicate one already held — and that is not a property of the work anybody
 * could read back off it afterwards.
 *
 * `onVerdict` is how anything outside this card learns that one was recorded,
 * and it is deliberately required rather than defaulted to a no-op: a caller
 * that forgets it gets a TypeError on the first verdict, where a silent default
 * would leave the re-search offer quietly describing a page that had moved on —
 * which is the defect this argument exists to close. */
function candidateCard(card, notice, alternatesOpen = false, onVerdict) {
  const work = card.work;
  const node = el("li", { class: "card review-card", "data-work": work.work_id });
  const hooks = { onVerdict };
  BUILT.set(node, { signature: JSON.stringify(card), hooks });

  const repaint = async (message) => {
    const fresh = await api(`/api/candidates/${encodeURIComponent(work.work_id)}`);
    // Announced on every repaint rather than from the verdict buttons alone,
    // because this is the one path both ways of settling a work pass through:
    // the card's own Accept and Reject, and choosing or turning down a scan in
    // the alternates below, which reaches here as `after`.
    hooks.onVerdict(work.work_id, fresh.work.verdict);
    // A held verdict can land after the page redrew this card from a newer
    // answer; the card standing for the work now is the one repainted.
    const current = node.isConnected
      ? node
      : document.querySelector(`li.review-card[data-work="${CSS.escape(work.work_id)}"]`);
    if (!current) return;
    // The disclosure's state is carried over, because choosing between scans is
    // a sequence rather than one act: a curator turning one down is usually
    // about to turn down or choose another. Rebuilding the card closed would
    // collapse the list they are working in, on every click, and cost a second
    // fetch to get back to where they were.
    current.replaceWith(candidateCard(fresh, message, disclosure.open, hooks.onVerdict));
  };

  // An accepted work's image is fetched by the acquisition queue, not by the
  // verdict, so the card says how that is coming along — the moment after
  // Accept is when a curator wonders whether anything happened.
  const acquisitionSlot = work.verdict === "accepted" && work.artwork_id ? el("div", { class: "acquisition-slot" }) : null;
  if (acquisitionSlot) guard(() => paintAcquisition(acquisitionSlot, work));

  const reason = el("input", { type: "text", id: `reason-${work.work_id}` });
  // `words` is the act as the failure would name it: "accept Nighthawks".
  //
  // Pressed, the verdict is held (`core/holding.js`): the card's controls give
  // way to what is about to happen and Undo, and only when the hold runs out,
  // or the curator leaves the page, is it sent. A failure to send brings the
  // controls back with the failure said beside the button that was pressed.
  const decide = (verdict, words) => (event) =>
    hold({
      key: work.work_id,
      act: words,
      title: work.title,
      controls,
      pressed: event.currentTarget,
      write: ({ keepalive }) =>
        api(`/api/candidates/${encodeURIComponent(work.work_id)}/verdict`, {
          method: "POST",
          body: JSON.stringify({ verdict, reason: reason.value || null }),
          keepalive,
        }),
      then: async (outcome) => {
        // A verdict is one fewer work to review: the sidebar's count is read
        // again as soon as it is recorded, whatever happens to the repaint.
        paintAwaiting();
        await repaint(outcome.notice);
      },
    });

  const alternates = el("div", { class: "stack" }, [el("p", { class: "muted", text: "Loading this work's scans…" })]);
  // **"Scans", not "other scans", and the count is deliberately every scan the
  // work holds.** The panel below lists all of them — the one pictured on the
  // card included, because seeing which is currently selected is half of
  // choosing between them. Labelling that "Other scans (1)" promised a curator
  // something new behind a disclosure whose single entry was the picture they
  // were already looking at, which is a promise every single-scan work broke.
  // The count matches the panel's contents; making the *word* true was the fix,
  // because subtracting the shown scan from the number would have made the
  // summary disagree with what opening it reveals.
  const disclosure = el("details", { class: "scans-disclosure" }, [
    el("summary", { text: `Scans (${card.instances_held})` }),
    alternates,
  ]);
  // Fetched when it is opened rather than with the grid: a thirty-work page
  // would otherwise carry up to twelve instances each, and a curator opens the
  // alternates for the few works whose first answer they doubt.
  disclosure.addEventListener("toggle", () => {
    if (disclosure.open) guard(async () => fill(alternates, await alternatesPanel(work.work_id, (message) => repaint(message))));
  });
  // Opening it here fires `toggle`, which is what fetches the list — so a
  // carried-over disclosure loads rather than restoring the placeholder.
  //
  // The order relative to the listener above does not matter, and the comment
  // here used to claim it did. `toggle` is dispatched asynchronously, so a
  // listener attached after the property is set still receives it; the mutation
  // sweep proved the claim false by swapping the two lines and watching every
  // test pass. Left in this order because it reads better, not because anything
  // depends on it.
  if (alternatesOpen) disclosure.open = true;

  // A work its search finished without finding any scan for: nothing to
  // accept, so Want or Forget. Not one whose search is still running, which has
  // found nothing *yet* and may still.
  const noScan = card.instances_held === 0 && work.resolution_status === "unresolved";
  // A decided work (accepted or rejected, the server's `decided`) takes no
  // second verdict and no change of scan, so its card says what was decided in
  // place of the controls: offering them again read as though the click had not
  // taken. Wanted is not decided: it keeps Forget.
  const decided = work.decided;
  const acceptOrReject = () => [
    card.held_artwork_id
      ? link({ view: "work", id: card.held_artwork_id }, { class: "action", text: "Open it in Artworks", "aria-label": `Open ${work.title} in Artworks` })
      : el("button", { class: "action", type: "button", text: "Accept", "aria-label": `Accept ${work.title}`, onclick: decide("accepted", "accept") }),
    card.held_artwork_id
      ? el("button", {
          class: "action quiet",
          type: "button",
          text: "Accept anyway",
          "aria-label": `Accept ${work.title} anyway, as a second artwork`,
          onclick: decide("accepted", "accept"),
        })
      : null,
    el("button", { class: "action quiet", type: "button", text: "Reject", "aria-label": `Reject ${work.title}`, onclick: decide("rejected", "reject") }),
  ];
  const want = (event) =>
    attempt(
      event.currentTarget,
      `want ${work.title}`,
      () => api(`/api/candidates/${encodeURIComponent(work.work_id)}/want`, { method: "POST", body: JSON.stringify({}) }),
      {
        then: async () => {
          paintAwaiting();
          paintWanted();
          await repaint(WANTED_NO_SCAN);
        },
      },
    );
  const wantOrForget = () => [
    // Already wanted: Want would change nothing, so only Forget is offered.
    work.verdict === "wanted"
      ? null
      : el("button", { class: "action", type: "button", text: "Want", "aria-label": `Want ${work.title}, and find a scan later`, onclick: want }),
    // Reject by another name: it stops the work being proposed again, which
    // is what a curator forgetting a painting means.
    el("button", {
      class: "action quiet",
      type: "button",
      text: "Forget",
      "aria-label": `Forget ${work.title}: stop proposing it`,
      onclick: decide("rejected", "forget"),
    }),
  ];

  const controls = el("div", { class: "row" }, [
    el("div", { class: "field" }, [
      el("label", { for: `reason-${work.work_id}`, text: "Why (optional)" }),
      reason,
    ]),
    // **A work nothing was ever found for offers Want and Forget**, not
    // Accept and Reject: accepting it would mint a work with no image, and
    // rejecting it is "forget it for good", which is said as such. Want is
    // the one way to say "I want this painting; no scan exists yet", and it
    // waits in Wanted (the owner's ruling on #168, 2026-10-02).
    ...(noScan ? wantOrForget() : acceptOrReject()),
  ]);

  node.append(
    card.shown
      ? instanceImage(card.shown, {
          alt: pictured(work),
          label: `Enlarge the picture of ${work.title}`,
          name: pictured(work),
        })
      : el("div", { class: "card-image" }, [absentImage(absentScanReason(card))]),
    el("div", { class: "card-body" }, [
      el("h2", { class: "card-title", text: work.title }),
      el("p", { class: "card-artist", text: work.artist || "Artist unrecorded" }),
      // The shown scan's own size, above the fold: the one fact a picture at
      // card size cannot convey, and the first thing asked of a scan.
      card.shown && scanSize(card.shown) ? el("p", { class: "card-resolution", text: scanSize(card.shown) }) : null,
      el("div", { class: "card-footer" }, [
        verdictBadge(work),
        provenanceBadge(work),
        confirmationBadge(work),
        resolutionBadge(work),
        reasonBadge(work),
        card.shown ? fitBadge(card.shown, "size unrecorded") : null,
      ]),
      acquisitionSlot,
      // A chosen work names the Wikidata item it was got by, which opens that
      // item's page here: what the registry knows of the work, to judge it by.
      work.wikidata_qid
        ? el("p", { class: "card-meta" }, [
            "You chose this from Wikidata: ",
            link({ view: "work", id: work.wikidata_qid }, { class: "link", text: work.wikidata_qid }),
          ])
        : el("p", { class: "card-meta" }, prose(work.rationale)),
      confirmationNote(work),
      // The picture is not the one a verdict would accept on, and saying so is
      // the difference between a curator understanding the refusal and being
      // surprised by it. Accepting really is refused in this state — the service
      // will not record a work with no primary source — so the card says which
      // action reaches the way out.
      card.shown && !card.shown_is_on_offer && !decided
        ? el("p", {
            class: "note",
            text: "No scan is on offer for this work. The picture is what was found, shown so you can judge it — accepting is refused until you choose one from the scans below.",
          })
        : null,
      notice ? el("p", { class: "note", text: notice }) : null,
      // Sonarr's *Already in your library* on an Add New result: a run can
      // propose a work an earlier run acquired, and accepting it again would mint
      // a second artwork for one painting. So the card says so, and its first
      // control opens the one already held. **Accept stays, quieter, as "Accept
      // anyway"**: "held" is found by title and artist, and two different works
      // can share both ("Untitled"), so taking Accept away would block acquiring
      // a painting the library does not hold. Reject stays too, because "stop
      // proposing this" is a fair thing to say about a work you already own.
      card.held_artwork_id && !decided
        ? el("p", { class: "note already-held" }, [
            el("span", { class: "glyph", text: "✓", "aria-hidden": true }),
            el("span", { text: " Already in your library, by title and artist. Accepting it again acquires a second artwork." }),
          ])
        : null,
      decided ? decidedLine(work) : controls,
    ]),
    // Beneath the picture and the facts both, the card's full width: the Scans
    // table needs it, and at the facts column's width its columns were what
    // wrapped.
    disclosure,
  );
  // A card drawn again while its verdict is held shows the hold, not a
  // verdict to press a second time.
  const held = decided ? null : heldFor(work.work_id);
  if (held) {
    const pressed = [...controls.querySelectorAll("button")].find((button) => button.textContent.toLowerCase().startsWith(held.act)) || null;
    showHold(held, controls, pressed);
  }
  return node;
}

/* What a decided card says where its controls were: the decision, and for an
 * accepted work the way to the artwork it became. Its image's progress is the
 * acquisition line above. */
function decidedLine(work) {
  const accepted = work.verdict === "accepted";
  return el("div", { class: "row decided" }, [
    el("p", { class: "muted", text: accepted ? "Accepted. It is in your library." : "Rejected. It will not be proposed again." }),
    accepted && work.artwork_id
      ? link({ view: "work", id: work.artwork_id }, { class: "action quiet", text: "Open it in Artworks", "aria-label": `Open ${work.title} in Artworks` })
      : null,
  ]);
}

/* Where an accepted work's image stands: the queue's line while it owes one,
 * and a plain sentence once it does not. */
async function paintAcquisition(slot, work) {
  const detail = await api(`/api/works/${encodeURIComponent(work.artwork_id)}`);
  fill(
    slot,
    detail.acquisition
      ? acquisitionLine(detail.acquisition, work.title, () => paintAcquisition(slot, work))
      : el("p", {
          class: "muted",
          text: detail.original ? "Its image is held and prepared for the wall." : "No image is being fetched for it.",
        }),
  );
}

/* The offer to look again, over the works currently wanted.
 *
 * `wanted` is a function rather than the list itself, so the button reads the
 * set again at the moment it is clicked rather than closing over the one this
 * paint was built from. **A mutation sweep survives replacing that call with the
 * captured list, and that is expected rather than a gap to close**: the map is
 * only ever written by the callback that repaints this panel in the same breath,
 * so the two are equal on every path that exists today and no test can tell them
 * apart. It is kept because the failures either side of it are not the same
 * size — a stale count misinforms a curator, a stale list *acts*: it starts a
 * run over exactly the ids in this body, which would re-search a work the
 * curator has since accepted. Reading at click time is what keeps that list
 * correct without it resting on the panel's
 * render bookkeeping being right, which is the coupling that produced the
 * defect this function was extracted to fix. */
function reSearchOffer(wanted) {
  const works = wanted();
  // Offered only when there is something to re-search. A button that starts a
  // run over an empty list is worse than no button: it does nothing and says
  // it did something.
  if (works.length === 0) return null;
  return el("div", { class: "panel" }, [
    el("h2", { text: "Wanted" }),
    el("p", {
      class: "muted",
      // Says that nothing is looking, which is the fact a curator cannot
      // see. Wanting a work records a wish; it does not start a search, and a
      // page that stayed silent would leave them waiting for one that is
      // never coming.
      text: `${works.length} ${works.length === 1 ? "work is" : "works are"} wanted. Nothing is looking for a scan — a re-search is what looks, and it costs nothing.`,
    }),
    el("div", { class: "row" }, [
      el("button", {
        class: "action",
        type: "button",
        text: "Look again for these",
        onclick: (event) =>
          attempt(
            event.currentTarget,
            "start the re-search",
            () => api("/api/runs/resolve", { method: "POST", body: JSON.stringify({ work_ids: wanted() }) }),
            { then: (run) => go("run", run.run_id) },
          ),
      }),
      tierMark("free"),
    ]),
  ]);
}

/* The offered works, bucketed by the browse query that produced each.
 *
 * Keyed on `offered_for_artist`, which is the *run's* spelling of the artist —
 * the same string `proposed_artist` carries on the works the run named, so the
 * two halves of a group can be counted against each other below. The work's own
 * `artist` is the collection's attribution and is deliberately not used: it
 * differs, verbatim and on purpose.
 *
 * A work whose query is unknown buckets under `null` rather than being skipped.
 * Skipping would drop it off the page altogether — the review surface silently
 * showing fewer works than the run holds, which is a worse defect than the one
 * this grouping exists to fix. */
function offeredGroups(cards) {
  const groups = new Map();
  for (const card of cards) {
    const artist = card.work.offered_for_artist || null;
    if (!groups.has(artist)) {
      groups.set(artist, { artist, matched: card.work.offered_artist_matched, cards: [] });
    }
    groups.get(artist).cards.push(card);
  }
  return [...groups.values()];
}

/* What one offered group says, once, above its own works.
 *
 * `product-brief.md` requires a curator to be able to tell being offered one work
 * out of four hundred from being offered one out of one, and — as amended for
 * issue #95 — requires it said here rather than restated on every card.
 *
 * **Every number is counted from something the reader can see, or named as what
 * it is.** `shown` counts the cards actually rendered, so it cannot disagree with
 * the page the way a server-composed total did. `matched` is the collection's
 * holdings, stated as holdings and reconciled against the per-run bound in the
 * same breath — the old sentence put "one of 25 works it holds" beside twelve
 * cards and left the gap unexplained.
 *
 * **The first clause counts the unresolved works only, and that is not
 * pedantry.** An artist reaches this supplement by having *any* named work come
 * back unresolved, so they may well have others that resolved perfectly well.
 * "found an image for none of them" would be false for exactly those artists —
 * the same shape of false-on-the-page-that-shows-both claim this issue exists to
 * remove. When no such work is on the page the clause is omitted rather than
 * printed with a zero. */
function offeredGroupSentence(group, allCards) {
  const named = group.artist
    ? allCards.filter(
        (card) =>
          card.work.provenance !== "offered" &&
          card.work.artist === group.artist &&
          card.work.resolution_status === "unresolved",
      ).length
    : 0;
  const shown = group.cards.length;
  const matched = group.matched;
  // Was a private plural helper here — a seventh spelling of the rule
  // `core/counting.js` holds, three lines from a clause that got the verb wrong.
  // That adjacency is the whole argument for not keeping a local one.
  const works = (n) => counted(n, "work");

  const clauses = [];
  if (named > 0) clauses.push(`This run found no image for ${works(named)} it named by this artist.`);
  if (typeof matched !== "number") {
    // No holdings count recorded — say nothing about a total rather than guess
    // one, which is the failure this whole change is undoing.
    clauses.push(`The collection offered ${works(shown)} it holds by them.`);
  } else if (shown < matched) {
    // Says that these are a subset and stops there. Naming the per-run bound as
    // the *cause* of the gap is a claim this surface cannot support: a group also
    // comes up short when works were declined for rendering below the display
    // floor, and on a re-search page where the bound is never reached at all. The
    // reconciliation the requirement asks for is that the two numbers not appear
    // to disagree — which "what this run offered" delivers without inventing a
    // reason for the difference.
    // The demonstrative agrees as well as the verb. "these 1 are" is the same
    // defect as "1 works" with an extra word in it, and a run that offered one
    // work out of several the collection holds is the ordinary case here.
    clauses.push(
      `The collection holds ${works(matched)} by them; ${agree(shown, "this", "these")} ${shown} ${agree(shown, "is", "are")} what this run offered.`,
    );
  } else {
    clauses.push(`These are all ${works(matched)} the collection holds by them.`);
  }
  return clauses.join(" ");
}


/* Everything below a review's heading: the offer to re-search, the cards, and
 * the collection's offers grouped under their queries — as nodes, for the
 * screen drawing them to place under whatever heading it has.
 *
 * `page` is `fetchAllCandidates`'s `{run, works, total}`. `keptFrom` is the
 * section this one replaces, when the screen is redrawing the same run: its
 * cards whose works have not changed are kept rather than rebuilt (`BUILT`). */
export function reviewSection(page, { keptFrom = null } = {}) {
  /* One answer to "which works are wanted", held for as long
   * as this section is on screen.
   *
   * The grid repaints a card in place and leaves its neighbours alone — see
   * `candidateCard`, where that choice is argued — so a verdict changes one node
   * and nothing around it. Deriving the offer from `page.works` gave the screen
   * two answers to this question: the offer's, fixed at paint, and the grid's,
   * current. They diverge on a transition reachable from this very page, and the
   * offer is the one that starts a run. */
  const verdicts = new Map(page.works.map((card) => [card.work.work_id, card.work.verdict]));
  const isWanted = (verdict) => verdict === "wanted";
  const wanted = () => [...verdicts].filter(([, verdict]) => isWanted(verdict)).map(([workId]) => workId);

  /* Always on the page, whether or not it holds anything.
   *
   * Two things need that. A run can arrive with nothing wanted and reach a work
   * wanted through the curator's own next click, so an offer built only when the
   * first paint found one could never appear. And a live region has to exist
   * *before* the content it announces is put into it — a `role="status"` element
   * created and filled in the same breath announces nothing, which is the usual
   * way this is got wrong. Empty, it is an empty div: measured at 0px high with
   * no margins, so it costs no space either.
   *
   * `status` rather than the error banner's `alert` because an offer appearing is
   * news, not an emergency: polite waits for a pause instead of interrupting. */
  const offer = el("div", { role: "status" });
  const paintOffer = () => {
    const panel = reSearchOffer(wanted);
    fill(offer, ...(panel ? [panel] : []));
  };
  paintOffer();

  const noteVerdict = (workId, verdict) => {
    const was = isWanted(verdicts.get(workId));
    verdicts.set(workId, verdict);
    // Repainted only when this work's *membership* moved — not merely when its
    // verdict did. The offer depends on nothing else, so accepting a work that
    // was never wanted leaves it word for word identical, and rewriting a live
    // region re-announces it: a curator working by screen reader would hear the
    // whole offer read out again for a verdict that did not concern it.
    // Comparing verdicts instead of membership looks equivalent and is not; the
    // test that accepts an unrelated work is what says so.
    if (was !== isWanted(verdict)) paintOffer();
  };

  // One work to a row, not a grid of tiles: a card is judged by reading it, its
  // scans open beneath it as a table, and a column of tiles a quarter of the
  // page wide wrapped every fact in them a few characters at a time.
  const keepable = new Map();
  if (keptFrom) for (const node of keptFrom.querySelectorAll("li.review-card")) keepable.set(node.dataset.work, node);
  const cardFor = (card) => {
    const kept = keepable.get(card.work.work_id);
    const record = kept ? BUILT.get(kept) : null;
    if (record && record.signature === JSON.stringify(card)) {
      record.hooks.onVerdict = noteVerdict;
      return kept;
    }
    return candidateCard(card, null, false, noteVerdict);
  };
  const gridOf = (cards) => el("ul", { class: "review-grid" }, cards.map(cardFor));

  /* The works the run named, then the collection's offers under their own
   * queries. Two sections rather than one list, because the sentence each offer
   * group carries is about the group — putting it anywhere else is what this
   * change is undoing.
   *
   * The offers are gathered here rather than left in arrival order, which
   * interleaves artists: `_round_robin` takes one work per artist per pass so a
   * bound of twelve reaches every artist rather than filling up on the first.
   * That spread is a choice about *which* works are offered and survives being
   * displayed in any order — its own docstring says the spread is the point, not
   * the order within a facet. */
  const offered = page.works.filter((card) => card.work.provenance === "offered");
  const named = page.works.filter((card) => card.work.provenance !== "offered");

  return [
    // The catalogue grid's own helper: `fetchAllCandidates` returns the
    // `{works, total}` shape it takes, and a second copy of the sentence is how
    // one grid comes to word truncation differently from the other.
    shortfallNote(page),
    offer,
    page.works.length ? null : el("p", { class: "muted", text: "This run settled on no works, so there is nothing to review." }),
    named.length ? gridOf(named) : null,
    // Each group in its own element rather than as three loose siblings. The
    // requirement is an *association* — this sentence belongs to these works —
    // and flat siblings leave that expressible only by document order, which no
    // assertion can hold and a screen reader does not convey. It also gives the
    // browser tests something to scope to: page-wide text matching passes on two
    // groups whose sentences have been swapped.
    ...offeredGroups(offered).map((group) =>
      el("section", {
        class: "offer-group",
        // The query, as an attribute rather than only as heading prose. A card's
        // own artist is the collection's attribution and differs from the query
        // on purpose, so matching a group by visible text finds the wrong one —
        // which is exactly what happened to the test written that way.
        "data-offer-artist": group.artist,
        "aria-label": group.artist ? `Offered by the collection: ${group.artist}` : "Offered by the collection",
      }, [
        el("h2", { text: group.artist ? `Offered by the collection — ${group.artist}` : "Offered by the collection" }),
        el("p", { class: "muted", text: offeredGroupSentence(group, page.works) }),
        gridOf(group.cards),
      ]),
    ),
  ];
}
