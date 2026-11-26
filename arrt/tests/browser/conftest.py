"""The shipped browser client, driven by a real browser against a real server.

Every other suite here stops at the HTTP boundary: it asserts what `/api/*`
answers and takes on trust that the page does something sensible with it. That
trust has been wrong three times. `replaceChildren` coerced a null and put the
string "null" on the page; every image tile silently took the shape of its own
picture; and the run view repainted on every poll, so a keyboard user standing on
"Approve the list" lost the focus every two seconds. None of the three is visible
to a test that reads JSON, and two of them reached a running product.

So this level runs the real `app.js`, served by the real server, in a real
Chromium. **The client is what is under test and `/api` is its boundary** — which
is why several tests here stub a route rather than seed a catalogue. Some of the
control flow worth pinning describes states a real server reaches only slowly,
expensively, or cannot be asked for deterministically at all: a poll that changes
nothing, a page that keeps insisting there is more, an unresolved work carrying
each kind of nothing in turn. A harness that could not reach them would cover the
client's rendering and none of its control flow, which is the half that has
actually broken.

**Where a real server can produce the state, it does.** Paging runs against a
real catalogue and the real `truncated` flag; the image tests write a real file
and take it away; the focus move runs against the real routes. Stubs are for what
a server cannot be asked to do on purpose.

Payload builders live in `payloads.py` beside this file, and the rule they follow
— build from the API's own response models, never a hand-written dict — is
stated there.

**A wait must name something that is true only in the state being waited for.**
`wait_for_selector("h1")` after a click that leaves a screen already carrying an
`h1`, or `[role=alert]` on a screen whose first paint puts one there, matches
instantly and waits for nothing — after which the assertions under it read the
state that was there beforehand, and the test passes for exactly as long as the
write happens to win a race nothing is holding open. Four have been found here:
two heading waits that stopped meaning "the grid painted" once Collection grew a
loading placeholder with an `h1` of its own, one over the live region the
unanswered-turn panel puts up at first paint, and one over a heading the hang
navigates away from. Every one passed alone and failed in the full suite, where a
heavier test ran ahead of it and moved the timing. Wait for the *new* thing — the
text the write produced, the section the navigation lands on — and let the
assertions be about the rest.

**And the assertions retry.** A read such as `loc.inner_text()` is one instant
of the page; `expect(loc).to_have_text(…, use_inner_text=True)` is the same
question asked until the page agrees. The table of which read becomes which
assertion, and the shapes that have none, is `docs/testing.md` § "Assertions
read the page through `expect`"; `tests/unit/test_browser_reads_retry.py`
refuses a one-shot read or a fixed sleep in a converted file.
"""

import pathlib
from datetime import UTC, datetime, timedelta

import pytest
from fixed_instant import fixed_instant
from page_ui import Ui

from arrt.http import api as http_api
from arrt.http.models import (
    BackupOut,
    HealthOut,
    PicturesOut,
    PlayerHealthOut,
    SetupStepOut,
    SourcePluginOut,
    TroubleOut,
    WallHeartbeatOut,
    WatchesHealthOut,
)
from arrt.library.services.watches import WatchesReading
from arrt.library.sources.loading import PluginIdentity, PluginPart, PluginReading, PluginState
from arrt.persistence.records import (
    AcquisitionMethod,
    BackupReading,
    Client,
    Display,
    FetchStatus,
    RightsStatus,
    SourceClass,
    Wall,
)
from arrt.programming.client_heartbeat import ClientHeartbeatReading, ReportedLabelOutput, ReportedOutput
from arrt.programming.clients import PlacementSurvey, view_of
from arrt.programming.manifest.heartbeat import HeartbeatReading
from arrt.programming.reports import WallHeartbeat
from arrt.services.health import HealthReading, PicturesReading, SourceHealth, failed_fetches, walls_waiting

BROWSER_DIR = pathlib.Path(__file__).parent

#: How long an `expect` keeps asking: Playwright's own default for an action
#: and for `wait_for`, where `expect`'s is five seconds. A converted read then
#: gives up no sooner than the wait it replaced did, under the pool's load.
EXPECT_TIMEOUT_MS = 30_000

try:
    from playwright.sync_api import expect
except ImportError:  # collected without the browser group: every test here skips
    expect = None
else:
    expect.set_options(timeout=EXPECT_TIMEOUT_MS)


def pytest_collection_modifyitems(items):
    """Mark everything in this directory `browser`, rather than trusting each file to.

    The marker is what keeps a suite needing a 200MB browser out of the default
    run, so a file that forgot it would not fail here — it would fail for every
    contributor who had not installed one, in a suite they never asked to run.
    Applying it from the directory means a new test file cannot be added without
    it. Scoped by path because this hook is handed every collected item, not only
    the ones beneath this conftest.
    """
    for item in items:
        if BROWSER_DIR in item.path.parents:
            item.add_marker(pytest.mark.browser)


@pytest.fixture
def work_with_an_image(service, settings, decodable_jpeg):
    """A work whose master is really on disk, so its thumbnail really renders.

    `ready_work` records an original without writing one, which is right for the
    readiness rules it serves and wrong here: the browser has to actually decode
    what the thumbnail endpoint returns, and a work whose file is missing would
    exercise the absent-image path in a test asking about the present-image one.
    """

    def _work(title="Nighthawks", *, width=1600, height=1200):
        artwork = service.add_artwork(title=title, date_created="1942", medium="Oil on canvas")
        source = service.add_source(
            artwork_id=artwork.id,
            url=f"https://museum.example/{artwork.id}",
            provider="artic",
            source_class=SourceClass.INSTITUTIONAL,
            acquisition_method=AcquisitionMethod.DEZOOMIFY,
            rights_status=RightsStatus.PUBLIC_DOMAIN,
            is_primary=True,
        )
        relative = f"raw/{artwork.id}.jpg"
        decodable_jpeg(settings.art_root / relative, width=width, height=height)
        service.record_original(
            artwork_id=artwork.id,
            source_id=source.id,
            path=relative,
            width=width,
            height=height,
            byte_size=(settings.art_root / relative).stat().st_size,
            content_hash=f"hash-{artwork.id}",
            fetch_status=FetchStatus.OK,
        )
        return artwork

    return _work


@pytest.fixture
def give_a_master(service):
    """Record a master for a work, as a finished fetch leaves it: `give_a_master(work)`.

    A held registry row asks for a picture only when the server says its work
    holds one (`pictured_artwork_id`), so a test of a row's picture gives its
    work one. No file is written, so the server refuses the thumbnail: serve it
    (`pictures_load`) where the picture itself is the question.
    """

    def _give(work):
        source = service.add_source(
            artwork_id=work.id,
            url=f"https://museum.example/{work.id}",
            provider="artic",
            source_class=SourceClass.INSTITUTIONAL,
            acquisition_method=AcquisitionMethod.DEZOOMIFY,
            rights_status=RightsStatus.PUBLIC_DOMAIN,
            is_primary=True,
        )
        service.record_original(
            artwork_id=work.id,
            source_id=source.id,
            path=f"raw/{work.id}.tif",
            width=6000,
            height=4000,
            byte_size=90_000_000,
            content_hash=f"hash-{work.id}",
            fetch_status=FetchStatus.OK,
        )

    return _give


#: A 1×1 PNG, served for every picture a work's mark asks for when a test needs
#: them to load: the suite's server holds no masters, and Commons is not asked.
ONE_PIXEL_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360f8cfc0f01f0005fe02fea7d6a4"
    "e30000000049454e44ae426082"
)


@pytest.fixture
def pictures_load(ui):
    """Every work picture — the library's thumbnails and Wikidata's Commons files — answers with a real image."""

    def _serve(route):
        route.fulfill(status=200, content_type="image/png", body=ONE_PIXEL_PNG)

    ui.page.route("**/api/works/*/thumbnail*", _serve)
    ui.page.route("https://commons.wikimedia.org/**", _serve)
    return ui


@pytest.fixture
def want_item(discovery, propose):
    """Want a work and match it to a Wikidata item, as Review and the picker do: `want_item(qid, title)`."""

    def _want(qid, title):
        work = propose(title)
        discovery.want(work.id)
        discovery.set_wikidata_item(work.id, qid)
        return work

    return _want


@pytest.fixture
def a_player_shows(services, shared_clock):
    """Put a wall on a Player that has its token and has reported: `a_player_shows(wall_id)`, the Player returned.

    A Player chosen with no token, or with no report yet, is still being set up
    (`player_state.py`), and the walls it shows wait for it
    (`services.health.walls_waiting`): the question before a hang says so, never
    that everyone sees them change. A test of a wall a
    Player shows makes it shown through the server's own routes, so the wall is
    one `walls_waiting` does not name. `player` puts a second wall on the same one.
    """

    def _shows(wall_id, *, name="Hall Pi", output="hdmi-a-1", player=None):
        if player is None:
            player = services.clients.add_client(name=name)
            services.access.issue(player.id)
            outputs = [{"name": f"hdmi-a-{n}", "kind": "framebuffer", "connected": True, "screen": [1920, 1080]} for n in (1, 2)]
            services.clients.record_heartbeat(player.id, {"reported_at": shared_clock().isoformat(), "outputs": outputs})
        services.clients.assign_wall(wall_id, client_id=player.id, output=output)
        return player

    return _shows


@pytest.fixture
def a_health_reading():
    """`GET /api/health` as the API's own models define it: one heartbeat per wall.

    **Built from `HealthOut` and dumped, per `payloads.py`'s rule.** A
    model that changes shape then breaks the fixture rather than leaving it
    pinned to an old contract, and `HealthOut.walls` holds one heartbeat per wall.

    Every field is overridable, because what these tests vary is exactly which
    observation is wrong.

    **The one health model's fields are derived, never written here**
    (`_served`): each wall's `display_state` and `waiting_for`, the `players`, `failed_fetches`,
    `troubles` and `setup_steps` come from the server's own functions over the readings
    above, so a reading with a silent wall carries that wall's trouble and one
    with nothing wrong carries none. `player` overrides the Player that shows
    the walls (`_a_player`'s keys); `failed` is the queue's failed works, as
    `AcquisitionState`s. `description` is the server's sentence for these
    walls (`HealthReading.describe`) unless a test passes one, which only a
    test about a sentence that disagrees with the readings does.

    **A test changes a reading by passing it in, never by editing the answer
    after it was built**: an edit after the fact leaves the derived fields
    saying what the server would have said before it. A test whose point is an
    answer the server would not send (a part missing, a shape it cannot parse)
    says so where it edits.
    """

    def _reading(
        *,
        walls=None,
        backup=None,
        description=None,
        sources=None,
        pictures=None,
        watches=None,
        player=None,
        failed=(),
    ):
        walls = [_a_wall()] if walls is None else walls
        backup = _a_backup() if backup is None else backup
        sources = [_a_source()] if sources is None else sources
        watches = {"overdue": [], "allowance_spent": False} if watches is None else watches
        chosen = _a_player(**(player or {}))
        served = _served(walls, backup=backup, sources=sources, watches=watches, player=chosen, failed=failed)
        waiting = walls_waiting(served.walls, served.players)
        return HealthOut(
            watches=WatchesHealthOut(**watches),
            pictures=PicturesOut(**(_some_pictures() if pictures is None else pictures)),
            sources=[SourcePluginOut(**source) for source in sources],
            walls=[
                WallHeartbeatOut(
                    **_without_placement(wall),
                    display_state=http_api._display_state(seen.state),
                    waiting_for=http_api._wall_wait(waiting.get(seen.wall.id)),
                )
                for wall, seen in zip(walls, served.walls, strict=True)
            ],
            description=served.describe() if description is None else description,
            backup=BackupOut(**backup),
            players=[
                PlayerHealthOut(client_id=view.client.id, name=view.client.name, state=http_api._player_state(view.player))
                for view in served.players
            ],
            failed_fetches=None if served.failed_fetches is None else http_api._failed_fetches(served.failed_fetches),
            troubles=[
                TroubleOut(about=str(trouble.about), subject=trouble.subject, state=trouble.state, words=trouble.words)
                for trouble in served.troubles()
            ],
            setup_steps=[
                SetupStepOut(about=str(step.about), subject=step.subject, state=step.state, words=step.words)
                for step in served.setup_steps()
            ],
        ).model_dump()

    return _reading


#: The instant the fixture's readings were taken at: 41.2 seconds after the
#: default wall's report, which is the age `_a_wall` gives it.
_READ_AT = datetime(2026, 8, 12, 9, 14, 43, 200000, tzinfo=UTC)

#: The key `_a_wall` marks a wall no Player shows with; never sent to a model.
_SHOWN = "shown_by_a_player"


def _without_placement(wall):
    return {key: value for key, value in wall.items() if key != _SHOWN}


def _a_player(*, name="The living room Pi", token_issued=True, absent=False, problem=None, age_seconds=5.0, labels=()):
    """The Player that shows every wall a reading's walls say a Player shows: reporting, unless told otherwise.

    `labels` are the label panels it reports, as `(name, connected)` pairs, any
    number of them: a Player with labels exists even where no wall is shown, so
    one with label panels and no screen can be built (the owner's ruling 8).
    """
    return {
        "name": name,
        "token_issued": token_issued,
        "absent": absent,
        "problem": problem,
        "age_seconds": age_seconds,
        "labels": tuple(labels),
    }


def _served(walls, *, backup, sources, watches, player, failed):
    """The server's `HealthReading` for these readings, through the server's own functions.

    Each wall a Player shows is on one of that Player's screens, so
    `PlacementSurvey` and `display_state_of` decide its state as the route does;
    a wall marked as shown by none is on no display, so it reads `unassigned`.
    The Player exists only when some wall is shown by one, or it reports a label panel.
    """
    created = datetime(2026, 8, 1, tzinfo=UTC)
    shown = [wall.get(_SHOWN, True) for wall in walls]
    client = None
    if any(shown) or player["labels"]:
        client = Client(
            id="player-1",
            name=player["name"],
            created_at=created,
            token_issued_at=created if player["token_issued"] else None,
        )
    displays = {}
    records = []
    for index, (wall, on_a_player) in enumerate(zip(walls, shown, strict=True), start=1):
        display_id = None
        if on_a_player:
            display_id = f"display-{index}"
            displays[display_id] = Display(
                id=display_id,
                identity=f"player-1/hdmi-a-{index}",
                client_id="player-1",
                output=f"hdmi-a-{index}",
                kind="framebuffer",
                first_seen=created,
            )
        records.append(Wall(id=wall["wall_id"], name=wall["wall_name"], created_at=created, display_id=display_id))
    report = None
    if client is not None:
        report = ClientHeartbeatReading(
            path=pathlib.Path("/art/client-heartbeat-player-1.json"),
            reported_at=None if player["absent"] else _READ_AT - timedelta(seconds=player["age_seconds"]),
            age_seconds=None if player["absent"] else player["age_seconds"],
            outputs=(
                []
                if player["absent"] or player["problem"]
                else [ReportedOutput(display.output, "framebuffer", True, (1920, 1080)) for display in displays.values()]
            ),
            problem=player["problem"],
            absent=player["absent"],
            label_outputs=(
                ()
                if player["absent"] or player["problem"]
                else tuple(ReportedLabelOutput(label, "epaper", connected, (800, 480)) for label, connected in player["labels"])
            ),
        )
    survey = PlacementSurvey(
        clients={} if client is None else {client.id: client},
        displays=displays,
        walls=records,
        label_outputs=[],
        readings={} if report is None else {"player-1": report},
        faults={},
    )
    seen = []
    for wall, record in zip(walls, records, strict=True):
        beat = wall["heartbeat"]
        reading = HeartbeatReading(
            path=pathlib.Path(beat["path"]),
            reported_at=None if beat["reported_at"] is None else datetime.fromisoformat(beat["reported_at"]),
            age_seconds=beat["age_seconds"],
            contents=None if beat["problem"] is not None else beat["reported"],
            problem=beat["problem"],
        )
        seen.append(WallHeartbeat(wall=record, heartbeat=reading, state=survey.wall_state(record, reading)))
    return HealthReading(
        walls=seen,
        backup=BackupReading(
            path=pathlib.Path(backup["path"]),
            completed_at=None if backup["completed_at"] is None else datetime.fromisoformat(backup["completed_at"]),
            age_seconds=backup["age_seconds"],
            contents=None if backup["problem"] is not None else backup["reported"],
            problem=backup["problem"],
        ),
        pictures=PicturesReading(pictures_bytes=0, pictures_files=0, age_seconds=0.0),
        sources=[
            SourceHealth(
                reading=PluginReading(
                    name=source["name"],
                    state=PluginState(source["state"]),
                    reason=source["reason"],
                    faults=source["faults"],
                    last_fault_at=None,
                    last_fault=source["last_fault"],
                ),
                last_fault_age_seconds=source["last_fault_age_seconds"],
            )
            for source in sources
        ],
        watches=WatchesReading(overdue=tuple(watches["overdue"]), allowance_spent=watches["allowance_spent"]),
        players=() if client is None or report is None else (view_of(client, survey, report),),
        failed_fetches=failed_fetches(tuple(failed), now=_READ_AT),
    )


def _some_pictures(*, files=2, size=48_000, age_seconds=12.0, unreadable=0):
    # Through the server's own reading and route projection, never a sentence
    # written here: `PicturesReading.describe` says it, `_pictures` answers it.
    return http_api._pictures(
        PicturesReading(pictures_bytes=size, pictures_files=files, age_seconds=age_seconds, unreadable=unreadable)
    ).model_dump()


def _a_wall(*, wall_id="wall-1", name="The living room", absent=False, problem=None, age_seconds=41.2, reported=None, shown=True):
    """One wall's reading. `shown=False` is a wall no Player shows (`unassigned`), a step of setting up."""
    return {
        _SHOWN: shown,
        "wall_id": wall_id,
        "wall_name": name,
        "heartbeat": {
            "path": f"/art/display-heartbeat-{wall_id}.json",
            "reported_at": None if absent else "2026-08-12T09:14:02+00:00",
            "age_seconds": None if absent else age_seconds,
            "absent": absent,
            "problem": problem,
            # The server's own sentence for this reading (`HeartbeatReading.describe`).
            "description": HeartbeatReading(
                path=pathlib.Path(f"/art/display-heartbeat-{wall_id}.json"),
                reported_at=None if absent else datetime.fromisoformat("2026-08-12T09:14:02+00:00"),
                age_seconds=None if absent else age_seconds,
                contents=None if absent or problem is not None else {},
                problem=problem,
            ).describe(),
            "reported": None if absent else {"reported_at": "2026-08-12T09:14:02+00:00"} | (reported or {}),
        },
    }


def _a_backup(*, absent=False, problem=None):
    path = "/art/backup-receipt.json"
    completed_at = None if absent else "2026-08-12T03:00:00+00:00"
    age_seconds = None if absent else 22440.0
    reported = None if absent else {"completed_at": completed_at}
    return {
        "path": path,
        "completed_at": completed_at,
        "age_seconds": age_seconds,
        "absent": absent,
        "problem": problem,
        # The server's own sentence for this reading (`BackupReading.describe`),
        # as `_a_wall`'s is the heartbeat's, never written here.
        "description": BackupReading(
            path=pathlib.Path(path),
            completed_at=None if absent else datetime.fromisoformat(completed_at),
            age_seconds=age_seconds,
            contents=None if absent or problem is not None else reported,
            problem=problem,
        ).describe(),
        "reported": reported,
    }


def _a_source(
    *,
    name="artic",
    state="loaded",
    reason=None,
    faults=0,
    distribution="arrt",
    version="0.3.0",
    api_major=1,
    provides=None,
    museum=None,
):
    # Through the server's own functions, never written here: `SourceHealth`
    # says the sentence (`services/health.py`, `describe`), by the museum and
    # never the plugin id, and `_source_plugin` is the route's own projection,
    # so every field the route answers is here as it would answer it. A plugin
    # from elsewhere names its own museum (1.4). Nothing could not be asked and
    # nothing has been answered, which is what a plugin just loaded reports.
    parts = (["finds_images", "reads"] if state == "loaded" else []) if provides is None else provides
    reading = PluginReading(
        name=name,
        state=PluginState(state),
        reason=reason,
        faults=faults,
        last_fault_at=datetime(2026, 10, 3, 12, 0, tzinfo=UTC) if faults else None,
        last_fault="KeyError: 'x'" if faults else None,
        identity=PluginIdentity(
            distribution=distribution,
            version=version,
            api_major=api_major,
            provides=tuple(PluginPart(part) for part in parts),
            museum=museum,
        ),
    )
    return http_api._source_plugin(SourceHealth(reading=reading, last_fault_age_seconds=12.0 if faults else None)).model_dump()


@pytest.fixture
def a_source_reading():
    return _a_source


@pytest.fixture
def a_wall_reading():
    return _a_wall


@pytest.fixture
def a_backup_reading():
    return _a_backup


@pytest.fixture
def ui(page, server_url, request):
    """The page, kept off every origin but the suite's own server.

    The client asks Commons for the pictures a reply or a search names, and an
    unguarded page fetched them from the live site: a test then read a picture
    box that filled with "Picture unavailable" whenever the internet answered,
    which is when it failed (#343). Aborted here, every outside request fails
    the same way on every run, and a test that needs a picture to load says so
    with `pictures_load` or a route of its own, which Playwright tries first
    because it was registered later.

    A test marked `at_a_fixed_instant` has the page's `Date` fixed at that instant
    (`fixed_instant.py`), the instant the services' clock starts at: the page's ages
    and the server's are then read from one moment.
    """
    instant = fixed_instant(request)
    if instant is not None:
        page.clock.set_fixed_time(instant)
    # With its slash, so a port that merely begins with this one's digits is outside.
    page.route(lambda url: not url.startswith(f"{server_url}/"), lambda route: route.abort())
    return Ui(page, server_url)
