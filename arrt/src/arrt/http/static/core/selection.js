/* Hanging chosen works on a wall, by themselves, until something else is hung there.
 *
 * **In `core/` because the act is not the Work page's alone**: the IA gives
 * *Hang…* to any selection (Artist, Search, Topic), and `screens/` modules do
 * not import each other. One question, one sentence, one route. The Work page
 * hangs one work through `hangSelection`; every list's selection hangs what is
 * ticked through `hangOnAWall` (`core/selecting.js`).
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
import { counted } from "./counting.js";
import { openPanel } from "./editing.js";
import { whoSees } from "./hanging.js";
import { el } from "./render.js";

/* What a wall would stop showing, said after "in place of". */
function replacing(wall) {
  if (!wall.theme) return "";
  return wall.theme.hidden ? ", in place of the works hung there now" : `, in place of ${wall.theme.name}`;
}

/* The question, for `title` (the works, as a curator would name them) on `wall`.
 * `count` is how many works that is, so "it" is "them" of a selection;
 * `leftOut` is how many the curator ticked that will not be hung, said first so
 * the question never claims more than the act will do. */
export function hangQuestion(title, wall, { count = 1, leftOut = 0 } = {}) {
  const left = leftOut ? `Left out, as they cannot be shown (no picture yet, or archived): ${counted(leftOut, "work")}. ` : "";
  return {
    title: `Hang ${title} on ${wall.name}?`,
    consequence: `${left}${wall.name} shows ${count === 1 ? "it" : "them"} until something else is hung there${replacing(wall)}. ${whoSees([wall])}`,
    confirmLabel: "Hang",
  };
}

/* Ask, and hang `artworkIds` on `wall` if the answer is yes. `control` is what
 * was pressed, and a refusal is said beside it (`core/acting.js`). `then` is
 * handed the manifest build the hang answers with.
 *
 * Returns whether it hung, so a declined question and a failed hang are told
 * apart from a completed one. */
export async function hangSelection({ control, artworkIds, title, wall, leftOut = 0, then }) {
  const confirmed = await confirmAct(hangQuestion(title, wall, { count: artworkIds.length, leftOut }));
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

/* *Hang…* on a selection: the walls are read when it is pressed, never from an
 * earlier paint, since what hangs on each is part of the question. With one
 * wall the question is asked directly, since a choice of one is not a choice;
 * with several, a dialog offers each, and the one pressed is asked about; with
 * none, the dialog says there is nowhere to hang them yet.
 *
 * The Work page asks the same of one work (`screens/work.js` `chooseWall`),
 * which a `screens/` module cannot lend: this is the selection's, in the same
 * words. `leftOut` and `then` are `hangSelection`'s. Nothing is returned: a
 * dialog of walls is answered by one of its buttons, not by this call. */
export async function hangOnAWall({ control, artworkIds, title, leftOut = 0, then }) {
  let walls = null;
  const read = await attempt(control, `hang ${title}`, async () => {
    walls = (await api("/api/walls")).walls;
  });
  if (!read) return;
  const hangOn = (wall) => hangSelection({ control, artworkIds, title, wall, leftOut, then });
  if (walls.length === 1) {
    await hangOn(walls[0]);
    return;
  }
  if (!walls.length) {
    openPanel({ title: `Hang ${title}`, lead: `There is no wall to hang ${artworkIds.length === 1 ? "it" : "them"} on yet.` });
    return;
  }
  const panel = openPanel({
    title: `Hang ${title} on…`,
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
              hangOn(wall);
            },
          }),
        ),
      ),
    ],
    closeLabel: "Cancel",
  });
}
