/* Settings — the index of the pages Settings holds.
 *
 * **As Sonarr's and Radarr's v4 /settings page**: the section's own link opens a
 * list of its pages, each a link with one line saying what it holds, rather than
 * opening whichever page happened to be first. Which page is "first" is then no
 * question at all, and a curator who does not know where something is set reads
 * one line per page instead of opening each (`information-architecture.md`
 * § The *arr layout).
 *
 * The pages are listed in the sidebar's order, Taste last: Clients and Sources
 * are what the server works with, and Taste is what it has come to believe. Each
 * row is a link because it navigates (§ Direction: navigation is a link, an act
 * is a button). The lines are written here rather than read from the route
 * table, because what a page holds is said to a curator, and a table entry
 * carries an address and a label.
 */

import { el, render } from "../core/render.js";
import { link } from "../core/router.js";

const PAGES = [
  {
    view: "clients",
    label: "Clients",
    holds: "The Players that show your walls: their tokens, what they last reported, and which wall each output shows.",
  },
  {
    view: "sources",
    label: "Sources",
    holds: "The museums and archives the server searches for images, most preferred first, and whether each loaded.",
  },
  {
    view: "taste",
    label: "Taste",
    holds: "What the product has come to think you like, where each judgment came from, and how to correct it.",
  },
];

export async function viewSettings(generation) {
  render(
    generation,
    el("h1", { text: "Settings" }),
    el(
      "ul",
      { class: "settings-index" },
      PAGES.map(({ view, label, holds }) =>
        el("li", { "data-page": view }, [
          link({ view }, { class: "settings-index-link", text: label }),
          el("p", { class: "muted", text: holds }),
        ]),
      ),
    ),
  );
}
