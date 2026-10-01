# Information Architecture — a proposal from the scenarios

**Written 2026-10-01, at the owner's request: "Without preconceptions from what
we've already built, build a strong IA story for the app."** It is derived from
`user-scenarios.md` and from measurements, and it looks at the built screens only
in § Against what is built. **The owner ruled on all of its decisions on
2026-10-01** (§ Rulings), and the body below is revised to match.
`information-architecture.md` is not yet amended; that is the next step.

## The story

**Arrt is a record collection for paintings, with the walls as its rooms.**

- **The artist is the centre**, as in a music library. Of the six scenarios about
  finding something (S1–S5, S11), four are phrased by artist: S1's "the Dalí", S3,
  S5 and S11.
- **Everything that exists can be browsed for free.** Owning is a state a work is
  in, not a different part of the app.
- **There is one door that costs money: *Get*.** It is always explicit and always
  priced before you press it.
- **Walls are rooms you hang to**, the way a music app plays to a room. Hanging
  for a duration, after which each wall goes back to what it showed before, waits
  for wave 4's schedule (ruling 6).

The *arr precedent is **Lidarr, not Radarr**. A film has no creator page that
organises a body of work, so Radarr is built around single items. Lidarr's
artist page lists every album the artist made, each marked complete, missing or
unmonitored. It decides that by comparing the tracks held against the album's
total (read from Lidarr's source, `frontend/src/Artist/Details/AlbumRow.js`,
2026-10-01). Paintings are organised the way music is: by creator, with a
catalogue the world keeps and a collection the owner keeps.

## Principles

Each is derived from scenarios or measurements, and each is a decision the owner
can reverse.

**P1. One world; owning is a state, not a place.** Search results, artist pages
and work pages show works whether they are held or not, each marked with its
state (§ States). The scenarios that cross layers (S2, S3, S4a, S5, S11) are the
ones a two-place design serves worst: the curator has to decide which place to
look in before they know the answer. The earlier reason for splitting was cost,
and cost applies only to getting. *Exists* and *Seeable* are free:
`user-scenarios.md` § Four layers, and the 16th-century measurement below.

**P2. The artist is the hub.** An artist page answers S3, S5 and S11 in one
place. It shows what you hold, what exists, what can be seen, who is similar, and
whether you like them.

**P3. Pay at one door.** Getting is the only act that costs money or takes
minutes, so it is one control with one shape everywhere. Select works, from any
page, press **Get**, see the estimate, confirm. The open-ended intent ("American
modernists") is the same door reached by asking (§ Ask). Browsing, searching and
looking never spend.

**P4. Walls are rooms.** Hanging works like playing music to a room. It takes any
set: a theme, an artist, a selection or one work. You choose which walls (one,
some or all). **The duration half waits for wave 4** (ruling 6): until then a
hanging lasts until changed, and ending an excursion is hanging the default theme
again, one wall at a time. A wall keeps a history, which answers S6's "what was
that?".

**P5. Taste is what the curator says, and excursions do not count.** Reactions
("more like this", "not for me") can be given on any artist or work and are
recorded as taste. Accepting works from a Get marked as an **excursion** writes
no taste, while a reaction given during it still counts (ruling 5b). The
excursion's works form a theme and **do not join the default theme** (ruling
5a). This principle matters only once something reads taste; today nothing does
(`user-scenarios.md` § Tested, the Delaunay request).

**P6. A thing has one page in every state.** An artist, work or topic has one
address, whether held or not, so a link never breaks when a work arrives. Where a
registry knows the thing, its registry ID is the identity (Wikidata QID, Getty
ULAN for artists). Otherwise the identity is the holding museum's object ID, and
for held works the catalogue's own. This depends on `user-scenarios.md` open
question 4.

## Objects

| Object | What it is | Music equivalent | Where its data comes from |
|---|---|---|---|
| **Artist** | A person or workshop with a body of work | Artist | Library; Wikidata and ULAN for life, movement and the catalogue of works |
| **Work** | One artwork, independent of any image of it | Album | Library; Wikidata, the holding museum |
| **Image** | One instance of a work: a source, a size, a route | A specific release or rip | Museum APIs, Commons, tile assembly |
| **Topic** | A period, movement, subject or medium | Genre, decade | Wikidata (movement, inception, depicts), facets on held works |
| **Theme** | A curated, ordered set of held works | Playlist | Library only |
| **Wall** | A display, and what it shows over time | Room or speaker | Programming |
| **Get** | One acquisition: works chosen, cost, progress, candidates to judge | A download in the queue | Discovery runs |
| **Taste** | What the curator has said they like and dislike | Likes, "not interested" | Affinities |

### States

A work's state is shown wherever the work appears, as glyph, word and colour
(`accessibility-spec.md`):

| State | Means | Offers |
|---|---|---|
| **Held** | In the library | Hang, add to a theme, archive |
| **Archived** | Held, out of rotation | Restore |
| **To review** | A Get found candidates for it; not yet judged | Review |
| **Image found** | A museum or Commons has an image of it. Whether it reaches wall resolution is not known until a Get tries | Get |
| **No image known** | It exists, and no source has an image | Want (§ Wanted) |

**Seeable-but-not-Hangable is not a state**, because nothing can know it without
trying. Promising "hangable" before a Get tries the route would be the error
corrected in `user-scenarios.md` (the Rothko the library already holds at
5,092 px). The honest label before trying is *Image found*. After a Get, the
candidates carry real sizes.

## The map

```
┌──────────────────┬───────────────────────────────────────────────┐
│ Arrt             │ [ Search artists, works, topics…            ] │
├──────────────────┼───────────────────────────────────────────────┤
│ ▣ Library (home) │                                               │
│     Artists      │                                               │
│     Works        │                                               │
│     Themes       │                                               │
│     Topics       │                                               │
│     Ask          │                                               │
│ ▢ Walls          │                                               │
│ ↻ Activity    ③  │                                               │
│     To review    │                                               │
│     Queue        │                                               │
│     History      │                                               │
│     Wanted       │                                               │
│ ⚙ Settings       │                                               │
│     Taste        │                                               │
│ ♥ System         │                                               │
│     Status       │                                               │
└──────────────────┴───────────────────────────────────────────────┘
```

Sub-pages show only under the current section, as in the *arr apps. Activity's
badge counts works waiting for review, the one queue that needs the curator.
Wanted appears once something is in it.

**The sidebar keeps the ratified *arr-layout norm** (`information-architecture.md`
§ Direction; ruling 9): no new top-level section. Topics and Ask sit under
Library, where every *arr app puts Add New. Walls keeps its slot. Pages an *arr
app has keep the *arr name, so the page this proposal first called *Getting* is
**Queue**. Two pages of the first draft are dropped: *Spending*, because the spend
record already lives in System › Status, and *Sources*, because no scenario needs
it. *(Builder's call, 2026-10-01; the owner can overrule it.)*

**Home is Library** (ruling 1). The owner chose it over Now Showing, the
builder's recommendation, which was argued from assumed weekly frequencies for
S1 and S6. The choice is evidence that browsing and acquiring is what Arrt is
opened for most, and that the walls scenarios are rarer than
`user-scenarios.md` assumed. What is on each wall now is shown on Walls.

## Pages

### Walls

What hangs on each wall, and how each wall is set up. One card per wall. Each card shows the work on the wall now, large, with its
label facts. Below it: what it is drawn from (a theme, an artist or a selection);
how long that lasts ("until changed" or "until Friday, then back to *Modern*");
and the next three works.

The controls on each card are **Skip**, **Not this one again**, and **Change**.
*Not this one again* asks one question, *from this theme* or *from every wall*,
because S8 says "nothing else changed" and those are two different changes.
*Hang everywhere…*, one act for all walls, waits for wave 4 with the rest of
hanging for a duration (ruling 6). Each wall's history (what hung when, and
from what) and its configuration open from its card.

### Artist (the hub)

- **Header:** name, life dates, movements, a short note from the registry, and a
  taste control (*More like this*, *Not for me*).
- **In your library (n):** the held works, as in Library › Works filtered to the
  artist. Hang and add to a theme apply to a selection.
- **Their work:** every work the registry knows, each with its state and a
  preview where one was found. Sorted by renown, with fame measured by how many
  Wikipedias cover the work. Filter by state ("Image found" only), period or
  medium. Select, then **Get**.
- **Similar artists:** from the registry's movement and influence links, then
  from Ask. Each shows how many of their works have an image found, so the
  curator does not commit to an artist nobody can supply (the Delaunay gap).
- **Holdings:** which museums hold their work, with counts.

### Work

One page in every state. It shows the image (held), the preview (image found), or
an empty frame (no image known), with title, artist, date, medium and holder
(museum and accession number). The state strip changes with the state: walls and
themes it is on (held); images found, with their sources, and **Get** with its
estimate (not held); **Want** (no image known). The rest of the artist's work
shows below, as the next thing to look at.

### Topic

A period, movement, subject or medium, browsed like a genre. It shows held works
in the topic, then **representative works** ranked by renown with their states,
then artists in the topic. Select, then **Get**, optionally as an excursion. This
is S12's door in. Representative works are free to list: measured 2026-10-01, the
15 most-covered 16th-century paintings on Wikidata (sitelinks over 25) all have a
free image (Mona Lisa, *The Hunters in the Snow*, *The Ambassadors*, …). It also
shows the registry's messiness: *Salvator Mundi* appears twice, once for Leonardo
and once for "Leonardeschi".

### Search

**As you type** (free and instant): matches grouped by object, with Artists
first, then Works, Topics and Themes. Each row carries its state. Library matches
come first, then registry matches. Matching ignores case and accents, so `dali`
finds Dalí (`user-scenarios.md` measured that it does not today).

**On Enter:** the results page, with *All*, *In your library* and *Not held*
views. If the query names one artist, that artist is the top result and is one
key from the hub. Nothing on this page spends.

**When a registry has nothing** (contemporary or web work, `re-architecture.md`):
the results say so and offer **Ask**, which can still find and Get by intent.

### Ask

The conversation, unchanged in purpose: open intent that is not an artist, a
work or a topic ("who's like the Delaunays?", "quiet interiors"). Its suggestions
are artists, works and topics, each linking to its page and showing its state, so
the conversation is a way into the same world rather than a separate one. A
direction it settles on becomes a **Get**, in place (the seam ruling in
`information-architecture.md` § Flow 1 stands).

### Theme

A playlist: held works in an order. **Hang…** takes walls (and, from wave 4, a
duration).

**The default theme is the everyday rotation, and it is an ordinary theme.** An
excursion's works form their own theme and are not in the default one (ruling
5a). Nothing else marks an excursion: when it is over, the curator hangs the
default theme again, and the excursion's works stay held, in their theme, out of
the rotation. *"I'm not sure
there's anything needed beyond marking them as a theme, and not being in the
default theme? Let's not overcomplicate."* (the owner, 2026-10-01).

**This already holds today, with no change.** Measured 2026-10-01: the owner's
*All works* is an ordinary theme with recorded membership (40 members, the 40
accepted works), and it is what their wall is hanging. Nothing adds a work to a
theme automatically: the only callers of `add_to_theme` are the HTTP route and
its MCP twin. So an excursion's works stay out of *All works* simply by not
being added. But an ordinary acceptance joins no theme either, so every new
everyday work had to be added to *All works* by hand. **Ruling 8 makes *All
works* the default theme**: ordinary acceptances join it automatically, and
excursion acceptances still do not.

### Activity

**To review** is the inbox: candidates from Gets, grouped by Get, judged with
explicit controls (the no-gesture ruling stands). **Queue** shows Gets in
progress, with spend so far. **History** lists finished Gets. **Wanted** holds
works marked Want (no image known, or a Get that found nothing). It is where a
future Watch would land, like Lidarr's Wanted › Missing.

## The scenarios, walked

| # | Path in this IA | Spends? |
|---|---|---|
| S1 Put an owned work up now | Search `dali` → work → **Hang…** → wall → Now | No |
| S2 Do I have it? | Search → the row's state says Held or not | No |
| S3 More by an artist | Search → Artist → Their work, filter *Image found* → select → **Get** | At Get |
| S4a Does this work exist? | Search → Work page: holder, accession, state | No |
| S4b Get a copy | Work → **Get** | At Get |
| S5 Who's like…? | Artist → Similar artists; or Ask | No, until Get |
| S6 What's on the wall? | Walls | No |
| S7 Make a theme and hang it | Library › Works → select → add to theme → Theme → **Hang…** | No |
| S8 Tired of this one | Walls → card → **Not this one again** → this theme or every wall | No |
| S9 Clean-up | Library › Works filtered by low resolution or never hung; Activity › To review | No |
| S10 Is it working? | The status indicator in the top bar → System › Status | No |
| S11 Rothko, knowing nothing | Search `rothko` → Artist: 2 held, then their work with previews and states → select → **Get** | At Get |
| S12 16th century for two days | Library › Topics → 16th century → representative works → **Get as excursion** → its theme → **Hang…** on each wall → when done, hang the default theme again. The works stay in their theme, out of the rotation. From wave 4: **Hang… on all walls until Sunday**, and the walls return by themselves | At Get |
| Delaunays | Search → Robert Delaunay → Similar artists (each with how much has an image) → *More like this* records taste → Ask for more | No, until Get |

S11 and S12, the two scenarios the built IA failed in `user-scenarios.md`
§ Tested, become one search and one topic page.

## Against what is built

| Built (as of 2026-10-01) | Proposal | Change |
|---|---|---|
| Artworks is home | Library › Works is home | **Kept** (ruling 1) |
| Library has Artworks and Themes | Library has Artists, Works, Themes, Topics, Ask | **New:** Artist page and index, Topic pages |
| Add New is a place: an intent box and conversations | Gone as a place. Get is an action on any selection; Ask is the conversation, under Library | **Removed** as a place: an owner-ruled departure from the *arr norm (ruling 3) |
| Two-scope search: library, then *Search museums* → a paid run | One world: library and registry matches with states, free | **Changed** |
| Search misses `dali` | Folds accents | **Fix**, independent of everything else |
| Hang on one wall per click; no end; no history | Walls keep a history now; hanging on several walls, for a duration, with revert comes with wave 4's schedule | **New**, mostly deferred (ruling 6) |
| *All works* is an ordinary theme, kept by hand | The designated default theme: ordinary acceptances join it automatically, excursion acceptances do not | **Changed** (rulings 5a and 8) |
| Archive one work at a time | Archive a selection; *Not this one again* from Walls | **Changed** |
| Taste recorded, unread | Taste read by Ask and by similar artists; excursion acceptances write none, reactions during one do | **New** |
| Activity: Queue, History | Activity: To review, Queue, History, Wanted | **Added**: To review and Wanted |
| Walls as a top-level page | The same slot, now leading with what each wall shows | **Kept** (ruling 9) |

**Kept as they are:** the theme as an ordered set; review with explicit verdicts;
the conversation's in-place transformation into a run; facets with counts and no
dead ends; the health indicator in the top bar; the *arr layout of sidebar, top
bar search and toolbar.

## Dependencies and risks

- **Identity (P6) is a prerequisite.** Pages for works not held need a stable ID.
  Storing a Wikidata QID where one exists is `user-scenarios.md` open question 4,
  and the owner ruled *yes* (ruling 7). Without it, the artist page's "Their work"
  can still be built from live lookups, but *Held* cannot be matched to the
  registry reliably. Matching by title and artist is the current dedup key, which
  "Untitled" breaks (`re-architecture.md`).
- **Live lookups cost latency, not money.** Wikidata's query service is built
  for queries, not typeahead, and its latency was not measured here. Typeahead
  should hit the library and a cached registry index, not run a live query per
  keystroke. Rate limits apply
  (Wikidata asks for a descriptive User-Agent; the Art Institute asks for an
  `AIC-User-Agent` header).
- **Registry coverage is uneven, and not measured beyond four artists and one
  period.** Dalí, Rothko and both Delaunays are well covered for existence, but a
  museum can split one artist across two records (Robert Delaunay is two agent
  IDs at the Art Institute). Contemporary work may be in no registry; Search then
  falls back to Ask.
- **"Image found" is a weaker promise than it looks.** A preview proves an image
  exists, not that a Get will reach wall resolution. The label says only what is
  known.
- **P5 has no effect until taste is read.** Building the reader is its own piece
  of work.
- **Departing from the built IA costs re-work** in `static/` and its browser
  suite (16 test files). The accent fix and the Artist page stand on their
  own and could ship first. The rest follows the rulings below.

## Rulings (2026-10-01)

The owner ruled on each decision in turn, then on two the rulings raised. The wording of each option is the
builder's; the choice is the owner's.

| # | Decision | Ruling |
|---|---|---|
| 1 | Home | **Library.** The builder recommended Now Showing. |
| 2 | Search scope | **One world**: library and registry matches together, each with its state. |
| 3 | Add New | **Dissolved.** Get is an action on any selection; Ask is the conversation. Every *arr app has an Add New, so this is a ruled departure from the *arr-layout norm. |
| 4 | Artist page | **The full hub**: held works, their work, similar artists, holdings, taste. |
| 5a | When an excursion ends | **Nothing beyond a theme**: its works form a theme and are not in the default theme. The builder's options (archive, keep, ask, delete) were all declined as overcomplicated. |
| 5b | Excursions and taste | **Acceptances do not count; explicit reactions during one do.** |
| 6 | Hanging for a duration | **Wait for wave 4's schedule.** Neither the end time nor the one-act "all walls" control is built before it. |
| 7 | Registry IDs | **Store them** where one exists (Wikidata QIDs for works and artists), and keep the catalogue's own identity where none does. |
| 8 | A default theme | **Yes: "There should be a default 'all works' theme."** A work accepted from an ordinary Get joins it; one accepted from an excursion Get does not. Raised by ruling 5a, ruled the same day. |
| 9 | The sidebar | **Fit the norm**: no new top-level sections. Topics and Ask under Library, Walls in its slot. The builder's map had added Explore and Now Showing, which the norm allows only by an *arr precedent or an owner ruling; offered both, the owner chose the norm. |

**Ruling 8 changes one built thing.** Today nothing adds a work to a theme
automatically, so acceptance has to start doing so. The owner's existing *All
works* (40 members, all 40 accepted works) is the natural theme to designate,
and needs no backfill. How it is designated, and whether it can be renamed or
deleted, is not ruled; the build plan proposes it.

**What follows, in order.** Amend `information-architecture.md` from this
proposal. Then a build plan, whose first pieces stand on their own: the accent
fix, the default theme (ruling 8), storing registry IDs (ruling 7), and the
Artist hub (4), which needs the IDs.
