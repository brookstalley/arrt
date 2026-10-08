---
artifact: information-architecture
version: 1
depends_on:
  - artifact: product-brief
  - artifact: data-model
  - artifact: nonfunctional-requirements
  - artifact: api-contract
last_validated: null
---

# Information Architecture

The curation plane's screen structure, navigation and flows. Authored 2026-08-10,
after the surface had already been built across six chunks — so this artifact is
partly a description of what exists and partly a redesign of it, and every place
those differ is marked **CHANGE** with the reasoning.

> **Direction changed 2026-09-30 — see `re-architecture.md`.** The curation
> plane becomes the **server** of a two-product system. That server holds a
> *Library* (what exists and what to acquire) and *Programming* (what hangs
> where), and it runs on the household NAS rather than the Pi. **This remains the
> one human interface.** *(The navigation norm below was amended later the same
> day, to the *arr layout. The owner's ruling and its cost are in § Direction.)*
> What moves underneath:
> themes become **playlists** owned by Programming, possibly smart ones defined
> by rules over facts and tags; a second, open layer of *programming tags* sits
> beside the Library's facets; and **Watches** (standing searches) join
> discovery. None of that is designed into a screen yet. § Open questions names
> where each is expected to land. No table in this artifact changed, because no
> screen was added or removed.

> **Direction changed 2026-10-01 — see `ia-proposal.md` § Rulings.** The owner
> ruled nine decisions on an IA derived from `user-scenarios.md`: one-world search
> (held and unheld works together, each with its state), an Artist page as hub,
> Topic pages, Add New dissolved into a *Get* action and *Ask*, a default *All
> works* theme that ordinary acceptances join, registry IDs stored, and hanging
> for a duration left to wave 4. *(2026-10-02: ruling 5a's "excursion" became a
> **destination** on every Get, *All works* by default or any other theme, by the
> owner's rulings in `build-plan-topics-and-destinations.md`, which also places
> Topics under Library. *Topic pages* are built by that plan's Chunk 05: Library ›
> Topics at `#topics` and one topic at `#topic/<qid>`, in the tables below.)* **This artifact still describes what runs**, and
> its tables are guarded against the built client. Where the two differ,
> `ia-proposal.md` wins for the target and this text wins for today, until the
> build plan that lands each piece amends it.

## Direction

<!-- Ratified by the owner 2026-08-11. Amended by the owner 2026-09-30. Enforcement row in project-preferences.md. -->

**The curation surface is laid out like the *arr apps.** It has a sidebar of
sections, each with its pages listed beneath it, a top bar that carries search,
a toolbar on list pages, and the library as the home page. If Arrt has a
page that an *arr app also has, it goes where the *arr app puts it and uses the
*arr app's name. If Arrt has a page no *arr app has, it goes in the section
whose *arr meaning is closest. A new top-level section needs an *arr precedent
(Wanted, Calendar) or an owner ruling. A subsystem that gains a UI gets a page
inside an existing section, not a section of its own.

> **Why:** the owner ruled on 2026-09-30: *"More important to be familiar than to
> have our own thing."* Arrt runs on the NAS beside Sonarr, Radarr and
> tacularr (`re-architecture.md` § Deployment target), and its operator moves
> between them. A page placed where every sibling app places it takes no effort to
> find. A page placed where only Arrt would place it has to be learned, and
> relearned by anyone else who opens it.
>
> **What the amendment replaced, and what it costs.** The 2026-08-11 statement
> read: *"The curation surface is organised around what a curator does, never
> around the pipeline's stages."* It required three flat destinations (the
> Walls, Collection, Discover), no drawer, and the Walls as home. Its why was that
> five tabs named for pipeline stages had each been correct as the chunk that
> produced it, and wrong in the sum. The *arr layout knowingly breaks that rule in
> two places: **Activity** (Queue, History) and **System** (Status) are organised
> around how the software works. The owner's ruling accepts that cost. *(Builder's
> reading, 2026-09-30:)* the old why survives in one clause. A subsystem that
> gains a UI still does not get a section of its own, which is the last sentence
> of the statement. That clause catches the same sixth-tab drift the old norm was
> written against.
>
> **Enforcement:** the Critic judges placement and naming, because neither can be
> found with a grep. The browser suite holds the sidebar's shape (its sections, their
> pages, and the home page) from `build-plan-arr-navigation.md` Chunk 02 on.
>
> **Status:** steady-state. The migration, `build-plan-arr-navigation.md`, landed
> on the same branch as this amendment.
>
> **Retroactivity:** migrate, completed at birth: `build-plan-arr-navigation.md`
> moved every page of the built surface into the sidebar, and there are no
> residual sites.
>
> **Ruled departure, 2026-10-01: Add New is dissolved.** Every *arr app has an
> Add New page, so the norm would keep one. The owner ruled it away
> (`ia-proposal.md` ruling 3): acquiring becomes a *Get* action on any selection,
> and the conversation becomes *Ask*, under Library where Add New stood. The rest
> of the target sidebar keeps the norm (ruling 9): no new top-level section, and
> *arr names where an *arr page exists (Queue, History, Wanted).
>
> **Ruling 2026-10-05 (the owner, at the Norm Health sweep): Wanted becomes a
> top-level section.** Ruling 9 placed it under Activity, which the paragraph
> above described as keeping the norm. It did not: Sonarr, Radarr and Lidarr all
> give Wanted its own section, and this statement names Wanted as the precedent
> for one. The owner chose the precedent over ruling 9 for this page. Activity
> keeps Queue and History. Built by `build-plan-norm-sweep-2026-10.md`, which
> brings the tables below to match.

<!-- Ratified by the owner 2026-10-07. Enforcement row in project-preferences.md. -->

**Navigation is a link; an act is a button.** Anything that takes the curator
to another screen or address is an `<a href="#…">`, so it opens in a new tab,
copies as an address, previews in the status bar, and is announced as a link.
A `<button>` does something here: accept, hang, get, archive, sort, open a menu.
A control is never both.

> **Why:** the first UX walkthrough (`ux-review-2026-10.md`, finding 4) found
> every work, artist, topic, run and review opened by a button calling the
> router, while the sidebar and one Walls link were real links. Nothing had
> chosen buttons: the router answers a plain `#…` link already. The cost was
> four lenses' worth of findings: no new tab or copyable address, links that
> look like tags and buttons that look like links, and a screen reader that
> announces "Open … in Artworks" (moves you) and "Accept" (spends) the same way.
> Each screen's button was a locally reasonable choice, which is the shape a
> norm exists for.
>
> **How a link is built:** `link()` in `core/router.js` — an `href` from the
> same `formatRoute` the router writes, and a plain click still routed through
> `go`, which remembers where the page it leaves was scrolled and which link left
> it, so Back returns there with that link focused. A click with a modifier is
> the browser's (a new tab). Arriving at a screen scrolls to its top and focuses
> the view without scrolling it; a change of state on the same screen (a sort, a
> filter) keeps the place.
>
> **What stays a button, and why it is not navigation:** an act that lands
> somewhere afterwards (Ask's *Get* opens the Get it started); a
> filter, View, Sort or Theme toggle on the page showing, which changes that
> page's state rather than which page it is (`goWithParams`). **And one recorded
> exception:** the top-bar search's suggestions are `role="option"` rows of a
> combobox, chosen with the arrow keys and Enter, which ARIA does not allow to
> be links; *All results for "…"* among them opens the results page, whose
> address is a link everywhere else. *(Builder's decision, 2026-10-07 —
> challenge it if the combobox is ever replaced.)*
>
> **Enforcement:** `arrt/tests/unit/test_navigation_is_a_link.py` reads every
> client module and fails on `go(` bound straight to a click or a row's `open`
> handler — the shape every list was built from — naming the file and line. It
> is a pattern over the source, so a navigation reached some other way (a handler
> that calls a helper that calls `go`) passes it; the Critic covers that. The
> browser suite holds the behaviour: `arrt/tests/browser/test_navigation.py`.
>
> **Status:** steady-state. #273 migrated every site (`build-plan-walls-work-and-trust.md`
> Chunk 01).
>
> **Retroactivity:** migrate, completed: no in-content `go(` call is bound to a
> click.

**A working prototype of everything below is committed beside this file:**
`prototypes/curation-ia-prototype.html` — one self-contained page, no build step,
opened directly in a browser. It carries a synthetic 2,000-work corpus because
every scale claim here is unfalsifiable against the real 41. It is a **design
deliverable, not a component**: it shares the product's tokens deliberately, but
nothing in `arrt/` imports from it and it ships to no one.

> **What the prototype does not demonstrate, so it is not mistaken for complete.**
> It has no archived works, so the **Restore** half of the archive rule below has
> nothing to render — the two Archive controls are there and their undo is not.
> *(The controls read "Remove" and were styled `danger` until 2026-08-11. Both were
> wrong for the same reason and the second was the sharper one: styling a cheap,
> reversible act as destructive produces exactly the hesitation the rule exists to
> prevent. A correction that reached this artifact and not the page it points at is
> this repo's most-recurred learning arriving one file away from where it was
> being applied.)*

## The problem this artifact was written to fix

The built surface has five equal tabs — Works, Discovery, Themes, On the wall,
Health. Those are **the pipeline's internal stages**, in pipeline order. They were
each correct as the chunk that produced them, and the sum is an interface organised
around how the software works rather than around what a curator does.

Three symptoms, each traceable to that:

- **Themes are a separate destination from the collection they select from.** A
  curator organising work sees the collection in one tab and the organisation of it
  in another, and must hold the mapping in their head.
- **Health is a peer of the art.** An appliance-status panel sits at the same rank
  as the catalogue, in a product whose stated identity is "museum, not gadget".
- **The wall is fourth.** The thing the entire product exists to produce is the
  fourth item in the navigation, behind three tabs about producing it.

## Labels

*(The owner, 2026-10-07, #267: "there's a pervasive pattern of 'The works' or
'the sources' labeling that feels affected. Why not just Works, Sources, etc.")*

**A label is a bare noun or a bare verb**: *Works*, *Sources*, *Backup*, *Get*,
*Review*, *Cancel*. That covers every place a word names a thing or an act
rather than saying something about it — navigation, headings, column headers,
buttons, field labels, a contextual screen's way back (*← Get*, *← Review*),
panel titles handed through a helper, and captions. A label may say what it
acts on when the screen does not (*Get again*, *Allow on walls again*), and
never opens with an article. **Sentences stay sentences**: notes, empty states,
announcements and failures are written as prose, and "The themes could not be
read" is a sentence, not a label.

Guarded by `tests/preferences/test_labels_are_bare.py`, which reads every string
literal in the client and the text of `index.html` — whatever form the label
takes — and refuses one of five words or fewer that opens with "The ".

## Vocabulary

*(Ruling 4 of 2026-10-07, `ia-proposal.md` § Rulings; #291 and #283.)*

- **Every spending request is a Get**, wherever it started: from words in Ask,
  again for works a Get found no scan of (*Get again*), or for works the curator
  chose. Its page is `#get/<id>`; `#run/<id>` is an alias (`core/route.js`
  `FRAGMENT_ALIASES`), so old links and bookmarks still open it. The server's
  records and the MCP tool still say *run* (`RunKind`, `art_discovery`'s
  `start`, `status`, `list_runs`, `resolve_images`): tool and action names are a
  frozen contract with the agents already calling them, and the MCP surface has
  no action aliases, so `art_discovery`'s summary tells an agent to call a run a
  Get when it speaks to the curator, and the names stay.
- **"Search" means only the free search**: the top bar's box and its results
  page. The model's own web lookups while choosing works are *web lookups*.
- **"Run" is not a curator-facing word**, nor *re-search*, *phase 1*,
  *manifest build* or *directive*. A work comes back to a wall "the next time a
  theme holding it is hung", and re-hanging is how to make that now.
- **One date formatter**, `core/dates.js`: a readable date and how long ago
  ("5 Oct 2026, 14:46 (3 days ago)"). The instant itself goes only in a
  `<time datetime>` or inside a *Details* disclosure; `tests/browser/
  test_no_machine_dates.py` fails on one shown anywhere else.
- **Costs to the cent** (`core/spend.js` `dollars`): "$0.04", and "under $0.01"
  for a cost above nothing that would round to it.
- **Museums by their names**, never by plugin id (`core/providers.js`): "Art
  Institute of Chicago", not `artic`. Server states and reasons are words too
  (a Get's state, why a work is not on a wall, a plugin's state), each map held
  to its enum by `tests/unit/test_client_vocabulary.py`.

## Screen Inventory

Priority is **core** (on a stated core flow) or **supporting**.

| Screen | Purpose | Entry points | Priority |
|---|---|---|---|
| **Walls** | One card per wall, leading with what its screen is doing (`display_state` on `GET /api/walls`, 2026-10-08): the work on it now when it is showing art, otherwise the state in words, then what the wall draws from (a theme, or "a selection") and "until changed". *Skip*, *Not this one again* (from this theme or from every wall), *Change*, and the wall's history *(2026-10-07, `build-plan-walls-work-and-trust.md` Chunk 05)*. | The sidebar; after activating a theme | core (flow 6) |
| **Artworks** | Everything acquired. Find, sort, filter, group, organise into themes, archive. The product's home. *(Collection until 2026-09-30.)* | Launch; the sidebar; the Search results page's *Open in Artworks* (Enter opened it directly until 2026-10-06); from a theme; after a run's accepted works land | core (flows 3, 5) |
| **Work** | One work at full size, with its sources, renditions, mat history and theme membership. **Since 2026-10-07** (`build-plan-walls-work-and-trust.md` Chunk 06) the picture is the wall render, mat and all, and the largest thing on the page; the title under it is the page's heading, then a state strip: the walls and themes the work is on (a selection said as its wall, one hanging nowhere not said), *Hang…* (pick a wall, confirm, and it hangs alone until something else is hung there), and, for a work kept off every wall, that and *Allow on walls again*. Archive is a secondary act after the facts, and a description's emphasis shows as emphasis. At `#work/Q…`, a work Wikidata knows that the library does not hold: its image found or none, with that picture's pixels and fit as a review card gives a scan's, its facts (its size among them, in cm and inches), its holder and number there, *Get this work*, and the rest of its artist's work; the library's own page replaces it, in place, when the library holds it. *(QID form built 2026-10-01, ruling 2.)* **Since 2026-10-06 it shows what the image sources hold now, before any Get** (`build-plan-look-before-get.md`): a panel, *What the image sources hold*, fills in as each source answers, the page polling every two seconds while any is still being asked, with a row per source and the finds best first, each enlargeable; Wikidata's picture stays on top when there is one, and otherwise the first find takes the top and keeps it. The line under *Get this work* reads "These are what the sources hold now; getting the work records them and spends nothing.", and Wikidata's picture, when there is one, is said to be Wikidata's. | A tile in Artworks; a tile on a Wall; a row in Review; a title in an artist's *Their work* or a work's *More by* | core (flows 4, 5) |
| **Search results** | Everything a few words find, in one world (ruling 2), in two groups: *Held*, the library's artists, works and topics that match, and any of Wikidata's matches the library holds that those rows do not show; then *Not held*, the rest of Wikidata's artists, works and topics. An artist row carries no mark, its group saying whether it is held, and a work carries § A work's mark in its grouped words (the owner, 2026-10-06); a top result, marked ● *In your library* or ○ *Not held*, when the words name one artist. Wikidata's works the library does not hold can be ticked and got (*Get N works*). *(Built 2026-10-01, `build-plan-one-world-search.md` Chunk 04; Get added 2026-10-02, `build-plan-get-and-ask.md` Chunk 04; grouped Held / Not held, with topics, replacing the *All*, *In your library*, *Not held* switch, the owner 2026-10-06, `build-plan-search-held-not-held.md`.)* | Enter in the search box; the dropdown's last row, *All results for "…"*; its own address (`#search?q=`; a `view=` left in an old one is ignored) | core (S2, S3) |
| **Ask** | Asking for something in words: the direct intent box on top, then the conversations, with a run's progress shown in the thread that started it. *(Discover until 2026-09-30, when it also listed every run; Add New until 2026-10-02, when ruling 3 made acquiring a Get action and this page Ask, at the same address `#discover`.)* | The sidebar, under Artworks; *Ask about "…"* in the search box and on an empty results page; an empty Artworks, Artists, Queue and Taste | core (flows 1, 2) |
| **To review** | Every Get holding works that found an image and wait for a verdict, newest first, each opening Review — a Get opening its own page, where it is reviewed (2026-10-02); the count is on its link and on Activity's. *(Built 2026-10-02, `build-plan-get-and-ask.md` Chunk 06.)* | The sidebar, under Activity, first | core (flow 3) |
| **Queue** *(new)* | The Gets that have not ended: working, or stored stopped at the approval gate before it was removed (2026-10-07, #290). Beneath them, **Fetching images**: every accepted work still owed its image or its preparation, in the order the acquisition queue will try them, each queued, fetching, failed, given up on or paused, with Retry where it failed; a pause is said above them with its remedy *(the owner's decision on #167, 2026-10-02, `build-plan-after-review.md` Chunk 02)*. Not counted on Activity's link, which is To review's: a fetch needs time, not the curator. | The sidebar, under Activity | core (flow 2) |
| **History** *(new)* | The event log, newest first: Gets started and ended, verdicts, archives, restores, hangs and *Not this one again*, each with how long ago; filtered by kind, or to one wall (`#history?wall=<id>`, from its Walls card). Recorded from 2026-10-07 on *(Chunk 03, ruling 6 of 2026-10-07)*. | The sidebar, under Activity; a wall's *History* on Walls | supporting |
| **Wanted** *(new 2026-10-02)* | Every work the curator wants and holds no acceptable scan of — wanted on a no-scan card, or by turning down the scan on offer — each pictured by the scan its card shows, enlargeable and badged (usually below the floor; words where no scan stands, *added 2026-10-06*, `build-plan-wanted-pictures.md`), saying why it is wanted (scans turned down, found only too small, or none found), with its Wikidata item or none, the Get it came from, *Get again* (its tier, *Free*, beside it) and *Forget*, which waits five seconds with *Undo* as a review verdict does; *Get all again* above. Get again on a work with no item first offers Wikidata's matches to pick from (`build-plan-after-review.md` Chunks 04-05; the owner's ruling on #168). Empty, it names the two controls that put a work here: *Want* on a review card for a work a Get found no scan of, and *Turn it down* on the scan a card offers *(2026-10-07, #292)*. | The sidebar's Wanted section, always (ruling 5 of 2026-10-07); a review card's *Want*; turning down a scan on offer | core (flow 3) |
| **Get** | One Get while it works and after it stops, at `#get/<id>` (`#run/<id>`, its address until 2026-10-07, is an alias): what it proposed, what it found images for, *Approve the list* and *Decline it* only for a Get stored at the approval gate before asking became the approval (2026-10-07, #290), why it stopped (one halted at the cap: the server's "This month's budget is spent…"), and its work table. **A Get of chosen works is reviewed on its own page**: the review cards in place of the work table, and no *Review these works* *(the owner's ruling, 2026-10-02, `build-plan-topics-and-destinations.md` Chunk 07)*. *(Run until 2026-10-07, ruling 4.)* | Queue or History; Ask, as it starts; a Get's *Open the Get*; a Get's row in To review; a *Get these again* on the review grid or Wanted; its own address | core (flow 2) |
| **Review** | Judging one Get's candidates: accept, reject, choose a scan, ask for a better one. One work to a row, the picture left and the facts and verdicts right (one column on a phone), the scan's pixels above the fold, *Scans* opening beneath as a table, one row a scan; clicking a picture enlarges it in place. The same cards are a Get of chosen works' page; `#review/<id>` still answers for one. A card a source does not confirm says *Not confirmed* (with why), and one nobody asked about *Unchecked*; a confirmed one carries no mark. The model's notes show their Markdown as words and links (`http(s)` only), never as brackets or markup. **A verdict waits five seconds with *Undo* and the seconds left before it is sent**, since the server cannot take an acceptance back; a card drawn again while its verdict waits shows the wait, not the verdict again; leaving the page sends it, and a failure then is said at the top of the page left for, naming the act and the work *(2026-10-07, #276; rewording notes into the product's voice waits for paid evals)*. | A finished Get from Ask or Get again, from its own page or To review; the Get's own notification | core (flow 3) |
| **Artists** | The artists the library holds, by surname, as Lidarr's poster index — each a card pictured by their first accepted work, with life dates and how many works of theirs are in circulation — with a View menu to the table, kept in the address (`?view=table`) *(the owner's ruling on #173, 2026-10-02; the surname is the stored family name, else the last word once *the Elder* / *the Younger* / *Jr.* is set aside)*; and at its own address one artist as the hub: who they are, what the library holds of theirs, what Wikidata lists with the held ones marked and the rest tickable to get (*Get N works*), and which collections hold their work. At `#artist/Q…`, an artist Wikidata knows that the library does not hold: the registry half alone, saying nothing of theirs is held; the library's page replaces it, in place, when the library holds them. Below Holdings, *Similar artists*: visual artists sharing a movement, by renown, each with how many of their works have an image, and ● where the library holds them. Under the name, which Wikidata item this is and who set it, with one quiet *Edit* *(the owner's ruling on #174, 2026-10-02)* that reveals the control to change it (looked up and shown before it is stored) and to say there is none (confirmed). An artist with no item, and none said, is offered Wikidata's people of that name, those whose years agree first, each with *This is them*; at `#artist/Q…`, a library artist of the same name with no item is offered *Link them to this item*; and an artist Wikidata lists no works for is offered *Ask for their work*, which fills in Ask and starts nothing *(the owner's Franz Kline and Lucy Bull, 2026-10-06, `build-plan-artist-search-review-fixes.md`)*. *(Built 2026-10-01, ruling 4; the QID form, Similar artists and the control the same day, `build-plan-one-world-search.md`.)* | The sidebar, under Artworks; an artist's name on a work card, a table row or the Work page (either form); the top-bar search's Artists group; its own address | core (S2, S3, S11) |
| **Themes** | The themes there are, as cards — each its name, how many works, up to four of its pictures and the walls it hangs on, a link to its page — with *New theme*; and at its own address one theme: its members in curated order, moved with ↑, ↓, *Move to top* and *Move to bottom*, its name, the act of hanging it, and which theme is the default that accepted works join. The order copy says position decides what the wall shows first only when the theme is not shuffled, else *Shown in shuffled order*, as Walls says. *(Cards since 2026-10-08, `build-plan-lists-settings-and-scale.md` Chunk 03, #284; until then the index expanded every theme with all its acts and its whole membership.)* | The sidebar, under Artworks; a wall's theme control; its own address *(Artworks' theme rail and its per-theme *Open* went on 2026-10-02, #169)* | core (flows 5, 6) |
| **Topics** | The periods, movements, subjects and media the library's works are in, by kind, each kind in columns by name *(the owner's ruling on #175, 2026-10-02: one column on a phone)*, each with how many of them beside its name, each opening its page; and *Find a topic*, which asks Wikidata for any other (`#topics?find=`). *(Built 2026-10-02, `build-plan-topics-and-destinations.md` Chunk 05; topics come from Wikidata, so without `WIKIDATA_USER_AGENT` the page says they need it and offers no search.)* | The sidebar, under Artworks, after Themes | core (S12) |
| **Topic** | One topic, browsed like a genre: its name, kind, Wikidata's description and a link to its item; *In your library*, your works in circulation in it; *Representative works*, the most renowned Wikidata lists, each by § A work's mark (○ reading *No image known*), the unheld tickable to get into a theme named after the topic (*Add to* defaults to it); and *Artists*, those whose works in it are best known first (the sum of those works' sitelinks), each opening their page. A period's works are headed with its years ("Works from 1501–1600"), since they are matched by date alone. *(Built 2026-10-02, `build-plan-topics-and-destinations.md` Chunk 05.)* | Library › Topics; *Find a topic*; the top bar's *Held: topics* and *Not held: topics* groups and the Search results page; its own address | core (S12) |
| **Status** | The three observations the panel states, and the spend record. Each wall's panel names the work its heartbeat says is on it, by title and linked to it; times read as a readable date and how long ago; the raw fields (heartbeat file, the instant, the Player's reported keys, the backup record) sit behind a *Details* disclosure *(2026-10-07, #283)*. *Image sources* is one table, one row per installed source, most preferred first: Source (the museum's name, and for one not working here the reason, which names the setting), State (a word), Offered (distinct images it has offered to a search or as a held work's source), Chosen (works held by an image from it), Only here (of those, works no other source offered an image for), Median long edge (of its offered images whose size is known), Faults since startup and Last fault. Source, State, Offered and Chosen always show; as the width narrows Median long edge goes first, then Last fault, then Only here, then Faults since startup, whose count then moves into State ("Loaded · 2 faults") so a fault is always on screen; on a phone each row is a card *(2026-10-08, #265)*. No geometry panel: it was one television's, and a wall's own returns under Clients in wave 4 *(2026-10-08, #266)*. *(Health until 2026-09-30.)* | The sidebar, under System; the top bar's status indicator; a failure's own link | supporting |
| **Conversation** *(new)* | One intent-forming thread, its samples, and what it committed to. | Ask; the conversation list; an affinity's provenance | core (flow 1) |
| **Settings** *(new 2026-10-08)* | The index of Settings' pages, as Sonarr's and Radarr's v4 /settings: Clients, Sources and Taste, in that order, each a link with one line on what it holds. *(Chunk 04, #286; Settings opened on Taste until then.)* | The sidebar's Settings | supporting |
| **Taste** *(new)* | The affinities the product has accumulated, with their derivation, correctable. Headed *Taste* ("What this product thinks you like" until 2026-10-08), with help naming every control that records a judgment: a conversation sample's *more like this*, *not this* and *tell me more*; an Artist page's *More like this* and *Not this*; this page's own corrections; and an assistant over MCP (`art_taste`). | The sidebar, under Settings, last; the Settings index; Ask's *See what this product thinks you like*; a suggestion's "why am I seeing this?" | supporting |
| **Clients** *(new 2026-10-02)* | The installed Players the server knows (`clients.md`): each client's name, whether it has a token, what it last reported about its outputs and how long ago, and the walls assigned to it on which outputs. Add a client (its token issued with it and shown once, with what to put in the Player's settings), rename, rotate the token, remove, assign a wall to an output, unassign. *(Built 2026-10-02, `build-plan-clients.md` Chunk 02.)* | The sidebar, under Settings, first; the Settings index; a wall's *Assign it in Settings › Clients* on the Walls screen | core (flow 6) |
| **Sources** *(new 2026-10-06)* | Every installed image source plugin, most preferred first (`source-plugins.md`): its museum's name and its plugin id, the package that installed it and that package's version, whether it loaded, declined or failed and why, what it provides, the plugin interface it was written for beside the one Arrt provides, and its place in the order. Read-only. The same reading Status's *Image sources* panel shows, and `art_discovery(action='source_plugins')` answers. *(Built 2026-10-06, `build-plan-met-source.md` Chunk 02.)* | The sidebar, under Settings, after Clients; the Settings index | supporting |

**One row here per screen the client routes.** Two are new and exist only because
conversational intent-forming does (`product-brief.md` flow 1, amended
2026-08-10).

> **Stated as a rule rather than as a count, and the count it replaced was
> wrong.** This line read "Nine screens" while the route table carried ten — Run
> had been routed, built and reachable by URL for chunks, and appeared in none of
> this artifact's three tables (#148). A number here has to be edited by whoever
> adds the tenth screen, which is exactly the person who did not edit this table;
> the rule does not. **`tests/preferences/test_screen_tables.py` is what holds
> it** — it reads `app.js`'s route table and all three tables below, and fails
> when a screen has no row or a row has no screen.

**CHANGE — Themes stops being a top-level screen.** A theme is a *saved selection
over the collection*, not a parallel noun, and the built surface's own routes say
so: every theme operation is membership and order over works. Promoting it to a
peer of the collection is what forces the curator to hold a mapping in their head.
It becomes a rail inside Collection — a filter that is also editable — plus a
**Theme** screen for the one thing that genuinely is its own act: hanging it.

> **RULING 2026-08-17 — Theme is an index *and* an addressable detail (#133).**
> The row above described one theme, and the built screen was a themes index: a
> create form plus a panel per theme, with no address for any of them. Both are
> real, and the honest record is that the screen is both. `#theme` is the index;
> `#theme/<id>` is one theme.
>
> **The rule this settles is § Navigation Structure's** — "every screen and every
> consequential state is addressable" — and one theme is a consequential state.
> It is what a wall's theme control is *about*, what a curator bookmarks while
> deciding an order, and the only thing an agent can be given a link to. The rule
> had no enforcement, so a screen shipped unaddressable and stayed that way until
> it was noticed by eye a chunk later.
>
> **The index survives because creating a theme, and managing the set of them,
> have no other home.** Collection's rail is a *filter over the grid*; making it a
> manager is a redesign of two screens and moves organising away from the works
> being organised, which is what the CHANGE above just decided. So the id is
> optional rather than required — the third mode `core/route.js`'s grammar grew
> for this, and the only route that uses it.
>
> **Two alternatives were put to the owner and declined.** Making Theme
> detail-only matches this table's old wording literally and pays for it with that
> redesign. Deep-linking a panel with `?focus=` satisfies the navigation rule in
> wording only: the address would name the index and a scroll position, not the
> theme.
>
> **Both paths carry every act.** Rename, reorder, hang and delete are the
> theme's own, and a curator must not lose one by having arrived a different way.
> The only difference is what a delete does afterwards — the index repaints from
> the themes that remain, and the addressed view has to leave, because the thing
> it addresses is gone.

## The *arr layout (target, amended 2026-09-30)

This is the layout § Direction now requires, and everything below is built
(`build-plan-arr-navigation.md`).

> **A gap in Activity, recorded 2026-09-30 while building it, closed 2026-10-02.**
> Radarr's Queue also holds what finished but needs the user, such as a manual
> import. Arrt's equivalent is a run that finished with candidates nobody has
> judged. The run listing now counts them (`GET /api/runs` and `art_discovery
> list_runs` carry `awaiting` by run and `awaiting_works` in all, and narrow to
> them with `awaiting`), and they have a page of their own, **To review**, first
> under Activity as `ia-proposal.md` § The map places it, rather than a row in
> Queue (`build-plan-get-and-ask.md` Chunk 06).

The owner chose the name, the home page and the scope on 2026-09-30. The
placement of each page is the builder's reading of Radarr, and each placement is
listed below so it can be disputed.

```
┌──────────────┬──────────────────────────────────────────────┐
│ Arrt     │ [ Search artworks…                        ]  │
├──────────────┼──────────────────────────────────────────────┤
│ ▣ Artworks   │  actions …                View ▾ Sort ▾ Filter ▾
│   Ask        │                                              │
│   Themes     │                                              │
│   Topics     │                                              │
│   Artists    │                                              │
│ ▢ Walls      │                                              │
│ ↻ Activity ③ │                                              │
│   To review ③│                                              │
│   Queue      │                                              │
│   History    │                                              │
│ ◑ Wanted  ⑦  │                                              │
│ ⚙ Settings   │                                              │
│   Clients    │                                              │
│   Sources    │                                              │
│   Taste      │                                              │
│ ♥ System  ②  │                                              │
│   Status     │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

| Sidebar entry | Was | The *arr page it follows |
|---|---|---|
| **Artworks** (home) | Collection, with Work as its detail page | Radarr's Movies index and movie page. Named with the plural noun of the item, as every *arr app names this section |
| Artworks › **Ask** | Discover's intent box and its conversations (Add New until 2026-10-02) | Radarr's Add New's slot: an owner-ruled departure (ruling 3), since acquiring is the *Get* action on any selection and this page asks in words |
| Artworks › **Themes** | Theme, index and one theme | Radarr's Collections: a named grouping of items in the library |
| Artworks › **Topics** | New 2026-10-02 | None: no *arr page is a topic. The nearest idea is a music library's genre (`ia-proposal.md` § Objects), and ruling 9 placed it under the library, after Themes, with no section of its own. Its pages, one topic each (`#topic/<qid>`), are contextual and return to it |
| Artworks › **Artists** | New 2026-10-01 | Lidarr's artist index and artist page, which are that app's library: the artist is the unit, and their page lists what is held and what is missing |
| **Walls** | The Walls | No *arr page. It sits second, in Calendar's slot, because the wave-4 schedule (`re-architecture.md` § The manifest is a schedule) is the nearest *arr idea to "what is showing when" |
| Activity › **To review** | New 2026-10-02 | Radarr's Queue holds what finished but needs the user; here that is a page of its own, the one queue that needs the curator, counted on Activity's link as Sonarr counts its queue. Review opens from here |
| Activity › **Queue** | Discover's run list: runs that have not ended; and, since 2026-10-02, the images being fetched | Radarr's Queue: work in flight, downloads included. A Get and a Work open from here |
| Activity › **History** | The event log (finished runs until 2026-10-07) | Radarr's History |
| **Wanted** | New 2026-10-02 under Activity; a section of its own since 2026-10-05 (the owner's ruling) | Lidarr's Wanted › Missing: what the library wants and does not have. Always shown, counted when something is wanted (ruling 5 of 2026-10-07). Cutoff Unmet (wave 4) and a Watch's Missing (wave 6) become its tabs when they exist |
| **Settings** (its index) | New 2026-10-08 (`build-plan-lists-settings-and-scale.md` Chunk 04); Settings opened on Taste until then | Sonarr's and Radarr's v4 /settings: the section's link opens a list of its pages, each with a line on what it holds, so no page has to be "first" |
| Settings › **Clients** | New 2026-10-02 (`clients.md`) | Radarr's Settings › Download Clients: the server's list of the external programs it works with, which here are the installed Players. Its *Assign a wall* is per client, as a download client carries its own settings there |
| Settings › **Sources** | New 2026-10-06 (`build-plan-met-source.md` Chunk 02) | Radarr's Settings › Indexers: the places the server searches, which here are the installed source plugins. Read-only, because the order is `SOURCE_ORDER` and installing a plugin is an image build |
| Settings › **Taste** | Taste; first under Settings until 2026-10-08, last since | Radarr's Profiles: the preferences that rank what it finds. Last, after what the server works with, because it is what the server has come to believe |
| System › **Status** | Health, with the spend record | Radarr's System › Status, with health checks at the top |

- **Sub-pages show only under the current section**, as in Sonarr and Radarr.
  Other sections show just their names.
- **Under the sections, what is left of this month's budget** (#290, the owner's
  ruling 3 of 2026-10-07), read from `GET /api/budget`: "$12.40 left this month"
  where the key's limit or the configured budget gives a figure, what was spent
  where neither does, *Nothing spends* with no key, *Budget unknown* when the
  provider could not be asked, and the server's note beneath wherever it gives
  one (a configured budget nothing enforces says so). Read again on a
  navigation once a minute old. **Every spending control shows its tier**
  (*Free*, `$`, `$$`, `$$$`, the server's `tier`) beside it before it is
  pressed: Ask's *Get*, a conversation's *Get*, *Approve the list* on a Get
  stored at the gate, and, free by construction, every *Get* of chosen works,
  *Get these again* on a review and Wanted's *Get again* and *Get all again*.
- **Health gets the *arr badge on System, and keeps the status indicator in the
  top bar.** The badge shows the number of problems, as Sonarr's does. A number
  alone breaks `accessibility-spec.md`'s rule of glyph plus word plus colour, which
  says a state indicator with no word is a bug at every viewport. So the badge
  cannot carry the old indicator's contract (always present, never silent). The
  top-bar indicator keeps it, reading "well" or naming what is wrong, and opens
  System › Status. tacularr's top bar carries its status the same way.
  *(Builder's collision ruling, 2026-09-30: the accessibility rule outranks
  familiarity where they meet, because the familiarity norm governs where things
  are and what they are called, not whether a state can be read. The owner can
  overrule it.)*
- **One search box, two scopes, as in Sonarr.** *(2026-10-01: `user-scenarios.md`
  questions this from the scenarios side. A query can mean held, exists,
  seeable or hangable. An unaccented `dali` found no held Dalí until 2026-10-01, when search began ignoring accents.)* Read from Sonarr's source on
  2026-09-30 (`frontend/src/Components/Page/Header/SeriesSearchInput.js` and
  `AddSeries/AddNewSeries/AddNewSeriesSearchResult.js`; Radarr shares the code):
  - The top-bar box searches **the library** as you type. Its dropdown has two
    groups: *Existing Series*, the library's matches, and *Add New Series*, one
    row reading *"Search for {query}"*. Picking a match opens it, and picking the
    second row goes to `/add/new?term={query}`.
  - On Enter, Sonarr opens the first library match, or goes to Add New when
    nothing in the library matches.
  - Add New searches **everywhere** (TVDB). A result already in the library is
    marked *"Already in your library"*, and clicking it opens the library entry
    instead of the add dialog.

  **One world, since 2026-10-01** (ruling 2, `build-plan-one-world-search.md`
  Chunk 03), **in two halves since 2026-10-06** (the owner, `build-plan-search-held-not-held.md`):
  under a *Held* heading, the groups *Held: artists*, *Held: works*, *Held: topics*
  and *Held: themes* (the library's matches, themes by name, and any of
  Wikidata's matches the library holds that those rows do not show); under a
  *Not held* heading, *Not held: artists*, *Not held: works* and *Not held: topics*
  (the rest of Wikidata's); then *Ask*, then *Search*, whose one row, *All results
  for "…"*, opens the Search results page. A listbox cannot nest groups, so each
  group's accessible name carries its half and the two headings are drawn for
  the eye only (`aria-hidden`). A half with nothing in it is one line, not a
  group for each kind it lacks: "Nothing you hold matches.", and, once Wikidata
  has answered, "Wikidata has nothing more." The Not held half is left out below
  Wikidata's three letters, when there is nothing it could say. Wikidata's rows arrive after the library's and never hold them
  back, are asked from the third letter, carry a work's mark of glyph, word and colour
  (§ A work's mark, in its grouped words) and no mark on an artist, since the half
  heading says it (the owner, 2026-10-06), leave out what the library's rows already show, and open the library's
  page for a held match and the page by QID otherwise. Their arrival is announced
  in a polite live region and moves no highlight; a new query starts with none, so
  Enter is never sent to a row the curator did not choose. Wikidata off or down is said
  in a note where its rows would be, in its own class, apart from the library's
  note. Enter with nothing highlighted opens the Search results page (below).
  *(Topics added 2026-10-02, `build-plan-topics-and-destinations.md` Chunk 05:
  *Topics* is the topics your works are in whose names hold the words, after
  works as `ia-proposal.md` § Search orders the objects, each naming its kind;
  *Wikidata: topics* is the periods, movements, subjects and media Wikidata finds
  for them that *Topics* does not already show, each with Wikidata's description,
  which is what tells six *Impressionism*s apart. Both open the Topic page. The
  topic search is asked beside Wikidata's other search and arrives with it, under
  one note when Wikidata cannot be asked. Since 2026-10-06 the two are *Held:
  topics* and *Not held: topics*, and a topic of Wikidata's that your works are
  in is under Held even when its name is not the one the library knows.)*

  Arrt follows that shape. The library's groups are under *Held* (*In your
  library* until 2026-10-06), and the last two are *Ask* (*Add New* until
  2026-10-02) and *Search*, *Ask* named as Sonarr names its second group for the page it
  opens, and the row reads *Ask about "{query}"*. Picking it goes to
  `#discover?term={query}`. A candidate that is already an accepted work is
  marked *Already in your library*, and its first control opens that work.
  **Three departures, each forced by a fact Sonarr does not face:**
  - **Ask fills in the term and does not start the search.** Sonarr's lookup
    is free and instant. Arrt's is a discovery run, which takes minutes and
    spends money, so Ask shows the free estimate beside the filled-in box
    and the curator presses Search. *(Builder's ruling: nothing may spend on a
    keystroke.)*
  - **Enter opens the Search results page for the query, not its first match.**
    A series title usually matches one series, but an artist or a movement
    matches many works, so the first match is an arbitrary one. The page lists
    every match, *Held* then *Not held*, and leads on to Artworks filtered to the
    words through its Held works' *All N in Artworks*. The matches in the
    dropdown are still one arrow key away. *(**Ruled by the owner 2026-10-06**,
    reversing the ruling of 2026-09-30, kept 2026-10-01, that Enter opens
    Artworks filtered to the query: Artworks lists only what is held, so a search
    for a work not held found nothing there and offered no way on. This remains
    a recorded departure from the *arr precedent, for the reason above.)*
  - **A held work keeps a quieter *Accept anyway*.** Sonarr's card for a series
    already in the library offers no add at all, because a TVDB id makes
    "already held" certain. Arrt's is found by title and artist, which two
    different works can share ("Untitled"), so removing Accept would block
    acquiring a painting the library does not hold. Opening the held work is
    the card's first control. *(Builder's ruling, 2026-09-30, recorded as a
    DECISION in `build-plan-arr-navigation.md`. The owner can overrule it.)*
- **The toolbar** on Artworks puts the selection's actions on the left and
  View, Sort and Filter on the right. View offers Posters, Overview and Table
  (Posters was the contact sheet and Overview the catalogue; `?density=` keeps
  its spellings). Sort offers Title, Artist (unattributed last) and Recently
  added, and applies to a theme filtered here as to any filter (a theme's
  curated order is its own page's; #169). **Filter shows and hides the rails rather than replacing
  them with a dropdown**, so the facet counts stay in view while browsing
  (ruled by the owner 2026-09-30, departing from Radarr's Filter menu). Its
  label says what it does, *Hide filters* or *Show filters* (2026-10-08, #288).
  With the rails away, a facet or a theme still narrowing the works says so above
  them and offers the rails back, since the grid would otherwise read as the
  whole collection. An Artist's page, the search results and a Topic's page
  have a toolbar holding *Select* alone (2026-10-08, Chunk 05); other list
  pages have none yet, because they have no actions or views to put in one.
- **Two clean-up facets in the rail** *(2026-10-08,
  `build-plan-lists-settings-and-scale.md` Chunk 06, #288)*: *Size on the
  wall*, the fit bands a card's badge names (Native, Matted small, Below floor,
  and No size known for a work with no master), and *Walls › Not on any wall*,
  the works no wall plays now through the theme or selection hanging on it
  (the owner's ruling: which works a wall has shown is not recorded, so "never
  hung" is not offered). Both are counted by the server like a facet and
  compose with the search, the theme and the facets. Each group is drawn only
  once it can narrow: *Size on the wall* when two bands hold works, *Not on any
  wall* once something hangs.
- **Wanted holds the works the curator wants** *(shown since 2026-10-02, the
  owner's ruling on #168, `build-plan-after-review.md` Chunk 05)*: a work wanted
  on a no-scan review card, or whose scan on offer was turned down, which is one
  state. Its link is always in the sidebar, with its count when something is
  wanted, as in every *arr app (ruling 5 of 2026-10-07, #292). It is also
  where *Cutoff Unmet* (works below the quality profile's cutoff,
  `re-architecture.md` wave 4) and *Missing* (a Watch's unmet wants, wave 6)
  land, as tabs beside today's list. Watches themselves follow Radarr's Lists and
  go under Settings.
- **On phones the sidebar becomes a drawer** behind a menu button, as it does in
  the *arr apps. This replaces the bottom bar in `design-direction.md`'s layout
  table. **The top bar is one row on a phone** — menu, name, search, indicator —
  with the search field taking what the others leave and an indicator naming a
  long trouble showing its start. **Below 40rem Activity's tables (To review,
  Queue, a run's works) are stacked cards**, each value under its heading, and
  where the row opens one page the whole card is that link. No page scrolls
  sideways at 390 px, pinned per route from the route table by
  `arrt/tests/browser/test_keyboard_and_phone.py`. *(2026-10-07, #279.)*

## Navigation Structure

**Primary pattern: the *arr sidebar**, laid out in § The *arr layout above. That
section places each page and says which *arr page it follows; this one holds the
rules that apply to all of them.

- **Persistent:** the sidebar (a drawer behind the menu button below 40rem), the
  search box, and the status indicator, in the top bar on every page.
- **Contextual:** everything that is not a sidebar page. Work, Get, Review,
  Conversation, Topic and Search results are reached *from* a page and return to it. A page showing one
  of its own things — one theme, at `#theme/<id>` — is contextual in the same
  way, and returns to whichever page opened it.
- **Status is a page under System**, with Sonarr's count badge on System. The
  top-bar indicator stays beside the badge and keeps the contract it had when it
  was the only way to reach health: it is always present, and it reads "Well" or
  names what is wrong. § The *arr layout records why the badge could not take
  that contract over.

**Back/escape.** Every contextual screen returns to the page it was opened from,
not to a fixed parent — a Work opened from Review returns to Review, the same Work
opened from Artworks returns to Artworks with scroll position intact. A sidebar
page is named in `?from=` by itself; Review, a screen about one run, is named
with its run (`?from=review/<id>`), and only for the Work it opens, so the hops
between a run and its review record nothing (`core/router.js`, `returnFor`). A
Get's page is its review, so a Work opened from one of its cards returns to it
the same way (`?from=run/<id>`, *← The Get*; 2026-10-02). Browser back
does this natively if each is a real URL, which is the reason they are. A sidebar
page has no back link: the sidebar is its way out.

**URLs.** Every screen and every consequential state (a search query, an active
filter set, a run, a conversation) is addressable, so a curator can bookmark
"unmatted works by Kandinsky" and an agent can link to one. **The fragments kept
their spellings when the labels changed on 2026-09-30** — `#collection` is
Artworks, `#discover` is Ask, `#health` is Status — because an address is
what a bookmark and an agent's link hold, and none of them should break over a
word the curator never sees. Older fragments still resolve through
`FRAGMENT_ALIASES` in `core/route.js`.

> **The home page was the Walls until 2026-09-30,** with a recorded
> counter-argument: most sessions begin with an intention, and opening on
> pictures puts a click in front of each. The owner's *arr ruling settled it
> the other way — every *arr app opens on its library — and the Walls moved to
> second in the sidebar.

## More than one wall

The operator stated on 2026-08-10 that multiple displays are coming soon. Nothing
here builds for them; what this section does is fix the **shape** now, while the
shape is still free to choose, and name what genuinely blocks the extension so it
is found in a plan rather than in a chunk.

**The governing rule: one wall is the degenerate case of many, never a special
case.** The screen is "The Walls" from the outset. With one display it shows one
wall filling the screen and reads exactly as a single-wall home would; with three
it shows three. There is no single-wall layout that a second display replaces —
which is what stops the extension from being a rewrite of the product's home.

Three consequences, all cheap to honour now and expensive to retrofit:

- **Every act that changes a wall names which wall**, in its control and in its
  confirmation, even when there is one and the answer is obvious. "Hang Winter"
  becomes "Hang Winter in the living room". A confirmation that reads correctly
  today only because there is one possible target is a sentence that silently
  becomes wrong.
- **Health is per-device and already nearly is.** The top bar's status
  indicator aggregates — "well", or "the study panel has not reported since 09:14" — so it
  gains a device dimension rather than a new design.
- **A theme is not owned by a wall.** Themes stay collection-scoped; *hanging* is
  the per-wall act. Two walls may hang the same theme, and that must not require
  duplicating it.

> **Direction changed 2026-09-30 — see `re-architecture.md`.** This rule survives
> and gains an owner: a theme is a **playlist**, owned by the Programming role,
> still global, and still hung per wall. What changes is what a playlist *can be*.
> Besides a hand-ordered list, it may be a **smart playlist**: a rule over Library
> facets (`subject: Nativity`) and programming tags (`party`), plus manual
> additions and exclusions. The Theme screen will need to show which members came
> from the rule and which were placed by hand. That is new design owed here, and
> it is not started.

### Two structural blockers, found 2026-08-10 — both ruled on 2026-08-12

Both were in `data-model.md`, both needed a decision before multi-display could be
planned, and both were answered by the operator on 2026-08-12. Recorded here
because an interface designed against them unknowingly is the expensive kind of
wrong — and kept rather than deleted, because the shape of this design was chosen
while they were open.

- **`TvBinding.artwork_id` was `required, unique`** — one row per artwork across
  the whole installation, so two televisions showing the same work was a state the
  model forbade. **Ruled:** our artwork id is the identity and is independent of
  any per-renderer id; `tv_content_id` is a per-set cache key, not an identity, so
  the same work legitimately carries a different one per wall. The key becomes
  (`wall_id`, `artwork_id`).
- **Constraint 1 — the single-wall assumption stated as an invariant.** **Ruled:**
  themes are created globally and assigned per wall. Activation moves off
  `Theme.is_active` onto a new **ThemeAssignment**, whose primary key *is* the wall
  — so "one theme per wall" is a key rather than a claim, and two walls may hang
  the same theme with no duplication. A new **Wall** entity holds the identity and
  the name and nothing device-shaped.

**Neither changed anything in this artifact's layouts**, which is the evidence that
fixing the shape early was worth it. What they changed is underneath: the routes
(`POST /api/themes/{id}/activate` and `GET /api/manifest` become per-wall), the
`Directive` singleton (one row per wall, so a `next` in the living room does not
step the study), and the inter-plane contract (`architecture.md` § One manifest per
wall).

**The data half is built as of 2026-08-12** — walls, assignments, per-wall directives,
the routes and tool actions that name a wall, and an unhang. **The inter-plane half
landed the same day**: one manifest and one heartbeat per wall, and each display
plane serves the one wall its `WALL_ID` names (`architecture.md` § One manifest per
wall). That is what lets the health panel meet this artifact's requirement to name
*which* wall is silent, which one shared heartbeat file could never have done.
**The screens followed, and landed by 2026-08-12**: the Walls screen renders one
section per wall with no single-wall layout underneath it, the Theme screen hangs
on named walls and takes down from them, and Collection, Discover, Work, Review,
Conversation and Taste all ship — with the navigation being the three
destinations the Direction asked for until its 2026-09-30 amendment, rather than a
list of screens.
Every layout described in this artifact is built.

**What is not built is named where it is described, not here.** A blanket "the
screens are not" outlived its truth by a day and was still being read a chunk
later, which is the failure this replacement is shaped to avoid: a claim about
the whole surface goes stale the moment any part of it moves, so the remaining
gaps belong beside the thing that has them. `build-plan-curation-ux.md` is the
record of which chunk delivered what.

## Retrieval: search and facets

The amendment to `nonfunctional-requirements.md` made search mandatory rather than
optional. This section states what it has to do, and one thing it currently
*cannot*.

### A control never offers a dead end

**Facet options are derived from the current result set, carry their counts, and a
zero-count option is disabled.** The first prototype offered Movement and Era as
independent lists, which let a curator select "Colour Field" and "1920s" — a
combination that cannot exist — and get an empty grid with no explanation. A filter
that promises results it cannot produce is worse than no filter: it teaches the
curator that the collection is smaller than it is.

Three rules make that hold:

- **Each facet's counts are computed over the results filtered by every *other*
  facet, never by its own.** Including its own collapses the control to the single
  value already chosen, so the curator cannot change their mind without first
  clearing.
- **A zero option is disabled, not hidden.** Hiding it makes the vocabulary appear
  to shrink, which reads as data loss rather than as an empty intersection.
- **Counts are shown.** "Baroque (51)" is the difference between a filter and a
  guess, and at thousands of works it is how a curator decides where to look.

### The vocabulary has more than one axis

The operator's own list — "baroque, pointilism, street art, architecture,
impressionism" — mixes three kinds of thing, and that is evidence rather than
carelessness:

| Named | Actually |
|---|---|
| Baroque, Impressionism, Street art | **movement** — a school, with a period |
| Pointillism | **technique** — a method, used within a movement |
| Architecture | **subject** — what the work depicts |

A single flat "movement" facet forces all three into one list, where they read as
alternatives to each other and their counts become meaningless. **The facet
vocabulary is therefore typed, and it should be the same typed vocabulary
`Affinity.kind` already uses** — `artist`, `movement`, `era`, `subject`, `medium`,
`palette`. One vocabulary then serves three purposes: what a work *is*, what the
curator *likes*, and what discovery *weights*. Two vocabularies for the same idea
is the drift to avoid.

**A movement also implies its period.** Selecting Baroque should narrow Era to the
17th and 18th centuries automatically, because that is a fact about the world and
not a preference. This falls out of derived facets rather than needing its own
rule — but only if the underlying data actually carries both.

### The fields did not exist, and now have a home

**`Artwork` has no `movement`, no `subject` and no period.** It carries `title`,
`artist_id`, `date_created`, `medium`, `dimensions`, `description`, `rights` and
`status`. The first version of this section was designed against fields the
catalogue does not have — recorded rather than quietly fixed, because it is the
failure this artifact exists to prevent.

**Resolved 2026-08-10: `WorkFacet`** (`data-model.md`), carrying `kind`, `value`
and a required `derivation` of `sourced` or `inferred`. It uses **the same typed
vocabulary as `Affinity.kind`**, which is what lets the collection be filtered and
the curator's taste be matched against it in one set of terms.

Two consequences the interface must show rather than hide:

- **Most facets are `inferred`, and the marking is therefore inverted.**
  `arrt/src/arrt/library/discovery/browse.py` records that for the wired collection
  "style, classification and period were measured missing on ordinary spellings",
  and the recorded field inventory has no style field at all. The operator's
  direction is to lean on model inference rather than accept that coverage — so
  inferred is the *rule*, and **the screen states the default once, as a footnote,
  and marks only the exception — with a tick, not a word.** A first draft badged
  every inferred row, which is the failure mode to avoid: a label on almost
  everything is a label nobody reads, and it buried the rare sourced value that
  actually carries authority.

  **Two corrections followed from the same instinct, and they generalise.** The
  bordered word "sourced" was louder than the value it qualified — an annotation
  must not outrank its subject — so it became a tick, with the word kept for
  assistive technology so neither colour nor shape is the sole carrier. And the
  sentence explaining the default sat *above* the facts, where a rule that holds
  for every work outranked the facts particular to this one; it belongs below them,
  where a museum label puts its qualifications.
- **Era is a derived, lossy reading that sits beside `date_created`, never over
  it.** The free text stays the evidence; the facet is only the index. A work shown
  as "Late 19th c." must still show "1888–89" on its own screen.

### A work's mark

*The owner's ruling on #172, 2026-10-02.* Wherever registry works are listed —
the search typeahead, the Search results page, the Topic page's *Representative
works*, the Artist page's *Their work* and a work's *More by* — each carries its
picture in the image style of its state, then glyph and word:

| State | Picture | Glyph and word |
|---|---|---|
| Held | The library's own thumbnail, in the held style; the mark opens the work | ● *Held* (*Held ×n* for a duplicate) |
| Waiting for review (a run found it and it has no verdict; `in_review`) | None | ◔ *Waiting for review*; the mark opens that review (`#review/<run>`), except inside a search suggestion, and the row has no Get *(2026-10-07, #275)* |
| Wanted (the Wanted section, matched to the item) | Wikidata's picture where it has one, in the wanted style | ◑ *Wanted* |
| Not held, with a picture | Wikidata's picture, in the not-held style | ◐ *Not held · Image found* (*Image found* under a *Not held* heading) |
| Not held, no picture | None | ○ *Not held* (*No image known* on the Topic page and under a *Not held* heading) |

**Under a *Not held* heading the words say only what the heading does not**
(the owner, 2026-10-06: "the 'not held' box on search results doesn't really make
sense when the whole section is 'not held'"): the search typeahead and the Search
results page drop *Not held* from a not-held work's mark, and mark no artist at
all; the Search results page's top result, under no heading, keeps its mark.
*Waiting for review* is the exception for artists: no heading says it, so a
not-held artist a run proposed a work of carries it, in the typeahead and on the
Search results page alike (2026-10-07, #275).

Held wins over waiting for review, which wins over wanted. **The three image styles are one block in `app.css`**,
to be tuned against one another: the owner asked to "css style held, wanted,
not held as image styles and then iterate on what's most clear". Held has a
quiet outline and wanted a dashed accent outline; not held is the picture plain,
marked by its badge, since the owner's ruling on tiles (`ia-proposal.md` §
Rulings 2026-10-07, ruling 7) that a preview of a work not held is a real
picture with a badge, not hatching. Every picture is drawn whole at its own
aspect inside its square, never cropped. Glyph and word carry the state whatever the
picture does, so a picture that fails to load, or none, leaves every state
readable (`accessibility-spec.md`).

**The picture shows at every width** *(the owner's feedback of 2026-10-05: on a
phone the lists showed none, which made choosing what to Get guesswork)*. In the
three lists (*Their work*, *Representative works*, *More by*) it is 5rem, large
enough to judge a work before spending on it (3rem until ruling 7; the Search
results page draws it at 3.5rem and the typeahead at 2rem); on a phone the badge stacks the picture above
glyph and word, and the By and Year columns fold under the title so the row
fits without scrolling sideways.

## User Flows

Each core flow from the Product Brief, traced through screens. A flow that cannot
be traced means the inventory is wrong.

### Flow 1 — Express curatorial intent *(rewritten 2026-08-10)*

`Artworks → Ask → Conversation → [commit] → Conversation (run inline)`

1. Curator opens Ask and types, or picks up an existing thread.
2. Each turn answers from model knowledge and shows a few sample pictures. Reactions
   are captured both in prose and by direct control on each sample — a sample
   carries "more like this" / "not this" / "tell me more", which is what writes an
   `Affinity` with `derivation='stated'` rather than making the model infer one.
   A fourth control, **"go to <artist>'s work"**, is kept visually apart from those
   three because it is a different kind of act: the reactions record taste and stay
   in the thread; this one leaves it, filtering Artworks to that artist.

   > **Where it lands is the interesting part, and it is usually nowhere.** The
   > artists a conversation surfaces are by definition ones the curator could not
   > have named, so the overwhelmingly common outcome is a collection holding
   > nothing by them. Reporting that as "nothing matches these filters" would be
   > true and useless. The artist-filtered empty state therefore says so plainly —
   > *"Nothing by Wassily Kandinsky yet"* — states that this is normal rather than
   > broken, and offers the search. **This is a third empty state for Artworks,
   > not a variant of the other two**, and it is the one the conversation makes
   > common.
3. When a direction firms up, the system offers it as a **commit card** in the
   thread: what would be searched, how many works, what it would cost.

   > **"How many works" is not available before the run, and the built card does
   > not show it.** Recorded 2026-08-12, on building it. The estimate the card is
   > drawn from carries no count, and the runner's own note says the number is
   > only known once phase 1 has settled against a real work list — which is
   > after committing, not before. So the card states what would be searched and
   > what it would cost, and the count arrives on the progress card the commit
   > transforms into.
   >
   > This line asked for a figure the pipeline cannot produce, which is the
   > failure this artifact exists to catch — a design written against fields the
   > system does not have. It is left in place rather than edited away, with the
   > correction beneath it, for the same reason the facet section keeps its own.
4. Committing starts a `DiscoveryRun`. **The curator does not leave the
   conversation.**

> **The seam is the flow's hard requirement, not a polish item.** The commit card
> *becomes* the run's progress card in place, and then becomes "12 works ready to
> review", which opens Review. The transcript stays above it the whole time. A
> commit that navigates away turns the conversation into a wizard wearing a
> costume — the risk `product-brief.md` flow 1 names — and the in-place transform
> is this artifact's answer to it. Anything that breaks the transform breaks the
> flow.

### Flow 2 — Discovery

`Conversation (commit) or Ask (direct intent) → run → Review`

Unchanged from the built behaviour, and deliberately so: two phases, an estimate
against a real work list once phase 1 settles, a trimmable list, then phase 2.
Conversation is one of two ways in; the direct intent box is the other and does not
go away, because a curator who already knows what to ask for should not have to
chat their way to it.

### Flow 3 — Review and accept

`Review (grid of candidates) → Work or the card's own alternates → verdict`

Judging is the product's highest-stakes screen: accepting spends money and
acquires, rejecting suppresses a work from future runs (Q3). Both are consequential
and neither is fully reversible, which drives two rules:

- **No gesture-based judging**, on any viewport. No swipe-to-accept, no
  swipe-to-reject. Verdicts are explicit, labelled controls.
- **The picture is the evidence and gets the space.** Every other element on a
  candidate card yields to it.

### Flow 5 — Organise into themes

`Artworks → Select → add to theme` *(and)* `Library › Themes → Theme → reorder`

**CHANGE — organising happens in the collection, against the works being
organised.** Membership is edited from the grid, in place, with multi-select.
Reordering — which is genuinely about the theme rather than about the works —
happens on the Theme screen.

**Radarr's pattern, the owner's ruling of 2026-10-02 (#169).** The rail's theme
list read as the way to add works to a theme, and the toolbar's theme picker as
a filter; the two were redrawn apart:

- **A theme is one more group in the *Filter* rail**, beside the facets, one
  theme at a time. It composes with the facets and the search on the server
  (`GET /api/works?theme=`), and each theme carries the count it would select
  given every other filter, disabled at zero, as a facet value does
  (§ A control never offers a dead end). A theme filtered here is in the Sort
  menu's order, as any filter is; its curated order is its own page's. The
  rail's separate theme list and its per-theme *Open* are gone: themes are
  reached from Library › Themes.
- **Adding and removing appear only in *Select* mode**, as Radarr's mass editor
  does: a *Select* toggle in the toolbar shows ticks on the
  tiles and an action bar whose buttons say the whole act — "Add 3 works to
  Winter", with a visibly labelled *Theme* picker, and "Remove 3 from Baroque"
  when a theme is in the filter. Outside the mode, nothing on the screen changes
  a theme's members. Leaving it drops the ticks.
- **One selection model on every list** *(2026-10-08,
  `build-plan-lists-settings-and-scale.md` Chunk 05, #285)*: Artworks, an
  Artist's page, the search results and a Topic's page share `core/selecting.js`.
  The toggle's label says the mode — *Select*, then *Stop selecting*. Outside
  the mode a card carries no tick and so no Tab stop. In it, a bar held at the
  foot of the window offers *Select all*, then every act valid for what can be
  ticked there: *Add to theme* with *New theme…* (so S7 runs without leaving
  Artworks) and *Archive* for held works, asking first; *Get* for works not
  held. **Select all means every work the list's filter matches, loaded or
  not**: the acts send the filter and the works unticked since, not the ids on
  screen. Since a selection can always make a theme or archive, *Select* is
  offered on Artworks with no themes at all.

**One theme is the default, and acceptance fills it** *(the owner's ruling 8,
built 2026-10-01)*. A work accepted from any route joins the default theme at the
end of its order, once: taken out by hand, it stays out through a restart and a
restore. A Get may name another theme as its destination: the Get control's *Add to*
select, the API and MCP (`build-plan-topics-and-destinations.md` Chunks 01-02,
2026-10-02). Its accepted works join that theme instead, and none if it was
deleted meanwhile; Queue, the run page and Review say which. The Theme screen marks the default with a star, the word *default* and
the accent colour, offers *Make default* on every other theme, and says so when
no theme is the default. The default cannot be deleted until another theme is
made the default. *(The 2026-08-12 "whether it is the active theme" status this
screen once carried was retired with `is_active`; the hierarchy row now reads
"which walls it hangs on".)*

### Flow 6 — Display and sync

`The Walls → a wall's theme control → activate` *(or)* `Theme → hang this`

Activation is the one act in the product that changes what other people in the
house see. It gets a confirmation that names the consequence in those terms, and
the wall repaints from the published manifest rather than from optimism.

> **Direction changed 2026-09-30 — see `re-architecture.md`.** Unchanged for the
> curator. Underneath, "the published manifest" becomes a per-wall document the
> server serves over HTTP (wave 2) instead of a file in a shared directory, and a
> wall's player pulls it into a local cache. The confirmation's wording still
> names the wall and the consequence.

## Information Hierarchy

The governing rule, inherited from `product-brief.md` § Identity: **the artwork is
the primary content on every screen that shows one, and chrome yields to it.** What
follows applies it per screen.

**One row here per screen in § Screen Inventory, and the agreement is the check.**
Stated as a rule rather than as a count on purpose: a number written here would
have to be edited by whoever adds the tenth screen, which is exactly the person
who did not edit this table.

> **The rule keeps its sentence and has lost its job to a test.** It still says
> what agreement *means*, which is why it is not deleted — without it
> `tests/preferences/test_screen_tables.py` asserts a contract no artifact
> states. What it no longer says is that *reading the two lists against each
> other* is the enforcement, because that has now failed three times in this one
> artifact: Conversation and Taste shipped into § Screen Inventory and this table
> stayed at seven rows for a chunk (#123, closed 2026-08-12); then Run was routed
> and built and appeared in none of the three tables, while § Screen States
> claimed to assess every screen and carried seven of ten (#148).
>
> Three failures of one rule is the rule's measurement, not the readers'. The
> drift is invisible per-chunk — the chunk that adds a screen adds it where the
> work is, and these tables are in another project's directory — which is
> precisely the class of thing a test catches and a careful reading does not.

| Screen | Primary | Secondary | Actions | Status |
|---|---|---|---|---|
| Walls | What each wall's screen is doing, from the server's `display_state` *(2026-10-08, `build-plan-display-state.md` Chunk 04; `current_work_id` alone is no longer read)*: showing art leads with the work, large, under "On the wall now", and a picture the wall did not put there says "A picture {wall} did not put there"; "Somebody is using the screen", "Its screen is off", "No screen", "Not assigned to a screen" or "Not known", each with since when where known; a wall silent past three heartbeats says "Not heard from since {date} ({age})" and leads with the work it last reported, or says what it last reported. "Its screen is off" rather than "The screen is off", because a short string opening "The" reads as a label (§ Labels) | Title, artist, date and medium; what the wall draws from and "until changed"; which wall; which client shows it, on which output ("Shown by Hall Pi on hdmi-a-1"), or "No client shows this wall" with a link to Settings › Clients *(2026-10-02, `build-plan-clients.md` Chunk 02)*; "Shown by" only where the client reports a screen detected on that output, else "Assigned to…" with no screen detected (off or unplugged), or why that is not known *(2026-10-07, #274; `core/outputs.js`)*; a client report older than three heartbeats is not known now, with its age, on Walls and Clients alike *(#295)* | Skip, Not this one again, Change, History, open work *(Skip was "next" until 2026-10-07; the wall token panel, added 2026-09-30, was retired 2026-10-02 with wall tokens; a wall is assigned to a client in Settings › Clients)* | Panel + TV health, quietly |
| Artworks | The grid of images | Counts, active filters | Search; filter by facet, by theme, by size on the wall and by *Not on any wall*, which compose; *Hide filters* / *Show filters*; *Select* mode (`core/selecting.js`, one model on every list), whose bar at the foot of the window offers *Select all* — every work the filter matches, loaded or not — and adds the ticked works to a theme or to a *New theme…*, removes them from the theme being filtered, or archives them; reach every work: the grid loads a page from the server as its end nears, with *Show more* for the keyboard, and Back from a work restores the pages loaded and the scroll *(2026-10-08, Chunk 07, #131)* | Total, how many are on screen so far ("Showing 25 of 2,003."), and what is filtered out |
| Work | The image at full size; for a work not held, the image Wikidata found, else the first picture an image source answers with (2026-10-06) | Artist, facets, mat colour, rendition size; for a work not held, its date, medium, and holder with number, and *What the image sources hold* (2026-10-06): a row per source as a glyph and a word (◌ Asking…, ● N found, ○ Holds none, ○ Holds this work but gives no size for it; not shown, ⊘ Holds a work by this title by another artist; not shown, ▲ Could not be asked; trying again in 10 minutes, — Can't look this work up), then its finds best first, each with its pixels, fit, source and why a Get would keep it, six and then *Show N more*, and one status line saying only what changed | *Hang…* on a wall, *Allow on walls again* when kept off every wall (2026-10-07), theme membership, re-mat, archive (secondary), change the Wikidata item or say there is none, Retry a failed fetch; for a work not held, *Get this work*, its artist, and the rest of their work | The walls and themes it is on, or kept off every wall since when (2026-10-07); fit verdict, image state, and while the acquisition queue owes it one, where it stands there; for a work not held, *Wanted* (◑), *Not held · Image found* (◐) or *Not held* (○) |
| Search results | The artists, works and topics the words find, *Held* then *Not held*, artists first in each | Each artist's years; each work's maker; each topic's kind, and Wikidata's description for its own; how many library works match beyond those listed | Open any result; open the library's matches in Artworks (*All N in Artworks*); in *Select* mode, the one model every list shares, tick works not held (or *Select all*) and get them; *Ask about* when Wikidata has nothing | Each artist's and work's mark; the group each result is in; whether Wikidata answered |
| Ask | The intent box and the conversations | Samples inline | Type, react, commit, *Get* with its tier | A Get's progress, spend |
| To review | The Gets with works waiting for a verdict | What each asked for, its kind, how many works wait, when (a readable date and how long ago) | Review a Get's works | The count, as a word and a number |
| Queue | The Gets in flight, then the images being fetched | What each asked for, its state in words, and when; for a fetch, why it failed and when it tries again | Open a Get; open a work, Retry a failed fetch | Which state each is in; a fetch's as glyph and word (◌ queued, ↻ fetching, ▲ failed, ▲ gave up, ‖ paused; failed and gave up share the glyph for a problem, and the word and the border tell them apart, `core/glyphs.js`) |
| History | What happened, as one sentence per event | When, as a readable date and how long ago | Filter by kind; open the work, theme or Get an event names | Older pages |
| Wanted | The works wanted | Why each is wanted, its Wikidata item, the Get it came from | Get again (picking a Wikidata item first where it has none), Forget (held for Undo), Get all again | No scan found, or *n* scans turned down, in words |
| Get | The Get's own sentence, and its work table; for a Get of chosen works, its review cards in place of the table | The tally behind the sentence, and the gate's price broken down, to the cent | Approve, decline, cancel, open a work, go to the review; for a Get of chosen works, everything Review offers on its cards | Which state the Get is in, and whether the watch is still live |
| Conversation | The thread, newest exchange last | Each turn's suggestions, with their samples | Type, react to a sample, commit a direction, delete the thread | Whether a turn is in flight, and what the exchange cost |
| Settings | Its pages, in order | One line on what each holds | Open a page | — |
| Taste | The judgments, grouped by kind | Sentiment, openness, and how the claim was derived | React, correct, forget, follow a claim back to its turn | Which claims the product inferred rather than was told |
| Clients | Each client by name, with the walls assigned to it and on which outputs | When its token was issued; its last report's outputs (name, kind, whether a screen is detected — "none detected (off or unplugged)", since a set switched off reads as unplugged — and its size; #274) | Add (issuing its token, shown once), rename, rotate the token (asks first), issue a first token, remove (asks first, naming the walls left without a client), assign a wall to an output, unassign | The last report's age in words; no token, no report, an unreadable report and no outputs, each said |
| Sources | Each plugin by name, with the sentence saying what became of it | Its package and version, state, what it provides, the interface it was written for, its place in the order | None: read-only | A declined or failed plugin's reason; an unknown package or interface, each said in words |
| Review | The candidate picture | Title, artist, the scan's pixels (*3,840 × 2,604 px*; inches on a wall dropped 2026-10-02, back with per-wall geometry in wave 4) | Accept, reject, choose scan, ask better, enlarge the picture in place; once accepted or rejected, none of these but enlarging: the card says "Accepted. It is in your library." with *Open it in Artworks*, or "Rejected. It will not be proposed again.", where the controls were, and its scans offer no choice (both verdicts are final; the owner, 2026-10-06) | Verdict, provenance, resolution, fit verdict word |
| Themes | The index: one card per theme. One theme: members in wall order | A card's name, count and first four pictures; a theme's name and count | The index: open a theme, create one. One theme: reorder (↑, ↓, to top, to bottom), rename, hang, make default, delete | Which walls it hangs on; whether it is the default (★ default); whether position decides what the wall shows first |
| Artists | The artist: on the index, every held artist by surname, as posters or a table; on one artist's page, their held works, then what Wikidata lists | Life dates, nationality, Wikidata's description and movements; each listed work's year; the collections holding their work | Open an artist; in *Select* mode, the one model every list shares, tick held works to add to a theme (a *New theme…* included) or archive, and listed works not held to get, or *Select all*; react (*More like this*, *Not this*); open a held work from its *Held* mark, and any listed work from its title; open a similar artist; change the Wikidata item or say there is none; with no item, choose one of Wikidata's people of that name (*This is them*); at `#artist/Q…`, link a library artist of that name (*Link them to this item*); with no works listed, *Ask for their work* | Each listed work marked by § A work's mark; whether Wikidata answered; for an artist not held, that nothing of theirs is held |
| Topics | Your topics by kind, each by name, in columns | How many of your works are in each | Open a topic; find any other topic by name | Whether Wikidata is configured, said when it is not |
| Topic | Your works in it, then the works Wikidata lists for it | Its kind, description and Wikidata item; each listed work's maker and year; each artist's life and how many of their works have an image | Open a held work, a listed work, a maker or an artist; in *Select* mode, the one model every list shares, tick unheld works (or *Select all*) and *Get* them, *Add to* defaulting to a theme named after the topic | Each listed work marked by § A work's mark (○ reading *No image known*); each artist ● where the library holds them; whether Wikidata answered, per section |
| Status | The three observations | Spend history | — | The whole screen is status |

**"Remove" is the wrong word for a *work*, and that control must not use it.**
`Artwork.status` is `accepted` or `archived` and restoration is permitted — **there
is no delete of a work in this product**, and `api-contract.md` § The routes the
interface design requires records why a delete route was not written. A button
labelled *Remove* promises the work is gone; the work is in fact still catalogued,
still restorable, and merely out of circulation. The label is **Archive**, its
undo is **Restore**, and the confirmation says which of the two it is doing. This
matters beyond wording: a curator who believes removal is destructive will
hesitate over an action that is cheap and reversible, and one who discovers the
work is still there will trust the next confirmation less.

> **Scoped to works deliberately, because this product does delete other things.**
> The Theme row above carries a `delete` control and `api-contract.md` designs
> `DELETE /api/themes/{id}`, `DELETE /api/conversations/{id}` and
> `DELETE /api/affinities/{id}`. An unscoped "there is no delete in this product"
> would read as forbidding all four — the over-claiming shape this repo keeps a
> rule about, arrived at while fixing its mirror image.

**Archiving a work that is in the active theme takes a picture off the wall**, and
the confirmation says so.

> **Corrected 2026-08-12, while building it: it takes the picture off the wall at
> the next manifest build, not at the moment of archiving.** Nothing in the archive
> path republishes a manifest — only activation and sync do — so a work archived
> while hanging stays on the television until something rebuilds. The confirmation
> therefore says the room "loses it at the next manifest build", which is the true
> sentence and a longer one.
>
> The alternative was to make archiving republish, and it was rejected on the
> precedent that catalogue-side tidying does not reach across the plane boundary —
> the same reason `clear_wall` does not. **That is a defensible ruling and it
> leaves a real gap**: a curator who archives the picture they are looking at will
> still be looking at it.
>
> **The operator ruled on that gap on 2026-08-12 (Brooks): the picture may stay up,
> on the condition that some path exists to push the update, however clunky.** The
> condition is met, and by a path that is not clunky at all — **re-hanging the same
> theme on the same wall from the Walls screen.** `activate_theme` writes the
> assignment and syncs unconditionally, so hanging what is already hanging
> republishes; the Walls picker lists every theme including the one up, so nothing
> filters the act out. `screens/theme.js` is the one that cannot do it: it offers a
> hang button per wall the theme is *not* on, which is right for its own screen and
> means the republish path lives on Walls alone. A later change that makes the
> Walls picker skip the hanging theme would silently remove the only path this
> ruling rests on.
>
> So the archive path still does not republish, and the plane boundary still holds:
> a catalogue edit does not drive a display, and the curator who wants the wall to
> catch up performs a display act to make it. `architecture.md` records that archiving removes a work
from the manifest and leaves it in the theme, with `archived` the first of the five
exclusion causes — and calls that silence "precisely this product's characteristic
failure". Flow 6 already requires activation to name its consequence in
those terms; archive reaches the same room by a quieter route and inherits the same
rule. `GET /api/manifest?theme_id=` evaluates a theme's exclusions without writing,
so the confirmation can state the consequence rather than predict it.

**A screen states a fact once.** The Work screen carried the movement twice — as an
eyebrow above the title and as a row in the facts list three lines below — which
is not merely redundant: two copies of one fact invite the reader to look for the
difference between them, and one of the two will eventually be the one that goes
stale. Where a fact has a labelled home, that is its only home; the eyebrow slot is
for something the labelled list does not carry, or it is empty.

**An annotation must not outrank its subject.** A qualifier — a provenance mark, a
derivation note, a count — is read *after* the value it qualifies and should be
quieter than it. Where the qualifier applies to every row, it is a footnote under
the block rather than a mark on each row.

**What is recorded and what is shown are different questions**, and the Work screen
answers the second. Two consequences, decided 2026-08-10:

- **The mat shows its colour and nothing else.** `MatColor` keeps the method and
  the date it was derived, and must — that record exists so "the new model picked a
  worse colour" stays answerable and reversible, and because the engine's silent
  fallback to a darkened dominant colour would otherwise be invisible in the data.
  But that is a *diagnostic* question asked rarely, and putting its answer on every
  work's label is putting the audit trail where the label goes. **Nothing here
  reduces what is stored.**
- **Label geometry is not shown, because it is not a property of the work.**
  `data-model.md` already settles this — "panel geometry is in neither store; it is
  configuration both planes read" — and a label is rendered to whatever panel is
  asking, whenever it asks. A per-work label resolution was a fact this artifact
  invented, and it contradicted a recorded decision. Only the artwork rendition,
  which *is* a per-work artefact, remains.

**Density is a control, not a decision, and this is what makes Artworks work at
thousands.** Three views, in the toolbar's View menu:

- **Posters** (was *Contact sheet*) — image only, uniform tiles, metadata on
  hover and on focus. The default above a few hundred works, because per-tile
  chrome that reads as informative at 41 reads as noise at 4,000 and actively
  competes with the art.
- **Overview** (was *Catalogue*) — the built card: image, title, artist, badges.
  The default below that threshold, and always available above it.

**Every library tile shows the work itself at its own aspect** — Artworks at
both densities, the Artist and Topic pages' held works — and never the wall
render, whose mat and bars are the wall's and which appears only on the Work
page, where it is the subject (ruling 7 of 2026-10-07). A tile carries a badge
only where it is news: archived, or a fit other than native. "Native" and the
image's source ("wall render", "master image") say nothing on a tile and are not
drawn there.
- **Table** — one row per work: title, artist, date, medium, status. Never a
  default; for scanning by the words when the pictures are not what you are
  looking for.

The view, the sort and whether the rails are shown are remembered and are part
of the addressable state.

## Screen States

Empty, loading, populated, error — assessed for every screen, because the built
surface has good error handling (`role="alert"`, announced not merely coloured) and
almost no considered empty states.

| Screen | Empty | Loading | Error |
|---|---|---|---|
| Walls | Nothing hanging on a wall: name the reason (no active theme / empty theme / display plane silent) and offer the fix for that reason specifically. No client showing a wall → say so, with the link to Settings › Clients | The frame, then the image | Cannot reach the display plane — say which of the two planes answered. A client listing that does not arrive → each assigned wall says its output and that its client's name could not be read |
| Artworks | **Three different empties.** No works at all → an invitation into Ask. No works *matching the filter* → the filter, and how to clear it. **Filtered to one artist and holding none of them** → say so as a normal state and offer the search (see flow 1). Conflating the first two tells a curator with 3,000 works that they own nothing; conflating the third with the second reports the expected result of following a suggestion as a failed query | Skeleton tiles at the grid's real geometry, so nothing reflows, below the grid while the next page arrives as well | Partial page: show what arrived and say what did not |
| Work | n/a. For a work not held: Wikidata has no such item → "Wikidata has no such work", with the QID | Image placeholder at the work's own aspect ratio | Named per missing part — a work with no rendition is not a failed page. For a work not held, Wikidata not configured or not answering is said in a sentence, and its *More by* section says so on its own. Its *What the image sources hold* panel (2026-10-06) says, in its status line, "No image source holds a picture of this work now." once every source has answered with none ("No image source that answered…" when one could not be asked), that a Get is already asking when one is, that no image source is configured, or that the sources could not be asked just now; the top stays "No free image of this work is known." until a find arrives |
| Search results | No words → a note to type in the search box. A group with nothing in it is one line, with no line for each kind it lacks: Held says "Nothing you hold matches."; Not held, once Wikidata has answered, says "Wikidata has nothing more." when all it found is already under Held, and "Wikidata has nothing for "…"." with *Ask about* (fills in Ask, starts nothing) when it found nothing at all | The Held group first; *Asking Wikidata…* in a live region under *Not held* until both of Wikidata's searches answer, nothing above it waiting | The library's refusal in the page's error banner; Wikidata off or down said in that live region, the Held group left standing |
| To review | Nothing waiting → say so, and say what would appear here | Nothing until the listing arrives | The request's refusal, in the page's error banner |
| Queue | No Get in flight → say so, say what would appear here, and offer Ask. Over a truncated listing it says what it checked, since an older Get may still be at the gate. No image owed → "Every accepted work holds its image" | Nothing until both listings arrive, then the headings and the tables together | The request's refusal, in the page's error banner; a paused acquisition queue is not an error, and is said above its works with its remedy |
| History | Nothing recorded → say what it records and that nothing before it began is; nothing of a kind → say so | Nothing until the listing arrives, then the heading and the list together | The request's refusal, in the page's error banner |
| Wanted | Nothing wanted → say so, and name the controls that put a work here (*Want* on a review card, *Turn it down* on a card's scan), with a way to To review | Nothing until the listing arrives, then the heading and the table together | The request's refusal, in the page's error banner; Wikidata off or not answering is said in the picker, with *Get without an item* still offered |
| Ask | No conversations → the intent box, prominent, with two or three worked examples | Per-turn, in the thread | A failed turn stays in the thread and is retryable; it never silently vanishes |
| Get | n/a — a Get always has a status, and "no works yet" is a populated Get in `resolving_works` | The sentence first, then the work table filling in beneath it without moving it | **The watch says whether it is still watching.** A blip is reported and retried; after five consecutive failures it says it has given up and to reload, because a page that stopped polling silently is indistinguishable from a live one |
| Conversation | A thread with no turns → the intent box, with the same worked examples Ask offers | Per-turn, in the thread, with the turn in flight named as such | A failed turn stays in the thread and is retryable; it never silently vanishes |
| Review | No candidates: which of the four kinds of nothing (Q12) | Per-card | Per-card, so one bad candidate does not blank the grid |
| Themes | No themes → say so, and that works are added from Artworks or a theme's page, under *New theme*. A card for a theme with works and no picture yet says so, beside its count. A theme with no members → how to add from Artworks | Skeleton rows | Inline |
| Artists | No artists → say that accepted works bring them, and offer Ask. On one artist's page: no work in circulation → say so; **Wikidata's half has four states** (answered; the artist is not matched; no registry configured; Wikidata could not be asked), each said in a sentence in that section; not matched lists Wikidata's people of that name to choose from, unless the curator said there is none (said so instead) or Wikidata could not be asked who they might be (said so); answered with no works listed offers *Ask for their work* | The library half first; the registry section says *Asking Wikidata…* until it answers, and nothing above it waits | The library half's refusal in the page's error banner; the registry's failure only in its own section, the library half left working. An address naming no artist → "That artist is not here", and a way to all artists. At `#artist/Q…` the registry half is the page, with the same states in its own section under the header |
| Topics | No work in a topic yet → say that a work's topics are read from Wikidata once it or its artist is matched; a kind with none → say so under its heading. No `WIKIDATA_USER_AGENT` → say topics need it, list what an earlier configuration recorded, and offer no search. A search finding nothing → say Wikidata has no topic by that name | Nothing until the listing arrives; a search's section, above the listing, says *Asking Wikidata…* until it answers | The listing's refusal in the page's error banner; the search's failure in its own section |
| Topic | None of your works in it → say so in *In your library*; Wikidata lists no works or no artists → said in that section | The head and *In your library* first; *Representative works* and *Artists* each say *Asking Wikidata…* until they answer, nothing above them waiting | An address that is not a QID → "That is not a topic's address", and a way to all topics; Wikidata not configured, without the item, or not answering → a sentence in the head and in each registry section, the library half left standing |
| Settings | n/a — its pages are fixed | Painted at once; it reads nothing | — |
| Taste | No affinities yet → what would create some, under the help that names every way one is recorded | — | Inline |
| Clients | No client → say so, under the add. Per client, each its own sentence: no token yet (admitted nowhere), outputs never reported, a report that cannot be read, no outputs reported, no wall shown. An output with no report is typed (placeholder `hdmi-a-1`) with a sentence saying why | Nothing until the listing arrives | The request's refusal in the page's error banner — an output already showing a wall among them — with the page left as it was. An assignment's server notice (output not reported) is said beside the result, not as an error |
| Sources | No plugin installed → say so, and that a package installed without its entry points is the likely cause | Nothing until the listing arrives | The request's failure in the page's error banner |
| Status | n/a — every observation has a value, and "never reported" is one of them | Per observation, so a slow plane does not hold the other two | **A plane that cannot be reached is an observation, not a failed page.** This screen's subject is failure, so rendering an error over it would hide the thing it was opened to show |

**The loading state's job is to not move.** Skeletons occupy the final geometry.
The built client has already been bitten by layout that reflows as images arrive
(`project-preferences.md`, the browser-suite row — every image tile taking the
shape of its own picture), and a grid
of art that jumps while it loads is the opposite of the identity.

**One state rule that is not in the table:** a poll must never move focus. This is
a recorded defect from the built surface (`project-preferences.md`, the
browser-suite row; also in `change-log.md`) — a two-second poll stole focus on the one
screen with a decision on it — and it binds every live region here, of which this
design adds several.

## Boundaries

What this interface does **not** include, stated so the absences read as decisions:

- **No accounts, login, roles, or sharing.** One operator (`data-model.md`).
- **No editing of artwork metadata.** Titles, artists and dates come from the
  source and are the label's evidence; a free-text override would make the physical
  label unfalsifiable against the collection it cites.
- **No in-browser image editing** — no crop, no colour adjustment, nothing that
  paints on the picture. The mat engine is the product's hardest-won logic and the
  interface does not reimplement it. **What a mat may never be is unrecorded**:
  every mat the catalogue holds says how it was arrived at.

  > **Amended 2026-08-18, ruled by the operator, on #91.** The clause used to read
  > "no manual mat override beyond re-deriving it… a hand-placed mat would have no
  > recorded basis". That reason was false when it was written and had been since
  > before the artifact existed: `MatMethod.MANUAL` is in `records.py`'s enum and
  > `art_catalogue(action='set_mat_color')` already writes it, so a hand-picked mat
  > has always carried a recorded basis. The boundary now names the property it was
  > reaching for — a recorded method — instead of the actor. Its only actual effect
  > was to forbid the curator what an agent could already do, which is the defect
  > #91 was filed about; the presets it blocked were settled with the operator on
  > 2026-08-05 and refined on 2026-08-10 against measured evidence.
- **No mobile-native app.** Responsive web only.
- **No TV-facing or panel-facing screen here.** Those surfaces have no interface by
  requirement — they are the artwork and the label.
- **No onboarding flow.** A single expert operator who built the thing; a first-run
  wizard would be the condescension `product-brief.md` warns against. The empty
  states carry the work an onboarding flow would otherwise do.
- **No offline mode.** The curation plane is a loopback service on the same Pi.

> **Direction changed 2026-09-30 — see `re-architecture.md`.** Two items above
> move, and neither is decided here.
> - **Offline mode.** The server moves off the Pi to the household NAS (wave 3),
>   so the curation surface stops being loopback on the wall's own machine. It
>   stays a LAN service with no offline mode.
> - **Metadata editing.** The re-architecture sends factual corrections ("that's
>   an eel, not a snake") to the Library through this UI. That is a **facet**
>   edit, not the title, artist or date edit the metadata item forbids, and the
>   facet's `derivation` is what keeps it honest. Whether the item above should
>   say so explicitly is open for the operator. Until then, facet editing is not
>   designed.

## Status — what this artifact is waiting on

Recorded here rather than only in a session handoff file, because a handoff file is
session-scoped and these obligations are not.

**The plan exists: `build-plan-curation-ux.md`, written 2026-08-12.** This row
used to say no build plan referenced this artifact, and that the work waited on
Chunk 13A resolving. **The operator lifted that gate on 2026-08-12** and directed
that the plan be independent of the display-plane chunks. It is: 13A and 13B are
blocked on a television and a panel, this work is blocked on neither, and queuing
it behind hardware bought nothing but delay. `build-plan.md` stayed the
`active_build_plan` pointer until 2026-09-30, when it was archived as superseded
by `re-architecture.md` (`archive/build-plan.md`).

| What | Owed to | State |
|---|---|---|
| The routes this design needs: text search and facet counts, theme rename and delete, work **archive** (not delete), the conversation surface, the taste surface | `api-contract.md` | **Amended 2026-08-11** — § The routes the interface design requires. The set and the rules are fixed; field-level shapes belong to the chunk that builds each. The two decisions that section held open for the operator were both taken the same day: deleting an active theme **refuses**, and taste **does** earn an MCP tool — `art_taste`, designed in that artifact's § `art_taste`. Nothing on this row is open |
| `accessibility-spec.md` | the human-interface artifact set | **Written 2026-08-11.** It is *not* the browser-only codification this row used to describe — `design_decisions.accessibility_approach` records two surfaces with different profiles and says the important one is the physical label, so a spec scoped to this artifact's screens would have covered the lesser half |
| The revised palettes | `app.css` and `test_design_tokens.py` | **Landed 2026-08-12.** In the stylesheet, read by the test, governed. The status tokens and the scrim are the exception until a rule consumes them — see the token row in `project-preferences.md` |
| Conversation deletion's effect on derived affinities | `security-model.md` | **Closed 2026-08-12** (issue #118). Ruled: deletion does not flow to what was derived — the turns go, the affinities and the spend rows keep their judgment and lose their citation. Written in `security-model.md` § Deleting a conversation, which is the authority; two derived consequences landed in `data-model.md` and `api-contract.md` |
| Multi-display: `TvBinding.artwork_id` uniqueness, and one-active-theme-per-wall | `data-model.md` | **Closed 2026-08-12.** Both ruled — see § More than one wall for the answers and what they changed underneath. New **Wall** and **ThemeAssignment** entities; `Directive` stops being a singleton |

## Open questions

- ~~**Deleting a conversation must have a stated effect on the affinities derived
  from it.**~~ **Closed 2026-08-12 — the first of the three candidates.** The
  affinities are orphaned: they keep the judgment and lose the provenance. The rule
  is in `security-model.md` § Deleting a conversation. Kept rather than deleted
  because the *second* sharp half was found while answering the first and is not
  obvious from the outcome: `SpendRecord.conversation_turn_id` is the same
  question asked about money, where the reason to orphan is not "the judgment is
  worth keeping" but "a ledger must not change retroactively".
- **The threshold at which Artworks defaults to contact sheet** is written above
  as "a few hundred" and is a guess. It should be set from the first real
  thousands-scale corpus, not now.
- **Whether Review needs its own density control.** Judging wants maximum picture;
  a run of 40 wants an overview. Deferred until a run is large enough to hurt.

- **Where the re-architecture's new objects live on the surface** *(added
  2026-09-30; see `re-architecture.md`)*. Each needs a home that satisfies the
  navigation norm: where its *arr precedent puts it, as a page inside an
  existing section rather than a section of its own:
  - **Watches** follow Radarr's Lists under Settings, and what they still want
    appears under Wanted › Missing. *(Changed 2026-09-30 with the *arr
    amendment. The earlier answer was under Discover, as the standing form of a
    run.)*
  - **Programming tags** belong on Artworks and Work, beside the facets they
    are deliberately distinct from.
  - **Smart-playlist rules** belong on the Theme screen.
  - **Watch spend** belongs on the status indicator.

  None is designed. The screen tables above will need rows only if one of them
  turns out to be a screen rather than a panel on an existing one, and
  `tests/preferences/test_screen_tables.py` will hold that to `app.js`.
