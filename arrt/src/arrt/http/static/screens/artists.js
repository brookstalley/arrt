/* Artists — the artists the library holds, and one artist as the hub.
 *
 * **Library › Artists, as Lidarr's artist index is its library** (ruling 4,
 * `ia-proposal.md` § Artist). `#artist` is every held artist with a count;
 * `#artist/<id>` is one: who they are, what the library holds of theirs, what
 * Wikidata lists, and which collections hold their work. `#artist/Q…` is an
 * artist reached through the registry (ruling 2): the registry half alone, or
 * the library's page in its place when the library holds them.
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
import { identityControl } from "../core/identity.js";
import { addedSentence, addWorksToTheme, stoppedSentence } from "../core/membership.js";
import { getSelection } from "../core/getting.js";
import { el, fill, guard, render } from "../core/render.js";
import { isQid, lifeDates, named, stateMark, wikidataLink, workLink, workState } from "../core/registry.js";
import { backLink, backRow, go, redirect, refresh } from "../core/router.js";
import { recordReaction } from "../core/taste.js";

export async function viewArtists(artistId, generation) {
  if (isQid(artistId)) {
    await registryArtist(artistId, generation);
    return;
  }
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
  const similarSection = artist.wikidata_qid ? similarShell() : null;

  render(
    generation,
    el("p", {}, [backLink()]),
    el("div", { class: "panel" }, [
      el("h2", { text: artist.name }),
      facts([
        ["Life", lifeDates(artist)],
        ["Nationality", artist.display_nationality || artist.nationality],
      ]),
      identityControl("artist", artist, () => refresh()),
      about,
      tasteControls(artist),
    ]),
    heldSection(works, themes.themes),
    registrySection,
    similarSection,
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
  if (similarSection) await paintSimilar(similarSection, artist.wikidata_qid);
}

/* An artist addressed by QID. The library's page replaces it when the library
 * holds them, in place, so Back does not return to an address that only
 * forwards. Otherwise the registry is all there is to say, and the page says
 * that nothing of theirs is held. */
async function registryArtist(qid, generation) {
  let view;
  try {
    view = await api(`/api/registry/artists/${encodeURIComponent(qid)}`);
  } catch (failure) {
    if (failure.status !== 400) throw failure;
    view = { state: "unavailable", note: "That is not a Wikidata address.", works: [], holdings: [], movements: [] };
  }
  if (view.artist_id) {
    redirect("artist", view.artist_id);
    return;
  }
  const registrySection = el("section", { class: "panel", "aria-labelledby": "their-work" }, [el("h3", { id: "their-work", text: "Their work" })]);
  const about = el("div", { class: "stack" });
  const similarSection = similarShell();
  // Said only when it can be known. A held work listed here belongs to a library
  // artist who is not matched to this item, so the curator is told where it is;
  // when Wikidata did not answer, nothing is claimed either way.
  const filedElsewhere = view.state === "known" && (view.works || []).some((work) => work.held_artwork_ids.length);
  const heldNote =
    view.state !== "known"
      ? null
      : el("p", {
          class: "note",
          text: filedElsewhere
            ? "Some of their work is in your library, filed under another artist; it is marked Held below."
            : "Nothing of theirs is in your library.",
        });
  render(
    generation,
    el("p", {}, [backLink()]),
    el("div", { class: "panel" }, [
      el("h2", { text: view.name ? named(view.name, qid) : `Wikidata ${qid}` }),
      facts([["Life", lifeDates(view)]]),
      el("p", { class: "muted" }, [wikidataLink(qid, `Wikidata ${qid}`)]),
      about,
      heldNote,
    ]),
    registrySection,
    similarSection,
  );
  paintRegistry(registrySection, about, view);
  await paintSimilar(similarSection, qid);
}

/* *Similar artists* (ruling 4): visual artists sharing a movement, by renown,
 * each with how many of their works have an image, so a curator does not commit
 * to an artist nobody can supply. Asked last: the query takes seconds. */
function similarShell() {
  return el("section", { class: "panel", "aria-labelledby": "similar-artists" }, [
    el("h3", { id: "similar-artists", text: "Similar artists" }),
    el("p", { class: "muted", "aria-live": "polite", text: "Asking Wikidata…" }),
  ]);
}

async function paintSimilar(section, qid) {
  let view;
  try {
    view = await api(`/api/registry/artists/${encodeURIComponent(qid)}/similar`);
  } catch (failure) {
    view = { state: "unavailable", note: "Wikidata could not be asked just now.", artists: [] };
  }
  if (!section.isConnected) return;
  const heading = section.querySelector("h3");
  if (view.state !== "known") {
    fill(section, heading, el("p", { class: "note", text: view.note }));
    return;
  }
  fill(section, 
    heading,
    view.artists.length
      ? el("ul", { class: "results-list" }, view.artists.map((person) =>
          el("li", {}, [
            el("button", { class: "row-title", type: "button", text: named(person.name, person.qid), onclick: () => go("artist", person.artist_id || person.qid) }),
            lifeDates(person) ? el("span", { class: "muted", text: ` ${lifeDates(person)}` }) : null,
            el("span", { class: "muted", text: ` · ${person.images} ${person.images === 1 ? "work" : "works"} with an image` }),
            stateMark({ held: Boolean(person.artist_id) }),
          ]),
        ))
      : el("p", { class: "muted", text: "Wikidata records no movement shared with another painter." }),
  );
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
 * or *Image found* where Wikidata has a free image; then the collections.
 *
 * Every work the library does not hold can be ticked and got, image found or not:
 * a museum may hold one Wikidata has no picture of. A held row has no tick box. */
function paintRegistry(section, about, view) {
  const heading = section.querySelector("h3");
  if (view.state !== "known") {
    fill(section, heading, el("p", { class: "note", text: view.note }));
    return;
  }
  fill(about, 
    view.description ? el("p", { text: view.description }) : null,
    view.movements.length ? el("p", { class: "muted", text: view.movements.join(", ") }) : null,
  );
  const getting = getSelection();
  const rows = view.works.map((work) =>
    el("tr", {}, [
      el("td", {}, [work.held_artwork_ids.length ? null : getting.box(work.qid, named(work.title, work.qid))]),
      el("td", {}, [workLink(work)]),
      el("td", { text: work.year ? String(work.year) : "—" }),
      el("td", {}, [workState(work)]),
    ]),
  );
  const holdings = view.holdings.map((holding) => el("li", { text: `${named(holding.name, holding.qid)}: ${holding.works}` }));
  fill(section, 
    heading,
    view.works.length
      ? el("div", { class: "artist-works" }, [el("table", {}, [
          el("caption", {
            text: `The most renowned of the ${view.works_total} works Wikidata lists, by how many Wikipedias cover them, and every one the library holds`,
          }),
          el("thead", {}, [el("tr", {}, ["Get", "Work", "Year", "State"].map((h) => el("th", { scope: "col", text: h })))]),
          el("tbody", {}, rows),
        ])])
      : el("p", { class: "muted", text: "Wikidata lists no works for them." }),
    view.works.some((work) => !work.held_artwork_ids.length) ? getting.node : null,
    el("h3", { id: "holdings", text: "Holdings" }),
    holdings.length ? el("ul", { "aria-labelledby": "holdings" }, holdings) : el("p", { class: "muted", text: "Wikidata names no collection holding their work." }),
  );
}
