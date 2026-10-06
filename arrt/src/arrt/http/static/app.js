/* The browser client: boot, and the table of every screen it can show.
 *
 * No framework and no build step, deliberately: this is one operator's tool on
 * a private network, and the client is small enough that plain modules carry it.
 * A toolchain would be a second thing to pin, update and keep building for no
 * gain a curator can see, and the *arr look this surface follows is a layout,
 * not a library — Sonarr's React frontend is not published as one to adopt. ES
 * modules are the browser's own, so `type="module"` in `index.html` is the whole
 * of the "build".
 *
 * **This file holds boot and the route table and nothing else.** Everything it
 * imports obeys one structural rule, recorded in `architecture.md` § Components
 * & Responsibilities: `core/` is shared and knows no screen; a module under
 * `screens/` may import from `core/` and must never import another screen. The
 * route table below is the one place they meet. That is what lets several
 * screens be built at once — a screen reaching sideways into another rebuilds
 * the single writer this split exists to end.
 *
 * TEXT IS SET WITH textContent, NEVER innerHTML — the rule is stated at
 * `core/render.js`, where the helper that enforces it lives, and it binds every
 * module here.
 */

import { OPTIONAL_ID } from "./core/route.js";
import { install, go, refresh } from "./core/router.js";
import { installSearch, paintSearch } from "./core/search.js";
import { installStatus, paintStatus } from "./core/status.js";
import { paintAwaiting, paintWanted } from "./core/awaiting.js";
import { state } from "./core/state.js";
import { viewHistory, viewQueue, viewToReview, viewWanted } from "./screens/activity.js";
import { viewArtists } from "./screens/artists.js";
import { viewClients } from "./screens/clients.js";
import { viewCollection } from "./screens/collection.js";
import { viewConversation } from "./screens/conversation.js";
import { viewDiscover } from "./screens/discover.js";
import { viewHealth } from "./screens/health.js";
import { viewReview } from "./screens/review.js";
import { RUN_POLL_MAX_FAILURES, viewRun } from "./screens/run.js";
import { viewSearch } from "./screens/search.js";
import { viewSources } from "./screens/sources.js";
import { viewTaste } from "./screens/taste.js";
import { viewTheme } from "./screens/theme.js";
import { viewTopic, viewTopics } from "./screens/topics.js";
import { viewWalls } from "./screens/walls.js";
import { viewWork } from "./screens/work.js";

/* The sidebar's sections, in order: `information-architecture.md` § The *arr
 * layout. Each is a link to its first page below, and lists its other pages
 * beneath it while it is the current one (`core/sidebar.js`).
 *
 * **A new section needs an *arr precedent or an owner ruling** — § Direction's
 * last sentence, and the one clause of the old navigation norm that survived
 * its amendment. A subsystem that gains a UI gets a page in an existing section.
 * Wanted is a section of its own, as in Sonarr, Radarr and Lidarr (the owner's
 * ruling of 2026-10-05): the works the curator wants and holds no acceptable
 * scan of (#168). `untilCounted` draws it hidden, and `paintWanted` shows it
 * once its count says something is wanted (or once the count cannot be read),
 * rather than drawing it and then hiding it. */
const SECTIONS = [
  { key: "artworks", label: "Artworks", glyph: "▣" },
  { key: "walls", label: "Walls", glyph: "▢" },
  // `badge` names the count `core/awaiting.js` writes beside the label.
  { key: "activity", label: "Activity", glyph: "↻", badge: "awaiting" },
  { key: "wanted", label: "Wanted", glyph: "◑", badge: "wanted", untilCounted: true },
  { key: "settings", label: "Settings", glyph: "⚙" },
  // `status` marks the section whose link carries the health badge.
  { key: "system", label: "System", glyph: "♥", status: true },
];

/* Every screen, and how it is reached.
 *
 * **A sidebar page carries `section` and `page`**: the section it sits in, and
 * the label its link shows. Each is where the *arr app it follows puts it, and
 * the table in § The *arr layout names that page for every row. **The first
 * page in this table is the product's home**, as the library is in every *arr
 * app, so its order is not cosmetic for that one line.
 *
 * **The keys are addresses, and they keep the spellings they had before the
 * labels changed** — `#collection` is Artworks, `#discover` is Ask,
 * `#health` is Status. A bookmark or an agent's link is an address, and every
 * one of them would otherwise break for a word the curator never sees.
 *
 * `opensFrom` is a *default* return, not a parent: a contextual screen returns
 * to the page it was actually opened from, which travels in the address as
 * `?from=`. The default is what a bookmark or an agent's link gets, having no
 * opener to remember.
 */
const ROUTES = {
  collection: { render: viewCollection, section: "artworks", page: "Artworks" },
  // Ask, in the slot Radarr's Add New holds (ruling 3 dissolved Add New into
  // Get): the intent box and the conversations. Keyed `discover`, the address it
  // has always had; the searches it starts are listed under Activity.
  discover: { render: viewDiscover, section: "artworks", page: "Ask" },
  // An index *and* an addressable detail, which is what the optional id buys:
  // `#theme` is every theme, `#theme/<id>` is one. § Navigation Structure
  // requires every consequential state to be addressable and one theme is one —
  // it is what a wall's theme control points at and what a curator bookmarks.
  // Radarr's Collections: a named grouping of what the library holds.
  theme: { render: viewTheme, detail: OPTIONAL_ID, section: "artworks", page: "Themes" },
  // The periods, movements, subjects and media the library's works are in. No
  // *arr page is one; the nearest idea is a music app's genre (`ia-proposal.md`
  // § Objects), and ruling 9 put it under the library, after Themes.
  topics: { render: viewTopics, section: "artworks", page: "Topics" },
  // Lidarr's artist index, which is that app's library: every held artist, and
  // at `#artist/<id>` one of them as the hub (ruling 4).
  artist: { render: viewArtists, detail: OPTIONAL_ID, section: "artworks", page: "Artists" },
  walls: { render: viewWalls, section: "walls", page: "Walls" },
  // What waits for the curator's verdict, first under Activity because it is
  // the one queue that needs them (`ia-proposal.md` § The map), with its count.
  to_review: { render: viewToReview, section: "activity", page: "To review", badge: "awaiting" },
  // Radarr's Activity: the searches in flight, and the ones that ended.
  queue: { render: viewQueue, section: "activity", page: "Queue" },
  history: { render: viewHistory, section: "activity", page: "History" },
  // Lidarr's Wanted: works the curator wants and holds no acceptable scan of.
  // Its section appears once one is wanted (`core/awaiting.js`).
  wanted: { render: viewWanted, section: "wanted", page: "Wanted" },
  // Radarr's Profiles: the preferences that rank what it finds.
  taste: { render: viewTaste, section: "settings", page: "Taste" },
  // Radarr's Settings › Download Clients: the external programs the server
  // works with, which here are the installed Players (`clients.md` ruling 1).
  clients: { render: viewClients, section: "settings", page: "Clients" },
  // Radarr's Settings › Indexers: the places the server searches, which here
  // are the installed source plugins, with where each came from.
  sources: { render: viewSources, section: "settings", page: "Sources" },
  health: { render: viewHealth, section: "system", page: "Status" },
  work: { render: viewWork, detail: true, opensFrom: "collection" },
  // Everything a few words find, the library's and Wikidata's (ruling 2), as
  // Sonarr's search results are a page of their own. Reached from the
  // dropdown's last row; Enter still opens Artworks filtered, so it returns
  // there by default.
  search: { render: viewSearch, opensFrom: "collection" },
  // One topic, browsed like a genre, reached from Library › Topics, the top
  // bar's dropdown, or a search on the Topics page, and returned to Topics by a
  // bookmark. Its own route rather than an id on `topics`, as the plan
  // addresses it (`#topic/<qid>`).
  topic: { render: viewTopic, detail: true, opensFrom: "topics" },
  // A search is listed under Activity, so a bookmark to one returns to Queue.
  // Run and Review share that default because they are one search's two pages:
  // each opens the other, and with different defaults every hop between them
  // would record an opener the curator never chose.
  //
  // A Get's page is its review, so a Work opened from one of its cards returns
  // to it, as one opened from Review returns to Review. Labelled for a Get
  // because a Get's page is the only run page that opens a Work.
  run: { render: viewRun, detail: true, opensFrom: "queue", returnLabel: "The Get", returnFor: ["work"] },
  // Contextual rather than a page: a conversation is something a curator does
  // *within* Ask, and returns there.
  conversation: { render: viewConversation, detail: true, opensFrom: "discover" },
  // Keyed by the run whose works are being judged, not by a work: a curator
  // reviews a run's output as a set, and a per-work address would make the grid
  // unreachable by URL.
  // `returnLabel` makes Review a place to come back to: a Work opened from a
  // review card returns to that review, not to the page the review sits under.
  review: { render: viewReview, detail: true, opensFrom: "queue", returnLabel: "The review", returnFor: ["work"] },
};

installStatus();
installSearch();
install(ROUTES, {
  sections: SECTIONS,
  onNavigate: () => {
    paintSearch();
    paintStatus();
    paintAwaiting();
    paintWanted();
  },
});

/* The handful of internals the browser suite drives directly.
 *
 * A module's bindings are not globals, which is right — the client should not
 * be scattering names onto `window` — but `tests/browser` reaches four of them
 * through `page.evaluate` to express states a real server cannot be asked for on
 * purpose: a paint that loses its view, two refreshes racing, a watch's failure
 * count. Published explicitly, in one place, so what the tests may touch is a
 * decision recorded here rather than an accident of which functions happened to
 * be top-level.
 *
 * It is also the console surface for the operator this product is built for,
 * which is why it is not hidden behind a debug flag: a tool on a private network
 * whose author is its only user gains nothing from being harder to poke at. */
Object.assign(window, { go, refresh, state, viewRun, RUN_POLL_MAX_FAILURES });
