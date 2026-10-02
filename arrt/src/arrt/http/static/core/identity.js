/* Which Wikidata item a held work or artist is, and the control to change it.
 *
 * Ruling 7 stores the identity; the matcher sets it where it is certain, and
 * this is how the curator corrects it. A wrong item marks the wrong work *Held*
 * and links the wrong artist, so a new item is **looked up and shown before it is
 * stored**: a typo cannot pass as an identity. *There is none* says the item does
 * not exist, which stops the matcher looking, and is confirmed first.
 *
 * **Every refusal is the service's.** The control refuses nothing the routes
 * would accept, so a click and an agent's `art_catalogue` action get the same
 * answer: it shows what the item is first, and a refusal (an item another artist
 * has, one Wikidata does not have, one Wikidata could not be asked about) is
 * the route's, said in its words. Shared by the Artist and Work pages, which call
 * the same two routes (`POST /api/artists|works/{id}/wikidata`). Registry text
 * is shown as text. */

import { api } from "./api.js";
import { confirmAct } from "./confirm.js";
import { isQid, lifeDates, named, wikidataLink } from "./registry.js";
import { el, guard } from "./render.js";

/* `kind` is "work" or "artist"; `record` the work or artist as the library
 * serves it; `onChanged` repaints from the route's answer. */
export function identityControl(kind, record, onChanged) {
  const id = kind === "work" ? record.artwork_id : record.artist_id;
  const path = `/api/${kind === "work" ? "works" : "artists"}/${encodeURIComponent(id)}/wikidata`;
  const said = el("p", { class: "muted", "aria-live": "polite" });
  const field = el("input", { id: `identity-${kind}`, type: "text", inputmode: "text", autocomplete: "off", placeholder: "Q…", spellcheck: "false" });
  const use = el("button", { class: "action", type: "button", text: "Use this item", hidden: true });
  const form = el("div", { class: "stack", hidden: true }, [
    el("div", { class: "row" }, [
      el("div", { class: "field" }, [el("label", { for: `identity-${kind}`, text: "Wikidata item" }), field]),
      el("button", { class: "action quiet", type: "button", text: "Look up", onclick: () => guard(lookUp) }),
    ]),
    said,
    use,
  ]);
  let found = null;

  const lookUp = async () => {
    const qid = field.value.trim().toUpperCase();
    use.hidden = true;
    found = null;
    if (!isQid(qid)) {
      said.textContent = "That is not a Wikidata item id: a Q followed by digits, as in Q160149.";
      return;
    }
    said.textContent = "Asking Wikidata…";
    const sentence = kind === "work" ? await describeWork(qid, id) : await describeArtist(qid, id);
    said.textContent = sentence.words;
    if (sentence.usable) {
      found = qid;
      use.textContent = `Use ${qid}`;
      use.hidden = false;
    }
  };

  use.addEventListener("click", () =>
    guard(async () => {
      if (!found) return;
      onChanged(await api(path, { method: "POST", body: JSON.stringify({ qid: found }) }));
    }),
  );

  const none = el("button", {
    class: "action quiet",
    type: "button",
    text: "There is none",
    onclick: () =>
      guard(async () => {
        const agreed = await confirmAct({
          title: `Say Wikidata has no item for ${kind === "work" ? record.title : record.name}?`,
          consequence: "The matcher stops looking for one. You can set an item here later.",
          confirmLabel: "There is none",
        });
        if (!agreed) return;
        onChanged(await api(path, { method: "POST", body: JSON.stringify({ qid: null }) }));
      }),
  });

  const change = el("button", {
    class: "action quiet",
    type: "button",
    text: "Change…",
    "aria-expanded": "false",
    onclick: () => {
      form.hidden = !form.hidden;
      change.setAttribute("aria-expanded", String(!form.hidden));
      if (!form.hidden) field.focus();
    },
  });

  return el("div", { class: "stack identity" }, [
    el("p", { class: "muted" }, [currentWords(record)]),
    el("div", { class: "row" }, [change, none]),
    form,
  ]);
}

/* What the record says now, and who said it. */
function currentWords(record) {
  if (record.wikidata_qid) {
    const by = record.wikidata_qid_set_by === "curator" ? "set by you" : "matched";
    return el("span", {}, ["Wikidata: ", wikidataLink(record.wikidata_qid, record.wikidata_qid), ` (${by})`]);
  }
  if (record.wikidata_qid_set_by === "curator") return el("span", { text: "Wikidata: none (you said there is none)" });
  return el("span", { text: "Wikidata: not matched yet" });
}

/* With no registry configured the service stores an item unchecked, so the
 * control offers it too, saying so. */
function unchecked(qid) {
  return { words: `Wikidata is not configured on this server, so ${qid} cannot be checked. It can still be stored.`, usable: true };
}

async function describeWork(qid, artworkId) {
  const page = await api(`/api/registry/works/${encodeURIComponent(qid)}`);
  if (page.state === "not_configured") return unchecked(qid);
  if (page.state === "not_found") return { words: `Wikidata has no item ${qid}.`, usable: false };
  if (page.state !== "known") return { words: page.note || "Wikidata could not be asked just now.", usable: false };
  const by = page.creators.length ? `, by ${page.creators.map((c) => named(c.name, c.qid)).join(", ")}` : "";
  const year = page.year ? ` (${page.year})` : "";
  const others = page.held_artwork_ids.filter((other) => other !== artworkId);
  const duplicate = others.length ? " Another work in your library already has this item; both will show as one." : "";
  return { words: `${qid} is “${named(page.title, qid)}”${by}${year}.${duplicate}`, usable: true };
}

async function describeArtist(qid, artistId) {
  const page = await api(`/api/registry/artists/${encodeURIComponent(qid)}`);
  if (page.state === "held") {
    return page.artist_id === artistId
      ? { words: `This artist already has ${qid}.`, usable: false }
      : { words: `Another artist in your library already has ${qid}. Correct that one first.`, usable: false };
  }
  if (page.state === "not_configured") return unchecked(qid);
  if (page.state !== "known") return { words: page.note || "Wikidata could not be asked just now.", usable: false };
  // An item named only in another language (a Japanese painter's, say) is an
  // item all the same; the service accepts it, so the control does too.
  if (!page.name || page.name === qid) return { words: `${qid} exists on Wikidata with no English name; check it is the one you mean.`, usable: true };
  const life = lifeDates(page);
  return { words: `${qid} is ${page.name}${life ? ` (${life})` : ""}.`, usable: true };
}
