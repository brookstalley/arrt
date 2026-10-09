/* Every glyph a badge or a state line draws, keyed by what it means.
 *
 * **One glyph, one meaning, across every screen** (`design-direction.md`
 * § Component Patterns, Badges). A glyph is the signal that survives greyscale
 * and a dimmed room, so a reader learns it once: ● on a Work page and ● on the
 * Queue have to say the same thing. The word beside it carries the specifics
 * ("below minimum", "the Get found an image", "on The wall"); the glyph carries
 * only the kind of state. Before this table each screen chose its own, and ◇
 * meant three different things depending on where it was read.
 *
 * So a screen never writes a glyph literal: it names a meaning here, and
 * `tests/unit/test_glyphs_have_one_meaning.py` fails on a literal anywhere else and on two
 * meanings sharing a glyph. A new meaning is a new key, never a reused glyph.
 *
 * The sidebar's section icons are not badges and live with the sections in
 * `app.js`. Where one of them is also here it means the same thing (↻ Activity
 * and fetching; ◑ Wanted and wanted), and the test holds that overlap to those. */
export const GLYPHS = Object.freeze({
  // Present, done, well: found, resolved, in your library, on a wall.
  good: "●",
  // Looked, and there is none: a source holding nothing, not held.
  none: "○",
  // Not held, but an image is known for it.
  imageFound: "◐",
  // Waiting on the machine: queued, asking, not looked up, a Get still running.
  waiting: "◌",
  // In motion: an image being fetched.
  moving: "↻",
  // Stopped on purpose until somebody resumes it.
  paused: "‖",
  // Waiting on the curator's verdict.
  forReview: "◔",
  // Went wrong, or falls short: failed, gave up, below the minimum, unreachable,
  // the Get found none, unwell.
  problem: "▲",
  // Turned away: turned down, refused, archived, kept off every wall.
  refused: "⊘",
  // Affirmed: the curator said yes, or a source recorded the value.
  yes: "✓",
  // The curator said no: rejected, declines.
  no: "✗",
  // Wanted, and no acceptable scan is held.
  wanted: "◑",
  // Picked out above the rest: the default theme, the image on offer, loves.
  picked: "★",
  // Liked, short of picked.
  liked: "☆",
  // Lukewarm.
  cool: "◦",
  // Put forward by the product: asked for, suggested.
  putForward: "◆",
  // Offered by a source rather than asked for.
  offered: "◈",
  // Chosen by the curator from what was offered.
  chosen: "◎",
  // The wall render, as opposed to the master image.
  render: "▤",
  // The master image, where no wall render exists yet.
  master: "□",
  // A state this client has no words for, drawn as itself.
  unknown: "?",
  // Cannot be said: no size known, nothing to compare.
  cannot: "—",
});
