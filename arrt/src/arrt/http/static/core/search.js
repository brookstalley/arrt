/* The persistent search affordance.
 *
 * `information-architecture.md` § Navigation Structure keeps search in the top
 * bar on every page, as the *arr apps do, and for this product's own reason: at
 * thousands of works it is the primary way in, and a search you must first
 * navigate to is one more step on the most frequent action.
 *
 * Searching is a **navigation**, not a mode. It writes `?q=` into the fragment
 * and goes to Artworks, which means a search is bookmarkable, sendable, and —
 * because it lands in the history like every other navigation — undone by the
 * browser's own back button rather than by a Clear control the curator has to
 * find.
 */

import { api } from "./api.js";
import { el } from "./render.js";
import { go } from "./router.js";
import { state } from "./state.js";

/* The field shows the search that is currently in the address bar.
 *
 * Skipped while the field has focus. A curator mid-word is the one person whose
 * text must not be replaced by the state a repaint thinks is current, and a
 * repaint happens on every navigation — including the one the typing is about to
 * cause. */
export function paintSearch() {
  const field = document.getElementById("search");
  const current = state.params.q || "";
  if (document.activeElement !== field && field.value !== current) field.value = current;
}

/* How many library matches the dropdown shows. Enough to recognise the one you
 * meant; more is what Enter, which opens every match in Artworks, is for. */
const SUGGESTIONS = 6;

/* Wait this long after the last keystroke before asking, so typing a word asks
 * once rather than once a letter. */
const PAUSE_MS = 200;

/* The dropdown under the search box: Sonarr's two groups, in Arrt's words.
 *
 * `information-architecture.md` § The *arr layout records Sonarr's pattern from
 * its source: the box searches the library as you type, and the last row offers
 * the same words as a search of everything. Here that row goes to Add New with
 * the words filled in, and Add New does not start the search, because a
 * museum search is a paid run and nothing may spend on a keystroke.
 *
 * **Enter with nothing highlighted opens Artworks filtered to the query**, as it
 * did before the dropdown existed. That departs from Sonarr, which opens the
 * first match, and the owner ruled it on 2026-09-30: an artist or a movement
 * matches many works where a series title matches one.
 *
 * An ARIA combobox: the input keeps focus, arrow keys move
 * `aria-activedescendant` through the options, Escape closes the list, and the
 * two groups are named so a screen reader says which one an option is in. */
function installSuggestions(field) {
  // Its own class name: `.suggestions` is a conversation turn's block, and a
  // shared name gave every turn the dropdown's absolute positioning.
  const list = el("ul", { id: "search-suggestions", class: "search-suggestions", role: "listbox", "aria-label": "Suggestions" });
  list.hidden = true;
  field.after(list);
  field.setAttribute("role", "combobox");
  field.setAttribute("aria-autocomplete", "list");
  field.setAttribute("aria-controls", "search-suggestions");
  field.setAttribute("aria-expanded", "false");

  let options = [];
  let active = -1;
  let asked = 0;
  let timer = null;

  const close = () => {
    list.hidden = true;
    field.setAttribute("aria-expanded", "false");
    field.removeAttribute("aria-activedescendant");
    options = [];
    active = -1;
  };

  const highlight = (index) => {
    active = index;
    options.forEach((option, at) => option.node.setAttribute("aria-selected", at === index ? "true" : "false"));
    if (index < 0) field.removeAttribute("aria-activedescendant");
    else field.setAttribute("aria-activedescendant", options[index].node.id);
  };

  const choose = (option) => {
    close();
    option.act();
  };

  const option = (id, text, act) => {
    const node = el("li", { id, role: "option", "aria-selected": "false", text });
    // Mousedown rather than click: a click lands after the field's blur, which
    // has already closed the list the click was aimed at.
    node.addEventListener("mousedown", (event) => {
      event.preventDefault();
      choose(entry);
    });
    const entry = { node, act };
    return entry;
  };

  const group = (id, label, entries) =>
    el("li", { role: "presentation" }, [
      el("ul", { role: "group", "aria-labelledby": id }, [
        el("li", { id, role: "presentation", class: "search-suggestions-label", text: label }),
        ...entries.map((entry) => entry.node),
      ]),
    ]);

  const paint = (query, works, failed) => {
    const held = works.map((work, at) =>
      option(`suggestion-work-${at}`, work.artist ? `${work.title} — ${work.artist.name}` : work.title, () =>
        go("work", work.artwork_id),
      ),
    );
    const museums = option("suggestion-museums", `Search museums for “${query}”`, () =>
      go("discover", null, { term: query }),
    );
    options = [...held, museums];
    // A lookup that failed is not a library with no matches, and must not read as
    // one: the row below it spends money, on a work the curator may already own.
    const unsearched = failed
      ? [
          el("li", {
            role: "presentation",
            class: "search-suggestions-note",
            text: "Your library could not be searched just now.",
          }),
        ]
      : [];
    list.replaceChildren(
      ...unsearched,
      ...(held.length ? [group("suggestions-held", "In your library", held)] : []),
      // Named for the page the row opens, as Sonarr names its group "Add New
      // Series": the *arr precedent decides what things are called here.
      group("suggestions-add-new", "Add New", [museums]),
    );
    list.hidden = false;
    field.setAttribute("aria-expanded", "true");
    highlight(-1);
  };

  const ask = async () => {
    const query = field.value.trim();
    const ticket = ++asked;
    if (!query) {
      close();
      return;
    }
    let works = [];
    let failed = false;
    try {
      const page = await api(`/api/works?q=${encodeURIComponent(query)}&limit=${SUGGESTIONS}`);
      works = page.works;
    } catch (failure) {
      // The dropdown is a shortcut; the search itself still works on Enter. So a
      // failed lookup costs the matches, says so, and keeps the other row.
      failed = true;
    }
    // A slower answer to an earlier keystroke must not replace a later one.
    if (ticket !== asked || document.activeElement !== field) return;
    paint(query, works, failed);
  };

  field.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(ask, PAUSE_MS);
  });
  field.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      if (!list.hidden) {
        event.preventDefault();
        close();
      }
      return;
    }
    if (list.hidden || !options.length) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      highlight((active + 1) % options.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      highlight(active <= 0 ? options.length - 1 : active - 1);
    } else if (event.key === "Enter" && active >= 0) {
      event.preventDefault();
      choose(options[active]);
    }
  });
  field.addEventListener("blur", () => {
    clearTimeout(timer);
    asked += 1;
    close();
  });
  return () => {
    clearTimeout(timer);
    asked += 1;
    close();
  };
}

export function installSearch() {
  const form = document.getElementById("search-form");
  const field = document.getElementById("search");
  const dismiss = installSuggestions(field);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    dismiss();
    const query = field.value.trim();
    // Filters already in the address survive a search made from Artworks, and
    // do not follow one made from anywhere else: narrowing what you are looking
    // at is a different act from starting a search over the whole collection,
    // and carrying a rail's state onto the second would silently hide most of
    // the answers.
    const params = state.view === "collection" ? { ...state.params, q: query } : { q: query };
    go("collection", null, params);
  });
}

/* The way out of a search, offered where the emptiness is. Written here beside
 * the affordance it undoes rather than in the screen, so the two cannot come to
 * disagree about what clearing a search means. */
export function clearSearchLink(text = "Clear the search") {
  return el("button", {
    class: "action quiet",
    type: "button",
    text,
    onclick: () => go("collection", null, { ...state.params, q: "" }),
  });
}
