/* Artists — the artists the library holds, and one artist as the hub.
 *
 * **Library › Artists, as Lidarr's artist index is its library** (ruling 4,
 * `ia-proposal.md` § Artist). `#artist` is every held artist with a count;
 * `#artist/<id>` is one: who they are, what the library holds of theirs, what
 * Wikidata lists, and which collections hold their work.
 *
 * **Two halves, asked separately, and the order is the design.** The library
 * half (`/api/artists/<id>` and the artist's works) always answers and is drawn
 * first. The registry half (`/api/artists/<id>/registry`) can take seconds, may
 * not be configured, and may fail; it fills its own section when it answers and
 * says which of those it was when it does not, so a slow or absent Wikidata never
 * holds back what the curator owns.
 *
 * **Every string from the registry is untrusted text.** Titles, descriptions,
 * movement and collection names are written by anyone, so they reach the page
 * through `el`'s `text` and never as markup; image sources are Commons file URLs
 * the server has already checked, and nothing else is offered as one. */

import { api, fetchAllWorks } from "../core/api.js";
import { absentImage, facts } from "../core/badges.js";
import { addedSentence, addWorksToTheme, stoppedSentence } from "../core/membership.js";
import { el, guard, render } from "../core/render.js";
import { backLink, backRow, go } from "../core/router.js";
import { recordReaction } from "../core/taste.js";

export async function viewArtists(artistId, generation) {
  if (artistId) {
    await oneArtist(artistId, generation);
    return;
  }
  const listing = await api("/api/artists");
  const rows = listing.artists.map(({ artist, held }) =>
    el("tr", {}, [
      el("td", {}, [el("button", { class: "row-title", type: "button", text: artist.name, onclick: () => go("artist", artist.artist_id) })]),
      el("td", { text: lifeDates(artist) || "—" }),
      el("td", { text: String(held) }),
    ]),
  );
  render(
    generation,
    backRow(),
    el("h2", { text: "Artists" }),
    listing.artists.length
      ? el("table", {}, [
          el("caption", { text: `${listing.artists.length} ${listing.artists.length === 1 ? "artist" : "artists"} with works in the library` }),
          el("thead", {}, [el("tr", {}, ["Artist", "Life", "Works held"].map((h) => el("th", { scope: "col", text: h })))]),
          el("tbody", {}, rows),
        ])
      : el("div", { class: "panel" }, [
          el("p", { class: "muted", text: "No artists yet. Works you accept bring their artists here." }),
          el("button", { class: "action", type: "button", text: "Add New", onclick: () => go("discover") }),
        ]),
  );
}

/* One artist, addressed by `#artist/<id>`. An address that names nobody the
 * catalogue holds is an ordinary state, for the reason one theme's is: a link
 * outlives what it pointed at. */
async function oneArtist(artistId, generation) {
  let page;
  try {
    page = await api(`/api/artists/${encodeURIComponent(artistId)}`);
  } catch (failure) {
    // Only the refusal says nobody is here; a fault is the error banner's, and
    // telling a curator an artist is gone because the server stumbled would
    // send them looking for something that was never lost.
    if (failure.status !== 400) throw failure;
    render(
      generation,
      el("p", {}, [backLink()]),
      el("h2", { text: "That artist is not here" }),
      el("p", { class: "note", text: "Nothing in the library has this address. The artists the library holds are listed together." }),
      el("div", { class: "row" }, [el("button", { class: "action", type: "button", text: "All artists", onclick: () => go("artist") })]),
    );
    return;
  }
  const artist = page.artist;
  // Paged by the shared loop, which sends no limit of its own: the server's
  // default and cap govern, and the client holds no copy of either (`core/api.js`).
  const [works, themes] = await Promise.all([
    fetchAllWorks("", null, null, null, { artistId, status: "accepted" }),
    api("/api/themes"),
  ]);

  const registrySection = el("section", { class: "panel", "aria-labelledby": "their-work" }, [
    el("h3", { id: "their-work", text: "Their work" }),
    el("p", { class: "muted", "aria-live": "polite", text: "Asking Wikidata…" }),
  ]);
  const about = el("div", { class: "stack" });

  render(
    generation,
    el("p", {}, [backLink()]),
    el("div", { class: "panel" }, [
      el("h2", { text: artist.name }),
      facts([
        ["Life", lifeDates(artist)],
        ["Nationality", artist.display_nationality || artist.nationality],
      ]),
      artist.wikidata_qid ? el("p", { class: "muted" }, [wikidataLink(artist.wikidata_qid, `Wikidata ${artist.wikidata_qid}`)]) : null,
      about,
      tasteControls(artist),
    ]),
    heldSection(works, themes.themes),
    registrySection,
  );

  // After the page is drawn, and into its own section: see the module's note
  // on the two halves.
  let view;
  try {
    view = await api(`/api/artists/${encodeURIComponent(artistId)}/registry`);
  } catch (failure) {
    view = { state: "unavailable", note: "Wikidata could not be asked just now. What the library holds is above; try again later." };
  }
  if (!registrySection.isConnected) return;
  paintRegistry(registrySection, about, view);
}

function lifeDates(artist) {
  if (artist.born || artist.died) return `${artist.born || "?"}–${artist.died || ""}`;
  return artist.lifespan_text || null;
}

/* A link out to Wikidata. The QID is the server's, checked against `Q` and
 * digits, so the address cannot be bent into anything else. */
function wikidataLink(qid, text) {
  return el("a", { href: `https://www.wikidata.org/wiki/${encodeURIComponent(qid)}`, rel: "noopener noreferrer", target: "_blank", text });
}

/* *More like this* and *Not this*, the same two of the three reactions a
 * conversation sample offers and in the same words (`core/taste.js`): one
 * judgment about one artist, wherever it is made. */
function tasteControls(artist) {
  const said = el("p", { class: "muted", "aria-live": "polite" });
  const react = (reaction) =>
    guard(async () => {
      await recordReaction({ kind: "artist", value: artist.name, reaction });
      said.textContent = `Recorded: ${reaction} for ${artist.name}.`;
    });
  return el("div", { class: "row" }, [
    el("button", { class: "action quiet", type: "button", text: "More like this", onclick: () => react("more like this") }),
    el("button", { class: "action quiet", type: "button", text: "Not this", onclick: () => react("not this") }),
    said,
  ]);
}

/* *In your library*: the artist's works in circulation, each selectable, and
 * *Add to theme* on the selection, the act Library › Works offers on one. */
function heldSection(works, themes) {
  const chosen = new Set();
  const announcement = el("p", { class: "muted selection-status", "aria-live": "polite", tabindex: "-1" });
  const picker = el("select", { id: "artist-add-to-theme", "aria-label": "Theme to add the selected works to" });
  for (const placement of themes) picker.append(el("option", { value: placement.theme.theme_id, text: placement.theme.name }));
  const add = el("button", { class: "action", type: "button", text: "Add to theme", disabled: true });
  // Not rewritten unchanged, as on Artworks: a live region reassigned the same
  // sentence announces it again, which trains a listener to tune the region out.
  const say = (words) => {
    if (announcement.textContent !== words) announcement.textContent = words;
  };
  const settle = () => {
    add.disabled = chosen.size === 0 || !themes.length;
    say(chosen.size === 0 ? "No works selected." : `${chosen.size} selected.`);
  };
  const grid = el("ul", { class: "grid" }, works.works.map((work) => heldCard(work, chosen, settle)));
  add.addEventListener("click", () =>
    guard(async () => {
      const name = picker.options[picker.selectedIndex].text;
      const untick = (artworkId) => {
        chosen.delete(artworkId);
        const box = grid.querySelector(`[data-artwork="${CSS.escape(artworkId)}"] input[type="checkbox"]`);
        if (box) box.checked = false;
      };
      let outcome;
      try {
        outcome = await addWorksToTheme(picker.value, [...chosen], { onAdded: untick });
      } catch (failure) {
        settle();
        if (failure.progress) say(stoppedSentence(failure.progress, name));
        announcement.focus();
        throw failure;
      }
      for (const artworkId of [...chosen]) untick(artworkId);
      settle();
      say(addedSentence(outcome, name));
      announcement.focus();
    }),
  );
  settle();
  const shown = works.works.length;
  return el("section", { class: "panel", "aria-labelledby": "in-your-library" }, [
    el("h3", { id: "in-your-library", text: `In your library (${works.total})` }),
    shown
      ? grid
      : el("p", { class: "muted", text: "None of their works is in circulation." }),
    works.total > shown ? el("p", { class: "muted", text: `Showing ${shown} of ${works.total}.` }) : null,
    shown && themes.length
      ? el("div", { class: "row" }, [el("div", { class: "field" }, [el("label", { for: "artist-add-to-theme", text: "Theme" }), picker]), add, announcement])
      : null,
  ]);
}

function heldCard(work, chosen, settle) {
  const box = el("input", { type: "checkbox", "aria-label": `Select ${work.title}` });
  box.addEventListener("change", () => {
    if (box.checked) chosen.add(work.artwork_id);
    else chosen.delete(work.artwork_id);
    settle();
  });
  const picture = work.image.available
    ? el("img", { src: `/api/works/${encodeURIComponent(work.artwork_id)}/thumbnail`, alt: "", loading: "lazy" })
    : absentImage(work.image.note);
  return el("li", { class: "card", "data-artwork": work.artwork_id }, [
    el("label", { class: "card-select" }, [box]),
    el("div", { class: "card-image" }, [picture]),
    el("div", { class: "card-body" }, [
      el("h4", { class: "card-title" }, [el("button", { type: "button", text: work.title, onclick: () => go("work", work.artwork_id) })]),
      el("p", { class: "card-meta", text: work.date_created || " " }),
    ]),
  ]);
}

/* The registry half, once it has answered: what Wikidata lists, most renowned
 * first, each marked *Held* where the library holds it (by QID, never by title)
 * or *Image found* where Wikidata has a free image; then the collections. */
function paintRegistry(section, about, view) {
  const heading = section.querySelector("h3");
  if (view.state !== "known") {
    section.replaceChildren(heading, el("p", { class: "note", text: view.note }));
    return;
  }
  about.replaceChildren(
    view.description ? el("p", { text: view.description }) : null,
    view.movements.length ? el("p", { class: "muted", text: view.movements.join(", ") }) : null,
  );
  const rows = view.works.map((work) =>
    el("tr", {}, [
      el("td", {}, [wikidataLink(work.qid, named(work.title, work.qid))]),
      el("td", { text: work.year ? String(work.year) : "—" }),
      el("td", {}, [workState(work)]),
    ]),
  );
  const holdings = view.holdings.map((holding) => el("li", { text: `${named(holding.name, holding.qid)}: ${holding.works}` }));
  section.replaceChildren(
    heading,
    view.works.length
      ? el("div", { class: "artist-works" }, [el("table", {}, [
          el("caption", {
            text: `The most renowned of the ${view.works_total} works Wikidata lists, by how many Wikipedias cover them, and every one the library holds`,
          }),
          el("thead", {}, [el("tr", {}, ["Work", "Year", "State"].map((h) => el("th", { scope: "col", text: h })))]),
          el("tbody", {}, rows),
        ])])
      : el("p", { class: "muted", text: "Wikidata lists no works for them." }),
    el("h3", { id: "holdings", text: "Holdings" }),
    holdings.length ? el("ul", { "aria-labelledby": "holdings" }, holdings) : el("p", { class: "muted", text: "Wikidata names no collection holding their work." }),
  );
}

/* A registry name, or what to say when it has none we can read. Wikidata's
 * label service answers with the bare QID for an item with no English or
 * language-neutral label (measured on 2026-10-01: a fifth of Rothko's fifty), and
 * an identifier printed where a title belongs reads as a title. */
function named(label, qid) {
  return label && label !== qid ? label : `No English title (${qid})`;
}

/* Glyph, word and the badge colour, the order every badge here uses. */
function workState(work) {
  const held = work.held_artwork_ids;
  if (held.length) {
    // Two held works naming one item is a duplicate the curator should see,
    // not a mark that quietly picks one; it opens the first.
    const words = held.length === 1 ? "Held" : `Held ×${held.length}`;
    return el("button", { class: "badge badge-held", type: "button", onclick: () => go("work", held[0]) }, [
      el("span", { class: "glyph", text: "●", "aria-hidden": true }),
      el("span", { text: words }),
    ]);
  }
  if (work.image) {
    return el("span", { class: "badge badge-image-found" }, [
      el("img", { src: `${work.image}?width=96`, alt: "", loading: "lazy", referrerpolicy: "no-referrer", class: "badge-thumb" }),
      el("span", { class: "glyph", text: "◐", "aria-hidden": true }),
      el("span", { text: "Image found" }),
    ]);
  }
  return el("span", { class: "muted", text: "—" });
}
