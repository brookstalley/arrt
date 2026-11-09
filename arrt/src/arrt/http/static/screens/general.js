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
 * The settings, their order, sections, labels and descriptions are the server's
 * (`GET /api/settings`), so a setting added there appears here with no edit; only
 * the words for a choice's values are written here, falling back to the value.
 * A setting is a picker when it is a choice, and a field otherwise (an amount in
 * dollars, a model's name), applied when the field is left or Enter is pressed.
 *
 * **A stored choice the server sets aside** (one this release or this deployment
 * no longer allows) says so beside its control, with the server's reason,
 * because showing the default alone would pass the choice off as nobody's.
 *
 * **Unattended work** is a section of its own: its settings, then one line from
 * the server saying whether such work may start now and what it has spent this
 * month against its allowance (`GET /api/unattended`).
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
  unattended_work: { off: "Off", on: "On" },
  unattended_cadence: { hourly: "Hourly", daily: "Daily", weekly: "Weekly" },
};

/* What an empty value means, where a setting takes one. */
const EMPTY_WORDS = {
  unattended_model: "Discovery model",
};

/* The section whose settings sit under the page's own name, with no heading of their own. */
const PAGE_SECTION = "General";

function choiceWords(setting, value) {
  if (setting.kind === "money") return `$${value}`;
  if (value === "") return EMPTY_WORDS[setting.key] || "None";
  return (CHOICE_WORDS[setting.key] || {})[value] || value;
}

export async function viewGeneral(generation) {
  const [listing, unattended] = await Promise.all([api("/api/settings"), api("/api/unattended")]);
  const settings = Array.isArray(listing.settings) ? listing.settings : [];
  const locked = settings.filter((setting) => setting.locked).length;
  render(
    generation,
    el("h1", { text: "General" }),
    el("p", {
      class: "page-facts muted",
      text: locked ? `Settings for the whole of this Arrt. ${locked} set in its environment.` : "Settings for the whole of this Arrt.",
    }),
    ...(settings.length === 0
      ? [emptyState("There are no settings to change here.", "This Arrt declares none, which is unexpected: the server's own list is empty.")]
      : sections(settings).map(([name, members]) => section(name, members, unattended))),
  );
}

/* The settings by section, in the order each section first appears. */
function sections(settings) {
  const grouped = new Map();
  for (const setting of settings) {
    if (!grouped.has(setting.section)) grouped.set(setting.section, []);
    grouped.get(setting.section).push(setting);
  }
  return [...grouped.entries()];
}

function section(name, members, unattended) {
  const list = el("dl", { class: "facts settings-general" }, members.flatMap(settingRow));
  if (name === PAGE_SECTION) return list;
  const isUnattended = members.some((setting) => setting.key === "unattended_work");
  return el("section", { class: "panel settings-section", "data-section": name }, [
    el("h2", { text: name }),
    list,
    isUnattended ? el("p", { class: "unattended-standing", text: unattended.sentence }) : null,
    isUnattended ? el("p", { class: "muted unattended-spend", text: spendWords(unattended) }) : null,
  ]);
}

function settingRow(setting) {
  const fieldId = `setting-${setting.key}`;
  return [
    el("dt", {}, [el("label", { for: fieldId, text: setting.label })]),
    el("dd", { "data-setting": setting.key }, [
      setting.locked ? lockedValue(setting, fieldId) : setting.kind === "choice" ? picker(setting, fieldId) : field(setting, fieldId),
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

/* What unattended work has spent this month against its allowance, whatever the standing:
 * the sentence above carries figures only when work may run or the allowance is spent. */
function spendWords(unattended) {
  return `$${unattended.spent_usd} spent this month of a $${unattended.allowance_usd} allowance; $${unattended.remaining_usd} left.`;
}

/* A value typed rather than chosen: dollars to the cent, or a model's name. Sent
 * when it changes and the field is left (or Enter is pressed), refused in the
 * server's words beside it, which then puts the value back. */
function field(setting, fieldId) {
  const money = setting.kind === "money";
  const control = el("input", {
    id: fieldId,
    type: "text",
    class: "setting-field",
    value: setting.value,
    inputmode: money ? "decimal" : null,
    placeholder: EMPTY_WORDS[setting.key] || null,
    autocomplete: "off",
    spellcheck: "false",
  });
  control.addEventListener("change", async () => {
    const typed = control.value.trim();
    const shown = typed === "" ? (EMPTY_WORDS[setting.key] || "nothing").toLowerCase() : money ? `$${typed.replace(/^[$]/, "")}` : typed;
    const changed = await attempt(
      control,
      `set ${setting.label.toLowerCase()} to ${shown}`,
      () => api(`/api/settings/${encodeURIComponent(setting.key)}`, { method: "POST", body: JSON.stringify({ value: typed }) }),
      { then: () => refresh() },
    );
    if (!changed) control.value = setting.value;
  });
  return money ? el("span", { class: "money-field" }, [el("span", { "aria-hidden": "true", text: "$" }), control]) : control;
}

/* Where the value came from, when that is worth a line: the environment, a choice set aside, or a change and when. */
function sourceLine(setting) {
  if (setting.locked) {
    return el("p", {
      class: "muted setting-source",
      text: `Set by ${setting.environment_variable} in this Arrt's environment. Change it there and restart Arrt, or remove it there to choose it here.`,
    });
  }
  if (setting.source === "set_aside") {
    // The household chose something this Arrt no longer allows (an allowance
    // above a budget since lowered): say so, rather than show the default as if
    // nobody had chosen.
    return el("p", {
      class: "setting-source setting-set-aside",
      text: `Your choice was set aside, so the default applies: ${setting.set_aside_reason} Choose again to replace it.`,
    });
  }
  if (setting.source === "stored" && setting.updated_at) {
    return el("p", { class: "muted setting-source" }, ["Changed ", el("time", stamp(setting.updated_at)), "."]);
  }
  return null;
}
