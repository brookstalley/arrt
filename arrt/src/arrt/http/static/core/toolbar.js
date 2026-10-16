/* The page toolbar, as the *arr apps draw it: actions on the left, and the
 * controls over how the page is shown — View, Sort, Filter — on the right.
 *
 * `information-architecture.md` § The *arr layout. Shared, and knowing no
 * screen: a page hands it its own actions and controls, built with the helpers
 * below, so every list page that has them puts them in the same place.
 *
 * **View and Sort are menu buttons**, and the filter rails' control is a plain
 * button whose label says what it does (*Show filters*, *Hide filters*), built
 * by the page. A menu button names its current choice on its face
 * ("View: Posters"), because a control whose state can only be read by opening
 * it is one a reader has to open to check.
 * The menu is an ARIA menu of `menuitemradio`s: arrow keys move, Enter or Space
 * chooses, Escape closes and hands focus back to the button.
 */

import { el } from "./render.js";

export function toolbar({ actions = [], controls = [] } = {}) {
  return el("div", { class: "page-toolbar" }, [
    el("div", { class: "page-toolbar-actions" }, actions),
    el("div", { class: "page-toolbar-controls" }, controls),
  ]);
}

/* A button that opens a menu of mutually exclusive choices.
 *
 * `options` is `[{ value, label }]`; `current` is the chosen value; `onChoose`
 * receives the value picked. Choosing the current one again does nothing. */
export function menuButton({ label, options, current, onChoose }) {
  const chosen = options.find((option) => option.value === current) || options[0];
  const id = `menu-${label.toLowerCase().replace(/\W+/g, "-")}`;
  const button = el("button", {
    class: "action quiet menu-button-trigger",
    type: "button",
    "aria-haspopup": "menu",
    "aria-expanded": "false",
    "aria-controls": id,
    text: `${label}: ${chosen.label} ▾`,
  });
  const items = options.map((option) =>
    el("li", {
      role: "menuitemradio",
      tabindex: "-1",
      "aria-checked": option.value === chosen.value ? "true" : "false",
      "data-value": option.value,
      text: option.label,
    }),
  );
  const menu = el("ul", { id, class: "toolbar-menu", role: "menu", "aria-label": label }, items);
  menu.hidden = true;

  const close = (refocus) => {
    menu.hidden = true;
    button.setAttribute("aria-expanded", "false");
    if (refocus) button.focus();
  };
  const open = () => {
    menu.hidden = false;
    button.setAttribute("aria-expanded", "true");
    (items.find((item) => item.getAttribute("aria-checked") === "true") || items[0]).focus();
  };
  const choose = (item) => {
    close(true);
    if (item.dataset.value !== chosen.value) onChoose(item.dataset.value);
  };

  button.addEventListener("click", () => (menu.hidden ? open() : close(false)));
  button.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" && menu.hidden) {
      event.preventDefault();
      open();
    }
  });
  for (const item of items) item.addEventListener("click", () => choose(item));
  menu.addEventListener("keydown", (event) => {
    const at = items.indexOf(document.activeElement);
    if (event.key === "Escape") {
      event.preventDefault();
      close(true);
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      items[(at + 1) % items.length].focus();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      items[at <= 0 ? items.length - 1 : at - 1].focus();
    } else if ((event.key === "Enter" || event.key === " ") && at >= 0) {
      event.preventDefault();
      choose(items[at]);
    }
  });
  // Closed by a click anywhere else, as any menu is; focus stays where it went.
  menu.addEventListener("focusout", (event) => {
    if (!menu.contains(event.relatedTarget) && event.relatedTarget !== button) close(false);
  });

  return el("div", { class: "toolbar-menu-wrap" }, [button, menu]);
}
