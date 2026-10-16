/* The mat, drawn in the browser as a wall draws it.
 *
 * The server composes no canvas: each Player draws a work inside its mat, by
 * the rule in `player-contract.md` § Layout. The Work page shows the work as a
 * wall shows it, mat and all, so it draws by the same rule. `matLayout` is that
 * rule, ported line for line from the Player's `layout`
 * (`arrt-player/src/arrt_player/compose.py`), and the browser suite runs every
 * vector in `contract/vectors/mat-geometry.json` through it, so the two cannot
 * drift without a test saying so.
 *
 * **The page is a screen with no known density**, as an HDMI monitor is: it
 * cannot know its physical size, so the mat takes the contract's relative
 * width, a share of the shorter side, and the Player's default bottom weight.
 *
 * `mattedPicture` takes its colour as an argument rather than reading the work's
 * current mat, so the same drawing can show a colour that has not been chosen
 * yet, beside the one that has. */

import { el } from "./render.js";

/* The contract's share of the screen's shorter side, for a screen of unknown
 * density. Checked against the vectors file's `relative_width`. */
export const RELATIVE_MAT_WIDTH = 0.06;

/* The bottom margin over the side margin: a true-centred picture reads as
 * sitting low. The Player's default, which the no-density vectors carry. */
export const BOTTOM_WEIGHT = 1.15;

export const MAT_MODES = ["none", "proportional", "full"];

/* A mat colour the catalogue would hold: `#rrggbb`. Anything else draws no mat,
 * as a Player does, because inventing a colour would put up a mat the Library
 * never chose. Checked here as well as by the catalogue because the colour
 * becomes a style value. */
const HEX = /^#[0-9a-fA-F]{6}$/;

export function isMatColour(value) {
  return typeof value === "string" && HEX.test(value);
}

/* The contract's rounding: half up, as the Player's `floor(x + 0.5)`. */
function roundHalfUp(value) {
  return Math.floor(value + 0.5);
}

/* The side-and-top margin and the bottom margin, in whole pixels. */
function margins({ screen, pixelsPerInch, matWidthInches, bottomWeight, mode }) {
  if (mode === "none") return [0, 0];
  const side =
    pixelsPerInch === null || pixelsPerInch === undefined
      ? roundHalfUp(RELATIVE_MAT_WIDTH * Math.min(screen.width, screen.height))
      : roundHalfUp(matWidthInches * pixelsPerInch);
  return [side, roundHalfUp(side * bottomWeight)];
}

/* Where the work and its mat go on one screen, in whole pixels from its top
 * left: `{ work, mat }`, each `{ left, top, width, height }`, `mat` null in
 * mode `none`.
 *
 * **The work is centred in the box, not on the screen.** The box sits higher
 * than centre because its bottom margin is the deeper one, and centring on the
 * screen would undo the bottom weighting while every size stayed right. A work
 * smaller than the box is not enlarged. */
export function matLayout({ screen, work, mode = "proportional", pixelsPerInch = null, matWidthInches = null, bottomWeight = BOTTOM_WEIGHT }) {
  const [side, bottom] = margins({ screen, pixelsPerInch, matWidthInches, bottomWeight, mode });
  const boxW = Math.max(1, screen.width - 2 * side);
  const boxH = Math.max(1, screen.height - side - bottom);
  const scale = Math.min(boxW / work.width, boxH / work.height, 1.0);
  const width = Math.max(1, roundHalfUp(work.width * scale));
  const height = Math.max(1, roundHalfUp(work.height * scale));
  const placed = { left: side + Math.floor((boxW - width) / 2), top: side + Math.floor((boxH - height) / 2), width, height };
  let mat;
  if (mode === "none") mat = null;
  else if (mode === "full") mat = { left: 0, top: 0, width: screen.width, height: screen.height };
  else mat = { left: placed.left - side, top: placed.top - side, width: width + 2 * side, height: height + side + bottom };
  return { work: placed, mat };
}

/* The work's size the right way up: the master's pixels, turned to the
 * picture's own orientation when the file is stored on its side. */
function upright(size, image) {
  const portrait = image.naturalHeight > image.naturalWidth;
  return portrait === size.height > size.width ? size : { width: size.height, height: size.width };
}

/* The work inside its mat, in `hex`, filling the width it is given and no more
 * than `maxHeight()` pixels tall: the proportional mode, which hugs the work.
 *
 * `size` is the master's `{ width, height }`, so a picture is enlarged only as
 * far as the master allows, as on a wall; the image's own size stands in when
 * the master's is not known. Laid out again whenever the width it is given
 * changes. Returns the element and `paint(hex)`, which recolours it. */
export function mattedPicture(image, { hex, size = null, maxHeight = () => window.innerHeight * 0.75 }) {
  const mat = el("div", { class: "mat-surround" });
  const frame = el("div", { class: "matted" }, [mat, image]);
  let colour = null;

  const paint = (next) => {
    colour = isMatColour(next) ? next : null;
    frame.classList.toggle("unmatted", colour === null);
    if (colour) mat.style.setProperty("--mat", colour);
    else mat.style.removeProperty("--mat");
    lay();
  };

  function lay() {
    const width = Math.floor(frame.clientWidth);
    if (!width || !image.naturalWidth) return;
    const natural = { width: image.naturalWidth, height: image.naturalHeight };
    const work = size ? upright(size, image) : natural;
    const screen = { width, height: Math.max(1, Math.floor(maxHeight())) };
    const placed = matLayout({ screen, work, mode: colour ? "proportional" : "none" });
    // The canvas is cut to the mat, so the page holds no band of nothing above
    // or below it; with no mat, to the work.
    const outer = placed.mat || placed.work;
    Object.assign(image.style, {
      left: `${placed.work.left}px`,
      top: `${placed.work.top - outer.top}px`,
      width: `${placed.work.width}px`,
      height: `${placed.work.height}px`,
    });
    Object.assign(mat.style, {
      left: `${outer.left}px`,
      width: `${outer.width}px`,
      height: `${outer.height}px`,
    });
    frame.style.height = `${outer.height}px`;
    frame.dataset.layout = JSON.stringify(placed);
  }

  if (image.complete) queueMicrotask(lay);
  image.addEventListener("load", lay);
  new ResizeObserver(lay).observe(frame);
  paint(hex);
  return { element: frame, paint, colour: () => colour };
}
