/* Putting a set of works into a theme: the one act two screens share.
 *
 * **In `core/` because Artworks and the Artist page both do it** to a selection,
 * and `screens/` modules never import each other (`architecture.md` § Components
 * & Responsibilities). A copy in each would be two answers to "what happens to a
 * work the theme already holds?", and only one of them would be kept right.
 *
 * **Read before writing.** The store refuses a work the theme already holds, and
 * a loop that discovered that halfway through would have applied half the edit
 * and reported a refusal. So the theme's members are read first and only the
 * works it lacks are sent. */

import { api } from "./api.js";

/* Add `artworkIds` to the theme, skipping those already in it.
 *
 * `onAdded` is told each id as it lands, so a screen can untick it at once. A
 * failure part way is rethrown, carrying `progress`, so the caller can say how
 * far it got while the server's own words say why it stopped. */
export async function addWorksToTheme(themeId, artworkIds, { onAdded = () => {} } = {}) {
  const detail = await api(`/api/themes/${encodeURIComponent(themeId)}`);
  const held = new Set(detail.works.map((work) => work.artwork_id));
  const wanted = artworkIds.filter((artworkId) => !held.has(artworkId));
  const already = artworkIds.length - wanted.length;
  let added = 0;
  try {
    for (const artworkId of wanted) {
      await api(`/api/themes/${encodeURIComponent(themeId)}/works`, {
        method: "POST",
        body: JSON.stringify({ artwork_id: artworkId }),
      });
      added += 1;
      onAdded(artworkId);
    }
  } catch (failure) {
    failure.progress = { added, wanted: wanted.length, already };
    throw failure;
  }
  return { added, wanted: wanted.length, already };
}

/* What happened, as one sentence for a live region. */
export function addedSentence({ added, wanted, already }, themeName) {
  if (!wanted) return `All ${already} ${already === 1 ? "was" : "were"} already in ${themeName}.`;
  const carried = already ? ` ${already} ${already === 1 ? "was" : "were"} already in it.` : "";
  return `Added ${added} ${added === 1 ? "work" : "works"} to ${themeName}.${carried}`;
}

/* How far a failed add got, for the same live region. */
export function stoppedSentence({ added, wanted }, themeName) {
  return `Added ${added} of ${wanted} to ${themeName}. The rest are still selected, so pressing Add again retries only those.`;
}
