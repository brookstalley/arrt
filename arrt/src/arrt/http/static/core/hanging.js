/* Putting a theme on a wall — the one act the IA gives a confirmation contract to.
 *
 * **In `core/` because two screens perform the identical act.** The Theme screen
 * offers "Hang on the living room" beside a theme; the Walls screen offers a
 * theme picker beside a wall. Same question, same endpoint, same sentence — and
 * `screens/` modules may not import each other (`architecture.md` § Components &
 * Responsibilities), so shared vocabulary lives here or it lives twice. It lived
 * twice until Critic review found it, down to the wording of the question, which
 * is the shape this repository has already been bitten by once: a sentence
 * duplicated across two files with a comment in each saying they must match and
 * nothing checking it.
 *
 * **The sentence matters more than the request does.** Hanging is the act flow 6
 * singles out for a confirmation, because it is the one that changes what other
 * people in the house see. A change made to the question in one screen and not
 * the other ships two different questions for one act, and the curator has no
 * way to know which one they answered.
 *
 * **The preview is fetched at the moment the question is asked**, never taken
 * from whatever the screen last painted: the consequence sentence is a statement
 * about the manifest that would result now, and a stale one would promise a wall
 * something a rebuild is about to contradict.
 *
 * **What each screen does afterwards is theirs**, which is the only thing that
 * genuinely differed — the Theme screen leaves for the Walls screen to show the
 * result, the Walls screen repaints in place. That is the parameter.
 */

import { attempt, reportElsewhere } from "./acting.js";
import { api } from "./api.js";
import { confirmAct } from "./confirm.js";

/* Ask, and hang if the answer is yes. `control` is what was pressed, and a
 * preview or a hang that fails is said beside it (`core/acting.js`).
 *
 * Returns whether it hung, so a caller can tell a declined question from a
 * completed one without inferring it from the screen not having changed.
 *
 * The question names the theme *and* the wall even while there is one wall. A
 * sentence that reads correctly today only because there is a single possible
 * target is the last place a mistake could have been caught, and it silently
 * stops being true when the second display arrives. */
export async function hangTheme({ control, themeId, themeName, wall, then }) {
  const act = `hang ${themeName} on ${wall.name}`;
  let preview = null;
  const previewed = await attempt(control, act, async () => {
    preview = await api(`/api/manifest?wall_id=${encodeURIComponent(wall.wall_id)}&theme_id=${encodeURIComponent(themeId)}`);
  });
  if (!previewed) return false;
  const confirmed = await confirmAct({
    title: `Hang ${themeName} on ${wall.name}?`,
    consequence: `${preview.summary} Everyone in the house sees ${wall.name} change.`,
    confirmLabel: "Hang",
  });
  if (!confirmed) return false;

  return attempt(
    control,
    act,
    () =>
      api(`/api/themes/${encodeURIComponent(themeId)}/activate`, {
        method: "POST",
        body: JSON.stringify({ wall_id: wall.wall_id }),
      }),
    { then },
  );
}

/* *Hang…* on a theme's page: the walls ticked where it should hang, as one
 * change asked once (ruling 9 of 2026-10-27, in place of a button per wall and
 * *Take down*). `hangOn` are the walls newly ticked and `takeDownFrom` those
 * unticked; a wall left as it was is in neither and is sent nothing, so a
 * theme already hanging is never re-hung from here (that republish is Walls').
 *
 * **One question naming every wall it changes**, for `hangTheme`'s reason: the
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
  const previews = [];
  const previewed = await attempt(control, `hang ${themeName}`, async () => {
    for (const wall of hangOn) {
      const preview = await api(`/api/manifest?wall_id=${encodeURIComponent(wall.wall_id)}&theme_id=${encodeURIComponent(themeId)}`);
      previews.push(`${wall.name}: ${preview.summary}`);
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
