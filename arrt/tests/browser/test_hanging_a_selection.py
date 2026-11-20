"""Hang… on any selection: Artworks, an Artist's works, the search results, a Topic.

`information-architecture.md` § Flow 6 and § One selection model on every list:
the IA gives *Hang…* to any set of works, so hanging an artist's works never
means building a theme first.

**The claim is the request.** Each test reads what the page sent to
`POST /api/walls/<id>/selection` and what the server then holds on the wall:
a button that opened the right dialog and sent the wrong works would pass a
check of the dialog alone.

Only held works with a picture are sent. A work a wall cannot show (no picture
yet, or archived) would hang the wall dark, as the Work page's disabled *Hang…*
says; a work Wikidata lists and the library does not hold has no id to send.
"""

import json
import re

import httpx
import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from fakes import FakeRegistry
from playwright.sync_api import expect

from arrt.library.registry import (
    CommonsFile,
    ItemId,
    RegistryArtist,
    RegistryCreator,
    RegistryText,
    RegistryTopic,
    RegistryTopicRef,
    RegistryTopicWork,
    RegistryWorkEntry,
    RegistryWorkMatch,
    TopicKind,
)
from arrt.persistence.records import (
    AcquisitionMethod,
    FetchStatus,
    MatMethod,
    RenditionKind,
    RightsStatus,
    SourceClass,
)

ROTHKO = "Q160149"
HUNTERS = "Q500985"
HERD = "Q500986"
SIXTEENTH = "Q7017"
HARVESTERS = "Q1170284"
COMMONS = "https://commons.wikimedia.org/wiki/Special:FilePath/Hunters.jpg"
BY = RegistryCreator(qid=ItemId("Q43270"), name=RegistryText("Pieter Brueghel the Elder"))

SELECTION = re.compile(r"/api/walls/[^/]+/selection$")


@pytest.fixture
def registry():
    century = RegistryTopicRef(qid=ItemId(SIXTEENTH), label=RegistryText("16th century"), kind=TopicKind.PERIOD)
    return FakeRegistry(
        artists={
            ROTHKO: RegistryArtist(
                qid=ROTHKO,
                name="Mark Rothko",
                works=(
                    RegistryWorkEntry(qid="Q2956755", title="Rothko Chapel", sitelinks=13, image=COMMONS),
                    RegistryWorkEntry(qid="Q17038023", title="No 1", sitelinks=6),
                ),
                works_total=2,
            )
        },
        matches={
            "snow": [
                RegistryWorkMatch(qid=HUNTERS, title="Hunters in the Snow", sitelinks=25, creator=BY),
                RegistryWorkMatch(qid=HERD, title="Return of the Herd in the Snow", sitelinks=12, creator=BY),
            ]
        },
        work_topics={HUNTERS: [century], HERD: [century]},
        topics={
            SIXTEENTH: RegistryTopic(
                qid=ItemId(SIXTEENTH), label=RegistryText("16th century"), kinds=(TopicKind.PERIOD,), start=1501, end=1600
            )
        },
        topic_works={
            SIXTEENTH: [
                RegistryTopicWork(
                    qid=ItemId(HARVESTERS),
                    title=RegistryText("The Harvesters"),
                    sitelinks=25,
                    year=1565,
                    image=CommonsFile(COMMONS),
                    creators=(BY,),
                )
            ]
        },
    )


@pytest.fixture
def hangable(service, settings, decodable_jpeg):
    """A work a wall can show: its image on disk, a mat and a presentation master.

    `work_with_an_image` (`conftest.py`) makes the image and not the artist or the item, which an
    Artist's page and a Topic's need; this is its body with the two, and the mat and master the
    build wants.
    """

    def _hangable(title, *, artist=None, qid=None):
        work = service.add_artwork(
            title=title, date_created="1942", medium="Oil on canvas", artist_id=artist.id if artist else None, wikidata_qid=qid
        )
        source = service.add_source(
            artwork_id=work.id,
            url=f"https://museum.example/{work.id}",
            provider="artic",
            source_class=SourceClass.INSTITUTIONAL,
            acquisition_method=AcquisitionMethod.DEZOOMIFY,
            rights_status=RightsStatus.PUBLIC_DOMAIN,
            is_primary=True,
        )
        raw = f"raw/{work.id}.jpg"
        decodable_jpeg(settings.art_root / raw, width=1600, height=1200)
        service.record_original(
            artwork_id=work.id,
            source_id=source.id,
            path=raw,
            width=1600,
            height=1200,
            byte_size=(settings.art_root / raw).stat().st_size,
            content_hash=f"hash-{work.id}",
            fetch_status=FetchStatus.OK,
        )
        service.record_mat_color(artwork_id=work.id, hex_rgb="#27285b", method=MatMethod.VISION_MODEL)
        decodable_jpeg(settings.art_root / f"presentation/{work.id}.jpg", width=400, height=300)
        service.record_rendition(
            artwork_id=work.id,
            kind=RenditionKind.PRESENTATION_MASTER,
            target_width=7680,
            target_height=7680,
            path=f"presentation/{work.id}.jpg",
        )
        return work

    return _hangable


@pytest.fixture
def api(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


def the_wall(services):
    return services.display.survey_walls()[0].wall


def hanging_on(api, wall_id):
    """The works the server says hang on a wall, in order, or none."""
    wall = next(wall for wall in api.get("/api/walls").json()["walls"] if wall["wall_id"] == wall_id)
    if wall["theme"] is None:
        return []
    return [work["artwork_id"] for work in api.get(f"/api/themes/{wall['theme']['theme_id']}").json()["works"]]


# -- the four lists, each with two works that can hang -------------------------


@pytest.fixture
def two_on(request, services, service, hangable):
    """The list named by the parameter: its address and the two works on it a wall can show."""
    if request.param == "artworks":
        return "#collection", [hangable("Study A"), hangable("Study B")]
    if request.param == "artist":
        artist = service.add_artist(name="Mark Rothko", born=1903, died=1970)
        services.identity.set_artist_identity(artist.id, ROTHKO)
        return f"#artist/{artist.id}", [hangable("Untitled A", artist=artist), hangable("Untitled B", artist=artist)]
    if request.param == "search":
        return "#search?q=harvest", [hangable("Harvest at Dusk"), hangable("Harvest Moon")]
    works = [hangable("The Hunters in the Snow", qid=HUNTERS), hangable("The Return of the Herd", qid=HERD)]
    services.topic_sweep.run()
    return f"#topic/{SIXTEENTH}", works


def selection_posts(ui):
    """Every request the page made to hang a selection on a wall (the client's own file of the same name is not one)."""
    return [url for url in ui.requests if SELECTION.search(url)]


def open_selecting(ui, address):
    ui.open(address)
    ui.page.locator("#view button.select-toggle:visible").wait_for()
    ui.page.click("#view button.select-toggle")
    expect(ui.page.locator("#view button.select-toggle")).to_have_text("Stop selecting", use_inner_text=True)


def tick(ui, work):
    ui.page.check(f"#view [data-artwork='{work.id}'] input[type='checkbox']")


def hang_from(ui, wall):
    """Press Hang…, say yes, and return the body the page sent."""
    ui.page.click("#view .selection button.selection-hang")
    ui.page.locator("dialog.confirm[open]").wait_for()
    with ui.page.expect_request(lambda request: bool(SELECTION.search(request.url)) and request.method == "POST") as sent:
        ui.page.click(".confirm-actions button:text-is('Hang')")
    return json.loads(sent.value.post_data)  # one-shot: the body of the request just matched


@pytest.mark.parametrize("two_on", ["artworks", "artist", "search", "topic"], indirect=True)
def test_hang_sends_the_ticked_works_and_the_wall_shows_them(ui, api, services, two_on):
    address, works = two_on
    wall = the_wall(services)
    open_selecting(ui, address)
    for work in works:
        tick(ui, work)

    body = hang_from(ui, wall)

    expect(ui.page.locator(".selection-status")).to_have_text(f"Hung 2 works on {wall.name}.", use_inner_text=True)
    assert body == {"artwork_ids": [work.id for work in works]}
    assert hanging_on(api, wall.id) == [work.id for work in works]
    # The ticks are spent, as after every other act, and the mode stays on.
    expect(ui.page.locator("#view input[type='checkbox']:checked")).to_have_count(0)
    expect(ui.page.locator("#view button.select-toggle")).to_have_text("Stop selecting", use_inner_text=True)


@pytest.mark.parametrize("two_on", ["artworks", "artist", "search", "topic"], indirect=True)
def test_hang_waits_for_a_tick_and_asks_naming_the_works_and_the_wall(ui, services, two_on):
    address, works = two_on
    wall = the_wall(services)
    open_selecting(ui, address)
    hang = ui.page.locator("#view .selection button.selection-hang")

    expect(hang).to_have_text("Hang…", use_inner_text=True)
    expect(hang).to_be_disabled()
    tick(ui, works[0])
    expect(hang).to_be_enabled()
    hang.click()

    expect(ui.page.locator(".confirm-title")).to_have_text(f"Hang 1 work on {wall.name}?", use_inner_text=True)
    expect(ui.page.locator(".confirm-consequence")).to_contain_text(f"{wall.name} shows it until something else is hung there")


@pytest.mark.parametrize("two_on", ["artworks"], indirect=True)
def test_a_selection_hung_on_a_wall_whose_player_has_no_token_says_it_waits_and_hangs(ui, api, services, two_on):
    """Through a list's *Hang…*: the server's words for the wait, not "Everyone in the house sees"; it still hangs."""
    address, works = two_on
    wall = the_wall(services)
    hall = services.clients.add_client(name="Hall Pi")
    services.clients.assign_wall(wall.id, client_id=hall.id, output="hdmi-a-1")
    words = services.health.observe_walls().waiting[wall.id].words
    open_selecting(ui, address)
    tick(ui, works[0])
    ui.page.click("#view .selection button.selection-hang")

    consequence = ui.page.locator("dialog.confirm[open] .confirm-consequence")
    expect(consequence).to_contain_text(f"{words}.", use_inner_text=True)
    assert words == f"{wall.name} waits for Hall Pi, which has no token yet"
    expect(consequence).not_to_contain_text("Everyone in the house", use_inner_text=True)
    ui.page.click(".confirm-actions button:text-is('Hang')")
    expect(ui.page.locator(".selection-status")).to_have_text(f"Hung 1 work on {wall.name}.", use_inner_text=True)
    assert hanging_on(api, wall.id) == [works[0].id]


def test_declining_the_question_sends_nothing(ui, api, services, two_on_artworks):
    address, works = two_on_artworks
    wall = the_wall(services)
    open_selecting(ui, address)
    tick(ui, works[0])

    ui.page.click("#view .selection button.selection-hang")
    ui.page.locator("dialog.confirm[open]").wait_for()
    ui.page.click(".confirm-actions button:text-is('Cancel')")

    expect(ui.page.locator("dialog.confirm")).to_have_count(0)
    assert selection_posts(ui) == []
    assert hanging_on(api, wall.id) == []
    # Still selected, and the keyboard is back on the control that asked.
    expect(ui.page.locator(".selection-status")).to_have_text("1 selected.", use_inner_text=True)
    assert ui.focused() == "Hang…"


@pytest.fixture
def two_on_artworks(hangable):
    return "#collection", [hangable("Study A"), hangable("Study B")]


def test_with_two_walls_hang_asks_which_and_hangs_only_there(ui, api, services, two_on_artworks):
    address, works = two_on_artworks
    hall = the_wall(services)
    study = services.display.add_wall(name="Study")
    open_selecting(ui, address)
    for work in works:
        tick(ui, work)

    ui.page.click("#view .selection button.selection-hang")
    expect(ui.page.locator("dialog.panel-dialog[open] .wall-choices button")).to_have_count(2)
    ui.page.click(".wall-choices button:text-is('Study')")
    ui.page.locator("dialog.confirm[open]").wait_for()
    expect(ui.page.locator(".confirm-title")).to_have_text("Hang 2 works on Study?", use_inner_text=True)
    expect(ui.page.locator(".confirm-consequence")).to_contain_text("Study shows them until")
    ui.page.click(".confirm-actions button:text-is('Hang')")

    expect(ui.page.locator(".selection-status")).to_have_text("Hung 2 works on Study.", use_inner_text=True)
    assert hanging_on(api, study.id) == [work.id for work in works]
    assert hanging_on(api, hall.id) == []


# -- what is not sent ----------------------------------------------------------


@pytest.fixture
def a_rothko_page(services, service, hangable):
    """An artist's page: two works a wall can show, 26 it cannot (no picture yet), Wikidata's two not held.

    The two are named to sort last, past the server's first page of twenty-five: *Select all* here
    reads the works across pages, and the first page alone holds neither.
    """
    artist = service.add_artist(name="Mark Rothko", born=1903, died=1970)
    services.identity.set_artist_identity(artist.id, ROTHKO)
    pictureless = [service.add_artwork(title=f"Sketch {number:02d}", artist_id=artist.id) for number in range(26)]
    first, second = hangable("Zed Untitled A", artist=artist), hangable("Zed Untitled B", artist=artist)
    return artist, [first, second], pictureless


def test_select_all_on_an_artist_sends_only_the_held_works_a_wall_can_show(ui, api, services, a_rothko_page):
    artist, hung, pictureless = a_rothko_page
    wall = the_wall(services)
    open_selecting(ui, f"#artist/{artist.id}")
    # Wikidata's two works are on the page to tick, so Select all ticks them too:
    # they have no id to send, and none is sent.
    expect(
        ui.page.locator("#view .get-control, #view input[type='checkbox'][aria-label^='Select Rothko Chapel']").first
    ).to_be_attached()

    ui.page.click("#view .selection button.select-all")
    # The 28 held works and the 2 listed ones, all ticked, so the ticked listed works are what must not be sent.
    expect(ui.page.locator(".selection-status")).to_have_text("30 selected.", use_inner_text=True)
    body = hang_from_after_question(ui, wall, left_out=len(pictureless))

    expect(ui.page.locator(".selection-status")).to_have_text(f"Hung 2 works on {wall.name}.", use_inner_text=True)
    assert sorted(body["artwork_ids"]) == sorted(work.id for work in hung)
    assert set(body) == {"artwork_ids"}
    assert sorted(hanging_on(api, wall.id)) == sorted(work.id for work in hung)


def hang_from_after_question(ui, wall, *, left_out):
    ui.page.click("#view .selection button.selection-hang")
    ui.page.locator("dialog.confirm[open]").wait_for()
    noun = "work" if left_out == 1 else "works"
    expect(ui.page.locator(".confirm-consequence")).to_contain_text(
        f"Left out, as they cannot be shown (no picture yet, or archived): {left_out} {noun}."
    )
    with ui.page.expect_request(lambda request: bool(SELECTION.search(request.url)) and request.method == "POST") as sent:
        ui.page.click(".confirm-actions button:text-is('Hang')")
    return json.loads(sent.value.post_data)  # one-shot: the body of the request just matched


def test_a_work_unticked_after_select_all_is_not_hung(ui, api, services, a_rothko_page):
    artist, hung, pictureless = a_rothko_page
    wall = the_wall(services)
    open_selecting(ui, f"#artist/{artist.id}")
    ui.page.click("#view .selection button.select-all")
    expect(ui.page.locator("#view input[type='checkbox']:checked").first).to_be_attached()
    ui.page.uncheck(f"#view [data-artwork='{hung[0].id}'] input[type='checkbox']")

    body = hang_from_after_question(ui, wall, left_out=len(pictureless))

    expect(ui.page.locator(".selection-status")).to_have_text(f"Hung 1 work on {wall.name}.", use_inner_text=True)
    assert body == {"artwork_ids": [hung[1].id]}
    assert hanging_on(api, wall.id) == [hung[1].id]


def test_a_selection_with_nothing_a_wall_can_show_says_so_and_sends_nothing(ui, api, services, service):
    nothing = [service.add_artwork(title=f"Study {number}") for number in range(2)]
    wall = the_wall(services)
    open_selecting(ui, "#collection?q=study")
    for work in nothing:
        tick(ui, work)

    ui.page.click("#view .selection button.selection-hang")

    expect(ui.page.locator("dialog.panel-dialog[open] .panel-dialog-lead")).to_have_text(
        "Those 2 works have no picture yet or are archived, so there is nothing to show on a wall.",
        use_inner_text=True,
    )
    expect(ui.page.locator("dialog.confirm")).to_have_count(0)
    assert selection_posts(ui) == []
    assert hanging_on(api, wall.id) == []


def test_an_archived_work_is_left_out_with_the_ones_without_a_picture(ui, api, services, service, hangable):
    shown, gone = hangable("Study A"), hangable("Study B")
    service.archive_artworks([gone.id])
    wall = the_wall(services)
    open_selecting(ui, "#collection?q=study")
    tick(ui, shown)
    tick(ui, gone)

    ui.page.click("#view .selection button.selection-hang")
    ui.page.locator("dialog.confirm[open]").wait_for()

    expect(ui.page.locator(".confirm-title")).to_have_text(f"Hang 1 work on {wall.name}?", use_inner_text=True)
    expect(ui.page.locator(".confirm-consequence")).to_contain_text("Left out, as they cannot be shown")
    ui.page.click(".confirm-actions button:text-is('Hang')")
    expect(ui.page.locator(".selection-status")).to_have_text(f"Hung 1 work on {wall.name}.", use_inner_text=True)
    assert hanging_on(api, wall.id) == [shown.id]


def test_a_refused_hang_is_said_beside_hang_and_keeps_the_selection(ui, services, two_on_artworks):
    address, works = two_on_artworks
    wall = the_wall(services)
    ui.serve("**/api/walls/*/selection", (400, {"error": "The wall is not taking a hang just now."}))
    open_selecting(ui, address)
    for work in works:
        tick(ui, work)

    ui.page.click("#view .selection button.selection-hang")
    ui.page.locator("dialog.confirm[open]").wait_for()
    ui.page.click(".confirm-actions button:text-is('Hang')")

    said = ui.said_beside(ui.page.locator("#view .selection button.selection-hang"))
    assert said == f"Couldn't hang 2 works on {wall.name}: The wall is not taking a hang just now. Nothing was changed."
    expect(ui.page.locator(".selection-status")).to_have_text("2 selected.", use_inner_text=True)


def test_a_held_work_wikidata_finds_hangs_only_when_it_has_a_picture(ui, api, services, service, hangable):
    """The search folds in held works by Wikidata's item, named in their own words so the library's
    own listing does not find them: those rows know a picture only by `pictured_artwork_id`."""
    pictured = hangable("Jagers in de sneeuw", qid=HUNTERS)
    bare = service.add_artwork(title="Terugkeer van de kudde", wikidata_qid=HERD)
    wall = the_wall(services)
    open_selecting(ui, "#search?q=snow")
    tick(ui, pictured)
    tick(ui, bare)

    body = hang_from_after_question(ui, wall, left_out=1)

    expect(ui.page.locator(".selection-status")).to_have_text(f"Hung 1 work on {wall.name}.", use_inner_text=True)
    assert body == {"artwork_ids": [pictured.id]}
    assert hanging_on(api, wall.id) == [pictured.id]


def test_a_theme_s_page_keeps_one_hang_and_it_hangs_the_theme(ui, services, hangable):
    """A theme's page asks for a selection too, and its own *Hang…* hangs the theme: a second *Hang…* in
    the selection's acts would name two acts alike. The selection offers it only where the page asks."""
    work = hangable("Study A")
    theme = services.display.add_theme(name="Studies")
    services.display.add_to_theme(theme_id=theme.id, artwork_id=work.id)
    ui.open(f"#theme/{theme.id}")
    ui.page.locator("#view button.select-toggle:visible").wait_for()
    ui.page.click("#view button.select-toggle")

    expect(ui.page.locator("#view .selection button.selection-remove")).to_be_visible()
    expect(ui.page.locator("#view .selection button.selection-hang")).to_have_count(0)
    expect(ui.page.locator("#view button:text-is('Hang…')")).to_have_count(1)
