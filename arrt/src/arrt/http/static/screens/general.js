/* General — the settings that apply to the whole of this Arrt.
 *
 * **As Radarr's and Sonarr's Settings › General**: one page of the server's own
 * settings. Each is its own control, a fact that can be changed (`design-direction.md`
 * § How a page reads): its value is the picker, and a change applies when it is
 * made, with no Save, because the server reads every setting when it is used.
 *
 * **A setting the environment gives is locked**, and says so in place of its
 * control: its value, and the variable that sets it. The server refuses a change
 * to it from here or over MCP (`library/services/settings.py`), so offering a
 * control would be offering a dead end.
 *
 * The settings, their order, labels and descriptions are the server's
 * (`GET /api/settings`), so a setting added there appears here with no edit; only
 * the words for a choice's values are written here, falling back to the value.
 *
 * TEXT IS SET WITH textContent, NEVER innerHTML — the rule is at `core/render.js`.
 */

import { api } from "../core/api.js";
import { attempt } from "../core/acting.js";
import { stamp } from "../core/dates.js";
import { el, emptyState, render } from "../core/render.js";
import { refresh } from "../core/router.js";

/* How a choice's value reads, by setting. A value with no words here reads as itself. */
const CHOICE_WORDS = {
  label_units: { imperial: "Imperial (inches)", metric: "Metric (centimetres)" },
};

function choiceWords(setting, value) {
  return (CHOICE_WORDS[setting.key] || {})[value] || value;
}

export async function viewGeneral(generation) {
  const listing = await api("/api/settings");
  const settings = Array.isArray(listing.settings) ? listing.settings : [];
  const locked = settings.filter((setting) => setting.locked).length;
  render(
    generation,
    el("h1", { text: "General" }),
    el("p", {
      class: "page-facts muted",
      text: locked ? `Settings for the whole of this Arrt. ${locked} set in its environment.` : "Settings for the whole of this Arrt.",
    }),
    settings.length === 0
      ? emptyState("There are no settings to change here.", "This Arrt declares none, which is unexpected: the server's own list is empty.")
      : el("dl", { class: "facts settings-general" }, settings.flatMap(settingRow)),
  );
}

function settingRow(setting) {
  const fieldId = `setting-${setting.key}`;
  return [
    el("dt", {}, [el("label", { for: fieldId, text: setting.label })]),
    el("dd", { "data-setting": setting.key }, [
      setting.locked ? lockedValue(setting, fieldId) : picker(setting, fieldId),
      el("p", { class: "muted setting-description", text: setting.description }),
      sourceLine(setting),
    ]),
  ];
}

/* The value, as text, where the environment holds it: no control to press and be refused. */
function lockedValue(setting, fieldId) {
  return el("output", { id: fieldId, class: "setting-locked", text: choiceWords(setting, setting.value) });
}

function picker(setting, fieldId) {
  const control = el(
    "select",
    { id: fieldId, class: "fact-picker" },
    setting.choices.map((value) => el("option", { value, text: choiceWords(setting, value), selected: value === setting.value })),
  );
  control.addEventListener("change", async () => {
    const chosen = control.value;
    const changed = await attempt(
      control,
      `set ${setting.label.toLowerCase()} to ${choiceWords(setting, chosen).toLowerCase()}`,
      () => api(`/api/settings/${encodeURIComponent(setting.key)}`, { method: "POST", body: JSON.stringify({ value: chosen }) }),
      { then: () => refresh() },
    );
    if (!changed) control.value = setting.value;
  });
  return control;
}

/* Where the value came from, when that is worth a line: the environment, or a change and when. */
function sourceLine(setting) {
  if (setting.locked) {
    return el("p", {
      class: "muted setting-source",
      text: `Set by ${setting.environment_variable} in this Arrt's environment. Change it there and restart Arrt, or remove it there to choose it here.`,
    });
  }
  if (setting.source === "stored" && setting.updated_at) {
    return el("p", { class: "muted setting-source" }, ["Changed ", el("time", stamp(setting.updated_at)), "."]);
  }
  return null;
}
