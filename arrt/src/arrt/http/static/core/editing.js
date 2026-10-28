/* A panel opened over the page: a thing's settings, a choice an act asks, or a
 * list too long for the card it qualifies.
 *
 * `design-direction.md` § Component Patterns, "How a page reads": a thing's
 * settings and its rarer acts are one step away, in a dialog its card or toolbar
 * opens, so the page shows what is true now. `confirm.js` asks one yes-or-no
 * question; this holds whatever the page puts in it, and stays open while the
 * curator works in it.
 *
 * **The platform's `<dialog>` with `showModal()`, for `confirm.js`'s reason**:
 * focus trapping, Escape, and the page behind made inert come from the browser,
 * not from code here. Removed from the document once closed, so ids stay unique
 * across a session of opening and closing.
 *
 * TEXT IS SET WITH textContent, NEVER innerHTML (`render.js`): a title may carry
 * a wall's name or a museum's title for a work.
 */

import { el } from "./render.js";

let opened = 0;

/* Open a panel and return `{ dialog, body, close }`.
 *
 * `body` is the nodes inside it, and stays reachable so a caller can repaint
 * part of it in place. `actions` go at its foot, after *Close*, which is always
 * there and is where the keyboard starts, for `confirm.js`'s reason: the safe
 * answer first. `onClose` runs once, however the panel was closed. */
export function openPanel({ title, lead = null, body = [], actions = [], closeLabel = "Close", onClose = null }) {
  opened += 1;
  const titleId = `panel-title-${opened}`;
  const content = el("div", { class: "panel-dialog-body" }, body);
  const close = el("button", { class: "action quiet", type: "button", text: closeLabel });
  const dialog = el("dialog", { class: "panel-dialog", "aria-labelledby": titleId }, [
    el("h2", { class: "confirm-title", id: titleId, text: title }),
    lead ? el("p", { class: "muted panel-dialog-lead", text: lead }) : null,
    content,
    el("div", { class: "confirm-actions" }, [close, ...actions]),
  ]);
  let settled = false;
  dialog.addEventListener("close", () => {
    if (settled) return;
    settled = true;
    dialog.remove();
    if (onClose) onClose();
  });
  close.addEventListener("click", () => dialog.close());
  // A link in the panel goes to another page, and the panel belongs to the one it
  // was opened on: left open, it would sit modal over the next page.
  const leave = () => dialog.close();
  window.addEventListener("hashchange", leave, { once: true });
  dialog.addEventListener("close", () => window.removeEventListener("hashchange", leave));
  document.body.append(dialog);
  dialog.showModal();
  close.focus();
  return { dialog, body: content, close: () => dialog.close() };
}
