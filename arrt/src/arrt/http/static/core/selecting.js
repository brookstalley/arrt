/* Selecting works on a list, and acting on the selection: one model for every list.
 *
 * Artworks, an Artist's page, the search results and a Topic's page all offer
 * the same thing, Sonarr's *Select* mode: a toggle whose label says which mode the page is in, ticks
 * on the works only while it is on, and the acts beside the toggle, in the
 * page's toolbar: *Select all* and every act valid for what is ticked. Held works can be added to a theme —
 * including *New theme…*, so a theme is made from a selection without leaving
 * the list — hung on a wall (*Hang…*, `core/selection.js`: only the works a
 * wall can show, the rest said as left out) or archived; works the library
 * does not hold can be got.
 *
 * **Outside the mode a card has no tick at all**, hidden by `hidden` rather
 * than by colour, so it is out of the tab order too: a tick on every card was
 * one more Tab stop per card.
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
import { api, fetchAllWorks } from "./api.js";
import { workName } from "./badges.js";
import { confirmAct } from "./confirm.js";
import { counted, number } from "./counting.js";
import { openPanel } from "./editing.js";
import { getSelection } from "./getting.js";
import { addedSentence, addWorksToTheme, stoppedSentence, themeChoice } from "./membership.js";
import { el } from "./render.js";
import { hangOnAWall } from "./selection.js";

/* Whether a held work can be shown on a wall at all: not archived, and with a
 * picture. The Work page leaves *Hang…* disabled for the same two, so a
 * selection leaves the same works out rather than hanging a wall short. A work
 * read without `image` or `status` is taken to be hangable; the build names
 * what it cannot show. */
function canHang(work) {
  return work.status !== "archived" && !(work.image && work.image.available === false);
}

/* The works a filter matches, read through to the end, as the grid reads them:
 * `held.filter` is the body the selection routes take, `fetchAllWorks` its
 * query. A list that stops short is refused rather than hung part way. */
async function worksOfFilter(filter) {
  const chosen = {};
  for (const [key, value] of Object.entries(filter)) if (Array.isArray(value)) chosen[key] = value;
  const read = await fetchAllWorks(filter.q || "", chosen, null, filter.sort || null, {
    artistId: filter.artist_id || null,
    status: filter.status || null,
    theme: filter.theme || null,
    notOnWall: Boolean(filter.not_on_wall),
    shown: filter.shown || null,
  });
  if (read.works.length < read.total) throw new Error(`Only ${number(read.works.length)} of the ${number(read.total)} matching works could be read.`);
  return read.works;
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
 *   - `hang`: true to offer *Hang…* (Artworks, an Artist's works, the search
 *     results, a Topic's). Not offered by default: a theme's page asks for a
 *     selection too, and has a *Hang…* of its own, which hangs the theme, so a
 *     second one beside it on that page would name two acts alike;
 *   - `hangOn`: `{ wall_id, name }` when the works are being chosen for one
 *     wall (Artworks, opened from that wall's card): *Hang…* names it and hangs
 *     there without asking which (`hangOnAWall`'s `wallId`), and `onHung(build)`
 *     is told instead of the bar saying "Hung…", since the page leaves;
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
  // Every theme is known to the picker, the shown one included, so a new
  // theme typed with its name joins it rather than being refused or doubled.
  const choice = held ? themeChoice(themes, { known: held.themes, onChange: () => settle() }) : null;
  // *Add to theme…* in the toolbar opens the choice of theme; the act itself is
  // the dialog's, named for what it will do, and only it is filled: the opener
  // commits nothing. The choice is a dialog rather than
  // a picker in the toolbar because the toolbar sticks while the list scrolls,
  // and a picker with its name field beside it filled half a phone's screen.
  const add = held ? el("button", { class: "action quiet selection-add", type: "button", "aria-haspopup": "dialog", text: "Add to theme…" }) : null;
  const confirmAdd = held ? el("button", { class: "action add-confirm", type: "button" }) : null;
  let addPanel = null;
  // *Hang…* puts the ticked works on a wall until something else is hung there
  // (`core/selection.js`). It names no count, as *Add to theme…* does not: the
  // question it opens does, and says how many were left out.
  //
  // Chosen for one wall (`held.hangOn`, from that wall's card on Walls), it names
  // the wall, as the page's note above does, since it asks no longer which.
  const hangOn = held && held.hang ? held.hangOn || null : null;
  const hang =
    held && held.hang
      ? el("button", { class: "action quiet selection-hang", type: "button", "aria-haspopup": "dialog", text: hangOn ? `Hang on ${hangOn.name}…` : "Hang…" })
      : null;
  // Whether each ticked work can hang (`canHang`), by id, kept as the ticks are drawn.
  const hangable = new Map();
  const archive = held ? el("button", { class: "action quiet selection-archive", type: "button" }) : null;
  const remove = held && held.shownTheme ? el("button", { class: "action quiet selection-remove", type: "button" }) : null;

  const destination = () => choice.destination();

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
      add.disabled = heldCount() === 0;
      confirmAdd.disabled = heldCount() === 0 || !choice.ready();
      confirmAdd.textContent = heldCount() ? `Add ${works} to ${destination()}` : `Add to ${destination()}`;
    }
    if (hang) hang.disabled = heldCount() === 0;
    if (archive) {
      archive.disabled = heldCount() === 0;
      archive.textContent = heldCount() ? `Archive ${works}…` : "Archive…";
    }
    if (remove) {
      remove.disabled = heldCount() === 0;
      remove.textContent = heldCount() ? `Remove ${works} from ${held.shownTheme.name}` : `Remove from ${held.shownTheme.name}`;
    }
    const reachable = (held ? (held.filter ? total : heldBoxes.size) : 0) + [...registryBoxes].filter((box) => box.isConnected).length;
    selectAll.textContent = allTicked() ? "Select none" : `Select all ${counted(reachable, "work")}`;
    selectAll.disabled = reachable === 0;
    say(count === 0 ? "No works selected." : `${number(count)} selected.`);
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
    // The toolbar holding the acts stays in reach while the list scrolls under
    // it, and only while it holds them: at rest it scrolls away with the page,
    // as every other page's toolbar does, and leaves a phone its height.
    const holder = toggle.closest(".page-toolbar");
    if (holder) holder.classList.toggle("selecting", selecting);
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

  if (add) {
    // Cancel and Escape leave the keyboard on *Add to theme…*: the platform's
    // dialog hands focus back to what opened it as it closes.
    add.addEventListener("click", () => {
      addPanel = openPanel({
        title: `Add ${counted(heldCount(), "work")} to a theme`,
        body: choice.fields,
        actions: [confirmAdd],
        closeLabel: "Cancel",
        onClose: () => (addPanel = null),
      });
      settle();
    });
    confirmAdd.addEventListener("click", () => {
      const asked = heldCount();
      // Closed before the sentence takes the keyboard, so the dialog handing
      // focus back to *Add to theme…* as it closes does not take it from there.
      const finish = (sentence) => {
        if (addPanel) addPanel.close();
        done(sentence);
      };
      return attempt(confirmAdd, `add ${counted(asked, "work")} to ${destination()}`, async () => {
        const theme = await choice.chosen();
        if (everything) {
          const outcome = await api(`/api/themes/${encodeURIComponent(theme.theme_id)}/works/bulk`, {
            method: "POST",
            body: JSON.stringify(body()),
          });
          if (held.onAdded) held.onAdded(theme, outcome.added);
          finish(addedSentence({ added: outcome.added, wanted: outcome.added, already: outcome.already }, theme.name));
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
          // the dialog's Add, which stays open to try again. The sentence above says how far it got; only the server can
          // say why it stopped.
          throw failure;
        }
        if (held.onAdded) held.onAdded(theme, outcome.added);
        finish(addedSentence(outcome, theme.name));
      });
    });
  }

  if (hang) {
    hang.addEventListener("click", async () => {
      // What is ticked, as works: the ticked ids, or, when *Select all* stands
      // for a filter, every work it matches read now, less what was unticked.
      let chosen = [];
      const read = await attempt(hang, "read the selected works", async () => {
        chosen = everything
          ? (await worksOfFilter(held.filter)).filter((work) => !unticked.has(work.artwork_id)).map((work) => [work.artwork_id, canHang(work)])
          : [...ticked].map((artworkId) => [artworkId, hangable.get(artworkId) !== false]);
      });
      if (!read) return;
      // Only held works are here, and only those a wall can show: a registry
      // work has no id to send, and one with no picture would hang a wall dark.
      const ids = chosen.filter(([, hangs]) => hangs).map(([artworkId]) => artworkId);
      const leftOut = chosen.length - ids.length;
      if (!ids.length) {
        openPanel({
          title: "Hang…",
          lead: `${chosen.length === 1 ? "That work has no picture yet or is archived" : `Those ${chosen.length} works have no picture yet or are archived`}, so there is nothing to show on a wall.`,
        });
        return;
      }
      const works = counted(ids.length, "work");
      await hangOnAWall({
        control: hang,
        artworkIds: ids,
        title: works,
        leftOut,
        wallId: hangOn ? hangOn.wall_id : null,
        then: (build) => {
          // Chosen for a wall: the page takes the curator back to it, where its
          // card says what it now hangs and what of it cannot be shown.
          if (hangOn && held.onHung) {
            clearAll();
            held.onHung(build);
            return;
          }
          const stuck = build.exclusions.length;
          const details = [...new Set(build.exclusions.map((exclusion) => exclusion.detail))].join(" ");
          done(
            stuck
              ? `Hung ${works} on ${build.wall_name}, but ${counted(stuck, "work")} cannot be shown yet: ${details}`
              : `Hung ${works} on ${build.wall_name}.`,
          );
        },
      });
    });
  }

  if (archive) {
    archive.addEventListener("click", async () => {
      const works = counted(heldCount(), "work");
      const agreed = await confirmAct({
        title: `Archive ${works}?`,
        consequence:
          "Each comes off every wall showing it now, and stays in its themes. " +
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
        hang,
        add,
        remove,
        archive,
      ])
    : null;

  // In the toolbar, after the toggle that shows it: the acts on what is selected
  // take the toolbar's left side (`design-direction.md` § Component Patterns,
  // "How a page reads"). A page puts it there with `toolbar({ selection })`,
  // which also stands the toggle on the right, and the toolbar sticks while it
  // shows.
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

    /* Turn the mode on as *Select* would, for a page that opens already
     * selecting (Artworks, choosing works for a wall). Called once the page is
     * drawn, since the mode marks the toolbar that holds it. */
    start() {
      if (selecting) return;
      selecting = true;
      apply();
    },

    /* The tick for one held work. `className` places it: Artworks' tiles lay it
     * over the picture. A work arriving on a later page while *Select all* is
     * in force is born ticked.
     *
     * None, on a page that offers no held half: a tick with no act to apply it
     * to would show the toggle and a bar with nothing in it. */
    heldBox(work, { className = "select-box" } = {}) {
      if (!held) return null;
      const box = el("input", { type: "checkbox", class: className, "aria-label": `Select ${workName(work)}` });
      box.hidden = !selecting;
      box.checked = isTicked(work.artwork_id);
      box.addEventListener("change", () => {
        setHeld(work.artwork_id, box.checked);
        settle();
      });
      heldBoxes.set(work.artwork_id, box);
      hangable.set(work.artwork_id, canHang(work));
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
