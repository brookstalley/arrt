/* Sources — every installed image source plugin, where it came from, and what it provides.
 *
 * **A page under Settings**, where Radarr keeps Settings › Indexers: the list of
 * the places the server searches. It is the inventory; System › Status reads the
 * same plugins for how they are doing, from the same reading, so the two pages
 * cannot describe a plugin differently.
 *
 * **Read-only.** The order is `SOURCE_ORDER`, and installing or removing a plugin
 * is a change to the image Arrt runs from; neither is an act on this page.
 *
 * **Every plugin is listed, loaded or not**, most preferred first. A declined one
 * is the plugin whose setting a curator comes here to find, and leaving it out
 * would make it look uninstalled. Every unknown is said in words: a plugin
 * registered by no installed package, one that failed before saying which
 * interface it was written for, one that did not load and so provides nothing.
 *
 * TEXT IS SET WITH textContent, NEVER innerHTML — the rule is at `core/render.js`,
 * and a plugin's name, package and reason are text somebody else wrote.
 */

import { api } from "../core/api.js";
import { facts } from "../core/badges.js";
import { museumName, PLUGIN_STATE_WORDS } from "../core/providers.js";
import { el, emptyState, render } from "../core/render.js";

/* What a plugin's parts provide, in the words a curator reads. */
const PART_WORDS = {
  finds_images: "finds images of a work",
  finds_pages: "finds pages about a work, for other plugins to read",
  reads: "reads the addresses it claims",
  browses: "offers a collection to browse",
};

export async function viewSources(generation) {
  const listing = await api("/api/sources");
  const sources = Array.isArray(listing.sources) ? listing.sources : [];
  const interfaceMajor = String(listing.interface_version).split(".")[0];
  render(
    generation,
    el("h1", { text: "Sources" }),
    el("p", {
      class: "muted",
      text:
        `The image source plugins installed in this Arrt, most preferred first: the order breaks a tie between two ` +
        `images ranked level. This Arrt provides plugin interface ${listing.interface_version}. Installing or removing ` +
        "a plugin is a change to the image Arrt runs from, and how each is doing since startup is on Status.",
    }),
    sources.length === 0
      ? emptyState(
          "No source plugin is installed, so no image can be found for a work.",
          "Arrt ships with built-in plugins, so none listed means the package was installed without its entry points.",
        )
      : el("ol", { class: "source-inventory" }, sources.map((source, index) => sourcePanel(source, index, sources.length, interfaceMajor))),
  );
}

function sourcePanel(source, index, count, interfaceMajor) {
  return el("li", { class: "panel source-entry" }, [
    el("h2", { text: museumName(source.name) }),
    el("p", { class: "reading-sentence", text: source.description }),
    facts([
      ["Plugin", source.name],
      ["Package", packageWords(source)],
      ["State", PLUGIN_STATE_WORDS[source.state] || source.state],
      ["Provides", providesWords(source)],
      ["Interface", interfaceWords(source, interfaceMajor)],
      ["Order", `${index + 1} of ${count}`],
    ]),
  ]);
}

function packageWords(source) {
  if (!source.distribution) {
    return "Not known: no installed package names this plugin alone.";
  }
  return source.version ? `${source.distribution} ${source.version}` : `${source.distribution}, version not recorded`;
}

function providesWords(source) {
  const parts = Array.isArray(source.provides) ? source.provides : [];
  if (parts.length === 0) {
    return "Nothing here, because it did not load.";
  }
  const words = parts.map((part) => PART_WORDS[part] || part).join("; ");
  return words.charAt(0).toUpperCase() + words.slice(1) + ".";
}

function interfaceWords(source, interfaceMajor) {
  if (source.api_major === null || source.api_major === undefined) {
    return "Not known: it failed before saying which interface it was written for.";
  }
  const written = `Written for interface ${source.api_major}`;
  return String(source.api_major) === interfaceMajor ? `${written}, which this Arrt provides.` : `${written}; this Arrt provides ${interfaceMajor}.`;
}
