/* The sidebar: sections, the pages beneath them, and the drawer it becomes on a phone.
 *
 * `information-architecture.md` § Direction lays the surface out like the *arr
 * apps, and § The *arr layout is what this draws: a list of sections, each a link
 * to its first page, with the current section's other pages listed beneath it
 * the way Sonarr and Radarr list theirs.
 *
 * **Built once, from the route table, and lit on every navigation.** Built once
 * because the System link holds the status badge, which `core/status.js` paints
 * after a fetch; a sidebar rebuilt per navigation would drop the badge and
 * redraw it a moment later on every click. Built from the table because the
 * labels then have one source, and a static copy in `index.html` is a second
 * place for the sidebar to stop matching what it navigates to.
 *
 * Mechanism only, like `router.js`: this module knows no screen, is handed the
 * table and the sections by `app.js`, and is handed `go` by the router rather
 * than importing it, so the two do not import each other.
 */

import { el, fill } from "./render.js";

/* The page a section's own link opens, and which pages it lists beneath it.
 *
 * A section's link opens its first page in table order. A page whose label is
 * the section's own label *is* that link and is not listed again — Artworks
 * under Artworks, Walls under Walls. Every other page is listed, which is why
 * Status sits under System and Taste under Settings, as they do in Sonarr. */
function layout(table, sections) {
  const pages = Object.entries(table).filter(([, entry]) => entry.page);
  return sections.map((section) => {
    const own = pages.filter(([, entry]) => entry.section === section.key);
    if (!own.length) throw new Error(`The ${section.label} section has no page in the route table.`);
    return {
      section,
      opens: own[0][0],
      listed: own
        .filter(([, entry]) => entry.page !== section.label)
        .map(([view, entry]) => ({ view, label: entry.page, badge: entry.badge })),
    };
  });
}

/* A link that navigates through the router rather than only through the address.
 *
 * A real `href`, so a page opens in a new tab or is copied like any *arr link.
 * The click still goes through `go`, because following a link to the address
 * already showing fires no `hashchange`, and clicking the page you are on must
 * still return it to its unfiltered state, as it always has. */
function link(view, attrs, children, pick) {
  return el(
    "a",
    {
      href: `#${view}`,
      "data-view": view,
      ...attrs,
      onclick: (event) => {
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
        event.preventDefault();
        pick(view);
      },
    },
    children,
  );
}

let sections = [];

/* Draw the sidebar. `pick(view)` is the router's `go`, plus closing the drawer. */
export function paintSidebar(table, sectionList, pick) {
  const nav = document.getElementById("sidebar");
  sections = layout(table, sectionList);
  fill(nav,
    el(
      "ul",
      {},
      sections.map(({ section, opens, listed }) =>
        el("li", { class: "section", "data-section": section.key }, [
          link(
            opens,
            { class: "section-link" },
            [
              el("span", { class: "glyph", text: section.glyph, "aria-hidden": true }),
              el("span", { class: "label", text: section.label }),
              // The slot `core/status.js` fills. Marked here rather than found by
              // label, so renaming the section cannot silently orphan the badge.
              section.status ? el("span", { class: "status-slot", "data-status-slot": true }) : null,
              // A count `core/awaiting.js` fills, for the section whose queue needs the curator.
              section.badge ? el("span", { class: "count-slot", "data-count-slot": section.badge }) : null,
            ],
            pick,
          ),
          listed.length
            ? el(
                "ul",
                { class: "pages" },
                listed.map(({ view, label, badge }) =>
                  el("li", {}, [
                    link(
                      view,
                      {},
                      [
                        el("span", { class: "label", text: label }),
                        badge ? el("span", { class: "count-slot", "data-count-slot": badge }) : null,
                      ],
                      pick,
                    ),
                  ]),
                ),
              )
            : null,
        ]),
      ),
    ),
  );
}

/* Mark where the curator is.
 *
 * **One link carries `aria-current`, and it is the page's own.** Settings' link
 * and Taste's point at the same address, and marking both would tell a screen
 * reader it is on two pages. So the listed page's link is marked when there is
 * one, and the section link only when the page is the section itself. The
 * current section is shown open through `data-open`, which is styling, not
 * state a reader needs announced. */
export function lightSidebar(page) {
  const nav = document.getElementById("sidebar");
  for (const node of nav.querySelectorAll("[aria-current]")) node.removeAttribute("aria-current");
  for (const node of nav.querySelectorAll("li.section")) node.removeAttribute("data-open");
  const current = sections.find(({ opens, listed }) => opens === page || listed.some((entry) => entry.view === page));
  if (!current) return;
  const item = nav.querySelector(`li.section[data-section="${current.section.key}"]`);
  item.setAttribute("data-open", "");
  const listed = item.querySelector(`ul.pages a[data-view="${page}"]`);
  (listed || item.querySelector("a.section-link")).setAttribute("aria-current", "page");
}

/* The phone's drawer: a menu button that shows and hides the sidebar.
 *
 * Below 40rem the stylesheet hides the sidebar unless `data-open` is set on it,
 * and shows the menu button, which is hidden everywhere else. Escape closes it
 * and focus goes back to the button, because a drawer that closes with focus
 * inside it leaves a keyboard user standing on nothing.
 *
 * **A backdrop behind it closes it on a tap.** The open drawer covers the menu
 * button, and a phone has no Escape key, so without one the only way out was to
 * pick a page. */
export function installDrawer() {
  const nav = document.getElementById("sidebar");
  const button = document.querySelector("button.menu-button");
  const backdrop = el("div", { class: "drawer-backdrop", "aria-hidden": true });
  nav.after(backdrop);
  const set = (open) => {
    button.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) {
      nav.setAttribute("data-open", "");
      backdrop.setAttribute("data-open", "");
    } else {
      nav.removeAttribute("data-open");
      backdrop.removeAttribute("data-open");
    }
  };
  backdrop.addEventListener("click", () => {
    set(false);
    button.focus();
  });
  button.addEventListener("click", () => {
    const opening = !nav.hasAttribute("data-open");
    set(opening);
    if (opening) {
      const first = nav.querySelector("[aria-current]") || nav.querySelector("a");
      if (first) first.focus();
    }
  });
  nav.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || !nav.hasAttribute("data-open")) return;
    set(false);
    button.focus();
  });
  return () => set(false);
}
