/* Putting a set of works into a theme: the one act several screens share.
 *
 * **In `core/` because every list does it to a selection, and the Work page to
 * one work**, with the same *Add to theme…* dialog, and `screens/` modules
 * never import each other (`architecture.md` § Components
 * & Responsibilities). A copy in each would be two answers to "what happens to a
 * work the theme already holds?", and only one of them would be kept right.
 *
 * **Read before writing.** The store refuses a work the theme already holds, and
 * a loop that discovered that halfway through would have applied half the edit
 * and reported a refusal. So the theme's members are read first and only the
 * works it lacks are sent. */

import { api } from "./api.js";
import { el, fill } from "./render.js";

/* The theme picker's value for *New theme…*. Theme ids are UUIDs, so it cannot
 * collide with one. */
const NEW_THEME = "new";

/* Two names for one theme: the curator's spacing and capitals are not a second
 * theme, as a Get's *New theme…* already rules (`core/getting.js`). */
function sameName(one, other) {
  return one.trim().toLowerCase() === other.trim().toLowerCase();
}

/* What *Add to theme…*'s dialog holds, wherever it is opened: a list's
 * selection and one work's page ask the same question, so they ask it with one
 * picker. `themes` is `[{ theme_id, name }]`, the themes offered; *New theme…*
 * is always offered after them, with a field for its name.
 *
 * `fields` go in the dialog's body; `destination()` names the choice for the
 * act's label; `ready()` says whether there is a choice to act on (a new theme
 * needs its name); `chosen()` answers the theme, making it first when it is
 * new. A typed name that is already a theme joins it. Once made, a new theme is
 * offered and chosen, so a second press joins it rather than making another.
 * `onChange` is told whenever the choice or the name changes. */
export function themeChoice(themes, { onChange = () => {} } = {}) {
  const offered = [...themes];
  const picker = el("select", { id: "add-to-theme" });
  const naming = el("input", { type: "text", id: "add-to-theme-name", autocomplete: "off" });
  const namingField = el("span", { class: "selection-field", hidden: true }, [
    el("label", { for: "add-to-theme-name", text: "Name for the new theme" }),
    naming,
  ]);
  const paint = (chosen) => {
    fill(
      picker,
      ...offered.map((theme) => el("option", { value: theme.theme_id, text: theme.name })),
      el("option", { value: NEW_THEME, text: "New theme…" }),
    );
    picker.value = chosen || (offered.length ? offered[0].theme_id : NEW_THEME);
    namingField.hidden = picker.value !== NEW_THEME;
  };
  paint(null);
  const changed = () => {
    namingField.hidden = picker.value !== NEW_THEME;
    onChange();
  };
  picker.addEventListener("change", changed);
  naming.addEventListener("input", changed);

  return {
    fields: [el("span", { class: "selection-field" }, [el("label", { for: "add-to-theme", text: "Theme" }), picker]), namingField],
    ready: () => picker.value !== NEW_THEME || Boolean(naming.value.trim()),
    destination: () => (picker.value !== NEW_THEME ? picker.options[picker.selectedIndex].text : naming.value.trim() || "a new theme"),
    async chosen() {
      if (picker.value !== NEW_THEME) return offered.find((theme) => theme.theme_id === picker.value);
      const wanted = naming.value.trim();
      const taken = offered.find((theme) => sameName(theme.name, wanted));
      if (taken) {
        paint(taken.theme_id);
        return taken;
      }
      const created = await api("/api/themes", { method: "POST", body: JSON.stringify({ name: wanted }) });
      const made = { theme_id: created.theme_id, name: created.name };
      offered.push(made);
      paint(made.theme_id);
      naming.value = "";
      return made;
    },
  };
}

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
