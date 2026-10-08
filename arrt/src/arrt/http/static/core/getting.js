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
 * 2026-10-02). A caller's name that is no theme yet, such as a Topic page's
 * topic, is offered just before *New theme…*, as "<name> (new theme)", and
 * chosen (the owner's review of the screens, Chunk 06). The default sends no
 * `theme_id`, so a run's destination is null
 * exactly when its works go to the default. A new theme is created by the
 * client's own `POST /api/themes` before the Get starts, never by the Get: the
 * binding that starts a Get does not branch on whether its theme exists. */

import { api } from "./api.js";
import { agree, counted } from "./counting.js";
import { attempt } from "./acting.js";
import { el, fill } from "./render.js";
import { link } from "./router.js";

/* The select's values for *New theme…* and for a caller's name that is no theme
 * yet. Theme ids are UUIDs, and the default theme's option has the empty value,
 * so neither can collide with these, or these with each other. */
const NEW_THEME = "new";
const OFFERED = "offered";

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
 * name that is already a theme joins it), and otherwise the name is offered as
 * an option of its own, "<name> (new theme)", and selected. Not given, the
 * default theme is selected. *New theme…* is for some other name, so its field
 * starts empty and is shown only while *New theme…* is chosen; like it, the
 * field follows the select in reading and tab order, and is not focused for
 * the curator, since a select fires its change as the keyboard moves through it.
 *
 * `resolve()` answers `{ themeId, name }` for the Get about to start: a null
 * `themeId` for the default, which the request then leaves out. An offered or
 * typed name is created here, first, and stays selected, so a second Get from
 * the same control joins it rather than making another. */
function destinationControl({ defaultName = null } = {}) {
  controls += 1;
  const pickerId = `get-into-${controls}`;
  const nameId = `get-into-name-${controls}`;
  const picker = el("select", { id: pickerId }, [el("option", { value: "", text: "Reading themes…" })]);
  const name = el("input", { type: "text", id: nameId, autocomplete: "off" });
  const naming = el("div", { class: "field", hidden: true }, [el("label", { for: nameId, text: "New theme's name" }), name]);
  let themes = [];
  // The caller's name while it is no theme: offered until it is made.
  let offered = null;
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
      offered ? el("option", { value: OFFERED, text: `${offered} (new theme)` }) : null,
      el("option", { value: NEW_THEME, text: "New theme…" }),
    );
  };

  const loaded = api("/api/themes").then((listing) => {
    themes = listing.themes.map((placement) => placement.theme);
    const taken = defaultName ? themes.find((theme) => sameName(theme.name, defaultName)) : null;
    if (defaultName && !taken) offered = defaultName;
    paint();
    if (taken) picker.value = taken.is_default ? "" : taken.theme_id;
    if (offered) picker.value = OFFERED;
    showNaming();
  });
  // The server's reason is said when the Get is pressed, beside the Get,
  // since `resolve` awaits this. Caught here as well, so the select does not go
  // on saying it is reading and a listing nobody has asked about yet is not an
  // unhandled rejection.
  loaded.catch(() => fill(picker, el("option", { value: "", text: "The themes could not be read" })));

  /* The theme by this name, made first if there is none, then selected. Once
   * made, the offered name is a theme like any other and is no longer offered. */
  async function intoNamed(wanted) {
    const taken = themes.find((theme) => sameName(theme.name, wanted));
    if (taken) {
      picker.value = taken.is_default ? "" : taken.theme_id;
      showNaming();
      return { themeId: taken.is_default ? null : taken.theme_id, name: taken.name };
    }
    const created = await api("/api/themes", { method: "POST", body: JSON.stringify({ name: wanted }) });
    themes.push(created);
    if (offered && sameName(offered, created.name)) offered = null;
    paint();
    picker.value = created.theme_id;
    showNaming();
    return { themeId: created.theme_id, name: created.name };
  }

  async function resolve() {
    await loaded;
    if (picker.value === OFFERED) return intoNamed(offered);
    if (picker.value === NEW_THEME) return intoNamed(name.value);
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
  in_review: ["is already waiting for review", "are already waiting for review"],
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
      ? link({ view: "run", id: outcome.run.run_id }, { class: "link", text: "Open the Get" })
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
  button.addEventListener("click", () => {
    const qids = [...chosen.keys()];
    attempt(button, `get ${counted(qids.length, "work")}`, async () => {
      button.disabled = true;
      try {
        await getAndSay(qids, status, destination);
        for (const box of chosen.values()) box.checked = false;
        chosen.clear();
      } finally {
        settle();
      }
    });
  });
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
    attempt(button, "get this work", async () => {
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
