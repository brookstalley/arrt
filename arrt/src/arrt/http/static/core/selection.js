/* Hanging chosen works on a wall, by themselves, until something else is hung there.
 *
 * **In `core/` because the act is not the Work page's alone**: the IA gives
 * *Hang…* to any selection (Artist, Search, Topic), and `screens/` modules do
 * not import each other. One question, one sentence, one route.
 *
 * **It changes a wall, so it asks first**, through `core/confirm.js`, and the
 * question names the works and the wall, as hanging a theme's does
 * (`core/hanging.js`). The consequence says what comes down: a curator hanging
 * one picture over the theme a room has been rotating through should know the
 * rotation stops.
 *
 * There is no preview to fetch, unlike a theme's: the selection does not exist
 * until it is hung, and the build that answers the hang says what reached the
 * wall and what did not.
 */

import { attempt } from "./acting.js";
import { api } from "./api.js";
import { confirmAct } from "./confirm.js";

/* What a wall would stop showing, said after "in place of". */
function replacing(wall) {
  if (!wall.theme) return "";
  return wall.theme.hidden ? ", in place of the works hung there now" : `, in place of ${wall.theme.name}`;
}

/* The question, for `title` (the works, as a curator would name them) on `wall`. */
export function hangQuestion(title, wall) {
  return {
    title: `Hang ${title} on ${wall.name}?`,
    consequence: `${wall.name} shows it until something else is hung there${replacing(wall)}. Everyone in the house sees ${wall.name} change.`,
    confirmLabel: "Hang",
  };
}

/* Ask, and hang `artworkIds` on `wall` if the answer is yes. `control` is what
 * was pressed, and a refusal is said beside it (`core/acting.js`). `then` is
 * handed the manifest build the hang answers with.
 *
 * Returns whether it hung, so a declined question and a failed hang are told
 * apart from a completed one. */
export async function hangSelection({ control, artworkIds, title, wall, then }) {
  const confirmed = await confirmAct(hangQuestion(title, wall));
  if (!confirmed) return false;
  return attempt(
    control,
    `hang ${title} on ${wall.name}`,
    () =>
      api(`/api/walls/${encodeURIComponent(wall.wall_id)}/selection`, {
        method: "POST",
        body: JSON.stringify({ artwork_ids: artworkIds }),
      }),
    { then },
  );
}
