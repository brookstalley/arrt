# Information Architecture — a proposal from the scenarios

**Written 2026-10-01, at the owner's request: "Without preconceptions from what
we've already built, build a strong IA story for the app."** It is derived from
`user-scenarios.md` and from measurements, and it looks at the built screens only
in § Against what is built. **It is a proposal, not ratified.** Nothing in
`information-architecture.md` changes until the owner rules on § Decisions for the
owner. The scenario frequencies it weighs are still the builder's assumptions
(`user-scenarios.md` § Scenarios).

## The story

**Arrt is a record collection for paintings, with the walls as its rooms.**

- **The artist is the centre**, as in a music library. Of the six scenarios about
  finding something (S1–S5, S11), four are phrased by artist: S1's "the Dalí", S3,
  S5 and S11.
- **Everything that exists can be browsed for free.** Owning is a state a work is
  in, not a different part of the app.
- **There is one door that costs money: *Get*.** It is always explicit and always
  priced before you press it.
- **Walls are rooms you hang to**, the way a music app plays to a room: one wall
  or all of them, until changed or until a date, after which each wall goes back
  to what it showed before.

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
some or all) and for how long (until changed, or until a date, after which each
wall returns to what it showed before). That is S1, S7 and S12 with one control.
A wall keeps a history, which answers S6's "what was that?" and lets an
excursion end cleanly.

**P5. Taste is what the curator says, and excursions do not count.** Reactions
("more like this", "not for me") can be given on any artist or work and are
recorded as taste. Accepting works from a Get marked as an **excursion** writes
no taste and keeps those works out of the everyday library view (S12). This
principle matters only once something reads taste; today nothing does
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
│ ▶ Now Showing    │                                               │
│ ▣ Library        │                                               │
│     Artists      │                                               │
│     Works        │                                               │
│     Themes       │                                               │
│ ◇ Explore        │                                               │
│     Topics       │                                               │
│     Ask          │                                               │
│ ↻ Activity    ③  │                                               │
│     To review    │                                               │
│     Getting      │                                               │
│     History      │                                               │
│     Wanted       │                                               │
│ ⚙ Settings       │                                               │
│     Walls · Taste · Sources · Spending · System                  │
└──────────────────┴───────────────────────────────────────────────┘
```

Sub-pages show only under the current section, as in the *arr apps. Activity's
badge counts works waiting for review, the one queue that needs the curator.
Wanted appears once something is in it.

**Home is Now Showing.** Under the assumed frequencies, the most common reasons
to open the app are about the walls: putting something up (S1, weekly), asking
what is up (S6, weekly), taking something down (S8, monthly), and ending an
excursion (S12). A music app's home is what is playing and what to play next, and
this is the same idea. **The alternative is Library as home**, the *arr default.
That is the right choice if the owner mostly opens Arrt to browse and acquire,
which is exactly what the frequency question in `user-scenarios.md` asks.

## Pages

### Now Showing (home)

One card per wall. Each card shows the work on the wall now, large, with its
label facts. Below it: what it is drawn from (a theme, an artist or a selection);
how long that lasts ("until changed" or "until Friday, then back to *Modern*");
and the next three works.

The controls on each card are **Skip**, **Not this one again**, and **Change**.
*Not this one again* asks one question, *from this theme* or *from every wall*,
because S8 says "nothing else changed" and those are two different changes.
**Hang everywhere…** applies to all walls at once.

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

A playlist: held works in an order. **Hang…** takes walls and a duration. A theme
made from an excursion Get is marked as one, and the theme offers **End
excursion**. That ends its hangings, so each wall goes back to what it showed
before, and archives the works or keeps them as the owner chooses (§ Decisions).

### Wall

Under Settings, since walls are configured rarely. It shows the wall's
configuration and its full history: what hung when, and from what. Now Showing
is where the walls are *used*.

### Activity

**To review** is the inbox: candidates from Gets, grouped by Get, judged with
explicit controls (the no-gesture ruling stands). **Getting** shows Gets in
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
| S6 What's on the wall? | Home | No |
| S7 Make a theme and hang it | Library › Works → select → add to theme → Theme → **Hang…** | No |
| S8 Tired of this one | Home → card → **Not this one again** → this theme or every wall | No |
| S9 Clean-up | Library › Works filtered by low resolution or never hung; Activity › To review | No |
| S10 Is it working? | The status indicator in the top bar → Settings › System | No |
| S11 Rothko, knowing nothing | Search `rothko` → Artist: 2 held, then their work with previews and states → select → **Get** | At Get |
| S12 16th century for two days | Explore › Topics → 16th century → representative works → **Get as excursion** → theme → **Hang… on all walls until Sunday** → Sunday: walls return, and the theme offers **End excursion** | At Get |
| Delaunays | Search → Robert Delaunay → Similar artists (each with how much has an image) → *More like this* records taste → Ask for more | No, until Get |

S11 and S12, the two scenarios the built IA failed in `user-scenarios.md`
§ Tested, become one search and one topic page.

## Against what is built

| Built (as of 2026-10-01) | Proposal | Change |
|---|---|---|
| Artworks is home | Now Showing is home | **Changed**, pending the frequency answer |
| Library has Artworks and Themes | Library has Artists, Works, Themes | **New:** Artist page and index |
| Add New is a place: an intent box and conversations | Gone as a place. Get is an action on any selection; Ask is the conversation | **Removed** as a place |
| Two-scope search: library, then *Search museums* → a paid run | One world: library and registry matches with states, free | **Changed** |
| Search misses `dali` | Folds accents | **Fix**, independent of everything else |
| Hang on one wall per click; no end; no history | Hang… on walls for a duration; walls keep history and revert | **New** in programming (wave 4's schedule) |
| Archive one work at a time | Archive a selection; *Not this one again* from Now Showing | **Changed** |
| Taste recorded, unread | Taste read by Ask and by similar artists; excursions write none | **New** |
| Activity: Queue, History | Activity: To review, Getting, History, Wanted | **Renamed** and **added** |
| Walls as a top-level page | Now Showing for using walls, Settings › Walls for configuring them | **Split** |

**Kept as they are:** the theme as an ordered set; review with explicit verdicts;
the conversation's in-place transformation into a run; facets with counts and no
dead ends; the health indicator in the top bar; the *arr layout of sidebar, top
bar search and toolbar.

## Dependencies and risks

- **Identity (P6) is a prerequisite.** Pages for works not held need a stable ID.
  Storing a Wikidata QID where one exists is `user-scenarios.md` open question 4,
  and this proposal answers it *yes*. Without it, the artist page's "Their work"
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
  own and could ship first. Everything else waits on the decisions below.

## Decisions for the owner

1. **Home:** Now Showing (recommended, if S1 and S6 really are weekly), or
   Library.
2. **One world (P1):** registry matches shown beside library matches with their
   states, or keep the *Search museums* split.
3. **Add New dissolves** into Get (on any selection) and Ask. Or keep it as a
   place as well, since every *arr app has one.
4. **The Artist page as hub (P2)**, on the Lidarr model.
5. **Excursions:** when one ends, archive its works or keep them? Should its
   acceptances be kept out of taste (P5)?
6. **Hang for a duration, with the wall reverting** (P4): build it now, or wait
   for wave 4's schedule?
7. **Store registry IDs** (P6, open question 4).
