/* A picture, enlarged in place over the page.
 *
 * Asked for on the review cards (the owner, 2026-10-02): clicking a picture
 * should show it larger without leaving the page — the card, its scans and the
 * Why a curator has half typed are all still there when it closes, and the
 * address never changes, so Back still means what it meant.
 *
 * **The platform's `<dialog>` with `showModal()`, for the reasons
 * `core/confirm.js` gives**: focus trapping, Escape, the inert page behind it
 * and the modal semantics are the browser's. It is not that module, because it
 * asks nothing. A confirmation refuses a backdrop click, since a click that
 * misses the question is not an answer to it; this has no question, so a click
 * outside the picture is the most natural way to say "done looking", and it
 * closes. Escape and the Close button close it too.
 *
 * **Focus goes back to the control that opened it**, said here rather than left
 * to the platform's restoration: a pointer press on a button does not focus it
 * in every browser (Safari's does not), and focus restored to `<body>` puts a
 * keyboard user back at the top of a page of cards. **A mutation sweep reports
 * the call as undefended, and that is expected**: the suite runs Chromium, whose
 * own restoration lands in the same place, so deleting it changes nothing a test
 * there can see. The browser test asserts the outcome; this line is what keeps
 * it true in the browser the suite does not run.
 *
 * TEXT IS SET WITH textContent, NEVER innerHTML — `render.js` holds the rule,
 * and a museum's title reaches the alt text here as readily as a card.
 */

import { el } from "./render.js";

export function enlarge({ src, alt, trigger }) {
  const close = el("button", { class: "action quiet", type: "button", text: "Close" });
  const image = el("img", { src, alt });
  // The frame, not the dialog, carries the padding. A click on the backdrop is
  // dispatched to the dialog element itself, and so is a click on the dialog's
  // own padding — so with the padding inside a child, "the target is the
  // dialog" means "outside the picture" and nothing else.
  const dialog = el("dialog", { class: "enlarged", "aria-label": alt }, [
    el("div", { class: "enlarged-frame" }, [image, el("div", { class: "enlarged-actions" }, [close])]),
  ]);

  dialog.addEventListener("close", () => {
    // Removed once closed, as a confirmation is, so opening a dozen pictures in
    // a session leaves no dozen dialogs behind.
    dialog.remove();
    if (trigger && trigger.isConnected) trigger.focus();
  });
  close.addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  image.addEventListener("error", () => {
    image.replaceWith(el("p", { class: "muted", text: "The larger picture could not be loaded just now." }));
  });

  document.body.append(dialog);
  dialog.showModal();
  close.focus();
  return dialog;
}
