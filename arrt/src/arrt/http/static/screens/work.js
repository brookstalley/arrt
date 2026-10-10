/* Work — one work at full size, what it is said to be, where it hangs, and the
 * acts that hang it, take it out of circulation and put it back.
 *
 * Contextual: reached from a tile in Artworks, a tile on a Wall, or a row in
 * Review, and it **returns to the page it was opened from**. That is the
 * requirement `information-architecture.md` states under Back/escape, and the
 * back control here reads it off the address rather than naming a fixed parent —
 * this screen's route out used to be "← All works" whatever route in had been
 * taken.
 *
 * **The picture comes first and the label sits under it.** The governing rule is
 * that the artwork is the primary content on every screen that shows one and
 * chrome yields to it; a title above the image puts a line of interface between
 * the reader and the thing they opened.
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
import { absentImage, facts, fitBadge, pixelSize, statusBadge, table } from "../core/badges.js";
import { confirmAct } from "../core/confirm.js";
import { counted } from "../core/counting.js";
import { dated } from "../core/dates.js";
import { GLYPHS } from "../core/glyphs.js";
import { FETCH_WORDS, museumName, RIGHTS_WORDS } from "../core/providers.js";
import { enlarge } from "../core/enlarge.js";
import { getOne } from "../core/getting.js";
import { identityControl } from "../core/identity.js";
import { el, emphasised, fill, render } from "../core/render.js";
import { isQid, listHeadings, named, personLink, stateMark, wikidataLink, workCell, workState, year, yearCell } from "../core/registry.js";
import { backLink, link, redirect, setTitle } from "../core/router.js";
import { hangSelection } from "../core/selection.js";

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
  render(
    generation,
    el("p", {}, [backLink()]),
    el("div", { class: "panel" }, [
      top,
      el("div", { class: "card-footer" }, [stateMark({ wanted: page.wanted, image: Boolean(page.image) })]),
    ]),
    el("div", { class: "panel" }, [
      el("h1", { text: title }),
      facts([
        ["Artist", page.creators.length ? el("span", {}, page.creators.flatMap((person, at) => (at ? [", ", personLink(person)] : [personLink(person)]))) : null],
        ["Date", page.year === null ? null : year(page.year)],
        ["Size", workSize(page.height_cm, page.width_cm)],
        ["Medium", page.media.join(", ")],
        ["Held by", page.holders.length ? page.holders.map(holderLine).join("; ") : null],
      ]),
      el("p", { class: "muted" }, [wikidataLink(qid, `Wikidata ${qid}`)]),
      getOne(qid),
      el("p", { class: "muted", text: GET_LINE }),
    ]),
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
 * Separate from the fetch because archive and restore answer with the same
 * dossier `GET /api/works/{id}` does — so the act repaints from what the server
 * actually recorded rather than from the client's opinion of what it asked for.
 * Neither changes which themes hold the work, so `where` — the work's
 * placements, which the state strip refreshes after its own acts — is carried over.
 *
 * `focusAction` is how the keyboard survives that repaint. The act's own button
 * is replaced by its opposite, and a screen that rebuilt itself under a focused
 * control would drop focus to `<body>`, leaving the next Tab at the top of the
 * page. This is not a poll — the accessibility rule that a poll must never move
 * focus is about paints the curator did not ask for, and this one is the direct
 * answer to a button they pressed.
 *
 * **The picture is the largest thing here**: on this page the subject is the
 * work. It is drawn from the master; the mat is drawn by the Player at each
 * wall, in the colour the mat panel below names. The title under
 * it is the page's one `h1`, and the state strip under that says where the work
 * is and offers *Hang…*, the act a curator most often comes here for. Archive is
 * secondary, after the facts: it takes the work out of the whole library, and
 * the loudest button on a page reached from a wall must not be that one. */
function paint(detail, generation, { where, focusAction = false }) {
  const work = detail.work;
  setTitle(generation, work.title);
  const image = work.image.available
    ? el("img", {
        class: "detail-image work-picture",
        // The work at a size this column draws sharply; a tile's thumbnail is a
        // fraction of this width.
        src: `${workPath(work.artwork_id)}/wall-preview`,
        alt: work.artist ? `${work.title}, by ${work.artist.name}` : work.title,
      })
    : el("p", { class: "note", text: work.image.note || "No image held." });
  const action = circulationControl(work, generation, where);
  const strip = el("section", { class: "state-strip", "aria-label": "Where it is" });
  paintStrip(strip, work, where);

  const head = [
    el("div", { class: "panel work-hero" }, [
      image,
      el("div", { class: "card-footer" }, [statusBadge(work), fitBadge(work)]),
      work.fit_note ? el("p", { class: "muted", text: work.fit_note }) : null,
    ]),
    el("div", { class: "panel work-label" }, [
      el("h1", { text: work.title }),
      strip,
      facts([
        ["Artist", work.artist ? artistLink(work.artist) : null],
        ["Nationality", work.artist ? work.artist.nationality : null],
        ["Lifespan", work.artist ? work.artist.lifespan_text : null],
        ["Date", work.date_created],
        ["Medium", work.medium],
        ["Dimensions", work.dimensions],
        ["Rights", work.rights],
        // No "Status" row, and its absence is the rule rather than an omission.
        // A screen states a fact once: the badge under the picture already says
        // `archived` when that is true and says nothing when it is not, which is
        // the same inversion the derivation footnote uses. A second, plainer copy
        // three lines below would invite the reader to look for the difference
        // between them, and one of the two would eventually be the stale one.
        ["Description", work.description ? emphasised(work.description) : null],
      ]),
      el("div", { class: "row secondary-actions" }, [action]),
      // The control repaints from the dossier the route answers with, as
      // archive and restore do.
      identityControl("work", work, (answer) => paint(answer, generation, { where })),
    ]),
  ];

  // The picture beside its label, as on a gallery wall; then the record, each
  // part a section of its own, two to a row where the page is wide enough.
  const panels = [facetPanel(detail.facets)];

  panels.push(
    el("div", { class: "panel" }, [
      el("h2", { text: "Master image" }),
      detail.original
        ? facts([
            ["File", detail.original.relative_path],
            ["Pixels", `${detail.original.width} × ${detail.original.height}`],
            ["Size", `${(detail.original.byte_size / 1048576).toFixed(1)} MB`],
            ["Content hash", detail.original.content_hash],
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

  panels.push(
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

  panels.push(matPanel(detail.mat_colors));

  render(
    generation,
    el("p", {}, [backLink()]),
    el("div", { class: "work-head" }, head),
    el("div", { class: "work-record" }, panels),
  );
  // Only if the paint actually landed. `render` declines a paint whose
  // navigation has been superseded, and focusing a control that was never put on
  // the page would move the keyboard onto a detached node.
  if (focusAction && document.contains(action)) action.focus();
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
    nodes.push(el("span", { class: "facet-value", text: facet.value }));
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

/* -- the state strip: which walls and themes the work is on, and Hang… -------
 *
 * Read from `GET /api/works/{id}/placements`, which lists every theme holding
 * the work with the walls hanging each, selections included. **A selection is
 * said as its wall**, never by its made-up theme name: the curator chose works,
 * not a theme. The server deletes a selection once no wall hangs it; one read
 * hanging nowhere would be an old hang, and is not said at all. A real theme is named, and links to its page.
 *
 * Its acts — *Hang…* and *Allow on walls again* — repaint the strip alone, from
 * the placements read afresh after the act, and put the keyboard back on
 * *Hang…*, the control that stands where the pressed one stood or beside it. */


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
  return [name, ` (on ${placement.hanging_on.map((wall) => wall.name).join(", ")})`];
}

function joined(parts) {
  return parts.flatMap((part, at) => (at ? ["; ", ...part] : part));
}

/* Paint the strip from `where.placements`. `said` is a sentence about the act
 * just taken, kept in the strip's status line; `focusHang` puts the keyboard on
 * *Hang…* (or on the undo while it is the strip's only control). */
function paintStrip(strip, work, where, { said = "", focusHang = false } = {}) {
  const placements = where.placements;
  const held = work.status === "accepted";
  const themes = placements.themes.filter((placement) => !placement.theme.hidden);
  const walls = wallsHanging(placements);
  const kept = placements.excluded_at;

  const lines = [];
  if (held && kept) {
    lines.push(["Walls", `Kept off every wall since ${dated(kept)}.`]);
  } else if (held) {
    lines.push(["Walls", walls.length ? walls.map((wall) => wall.name).join(", ") : "Not hanging on any wall."]);
  }
  lines.push(["Themes", themes.length ? el("span", {}, joined(themes.map(themeLine))) : "In no theme."]);

  const status = el("p", { class: "strip-said", role: "status" });
  const picker = el("div", { class: "row wall-picker", hidden: true });
  let control = null;
  if (held && kept) {
    control = el("button", {
      class: "action",
      type: "button",
      text: "Allow on walls again",
      onclick: (event) => allowAgain(event.currentTarget, strip, work, where),
    });
  } else if (held && work.image.available) {
    control = el("button", {
      class: "action",
      type: "button",
      text: "Hang…",
      "aria-expanded": "false",
      onclick: (event) => chooseWall(event.currentTarget, picker, strip, work, where),
    });
  }

  fill(strip, facts(lines), control ? el("div", { class: "row" }, [control]) : null, picker, status);
  // Filled a task later, as a live region must be to be heard
  // (`accessibility-spec.md` § Announcement and semantics).
  if (said) window.setTimeout(() => (status.textContent = said), 0);
  if (focusHang && control) control.focus();
}

/* Read the placements afresh and repaint the strip with a sentence about the act. */
async function refreshStrip(strip, work, where, said) {
  where.placements = await api(placementsPath(work.artwork_id));
  if (strip.isConnected) paintStrip(strip, work, where, { said, focusHang: true });
}

/* *Hang…*: the walls are read when it is pressed, never from an earlier paint,
 * since what hangs on each is part of the question. One wall is asked about
 * directly; several are offered, one button each, beside the control. */
async function chooseWall(control, picker, strip, work, where) {
  let walls = null;
  const read = await attempt(control, `hang ${work.title}`, async () => {
    walls = (await api("/api/walls")).walls;
  });
  if (!read) return;
  if (!walls.length) {
    fill(picker, el("p", { class: "muted", text: "There is no wall to hang it on yet." }));
    picker.hidden = false;
    return;
  }
  if (walls.length === 1) {
    await hangOn(control, walls[0], strip, work, where);
    return;
  }
  const close = () => {
    picker.hidden = true;
    fill(picker);
    control.setAttribute("aria-expanded", "false");
    control.focus();
  };
  fill(
    picker,
    el("span", { class: "muted", text: "On which wall?" }),
    ...walls.map((wall) =>
      el("button", {
        class: "action quiet",
        type: "button",
        text: wall.name,
        onclick: (event) => hangOn(event.currentTarget, wall, strip, work, where),
      }),
    ),
    el("button", { class: "action quiet", type: "button", text: "Cancel", onclick: close }),
  );
  picker.hidden = false;
  control.setAttribute("aria-expanded", "true");
  picker.querySelector("button").focus();
}

/* Ask, hang, and say what reached the wall: the build names a work that was
 * hung and cannot be shown yet, and why, which a curator should hear now rather
 * than notice at the wall. */
async function hangOn(control, wall, strip, work, where) {
  await hangSelection({
    control,
    artworkIds: [work.artwork_id],
    title: work.title,
    wall,
    then: async (build) => {
      const left = build.exclusions.find((exclusion) => exclusion.artwork_id === work.artwork_id);
      const said = left ? `Hung on ${build.wall_name}, but it cannot be shown yet: ${left.detail}` : `Hung on ${build.wall_name}.`;
      await refreshStrip(strip, work, where, said);
    },
  });
}

/* The undo for *Not this one again* from every wall. The work goes back on the
 * walls whose theme holds it as the undo lands, and the sentence says so. */
async function allowAgain(control, strip, work, where) {
  await attempt(control, `allow ${work.title} on walls again`, () => api(`/api/exclusions/${encodeURIComponent(work.artwork_id)}`, { method: "DELETE" }), {
    then: () => refreshStrip(strip, work, where, ALLOWED_AGAIN),
  });
}

/* Said after the undo, in the words `art_theme(action='allow_again')` uses, so
 * an agent and a click are told one thing about when the work returns. */
const ALLOWED_AGAIN = RESTORE_CONSEQUENCE;

/* Archive, or Restore — whichever this work's status leaves available.
 *
 * One control rather than two, because the two acts are the two directions of
 * one state machine and offering the unavailable one would be offering a
 * refusal. Nothing alarming either way: both are ordinary reversible acts, and
 * there is no danger class in this stylesheet to reach for.
 *
 * **Archive is quiet; Restore is not.** A held work's page is reached to look
 * at it or hang it, and a filled Archive was the loudest button in reach of a
 * curator who had only wanted a picture off one wall. An archived work's page
 * has one thing to offer, and Restore is it. */
function circulationControl(work, generation, where) {
  const archived = work.status !== "accepted";
  return el("button", {
    class: archived ? "action" : "action quiet",
    type: "button",
    text: archived ? "Restore" : "Archive",
    onclick: (event) =>
      archived ? restore(event.currentTarget, work, generation, where) : archive(event.currentTarget, work, generation, where),
  });
}

async function archive(control, work, generation, where) {
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
    then: (detail) => paint(detail, generation, { where, focusAction: true }),
  });
}

async function restore(control, work, generation, where) {
  const agreed = await confirmAct({
    title: `Restore ${work.title}?`,
    consequence: RESTORE_CONSEQUENCE,
    confirmLabel: "Restore",
  });
  if (!agreed) return;
  await attempt(control, `restore ${work.title}`, () => api(`${workPath(work.artwork_id)}/restore`, { method: "POST" }), {
    then: (detail) => paint(detail, generation, { where, focusAction: true }),
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
