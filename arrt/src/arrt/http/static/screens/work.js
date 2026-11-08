/* Work — one work at full size, what it is said to be, where it hangs, and the
 * acts that hang it, add it to a theme, take it out of circulation and put it
 * back.
 *
 * Contextual: reached from a tile in Artworks, a tile on a Wall, or a row in
 * Review, and it **returns to the page it was opened from**. That is the
 * requirement `information-architecture.md` states under Back/escape, and the
 * back control here reads it off the address rather than naming a fixed parent —
 * this screen's route out used to be "← All works" whatever route in had been
 * taken.
 *
 * **It opens as every page does**: the way back, the title, one line of facts
 * and the toolbar (`design-direction.md` § How a page reads; ruling 8 of
 * 2026-10-27). Then the picture, the largest thing on the page, with its label
 * beside it; the artwork is the primary content on every screen that shows
 * one, and the head above it is kept to those three lines so it yields.
 *
 * **There is no delete of a work here, and there is no route that could do one.**
 * `Artwork.status` is `accepted` or `archived`, restoration is permitted, and the
 * control therefore reads *Archive* with *Restore* as its undo. A button reading
 * "Remove" would promise the work was gone while it is in fact still catalogued,
 * still in every theme that held it, and one click from being back on the wall —
 * and a curator who learns that a confirmation overstates will read the next one
 * less carefully.
 *
 * **A work the library does not hold has a page here too**, at `#work/Q…`
 * (ruling 2): what Wikidata says of it, *Get this work*, what the image
 * sources hold of it now, before any Get (`watchLook`), and the rest of its
 * artist's work below. A QID the library
 * holds is sent to the library's own page, in place. Every string on it is
 * registry text, shown as text.
 */

import { acquisitionLine } from "../core/acquiring.js";
import { attempt } from "../core/acting.js";
import { api } from "../core/api.js";
import { absentImage, facts, fitBadge, noPicture, pixelSize, statusBadge, table } from "../core/badges.js";
import { confirmAct } from "../core/confirm.js";
import { counted } from "../core/counting.js";
import { dated } from "../core/dates.js";
import { GLYPHS } from "../core/glyphs.js";
import { FETCH_WORDS, museumName, RIGHTS_WORDS } from "../core/providers.js";
import { enlarge } from "../core/enlarge.js";
import { getOne } from "../core/getting.js";
import { identityControl } from "../core/identity.js";
import { isMatColour, mattedPicture } from "../core/mat.js";
import { el, emphasised, fill, render } from "../core/render.js";
import { isQid, listHeadings, named, personLink, stateMark, wikidataLink, workCell, workState, year, yearCell } from "../core/registry.js";
import { wallLinks } from "../core/places.js";
import { backLink, link, redirect, setTitle } from "../core/router.js";
import { hangSelection } from "../core/selection.js";
import { openPanel } from "../core/editing.js";
import { addWorksToTheme, offeredThemes, themeChoice } from "../core/membership.js";
import { actionMenu, toolbar } from "../core/toolbar.js";
import { DEBUG } from "../core/debug.js";

/* The typed vocabulary a work is filed under, in the words a label uses.
 *
 * The six are `VocabularyKind`, which `Affinity.kind` shares — one set of terms
 * for what a work *is*, what the curator likes, and what discovery weights. A
 * kind with no entry here falls through to its raw token, which is why a unit
 * test reads this map against the enum: a seventh kind should arrive as a
 * failing test rather than as `date_range` printed on a museum label. */
const FACET_KIND_WORDS = {
  artist: "Artist",
  movement: "Movement",
  era: "Era",
  subject: "Subject",
  medium: "Medium",
  palette: "Palette",
};

/* Stated once, below the facts it qualifies.
 *
 * **Inferred is the rule, so the exception is what gets marked.** The wired
 * collection publishes no style field and its classification and period are
 * missing on ordinary spellings, so nearly every facet here was read off the
 * work by a model. A badge on each of those is a label on almost everything,
 * which is a label nobody reads — and it buries the rare value that carries a
 * museum's own authority.
 *
 * Below rather than above, because a rule that holds for every work must not
 * outrank the facts particular to this one; a museum label puts its
 * qualifications at the foot for the same reason. */
const DERIVATION_FOOTNOTE =
  `Every value above is inferred unless it carries ${GLYPHS.yes}, which marks the few a source recorded.`;

/* What a restore does at the wall.
 *
 * **The MCP surface's own sentence, deliberately.** Two surfaces stating one
 * fact in different words is how a reader learns to trust neither, and the
 * agent-facing notice for `art_catalogue(action='restore')` already says this.
 * It says the wall catches up by itself, for the reason `RESTORE_NOTICE` gives
 * in `mcp/bindings.py`, where the literal lives; it is asserted into this file
 * by `tests/unit/test_client_vocabulary.py`, so the two surfaces cannot drift
 * into saying one thing in two wordings. */
const RESTORE_CONSEQUENCE = "It goes back into the rotation of every wall hanging a theme that holds it.";

function workPath(artworkId) {
  return `/api/works/${encodeURIComponent(artworkId)}`;
}

export async function viewWork(artworkId, generation) {
  if (isQid(artworkId)) {
    await viewRegistryWork(artworkId, generation);
    return;
  }
  // Together, and the page waits for both: the state strip is part of what the
  // page says the work is, not something to arrive later and push the facts down.
  const [detail, placements] = await Promise.all([api(workPath(artworkId)), api(`${workPath(artworkId)}/placements`)]);
  paint(detail, generation, { where: { placements } });
}

/* What the registry knows of a work the library does not hold, or why it cannot say. */
async function viewRegistryWork(qid, generation) {
  const page = await api(`/api/registry/works/${encodeURIComponent(qid)}`);
  if (page.held_artwork_ids.length) {
    redirect("work", page.held_artwork_ids[0]);
    return;
  }
  if (page.state !== "known") {
    render(
      generation,
      el("p", {}, [backLink()]),
      el("h1", { text: page.state === "not_found" ? "Wikidata has no such work" : `Wikidata ${qid}` }),
      el("p", { class: "note", text: page.note }),
    );
    return;
  }
  const title = named(page.title, qid);
  setTitle(generation, title);
  const maker = page.creators[0];
  const picture = page.image
    ? el("img", {
        class: "detail-image",
        src: `${page.image}?width=1200`,
        alt: maker ? `${title}, by ${named(maker.name, maker.qid)}` : title,
        referrerpolicy: "no-referrer",
      })
    : el("p", { class: "note", text: "No free image of this work is known." });
  const theirWork = el("section", { class: "panel", "aria-labelledby": "more-by" });
  // Wikidata's picture stays on top when there is one; otherwise the first
  // picture a source answers with takes the place (`paintLook`).
  const top = el("div", { class: "look-top" }, [
    picture,
    pictureSize(page),
    // Said because the two can differ: Wikidata's choice of picture is not
    // necessarily what a Get brings back, and the panel below is.
    page.image ? el("p", { class: "muted", text: WIKIDATA_PICTURE_LINE }) : null,
  ]);
  const look = el("section", { class: "panel look", "aria-labelledby": "look-heading" });
  // The same head as a held work's: the way back, the title, one line of facts
  // and the toolbar, whose filled act here is *Get this work*.
  const made = page.creators.length ? el("span", {}, page.creators.flatMap((person, at) => (at ? [", ", personLink(person)] : [personLink(person)]))) : null;
  const factLine = [made, page.year === null ? null : year(page.year), page.media.join(", ") || null, workSize(page.height_cm, page.width_cm)].filter(Boolean);
  render(
    generation,
    el("p", {}, [backLink()]),
    el("h1", { text: title }),
    factLine.length ? factsLine(factLine) : null,
    toolbar({ actions: [getOne(qid)] }),
    el("div", { class: "panel" }, [
      top,
      el("div", { class: "card-footer" }, [stateMark({ wanted: page.wanted, image: Boolean(page.image) })]),
      facts([["Held by", page.holders.length ? page.holders.map(holderLine).join("; ") : null]]),
      el("p", { class: "muted" }, [wikidataLink(qid, `Wikidata ${qid}`)]),
    ]),
    el("p", { class: "muted", text: GET_LINE }),
    look,
    maker ? theirWork : null,
  );
  // Both asked after the page is drawn, and neither waits for the other: the
  // look polls for as long as a source is still being asked.
  const watching = watchLook(look, qid, { top: page.image ? null : top, title, maker });
  if (maker) await paintTheirWork(theirWork, maker, qid);
  await watching;
}

/* Under Wikidata's picture, when it has one. */
const WIKIDATA_PICTURE_LINE = "This picture is the one Wikidata names; below is what every image source holds now.";

/* The line under *Get this work*: what the panel below shows, and what a Get adds. */
const GET_LINE = "These are what the sources hold now; getting the work records them and spends nothing.";

/* -- the look: what the image sources hold, before any Get ------------------
 *
 * Asked of `GET /api/registry/works/{qid}/look`, which answers at once with each
 * source's state and keeps asking behind it; the page polls every two seconds
 * while any source is still being asked, and repaints only this section.
 *
 * **Nothing a curator is standing on is replaced.** The status line is one node
 * whose text changes only when the summary does, so a screen reader hears each
 * change once and never the same sentence twice; a picture, once drawn, is never
 * redrawn or moved, and a better one arriving later is put in before it; the
 * *Show N more* button keeps its node and changes its words. The rows hold
 * nothing that takes focus, so they are redrawn whole. A poll never moves focus
 * (`accessibility-spec.md`).
 *
 * Every source string — titles, artists, the rationale — is text, set as text. */

const LOOK_POLL_MS = 2000;

/* How many pictures are shown before *Show N more*. */
const LOOK_SHOWN = 6;

/* A source's row: a glyph and a word, so the state survives greyscale. Keyed by
 * the server's `SourceState`, which `test_client_vocabulary.py` holds them to. */
const LOOK_SOURCE_GLYPHS = {
  asking: GLYPHS.waiting,
  found: GLYPHS.good,
  holds_none: GLYPHS.none,
  refused: GLYPHS.refused,
  unreachable: GLYPHS.problem,
  cannot: GLYPHS.cannot,
};

const LOOK_SOURCE_WORDS = {
  asking: "Asking…",
  // Preceded by how many, as in "2 found".
  found: "found",
  holds_none: "Holds none",
  refused: "Holds a work by this title by another artist; not shown",
  unreachable: "Could not be asked; trying again in 10 minutes",
  cannot: "Can't look this work up",
};

/* A source that holds a record of the work and gives no size for it. Phase 2
 * refuses such a find, since one with no size cannot be judged against the wall,
 * so "Holds none" would say the source has no such work, which it does. */
const LOOK_UNSIZED_WORDS = "Holds this work but gives no size for it; not shown";

function lookSourceWords(source) {
  if (source.state === "found") return `${source.found} ${LOOK_SOURCE_WORDS.found}`;
  if (source.state === "holds_none" && source.refusals.includes("size_unknown")) return LOOK_UNSIZED_WORDS;
  return LOOK_SOURCE_WORDS[source.state] || source.state;
}

/* Poll the look until no source is still being asked, or the page is gone. */
async function watchLook(section, qid, context) {
  const shown = { pictures: new Map(), limit: LOOK_SHOWN, topFilled: !context.top };
  const status = el("p", { class: "look-summary", role: "status" });
  const rows = el("ul", { class: "look-sources" });
  const grid = el("ul", { class: "grid look-pictures" });
  const more = el("button", { class: "action quiet", type: "button", hidden: true });
  more.addEventListener("click", () => {
    shown.limit = Infinity;
    const first = [...grid.children].find((node) => node.hidden);
    for (const node of grid.children) node.hidden = false;
    more.hidden = true;
    // The curator asked for these, so the keyboard goes to the first of them.
    const target = first && first.querySelector("button, [tabindex]");
    if (target) target.focus();
  });
  fill(section, el("h2", { id: "look-heading", text: "What the image sources hold" }), status, rows, grid, more);
  say(status, "Asking the image sources…");
  for (;;) {
    let look;
    try {
      look = await api(`/api/registry/works/${encodeURIComponent(qid)}/look`);
    } catch (failure) {
      look = null;
    }
    if (!section.isConnected) return;
    if (look === null) {
      say(status, "The image sources could not be asked just now. Reload the page to ask again.");
      return;
    }
    if (look.state === "held" && look.held_artwork_ids.length) {
      redirect("work", look.held_artwork_ids[0]);
      return;
    }
    paintLook({ look, qid, status, rows, grid, more, shown, context });
    if (look.state !== "asking") return;
    await new Promise((resolve) => window.setTimeout(resolve, LOOK_POLL_MS));
    if (!section.isConnected) return;
  }
}

/* Set the status line's words, unless they are already its words. */
function say(status, text) {
  if (status.textContent !== text) status.textContent = text;
}

function lookSummary(look) {
  if (look.state !== "asking" && look.state !== "answered") return look.note || "Nothing is being asked.";
  const total = look.sources.length;
  const answered = look.sources.filter((source) => source.state !== "asking").length;
  if (look.state === "asking") {
    const found = look.pictures.length ? `; ${counted(look.pictures.length, "picture")} so far` : "";
    return `Asking the image sources: ${answered} of ${total} answered${found}.`;
  }
  if (!look.pictures.length) return look.note || "No image source holds a picture of this work now.";
  const holding = look.sources.filter((source) => source.state === "found").length;
  return `${counted(look.pictures.length, "picture")} found, from ${counted(holding, "source")}.`;
}

function paintLook({ look, qid, status, rows, grid, more, shown, context }) {
  say(status, lookSummary(look));
  fill(rows, ...look.sources.map((source) => el("li", { class: "look-source" }, [
    el("span", { class: "look-provider", text: museumName(source.provider) }),
    el("span", { class: `badge badge-look-${source.state}` }, [
      el("span", { class: "glyph", text: LOOK_SOURCE_GLYPHS[source.state] || "·", "aria-hidden": true }),
      el("span", { text: lookSourceWords(source) }),
    ]),
  ])));
  // Best first, as the server orders them. A picture already drawn keeps its
  // node and its place; a new one goes in before the first drawn picture that
  // ranks below it, so nothing a curator may be standing on moves.
  look.pictures.forEach((picture, at) => {
    const id = lookPictureId(picture);
    if (shown.pictures.has(id)) return;
    const node = lookPicture(picture, qid);
    // Shown while fewer than the limit are; else it waits behind *Show N more*.
    // A picture once shown is never hidden again.
    node.hidden = [...grid.children].filter((child) => !child.hidden).length >= shown.limit;
    const after = look.pictures.slice(at + 1).map((later) => shown.pictures.get(lookPictureId(later))).find(Boolean);
    grid.insertBefore(node, after || null);
    shown.pictures.set(id, node);
  });
  const waiting = [...grid.children].filter((child) => child.hidden).length;
  more.hidden = waiting === 0;
  if (waiting) {
    const words = `Show ${waiting} more`;
    if (more.textContent !== words) more.textContent = words;
  }
  if (!shown.topFilled) {
    const first = look.pictures.find((picture) => picture.key);
    if (first) {
      shown.topFilled = true;
      fill(context.top, topPicture(first, qid, context));
    }
  }
}

/* Which find a card is, across polls: its key, or for a find with no picture, its source and address. */
function lookPictureId(picture) {
  return picture.key || `${picture.provider} ${picture.url}`;
}

/* The picture's address on Arrt's own route, by the key the server minted. */
function lookPictureSrc(qid, key, large = false) {
  const src = `/api/registry/works/${encodeURIComponent(qid)}/look/pictures/${encodeURIComponent(key)}`;
  return large ? `${src}?size=large` : src;
}

/* What a source calls the work, by whom, where from and how big: the picture's name. */
function lookPictureName(picture) {
  const who = picture.artist ? `${picture.title}, by ${picture.artist}` : picture.title;
  const size = pixelSize(picture.width, picture.height);
  return `${who}, from ${museumName(picture.provider)}${size ? `, ${size}` : ""}`;
}

/* The work's own picture, inside its mat in its current colour, as a wall
 * shows it (`core/mat.js`), and opening large over the page: a button, so a
 * keyboard reaches it as a pointer does, and the dialog's Escape, Close and
 * backdrop close it (`core/enlarge.js`). The column draws it at a size it can
 * hold sharply; enlarged, the picture alone fills the window, since what is
 * enlarged to be looked at closely is the work. */
function enlargeableHero(work, picture) {
  const alt = work.artist ? `${work.title}, by ${work.artist.name}` : work.title;
  const src = `${workPath(work.artwork_id)}/wall-preview`;
  const button = el(
    "button",
    {
      class: "work-picture-button",
      type: "button",
      "aria-label": `Enlarge ${alt}`,
      onclick: () => enlarge({ src, alt, trigger: button }),
    },
    [picture.element],
  );
  return button;
}

/* The work's own picture inside its current mat (`core/mat.js`), made once per
 * paint and handed to both the hero and the mat control, which previews on it. */
function heroPicture(work, detail) {
  const src = `${workPath(work.artwork_id)}/wall-preview`;
  const alt = work.artist ? `${work.title}, by ${work.artist.name}` : work.title;
  const current = detail.mat_colors.find((mat) => mat.is_current);
  const size = detail.original ? { width: detail.original.width, height: detail.original.height } : null;
  return mattedPicture(el("img", { class: "work-picture", src, alt }), { hex: current ? current.hex_rgb : null, size });
}

/* What a mat is, in a curator's words: the preset's name when it is one, else
 * how it was arrived at. The hex is the store's, and stays behind `?debug`. */
function matName(mat, presets) {
  const preset = presets.find((one) => one.hex_rgb === mat.hex_rgb);
  if (preset) return preset.label;
  if (mat.method === "derived" || mat.method === "dominant_color_fallback") return "From the picture";
  if (mat.method === "vision_model") return "Chosen by the vision model";
  if (mat.method === "manual") return "Set by hand";
  // A method this client does not know yet: said as unknown rather than
  // passed off as a person's choice.
  return "Chosen another way";
}

/* The mat, as a fact that is its own control (`design-direction.md` § How a
 * page reads): *Mat [Warm grey ▾]* in the line of facts under the title, whose
 * value opens the choices. Each one-press mat and the work's own derived
 * colour is a named swatch; choosing one shows it on the picture, as a wall
 * would draw it, and nothing is recorded until *Use this mat*; *Keep the
 * current mat* puts the picture back. Every choice here is free, and the
 * previous colour is kept by the store, so a choice is never lost.
 *
 * **The derivation is offered only when it would change the mat**: an option
 * that does nothing is a press that teaches the curator the control lies.
 *
 * **The choices open under the toolbar, above the picture**, not in a dialog:
 * a modal would lay its backdrop over the very picture the preview is drawn
 * on. Returns `{ fact, panel, status }`: the value in the facts line, the
 * choices it opens, and the line that says what was kept. */
function matControl(work, picture, { onChosen = () => {} } = {}) {
  const shown = el("span", { text: "Reading…" });
  const trigger = el("button", {
    class: "fact-control mat-trigger",
    type: "button",
    disabled: true,
    "aria-expanded": "false",
    "aria-controls": "mat-choices",
    "aria-label": "Mat: reading",
  }, [shown, el("span", { "aria-hidden": "true", text: " ▾" })]);
  const body = el("div", { class: "stack" });
  const panel = el("div", { class: "mat-control", id: "mat-choices", role: "group", "aria-label": "Choose a mat", hidden: true }, [body]);
  const status = el("p", { class: "muted mat-status", "aria-live": "polite" });
  trigger.addEventListener("click", () => {
    panel.hidden = !panel.hidden;
    trigger.setAttribute("aria-expanded", String(!panel.hidden));
    if (!panel.hidden) {
      const first = panel.querySelector("button:not(:disabled)");
      if (first) first.focus();
    }
  });

  const paintControl = (mat) => {
    const current = mat.current;
    const options = mat.presets.map((preset) => ({ label: preset.label, hex: preset.hex_rgb, body: { preset: preset.key } }));
    if (mat.derived_hex_rgb && (!current || current.hex_rgb !== mat.derived_hex_rgb)) {
      options.push({ label: "From the picture", hex: mat.derived_hex_rgb, body: { derive: true } });
    }
    let chosen = null;
    const use = el("button", { class: "action mat-use", type: "button", text: "Use this mat" });
    const keep = el("button", { class: "action quiet mat-keep", type: "button", text: "Keep the current mat" });
    const previewing = el("p", { class: "mat-previewing" });
    const confirm = el("div", { class: "stack mat-confirm", hidden: true }, [previewing, el("div", { class: "row" }, [use, keep])]);
    const buttons = options.map((option) => {
      const isCurrent = !!current && current.hex_rgb === option.hex;
      const button = el(
        "button",
        {
          class: "action quiet mat-option",
          type: "button",
          disabled: isCurrent,
          "aria-pressed": "false",
          onclick: () => {
            chosen = option;
            for (const other of buttons) other.setAttribute("aria-pressed", String(other === button));
            if (picture) picture.paint(option.hex);
            previewing.textContent = `Showing ${option.label.toLowerCase()} on the picture.`;
            confirm.hidden = false;
          },
        },
        [
          swatch(option.hex),
          el("span", { text: isCurrent ? `${option.label} (current)` : option.label }),
        ],
      );
      return button;
    });
    keep.addEventListener("click", () => {
      chosen = null;
      for (const button of buttons) button.setAttribute("aria-pressed", "false");
      if (picture) picture.paint(current ? current.hex_rgb : null);
      confirm.hidden = true;
      status.textContent = "";
    });
    use.addEventListener("click", async () => {
      const option = chosen;
      if (!option) return;
      await attempt(use, `use ${option.label.toLowerCase()} as the mat`, () => api(`${workPath(work.artwork_id)}/mat`, { method: "POST", body: JSON.stringify(option.body) }), {
        then: (next) => {
          if (picture) picture.paint(next.current ? next.current.hex_rgb : null);
          paintControl(next);
          onChosen(next);
          // Kept, so the choices fold away and the keyboard goes back to the
          // fact, which now names the new mat.
          panel.hidden = true;
          trigger.setAttribute("aria-expanded", "false");
          trigger.focus();
          status.textContent = `The mat is now ${option.label.toLowerCase()}. The walls showing it are sent the new colour.`;
        },
      });
    });
    const name = current ? matName(current, mat.presets) : "None chosen yet";
    fill(shown, current ? swatch(current.hex_rgb) : null, el("span", { text: name }));
    trigger.setAttribute("aria-label", `Mat: ${name}`);
    trigger.disabled = false;
    fill(body, el("div", { class: "row mat-options" }, buttons), confirm);
  };

  // Read here and said here when it fails: the page's banner is another
  // act's to fill, and a control left on "Reading…" would never say it stopped.
  api(`${workPath(work.artwork_id)}/mat`).then(
    (mat) => {
      if (trigger.isConnected) paintControl(mat);
    },
    () => {
      fill(shown, el("span", { text: "Unknown" }));
      trigger.setAttribute("aria-label", "Mat: unknown");
      trigger.disabled = false;
      fill(body, el("p", { class: "note", text: "The mat's choices could not be read just now. Reload the page to try again." }));
    },
  );
  return {
    fact: el("span", { class: "fact-with-control" }, [el("span", { text: "Mat " }), trigger]),
    panel,
    status,
  };
}

/* A colour as a small square, drawn only for a colour the catalogue would hold,
 * since it becomes a style value. */
function swatch(hex) {
  return isMatColour(hex) ? el("span", { class: "mat-swatch", style: `--swatch: ${hex}`, "aria-hidden": "true" }) : null;
}

/* Said only when the work has no mat to draw: a work not yet prepared has none,
 * and a picture shown without one must not pass for the wall's. */
function noMatNote(detail) {
  return detail.mat_colors.some((mat) => mat.is_current)
    ? null
    : el("p", { class: "muted no-mat", text: "No mat has been chosen for it yet, so it is shown without one." });
}

/* One find as a card: the picture, enlargeable in place as a review card's is,
 * then its pixels and fit, its source, and why a Get would keep it. */
function lookPicture(picture, qid) {
  const name = lookPictureName(picture);
  let frame;
  if (picture.key) {
    const image = el("img", { src: lookPictureSrc(qid, picture.key), alt: name, loading: "lazy" });
    frame = el("button", {
      class: "card-image enlargeable",
      type: "button",
      "aria-label": `Enlarge ${name}`,
      onclick: () => enlarge({ src: lookPictureSrc(qid, picture.key, true), alt: name, trigger: frame }),
    }, [image]);
    image.addEventListener("error", () => {
      frame.replaceWith(el("div", { class: "card-image" }, [absentImage("Its picture could not be loaded just now.")]));
    });
  } else {
    frame = el("div", { class: "card-image" }, [absentImage("This source gave no picture to show.")]);
  }
  return el("li", { class: "card look-picture" }, [
    frame,
    el("div", { class: "card-body" }, [
      el("div", { class: "row card-meta" }, [el("span", { text: pixelSize(picture.width, picture.height) }), fitBadge(picture)]),
      el("p", { class: "card-meta", text: `From ${museumName(picture.provider)}` }),
      el("p", { class: "card-meta", text: picture.selection_rationale }),
    ]),
  ]);
}

/* The first find, in the place Wikidata's picture would have had, and kept there. */
function topPicture(picture, qid, { title, maker }) {
  const name = maker ? `${title}, by ${named(maker.name, maker.qid)}` : title;
  const image = el("img", { class: "detail-image", src: lookPictureSrc(qid, picture.key, true), alt: `${name}, as ${museumName(picture.provider)} holds it` });
  const caption = el("div", { class: "row picture-size" }, [
    el("span", { class: "muted", text: `${pixelSize(picture.width, picture.height)}, from ${museumName(picture.provider)}` }),
    fitBadge(picture),
  ]);
  const holder = el("div", {}, [image, caption]);
  image.addEventListener("error", () => {
    fill(holder, el("p", { class: "note", text: "The picture a source found could not be loaded just now." }));
  });
  return holder;
}

/* The work's own size, as a museum label gives it: height before width, in
 * centimetres and then inches. Either alone is said as what it is. */
const CENTIMETRES = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });

function workSize(height, width) {
  const inches = (cm) => CENTIMETRES.format(cm / 2.54);
  if (height !== null && width !== null) {
    return `${CENTIMETRES.format(height)} × ${CENTIMETRES.format(width)} cm (${inches(height)} × ${inches(width)} in)`;
  }
  if (height !== null) return `${CENTIMETRES.format(height)} cm high (${inches(height)} in)`;
  if (width !== null) return `${CENTIMETRES.format(width)} cm wide (${inches(width)} in)`;
  return null;
}

/* The picture's own pixels and how they would meet the wall, under it, as a
 * review card states a scan's: the same words and the same badge. Nothing when
 * Commons did not say, rather than a badge reading "no size known" under a
 * picture that plainly exists. */
function pictureSize(page) {
  const size = pixelSize(page.image_width, page.image_height);
  if (!size || !page.fit) return null;
  return el("div", { class: "row picture-size" }, [el("span", { class: "muted", text: size }), fitBadge(page)]);
}

function holderLine(holder) {
  return holder.inventory ? `${holder.name} (${holder.inventory})` : holder.name;
}

/* The rest of the artist's work, the next thing to look at: what the Artist
 * page lists, without this one, asked after the page is drawn. */
async function paintTheirWork(section, maker, qid) {
  const heading = el("h2", { id: "more-by", text: `More by ${named(maker.name, maker.qid)}` });
  fill(section, heading, el("p", { class: "muted", "aria-live": "polite", text: "Asking Wikidata…" }));
  let view;
  try {
    view = await api(maker.artist_id ? `/api/artists/${encodeURIComponent(maker.artist_id)}/registry` : `/api/registry/artists/${encodeURIComponent(maker.qid)}`);
  } catch (failure) {
    view = { state: "unavailable", note: "Wikidata could not be asked just now." };
  }
  if (!section.isConnected) return;
  if (view.state !== "known") {
    fill(section, heading, el("p", { class: "note", text: view.note }));
    return;
  }
  const others = view.works.filter((work) => work.qid !== qid);
  fill(section,
    heading,
    others.length
      ? el("div", { class: "artist-works" }, [
          el("table", {}, [
            el("thead", {}, [listHeadings(["Work", "Year", "State"])]),
            el("tbody", {}, others.map((work) => el("tr", {}, [
              workCell(work),
              yearCell(work),
              el("td", {}, [workState(work)]),
            ]))),
          ]),
        ])
      : el("p", { class: "muted", text: "Wikidata lists nothing else by them." }),
  );
}

/* Draw the whole screen from one dossier and where the work is.
 *
 * Separate from the fetch because archive, restore and a new Wikidata match
 * answer with the same dossier `GET /api/works/{id}` does — so the act repaints
 * from what the server actually recorded rather than from the client's opinion
 * of what it asked for. None changes which themes hold the work, so `where` —
 * the work's placements, which the strip refreshes after its own acts — is
 * carried over.
 *
 * `focus` is how the keyboard survives that repaint: "primary" puts it on the
 * toolbar's filled act (Restore after an archive, Hang… after a restore),
 * "more" back on ⋯. The act's own control is replaced, and a screen that
 * rebuilt itself under a focused control would drop focus to `<body>`, leaving
 * the next Tab at the top of the page. This is not a poll — the accessibility
 * rule that a poll must never move focus is about paints the curator did not
 * ask for, and this one is the direct answer to a press.
 *
 * **The page opens as every page does** (`design-direction.md` § How a page
 * reads): the way back, the title as the one `h1`, one line of facts (the mat
 * among them, as its own control), and the toolbar. *Hang…* is its one filled
 * act, the one a curator most often comes here for; the rare acts, archiving
 * and correcting the Wikidata item, are behind ⋯, since the loudest button on
 * a page reached from a wall must not take the work out of the whole library.
 * An archived work cannot hang, so *Restore* takes the filled place.
 *
 * **Then the picture, the largest thing here**, beside its label: where the
 * work hangs, and what the museum says of it. It is drawn from the master,
 * inside its mat as a wall draws it (a Player draws its own at each wall, by
 * the same rule). There is no Rights fact: good catalogue data, of no use in
 * the home (ruling 8 of 2026-10-27); the sources table below keeps each
 * source's rights. */
function paint(detail, generation, { where, focus = null }) {
  const work = detail.work;
  const archived = work.status !== "accepted";
  setTitle(generation, work.title);
  const picture = work.image.available ? heroPicture(work, detail) : null;
  const image = picture ? enlargeableHero(work, picture) : el("div", { class: "card-image work-picture-absent" }, [noPicture(work.image.note)]);
  const missingMat = picture ? noMatNote(detail) : null;
  const mat = picture ? matControl(work, picture, { onChosen: (chosen) => chosen.current && missingMat && missingMat.remove() }) : null;

  const strip = el("section", { class: "state-strip", "aria-label": "Where it is" });
  const page = { work, generation, where, strip, hang: null, add: null, more: null };
  page.hang = !archived && work.image.available
    ? el("button", { class: "action", type: "button", text: "Hang…", "aria-haspopup": "dialog", onclick: (event) => chooseWall(event.currentTarget, page) })
    : null;
  const restoring = archived
    ? el("button", { class: "action", type: "button", text: "Restore", onclick: (event) => restore(event.currentTarget, page) })
    : null;
  page.add = el("button", {
    class: "action quiet",
    type: "button",
    text: "Add to theme…",
    "aria-haspopup": "dialog",
    onclick: (event) => addToTheme(event.currentTarget, page),
  });
  page.more = actionMenu({
    label: `More acts on ${work.title}`,
    items: [
      archived ? null : { label: "Archive…", act: (trigger) => archive(trigger, page) },
      { label: "Match on Wikidata…", act: (trigger) => matchOnWikidata(trigger, page) },
    ].filter(Boolean),
  });
  paintStrip(page);

  render(
    generation,
    el("p", {}, [backLink()]),
    el("h1", { text: work.title }),
    workFacts(work, mat),
    toolbar({ actions: [page.hang || restoring, page.add, page.more] }),
    mat ? mat.panel : null,
    mat ? mat.status : null,
    el("div", { class: "work-head" }, [
      el("div", { class: "panel work-hero" }, [
        image,
        missingMat,
        el("div", { class: "card-footer" }, [statusBadge(work), fitBadge(work)]),
        work.fit_note ? el("p", { class: "muted", text: work.fit_note }) : null,
      ]),
      el("div", { class: "panel work-label" }, [
        strip,
        facts([
          ["Wikidata", work.wikidata_qid ? wikidataLink(work.wikidata_qid, work.wikidata_qid) : null],
          // No "Status" row, and its absence is the rule rather than an omission.
          // A screen states a fact once: the badge under the picture already says
          // `archived` when that is true and says nothing when it is not, which is
          // the same inversion the derivation footnote uses.
          ["Description", work.description ? emphasised(work.description) : null],
        ]),
      ]),
    ]),
    el("div", { class: "work-record" }, recordPanels(detail, generation, where)),
  );
  // Only if the paint actually landed. `render` declines a paint whose
  // navigation has been superseded, and focusing a control that was never put on
  // the page would move the keyboard onto a detached node.
  // The first act the toolbar shows: *Hang…* is there but hidden while the
  // work is kept off every wall, which an archive and a restore leave as it was.
  const shown = [page.hang, restoring, page.add].find((control) => control && !control.hidden);
  const target = focus === "primary" ? shown : focus === "more" ? page.more.querySelector("button") : null;
  if (target && document.contains(target)) target.focus();
}

/* The one line of facts under the title, as a museum label begins: who made it
 * (a link to their page, with their nationality and life as a label gives
 * them), when, in what, how big, and the mat it is shown in. */
function workFacts(work, mat) {
  const artist = work.artist
    ? el("span", {}, [
        artistLink(work.artist),
        ...[work.artist.nationality, work.artist.lifespan_text].filter(Boolean).length
          ? [` (${[work.artist.nationality, work.artist.lifespan_text].filter(Boolean).join(", ")})`]
          : [],
      ])
    : null;
  return factsLine([artist, work.date_created, work.medium, work.dimensions, mat ? mat.fact : null].filter(Boolean));
}

/* The line of facts under a work's title, held or not, each part text or a
 * node, in one shape. */
function factsLine(parts) {
  return el("p", { class: "muted page-facts work-facts" }, parts.flatMap((part, at) => (at ? [" · ", part] : [part])));
}

/* The record below the picture and its label, each part a section of its own,
 * two to a row where the page is wide enough. */
function recordPanels(detail, generation, where) {
  const work = detail.work;
  const panels = [facetPanel(detail.facets)];

  panels.push(
    el("div", { class: "panel" }, [
      el("h2", { text: "Master image" }),
      detail.original
        ? facts([
            // Where it lies and what it hashes to are for whoever is debugging
            // the store; how big it is says what a wall can make of it.
            ["File", DEBUG ? detail.original.relative_path : null],
            ["Pixels", `${detail.original.width} × ${detail.original.height}`],
            ["Size", `${(detail.original.byte_size / 1048576).toFixed(1)} MB`],
            ["Content hash", DEBUG ? detail.original.content_hash : null],
          ])
        : detail.acquisition
          ? null
          : el("p", { class: "muted", text: "No master image has been acquired for this work yet." }),
      // Where the work stands in the acquisition queue, while it owes one: a
      // work held with no image is queued, fetching, failed or paused, and a
      // page that only said "not acquired yet" read the same in every case.
      detail.acquisition
        ? acquisitionLine(detail.acquisition, work.title, async () =>
            paint(await api(`/api/works/${encodeURIComponent(work.artwork_id)}`), generation, { where }),
          )
        : null,
    ]),
  );

  panels.push(
    el("div", { class: "panel" }, [
      el("h2", { text: "Where it can be obtained" }),
      detail.sources.length
        ? table(
            "Every recorded source, the primary one first.",
            ["Source", "Rights", "Primary", "Last fetch", "URL"],
            detail.sources.map((s) => [
              museumName(s.provider),
              RIGHTS_WORDS[s.rights_status] || s.rights_status,
              s.is_primary ? "Yes" : "No",
              s.last_fetch_status ? FETCH_WORDS[s.last_fetch_status] || s.last_fetch_status : "Not fetched yet",
              s.url,
            ]),
          )
        : el("p", { class: "muted", text: "No sources are recorded." }),
    ]),
  );

  // What was made from the master, and the mat's colour as a hex, are the
  // store's own record, shown only in debug (ruling 1 of 2026-10-11).
  if (DEBUG) panels.push(
    el("div", { class: "panel" }, [
      el("h2", { text: "What has been rendered" }),
      detail.renditions.length
        ? table(
            "A rendition is stale when the master it was made from is no longer the master this work holds.",
            ["Kind", "Target", "File", "State"],
            detail.renditions.map((r) => [
              r.kind,
              `${r.target_width} × ${r.target_height}`,
              r.relative_path,
              r.stale ? `${GLYPHS.problem} stale — needs regenerating` : `${GLYPHS.good} current`,
            ]),
          )
        : el("p", { class: "muted", text: "Nothing has been rendered for this work yet." }),
    ]),
  );

  if (DEBUG) panels.push(matPanel(detail.mat_colors));
  return panels;
}

/* What this work is said to be, in the vocabulary the collection filters by. */
function facetPanel(facets) {
  if (!facets.length) return null;
  // `facts` as well as `facets`, so it inherits the two-column grid every other
  // labelled list on this screen is drawn in — one list of facts about a work
  // should not be laid out two ways because one of them carries a mark.
  const list = el("dl", { class: "facts facets" });
  // Grouped by kind rather than one row per facet: a work with three subjects is
  // three claims of one kind, and three "Subject" terms down the left would read
  // as three different questions. Ordered by the vocabulary rather than by what
  // the store happened to return, so two works read in the same order.
  const known = Object.keys(FACET_KIND_WORDS);
  // Anything the client has no word for still goes on the page, after the six it
  // does. A kind this map has not caught up with is a fact about the work, and
  // dropping it silently is worse than printing its raw token.
  const unknown = [...new Set(facets.map((facet) => facet.kind))].filter((kind) => !(kind in FACET_KIND_WORDS));
  for (const kind of [...known, ...unknown]) {
    const held = facets.filter((facet) => facet.kind === kind);
    if (!held.length) continue;
    list.append(el("dt", { text: FACET_KIND_WORDS[kind] || kind }), el("dd", {}, facetValues(held)));
  }
  return el("div", { class: "panel" }, [
    el("h2", { text: "What this work is" }),
    list,
    el("p", { class: "note", text: DERIVATION_FOOTNOTE }),
  ]);
}

/* One kind's values, each with the mark that only the rare sourced one carries.
 *
 * A tick rather than the bordered word this was first drawn as: an annotation is
 * read after the value it qualifies and must be quieter than it, and a boxed
 * "sourced" beside a one-word value outranked its own subject. The word survives
 * for assistive technology, so neither colour nor shape is the sole carrier of a
 * distinction that decides how much authority a value has. */
function facetValues(held) {
  const nodes = [];
  for (const facet of held) {
    if (nodes.length) nodes.push(", ");
    // A value that names a Wikidata item is a topic, and opens its page.
    nodes.push(
      facet.value_qid
        ? link({ view: "topic", id: facet.value_qid }, { class: "facet-value link", text: facet.value })
        : el("span", { class: "facet-value", text: facet.value }),
    );
    if (facet.derivation === "sourced") {
      nodes.push(
        el("span", { class: "sourced" }, [
          // Hidden from a screen reader, which hears "sourced" instead.
          el("span", { class: "tick", text: GLYPHS.yes, "aria-hidden": true }),
          el("span", { class: "visually-hidden", text: "sourced" }),
        ]),
      );
    }
  }
  return nodes;
}

/* The mat shows its colour and nothing else.
 *
 * `MatColor` keeps the method, the model and the date it was derived, and must —
 * that record is what makes "the new model picked a worse colour" answerable and
 * reversible, and what makes the engine's silent fallback to a darkened dominant
 * colour visible at all. But that is a diagnostic question asked rarely, and the
 * superseded-choices table that stood here put the audit trail where the label
 * goes. **Nothing about this reduces what is stored.** */
function matPanel(matColors) {
  const current = matColors.find((mat) => mat.is_current);
  return el("div", { class: "panel" }, [
    el("h2", { text: "Mat colour" }),
    current
      ? el("p", { class: "mat" }, [
          // The swatch is the only place in this client that puts data in a style
          // attribute, and it is safe because the catalogue refuses a mat colour
          // that is not `#rrggbb` on the way in. The hex is printed beside it, so
          // the colour is never the sole carrier.
          el("span", { class: "mat-swatch", style: `background: ${current.hex_rgb}` }),
          el("span", { text: current.hex_rgb }),
        ])
      : el("p", { class: "muted", text: "No mat colour has been chosen for this work." }),
  ]);
}

/* -- the state strip: which walls and themes the work is on ------------------
 *
 * Read from `GET /api/works/{id}/placements`, which lists every theme holding
 * the work with the walls hanging each, selections included. **A selection is
 * said as its wall**, never by its made-up theme name: the curator chose works,
 * not a theme. The server deletes a selection once no wall hangs it; one read
 * hanging nowhere would be an old hang, and is not said at all. A real theme is
 * named, and links to its page.
 *
 * The acts that change it — *Hang…* and *Add to theme…* in the toolbar, and
 * *Allow on walls again* in the strip — repaint the strip alone, from the
 * placements read afresh after the act, with a sentence in its status line. */

function placementsPath(artworkId) {
  return `${workPath(artworkId)}/placements`;
}

/* The walls the work hangs on, each once, in the order the themes name them. */
function wallsHanging(placements) {
  const walls = new Map();
  for (const placement of placements.themes) {
    for (const wall of placement.hanging_on) walls.set(wall.wall_id, wall);
  }
  return [...walls.values()];
}

/* A real theme, as a link to its page, and the walls it hangs on. */
function themeLine(placement) {
  const name = link({ view: "theme", id: placement.theme.theme_id }, { class: "link", text: placement.theme.name });
  if (!placement.hanging_on.length) return [name];
  return [name, " (on ", ...wallLinks(placement.hanging_on), ")"];
}

function joined(parts) {
  return parts.flatMap((part, at) => (at ? ["; ", ...part] : part));
}

/* Paint the strip from `page.where.placements`. `said` is a sentence about the
 * act just taken, kept in the strip's status line.
 *
 * **Kept off every wall is an exception, and quiet**: one muted line at the end
 * of what it qualifies, with its undo, said only when it is true. While it is,
 * *Hang…* leaves the toolbar, since a hang would put up a work every wall is
 * told to keep down. */
function paintStrip(page, { said = "" } = {}) {
  const { work, strip } = page;
  const placements = page.where.placements;
  const held = work.status === "accepted";
  const themes = placements.themes.filter((placement) => !placement.theme.hidden);
  const walls = wallsHanging(placements);
  const kept = held ? placements.excluded_at : null;

  const lines = [];
  if (held && !kept) {
    lines.push(["Walls", walls.length ? el("span", {}, wallLinks(walls)) : "Not hanging on any wall."]);
  }
  lines.push(["Themes", themes.length ? el("span", {}, joined(themes.map(themeLine))) : "In no theme."]);

  const keptLine = kept
    ? el("p", { class: "muted kept-off" }, [
        `Kept off every wall since ${dated(kept)}. `,
        el("button", {
          class: "action quiet",
          type: "button",
          text: "Allow on walls again",
          onclick: (event) => allowAgain(event.currentTarget, page),
        }),
      ])
    : null;
  if (page.hang) page.hang.hidden = Boolean(kept);

  const status = el("p", { class: "strip-said", role: "status" });
  fill(strip, facts(lines), keptLine, status);
  // Filled a task later, as a live region must be to be heard
  // (`accessibility-spec.md` § Announcement and semantics).
  if (said) window.setTimeout(() => (status.textContent = said), 0);
}

/* Read the placements afresh and repaint the strip with a sentence about the
 * act, putting the keyboard on `focus`, the control that stands where the
 * pressed one stood. */
async function refreshStrip(page, said, focus) {
  page.where.placements = await api(placementsPath(page.work.artwork_id));
  if (!page.strip.isConnected) return;
  paintStrip(page, { said });
  if (focus && !focus.hidden) focus.focus();
}

/* *Hang…*: the walls are read when it is pressed, never from an earlier paint,
 * since what hangs on each is part of the question. With one wall the question
 * is asked directly, since a choice of one is not a choice; with several, a
 * dialog offers each, and the one pressed is asked about. */
async function chooseWall(control, page) {
  const { work } = page;
  let walls = null;
  const read = await attempt(control, `hang ${work.title}`, async () => {
    walls = (await api("/api/walls")).walls;
  });
  if (!read) return;
  if (walls.length === 1) {
    await hangOn(control, walls[0], page);
    return;
  }
  if (!walls.length) {
    openPanel({ title: `Hang ${work.title}`, lead: "There is no wall to hang it on yet." });
    return;
  }
  const panel = openPanel({
    title: `Hang ${work.title} on…`,
    body: [
      el(
        "div",
        { class: "stack wall-choices" },
        walls.map((wall) =>
          el("button", {
            class: "action quiet",
            type: "button",
            text: wall.name,
            // The choice closes first, so the question that follows hands the
            // keyboard back to *Hang…*, not to a dialog that is gone.
            onclick: () => {
              panel.close();
              hangOn(control, wall, page);
            },
          }),
        ),
      ),
    ],
    closeLabel: "Cancel",
  });
}

/* Ask, hang, and say what reached the wall: the build names a work that was
 * hung and cannot be shown yet, and why, which a curator should hear now rather
 * than notice at the wall. */
async function hangOn(control, wall, page) {
  const { work } = page;
  await hangSelection({
    control,
    artworkIds: [work.artwork_id],
    title: work.title,
    wall,
    then: async (build) => {
      const left = build.exclusions.find((exclusion) => exclusion.artwork_id === work.artwork_id);
      const said = left ? `Hung on ${build.wall_name}, but it cannot be shown yet: ${left.detail}` : `Hung on ${build.wall_name}.`;
      await refreshStrip(page, said, page.hang);
    },
  });
}

/* *Add to theme…*: the selection's dialog (`core/membership.js`), for this one
 * work. The themes are read when it is pressed; a theme already holding the
 * work is not offered, since adding it there would do nothing. */
async function addToTheme(control, page) {
  const { work } = page;
  let themes = null;
  const read = await attempt(control, `add ${work.title} to a theme`, async () => {
    themes = offeredThemes(await api("/api/themes"));
  });
  if (!read) return;
  const holding = new Set(page.where.placements.themes.map((placement) => placement.theme.theme_id));
  const confirm = el("button", { class: "action add-confirm", type: "button" });
  const settle = () => {
    confirm.disabled = !choice.ready();
    confirm.textContent = `Add to ${choice.destination()}`;
  };
  const choice = themeChoice(themes.filter((theme) => !holding.has(theme.theme_id)), { known: themes, onChange: settle });
  settle();
  const panel = openPanel({ title: `Add ${work.title} to a theme`, body: choice.fields, actions: [confirm], closeLabel: "Cancel" });
  confirm.addEventListener("click", () =>
    attempt(confirm, `add ${work.title} to ${choice.destination()}`, async () => {
      const theme = await choice.chosen();
      await addWorksToTheme(theme.theme_id, [work.artwork_id]);
      // Closed before the strip takes the keyboard, so the dialog handing
      // focus back to its opener does not land after it.
      panel.close();
      await refreshStrip(page, `Added ${work.title} to ${theme.name}.`, control);
    }),
  );
}

/* The undo for *Remove…* from every wall. The work goes back on the walls whose
 * theme holds it as the undo lands, and the sentence says so. */
async function allowAgain(control, page) {
  const { work } = page;
  await attempt(control, `allow ${work.title} on walls again`, () => api(`/api/exclusions/${encodeURIComponent(work.artwork_id)}`, { method: "DELETE" }), {
    then: () => refreshStrip(page, ALLOWED_AGAIN, page.hang),
  });
}

/* Said after the undo, in the words `art_theme(action='allow_again')` uses, so
 * an agent and a click are told one thing about when the work returns. */
const ALLOWED_AGAIN = RESTORE_CONSEQUENCE;

/* *Match on Wikidata…*: which item the work is, corrected in a dialog
 * (`core/identity.js`), its form open since opening the dialog was the asking.
 * The page repaints from the record the route answers with. */
function matchOnWikidata(trigger, page) {
  const { work } = page;
  const panel = openPanel({
    title: `Match ${work.title} on Wikidata`,
    body: [
      identityControl("work", work, (answer) => {
        panel.close();
        paint(answer, page.generation, { where: page.where, focus: "more" });
      }, { open: true }),
    ],
  });
}

/* *Archive…* behind ⋯, and *Restore* in its place once it is archived.
 *
 * The two directions of one state machine, so a page offers only the one the
 * work's status leaves available. Nothing alarming either way: both are
 * ordinary reversible acts, and there is no danger class in this stylesheet to
 * reach for. `control` is what was pressed (⋯ for Archive…), and a refusal is
 * said beside it. */
async function archive(control, page) {
  const { work } = page;
  const act = `archive ${work.title}`;
  let showing = null;
  // The walls are asked before the question, which needs them; a failure there
  // is this act failing, and is said beside it.
  const asked = await attempt(control, act, async () => {
    showing = await wallsShowing(work.artwork_id);
  });
  if (!asked) return;
  const agreed = await confirmAct({
    title: `Archive ${work.title}?`,
    consequence: wallConsequence(showing),
    confirmLabel: "Archive",
  });
  if (!agreed) return;
  await attempt(control, act, () => api(`${workPath(work.artwork_id)}/archive`, { method: "POST" }), {
    then: (detail) => paint(detail, page.generation, { where: page.where, focus: "primary" }),
  });
}

async function restore(control, page) {
  const { work } = page;
  const agreed = await confirmAct({
    title: `Restore ${work.title}?`,
    consequence: RESTORE_CONSEQUENCE,
    confirmLabel: "Restore",
  });
  if (!agreed) return;
  await attempt(control, `restore ${work.title}`, () => api(`${workPath(work.artwork_id)}/restore`, { method: "POST" }), {
    then: (detail) => paint(detail, page.generation, { where: page.where, focus: "primary" }),
  });
}

/* Which walls are showing this work, asked of the walls themselves.
 *
 * **Evaluated, never predicted.** `GET /api/manifest` builds a wall's manifest
 * without writing it, applying the same five exclusion rules the real build
 * applies — so a work that is in a hung theme but has no rendition is in that
 * wall's *exclusions* and not on its wall, and archiving it costs that room
 * nothing. A client that answered this from theme membership would name a wall
 * that was never showing the picture, which is a confirmation teaching the
 * curator that its sentences are guesses.
 *
 * **Per wall, because the manifest is per wall.** Two rooms hang different
 * themes and are asked separately. A wall with nothing hanging is not asked at
 * all — the route refuses one, and correctly: there is no theme to evaluate, and
 * a room showing nothing cannot lose a picture.
 *
 * The same two-request shape the Walls screen uses. It is written here rather
 * than shared because a `core/` module is what two callers earn, and these two
 * want different answers out of the same reads — that screen renders every
 * manifest, this one asks a single yes-or-no of each. */
async function wallsShowing(artworkId) {
  const walls = await api("/api/walls");
  const hung = walls.walls.filter((wall) => wall.theme);
  const builds = await Promise.all(
    hung.map(async (wall) => [wall, await api(`/api/manifest?wall_id=${encodeURIComponent(wall.wall_id)}`)]),
  );
  return builds
    .filter(([, manifest]) => manifest.entries.some((entry) => entry.artwork_id === artworkId))
    .map(([wall]) => wall.name);
}

/* The sentence that names which walls lose the picture, or no sentence at all.
 *
 * **The empty string is a real answer and not a degenerate one.** `confirmAct`
 * renders no description element for it, which is the difference between a
 * confirmation that says nothing about the wall because there is nothing to say
 * and one that says nothing because it never looked.
 *
 * **It says "now"**, because the archive takes the work off every feed as it
 * lands, and that Restore brings it back, which it does as the restore lands. It
 * is worded to survive more than one wall — these names can be walls hanging
 * *different* themes, so it cannot say "that theme". */
function wallConsequence(names) {
  if (!names.length) return "";
  const walls = names.length === 1 ? names[0] : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
  const showing = names.length === 1 ? "is showing" : "are showing";
  const losing = names.length === 1 ? "loses" : "lose";
  // Now, not at the next hang: Programming takes an archived work off every
  // published feed that carries it as the archive lands
  // (`tests/unit/test_reconciliation.py`).
  return `${walls} ${showing} this work, and ${losing} it now. It stays in the theme, and Restore brings it back.`;
}

/* The artist's name as the way to their page, `#artist/<id>`. */
function artistLink(artist) {
  return link({ view: "artist", id: artist.artist_id }, { class: "link", text: artist.name });
}
