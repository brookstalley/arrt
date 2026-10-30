/* Putting a theme on walls — the one act the IA gives a confirmation contract to.
 *
 * **In `core/` because two screens perform it.** Walls' Hanging picker puts a
 * theme on one wall; a theme's page puts it up on, and takes it down from, the
 * walls ticked in its *Hang…* (ruling 9 of 2026-10-27). `screens/` modules may
 * not import each other (`architecture.md` § Components & Responsibilities), so
 * the question lives here, once: `hangTheme` is `hangOnWalls` with one wall. It
 * lived twice once, down to the wording, until a review found it, which is the
 * shape this repository has been bitten by: a sentence duplicated across two
 * files with a comment in each saying they must match and nothing checking it.
 *
 * **The sentence matters more than the request does.** Hanging is the act flow 6
 * singles out for a confirmation, because it is the one that changes what other
 * people in the house see, and a curator answering two wordings of one act has
 * no way to know which they answered.
 *
 * **The preview is fetched at the moment the question is asked**, never taken
 * from whatever the screen last painted: the consequence sentence is a statement
 * about the feed that would result now, and a stale one would promise a wall
 * something a rebuild is about to contradict.
 *
 * **What each screen does afterwards is theirs** (`then`): both repaint in place.
 */

import { attempt, reportElsewhere } from "./acting.js";
import { api } from "./api.js";
import { confirmAct } from "./confirm.js";

/* Ask, and hang `themeName` on `wall` if the answer is yes: Walls' Hanging
 * picker. One wall's case of `hangOnWalls`, so the two screens ask one question
 * in one wording. `control` is what was pressed, and a preview or a hang that
 * fails is said beside it (`core/acting.js`).
 *
 * Returns whether it hung, so a caller can tell a declined question from a
 * completed one without inferring it from the screen not having changed.
 *
 * Unlike a theme's *Hang…*, it hangs even what is hanging already: that is how
 * Walls republishes a wall's feed (the picker lists the theme showing too). */
export function hangTheme({ control, themeId, themeName, wall, then }) {
  return hangOnWalls({ control, themeId, themeName, hangOn: [wall], takeDownFrom: [], then });
}

/* *Hang…* on a theme's page: the walls ticked where it should hang, as one
 * change asked once (ruling 9 of 2026-10-27, in place of a button per wall and
 * *Take down*). `hangOn` are the walls newly ticked and `takeDownFrom` those
 * unticked; a wall left as it was is in neither and is sent nothing, so a
 * theme already hanging is never re-hung from here (that republish is Walls').
 *
 * **One question naming every wall it changes**, for the module's reason: the
 * act changes what other people in the house see, so each wall is named, with
 * the server's preview for each wall it goes up on, fetched as the question is
 * asked. Taking down rewrites no feed: the wall goes on showing what it shows
 * until something else is hung, and the question says so.
 *
 * Returns whether every change was made. `then` runs when any wall changed, so
 * the page repaints to what is now true. A refusal before anything changed is
 * said beside `control` and nothing repaints, so the sentence stays; one after
 * a wall had changed is said where it outlives the repaint
 * (`core/acting.js` `reportElsewhere`), naming the wall it stopped at. */
export async function hangOnWalls({ control, themeId, themeName, hangOn, takeDownFrom, then }) {
  // The question names the theme *and* each wall even while there is one wall.
  // A sentence that reads correctly today only because there is a single
  // possible target is the last place a mistake could have been caught. A lone
  // hang's preview needs no wall's name before it, since the title has just
  // said which wall; with more than one change, each preview says its wall.
  const lone = hangOn.length === 1 && !takeDownFrom.length;
  const previews = [];
  const previewed = await attempt(control, lone ? `hang ${themeName} on ${hangOn[0].name}` : `hang ${themeName}`, async () => {
    for (const wall of hangOn) {
      const preview = await api(`/api/manifest?wall_id=${encodeURIComponent(wall.wall_id)}&theme_id=${encodeURIComponent(themeId)}`);
      previews.push(lone ? preview.summary : `${wall.name}: ${preview.summary}`);
    }
  });
  if (!previewed) return false;
  const names = (walls) => walls.map((wall) => wall.name);
  const listed = (words) => (words.length < 2 ? words.join("") : `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}`);
  const sentences = [...previews];
  if (takeDownFrom.length) {
    sentences.push(
      `Taken down from ${listed(names(takeDownFrom))}, which ${takeDownFrom.length === 1 ? "goes" : "go"} on showing what ${takeDownFrom.length === 1 ? "it shows" : "they show"} until something else is hung there.`,
    );
  }
  sentences.push(`Everyone in the house sees ${listed(names([...hangOn, ...takeDownFrom]))} change.`);
  const confirmed = await confirmAct({
    title: hangOn.length
      ? `Hang ${themeName} on ${listed(names(hangOn))}${takeDownFrom.length ? ` and take it down from ${listed(names(takeDownFrom))}` : ""}?`
      : `Take ${themeName} down from ${listed(names(takeDownFrom))}?`,
    consequence: sentences.join(" "),
    confirmLabel: hangOn.length ? "Hang" : "Take down",
  });
  if (!confirmed) return false;

  const steps = [
    ...hangOn.map((wall) => [
      `hang ${themeName} on ${wall.name}`,
      () => api(`/api/themes/${encodeURIComponent(themeId)}/activate`, { method: "POST", body: JSON.stringify({ wall_id: wall.wall_id }) }),
    ]),
    ...takeDownFrom.map((wall) => [
      `take ${themeName} down from ${wall.name}`,
      () => api(`/api/walls/${encodeURIComponent(wall.wall_id)}/theme`, { method: "DELETE" }),
    ]),
  ];
  let changed = 0;
  let done = true;
  for (const [act, write] of steps) {
    done = await attempt(changed ? null : control, act, write, { elsewhere: reportElsewhere });
    if (!done) break;
    changed += 1;
  }
  if (changed && then) await then(done);
  return done;
}
