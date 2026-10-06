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
import { identityControl, storeIdentity } from "../core/identity.js";
import { addedSentence, addWorksToTheme, stoppedSentence } from "../core/membership.js";
import { getSelection } from "../core/getting.js";
import { el, fill, guard, render } from "../core/render.js";
import { isQid, lifeDates, listHeadings, named, stateMark, wikidataLink, workCell, workState, yearCell } from "../core/registry.js";
import { backLink, backRow, go, goWithParams, redirect, refresh } from "../core/router.js";
import { state } from "../core/state.js";
import { recordReaction } from "../core/taste.js";
import { menuButton, toolbar } from "../core/toolbar.js";

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
  const count = `${listing.artists.length} ${listing.artists.length === 1 ? "artist" : "artists"} with works in the library`;
  const shown = artistView();
  render(
    generation,
    backRow(),
    el("h2", { text: "Artists" }),
    listing.artists.length
      ? toolbar({
          controls: [
            menuButton({
              label: "View",
              options: ARTIST_VIEWS,
              current: shown,
              onChoose: (value) => goWithParams({ view: value === POSTERS ? "" : value }),
            }),
          ],
        })
      : null,
    listing.artists.length
      ? shown === TABLE
        ? artistTable(listing.artists, count)
        : artistPosters(listing.artists, count)
      : el("div", { class: "panel" }, [
          el("p", { class: "muted", text: "No artists yet. Works you accept bring their artists here." }),
          el("button", { class: "action", type: "button", text: "Ask", onclick: () => go("discover") }),
        ]),
  );
}

/* Library › Artists' two views, Lidarr's names for them: posters by default,
 * the owner's ruling on #173, and the table it had before. The choice is in
 * the address (`?view=table`), as Artworks' View is, so a reload and a link
 * land on it; the default is left out of the address. */
const POSTERS = "posters";
const TABLE = "table";
const ARTIST_VIEWS = [
  { value: POSTERS, label: "Posters" },
  { value: TABLE, label: "Table" },
];

function artistView() {
  return state.params.view === TABLE ? TABLE : POSTERS;
}

/* One card per artist, in surname order, pictured by their first accepted
 * work: no artist has a picture of their own. Every artist the index lists
 * has one, since it lists only artists with a work in circulation. Uncropped,
 * as every work here is shown. A picture that fails to load — a work whose
 * master has not arrived yet — says so in its place, leaving the card's words. */
function artistPosters(artists, count) {
  return el("section", { "aria-label": count }, [
    el("p", { class: "muted", text: count }),
    el("ul", { class: "grid artist-posters" }, artists.map(({ artist, held, pictured_artwork_id: pictured }) => {
      const open = () => go("artist", artist.artist_id);
      const img = el("img", { src: `/api/works/${encodeURIComponent(pictured)}/thumbnail`, alt: "", loading: "lazy" });
      img.addEventListener("error", () => img.replaceWith(el("span", { class: "card-image-absent", text: "No picture" })));
      const picture = el("button", { class: "card-image", type: "button", tabindex: "-1", "aria-hidden": true, onclick: open }, [img]);
      return el("li", { class: "card", "data-artist": artist.artist_id }, [
        picture,
        el("div", { class: "card-body" }, [
          el("h3", { class: "card-title" }, [el("button", { type: "button", text: artist.name, onclick: open })]),
          el("p", { class: "card-meta", text: [lifeDates(artist), `${held} ${held === 1 ? "work" : "works"}`].filter(Boolean).join(" · ") }),
        ]),
      ]);
    })),
  ]);
}

function artistTable(artists, count) {
  const rows = artists.map(({ artist, held }) =>
    el("tr", {}, [
      el("td", {}, [el("button", { class: "row-title", type: "button", text: artist.name, onclick: () => go("artist", artist.artist_id) })]),
      el("td", { text: lifeDates(artist) || "—" }),
      el("td", { text: String(held) }),
    ]),
  );
  return el("table", {}, [
    el("caption", { text: count }),
    el("thead", {}, [el("tr", {}, ["Artist", "Life", "Works held"].map((h) => el("th", { scope: "col", text: h })))]),
    el("tbody", {}, rows),
  ]);
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
  paintRegistry(registrySection, about, view, { name: artist.name, artistId });
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
      ...(view.unlinked || []).map((artist) => namesakeOffer(artist, qid)),
    ]),
    registrySection,
    similarSection,
  );
  paintRegistry(registrySection, about, view, { name: view.name && view.name !== qid ? view.name : null });
  await paintSimilar(similarSection, qid);
}

/* A library artist of this name with no Wikidata item: most likely the same
 * person, held under a record nothing has linked yet, which is why search shows
 * them twice. The curator says so here, and the item is stored as their choice
 * (`POST /api/artists/{id}/wikidata`, the identity control's route, which
 * refuses an item another artist has); their own page then opens. Never linked
 * without the click: two people can share a name. */
function namesakeOffer(artist, qid) {
  const life = lifeDates(artist);
  return el("div", { class: "row namesake" }, [
    el("p", { class: "note", text: `Your library has ${artist.name}${life ? ` (${life})` : ""}, not linked to Wikidata. If they are this person, link them, and this page becomes theirs.` }),
    el("button", {
      class: "action",
      type: "button",
      text: "Link them to this item",
      "aria-label": `Link the library's ${artist.name} to ${qid}`,
      onclick: () =>
        guard(async () => {
          await storeIdentity("artist", artist.artist_id, qid);
          redirect("artist", artist.artist_id);
        }),
    }),
  ]);
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

/* Who Wikidata's name search says an unlinked artist might be, those whose
 * years agree with the library's first, each with *This is them*. The choice is
 * stored as the curator's, through the identity control's route, and the page
 * is drawn again: with an item, *Their work* lists what Wikidata does. */
function candidateList(candidates, artistId) {
  return el("div", { class: "stack" }, [
    el("p", { id: "candidates", text: "Wikidata knows these people by that name. If one is them, say so:" }),
    el("ul", { class: "results-list", "aria-labelledby": "candidates" }, candidates.map((person) => {
      const life = lifeDates(person);
      return el("li", {}, [
        el("span", { text: named(person.name, person.qid) }),
        life ? el("span", { class: "muted", text: ` ${life}` }) : null,
        el("span", { class: "muted" }, [" · ", wikidataLink(person.qid, person.qid)]),
        person.years_agree ? el("span", { class: "muted", text: " · their years agree" }) : null,
        " ",
        el("button", {
          class: "action quiet",
          type: "button",
          text: "This is them",
          "aria-label": `${named(person.name, person.qid)}${life ? `, ${life}` : ""}, ${person.qid}: this is them`,
          onclick: () =>
            guard(async () => {
              await storeIdentity("artist", artistId, person.qid);
              refresh();
            }),
        }),
      ]);
    })),
  ]);
}

/* The way on when Wikidata lists nothing of theirs: Ask, which searches the
 * web and the image sources rather than Wikidata, and is how a living painter's
 * work is usually found. Filled in and never started, as search's *Ask about*
 * is: asking is a paid run, and the curator presses the button beside its price. */
function askForTheirWork(name) {
  return el("div", { class: "row" }, [
    el("button", {
      class: "action",
      type: "button",
      text: "Ask for their work",
      onclick: () => go("discover", null, { term: `Paintings by ${name}` }),
    }),
  ]);
}

/* The registry half, once it has answered: what Wikidata lists, most renowned
 * first, each with a work's mark (`workState`; held is matched by QID, never by
 * title); then the collections.
 *
 * Every work the library does not hold can be ticked and got, image found or not:
 * a museum may hold one Wikidata has no picture of. A held row has no tick box. */
function paintRegistry(section, about, view, { name = null, artistId = null } = {}) {
  const heading = section.querySelector("h3");
  if (view.state !== "known") {
    const candidates = view.candidates || [];
    fill(section,
      heading,
      el("p", { class: "note", text: view.note }),
      candidates.length && artistId ? candidateList(candidates, artistId) : null,
    );
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
      workCell(work),
      yearCell(work),
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
          el("thead", {}, [listHeadings(["Get", "Work", "Year", "State"])]),
          el("tbody", {}, rows),
        ])])
      : el("p", { class: "muted", text: "Wikidata lists no works for them." }),
    view.works.length || !name ? null : askForTheirWork(name),
    view.works.some((work) => !work.held_artwork_ids.length) ? getting.node : null,
    el("h3", { id: "holdings", text: "Holdings" }),
    holdings.length ? el("ul", { "aria-labelledby": "holdings" }, holdings) : el("p", { class: "muted", text: "Wikidata names no collection holding their work." }),
  );
}
