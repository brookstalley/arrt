/* Selecting works on a list, and acting on the selection: one model for every list.
 *
 * Artworks, an Artist's page, the search results and a Topic's page all offer
 * the same thing, Sonarr's *Select* mode (`build-plan-lists-settings-and-scale.md`
 * Chunk 05, #285): a toggle whose label says which mode the page is in, ticks
 * on the works only while it is on, and an action bar holding *Select all* and
 * every act valid for what is ticked. Held works can be added to a theme —
 * including *New theme…*, so a theme is made from a selection without leaving
 * the list — or archived; works the library does not hold can be got.
 *
 * **Outside the mode a card has no tick at all**, hidden by `hidden` rather
 * than by colour, so it is out of the tab order too: a tick on every card was
 * one more Tab stop per card (`ux-review-2026-10.md` finding 30).
 *
 * **Select all means every work the list's filter matches, loaded or not.** A
 * held list that pages from the server passes its filter (`held.filter`, the
 * body `GET /api/works` takes as a query), and the acts send that filter, with
 * the works unticked since, rather than the ids that happen to be on screen.
 * A list that holds every work it has (a registry list, an artist's few) has
 * no filter, and *Select all* ticks what is there.
 *
 * Named `selecting` rather than `selection` because `core/selection.js` is the
 * act of hanging a selection on a wall, which predates this module.
 */

import { attempt } from "./acting.js";
import { api } from "./api.js";
import { workName } from "./badges.js";
import { confirmAct } from "./confirm.js";
import { counted } from "./counting.js";
import { getSelection } from "./getting.js";
import { addedSentence, addWorksToTheme, stoppedSentence } from "./membership.js";
import { el, fill } from "./render.js";

/* The theme picker's value for *New theme…*. Theme ids are UUIDs, so it cannot
 * collide with one. */
const NEW_THEME = "new";

/* Two names for one theme: the curator's spacing and capitals are not a second
 * theme, as a Get's *New theme…* already rules (`core/getting.js`). */
function sameName(one, other) {
  return one.trim().toLowerCase() === other.trim().toLowerCase();
}

/* `held`, for a list of works the library holds:
 *   - `themes`: `[{ theme_id, name }]` a selection can be added to;
 *   - `shownTheme`: the theme the list is filtered to, if any. It is not
 *     offered as a destination, since every work shown is in it already, and
 *     *Remove from* it is offered instead;
 *   - `filter`: the list's filter as `POST /api/works/archive` and the theme
 *     routes take it, when the list pages from the server; null when every
 *     work is loaded;
 *   - `total`: how many works the filter matches;
 *   - `onAdded(theme, added)`, `onArchived(ids)`, `onRemoved(id)` and
 *     `afterRemoval({ removed, complete })`: what the page does about an act's
 *     outcome, since only it knows its tiles and its counts.
 * `notHeld`, for registry works: `{ defaultName }`, passed on to Get's *Add to*.
 * `onToggle(selecting)` is told when the mode changes. */
export function selectionMode({ held = null, notHeld = null, onToggle = () => {} } = {}) {
  let selecting = false;
  let ready = false;

  // Held works: ticked one by one, or everything the filter matches less what
  // was unticked since.
  const ticked = new Set();
  let everything = false;
  const unticked = new Set();
  let total = held ? held.total : 0;
  const heldBoxes = new Map();
  // Registry works: their ticks are `core/getting.js`'s, counted from there.
  const registryBoxes = new Set();
  let gettable = 0;

  const heldCount = () => (everything ? Math.max(0, total - unticked.size) : ticked.size);
  const isTicked = (artworkId) => (everything ? !unticked.has(artworkId) : ticked.has(artworkId));

  // Focusable, and focused when an act completes: finishing it disables the
  // button the curator is standing on, a browser blurs a control it disables,
  // and the keyboard would land at the top of the document.
  const announcement = el("p", { class: "muted selection-status", "aria-live": "polite", tabindex: "-1" });
  const say = (words) => {
    // Not rewritten unchanged: a live region reassigned the same sentence
    // announces it again, which trains a listener to tune the region out.
    if (announcement.textContent !== words) announcement.textContent = words;
  };

  const toggle = el("button", { class: "action quiet select-toggle", type: "button", text: "Select" });
  const selectAll = el("button", { class: "action quiet select-all", type: "button" });

  /* -- the held half -------------------------------------------------------- */

  const themes = held ? held.themes.filter((theme) => !(held.shownTheme && theme.theme_id === held.shownTheme.theme_id)) : [];
  const picker = held ? el("select", { id: "add-to-theme" }) : null;
  const naming = held ? el("input", { type: "text", id: "add-to-theme-name", autocomplete: "off" }) : null;
  const namingField = held
    ? el("span", { class: "selection-field", hidden: true }, [el("label", { for: "add-to-theme-name", text: "Name for the new theme" }), naming])
    : null;
  const paintPicker = (chosen) => {
    fill(
      picker,
      ...themes.map((theme) => el("option", { value: theme.theme_id, text: theme.name })),
      el("option", { value: NEW_THEME, text: "New theme…" }),
    );
    picker.value = chosen || (themes.length ? themes[0].theme_id : NEW_THEME);
  };
  if (picker) paintPicker(null);
  const add = held ? el("button", { class: "action selection-add", type: "button" }) : null;
  const archive = held ? el("button", { class: "action quiet selection-archive", type: "button" }) : null;
  const remove = held && held.shownTheme ? el("button", { class: "action quiet selection-remove", type: "button" }) : null;

  const destination = () => {
    if (picker.value !== NEW_THEME) return picker.options[picker.selectedIndex].text;
    return naming.value.trim() || "a new theme";
  };

  /* -- the registry half ---------------------------------------------------- */

  const getting = notHeld
    ? getSelection({
        defaultName: notHeld.defaultName || null,
        onChange: (count) => {
          gettable = count;
          settle();
        },
      })
    : null;

  /* -- what the bar says ---------------------------------------------------- */

  function hasItems() {
    return heldBoxes.size > 0 || registryBoxes.size > 0 || total > 0;
  }

  function allTicked() {
    const heldAll = !held || everything ? unticked.size === 0 : [...heldBoxes.keys()].every((id) => ticked.has(id));
    const registryAll = [...registryBoxes].every((box) => box.checked || !box.isConnected);
    return heldAll && registryAll && heldCount() + gettable > 0;
  }

  function settle() {
    if (!ready) return;
    const count = heldCount() + gettable;
    toggle.hidden = !hasItems();
    const works = counted(heldCount(), "work");
    if (add) {
      add.disabled = heldCount() === 0 || (picker.value === NEW_THEME && !naming.value.trim());
      add.textContent = heldCount() ? `Add ${works} to ${destination()}` : `Add to ${destination()}`;
      namingField.hidden = picker.value !== NEW_THEME;
    }
    if (archive) {
      archive.disabled = heldCount() === 0;
      archive.textContent = heldCount() ? `Archive ${works}` : "Archive";
    }
    if (remove) {
      remove.disabled = heldCount() === 0;
      remove.textContent = heldCount() ? `Remove ${works} from ${held.shownTheme.name}` : `Remove from ${held.shownTheme.name}`;
    }
    const reachable = (held ? (held.filter ? total : heldBoxes.size) : 0) + [...registryBoxes].filter((box) => box.isConnected).length;
    selectAll.textContent = allTicked() ? "Select none" : `Select all ${counted(reachable, "work")}`;
    selectAll.disabled = reachable === 0;
    say(count === 0 ? "No works selected." : `${count} selected.`);
  }

  /* -- ticking -------------------------------------------------------------- */

  function setHeld(artworkId, on) {
    if (everything) {
      if (on) unticked.delete(artworkId);
      else unticked.add(artworkId);
    } else if (on) ticked.add(artworkId);
    else ticked.delete(artworkId);
  }

  function prune() {
    for (const [artworkId, box] of heldBoxes) if (!box.isConnected) heldBoxes.delete(artworkId);
    for (const box of registryBoxes) if (!box.isConnected) registryBoxes.delete(box);
  }

  function setRegistry(box, on) {
    if (box.checked === on || box.disabled) return;
    box.checked = on;
    // Through the box's own listener, so `core/getting.js` keeps the count.
    box.dispatchEvent(new Event("change"));
  }

  function clearAll() {
    everything = false;
    ticked.clear();
    unticked.clear();
    for (const box of heldBoxes.values()) box.checked = false;
    for (const box of registryBoxes) setRegistry(box, false);
  }

  function tickAll() {
    prune();
    if (held && held.filter) {
      everything = true;
      unticked.clear();
      ticked.clear();
    } else {
      for (const artworkId of heldBoxes.keys()) ticked.add(artworkId);
    }
    for (const box of heldBoxes.values()) box.checked = true;
    for (const box of registryBoxes) setRegistry(box, true);
  }

  function apply() {
    prune();
    toggle.textContent = selecting ? "Stop selecting" : "Select";
    bar.hidden = !selecting;
    for (const box of heldBoxes.values()) box.hidden = !selecting;
    for (const box of registryBoxes) box.hidden = !selecting;
    // Leaving the mode drops the ticks: a selection nobody can see would be
    // acted on the next time the mode is entered.
    if (!selecting) clearAll();
    onToggle(selecting);
    settle();
  }

  toggle.addEventListener("click", () => {
    selecting = !selecting;
    apply();
  });
  selectAll.addEventListener("click", () => {
    if (allTicked()) clearAll();
    else tickAll();
    settle();
  });

  /* -- the acts ------------------------------------------------------------- */

  // What an act on held works is for: the filter, when everything it matches
  // is ticked, else the ids.
  const body = () => (everything ? { filter: held.filter, except_ids: [...unticked] } : { artwork_ids: [...ticked] });

  const done = (sentence) => {
    clearAll();
    settle();
    say(sentence);
    announcement.focus();
  };

  if (picker) {
    picker.addEventListener("change", settle);
    naming.addEventListener("input", settle);
  }

  /* The theme the picker names, made first when it is *New theme…*. A typed
   * name that is already a theme joins it. Once made it is offered and chosen,
   * so a second press joins it rather than making another. */
  async function chosenTheme() {
    if (picker.value !== NEW_THEME) return themes.find((theme) => theme.theme_id === picker.value);
    const wanted = naming.value.trim();
    const taken = themes.find((theme) => sameName(theme.name, wanted));
    if (taken) {
      picker.value = taken.theme_id;
      return taken;
    }
    const created = await api("/api/themes", { method: "POST", body: JSON.stringify({ name: wanted }) });
    const made = { theme_id: created.theme_id, name: created.name };
    themes.push(made);
    paintPicker(made.theme_id);
    naming.value = "";
    return made;
  }

  if (add) {
    add.addEventListener("click", () => {
      const asked = heldCount();
      return attempt(add, `add ${counted(asked, "work")} to ${destination()}`, async () => {
        const theme = await chosenTheme();
        if (everything) {
          const outcome = await api(`/api/themes/${encodeURIComponent(theme.theme_id)}/works/bulk`, {
            method: "POST",
            body: JSON.stringify(body()),
          });
          if (held.onAdded) held.onAdded(theme, outcome.added);
          done(addedSentence({ added: outcome.added, wanted: outcome.added, already: outcome.already }, theme.name));
          return;
        }
        let outcome;
        try {
          outcome = await addWorksToTheme(theme.theme_id, [...ticked], {
            onAdded: (artworkId) => {
              ticked.delete(artworkId);
              const box = heldBoxes.get(artworkId);
              if (box) box.checked = false;
            },
          });
        } catch (failure) {
          if (failure.progress && held.onAdded) held.onAdded(theme, failure.progress.added);
          settle();
          if (failure.progress) say(stoppedSentence(failure.progress, theme.name));
          // Rethrown so the server's own words for the refusal are said beside
          // Add. The sentence above says how far it got; only the server can
          // say why it stopped.
          throw failure;
        }
        if (held.onAdded) held.onAdded(theme, outcome.added);
        done(addedSentence(outcome, theme.name));
      });
    });
  }

  if (archive) {
    archive.addEventListener("click", async () => {
      const works = counted(heldCount(), "work");
      const agreed = await confirmAct({
        title: `Archive ${works}?`,
        consequence:
          "Each leaves every wall at that wall's next build and stays in its themes. " +
          "An archived work is restored from its own page.",
        confirmLabel: "Archive",
      });
      if (!agreed) return;
      await attempt(archive, `archive ${works}`, () => api("/api/works/archive", { method: "POST", body: JSON.stringify(body()) }), {
        then: (outcome) => {
          if (held.onArchived) held.onArchived(outcome.archived);
          const already = outcome.already ? ` ${counted(outcome.already, "was", "were")} archived already.` : "";
          done(`Archived ${counted(outcome.archived.length, "work")}.${already}`);
        },
      });
    });
  }

  if (remove) {
    const theme = held.shownTheme;
    remove.addEventListener("click", async () => {
      const going = counted(heldCount(), "work");
      const removed = [];
      const complete = await attempt(remove, `remove ${going} from ${theme.name}`, async () => {
        if (everything) {
          const outcome = await api(`/api/themes/${encodeURIComponent(theme.theme_id)}/works/remove`, {
            method: "POST",
            body: JSON.stringify(body()),
          });
          for (const artworkId of outcome.removed) {
            removed.push(artworkId);
            held.onRemoved(artworkId);
          }
          clearAll();
          return;
        }
        // One at a time, each leaving the selection as it goes, so a refusal
        // part way leaves exactly the works that did not go still ticked.
        for (const artworkId of [...ticked]) {
          await api(`/api/themes/${encodeURIComponent(theme.theme_id)}/works/${encodeURIComponent(artworkId)}`, {
            method: "DELETE",
          });
          removed.push(artworkId);
          ticked.delete(artworkId);
          heldBoxes.delete(artworkId);
          held.onRemoved(artworkId);
        }
      });
      total -= removed.length;
      settle();
      if (held.afterRemoval) await held.afterRemoval({ removed, complete });
      if (!complete) return;
      say(`Removed ${counted(removed.length, "work")} from ${theme.name}.`);
      announcement.focus();
    });
  }

  const heldGroup = held
    ? el("div", { class: "selection-group" }, [
        el("span", { class: "selection-field" }, [el("label", { for: "add-to-theme", text: "Theme" }), picker]),
        namingField,
        add,
        remove,
        archive,
      ])
    : null;

  // Fixed to the foot of the window while it is shown, so its acts stay in
  // reach however far down the list the ticking went.
  const bar = el("div", { class: "selection", role: "region", "aria-label": "Selection", hidden: true }, [
    el("div", { class: "selection-group" }, [announcement, selectAll]),
    heldGroup,
    getting ? getting.node : null,
  ]);

  ready = true;
  settle();

  return {
    toggle,
    bar,
    selecting: () => selecting,

    /* The tick for one held work. `className` places it: Artworks' tiles lay it
     * over the picture. A work arriving on a later page while *Select all* is
     * in force is born ticked. */
    heldBox(work, { className = "select-box" } = {}) {
      const box = el("input", { type: "checkbox", class: className, "aria-label": `Select ${workName(work)}` });
      box.hidden = !selecting;
      box.checked = isTicked(work.artwork_id);
      box.addEventListener("change", () => {
        setHeld(work.artwork_id, box.checked);
        settle();
      });
      heldBoxes.set(work.artwork_id, box);
      settle();
      return box;
    },

    /* The tick for one registry work the library does not hold, to get it. */
    registryBox(qid, title) {
      const box = getting.box(qid, title);
      box.hidden = !selecting;
      registryBoxes.add(box);
      settle();
      return box;
    },

    /* The filter's count changed under the list, as a removal changes it. */
    setTotal(count) {
      total = count;
      settle();
    },
  };
}
