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

## Direction

<!-- Ratified by the owner 2026-08-11. Amended by the owner 2026-09-30. Enforcement row in project-preferences.md. -->

**The curation surface is laid out like the *arr apps.** It has a sidebar of
sections, each with its pages listed beneath it, a top bar that carries search,
a toolbar on list pages, and the library as the home page. If Curatarr has a
page that an *arr app also has, it goes where the *arr app puts it and uses the
*arr app's name. If Curatarr has a page no *arr app has, it goes in the section
whose *arr meaning is closest. A new top-level section needs an *arr precedent
(Wanted, Calendar) or an owner ruling. A subsystem that gains a UI gets a page
inside an existing section, not a section of its own.

> **Why:** the owner ruled on 2026-09-30: *"More important to be familiar than to
> have our own thing."* Curatarr runs on the NAS beside Sonarr, Radarr and
> tacularr (`re-architecture.md` § Deployment target), and its operator moves
> between them. A page placed where every sibling app places it takes no effort to
> find. A page placed where only Curatarr would place it has to be learned, and
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

**A working prototype of everything below is committed beside this file:**
`prototypes/curation-ia-prototype.html` — one self-contained page, no build step,
opened directly in a browser. It carries a synthetic 2,000-work corpus because
every scale claim here is unfalsifiable against the real 41. It is a **design
deliverable, not a component**: it shares the product's tokens deliberately, but
nothing in `curatarr/` imports from it and it ships to no one.

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

## Screen Inventory

Priority is **core** (on a stated core flow) or **supporting**.

| Screen | Purpose | Entry points | Priority |
|---|---|---|---|
| **Walls** | What is hanging right now on each display, the theme it is drawn from, and what is next. | The sidebar; after activating a theme | core (flow 6) |
| **Artworks** | Everything acquired. Find, sort, filter, group, organise into themes, archive. The product's home. *(Collection until 2026-09-30.)* | Launch; the sidebar; search from anywhere; from a theme; after a run's accepted works land | core (flows 3, 5) |
| **Work** | One work at full size, with its sources, renditions, mat history and theme membership. | A tile in Collection; a tile on a Wall; a row in Review | core (flows 4, 5) |
| **Add New** | Asking for something new: the direct intent box and the conversations, with a run's progress shown in the thread that started it. *(Discover until 2026-09-30, when it also listed every run.)* | The sidebar, under Artworks; "find something new" on the Walls and on an empty Artworks | core (flows 1, 2) |
| **Queue** *(new)* | The searches that have not ended: working, or stopped at the approval gate. | The sidebar, under Activity | core (flow 2) |
| **History** *(new)* | The searches that have ended, with how each ended. | The sidebar, under Activity | supporting |
| **Run** | One discovery run while it works and after it stops: what it proposed, what it found images for, the gate where phase 2 is approved, and its work table. | Queue or History; Add New, as it starts; a re-search started on the review grid; its own address | core (flow 2) |
| **Review** | Judging one run's candidates: accept, reject, choose a scan, ask for a better one. | A finished run, from History or its own page; the run's own notification | core (flow 3) |
| **Themes** | The themes there are, and — at its own address — one of them: its members in curated order, its name, and the act of hanging it. | The sidebar, under Artworks; Artworks' theme rail; a wall's theme control; its own address | core (flows 5, 6) |
| **Status** | The three observations the panel states, and the spend record. *(Health until 2026-09-30.)* | The sidebar, under System; the top bar's status indicator; a failure's own link | supporting |
| **Conversation** *(new)* | One intent-forming thread, its samples, and what it committed to. | Add New; the conversation list; an affinity's provenance | core (flow 1) |
| **Taste** *(new)* | The affinities the product has accumulated, with their derivation, correctable. | The sidebar, under Settings; a suggestion's "why am I seeing this?" | supporting |

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

> **A gap in Activity, recorded 2026-09-30 while building it.** Radarr's Queue
> also holds what finished but needs the user, such as a manual import. Curatarr's
> equivalent is a run that finished with candidates nobody has judged, and it
> belongs in Queue. The run listing carries no signal for it, so today it sits in
> History with its state. Adding one is an API change: a count of unjudged
> candidates per run, on `GET /api/runs` and its MCP twin. It is owed, and not
> part of this plan.

The owner chose the name, the home page and the scope on 2026-09-30. The
placement of each page is the builder's reading of Radarr, and each placement is
listed below so it can be disputed.

```
┌──────────────┬──────────────────────────────────────────────┐
│ Curatarr     │ [ Search artworks…                        ]  │
├──────────────┼──────────────────────────────────────────────┤
│ ▣ Artworks   │  actions …                View ▾ Sort ▾ Filter ▾
│   Add New    │                                              │
│   Themes     │                                              │
│ ▢ Walls      │                                              │
│ ↻ Activity   │                                              │
│   Queue      │                                              │
│   History    │                                              │
│ ⚙ Settings   │                                              │
│   Taste      │                                              │
│ ♥ System  ②  │                                              │
│   Status     │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

| Sidebar entry | Was | The *arr page it follows |
|---|---|---|
| **Artworks** (home) | Collection, with Work as its detail page | Radarr's Movies index and movie page. Named with the plural noun of the item, as every *arr app names this section |
| Artworks › **Add New** | Discover's intent box and its conversations | Radarr's Add New: search a source for something to add |
| Artworks › **Themes** | Theme, index and one theme | Radarr's Collections: a named grouping of items in the library |
| **Walls** | The Walls | No *arr page. It sits second, in Calendar's slot, because the wave-4 schedule (`re-architecture.md` § The manifest is a schedule) is the nearest *arr idea to "what is showing when" |
| Activity › **Queue** | Discover's run list: runs that have not ended | Radarr's Queue: work in flight. Run opens from here |
| Activity › **History** | Discover's run list: finished runs | Radarr's History |
| Settings › **Taste** | Taste | Radarr's Profiles: the preferences that rank what it finds |
| System › **Status** | Health, with the spend record | Radarr's System › Status, with health checks at the top |

- **Sub-pages show only under the current section**, as in Sonarr and Radarr.
  Other sections show just their names.
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
- **One search box, two scopes, as in Sonarr.** Read from Sonarr's source on
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

  Curatarr follows that shape. The groups are *In your library* and *Add New*,
  named as Sonarr names its second group for the page it opens, and the Add
  New row reads *Search museums for "{query}"*. Picking it goes to
  `#discover?term={query}`. A candidate that is already an accepted work is
  marked *Already in your library*, and its first control opens that work.
  **Three departures, each forced by a fact Sonarr does not face:**
  - **Add New fills in the term and does not start the search.** Sonarr's lookup
    is free and instant. Curatarr's is a discovery run, which takes minutes and
    spends money, so Add New shows the free estimate beside the filled-in box
    and the curator presses Search. *(Builder's ruling: nothing may spend on a
    keystroke.)*
  - **Enter opens Artworks filtered to the query, not its first match.** A series
    title usually matches one series, but an artist or a movement matches many
    works, so the first match is an arbitrary one. Opening the filtered library
    keeps today's behaviour, where search is the main way to find things at
    thousands of works. The matches in the dropdown are still one arrow key
    away. *(Ruled by the owner 2026-09-30: "yes to filtered to the query". This is
    a recorded departure from the *arr precedent, for the reason above.)*
  - **A held work keeps a quieter *Accept anyway*.** Sonarr's card for a series
    already in the library offers no add at all, because a TVDB id makes
    "already held" certain. Curatarr's is found by title and artist, which two
    different works can share ("Untitled"), so removing Accept would block
    acquiring a painting the library does not hold. Opening the held work is
    the card's first control. *(Builder's ruling, 2026-09-30, recorded as a
    DECISION in `build-plan-arr-navigation.md`. The owner can overrule it.)*
- **The toolbar** on Artworks puts the selection's actions on the left and
  View, Sort and Filter on the right. View offers Posters, Overview and Table
  (Posters was the contact sheet and Overview the catalogue; `?density=` keeps
  its spellings). Sort offers Title, Artist (unattributed last) and Recently
  added, and is not offered while a theme is showing, since a theme comes in
  its curated order. **Filter shows and hides the rails rather than replacing
  them with a dropdown**, so the facet counts stay in view while browsing
  (ruled by the owner 2026-09-30, departing from Radarr's Filter menu). With
  the rails away, a facet or a theme still narrowing the works says so above
  them and offers the rails back, since the grid would otherwise read as the
  whole collection. Other list pages have no toolbar yet, because they have no
  actions or views to put in one.
- **Wanted is not shown yet.** It is where *Cutoff Unmet* (works below the
  quality profile's cutoff, `re-architecture.md` wave 4) and *Missing* (a Watch's
  unmet wants, wave 6) land, and it appears when the first of those exists.
  Watches themselves follow Radarr's Lists and go under Settings.
- **On phones the sidebar becomes a drawer** behind a menu button, as it does in
  the *arr apps. This replaces the bottom bar in `design-direction.md`'s layout
  table.

## Navigation Structure

**Primary pattern: the *arr sidebar**, laid out in § The *arr layout above. That
section places each page and says which *arr page it follows; this one holds the
rules that apply to all of them.

- **Persistent:** the sidebar (a drawer behind the menu button below 40rem), the
  search box, and the status indicator, in the top bar on every page.
- **Contextual:** everything that is not a sidebar page. Work, Run, Review and
  Conversation are reached *from* a page and return to it. A page showing one
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
between a run and its review record nothing (`core/router.js`, `returnFor`). Browser back
does this natively if each is a real URL, which is the reason they are. A sidebar
page has no back link: the sidebar is its way out.

**URLs.** Every screen and every consequential state (a search query, an active
filter set, a run, a conversation) is addressable, so a curator can bookmark
"unmatted works by Kandinsky" and an agent can link to one. **The fragments kept
their spellings when the labels changed on 2026-09-30** — `#collection` is
Artworks, `#discover` is Add New, `#health` is Status — because an address is
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
- **Health is per-device and already nearly is.** The masthead indicator
  aggregates — "well", or "the study panel has not reported since 09:14" — so it
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
  `curatarr/src/curatarr/library/discovery/browse.py` records that for the wired collection
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

## User Flows

Each core flow from the Product Brief, traced through screens. A flow that cannot
be traced means the inventory is wrong.

### Flow 1 — Express curatorial intent *(rewritten 2026-08-10)*

`Artworks → Add New → Conversation → [commit] → Conversation (run inline)`

1. Curator opens Add New and types, or picks up an existing thread.
2. Each turn answers from model knowledge and shows a few sample pictures. Reactions
   are captured both in prose and by direct control on each sample — a sample
   carries "more like this" / "not this" / "tell me more", which is what writes an
   `Affinity` with `derivation='stated'` rather than making the model infer one.
   A fourth control, **"go to <artist>'s work"**, is kept visually apart from those
   three because it is a different kind of act: the reactions record taste and stay
   in the thread; this one leaves it, filtering Collection to that artist.

   > **Where it lands is the interesting part, and it is usually nowhere.** The
   > artists a conversation surfaces are by definition ones the curator could not
   > have named, so the overwhelmingly common outcome is a collection holding
   > nothing by them. Reporting that as "nothing matches these filters" would be
   > true and useless. The artist-filtered empty state therefore says so plainly —
   > *"Nothing by Wassily Kandinsky yet"* — states that this is normal rather than
   > broken, and offers the search. **This is a third empty state for Collection,
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

`Conversation (commit) or Add New (direct intent) → run → Review`

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

`Collection → select → add to theme` *(and)* `Collection → theme rail → Theme → reorder`

**CHANGE — organising happens in the collection, against the works being
organised.** The theme rail filters the grid to a theme's members; membership is
edited from the grid, in place, with multi-select. Reordering — which is genuinely
about the theme rather than about the works — happens on the Theme screen.

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
| Walls | Each wall's hanging work, large | Title, artist, theme, which wall | Change theme, next, open work, issue or rotate the wall's Player token *(added 2026-09-30: the token is shown once, in place, and rotating asks first)* | Panel + TV health, quietly |
| Artworks | The grid of images | Counts, active filters | Search, filter, select, add to theme, archive | Total, and what is filtered out |
| Work | The image at full size | Artist, facets, mat colour, rendition size | Theme membership, re-mat, archive | Fit verdict, image state |
| Add New | The intent box and the conversations | Samples inline | Type, react, commit, start direct | Run progress, spend |
| Queue | The searches in flight | What each asked for, and when | Open a search | Which state each is in |
| History | The searches that ended | What each asked for, and when | Open a search | How each ended |
| Run | The run's own sentence, and its work table | The tally behind the sentence, and the gate's price broken down | Approve, decline, cancel, open a work, go to the review | Which state the run is in, and whether the watch is still live |
| Conversation | The thread, newest exchange last | Each turn's suggestions, with their samples | Type, react to a sample, commit a direction, delete the thread | Whether a turn is in flight, and what the exchange cost |
| Taste | The judgments, grouped by kind | Sentiment, openness, and how the claim was derived | React, correct, forget, follow a claim back to its turn | Which claims the product inferred rather than was told |
| Review | The candidate picture | Title, artist, size on this wall | Accept, reject, choose scan, ask better | Verdict, provenance, resolution |
| Themes | Members in wall order | Name, count | Reorder, rename, hang, delete | Whether it is the active theme |
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
| Walls | Nothing hanging on a wall: name the reason (no active theme / empty theme / display plane silent) and offer the fix for that reason specifically | The frame, then the image | Cannot reach the display plane — say which of the two planes answered |
| Artworks | **Three different empties.** No works at all → an invitation into Add New. No works *matching the filter* → the filter, and how to clear it. **Filtered to one artist and holding none of them** → say so as a normal state and offer the search (see flow 1). Conflating the first two tells a curator with 3,000 works that they own nothing; conflating the third with the second reports the expected result of following a suggestion as a failed query | Skeleton tiles at the grid's real geometry, so nothing reflows | Partial page: show what arrived and say what did not |
| Work | n/a | Image placeholder at the work's own aspect ratio | Named per missing part — a work with no rendition is not a failed page |
| Queue | Nothing in flight → say so, say what would appear here, and offer Add New. Over a truncated listing it says what it checked, since an older search may still be at the gate | Nothing until the listing arrives, then the heading and the table together | The request's refusal, in the page's error banner |
| History | No search has finished → say so | Nothing until the listing arrives, then the heading and the table together | The request's refusal, in the page's error banner |
| Add New | No conversations and no runs → the intent box, prominent, with two or three worked examples | Per-turn, in the thread | A failed turn stays in the thread and is retryable; it never silently vanishes |
| Run | n/a — a run always has a status, and "no works yet" is a populated run in `resolving_works` | The sentence first, then the work table filling in beneath it without moving it | **The watch says whether it is still watching.** A blip is reported and retried; after five consecutive failures it says it has given up and to reload, because a page that stopped polling silently is indistinguishable from a live one |
| Conversation | A thread with no turns → the intent box, with the same worked examples Add New offers | Per-turn, in the thread, with the turn in flight named as such | A failed turn stays in the thread and is retryable; it never silently vanishes |
| Review | No candidates: which of the four kinds of nothing (Q12) | Per-card | Per-card, so one bad candidate does not blank the grid |
| Themes | A theme with no members → how to add from Artworks | Skeleton rows | Inline |
| Taste | No affinities yet → what would create some | — | Inline |
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
- **No in-browser image editing** — no crop, no colour adjustment, no manual mat
  override beyond re-deriving it. The mat engine is the product's hardest-won logic
  and a hand-placed mat would have no recorded basis.
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
- **The threshold at which Collection defaults to contact sheet** is written above
  as "a few hundred" and is a guess. It should be set from the first real
  thousands-scale corpus, not now.
- **Whether Review needs its own density control.** Judging wants maximum picture;
  a run of 40 wants an overview. Deferred until a run is large enough to hurt.

- **Where the re-architecture's new objects live on the surface** *(added
  2026-09-30; see `re-architecture.md`)*. Each needs a home that satisfies the
  navigation norm, meaning a thing a curator sets out to do rather than a
  subsystem that acquired a tab:
  - **Watches** follow Radarr's Lists under Settings, and what they still want
    appears under Wanted › Missing. *(Changed 2026-09-30 with the *arr
    amendment. The earlier answer was under Discover, as the standing form of a
    run.)*
  - **Programming tags** belong on Collection and Work, beside the facets they
    are deliberately distinct from.
  - **Smart-playlist rules** belong on the Theme screen.
  - **Watch spend** belongs on the health indicator.

  None is designed. The screen tables above will need rows only if one of them
  turns out to be a screen rather than a panel on an existing one, and
  `tests/preferences/test_screen_tables.py` will hold that to `app.js`.
