# Operator verification queue

Visual and live-integration work the operator has to look at with their own eyes.
An entry stays here until it is checked off; nothing here blocks a build, and
`operator_verification_required` is `false`, so this is a list rather than a gate.

**No screenshots are committed.** They are cheap to regenerate and would be stale
binaries in a public repo within a chunk. The command that produces them is in
each entry, which is the durable form.

## Pending

### An HDMI wall on its screen — added 2026-10-02

**`build-plan-clients.md` Chunk 04.** Visual change: yes.

Checked by the builder and the owner on 2026-10-02, on the Pi's HDMI-A-1 and a
4K LG, with the built output run by hand as `tvpi` against three renders (two
3840×2160 Frame renders and a 1200×2000 portrait); the measurements are in
`hdmi-output-findings.md`. **Still to look at, once Chunk 05 deploys the
Player:** a real wall rotating on the monitor, fitted whole with nothing
cropped, a portrait work with bars at the sides; the monitor switched off and on
(or its cable pulled) and the picture back within a poll; and, with the Player
stopped, the text console in its place.

### Settings › Clients, and which client shows each wall — added 2026-10-02

**`build-plan-clients.md` Chunk 02.** Visual change: yes.

Checked by the builder on 2026-10-02 at 1280 px and 390 px in the browser
suite's own server: no client; a client that had reported two outputs and
showed one wall beside one with no token and no report; the token shown once
after an add; and the Walls screen with one wall assigned and two not. Not on
your catalogue. Regenerate with
`cd arrt && uv run pytest -m browser -n0 tests/browser/test_the_clients.py tests/browser/test_the_walls.py -k client`
and a `page.screenshot` of your own.

- **Settings › Clients** is under Settings, after Taste. *Add a client* takes a
  name and issues its token in the same act: the token appears once, selected in
  a read-only field, with a sentence saying it is the only time and to set
  `CLIENT_TOKEN` and `SERVER_URL` in the Player's settings (the address is the
  one your browser used — check it is the one the Pi reaches). Reload, and it is
  gone.
- **Each client** says when its token was issued (or that it has none), its last
  report's age, its outputs as a table (Output, Kind, Connected, Screen), the
  walls it shows with **Unassign**, an **Assign a wall** row (a picker of reported
  outputs, the free one first; a text field with `hdmi-a-1` as placeholder when
  nothing is reported), and **Rename**, **Rotate the token** / **Issue a token**,
  **Remove**. Rotate and Remove ask first; Remove names the walls left without a
  client.
- **The Walls screen** says under each wall's title "Shown by pi4 on hdmi-a-1",
  or "No client shows this wall." with a link to Settings › Clients.
- **To look at:** whether the outputs table, which scrolls sideways inside its
  panel on a phone, reads well enough there; and whether adding a client and
  issuing its token in one act is what you want, rather than two steps.

### Want and Forget, Activity › Wanted, and the Wikidata picker — added 2026-10-02

**`build-plan-after-review.md` Chunk 05.** Visual change: yes.

Checked by the builder on 2026-10-02 at 1280 px and 390 px in the browser
suite's own server, with two works wanted through the service and the picker's
matches stubbed from the live answer for *Lobster Telephone*. Regenerate with
`cd arrt && uv run pytest -m browser -n0 tests/browser/test_wanted.py` and a
`page.screenshot` of your own.

- **A review card whose search found nothing** shows **Want** and **Forget**
  where Accept and Reject were. Want repaints the card `◑ wanted`, says "It
  waits in Activity › Wanted…", and leaves only Forget.
- **Activity › Wanted** appears in the sidebar, with its count, once a work is
  wanted. The page: "*n* works wanted", a sentence that searching spends nothing
  and why a work with no item is offered a pick, **Search all**, then a table of
  Work — Artist, Why (*No scan found* or *1 scan turned down*), Wikidata (the
  item, or *No item*), From (*The search*), and **Search again** / **Forget**.
- **Search again on a work with no item** opens *Which is <title>?* above the
  table: each match as **This one**, title, maker, item, and whether Wikidata
  has a picture; then *None of these — search without an item*.
- **To look at on your catalogue:** the seven no-scan works from the 16 August Dalí run. Want them, then
  pick *Lobster Telephone*'s item (Q2990594) and search again; and whether the
  picker's bulleted list reads well on a phone.


### Where an accepted work's image stands: the Work page, Review, Activity › Queue — added 2026-10-02

**`build-plan-after-review.md` Chunk 02.** Visual change: yes.

Checked by the builder on 2026-10-02 at 1280 px and 390 px in the browser
suite's own server (the seeded works plus two written into the queue's table),
not on your catalogue, and with no worker running. Regenerate with
`cd arrt && uv run pytest -m browser -n0 tests/browser/test_acquisition_states.py`
and a `page.screenshot` of your own.

- **Work page, *The master image*:** a work with no image says
  `◌ queued` and "Waiting its turn to be fetched…", with no button; one the
  queue gave up on says `✗ gave up`, "Gave up after 4 tries: <why>. Nothing tries
  again until you retry.", and **Retry**, which repaints it to queued. A failed
  try says "Try 1 of 4 failed: <why> It tries again at <date, time>." with
  **Retry now**. On a phone the sentence wraps beside the badge and Retry sits
  beneath.
- **Activity › Queue:** below the searches, *Fetching images (n)* is a table of
  Work, State, What happened, in the order the queue will try them. A paused
  queue says "Every fetch is paused: <why> <remedy>" above the table.
- **Review:** an accepted card says the same line under its badges.
- **To look at on your catalogue:** whether the repeated "Waiting its turn…"
  sentence on every queued row of the Queue reads as noise with a long backlog,
  and how *fetching* reads while a real tiled fetch runs (no test drives a live
  fetch).


### A Get reviewed on its own page, wide, with its scans readable — added 2026-10-02

**`build-plan-topics-and-destinations.md` Chunk 07.** Visual change: yes.

Checked by the builder on 2026-10-02 in the browser suite's own server, with
stubbed payloads and stand-in pictures (flat colour), not on your catalogue.
Regenerate the same views with
`cd arrt && uv run pytest -m browser -n0 tests/browser/test_reviewing_a_get.py`
and a `page.screenshot` in a test of your own; no images are committed.

- **1280 px.** A finished Get of *The Magpie*: the run's sentence and costs,
  then *Works (1)* and "1 work you chose.", then the card — the picture in the
  left two-fifths, and on the right the title, artist, **3,840 × 2,604 px**, the
  badges (◇ you chose · ● the run found an image · ● native, no inches), the
  Wikidata item, *Why*, *Accept*, *Reject*. No *Review these works* and no work
  table. With *Scans* open, a table across the card's full width: Scan,
  Resolution, Provider, Rights, Confidence, Chosen, Actions, one row a scan, and
  under each its *Why this one* and *Where it lives*. No label or button wraps;
  the card measured 811 px tall with two scans open (the owner's was about
  7,000). Nothing wider than the screen. Clicking the picture opened it over the
  page in a dialog with *Close*; Escape, *Close* and a click outside each shut it
  and left the address alone.
- **375 px.** One column: the picture above the facts. The Scans table scrolls
  sideways inside the card, and the sentences under each scan stay on screen
  while it does. Nothing wider than the screen.
- Artworks, a work's page and a theme's page show the fit verdict's word alone.

For you:

1. **On your catalogue, a Get with a few works**: is one work to a row right, or
   too tall to judge many in a sitting? (`#review/<get>` shows the same cards.)
2. **The enlarged picture** is the largest preview the server holds: 843 px wide
   from the Art Institute, 960 from Commons. Big enough to judge a scan by?
3. **The sentence a run writes about a scan** now says "It is 3,840 × 2,604 px,
   enough to fill the artwork box" rather than inches, for runs from now on.
   Older runs keep the sentence they wrote.

### Library › Topics and the Topic page — added 2026-10-02

**`build-plan-topics-and-destinations.md` Chunk 05.** Needs `WIKIDATA_USER_AGENT`
set; without it both pages say topics need it.

Checked by the builder on 2026-10-02 in the browser suite's own server, with a
fake Wikidata, not on your catalogue, at 1280 px and 375 px, nothing wider than
the screen. Topics, under Artworks after Themes, read *Find a topic*, then
Periods (*16th century · 2 works*), Movements, Subjects (*winter · 1 work*) and
Media, each kind with none saying so. Finding `impressionism` listed two
*Impressionism*s told apart by Wikidata's description. The *16th century* page
showed its kind, description and Wikidata link, *In your library (2)* as cards,
then *Works from 1501–1600* (● Held, ◐ Image found, ○ No image known; no box on
the held row), *Add to* already on *16th century (new theme)* with no name field showing (since Chunk 06), and
*Artists*. At 375 px the works table scrolls sideways inside its panel, as the
Artist page's does. S12's path was driven through the API on a copy of your
catalogue on 2026-10-02 (16th century, three works into a new theme *16th
century*, accepted: in it and not in *All works*), so what is left is the look.
For you:

1. **A period's heading.** Its works are headed *Works from 1501–1600* rather
   than *Representative works*, because they are matched by date alone. Every
   period, centuries included. Right?
2. **The typeahead.** Typing a topic's name offers *Topics* (yours) after your
   works, and *Wikidata: topics* after Wikidata's works, each with Wikidata's
   description. Useful, or too much in the dropdown?
3. **The titles look like buttons** in the works table and the topic lists, as
   they do on the Artist page and the results page. Restyle them all as links?

### Add to: where a Get's works go — added 2026-10-02

**`build-plan-topics-and-destinations.md` Chunk 02.** Every Get control (the
Artist page's *Their work*, the results page, a work's own page) gains *Add to*,
and Queue, History, the run page and Review say where a run's accepted works go.

Checked by the builder on 2026-10-02 in the browser suite's own server, not on
your catalogue, at 1280 px and 375 px, nothing wider than the screen: *Add to*
read *All works*, *Winter*, *New theme…*; choosing *New theme…* showed a *New
theme's name* field, and a Get into *16th century* said "Getting 1 work into
16th century. Open the Get" and left *16th century* chosen. At 375 px the select
and *Get* sit on one line and the sentence wraps beneath. Driving a Get into a
new theme on a copy of your catalogue was done through the API on 2026-10-02 (in
that theme, not in *All works*, still not after a restart), so what is left is
the look. For you:

1. **The label.** *Add to* sits beside *Get*, and on the Artist page a second
   select, *Theme*, adds works you already hold. Are the two told apart?
2. **A name you type that is already a theme joins it**, ignoring capitals and
   spaces, as a name a Topic page suggests will. Right for a typed name too?
3. **With no default theme**, the first choice reads *No theme (none is the
   default)* and the sentence says "into no theme". Clear enough?
4. **History says *Into* for Ask runs too**, naming today's default, which may
   not be the theme they joined if you have moved the default since.

### To review, and its count in the sidebar — added 2026-10-02

**`build-plan-get-and-ask.md` Chunk 06.** Activity's first page lists the runs
holding works that found an image and wait for your verdict.

Checked by the builder on 2026-10-02, on a copy of your catalogue at 1280 px and
375 px, nothing wider than the screen: **your catalogue already had 16 works
waiting**, 12 from the August "salvador dali" search and 4 from "robert
delaunay's rhythm", plus the builder's 2-work Get, so To review listed three
runs and the sidebar read *Activity 18 to review* and *To review 18*. For you:

1. **Activity now opens To review**, not Queue, because it is first in the
   section. Sonarr's Activity opens its Queue. Which would you rather land on?
2. **The count's wording.** *18 to review* beside Activity and *18* beside To
   review. Clear, or too much in the sidebar?
3. ~~**The 16 old works.**~~ Answered 2026-10-02: leave them waiting, so To
   review has real works to show while it is developed.

### Ask, where Add New was — added 2026-10-02

**`build-plan-get-and-ask.md` Chunk 05.** Ruling 3 dissolved Add New: acquiring
is *Get* on a selection, and asking in words is *Ask*.

Checked by the builder on 2026-10-02, on a copy of your catalogue at 1280 px and
375 px, nothing wider than the screen: the sidebar reads Artworks › Ask, Themes,
Artists; typing `seurat` in the search box offered *Ask about "seurat"*, which
opened Ask with the words filled in and nothing started. The address is still
`#discover`, as `#collection` is still Artworks, so bookmarks keep working. For you:

1. **The name.** *Ask* for the intent box and the conversations, under Artworks.
   Does it read as the place to ask for a direction?
2. **The buttons.** They still say *Start the search* and *Talk it through first*;
   the plan had proposed *Search now* and *Talk it through*. Keep or change?

### Get, from the Artist page, the results page and a work's page — added 2026-10-02

**`build-plan-get-and-ask.md` Chunk 04.** Needs `WIKIDATA_USER_AGENT` and
`ARTIC_USER_AGENT` set. A Get fetches real images, so try it on a copy of your
catalogue first if you would rather not add works to the real one by accident.

Checked by the builder on 2026-10-02, on a copy of your catalogue at 1280 px and
375 px, nothing wider than the screen: on Renoir's page, *Their work* offered a
tick box on each of the 50 works you do not hold and none on *Seascape*, which you
do. Ticking *Bal du moulin de la Galette* and *Luncheon of the Boating Party* and
pressing *Get 2 works* said "Getting 2 works. Open the Get"; the run finished "2 of
the 2 works you chose have an image", both from Commons at 3840 px, and Review
showed each marked *◇ you chose* with its Wikidata item linked. For you:

1. **Where the tick boxes are.** A *Get* column on the left of *Their work* and a
   box beside each Wikidata work on the results page. Is ticking in a table the
   right gesture, or would you rather select from cards with pictures?
2. **No box on a held row.** The plan considered "Get 2 works (1 held, skipped)";
   leaving held rows unticked seemed plainer. Agree?
3. **What happens after.** The page stays put and says what started, with *Open
   the Get*. Would you rather be taken to the run?

### Similar artists, and setting a Wikidata item by hand — added 2026-10-01

**`build-plan-one-world-search.md` Chunk 05.** Needs `WIKIDATA_USER_AGENT` set.

Checked by the builder on 2026-10-01, on a copy of your catalogue at 1280 px and
375 px, with no page errors and nothing wider than the screen: Rothko's *Similar
artists* lead with Jackson Pollock (0 works with an image), then Bourgeois, de
Kooning, Appel and Gorky; Dalí's list Picasso, Kahlo, Miró (● in your library),
Lynch and Klee (●). On your held Rothko's Work page, looking up `q500985` named
*The Hunters in the Snow* and offered *Use Q500985*, which was not pressed. For you:

1. **Similar artists.** Wikidata calls some non-painters painters too (Captain
   Beefheart for Rothko, André Breton for Dalí). Is the list useful as it is, or
   should it wait for taste (plan 4)?
2. **The image count.** Does "0 works with an image" beside Pollock tell you what
   you need before you commit to him?
3. **The control.** Change… → type an id → Look up → *Use Q…*. Is showing the item
   first enough to stop a wrong one, and is *There is none* worded right?

### The search results page — added 2026-10-01

**`build-plan-one-world-search.md` Chunk 04.** Reached from the search box's last
row, *All results for "…"*; Enter still opens Artworks.

Checked by the builder on 2026-10-01, on a copy of your catalogue at 1280 px and
375 px, with no page errors and nothing wider than the screen: `rothko` led with
Mark Rothko as the top result, then your two Rothkos (● *In your library*), then
twenty more from Wikidata; `salvador dali` the same for Dalí; `hunters` led with
*The Hunters in the Snow*. For you:

1. **Is the row the right way in?** You kept Enter on Artworks; this page is one
   arrow-key and Enter away. Is that enough, or should it be more visible?
2. **The three views.** Do *All*, *In your library* and *Not held* answer "do I
   have it?" and "what exists?" without making you scroll?
3. **The top result** appears only when the words name exactly one artist.

### The search box covers Wikidata too — added 2026-10-01

**`build-plan-one-world-search.md` Chunk 03.** Needs `WIKIDATA_USER_AGENT` set.

Checked by the builder on 2026-10-01, on a copy of your catalogue with Playwright
at 1280 px and 375 px, with no page errors and nothing wider than the screen:
`dali` gave your Dalí and *Untitled (Desert Landscape)* first, then Wikidata's
*Dalibor Chatrný* and five Dalí works, with *Image found* where there is one;
`the persistence` gave *The Persistence of Memory* first; `hunters` gave Bruegel's
*The Hunters in the Snow* first. Wikidata's rows arrived about half a second
after the library's. For you:

1. **Type the way you search.** Do Wikidata's rows help, or crowd the library's?
   Five works and three artists is the cap; is it the right size?
2. **What a row says.** *in your library*, *Image found*, or nothing. Enough to
   choose by?
3. **Enter** still opens Artworks filtered, as you ruled. Does that still feel
   right with Wikidata in the list?

### Pages for works and artists you do not hold — added 2026-10-01

**`build-plan-one-world-search.md` Chunk 02.** Needs `WIKIDATA_USER_AGENT` set, as
the Artist page entry below does. Nothing here migrates the catalogue.

Checked by the builder on 2026-10-01, on a copy of your catalogue with Playwright
at 1280 px and 375 px, with no page errors and nothing wider than the screen:
`#work/Q500985` (*The Hunters in the Snow*) showed its picture, Bruegel, 1565, oil
on panel, the Kunsthistorisches Museum with its number GG_1838, *Search museums
for this work*, and 49 more of Bruegel's works below; `#artist/Q43270` showed
Bruegel's dates and what Wikidata lists; your Rothko's QID (`#work/Q20270685`)
and Rothko's (`#artist/Q160149`) were replaced by the library's own pages, and
Back skipped them; *Rothko Chapel*, from Rothko's *Their work*, opened as a
work you do not hold. Your held Rothko's own Work page was 333 px wider than a
phone before this chunk (a source URL in a table); it now scrolls the table
instead. For you:

1. **From an artist you hold, open a work you don't** (Rothko › *Their work* ›
   *Rothko Chapel*), then its artist, then back. Does it read as one world?
2. **The page of a work you don't hold.** Is *Search museums for this work* the
   right offer until *Get* exists (plan 2), and is *Not held · Image found* clear?
3. **An artist you don't hold** (`#artist/Q43270`, Bruegel). It says nothing of
   theirs is in your library; is that the first thing you want to know?

### The Artist page, against your own catalogue — added 2026-10-01

**`build-plan-ia-foundations.md` Chunks 03 and 04.** First, copy `catalogue.sqlite`
somewhere safe: this branch's first start migrates it (new columns, a new table,
*All works* marked the default), and a rollback across a migration is a restore
from that copy. Set `WIKIDATA_USER_AGENT` in
`.env` (`.env.example` says what Wikimedia asks for), stop the server, run
`cd arrt && uv run python -m arrt.identify` once, then start the server again.
On a copy of the catalogue this matched 22 of 40 works and 24 of 31 artists.

Checked by the builder on 2026-10-01, on a copy, with Playwright at 1280 px and
375 px: Library › Artists listed all 31; Rothko's page showed both held works,
*Held* on both in *Their work* (listed after the 50 most renowned, which neither
is among), *Image found* on the Rothko Chapel, and his holdings; Dalí's showed
his one work and four *Image found*; typing `dali` offered *Salvador Dalí —
artist* first; no page errors at either width. Screenshots are not committed;
the command above regenerates the state they show. For you:

1. **Rothko and Dalí, at desktop width and on a phone.** Do *In your library*,
   *Their work* and *Holdings* answer "what is their work, and what do I have
   of it?" The scenario is S11 (`user-scenarios.md`).
2. **Pictures.** *Image found* is almost empty for both, because Wikidata
   images are Commons files and both are in copyright. Is the page still worth
   its place for them, or should *Their work* lead with what can be seen?
3. **The titles Wikidata gives.** Your *Untitled (Desert Landscape)* is
   "Atmospheric Chair" on Wikidata, and about a fifth of Rothko's top fifty
   have no English title at all (shown as *No English title (Q…)*).
4. **An unmatched artist** (Clyfford Still, Josef Albers): the page should say
   Wikidata knows nothing for them yet, and the rest should work.

### The default theme, and search without accents — added 2026-10-01

**`build-plan-ia-foundations.md` Chunks 01 and 02.** Run it against your own
catalogue (`cd arrt && uv run python -m arrt`). The first start marks your *All
works* theme the default and records your 40 works as already placed, so nothing
moves on its own.

1. **Themes:** *All works* should carry ★ *default* in the accent colour, and
   every other theme a *Make default* button. Make another the default and back:
   the mark should move each time. Does the badge read as a role rather than a
   warning?
2. **Delete *All works*:** it should be refused, saying to make another theme
   the default first.
3. **Accept a work from a search:** it should appear at the end of *All works*.
   Take it out of *All works*, restart the server, and archive and restore it:
   it should stay out.
4. **Search without accents:** type `dali` in the top bar. Your Dalí should be
   offered before *Search museums*.

### The *arr sidebar, at desktop width and on a phone — added 2026-09-30

**`build-plan-arr-navigation.md` Chunk 02.** The three tabs are now a Sonarr-style
sidebar: Artworks (home, with Add New and Themes beneath it), Walls, Settings ›
Taste, and System › Status with a problem-count badge. The top bar keeps the
search and the status indicator. Run it (`cd arrt && uv run python -m
arrt`) and open it in a browser.

1. **Does it feel like Sonarr?** The question the owner's ruling asks: would a
   Sonarr user find each page where they expect it? Click through every section.
2. **Does the sidebar crowd the Walls page?** It takes 14rem on every page,
   including the one whose content is the artwork.
3. **Stop a wall's heartbeat or remove the backup receipt:** the System link
   should show a count, and the top-bar indicator should name the problem.
4. **Narrow the window below 40rem** (or open it on a phone): the sidebar
   should be gone behind a Menu button, which opens it as a drawer. Escape, or
   a tap beside it, closes it.
5. **Activity › Queue and History** (Chunk 03): start a search in Add New. It
   should appear in Queue while it works and while it waits at the approval
   gate, then move to History when it ends. Is a finished search with works to
   review easy enough to find in History, or does it need to stay in Queue
   (the recorded gap)?
6. **Search in two scopes** (Chunk 04): type an artist in the top bar. The
   dropdown should list your matches, then *Search museums for "…"*, which
   opens Add New with the words filled in and nothing started. Enter with
   nothing highlighted opens Artworks filtered.
7. **The toolbar** (Chunk 05): on Artworks, try View › Table, Sort › Artist,
   and Filter to put the rails away. Does the Table earn its place, and does
   hiding the rails give the grid enough back to be worth a button?

### Switch the Pi to HTTP mode, and let it soak — added 2026-09-30

> **Partly done, and changed, 2026-10-02.** The Pi pulled from the NAS in HTTP
> mode on 2026-10-02 (`build-plan-nas.md` Chunk 05: manifest and 40 renders
> cached, heartbeat seen on the NAS); the soak below did not run, because the
> owner skipped the Frame and the Pi's player is stopped. Steps 1, 2 and 5 name
> the retired wall token: a Player now connects as a client
> (`CLIENT_TOKEN`, from Settings › Clients), and `build-plan-clients.md`
> Chunk 05 replaces this soak on the Pi's HDMI output.

**Wave 2b Chunk 04.** Postarr can now pull its wall from Arrt instead of
reading the shared file. The file channel stays the default, and wave 3 retires
it only after this has run on the real wall. After wave 2b reaches the Pi:

1. On the Walls screen, issue a Player token for the wall (Player token panel).
2. In the display plane's `.env`, set `MANIFEST_SOURCE=http`,
   `SERVER_URL=http://127.0.0.1:<CURATION_PORT>`, `WALL_TOKEN=<the token>` and
   `CACHE_DIR=` to a local directory the service account can write. Then
   `sudo systemctl restart display.service`.
3. **Watch the journal** (`journalctl -u display.service -f`): `pull.started`,
   then `pull.adopted` with every entry cached. Press Next on the Walls screen:
   the set should step within a couple of seconds.
4. **Stop the server** (`sudo systemctl stop curation.service`): expect one
   `pull.unreachable` line and nothing more, and the wall keeps rotating. Restart
   `display.service` while the server is still down: the wall comes back from
   the cache. Start `curation.service` again: expect one `pull.reachable`.
5. **Rotate the token** on the Walls screen without updating `.env`: expect one
   `pull.refused` line naming WALL_TOKEN, and one `pull.heartbeat_refused`, and
   the wall keeps rotating. Put the new token in `.env` and restart.
6. **The health panel** should keep showing the wall's heartbeat throughout. In
   HTTP mode the Player writes its heartbeat into `CACHE_DIR`, and only the
   server writes the one in `ART_ROOT` that the panel reads, so a panel showing a
   fresh heartbeat is proof the POST works. During step 5 it should go stale.
7. Let it run for a few days, then record here what the journal showed. To go
   back, set `MANIFEST_SOURCE=file` and restart.

### ~~The Player token panel on the Walls screen~~ — retired 2026-10-02

The per-wall token and its panel were retired by `build-plan-clients.md`
Chunk 01: a Player now connects as a **client** with one token, issued on
Settings › Clients (Chunk 02). Nothing here is left to check; the clients
entry replaces it when Chunk 02 lands.

### Next and show_now move the wall without a sync — added 2026-09-30

**Wave 2b Chunk 02.** Until now, pressing **Next** on the Walls screen, or asking
for `art_display(action='next')` or `show_now`, advanced the directive in the
catalogue and never wrote it into the wall's manifest. The Player reads its
directive only from the manifest, so the wall did not move until something else
synced. After this reaches the Pi:

1. Hang a theme on the wall, wait for it to settle, then press **Next** once.
   The set should step to another work within about a second of the Player's
   next poll, with no sync in between.
2. Archive a work that is currently in the wall's rotation. It should come out
   of the rotation without a sync. The journal says `took works the Library no
   longer offers off the published manifest`.
3. Restart `curation.service`. The journal should say `Reconciled … against the
   Library at startup: nothing to change`.

### The Pi's units after the renames to arrt/ and postarr/ — added 2026-09-30, rewritten 2026-10-01

**Wave 2a and the rename of 2026-10-01, in one step.** The projects moved from
`curation/` and `display/` to `curatarr/` and `arrt/` (wave 2a), and then to
`arrt/` (the server) and `postarr/` (the player). The modules moved the same way.
The installed units still name the old directories and modules, so after pulling
this they fail to start until they are replaced. The unit *files* keep their
names until wave 3, so this replaces them rather than adding new ones.

**`arrt/` changed meaning.** In a checkout that took wave 2a, `arrt/` is the
player and holds its untracked `.venv`. After the pull the server's files land in
the same directory, beside a virtualenv built for the player. So every project's
`.venv` is removed before the pull, whichever names this checkout has.

    sudo systemctl stop display.service curation.service
    cd /opt/samsung-frame-art-loader
    sudo -u tvpi git rev-parse HEAD    # write this down: "To go back" returns to it
    sudo rm -rf curation/.venv display/.venv curatarr/.venv arrt/.venv
    sudo -u tvpi git pull
    # git moves the tracked files; the old directories keep only what was untracked.
    # Expect nothing but caches in whichever of these exist before removing them:
    ls -A curation display curatarr 2>/dev/null
    sudo rm -rf curation display curatarr
    cd /opt/samsung-frame-art-loader/postarr && sudo -u tvpi /usr/local/bin/uv sync --group raster --group epaper
    cd /opt/samsung-frame-art-loader/arrt && sudo -u tvpi /usr/local/bin/uv sync
    cd /opt/samsung-frame-art-loader
    sudo cp deploy/display.service deploy/curation.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl start curation.service display.service

Then run the four checks in `deploy/README.md` § How to tell your own install
worked: both units active and enabled, the installed copies matching the
checkout, the account reaching what it needs, and a fresh heartbeat. Logger
names now start `arrt.` (the server) and `postarr.` (the player), so a saved
journal filter on `curation.` or `display.` stops matching, and one on `arrt.`
from wave 2a now matches the server rather than the player. The wall is dark
between the stop and the start, so do it when nobody is looking at it.

**To go back**, check out the commit `git rev-parse HEAD` printed before the
pull, not "the commit before this merge": the step covers two merges, and the
one before the last has the server in `curatarr/` and the player in `arrt/`.
Then run the same steps with the names swapped: stop both units, remove every
project's `.venv`, check out, remove `arrt/` and `postarr/` if the old commit
has no such directory (only caches remain), `uv sync` in each project directory
the old commit has, copy its units in, reload and start.

### ✅ The rebuilt identification block, at the panel — added 2026-08-13, VERIFIED 2026-08-14

**Verified at the panel on 2026-08-14**, together with the entry below it — one
sitting answered both, and the two tunings it asked for are built, swept and
drawn. Six records were set: `hokusai`, `okeeffe`, `moche`, `nationality-only`,
and `hokusai` twice more as the tunings landed. `anonymous`, `unattributed`,
`wright` and `kandinsky` were deliberately not drawn — each is a milder reading of
one already judged, and the operator's panel time is the scarce thing here.

**What the sitting settled, question by question.**

1. **`KATSUSHIKA` over `Hokusai` reads as one name — after a change.** It did not
   at first: the gap inside the name was 46 px and the gap below it was 46 px, so
   nothing told the eye which two lines belonged together. Both are now charged to
   different lines, at 0.28 against 0.35 of the size. **Judged good.**
2. **The family name is set larger, at the operator's ask** — 1.2× the
   identification tier, 156 px against 130, on the rung where the ladder has given
   it its own line. **Judged good**, and the asymmetry it creates was accepted
   knowingly: `KATSUSHIKA` is larger than `O'KEEFFE` because his name earned a
   line and hers did not.
3. **32 px of border stands.** Seen against the fullest label in the corpus
   (`okeeffe`, six facts, nothing dropped) and not questioned.
4. **The bold still earns its place.** Seen on a broken name and an unbroken one a
   minute apart; the one comma on its line is doing the work the weight was chosen
   for.

**Three findings the questions were not looking for.**

- **The label was top-aligned and the slack all fell to the bottom** — 129 px of
  white under the reference record against 32 above. It now spends the leftover on
  the gaps by a capped multiplier and centres the residual, so the margins match on
  every record. Built and drawn in the sitting; `accessibility-spec.md` § Amended
  2026-08-14 carries the rule.
- **`Moche` is set at the identification tier but unstyled**, where a family name
  in the same position is bold capitals. Filed as **#143** — the catalogue stores
  the same two nulls for a culture that it stores for a person nobody has split,
  so the panel has nothing to style on. Distinct from **#140**, which is why the
  culture never arrives; both must land before a culture-attributed record reads
  as one.
- **Dimensions reach the label as source prose carrying both metric and
  imperial.** Filed as **#142**, at `stage: requirements` — 34 of 39 rows carry
  both systems, five carry one, in five different grammars, and every sourced
  imperial value uses a binary fraction, so a derived value needs a stated
  rounding convention before it can look like a museum's number.

**What the panel drew is not what any suite measures.** The three green suites
model type arithmetically; the wall resolves a different face. Every number quoted
above is from the panel's own machine.

---

**This entry replaces the two below it for the questions they asked about the
name.** Those were written against a Mac's font metrics and predicted an
arrangement the wall never drew; the sitting on 2026-08-13 found out why, and the
block has been rebuilt since. What is on the wall now is different enough that
the old questions no longer describe it.

**What the sitting found, so the next one starts from the truth.** The panel drew
`KATSUSHIKA,` / `Hokusai, Japanese` / `1760–1849` — every fact broken across a row
boundary. Three separate faults, all now fixed: the ladder engaged only on
vertical *overflow*, so a name that merely wrapped never triggered it; the
nationality and dates rode the name's line and took its tier, setting a demonym as
large as the name; and the preview's report collapsed wrapped rows, which is why
no reading of its output had ever shown this.

The block is now: `FAMILY, Given` at 12.4′ when it fits, broken to `FAMILY` /
`Given` — both still at 12.4′ — when it would wrap, with `Nationality, dates`
always on its own line at the 8.8′ floor. The border halved to 32 px, and four
artists gained a short nationality (`Born Moscow (formerly Russian Empire, now
Russia)` → `Russian`).

```sh
sudo systemctl stop display.service
cd /opt/samsung-frame-art-loader/postarr
draw() { sudo -u tvpi env HOME=/var/lib/tvpi /usr/local/bin/uv run \
    --group raster --group epaper python tools/label_preview.py --panel --record "$1"; }
draw hokusai; draw okeeffe; draw wright; draw kandinsky; draw moche; draw nationality-only
sudo systemctl start display.service
```

**No `--cap-arcmin`** — it is an override, and everything below is written in
terms of the calibrated 12.4′ and the 8.8′ floor.

**Four things to look for:**

1. **Does `KATSUSHIKA` over `Hokusai` read as one name?** Both are at 12.4′ now
   and the biography is a size below. If the two lines read as two facts rather
   than one name, the leading between them is one constant.
2. **Does the bold still earn its place?** `KATSUSHIKA, Hokusai` has one comma on
   its line instead of three, so the weight is no longer competing with a list —
   which was the original argument for it. Draw `okeeffe` and `wright`, which stay
   on one line, against `hokusai`, which breaks.
3. **Is 32 px of border right?** You judged this from 0 and 65 without seeing the
   rebuilt block. It is the number most likely to want a nudge now that the label
   holds more.
4. ~~**`Water Jar` still sits beneath `Japanese`**~~ — **struck 2026-08-13, and
   nothing here needs your eyes on it.** This asked you to judge an ordering that
   turned out to be the museum convention already: a culture-attributed work
   leads with the culture, and the title follows it
   (`museum-label-findings.md`). What is actually wrong is upstream — the culture
   should be in the *maker* field rather than arriving as a nationality, which is
   an acquisition-path defect now in the backlog. **Three questions at the panel,
   not four.**

**What the suite cannot tell you, and this is why the entry exists.** The wall
resolves a different typeface from the development Mac — 108 px rows against 93 at
the same declared size — so every measurement in `accessibility-spec.md` older
than this entry describes type the wall does not set. The panel is the only
authority on how any of this reads.

### ✅ The fill model and the name ladder, at the panel — added 2026-08-13, VERIFIED 2026-08-14 (see the entry above)

**Why this needs eyes.** 13B-4 changed what the panel shows for every work on the
wall, and the two judgements behind it are both about how a label *reads* rather
than about whether it fits. The suite proves the rules hold over every content
shape there is; it cannot say whether the result looks like a wall label.

**`--record` chooses which of the wall's eight records is set**, and every
question below is comparative, so the sitting is a sequence of runs rather than
one. At the panel, stop `display.service` once and draw each record against the
stopped unit — the invocation with this deployment's paths is in
`deploy/README.md` § The cutover.

```sh
cd postarr && uv run --group raster python tools/label_preview.py /tmp/label.png
cd postarr && uv run --group raster python tools/label_preview.py /tmp/short.png --record okeeffe
```

The report names the record first, then prints the type sizes in arcminutes,
names the styled runs, and prints anything **dropped** and anything **set below
the floor** — the two things that are invisible in the image and are the whole
point of the model.

**Four things to look for:**

1. **Does the two-line name read as one fact or as two?** `KATSUSHIKA` at 12.4′
   with `Hokusai, Japanese, 1760–1849` at 8.8′ beneath it is the ladder's second
   rung, and it is what most of this corpus will get. If the given name reads as
   belonging to the *next* fact rather than to the name above it, the leading
   between the two wants to be tighter than the leading between ordinary lines —
   which is one constant, not a redesign.
2. **Is the ladder taking its second rung too eagerly, or not eagerly enough?**
   Draw `hokusai` and `okeeffe` in the same sitting. `O'KEEFFE, Georgia,
   American, 1887–1986` stays on one line at 12.4′ and Hokusai's name does not,
   so the two together are the rung being *chosen* rather than applied — and
   `wright` is the third reading, a three-word name that also stays on one line.
   The rung is chosen by measurement, so if it looks wrong the thing to change is
   the tier the tail is set at, not the rule.
3. ~~**Is a sparse label too empty, or now too large?**~~ — **struck 2026-08-14:
   this predicted an arrangement the engine no longer produces, and the sitting
   drew the corrected one.** It warned that `--record moche` would set both
   `Moche, North coast, Peru` and `Stirrup Spout Vessel` at 12.4′ with the rest of
   the panel white, and called it the likeliest to look wrong. None of that
   happens now. The cumulative review's behavioural finding changed growth from
   asking whether a line may be *dropped* to asking whether *every* fact on it
   identifies the work, so `North coast, Peru` — a place of origin, and optional —
   stops growth before it reaches the title. What drew instead is `Moche` alone at
   12.4′, everything else at the floor, all six facts placed and the panel nearly
   full, which is the culture-attributed tombstone `museum-label-findings.md`
   records. **Judged good at the panel.**

   **What the sitting found here instead**, and it is not what this question was
   looking for: `Moche` is set at the identification tier but **unstyled**, where
   a family name in the same position is bold capitals. The size is right — 130 px
   is what every unbroken name gets, and the 156 px emphasis is rung-2-only — but
   the weight is withheld because the bold is applied to the *family name* run and
   a culture has no name parts. The seed table knows `"Moche": (None, None)` means
   a culture; the catalogue does not, storing the same nulls a person's unsplit
   name would. In the backlog.
4. **The two records with no artist name go the *other* way, and this is the
   thing most likely to look like a bug.** `--record nationality-only` (`Water
   Jar`, a nationality and no name) and `--record anonymous` (medium and date
   only) are set **small throughout** — 8.8′ on every line, with most of the
   panel empty. That is deliberate: the identification tier is withheld when
   nothing on the leading line identifies the work, because the alternative was a
   demonym set larger than the work's own title. ~~**What it does not fix is the
   ordering**~~ — **struck 2026-08-13**: the ordering was already the museum's,
   and the culture leading the title is the convention rather than a defect
   (`museum-label-findings.md`). The real fault is that the culture reaches the
   panel as a nationality at all, which is an acquisition-path defect and is in
   the backlog.

**What it would take to change any of these:** the first two are single constants
in `postarr/src/postarr/panel/layout.py`, not a redesign. Say what you see and the
tuning is cheap. **The third is struck and its replacement finding is not cheap** —
styling a culture like a maker needs the catalogue to record that it is one.

### ✅ The styled name, at the panel — added 2026-08-13, VERIFIED 2026-08-14

**Answered by the 2026-08-14 sitting, question 3 last and only when asked for
directly.** That sitting set six records and the operator judged the styling as it
went, which covered questions 1 and 2; question 3 had been on the panel the whole
time without being spoken about, and was put to the operator explicitly rather
than inferred from their silence. Absence of complaint is not a judgement, and an
entry ticked on two of three would have retired an unlooked-at question — which is
the failure this queue exists to prevent.

- **Question 1 — the bold does the disambiguating. Answered.** Seen on a broken
  name and an unbroken one within a minute of each other; the one comma on its
  line is doing the work the weight was chosen for, and the operator judged it
  good without prompting on the second reading.
- **Question 2 — 12.4′ is not too large in bold. Answered, in the opposite
  direction to the one this entry anticipated.** It asked whether bold reaches the
  same comfort a step *down*, freeing size for content. Standing at the wall the
  operator asked for the family name to go **up** — "could go even bigger and be
  more readable from across the room" — which is now 1.2× on the ladder's second
  rung. There is no size here for the fill model to reclaim.
- **Question 3 — the italic title at the 8.8′ floor. Answered: the convention
  stays.** Asked with `Water Jar` in italic on the panel. The italic is visible
  and reads; what the operator noted is that a title at the floor is not a size
  meant to be taken in from the couch, and accepted that.

  **Recorded in the scale's own terms, because the sitting's phrasing would
  contradict the section above it.** The operator described the floor as
  "intentionally too small for the 7 foot view"; the floor *is* a 7-foot size —
  § The type floor is derived from viewing distance derives 8.8′ from the 84-inch
  distance as the **threshold** of legibility, where 12.4′ is the comfortable
  reading. So what was accepted is that a title sits at the effortful size and is
  read by whoever walks up, which is the two-distance label this spec argues for
  working as designed — not that the floor is below its own derivation. The
  decision is the same under either wording; only this artifact's agreement with
  itself depends on which is written down.

**Why this needs eyes and not a test.** 13B-2 set the family name in bold
capitals and the title in italic. The suite can prove the right bytes got the
right attribute — it does, against real type — but it cannot say whether the
weight *does the job it was chosen for* at 7 feet on a reflective panel: making
a reader take `KATSUSHIKA` and then the rest, instead of four equal
comma-separated parts. That was the whole argument for collapsing the tombstone
onto one line, and it has never been looked at.

```sh
cd postarr && uv run --group raster python tools/label_preview.py /tmp/label.png
```

The report now prints each line as the panel sets it and names the styled runs
under it, because a terminal cannot show weight. Question 1 below is about a
comma that only the one-line arrangement has, so draw `--record okeeffe` or
`--record wright` for it — those are the names that stay on one line, and the
entry above explains why the reference record no longer does.

**Three things to look for, in this order:**

1. **Does the bold do the disambiguating?** Stand where you read the wall. If the
   first comma still reads like the other two, the collapse is not paying for
   itself and the name wants its own line — which is the ladder 13B-4 builds, and
   this is the observation that would settle how it should be tuned.
2. **Is 12.4′ still right in bold?** This was already queued under § The label's
   type sizes and is now answerable: the ladder was read in regular weight, and
   stroke weight matters disproportionately where contrast rather than resolution
   is the limit. If bold reaches the same comfort a step down, that size is room
   the fill model can spend on content.
3. **Is the italic title legible, or merely different?** Italic at the 8.8′ floor
   on e-paper is the least certain thing here — it is a convention borrowed from
   museum practice, where labels are read at 18 inches and not at 7 feet. A title
   that is harder to read than its upright form is a reason to drop the
   convention, and nothing but the panel can say so.

**The consequence this entry warned about has been answered — read it with the
entry below.** Capitals are wider than the letters they replace, so on the
reference wall's fully-populated Hokusai record the identification line went from
262 px to 393 px and the medium dropped. **13B-4's name ladder landed 2026-08-13
and gave it back**: the same record now sets `KATSUSHIKA` on a line of its own
and `Hokusai, Japanese, 1760–1849` beneath it, 269 px for the pair, with the
medium back on the panel. So what you will be looking at is the *two-line*
arrangement, not the three-row one described above — which also changes what
question 1 is asking, since the bold no longer has to disambiguate a comma that
is on a different line from the name.

### The Theme screen, and the reorder that had never worked — added 2026-08-12

**Chunk 09.** Run `cd arrt && uv run python -m arrt` and open Themes.

1. **The ↓ button now does something, and until this chunk it never had.** The
   service wrote the requested number into the position column and stopped;
   `list_memberships` breaks a tie on `added_at`, so a work sent from 0 to 1 tied
   with its neighbour and sorted ahead again as the older row. Moving *up* worked,
   on both surfaces, for as long as reordering has existed. Worth doing a few
   moves in both directions and trusting your eyes rather than the fact that it is
   now tested.
2. **Adding a work now places it at the end, and that is your ruling from this
   session (#132).** A position is an index everywhere — on an add as much as on
   a move — and "unplaced" is no longer reachable from anything you can click. It
   survives as something an agent can ask for on a reorder. If a theme ever wants
   a "no opinion" pile again, this is the decision that removed it.
3. **A theme hanging on any wall cannot be deleted, and the refusal names the
   rooms.** Hang one in two rooms and try. The sentence is the server's own — the
   screen predicts nothing — so judge it as a sentence: does it tell you what to
   do next, or only what went wrong?
4. **Rename, Delete and the name field carry accessible names saying which
   theme.** Invisible unless you use a screen reader; the visible words are
   unchanged. Mentioned because it changed `accessibility-spec.md`'s rule from
   *icon-only controls* to *controls whose visible words repeat across sibling
   panels*, which is my reading of what the rule was for and is challengeable.
5. **Each theme states its member count**, which the IA has always asked for and
   the screen never showed. Check it does not read as clutter above the table
   that already numbers the rows.
6. **"Take down from {wall}" asks no question, deliberately.** Flow 6 makes
   *activation* the confirmed act; a take-down rewrites no manifest, the room goes
   on showing what it was showing, and the undo is the hang button reappearing in
   its place. That is a judgement call nobody has reviewed.

**Visual change: yes.**

### Taste, and the delete that detaches instead of cascading — added 2026-08-12

**Chunk 11.** Run `cd arrt && uv run python -m arrt` and open Taste.

1. **Reactions on a conversation sample are keyed on the artist, not the
   picture.** The three controls sit under each sample, but an affinity is one row
   per (kind, value) — so reacting to one Kandinsky and then to another writes the
   same row, and the second overwrites the first. Built as specified. **If you
   want per-picture judgments, say so: the data model changes, not the screen.**
2. **"Tell me more" is cool *and* still open**, which is the pair the whole
   two-field design exists for. Check that the three controls read as three
   distinct things rather than as a warmth slider with gaps.
3. **A stronger provenance is not overwritten by a weaker one** — `stated` beats
   `observed` beats `inferred`, equal ranks permitted so a re-inference can correct
   an inference. *That ranking is the builder's ruling, not an artifact's, and they
   flagged it as the thing most worth challenging.* The visible effect: something
   you said yourself cannot be silently replaced by something a model inferred.
4. **Deleting a conversation detaches rather than cascades**, per your #118
   ruling. The affinities it produced survive with their rationale and lose only
   the citation; the spend stays on the books. The confirmation names what is lost
   in those terms rather than reporting a row count — judge whether it does.

**Visual change: yes.**

### The Walls screen, and the Work screen's archive — added 2026-08-12

**Two screens rebuilt, and the first confirmation dialog the product has ever
had.** Run `cd arrt && uv run python -m arrt` and open The Walls.

**Specific things worth an opinion, each a judgement call made while building:**

1. **`--text-3xl` (2.25rem/36px) went to the screen's own `h2` — "The Walls" —
   and not to a wall's name.** `design-direction.md` reserved the token for "the
   Walls screen's single large heading" without saying which heading, and that
   sits in tension with the Information Hierarchy row making *which wall*
   secondary to the artwork. So the page title is the large thing and the walls
   below it are not. The other reading — each wall's name set large, the screen
   title small — is a different product and is one line to try.
2. **The confirmation is a modal `<dialog>`**, and it is the pattern every
   consequential act will now use. Focus lands on **Cancel**, a click on the
   backdrop dismisses nothing, and `Escape` cancels. It names the wall even
   though you have one: "Hang Winter in the living room?" That is deliberate and
   it will read as over-explaining until there are two walls.
3. **The Walls screen does not poll.** Nothing repaints behind you. The masthead
   indicator is what carries liveness. If a wall feels stale, that is why.
4. **Archive and Restore are styled as ordinary controls, not as danger.** The
   argument is that archiving is cheap and reversible and dressing it as
   destructive makes a curator hesitate over nothing. Check whether it now reads
   as *too* quiet for an act that takes a picture off the wall.
5. **The archive confirmation names which walls lose the picture**, computed from
   each wall's real manifest rather than predicted — and it says the room "loses
   it at the next manifest build", which is the honest sentence. ~~**Worth your
   ruling:** archiving does not itself republish.~~ **RULED 2026-08-12: the
   picture may stay up, provided a path exists to force a rebuild.** It does, and
   it is re-hanging a wall's current theme — `activate_theme` syncs
   unconditionally and the Walls picker lists the theme already up, so hanging
   what is hanging republishes. The catalogue still does not drive the display.
   **What changed as a result, and is what to look at:** both confirmations now
   name the remedy as well as the timing — "Re-hanging a wall's current theme
   builds one" — because a curator told only *when* holds a fact they cannot act
   on. Judge whether that reads as helpful or as a second sentence in a dialog
   that was already long. See `information-architecture.md` § the archive
   correction.
6. **A work's facets are listed with the rare `sourced` ones marked by a tick**,
   under one footnote saying everything else is inferred. `artist` appears both
   as its own fact row above and in the facet list, which duplicates it — the
   alternative was a filtering rule no artifact states, which would silently drop
   a sourced artist's provenance.

### Three destinations, and the whole client rebuilt as modules — added 2026-08-12

**The largest visual change since the surface was built, and none of it is a
thing a test can approve.** Five pipeline-stage tabs became three destinations —
**The Walls · Collection · Discover** — with Health demoted out of the navigation
into a masthead indicator, and Review and Theme becoming contextual screens you
open from somewhere and come back to. The product now opens on **The Walls**
rather than on Works: the thing it exists to produce was the fourth item, behind
three tabs about producing it.

The browser suite holds what a test can hold — the navigation is those three and
no more, every screen has a URL, a Work opened from Collection returns to
Collection, the indicator announces a degraded state without colour being the sole
carrier. **What it cannot hold is whether the reshape reads as one product**, and
that is the question.

```sh
cd arrt && uv run python -m arrt
```

**Four things worth an opinion, each a judgement call the plan did not settle:**

1. **Landing on The Walls.** It is the strongest claim this reshape makes about
   what the product is for. If the first thing you want on opening is the
   collection, that is worth saying now rather than after four more screens are
   built on top of it.
2. **The masthead status indicator.** It replaced a tab, and the demotion is only
   safe because the indicator speaks — it names *which wall* has gone quiet rather
   than reporting that a wall has. It is also the first consumer of the
   `--good`/`--warn`/`--crit` tokens the palette entry above flagged as the
   least-proven values in the scheme. This is the look they were waiting for.
3. **The persistent search box is a stopgap and is written as one.** It navigates
   to Collection and filters title and artist over what that screen already
   fetched. Real search — `q` against the catalogue, with facet counts — landed in
   the same wave but the two chunks could not see each other; wiring the box to it
   is the next screen chunk's. A dead control would have taught you the collection
   cannot be searched, which is worse than a partial one.
4. **Contextual screens and browser Back.** A Work opened from the Walls returns
   to the Walls, one opened from Collection returns to Collection, and the address
   bar carries `?from=` only when it differs from the default. Try Back and
   Forward, and try copying a URL into a fresh tab — that second one is what the
   addressability criterion is actually for.

**Not a visual question but worth knowing while you look:** `app.js` was 2,033
lines and is now 16 modules — `app.js` boots and holds the route table, `core/`
holds the plumbing, `screens/` holds one module per screen, and no module under
`screens/` may import another. That split is what lets the next two waves build
four screens at once. The move was mechanical by design: the review grid's
1,150-line browser test passes byte-for-byte across it.

### The revised palette, now that it is in the stylesheet — added 2026-08-12

**Every pair passes AA in both schemes and that settles nothing you care about.**
The contrast test computes ratios; it cannot tell you whether the surface looks like
a gallery or like a beige office. `build-plan-curation-ux.md` Chunk 03 says as much
in one line — "a palette is the one thing a contrast test cannot approve on its own;
the question is whether it looks like a museum" — and that question is yours.

The light scheme is warm off-white with a near-black brown accent; the dark is a
warm near-black with an old-gold accent. Both were designed in the committed
prototype and had lived only there, hand-checked and ungoverned, since 2026-08-11.
Nothing was adjusted on the way in: every value is the prototype's.

Look at both, since the browser's own setting picks and there is no in-app toggle:

```sh
cd arrt && uv run python -m arrt
```

Open the prototype beside it — it is the reference for what this was supposed to
feel like, and it carries a 2,000-work corpus where the real collection is 41:

```
.prawduct/artifacts/prototypes/curation-ia-prototype.html
```

**Three things worth an opinion, because each is a judgement a test cannot make:**

1. **The accent in each scheme.** Light uses a near-black brown; dark uses an old
   gold. They are not the same hue rotated — the dark scheme's accent is doing more
   work, because a warm near-black surface gives it more room. Whether they read as
   one product in two lights is exactly the thing only a person can say.
2. **The status trio and its quiet backgrounds.** `--good`, `--warn`, `--crit` and
   their `-quiet` variants are new; nothing consumes them yet. They arrive for the
   masthead health indicator, which is the control that makes demoting Health from a
   tab to an indicator safe. They were verified against every surface by hand rather
   than by the test, because no rule references them — so they are the least-proven
   values here and the most worth a look once the indicator exists.
3. **The scrim.** A translucent black at 62% in light and 70% in dark, carrying
   `--scrim-text` over whatever image sits behind it. Worst case measured 4.96:1 in
   light. That clears AA over the extremes tested, but a scrim sits over *pictures*,
   and a painting is not a grey card.
4. **The error callout's marker, which is the one rule that changed rather than
   just its values.** It drew its left border from the accent, which worked while the
   accent was blue and body text was not. The revised palette is warm throughout, so
   that marker became a hairline in the text's own family — 1.05:1 against body text.
   It now draws from `--crit` instead, which is what that token is for and what the
   palette's own comment says status must do. **This is the one place the built
   surface looks different for a reason other than the new colours**, so it is the
   one worth checking reads as a warning rather than as decoration.

**Nothing on your wall changed.** This is the browser surface only; no rendition, no
mat, no manifest, no television.

### The clamped mats, on the seven works that were over the bar — added 2026-08-11

**The numbers are settled; the look is not, and only you can settle it.** Issue
#115 is fixed — the mechanical derivation can no longer produce a mat lighter than
the corpus's own lightest, so the 7 of 40 works that breached the bar are now 0 of
40. What that arithmetic cannot tell you is whether a mat pinned at the ceiling
*reads* well around those particular paintings. `nonfunctional-requirements.md`
§ Output Quality makes that bar explicitly subjective, so this is the same kind of
judgement as the 2026-08-03 corpus entry below.

**Nothing on your wall changed and nothing needs re-rendering.** Every one of the
40 works already carries a recorded mat colour, and existing choices are never
overwritten. This changes what a *newly acquired* work gets when no vision model
is asked — so the seven below are the evidence, not a pending repair.

The seven, with what the derivation used to answer and what a human chose in 2024:

```
  ...And the Home of the Brave   Demuth      human #27285b L* 18.8   was L* 59.5
  Sky above Clouds IV            O'Keeffe    human #2a3a5e L* 24.7   was L* 58.4
  Eggplant and Plums             Demuth      human #342547 L* 18.0   was L* 57.6
  Seascape                                   human #22394b L* 22.9   was L* 51.6
  Corpse and Mirror II           Johns       human #1c1c1c L* 10.3   was L* 50.8
  Kaldor Public Art Project 10   Koons       human #303045 L* 20.7   was L* 50.2
  Lozenge Composition            Mondrian    human #6b6b6b L* 45.2   was L* 61.3
```

Reproduce the measurement, which is free and touches nothing:

```sh
cd arrt && uv run python tools/mat_masters.py ../all.json
```

**The specific question, and it is a real one.** The clamp puts a breaching work
at L\* 45.2 or darker — the corpus's lightest mat, which a human chose *once*, for
the Mondrian. (Darker, not exactly, when the work's own hue is one the panel cannot
show at that lightness: the colour goes down until it can, rather than losing its
hue and becoming a grey.) On the Mondrian 45.2 is arguably right. On the Johns,
whose human answer was L\* 10.3, a mat at 45.2 is still thirty-five points lighter
than the choice it replaces. The clamp fixes "too light to be in the corpus at all"; it
does not make the derivation choose the way you would. **If those read badly, say
so** — the answer is not a lower ceiling (that would be a number fitted to a
feeling) but that the derivation should not be the default where a vision model
can be asked, which is a live decision on #91.

### The announcement reaches both subscribers, at the set — added 2026-08-08

**This is Chunk 13A's Done-when step 0b, and it is the one thing between that
chunk and its `[x]`.** Everything else the chunk owed is built, swept and green.
The step exists because Chunk 12 was the only Foreign-API chunk that shipped
without a `verify-api`, and the seam this bundle touches is the one where getting
it wrong is silent: the television library keeps **one handler per event**, so a
label that subscribed by registering with the library would *replace* the
selection-confirmation handler, and every rotation would then report a wall that
would not move — while the label worked perfectly. The fan-out inside `SamsungTv`
is written against that constraint, read from library source and pinned by unit
tests over the handler. **No set has confirmed it.**

Needs the television awake and in art mode, and the display plane running against
it. Three things to see:

1. **A rotation still completes.** The daemon logs `rotation.selected` and the
   wall changes — that is the confirmation path resolving with a second subscriber
   attached, which is the whole question.
2. **The label follows.** The panel names the work the wall is showing. **In the
   journal that is `label.drawn`, carrying the `work_id` and the `tv_content_id`
   it captioned** — so this step can be checked against a recording rather than
   only by standing there, and the id can be read against the `rotation.selected`
   that preceded it. (With no panel attached, that event plus
   `label_surface_working` in that wall's `display-heartbeat-{wall_id}.json` are
   the proxy — one file per wall since 2026-08-12. Until 2026-08-13 the proxy was
   `label.failed` *absent*, which a daemon that never tried to caption anything
   satisfies just as well as a working one.)
3. **The remote is a curator too — added with the behaviour, 2026-08-08.** In art
   mode, pick a *different* work with the television's own remote, one the active
   theme carries. The label should follow within a poll interval rather than
   waiting for the next rotation. Then pick something from the set's own art store
   that this product never uploaded: the label should go **blank**, not keep the
   previous work's text. A confidently wrong label is worse than a stale one
   because the person in front of the wall cannot tell. **The blank has its own
   journal line — `label.blanked`, carrying the content id nothing could name** —
   so "the panel drew nothing on purpose" can be told apart from "the panel is
   broken" without opening the case.

`samsung-tv-state-findings.md` is the record — it currently says in its own words
that this is not verified against the set, and that sentence is what this entry
retires.

### The label's type sizes, at the panel — added 2026-08-07

**Status: answered 2026-08-11, and by a different route than this entry
anticipated.** It was written expecting somebody to judge three pixel values at
the panel. What happened instead is that the operator supplied the two physical
facts nobody had written down — a 6-inch panel read from 7 feet — and those made
the sizes *computable*. The judgement that remains is one calibrated angle
(12.4 arcminutes of cap height, read off a six-rung ladder at the viewing
position), and 13B-1 derives everything else from it. The provisional constants
this entry pointed at no longer exist.

**The trap it was written to avoid was real, and worse than it looked.** The
provisional `BODY_SIZE_PX = 26` gave a 2.5 arcminute cap at 7 feet against the 5
that 20/20 vision needs to resolve a letter at all — so the label was not merely
small, it was below the threshold of legibility, and had passed a hardware probe,
a review and a cutover in that state. Nothing could have caught it, because
nothing anywhere converted a pixel into the angle a person sees. That conversion
now exists, and `postarr/tests/test_type_floor.py` asserts in arcminutes.

**What is still worth a look at the panel, and it is smaller than this entry
was.** Whether 12.4′ is right in *bold* — the ladder was read in regular weight,
and stroke weight matters disproportionately on a reflective panel where contrast
rather than resolution is the limit, so the family name may reach the same comfort
a size step down. Worth measuring before spending the panel's budget on size that
weight could have bought.

```sh
cd postarr && uv sync --group raster            # once; the Pi, CI and this Mac all take it
cd postarr && uv run --group raster python tools/label_preview.py /tmp/label.png --cap-arcmin 11
```

The tool now prints arcminutes beside every pixel size, and says what the drop
rule took off — the half that is invisible in the image.

**One observation from the derived render** (1448×1072, the margin deriving to 65,
a fully populated Hokusai record): the identification block fills the panel and
**the medium and the dimensions drop**. That is the expected finding rather than a
regression — it is what the tombstone collapse in 13B-3 exists to reclaim, and it
is why the operator put 13B-3 ahead of 13B-2 in the build order.

### What 13B-3 changed on the panel, and the two things to look for — added 2026-08-11

**Run the preview before the daemon.** The label reorganised, so the next render
looks different in three ways at once and it is worth separating them by eye
rather than in a photograph of a rotating wall:

```sh
cd postarr && uv run --group raster python tools/label_preview.py /tmp/label.png
```

1. **The artist now leads and the title follows it.** Deliberate — the family
   name is what a passer-by scans at 7 feet, and a long title was consuming over
   half the panel. Not a regression.
2. **Name, nationality and dates are one line** where they were three. This is
   the ~260 px the collapse was for. Modelled against two real works it turns
   three dropped lines into one — but that was an arithmetic stand-in for the
   measurer, not Pango, so **the panel is what settles whether it is enough**.
3. ~~**The whole identification line is set at the primary 12.4′ tier**, because
   the layout sizes by position and that line is now first. On a long name it
   wraps to three rows and eats roughly 90 px the floor would not have.~~
   **Superseded 2026-08-13 by 13B-4 — do not go looking for this.** The name
   ladder now gives a long family name its own line at 12.4′ and sets the rest of
   the tombstone beneath it at the floor, so the three-row block this describes is
   not what the panel shows any more. What you will see on the reference record is
   `KATSUSHIKA` over `Hokusai, Japanese, 1760–1849`. Left struck through rather
   than deleted because the ~90 px figure is what the ladder was built to answer,
   and the entry below it is where the current question is asked.

**The thing to judge, and it is a real question rather than a formality:** the
identification line reads `O'KEEFFE, Georgia, American, 1887–1986` — four
comma-separated parts, where the first comma means "inverted" and the others mean
"and". The argument for it holding together is that **weight** separates the
family name from the rest, not punctuation. **13B-2 landed 2026-08-13, so the
bold capitals are there now** — which turns this from a question you could not
answer into the one this entry is really for, and it is asked in its own words
under § The styled name, at the panel. Judge it there; if it reads badly *with*
the bold capitals in place, the fallback is the name on its own line, which costs
about half the collapse's gain.

*(This paragraph said "13B-2 has not landed, so nothing is bold yet — what you
will see is four undifferentiated parts", which was true when it was written and
would have sent you looking for the wrong thing.)*

**Also worth a glance, and it is data rather than type:** two of the 31 seeded
artists carry something that is not a demonym in the nationality slot — Moche
reads `Moche, North coast, Peru` and Kandinsky's is a birthplace clause. Left as
the institution published them; correcting them is a curation-content call, and
this entry is where it is being put to you.

### The display daemon against the wall — added 2026-08-06

**Status: answered on 2026-08-07 — all three acceptance criteria met on the real
set, and the pass found a defect on the way.** Three unattended rotations at the
manifest's 180 s (Calder → Hokusai → Klee; intervals 182 s and 181 s), each
matching what the operator saw with their own eyes; the third with the curation
plane stopped; then a restart that re-showed the same picture without moving the
wall and carried on to the next work. Items 1, 3, 4 and 5 below are settled.

**What the pass found, because it is the reason this entry was worth keeping
open.** The confirming read shipped the day before was wrong in the direction
that stops the wall: `get_current` describes the art-store slot, not the display,
so every real rotation read as a failure and the wall parked on one picture.
Confirmation is now the set's own `image_selected` announcement. The read had
been verified against a *dark* set, where it agrees with the failure because it
never changes at all — which is why one state's worth of evidence proved nothing.

**Still owed here:** item 2 (`next` / `show_now` latency, which needs the curation
plane up), item 6 (brightness across a dusk), and item 9 (whether the five-minute
recovery ceiling reads as broken in the room).

**The television has to be in art mode, and what makes that hard to see is that
almost everything works without it.** This paragraph previously said that a set
in standby refuses the handshake and answers `ms.channel.timeOut`. **That is
wrong, and it was measured wrong on 2026-08-07**: with the set dark and reporting
`PowerState: standby`, both websocket channels opened, and uploads, deletions,
listings, brightness and the whole of `available()` worked. The daemon ran a full
pass against it — disabling the native slideshow, removing 41 orphans, uploading a
work — and the only thing that failed was the picture changing.

**So `PowerState` tells you whether the panel is lit and nothing more** — it
reads `on` for art mode and for somebody watching a channel alike. **`get_artmode`
is the discriminator**, answering `on` only in art mode, and the daemon now gates
every selection on it. The full map is `artifacts/samsung-tv-state-findings.md`;
read it before concluding anything is broken.

The consequence for whoever runs this: the set cannot be woken over the API
(`set_artmode('on')` returns cleanly and does nothing, and Wake-on-LAN to the
advertised MAC has no effect), so **someone has to be at the set** to put it into
art mode. `PowerState` is still worth reading first, as the cheapest thing that
distinguishes a dark panel from a lit one:

```sh
curl -s http://<TV_ADDRESS>:8001/api/v2/ | python3 -m json.tool | grep PowerState
```

**What remains here is the daemon itself.** The pin bump this entry used to ask
for first — the 2026-08-06 security work moving `aiohttp` 3.9.5 → 3.14.3 under
the television client, backed until then only by a call-site check in a clean
interpreter and a sibling lockfile resolving the same fork commit — **ran against
the set on 2026-08-06 and passed 9 checks, 0 failed**, on `aiohttp` 3.14.3,
`websockets` 16.1.1, `requests` 2.34.2 and the pinned fork. That is a measurement
on the hardware rather than a resolver argument, and it is recorded with its
numbers under the 2026-08-01 entry below. Rollback for the pins remains
`deploy/pi-freeze-2024.txt`.

```sh
cd postarr && uv run python -m postarr
```

**What to watch for, each being a behaviour chosen against a plausible
alternative:**

1. **The wall rotates the active theme**, and the first picture appears in
   seconds rather than minutes — uploads are carried one per pass precisely so
   the wall is not blank while forty works go up.
2. **`next` and `show_now` land within about a second.** That is the poll
   interval's whole justification; if it feels slow, the number is wrong.
3. **A restart neither moves the wall nor loses its place.** Stop the process and
   start it: the same picture should still be there, and the *next* rotation
   should go to the work after it. This one was got wrong in the first
   implementation and is the most likely to be got wrong again.
4. **Killing curation changes nothing.** Stop the curation plane and leave the
   wall alone for a few rotations.
5. **The legacy uploads are gone from the set**, and the works the manifest names
   are the only things in the user-upload category. A fresh binding table treats
   everything already on the television as an orphan — that is intended, and it
   is the one step that is not reversible from here.
6. **Brightness follows the sun.** Worth looking at across a dusk rather than at
   one instant; the curve is ported from the 2024 plane and should not read as a
   change to anyone living with it.

**These three need a person at the set**, which is the whole reason this entry
cannot be closed from a desk:

7. **A rotation the set performs is confirmed against the set's own word.**
   *Settled 2026-08-07.* The daemon waits for the television's `image_selected`
   announcement — which names the image and carries `is_shown` — before claiming
   to have shown anything, and every rotation of that pass matched what the
   operator could see. The earlier read this entry described, `get_current`, was
   removed: it reports the art-store slot rather than the wall, so it denied real
   rotations and parked the wall on one picture.
8. **Then switch the set off and leave the daemon running.** Expect exactly one
   INFO — `the television is not in art mode; leaving the wall alone until it is`
   — and then silence, not a line per interval. A set that is off is never asked
   to select at all now: selecting on a lit set that is showing a *programme*
   switches it into art mode and takes the screen off whoever is watching, so
   nothing reaches the wall unless `get_artmode` says art mode is on.
9. **Switch it back on, and time how long the wall takes to come back.** Expect
   one `the television is changing what it displays again`, and the wall to
   resume **on the work it was deferred at**, not somewhere further along the
   theme. **Expected to be about a second, and that is the thing to check.** The
   backoff ladder still runs to 300 s, but the set *announces* its own art-mode
   transitions and that announcement clears the wait — so switching the panel on
   should bring the wall back on the next poll rather than after a wait that has
   doubled its way up. If it instead takes minutes, the announcement is not
   arriving and the ladder is doing the work: say so, because the fix is then a
   different one from lowering the ceiling.

`artifacts/samsung-tv-state-findings.md` is the map of which call works in which
state, and carries its own list of what is still unmeasured — what
`select_image` does to somebody watching television, whether `KEY_POWER` lights
the panel, and how many art-channel clients the set allows at once. If you are at
the set anyway, those are cheap to settle and nothing else can settle them.

### The review half — the grid, its alternates, the panel — added 2026-08-05

**What to look at.** The review grid reached from a finished run ("Review these
works"), the alternates behind a card, and the Health tab. This is the screen a
curator spends their session in, and the tests hold that every figure on it is
right; what they cannot hold is whether judging thirty paintings on it is
pleasant or a chore.

**Free to look at if a run already exists**, which it will if you looked at the
run half. Nothing on this screen spends — accepting, rejecting and choosing a
scan are all local — with one exception named on the screen itself: "Look again
for these" starts a re-search, which reaches the museums but costs nothing (corrected
2026-10-02: the screen said "it spends" until `build-plan-after-review.md` Chunk 05b).

```sh
cd arrt
uv run python -m arrt
# then open the CURATION_PORT from .env — http://127.0.0.1:8770/ as shipped
# → Discovery → open a finished run → "Review these works"
```

**Specific things worth an opinion, because each was a judgement call:**

1. **The alternates are a disclosure on the card, not a screen of their own.**
   The choice is between the picture on the card and the ones behind it, and a
   curator who had to navigate away would be choosing from memory. The cost is
   that opening one pushes every card below it down the page. A side panel or a
   modal would trade differently.
2. **A "Why (optional)" field on every card.** It is what makes a rejection say
   *why* — a studio copy rather than merely "no" — and it is also a text input on
   thirty cards, which is a lot of furniture. It could be revealed only when
   Reject is pressed, at the cost of a second click on the commonest path.
3. **A work whose every scan is below the floor still shows a picture**, with a
   note saying accepting will be refused until a scan is chosen. The alternative
   — hiding it — is the one thing the contract forbids, but the note is doing
   real work and it may not be doing enough of it.
4. **The health panel prints the display plane's reported document as raw
   key/value rows.** Nothing writes one yet, so today it is invisible; it will
   read machine-ish when Chunk 13 lands. Deliberate — only `reported_at` is
   contract, so naming the other fields here would invent a second one — but if
   it reads badly in practice that is worth knowing before the writer exists.
5. **Backup age says "No backup has recorded itself here"**, permanently, until
   Chunk 20. It is a true observation and the panel's whole contract is stating
   those. Say if it reads as a defect rather than as a fact.

**The operator walked this on 2026-08-05.** Against a corpus of 40 accepted works
— all rendered for the first time that day — and the 19-work Dali run. Findings
below; each was checked against the code or the catalogue before being written
down, and which ones are defects rather than preferences is stated rather than
left to the reader.

*On the five questions above:* only **#5** was answered — the backup line reads as
a fact, not a defect, and stays. #4 was not reachable (nothing writes a heartbeat
yet, so the panel shows the absence sentence rather than the key/value rows the
question is about); re-ask it when Chunk 13 lands. #1 was answered *against* the
current design, by #C below. #2 and #3 went unremarked.

**Confirmed defects — verified, not merely reported:**

- **A. `Other scans (N)` counts the scan already on the card.** The disclosure is
  labelled from `instances_held`, which is every instance the work holds
  *including the one pictured above it*. Every work in the Dali run holds exactly
  one, so nineteen cards invite a curator to open "Other scans (1)" and find
  nothing they had not already seen. The operator guessed this from the screen and
  the catalogue confirms it: one instance per work, and it is the selected one.
  Either the count drops the shown instance or the label stops saying "other" —
  and the two are not equivalent, because a curator uses the number to decide
  whether opening it is worth the scroll.

- **B. Seven `proposed_title` values are corrupted, and it is the data, not the
  rendering.** They end mid-citation on a dangling open parenthesis — *"The
  Persistence of Memory (1931) - cited from blog.artsper.com ("*.

  **Fixed 2026-08-05, and the cause was ours rather than the model's.** This
  entry first read "nothing in this codebase truncates a title, so phase 1's
  model emitted them this way", which was wrong: `clean_name` did it. The model
  wrote an ordinary bare citation — `- cited from blog.artsper.com
  (https://blog.artsper.com/en/a-closer-look/dali/)` — and the rule that strips a
  URL was greedy to the next space, so it ate the bracket that *closed* the
  citation and left the one that opened it. Feeding that exact string to
  `clean_name` reproduced the stored value character for character. The
  hypothesis was checkable in one command and was not checked before it was
  written down.

  **The visible half was the smaller half.** `work_dedup_key` is derived from the
  same cleaned title, so each of the seven keyed as a different painting from the
  same work proposed cleanly — a rejection would not have suppressed the work it
  was about, silently, which is the failure a curator cannot see. Both halves are
  repaired at startup and both are pinned by tests.

**Requirements the walkthrough surfaced — none of them designed here:**

- **C. The alternates disclosure is unusable in a grid column.** This answers
  question #1 above with a failure rather than an opinion: expanding "other scans"
  crams the alternates into the narrow column the card occupies. The disclosure
  shape is the problem, not its contents.

- **D. An accepted work should be pictured as it will hang** — the composed
  render, mat and mat colour included, rather than the bare image. The preview a
  curator judges by should be the thing the television shows.

- **E. Mat colour has no control on any human surface.** `set_mat` and
  `choose_mat` exist as services and as MCP tools, so an agent can do what a
  curator cannot. What is asked for is re-running the AI choice, plus one-press
  black and one-press off-white — the two neutrals a curator reaches for without
  wanting a judgement made about them.

- **F. The run table should show a thumbnail where it says "has an image".** *(Open — issue #92, re-scoped S -> M on 2026-08-06; the run view's rows carry no instance reference, so the thumbnail needs a payload decision. The words it quotes now read "the run found an image", per issue #99.)* On
  the run detail view the Image column renders the words `has an image`; the
  review grid beside it shows the picture. A curator scanning a run is asking
  *which* image, and the answer is already on disk.

- **G. "Where it came from" is not understood.** *(Resolved 2026-08-06, issue
  #93.)* It headed the run table's provenance column and meant *how this row
  entered the run* — asked for by the model, or offered by the collection on top.
  In an art catalogue that phrase reads as the work's own provenance, which
  museum holds it.

  **The column is gone rather than renamed**, which is a correction to the
  sentence above: it was *not* "doing necessary work" on that screen. The
  offered/asked-for distinction is necessary, and this table was its fourth
  statement — after the tally's separate counts, the run sentence, and the line
  directly above the rows. What the per-row badge added was which *particular*
  work was offered, on a screen where nothing is decided per work. The badge
  stays on the review card, where the deciding happens.

- **H. A per-work preview of the e-paper card** would be welcome once that card
  exists. Depends on Chunk 13; recorded here so it is not rediscovered.

- **I. The offered-work sentence contradicted the screen it was printed on.**
  *(Fixed 2026-08-10 — see the annotation at the end of this entry. What follows
  is the observation as it was recorded on 2026-08-05, in the tense it was found
  in, because it is the evidence rather than a description of the product.)*

  Every offered card read *"…an artist this run named but could not confirm a work
  for"*, while seven works the run named for that same artist sat on the same
  page. The Dali run holds 7 `proposed` and 12 `offered`; the seven are real
  proposals — *The Persistence of Memory*, *Lobster Telephone*, *Metamorphosis of
  Narcissus* and four more — and each is badged `not held`. So the sentence is
  true only under a narrow reading of *confirm* ("resolved to a work the
  collection holds"), and nothing on the screen teaches that reading. The
  operator's objection was that the works say "Salvador Dalí" right underneath;
  the sharper version is that the run demonstrably *did* name works for the
  artist, and the sentence appears to deny it.

  `_offer_rationale`'s docstring anticipates the near miss — it notes the artist
  named is the run's spelling while the work carries the collection's own
  attribution — so the collision was seen from the writing end and judged
  survivable. Seen from the reading end, on a page carrying both halves at once,
  it is not.

  **A second unexplained number sits beside it.** The sentence says *"one of 25
  works it holds"* and twelve cards appear, because `offered_works_per_run` caps
  the offer at twelve. Each number is honest alone; together, and split across
  two views, they invite a curator to go looking for thirteen missing works. Any
  rewording should carry the cap or drop the total.

  Repetition compounds all of it: this is one identical 30-word sentence printed
  twelve times down a single page, carrying per-*group* information on a per-card
  line.

  **FIXED 2026-08-10 by issue #95 — and the fix is not visible on an old run.**
  The paragraphs above are kept in the past tense they were written in, as the
  record of what was seen; `_offer_rationale`, the function they reason from, no
  longer exists. Offered works now store the query that produced them
  (`offered_for_artist`, `offered_artist_matched`) and the review grid says it
  once above that query's works, reconciled against what the run offered.

  **To verify, start a fresh run — do not reopen the 2026-08-05 Dali run.** Rows
  written before this change keep their old sentence in `rationale` and carry no
  query, so that run renders the old wording and collapses into a single unnamed
  group: the defect, apparently unchanged. There is no backfill, by the operator's
  decision of 2026-08-10 that old runs need not be preserved and the database may
  be zeroed. What to look for on a new run: the denial gone (the page says the run
  found no *image* for the works it named), one sentence per artist rather than one
  per card, and the holdings total reconciled with what the run offered.

  **A fourth check, and it is the one here that needs eyes rather than a test.**
  (Not "no test can make": the *scoping* half — that a card title inside a group
  is styled the same as one outside it — is arithmetic, and a browser test now
  compares the computed margins. What follows is the judgement half, which is
  yours.) Each artist's
  offers sit in their own block with a heading above them — look at whether the
  groups are visually separated from the works the run named and from each other,
  and whether the heading reads as a heading rather than as browser-default bold.
  The browser suite asserts the heading's *text* and the group's attributes, and
  both are correct whether or not a single line of that block's styling exists;
  this bundle shipped with none of it until a reviewer read the page as a page.

## Decisions taken during the 2026-08-05 walkthrough

**The mat policy, settled with the operator against the corpus rather than in the
abstract.** Recorded here because it changes what item **E** above asks for, and a
reader finding E alone would build the wrong thing.

- **Every work always has a mat**, and the non-AI default is the **existing
  dominant-colour derivation** (Pillow median-cut), not off-white. Off-white was
  the operator's opening proposal and was withdrawn on evidence: the 41 hand-tuned
  2024 mats run L\* 6.7–45.2 with a median of 20.7, `nonfunctional-requirements.md`
  § Output Quality makes that corpus the regression bar, and
  `test_mat_corpus.py`'s `CORPUS_MAX_LIGHTNESS = 50.0` enforces it. The named
  failure mode — a pale work competing with a lighter mat — is the reason the bar
  exists. The mechanical fallback is free, deterministic, already built, and lands
  in the region the corpus occupies.

  **The last clause was measured on 2026-08-10 and is false** — see the amendment
  below. Kept in place rather than edited, because it is the belief the decision
  was taken on, and a reader who finds only a corrected sentence cannot tell that
  the premise was ever checked. The decision itself survives; its precondition
  does not.
- **Black and off-white become presets a curator presses**, so choosing one is a
  judgement someone made rather than something applied silently to forty works.
  **Superseded 2026-08-10 — see the amendment below:** the values are `#222222`
  and `#6b6b6b`, off-white is withdrawn a second time and pure black was never in
  the corpus. Marked inline because this bullet reads as an instruction to build.
- **The AI becomes an opt-in button that offers several candidate colours** shown
  against the work, with nothing applied until the curator picks one. The current
  choice stays current until then. This makes the spend buy options rather than a
  fait accompli, and it is the control that must say on itself that it spends.
- **Existing mats are never overwritten** — already true today and not a change:
  `prepare(force=True)` re-renders without re-choosing, and `mat_colors` keeps
  every choice with one marked current.
- **Consequence to retire deliberately:** a guaranteed default means the
  `NO_MAT_COLOR` exclusion can never fire again, so that branch and its reason
  become dead and should be removed rather than left looking live.

## Decisions taken 2026-08-10, on measurement rather than at a walkthrough

**These amend the 2026-08-05 mat policy above and close the discovery items #90
and #91 were filed to open.** They came out of measuring the claims the earlier
session recorded, against the operator's own `ART_ROOT` — which is why they are
dated separately rather than folded into the walkthrough that could not have
known them.

- **The mechanical derivation is fixed before it is promoted to the default.**
  Paired against the hand-tuned mat for the same painting it is lighter on 31 of
  40 works (median +15.2 L\*) and breaches `CORPUS_MAX_LIGHTNESS` on 7, where the
  human breached it on none — full figures in `nonfunctional-requirements.md`
  § Output Quality. Two changes, both measured: **clamp** the derived lightness to
  the corpus ceiling (takes 7/40 over the bar to 0), and **merge perceptually
  identical clusters** before taking the largest (takes a re-encode flipping the
  answer from 5/25 works to 2/25 — median-cut splits one perceptual colour across
  clusters and then loses the vote to a smaller rival, which is what puts teal on
  an Albers whose orange covers more of it).
- **The two presets are `#222222` and `#6b6b6b`, and off-white is withdrawn a
  second time.** Both values are the corpus's own; the reasoning is in
  `nonfunctional-requirements.md` § Output Quality, recorded there rather than
  here because it is a standing quality rule and not a meeting outcome.
- **The AI button offers three candidates, each composed against the work**, with
  nothing recorded until one is picked. Swatches were rejected: a mat is judged by
  how it reads *around* a picture, and a 40px square is not that judgement. Three
  rather than five because the tail candidates would not be chosen and five
  composed canvases is a lot of page for one decision.
- **The review grid keeps the bare candidate scan** — finding **D** is answered
  "no" for that surface, deliberately. At review time nothing is acquired and no
  mat exists, so an "as it will hang" preview would have to derive a mat from the
  480px museum preview; measured, that differs visibly from the master's answer on
  5 of 25 works, one of them flipping orange to teal. The judgement the review
  grid exists for is *which painting, and is this scan good enough* — the mat
  judgement belongs on the work detail, after acceptance, where the real composed
  canvas is.
- **Finding D's actual cause is a caching defect, not a missing feature.** The
  works grid and the work detail already ask for the composed canvas, and
  `sourceBadge` already distinguishes it from the master. What breaks is that a
  thumbnail's freshness is tested against the *original*'s hash, and composing a
  canvas does not change the original — so a thumbnail made before the first
  preparation is never regenerated, and the card serves the bare master under a
  badge reading "wall render". That is issue #90 now.

### The run half of the browser surface — added 2026-08-05

**What to look at.** The Discovery tab: entering an intent with the estimate
beside the field, the approval gate, and the run view while a run is working and
after it has finished. The tests hold that every figure is correct; what they
cannot hold is whether the screen makes the decision it is asking for an easy one.

**This look costs money, and here is exactly how much.** A real run spends about
**$0.013** — the phase-1 model call plus its search allowance. Everything except
starting a run is free to look at: the estimate, the run list, and any run
already in the catalogue. If you would rather not spend, the first two are still
worth an opinion and the third can be read against a run from an earlier session.

```sh
cd arrt
uv run python -m arrt
# then open the CURATION_PORT from .env — http://127.0.0.1:8770/ as shipped
# → the Discovery tab
```

Without `OPENROUTER_API_KEY` set, starting a run is refused with a sentence
saying why, which is itself worth seeing once — it is the first thing a fresh
deployment does.

**Specific things worth an opinion, because each was a judgement call:**

1. **The estimate sits above the button, not beside the result.** It reads
   "Asking costs at most $0.01336. One model call plus up to 10 web searches,
   which is the most phase 1 may use. Bounded, not typical." A ceiling rather
   than a typical figure, because a run may use the whole allowance. Two
   opinions wanted: does a bound read as reassuring or as evasive, and are five
   decimal places on a hundredth of a dollar precision or noise? The figure is a
   `Decimal` for good reasons and rendering fewer digits is a display choice
   nothing else depends on.
2. **A second estimate appears at the approval gate**, because that is where the
   phase-2 decision is actually made. It reads "Approving costs $0. Resolving
   the N works this run proposed. Phase 2 asks museum APIs, which are free, and
   identifies works locally — so approving this run spends nothing further. The
   gate is on the work count, not the price." The basis is doing the work there;
   a bare "$0" beside an approve button would invite reading the gate as being
   about money.
3. **Two badges per work: where it came from, and whether it got an image.**
   Offered works — the ones a wired collection volunteered rather than ones the
   model named — carry a 2px dashed border and the word "offered", against the
   plain border and "asked for" of the rest. The whole design rests on a curator
   seeing that difference *without reading*, because accepting an offered work
   believing you asked for it is the failure this labelling exists to prevent.
   Can you? Two badges sit in one cell and this is the densest thing on the
   screen; if it reads as clutter, say so.
4. **An unresolved work's reason is a badge with the sentence in its tooltip.**
   "too small", "wrong artist", "not held". Only "not held" suggests the work may
   not exist. Is the short word enough on its own, or does the distinction that
   matters need to be on the page rather than on hover? A tooltip is invisible on
   a touch screen and to anyone not hunting for it, which is the argument against
   the current choice.
5. **The page polls every two seconds and stops when the run ends.** Watch a run
   from `resolving_works` through to a terminal state. Does it feel live, or does
   it feel like it is doing nothing? Two seconds was chosen against a Pi's
   modesty, not measured against a curator's patience.

   **A test makes this check now, and it is still worth making by hand once.**
   On a run sitting at the approval gate, press Tab until "Approve the list" has
   the focus ring, then take your hands off the keyboard for ten seconds and
   press Enter. It must approve. A repaint on each poll would have thrown the
   focus away silently, so what you are checking is that the page leaves the DOM
   alone when nothing about the run changed. Do the same on a run that *is*
   changing — focus will legitimately move there, and that is the cost of the
   view being live.

   **What covers this, corrected 2026-08-05.** This paragraph used to read "the
   client has no test runner … none of them is executed by a test", and invited
   reopening that trade if the surface kept growing logic of this kind. It did,
   and the trade was reopened and settled: the client is executed by a real
   browser against a real server in `arrt/tests/browser/` (marker `browser`).
   The focus check above, the supersession of an in-flight repaint, and the
   polling are each executed — by `test_a_poll_that_changes_nothing_leaves_the_focus_alone`,
   `test_a_paint_superseded_in_flight_never_reaches_the_page`,
   `test_two_concurrent_paints_leave_only_one_poll_chain` and
   `test_leaving_the_run_view_stops_its_polling`. **The no-build-step decision
   this entry named is untouched** — it governs the *shipped* client, which is
   still one hand-written file served as-is; what landed is a dev and CI harness.

   **So the honest limit has moved rather than gone.** No browser test judges
   whether the screen is legible, whether the layout holds at the window size you
   actually use, whether two badges in one cell read as dense or as clutter, or
   whether the decision this page asks for is an easy one to make. Those are what
   this entry exists to collect, and they are why it is still Pending.
6. **The searches table prints raw ISO timestamps** — `2026-08-05T13:14:25.812…`
   — because that is what the rest of this surface does (the health panel shows
   `reported_at` the same way) and inventing a date format for one table would
   make it the odd one out. It is still the worst-reading thing on the screen,
   and the run list is the one place a curator scans many of them at once. If
   you want them humanised, that is a convention decision for the whole surface
   rather than a fix here, and it is yours to make.
7. **The completed sentence rates over what the model proposed.** "This run
   finished: 1 of 3 works it was asked for have an image", with the offered works
   named in a separate clause. The alternative — one merged count — reads better
   and reports a resolution rate the run never achieved. Confirm the honest
   version is legible enough to keep.

### The mat corpus look — is the new engine at least as good as 2024? — added 2026-08-03

**This is the product's stated quality bar and no test can settle it.**
`nonfunctional-requirements.md` § Output Quality says mat colour must be at least
as good as the 2024 implementation, that the bar is explicitly subjective, and
that an engine scoring well on any metric while producing visibly worse mats on
the 41-work corpus has failed. So the suite holds the one property the corpus
states unambiguously — every one of the 41 is darker than mid-grey — and this
entry holds the rest.

A full run is already done and its numbers are worth having before you look:

- **33 of the 41 compared.** The other eight are held outside the Art Institute
  and the tool only resolves `artic.edu` URLs; it names them at the end rather
  than quietly reporting 33 as the corpus.
- **Median CIEDE2000 distance to the 2024 colour: 9.8** (min 1.0, max 34.9).
- **The central tendency is the same.** New mats have a median LAB lightness of
  20.8 against the corpus's 20.7 — the engine lands in the region 2024 landed in.
- **One of 33 crossed the darkness bar** — a Rothko given `#8a7a6a` (L\* 52.2)
  where 2024 chose `#1c1818`. Two more sit just under it.
- **Zero mechanical fallbacks**, after the output reservation was raised.
- **It cost $0.0024.**

Regenerate the sheet and compare each pair by eye:

```
cd arrt
uv run python tools/mat_corpus.py ../all.json --out /tmp/mat-corpus
open /tmp/mat-corpus/corpus.jpg          # 2024 on the left, the engine on the right
```

**Three specific pairs are worth your attention first**, because they are where
the engine and 2024 most disagree and where I think 2024 may be the better
choice:

1. **Untitled (Purple, White, and Red)** — the one over the bar. `#8a7a6a`
   against 2024's near-black `#1c1818`.
2. **Sky above Clouds IV** — `#4a7c9d` against `#2a3a5e`. The work is pale and
   the lighter mat competes with it; this is the failure mode the bar exists for,
   arriving just *under* the bar at L\* 49.9.
3. **...And the Home of the Brave** — `#4a5d75` against the deep indigo
   `#27285b`. Debatable rather than wrong.

**One thing to know before reading the numbers as a baseline:** the model is not
deterministic. The same work asked twice gives different colours — this work drew
`#27285b`, exactly the 2024 colour, on an earlier run and `#4a5d75` on the full
one. So a corpus run is a sample of the engine's behaviour, not a fixed output,
and a single bad pair is weaker evidence than a pattern across several.

If the verdict is "worse than 2024", the cheapest levers in order: the prompt in
`library/acquisition/mat.py` (`MAT_PROMPT` — its guidance is deliberately carried over
from 2024's, so it is the least likely culprit), then `MAT_MODEL` in `.env`,
which was chosen on cost among models that cleared the bar rather than on taste.
`art_catalogue(action='set_mat_color', ...)` overrides any individual work
permanently, and the previous colour is never discarded.


### A curator can see the candidate images in their own client — added 2026-08-03

**Visual, and it is the one thing this chunk's tests cannot prove.** Chunk 17A
returns candidate thumbnails as MCP image content blocks. The suite asserts the
blocks are present, correctly sized, and correctly correlated to their rows — but
what a *client* does with them is the client's business, and the whole safety
argument (`security-model.md` § Content Appropriateness) rests on the picture
actually being visible at the moment of judgement. A block that every test
accepts and Claude Code renders as a broken box would satisfy the suite and
defeat the gate.

Point a real MCP client at the running plane and look:

```
art_discovery(action='list_runs')                  # take a run_id
art_review(action='list_works', run_id='<that>')   # expect: pictures, inline
art_review(action='list_images', work_id='<one>')  # expect: the alternates
```

What to check with your eyes, beyond "images appeared":

- **The pictures render inline**, not as attachments or placeholders.
- **Each work's picture is its own.** Rows carry `image_block_index`; a client
  that reorders or drops a block would pair the wrong scan with the wrong
  painting, and nothing below the wire can detect that.
- **A work with no local copy still lists**, with `preview_note` saying why —
  rather than vanishing or rendering blank.
- **The size beside each picture is legible and useful.** `renders_at_inches` is
  the number a thumbnail cannot convey, and it is what stops a postage stamp
  reaching the wall; if it reads as noise in a real client, say so — the
  presentation is worth changing.

Verified so far *without* a real client: the plane was booted from its own entry
point against a scratch tree on 2026-08-03 and a real MCP client session returned
1 text + 2 image blocks, each index resolving to a decodable 400x400-box JPEG,
with the below-floor work pictured and marked `is_on_offer: false`.

### The loader unit starts clean with its declared `EnvironmentFile=` — added 2026-08-02

> **DISCHARGED 2026-08-11, by the cutover rather than by running this item.** The
> question this was kept for — does an un-prefixed `EnvironmentFile=` start clean
> on the real machine — is answered, on the units that matter. Both
> `display.service` and `curation.service` declare it un-prefixed against
> `/opt/samsung-frame-art-loader/.env` and both came up clean on the first
> `systemctl enable --now`, curation logging its resolved configuration and
> display its startup line. Neither refused to start, which was the risk.
>
> **The unit named below is not the unit that was tested.** As predicted, the file
> under test became a different one: this item describes the 2024 loader, which is
> retired and will never be installed again. What follows is left as the record of
> a question that was owed and is not any more — do not run it. The properties it
> was written to protect are now asserted mechanically for both live units in
> `tests/test_repo_hygiene.py`, which is the durable form of this check.

**Not visual — this needs the Pi, and it is quick.** The unit now declares
`EnvironmentFile=/home/tvpi/source/samsung-frame-art-loader/.env` un-prefixed and
sets `StartLimitIntervalSec=0` / `RestartSec=10`. Everything about that was
established by reading systemd's documentation; whether *this* unit on *this*
machine starts under it has not been observed, and the un-prefixed directive is
precisely the kind of change that turns a working unit into one that refuses to
start if the path is wrong by a character.

The wall is running now, so do this at a moment when a brief outage is fine:

```sh
sudo cp deploy/samsung-frame-art-loader.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart samsung-frame-art-loader
systemctl status samsung-frame-art-loader          # expect: active (running)
```

**Then prove the guard actually guards**, which is the half that cannot be
checked by reading:

```sh
sudo systemctl stop samsung-frame-art-loader
mv .env .env.parked && sudo systemctl start samsung-frame-art-loader
systemctl status samsung-frame-art-loader          # expect: refuses to start, names the .env path
mv .env.parked .env && sudo systemctl restart samsung-frame-art-loader
```

The second command is expected to fail — that is the pass condition. What to
record is **whether the error names the path**, since "failed to start" without it
would leave the operator no better off than before. Check acceptance box 3 on
issue #43 with the status output pasted in.

**If the path is wrong**, the fix is the `EnvironmentFile=` line, not a rollback:
the checkout's absolute paths are machine-specific and already flagged as such in
`deploy/README.md`.

### The samsungtvws move, against the live television — added 2026-08-01

**Status: the television half is answered; the Pi half is not.** The 2026-08-06
run reached the set and passed, so what the library does against real hardware is
no longer an open question. It ran from a **macOS client against a hand-built
virtualenv holding only the television-path pins** — because nothing in this repo
installs `requirements.txt` on a Mac: that file carries `omni_epd`, `pycairo` and
`PyGObject`, none of which build there, and the root project declares only
`python-dotenv`, so `uv run python tv_api_check.py` fails at `import samsungtvws`.
**So `pip install -r requirements.txt` on the Pi remains unverified**, and that is
the half of this entry still owing. The pins are proven against the television;
they are not proven to install on the machine that will run them.

**Not visual — this one needs the hardware, not your eyes.** The library pin and
`websockets` both moved, and every claim behind the move comes from reading
source. What a television does is a separate question, and this is the only thing
that answers it.

On the Pi, with the set awake:

```sh
pip install -r requirements.txt          # the new pins
python tv_api_check.py --image "$ART_ROOT/ready/<a 4K composite>.jpg"
```

To reproduce the client-only run anywhere else, build the television-path pins
into a throwaway environment rather than reaching for `requirements.txt`:

```sh
uv venv --python 3.12 /tmp/tvcheck && VIRTUAL_ENV=/tmp/tvcheck uv pip install \
  "aiohttp==3.14.3" "async_timeout==4.0.3" "websockets==16.1.1" \
  "requests==2.34.2" "python-dotenv==1.2.2" \
  "samsungtvws @ git+https://github.com/NickWaterton/samsung-tv-ws-api.git@fe95ef1d784cd32f49bf9a07ec479576574eea07"
/tmp/tvcheck/bin/python tv_api_check.py --image "$ART_ROOT/ready/<any real JPEG>.jpg"
```

> **`ready/` is empty on the rebuilt card and the 2024 composites are gone with
> the old one** (2026-08-04), so there is no 4K composite to point this at. Any
> real JPEG the set will accept proves the same thing — this checks what the
> *television* does with an upload, not what the renderer produced. Use a
> bench file, or run it after the first work is prepared.

It uploads one image, watches which callback the set emits, removes that image
and confirms the removal — touching nothing else on the wall — and exits non-zero
if any check fails. Paste its output onto issue #3; the last three acceptance
boxes there are exactly what it measures.

**Four numbers worth recording from the run**, because each is an input to the
display daemon rather than a pass/fail. **Run 2026-08-06 from a macOS client
against the set in art mode: 9 checks, 0 failed.** What it measured:

1. **How long construction blocks: 4.53s**, against the tool's own 15s ceiling.
   It makes a REST call and, on 2024-or-later panels, a token round trip, all
   inside `__init__` — and this set is a 2024 panel, so the token trip is on the
   path. **The daemon cannot construct a client on its event loop**; 4.5 seconds
   of blocking I/O in an async loop stalls every other thing that loop owes,
   including the poll interval the `next`/`show_now` responsiveness depends on.
   A thread or an executor is a design constraint here, not a tuning choice.
2. **Which callback events this set emits: the run could not say, and its output
   looked as though it had.** Three are registered: `slideshow_image_changed`
   and `auto_rotation_image_changed` are the same notion under two spellings, and
   the wrong one fails silently, so both go on; `image_selected` is the
   acknowledgement of the request the script itself made. The report read
   `fired: d2d_service_message`, which **is not one of the three** — it is the
   outer websocket message type the library passes to every art-channel callback,
   whichever sub-event selected it. So what the run establishes is only that **at
   least one of the three fired** within 5s of `select_image`; the check fails
   when none do, and this run had no failures. Which one was unrecoverable from
   the output. *(Second defect fixed in the same pass as the model one below: the
   recorder now captures the trigger it was registered under, so a run names the
   event. This entry originally read the output at face value and concluded that
   nothing fired — a claim its own "0 failed" line contradicted.)*

   **Nothing here disturbs the earlier instrumented finding** that only
   `image_selected` fires, at +2.15s, and that the two rotation spellings are
   slideshow-advance events a host-driven wall never provokes
   (`platform-and-dependency-findings.md`). The next run is what confirms it from
   the tool rather than from a probe.
3. **The reported model and API version: `QN50LS03DAFXZA` (`24_PONTUSM_FTV`),
   API `5.0.1.0`** — the new half of the verb split, so `slideshow_*`. The model
   came from `/api/v2/` by hand, **not from the tool, which reported "model: not
   reported" against a set that names itself perfectly well** — see the defect
   note below.
4. **Upload seconds against file size: 2.2 MB in 3.0s**, first byte to
   acknowledgement, streamed by path. The comparison against the old
   whole-file-in-memory route is the reason the pin moved.

**A defect this run exposed, which is why item 3 above needed a hand check.**
`check_identity` reads the model from `get_device_info()`, but on the async art
client that is the *art channel's* payload — `current_rotation_status`,
`support_brightness_sensor`, `resolution_type` and so on, with **no model and no
`device` key at all**. The `{"device": {"modelName": …}}` shape the code destructures
is what the *REST* endpoint returns. So `model` is always `None`, and the cost is
not the cosmetic note: `panel_check.disagreement(None, …)` returns `None`, so the
**panel size check silently takes its "neither side stated one" branch and passes
without measuring anything**. That check exists because a live deployment ran 42"
against this 50" panel and mis-sized every judgement about whether a work belonged
on the wall — and `.env.example` still ships `TV_PANEL_DIAGONAL_INCHES=42`, so
the misconfiguration it guards against is the one a fresh clone starts in.
Confirmed by hand that the public `SamsungTVAsyncRest.rest_device_info()` returns
the expected shape, and that `disagreement("QN50LS03DAFXZA", 42.0)` produces the
full warning — the guard works; nothing was reaching it.

**Fixed, in two halves, and the second is the one that generalises.** The model
now comes from `samsungtvws.rest.SamsungTVRest.rest_device_info()` — the public
synchronous client for the `/api/v2/` route, which is where that shape lives, at
the configured `TV_PORT` rather than a literal (the library reads the scheme off
the port: `https` on 8002, `http` on 8001, and both serve the route) — and the
note reports `modelName` and the `24_`-prefixed model year
together, since the year is what the token handshake turns on. The second half is
that **`panel_check` now answers two questions instead of one**: `not_compared()`
says whether a comparison was possible, and `disagreement()` says how it came
out. A caller that reads only the second reports a pass for "they agree" and for
"one side said nothing" alike, which is the conflation that let a check comparing
`None` look satisfied. Driven against both captured payloads: fed the art
channel's, the panel line now reads `[note] panel size: not compared — no model
name was read from this television`; fed the REST payload against
`TV_PANEL_DIAGONAL_INCHES=42`, it fails with the full 104.9-against-88.1 warning.
(It says "was read" rather than "the television reported none" on purpose: on the
path where the REST endpoint does not answer, nothing ever asked the set, and the
failing `model` check above the line carries that reason.)

**What that leaves for the next run on the set**, and it is small: the REST read
itself has only been exercised against a captured payload, so the live pass
should confirm the `model` note names the set and the `panel size` line is an
`ok` or a `FAIL` — **never a `not compared`**. A `not compared` from a television
that answered everything else is the same defect wearing its new name, and now it
says so on the line rather than needing a hand check.

**The art channel's payload is worth having anyway**, because two fields bear on
the daemon: `support_brightness_sensor: "TRUE"` (the set has its own sensor,
which the ported sun-following curve is in addition to, not instead of) and
`current_rotation_status: 1`.

> **Picked up 2026-08-07 as issue #107**, after the operator found the wall
> reading bright on an overcast afternoon while the sun curve had it at 8–9 —
> which is exactly the case a solar angle cannot see. `get_artmode_settings`
> reports the sensor is switched **off** (`brightness_sensor_setting: "off"`),
> and the library exposes `set_brightness_sensor_setting`.
>
> **The flag above says a sensor exists; it is not a reading.** Nothing here has
> ever fetched an ambient *value*, which is why the first step is establishing
> whether one can be read at all. If the sensor only drives the set's own
> auto-brightness, the honest answer is to stop writing `set_brightness`
> altogether rather than to blend the two — a different design, not a variant.

**If it fails, the rollback is `deploy/pi-freeze-2024.txt`** and nothing else has
changed on the Pi — the new pins only take effect on an install.

### The first browser surface — added 2026-08-01

**What to look at.** The four sections and a work detail view, over the real
corpus. What matters is the judgement a test cannot make: does the chrome recede
behind the artwork, or compete with it? That is the whole visual constraint, and
it is subjective by nature.

**How to bring it up over the real works, without touching the deployed tree:**

> **Corrected 2026-08-04, and the correction itself expired 2026-08-06.**
>
> The recipe below replaced one that set `ART_ROOT` in the environment, on the
> grounds that **`ART_ROOT` could not be overridden that way**: `config.py`
> called `load_dotenv(override=True)`, and `find_dotenv()` walks up from *that
> module's own file*, so the checkout's `.env` won over the environment no matter
> what was exported. The old recipe seeded the real `ART_ROOT` while printing
> that it had — which reads as success, the first line being the only tell.
> Verified by running it.
>
> **That `override=True` has since been retired**, precisely because discarding
> an exported value in silence is the failure shape this product exists to
> correct. An exported `ART_ROOT` now wins, so the recipe the 2026-08-04 note
> declared impossible would work today. The recipe below is kept anyway: it does
> not depend on which way the precedence runs, which is the property worth having
> in a document somebody follows months later.

```sh
# The masters, read-only behind a symlink, inside the ART_ROOT `.env` names.
# One `rm ~/samsung-art/raw` undoes it; nothing is copied.
ln -sfn ~/art/raw "$(grep '^ART_ROOT=' .env | cut -d= -f2-)/raw"
cd arrt
uv run python -m arrt.seed ../all.json   # re-runnable; fills in what was absent
uv run python -m arrt
# then open the CURATION_PORT from .env — http://127.0.0.1:8770/ as shipped
```

To serve a *second* copy on another port without disturbing the first, change
`CURATION_PORT` in `.env` — for the same reason, it is not settable per command.

`~/art` on the dev Mac holds `raw/` and no `ready/`, so every work will show its
master image and the wall view will report every work as `no_rendition`. **That is
correct, not a fault** — and as of 2026-08-04 it is also permanent for these
works: the Pi was rebuilt and the 2024 renditions were on the old card, so
`ready/` exists nowhere. Re-rendering the corpus is real work, not a missing
symlink. To see a mixed
manifest, give a few works a rendition first; the wall view is the section most
worth seeing with both states in it.

**Specific things worth an opinion, because each was a judgement call:**

1. **Card density and the fixed 4:3 image box.** Works are letterboxed inside it
   rather than cropped to fill, so a tall work leaves large empty margins. The
   alternative — cropping — is the one thing an art tool must not do, but the
   margins are a real cost and a different aspect box would trade differently.
2. **The serif for work titles** against a sans for chrome. Intended as a museum
   label; it may read as fussy at grid size.
3. **The badge row on each card** — fit verdict and image source, plus a third
   on an archived work. Two or three badges is a lot of furniture under a
   picture. They are there because a thumbnail cannot convey resolution, so
   "would show at 15.2 inches" is the number a curator actually judges by, and
   because an archived work that looked identical to a live one would be the kind
   of silence this product exists to refuse.
4. **`no_rendition` and the other reasons appear as the raw domain words**, with
   the sentence beside them. Deliberate: the tool surface returns the same words,
   so a curator and an agent share one vocabulary. It reads slightly machine-y.
5. **Dark and light.** Both are authored; the browser's own setting picks. There
   is no in-app toggle — say if you want one, since an image-review tool arguably
   deserves the ability to pin the surround while judging colour.

**One decision explicitly awaiting a veto** (`nonfunctional-requirements.md` §
The mat is geometric): the mat's bottom margin is now 1.15x the top. The
weighting had only ever been stated as a direction, and a box height cannot be
computed from a direction. 1.15 is the factor that reproduces that artifact's own
42-inch worked example, so it is inference rather than invention — but it is a
subtle weighting, and a more pronounced one is taste, not correctness. It is
`MAT_BOTTOM_WEIGHT` in `.env`, so overruling it is a one-line change.
