/* Building nodes, writing them to the page, and saying when that failed.
 *
 * TEXT IS SET WITH textContent, NEVER innerHTML. Titles, descriptions and
 * provider names come from museum sites this product does not control, and
 * `<img src=x onerror=...>` inside a work's title is the whole of that attack.
 *
 * Description markup is the one field with emphasis in it, and it is still not
 * parsed: the catalogue reduces it to <i>/<b> and escaped text at ingest, and
 * `emphasised` below reads exactly those four tags and five escapes as tokens,
 * building each element with `createElement`. Everything else in the string,
 * a tag included, is text — so trusting this field extends to nothing.
 */

import { state } from "./state.js";

/* A page with nothing in it: what is missing, then why or what fills it, then
 * the way on. One shape on every page (`design-direction.md` § Component
 * Patterns, Empty states), so an empty page reads as a state rather than as
 * a page that failed to load. The lead is a paragraph, not a heading: it is
 * what the page says, and a reader moving by headings should not meet it as
 * a section. `next` holds links and acts, the first the one most worth taking. */
export function emptyState(lead, why = null, next = []) {
  return el("div", { class: "empty" }, [
    el("p", { class: "empty-lead", text: lead }),
    why ? el("p", { class: "muted", text: why }) : null,
    next.length ? el("div", { class: "row" }, next) : null,
  ]);
}

export function showError(message) {
  const box = document.getElementById("error");
  box.textContent = message;
  box.hidden = false;
}

export function clearError() {
  const box = document.getElementById("error");
  box.hidden = true;
  box.textContent = "";
}

export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "text") node.textContent = value;
    else if (key === "class") node.className = value;
    else if (key === "onclick") node.addEventListener("click", value);
    // `true` spells itself differently either side of the ARIA boundary, and
    // getting it wrong is silent. An HTML boolean attribute — `checked`,
    // `disabled`, `hidden` — is true by being present, so the empty string is
    // right. An `aria-*` state takes the literal word: `aria-hidden=""` is not a
    // valid token, so it is treated as unset and the thing stays announced.
    // Every glyph in this client was written `"aria-hidden": true`, so until this
    // line every badge read its shape aloud beside the word it accompanies —
    // "black circle native", "circled division slash archived".
    else node.setAttribute(key, value === true ? (key.startsWith("aria-") ? "true" : "") : String(value));
  }
  for (const child of [].concat(children)) {
    if (child) node.append(child);
  }
  return node;
}

/* Replace a node's children, leaving out the ones a condition left empty.
 *
 * `replaceChildren` writes a `null` argument as the word "null", so a page built
 * with `condition ? node : null` printed it wherever the condition was false. Every
 * screen goes through here instead, and `test_client_vocabulary.py` refuses a
 * direct call anywhere else. */
export function fill(node, ...children) {
  node.replaceChildren(...children.filter((child) => child !== null && child !== undefined && child !== false));
}

let captions = 0;

/* An act with one line of words under it, tied to it for a screen reader.
 *
 * The words say something about pressing — what it costs, what it starts — so
 * they sit under the act they belong to and are read with it
 * (`aria-describedby`), and they are plain text: nothing about them looks or
 * behaves like a second act. */
export function captioned(act, words) {
  captions += 1;
  const id = `caption-${captions}`;
  act.setAttribute("aria-describedby", id);
  return el("div", { class: "captioned" }, [act, el("span", { class: "act-caption", id, text: words })]);
}

/* Write a view's nodes to the page, unless the curator has moved on.
 *
 * `generation` is `state.nav` as it stood when this paint began, and passing it
 * is not ceremony: every view here awaits at least one request and three page
 * through up to fifty, so a paint routinely completes after the view it belongs
 * to is gone — and `replaceChildren` would put it over whatever replaced it,
 * with the sidebar highlight and the fragment both naming the other screen.
 * A stale screen that looks live is the class of defect this client has shipped
 * three times.
 *
 * Taken as an argument rather than read from a shared variable, which is what
 * this was first written as. A module-level "currently painting" is overwritten
 * by the LATER navigation, so the abandoned paint reads the generation that
 * superseded it and lands anyway — the guard passes and does nothing. A test
 * caught that; the value has to travel with the paint that captured it.
 *
 * It is also why the argument comes first and is required: a view that forgets
 * it passes a DOM node where a number belongs, and the check below throws
 * instead of silently painting whatever it was handed. */
export function render(generation, ...nodes) {
  if (typeof generation !== "number") {
    throw new TypeError("render() takes the navigation generation first; a view that omits it cannot be superseded.");
  }
  if (generation !== state.nav) return;
  const view = document.getElementById("view");
  fill(view, ...nodes);
}

/* Run something that talks to the server, and say so when it refuses.
 *
 * Failures are announced, not only shown: a curator who learns about a refused
 * operation by noticing a colour is a curator who misses it. */
export async function guard(work) {
  try {
    await work();
    clearError();
  } catch (failure) {
    showError(failure.message);
  }
}

/* A description's emphasis, from the markup the catalogue stores, without parsing HTML.
 *
 * The catalogue writes descriptions as escaped text with balanced `<i>` and `<b>`
 * (`services/fields.py`, `description_markup`), so this reads only those four
 * tags and the five escapes Python's `html.escape` produces. Anything else —
 * another tag, an attribute, an entity it did not write — is shown as the text
 * it is, so a row stored before the reduction, or written some other way, reads
 * as its own characters rather than as markup. A closer that does not close the
 * innermost open tag is text too (the reduction never crosses tags), and an
 * opener left open closes at the end.
 *
 * Returns a `<span class="described">`, whose stylesheet keeps the blank lines
 * the reduction leaves between paragraphs. */
const EMPHASIS_TOKENS = /<\/?[ib]>|&(?:amp|lt|gt|quot|#x27);/g;
const ESCAPES = { "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#x27;": "'" };

export function emphasised(markup) {
  const root = el("span", { class: "described" });
  const open = [root];
  const append = (text) => {
    if (text) open[open.length - 1].append(document.createTextNode(text));
  };
  const text = String(markup);
  let at = 0;
  for (const match of text.matchAll(EMPHASIS_TOKENS)) {
    append(text.slice(at, match.index));
    at = match.index + match[0].length;
    const token = match[0];
    if (token in ESCAPES) {
      append(ESCAPES[token]);
    } else if (token[1] !== "/") {
      const node = document.createElement(token[1]);
      open[open.length - 1].append(node);
      open.push(node);
    } else if (open.length > 1 && open[open.length - 1].localName === token[2]) {
      open.pop();
    } else {
      append(token);
    }
  }
  append(text.slice(at));
  return root;
}
