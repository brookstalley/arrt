/* A table that scrolls sideways can be scrolled from the keyboard.
 *
 * A box that scrolls is only reachable by a pointer unless it can take focus:
 * a keyboard user on a phone met a table whose last columns, the Review link
 * among them, were past its edge with no way to bring them in (`ux-review-2026-10.md`
 * finding 30, `accessibility-spec.md`). So a scroll box that actually overflows
 * becomes a Tab stop, named by its table's caption, and arrow keys scroll it.
 *
 * **Only while it overflows.** A Tab stop on every table that fits would be a
 * stop on nothing, one per table on every page, so each box is watched and the
 * stop comes and goes with the overflow — a window turned from portrait to
 * landscape gains or loses it.
 *
 * Installed once over the view rather than called by each screen, so a table a
 * screen adds later is covered without the screen remembering to ask. */

const SCROLL_BOXES = ".table-scroll, .artist-works";

const watched = new WeakSet();

function settle(box) {
  const overflows = box.scrollWidth > box.clientWidth + 1;
  if (overflows && box.getAttribute("tabindex") !== "0") {
    const caption = box.querySelector("caption");
    box.setAttribute("tabindex", "0");
    box.setAttribute("role", "region");
    box.setAttribute("aria-label", caption && caption.textContent.trim() ? caption.textContent.trim() : "A table wider than the screen");
    box.dataset.scrollStop = "";
  } else if (!overflows && "scrollStop" in box.dataset) {
    box.removeAttribute("tabindex");
    box.removeAttribute("role");
    box.removeAttribute("aria-label");
    delete box.dataset.scrollStop;
  }
}

export function installScrollRegions(root = document.getElementById("view")) {
  if (!root || typeof ResizeObserver === "undefined") return;
  // The table as well as its box: a table that widens inside a box that keeps
  // its size changes the overflow without resizing the box, and the entry it
  // reports is the table's, so each entry settles the box it is in.
  const sizes = new ResizeObserver((entries) => {
    for (const entry of entries) {
      const box = entry.target.closest(SCROLL_BOXES);
      if (box) settle(box);
    }
  });
  const adopt = () => {
    for (const box of root.querySelectorAll(SCROLL_BOXES)) {
      if (watched.has(box)) continue;
      watched.add(box);
      sizes.observe(box);
      const inner = box.querySelector("table");
      if (inner) sizes.observe(inner);
    }
  };
  new MutationObserver(adopt).observe(root, { childList: true, subtree: true });
  adopt();
}
