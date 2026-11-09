/* Watches — the household's standing requests, which Arrt runs with nobody watching.
 *
 * **As Radarr's Settings › Lists**: the things the server checks on its own and
 * adds from (`information-architecture.md` § Where the re-architecture's new
 * objects live). A Watch is words, how often, and an optional monthly cap; what
 * it finds waits in To review, because a Watch never accepts anything
 * (`security-model.md` § The unattended trigger fired).
 *
 * **Each Watch says where it stands in the server's sentence** (`WatchOut.sentence`):
 * running, refused and why, overdue, or what its last run did. The screen
 * composes no verdict of its own, so it and `art_watches` cannot disagree.
 *
 * **Every control applies when it is changed**, as on Settings › General, and is
 * refused in the server's words beside it. Removing a Watch asks first, because
 * nothing restores it; switching it off is the reversible way to stop one.
 *
 * Above the list, whether unattended work may run at all (`GET /api/unattended`),
 * with the way to Settings › General, where it is switched on and its allowance
 * set: a Watch on a household with unattended work off never runs.
 *
 * TEXT IS SET WITH textContent, NEVER innerHTML — the rule is at `core/render.js`.
 * A Watch's words are the household's own, and are still only ever text.
 */

import { api } from "../core/api.js";
import { attempt } from "../core/acting.js";
import { confirmAct } from "../core/confirm.js";
import { stamp } from "../core/dates.js";
import { el, emptyState, render } from "../core/render.js";
import { link, refresh } from "../core/router.js";

const CADENCE_WORDS = { hourly: "Hourly", daily: "Daily", weekly: "Weekly" };
const CADENCES = ["hourly", "daily", "weekly"];

export async function viewWatches(generation) {
  const [listing, unattended] = await Promise.all([api("/api/watches"), api("/api/unattended")]);
  const watches = Array.isArray(listing.watches) ? listing.watches : [];
  const on = watches.filter((watch) => watch.enabled).length;
  render(
    generation,
    el("h1", { text: "Watches" }),
    el("p", {
      class: "page-facts",
      text: watches.length ? `${counted(watches.length, "Watch", "Watches")}, ${on} on.` : "No Watches yet.",
    }),
    el("div", { class: "panel watches-standing" }, [
      el("p", { class: "unattended-standing", text: unattended.sentence }),
      el("p", { class: "muted" }, [
        "Unattended work is switched on, and its monthly allowance set, in ",
        link({ view: "general" }, { text: "Settings › General" }),
        ".",
      ]),
    ]),
    newWatch(),
    ...(watches.length
      ? watches.map(watchPanel)
      : [emptyState("No Watch is written yet.", "Write what to look for above, and Arrt looks for it on its own, leaving what it finds in To review.")]),
  );
}

function counted(count, one, many) {
  return `${count} ${count === 1 ? one : many}`;
}

/* The form for a new Watch: its words, how often, and a cap, then Add. */
function newWatch() {
  const words = el("input", { id: "new-watch-words", type: "text", class: "watch-words", autocomplete: "off" });
  const cadence = cadencePicker("new-watch-cadence", null);
  const cap = el("input", { id: "new-watch-cap", type: "text", class: "setting-field", inputmode: "decimal", placeholder: "Only the allowance", autocomplete: "off" });
  const add = el("button", { type: "submit", class: "action", text: "Add Watch" });
  const form = el("form", { class: "panel new-watch" }, [
    el("h2", { text: "New Watch" }),
    el("dl", { class: "facts settings-general" }, [
      el("dt", {}, [el("label", { for: "new-watch-words", text: "Look for" })]),
      el("dd", {}, [words, el("p", { class: "muted setting-description", text: "In words, as you would ask Discover for it." })]),
      el("dt", {}, [el("label", { for: "new-watch-cadence", text: "How often" })]),
      el("dd", {}, [cadence]),
      el("dt", {}, [el("label", { for: "new-watch-cap", text: "Monthly cap" })]),
      el("dd", {}, [
        el("span", { class: "money-field" }, [el("span", { "aria-hidden": "true", text: "$" }), cap]),
        el("p", { class: "muted setting-description", text: "What this Watch may spend in a month, out of the unattended allowance. Empty leaves only the allowance." }),
      ]),
    ]),
    add,
  ]);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const body = { intent_text: words.value, cadence: cadence.value, monthly_cap_usd: cap.value.trim().replace(/^[$]/, "") };
    await attempt(add, "add the Watch", () => api("/api/watches", { method: "POST", body: JSON.stringify(body) }), {
      then: () => refresh(),
    });
  });
  return form;
}

/* How often a Watch runs: its own choice, or the household's, said as such. */
function cadencePicker(id, watch) {
  const following = watch ? `As Settings › General (${CADENCE_WORDS[watch.effective_cadence] || watch.effective_cadence})` : "As Settings › General";
  return el(
    "select",
    { id, class: "fact-picker" },
    [
      el("option", { value: "", text: following, selected: !watch || watch.cadence === null }),
      ...CADENCES.map((value) => el("option", { value, text: CADENCE_WORDS[value], selected: watch ? watch.cadence === value : false })),
    ],
  );
}

function watchPanel(watch) {
  const id = watch.watch_id;
  return el("section", { class: "panel watch", "data-watch": id }, [
    el("h2", { text: watch.intent_text }),
    el("p", { class: watch.overdue ? "watch-standing fault" : "watch-standing", text: watch.sentence }),
    el("dl", { class: "facts settings-general" }, [
      el("dt", {}, [el("label", { for: `watch-${id}-enabled`, text: "Runs" })]),
      el("dd", {}, [enabledPicker(watch)]),
      el("dt", {}, [el("label", { for: `watch-${id}-words`, text: "Look for" })]),
      el("dd", {}, [wordsField(watch)]),
      el("dt", {}, [el("label", { for: `watch-${id}-cadence`, text: "How often" })]),
      el("dd", {}, [applied(cadencePicker(`watch-${id}-cadence`, watch), watch, "cadence", "how often it runs")]),
      el("dt", {}, [el("label", { for: `watch-${id}-cap`, text: "Monthly cap" })]),
      el("dd", {}, [capField(watch)]),
      el("dt", { text: "This month" }),
      el("dd", { class: "watch-spend", text: `$${watch.spent_usd} spent of $${watch.effective_cap_usd}.` }),
      el("dt", { text: "Next" }),
      el("dd", { class: "watch-next" }, nextWords(watch)),
      el("dt", { text: "Last run" }),
      el("dd", { class: "watch-last-run" }, lastRun(watch)),
    ]),
    removeButton(watch),
  ]);
}

function nextWords(watch) {
  if (watch.next_due_at === null) return [watch.enabled ? "When its run ends." : "Not while it is off."];
  return ["Due ", el("time", stamp(watch.next_due_at)), "."];
}

function lastRun(watch) {
  if (!watch.last_run_id) return ["None yet."];
  return [link({ view: "get", id: watch.last_run_id }, { class: "action quiet", text: "Open its last Get" })];
}

function enabledPicker(watch) {
  const control = el("select", { id: `watch-${watch.watch_id}-enabled`, class: "fact-picker" }, [
    el("option", { value: "on", text: "On", selected: watch.enabled }),
    el("option", { value: "off", text: "Off", selected: !watch.enabled }),
  ]);
  control.addEventListener("change", async () => {
    const enabled = control.value === "on";
    const changed = await send(control, watch, { enabled }, enabled ? "switch the Watch on" : "switch the Watch off");
    if (!changed) control.value = watch.enabled ? "on" : "off";
  });
  return control;
}

/* A picker sent as one field when it changes, put back when refused. */
function applied(control, watch, field, what) {
  const was = control.value;
  control.addEventListener("change", async () => {
    const changed = await send(control, watch, { [field]: control.value }, `change ${what}`);
    if (!changed) control.value = was;
  });
  return control;
}

function wordsField(watch) {
  const control = el("input", { id: `watch-${watch.watch_id}-words`, type: "text", class: "watch-words", value: watch.intent_text, autocomplete: "off" });
  control.addEventListener("change", async () => {
    const changed = await send(control, watch, { intent_text: control.value }, "change what the Watch looks for");
    if (!changed) control.value = watch.intent_text;
  });
  return control;
}

function capField(watch) {
  const control = el("input", {
    id: `watch-${watch.watch_id}-cap`,
    type: "text",
    class: "setting-field",
    inputmode: "decimal",
    value: watch.monthly_cap_usd ?? "",
    placeholder: "Only the allowance",
    autocomplete: "off",
  });
  control.addEventListener("change", async () => {
    const typed = control.value.trim().replace(/^[$]/, "");
    const changed = await send(control, watch, { monthly_cap_usd: typed }, typed ? `set the Watch's cap to $${typed}` : "clear the Watch's cap");
    if (!changed) control.value = watch.monthly_cap_usd ?? "";
  });
  return el("span", { class: "money-field" }, [el("span", { "aria-hidden": "true", text: "$" }), control]);
}

function send(control, watch, body, act) {
  return attempt(control, act, () => api(`/api/watches/${encodeURIComponent(watch.watch_id)}`, { method: "POST", body: JSON.stringify(body) }), {
    then: () => refresh(),
  });
}

function removeButton(watch) {
  const button = el("button", { type: "button", class: "action quiet", text: "Remove…" });
  button.addEventListener("click", async () => {
    const yes = await confirmAct({
      title: `Remove the Watch “${watch.intent_text}”?`,
      consequence: "Nothing restores it. What it has already found stays in To review. To stop it for a while, switch it off instead.",
      confirmLabel: "Remove",
    });
    if (!yes) return;
    await attempt(button, "remove the Watch", () => api(`/api/watches/${encodeURIComponent(watch.watch_id)}`, { method: "DELETE" }), {
      then: () => refresh(),
    });
  });
  return button;
}
