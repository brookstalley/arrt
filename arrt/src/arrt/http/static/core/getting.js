/* Get: the one acquiring act, on any selection of works the library does not hold.
 *
 * Ruling 3 of `ia-proposal.md` dissolved Add New into this: a curator who has found
 * works on the Artist page or the results page ticks them and gets them, and a work's
 * own page gets that one. Each work is named by its Wikidata item, which is what the
 * server asks the image sources by.
 *
 * **The page stays where it is.** Getting takes minutes, so the control says what
 * started, in its live region, with a link to the run; Queue lists it too. A held
 * row offers no tick box, because the library already has it, so the only skips the
 * curator hears about are the server's: an item already being got, or one Wikidata
 * does not have.
 *
 * **Every Get names where its accepted works go**, beside its button: *Add to*,
 * the default theme first and selected, then every other theme, then *New
 * theme…* (`build-plan-topics-and-destinations.md`, the owner's rulings of
 * 2026-10-02). The default sends no `theme_id`, so a run's destination is null
 * exactly when its works go to the default. A new theme is created by the
 * client's own `POST /api/themes` before the Get starts, never by the Get: the
 * binding that starts a Get does not branch on whether its theme exists. */

import { api } from "./api.js";
import { agree, counted } from "./counting.js";
import { el, fill, guard } from "./render.js";
import { go } from "./router.js";

/* The select's value for *New theme…*. Theme ids are UUIDs, and the default
 * theme's option has the empty value, so neither can collide with it. */
const NEW_THEME = "new";

/* Ids for the label-to-control pairs, unique however many controls a page has. */
let controls = 0;

/* Two names for one theme, by the rule that a name already taken joins that
 * theme: the curator's spacing and capitals are not a second theme. */
function sameName(one, other) {
  return one.trim().toLowerCase() === other.trim().toLowerCase();
}

/* *Add to*: where the accepted works of a Get go.
 *
 * `defaultName` is a caller's suggestion, such as a Topic page's topic. Given,
 * the theme of that name is selected if there is one (the owner's ruling: a
 * name that is already a theme joins it), and otherwise *New theme…* with the
 * name filled in. Not given, the default theme is selected.
 *
 * `resolve()` answers `{ themeId, name }` for the Get about to start: a null
 * `themeId` for the default, which the request then leaves out. A new name is
 * created here, first, and stays selected, so a second Get from the same
 * control joins it rather than making another. */
function destinationControl({ defaultName = null } = {}) {
  controls += 1;
  const pickerId = `get-into-${controls}`;
  const nameId = `get-into-name-${controls}`;
  const picker = el("select", { id: pickerId }, [el("option", { value: "", text: "Reading themes…" })]);
  const name = el("input", { type: "text", id: nameId, autocomplete: "off" });
  const naming = el("div", { class: "field", hidden: true }, [el("label", { for: nameId, text: "New theme's name" }), name]);
  let themes = [];
  const showNaming = () => {
    naming.hidden = picker.value !== NEW_THEME;
  };
  picker.addEventListener("change", showNaming);

  const option = (theme) => el("option", { value: theme.is_default ? "" : theme.theme_id, text: theme.name });
  const paint = () => {
    const fallback = themes.find((theme) => theme.is_default);
    fill(
      picker,
      // With no default, a Get left here joins no theme, and the option says so.
      fallback ? option(fallback) : el("option", { value: "", text: "No theme (none is the default)" }),
      ...themes.filter((theme) => !theme.is_default).map(option),
      el("option", { value: NEW_THEME, text: "New theme…" }),
    );
  };

  const loaded = api("/api/themes").then((listing) => {
    themes = listing.themes.map((placement) => placement.theme);
    paint();
    if (defaultName) {
      const taken = themes.find((theme) => sameName(theme.name, defaultName));
      picker.value = taken ? (taken.is_default ? "" : taken.theme_id) : NEW_THEME;
      if (!taken) name.value = defaultName;
    }
    showNaming();
  });
  // The server's reason is said when the Get is pressed, by the Get's own guard,
  // since `resolve` awaits this. Caught here as well, so the select does not go
  // on saying it is reading and a listing nobody has asked about yet is not an
  // unhandled rejection.
  loaded.catch(() => fill(picker, el("option", { value: "", text: "The themes could not be read" })));

  async function resolve() {
    await loaded;
    if (picker.value === NEW_THEME) {
      const taken = themes.find((theme) => sameName(theme.name, name.value));
      if (taken) {
        picker.value = taken.is_default ? "" : taken.theme_id;
        showNaming();
        return { themeId: taken.is_default ? null : taken.theme_id, name: taken.name };
      }
      const created = await api("/api/themes", { method: "POST", body: JSON.stringify({ name: name.value }) });
      themes.push(created);
      paint();
      picker.value = created.theme_id;
      showNaming();
      return { themeId: created.theme_id, name: created.name };
    }
    if (picker.value === "") {
      const fallback = themes.find((theme) => theme.is_default);
      return { themeId: null, name: fallback ? fallback.name : null };
    }
    const chosen = themes.find((theme) => theme.theme_id === picker.value);
    return { themeId: chosen.theme_id, name: chosen.name };
  }

  return {
    node: el("div", { class: "row get-into" }, [
      el("div", { class: "field" }, [el("label", { for: pickerId, text: "Add to" }), picker]),
      naming,
    ]),
    resolve,
  };
}

/* Why the server left an item out, as a clause after "N works" or "1 work". The keys
 * are `SkipReason`'s values, held to it by the vocabulary test. */
export const SKIP_WORDS = {
  held: ["is already in your library", "are already in your library"],
  being_got: ["is already being got", "are already being got"],
  not_found: ["is not a work Wikidata has", "are not works Wikidata has"],
};

/* What a Get did, in one or two sentences: what started and into which theme,
 * and what was left out. `into` is the theme's name, or null when no theme is
 * the default and the Get named none. */
export function getSentence(asked, outcome, into) {
  const skipped = outcome.skipped || [];
  const started = asked - skipped.length;
  const lead = outcome.run ? `Getting ${counted(started, "work")} into ${into || "no theme"}.` : "Nothing was started.";
  const reasons = Object.keys(SKIP_WORDS)
    .map((reason) => [reason, skipped.filter((entry) => entry.reason === reason).length])
    .filter(([, count]) => count > 0)
    .map(([reason, count]) => `${count} ${agree(count, ...SKIP_WORDS[reason])}`);
  return reasons.length ? `${lead} Left out: ${reasons.join("; ")}.` : lead;
}

/* Ask for these items, into the theme `destination` resolves to, and show what
 * happened in `status`, a live region. */
async function getAndSay(qids, status, destination) {
  const into = await destination.resolve();
  // Left out entirely for the default, rather than sent as null: a run's
  // destination is null exactly when its works go to the default theme.
  const body = into.themeId === null ? { qids } : { qids, theme_id: into.themeId };
  const outcome = await api("/api/gets", { method: "POST", body: JSON.stringify(body) });
  fill(
    status,
    el("span", { text: getSentence(qids.length, outcome, into.name) }),
    outcome.run ? " " : null,
    outcome.run
      ? el("button", { class: "link", type: "button", text: "Open the Get", onclick: () => go("run", outcome.run.run_id) })
      : null,
  );
  status.focus();
  return outcome;
}

function aStatus() {
  return el("p", { class: "muted get-status", "aria-live": "polite", tabindex: "-1" });
}

/* A selection of registry works and the control that gets them.
 *
 * `box(qid, title)` makes the tick box for one row; `node` is the control, which
 * reads *Get 3 works* and is disabled while nothing is ticked. A Get clears the
 * ticks, since those works are now being got. `defaultName` is passed on to
 * *Add to*. */
export function getSelection({ defaultName = null } = {}) {
  const chosen = new Map();
  const status = aStatus();
  const destination = destinationControl({ defaultName });
  const button = el("button", { class: "action", type: "button" });
  const settle = () => {
    button.disabled = chosen.size === 0;
    button.textContent = chosen.size ? `Get ${counted(chosen.size, "work")}` : "Get";
  };
  button.addEventListener("click", () =>
    guard(async () => {
      const qids = [...chosen.keys()];
      button.disabled = true;
      try {
        await getAndSay(qids, status, destination);
        for (const box of chosen.values()) box.checked = false;
        chosen.clear();
      } finally {
        settle();
      }
    }),
  );
  settle();
  return {
    node: el("div", { class: "row get-control" }, [destination.node, button, status]),
    box(qid, title) {
      const box = el("input", { type: "checkbox", "aria-label": `Select ${title} to get` });
      box.addEventListener("change", () => {
        if (box.checked) chosen.set(qid, box);
        else chosen.delete(qid);
        settle();
      });
      return box;
    },
  };
}

/* *Get this work*, for the page of one work the library does not hold. */
export function getOne(qid, { defaultName = null } = {}) {
  const status = aStatus();
  const destination = destinationControl({ defaultName });
  const button = el("button", { class: "action", type: "button", text: "Get this work" });
  button.addEventListener("click", () =>
    guard(async () => {
      button.disabled = true;
      try {
        const outcome = await getAndSay([qid], status, destination);
        // Got once, it stays got: a second press would only be skipped as being got.
        button.disabled = Boolean(outcome.run);
      } catch (failure) {
        button.disabled = false;
        throw failure;
      }
    }),
  );
  return el("div", { class: "row get-control" }, [destination.node, button, status]);
}
