"""The NGA as an image source, driven through the real client against recorded rows of its open data.

`tests/fixtures/nga/` holds real rows of NGA's `published_images.csv` and
`objects.csv` as published on 2026-10-06, header included (`nga-api-findings.md`).
The open data's host is a fake that serves them gzipped with an ETag, as GitHub
does; the clock and the idle timer are injected.
"""

import gzip
import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from fakes import FakeRegistry

from arrt.library.discovery.images import ImageQuery, ImageQueryUnanswerable, ImageSearchFailure
from arrt.library.discovery.phase_two import CONFIDENT, PhaseTwoEngine
from arrt.library.discovery.pool import ImageSourcePool
from arrt.library.registry import ItemId, WorkPage
from arrt.library.services.display_fit import ArtworkBox
from arrt.library.sources import Declined, FetchLocator, LocatorKind, SourceContext, SourceParts
from arrt.library.sources.nga import (
    DATA_URL,
    IDLE_SECONDS,
    PLUGIN,
    REFRESH_SECONDS,
    NgaCatalogue,
    NgaFinder,
    NgaReader,
    claims,
    object_id,
)
from arrt.persistence.discovery_records import UnresolvedReason
from arrt.persistence.records import AcquisitionMethod, RightsStatus

FIXTURES = Path(__file__).parent.parent / "fixtures" / "nga"
FILES = ("published_images.csv", "objects.csv")

#: Murillo's *Two Women at a Window* (Q3757652): open access, served in full at 17385 × 20855.
MURILLO_ITEM = ItemId("Q3757652")
MURILLO_PAGE = "https://www.nga.gov/collection/art-object-page.1185.html"
MURILLO_SERVICE = "https://api.nga.gov/iiif/099e8599-3242-46f4-bf5d-1a2e6032eb13"
#: Escher's *Square Limit*: served capped at 900, 3605 × 3659 (the capped service states 887 × 900).
SQUARE_LIMIT_PAGE = "https://www.nga.gov/collection/art-object-page.61287.html"
SQUARE_LIMIT_SERVICE = "https://api.nga.gov/iiif/44657ab0-8a2d-4c5a-b3f4-c47e5cda85ce__900"
ITEM = ItemId("Q1")


class Clock:
    def __init__(self, now: float = 1_800_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class Timers:
    """The idle timer, held rather than run: a test fires what is due."""

    def __init__(self) -> None:
        self.armed: list[tuple[float, Callable[[], None]]] = []

    def __call__(self, delay: float, call: Callable[[], None]) -> None:
        self.armed.append((delay, call))

    def fire(self) -> float:
        """Run the earliest armed timer, and say how long it was armed for."""
        delay, call = self.armed.pop(0)
        call()
        return delay


class Body(httpx.SyncByteStream):
    """A body that arrives as a stream, as one from the network does (a `content=` body is read on creation)."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def __iter__(self):
        yield self._data


def served(status: int, body: bytes = b"", **headers: str) -> httpx.Response:
    return httpx.Response(status, stream=Body(body), headers={key.replace("_", "-"): value for key, value in headers.items()})


class OpenData:
    """GitHub's raw host as it serves NGA's open data: gzipped, with an ETag, answering If-None-Match with 304."""

    def __init__(self) -> None:
        self.bodies = {name: (FIXTURES / name).read_bytes() for name in FILES}
        self.etags = {name: f'W/"{name}-1"' for name in FILES}
        self.asked: list[httpx.Request] = []
        #: name → a response to give instead, once per request while set.
        self.instead: dict[str, Callable[[httpx.Request], httpx.Response]] = {}
        self.gzipped = True

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(request)
        assert str(request.url).startswith(DATA_URL), f"asked a host the plugin is not about: {request.url}"
        name = request.url.path.rsplit("/", 1)[1]
        if name in self.instead:
            return self.instead[name](request)
        if request.headers.get("If-None-Match") == self.etags[name]:
            return httpx.Response(304, headers={"ETag": self.etags[name]})
        headers = {"ETag": self.etags[name], "Last-Modified": "Tue, 06 Oct 2026 10:00:47 GMT"}
        if not self.gzipped:
            return served(200, self.bodies[name], **headers)
        return served(200, gzip.compress(self.bodies[name]), **headers, Content_Encoding="gzip")

    def publish(self, name: str, body: bytes) -> None:
        """A new day's file, with a new ETag."""
        self.bodies[name] = body
        self.etags[name] = f'W/"{name}-{len(self.asked)}"'

    def files_asked(self) -> list[str]:
        return [r.url.path.rsplit("/", 1)[1] for r in self.asked]


@pytest.fixture
def world(tmp_path):
    """One deployment: its directory, the open data's host, the clock and the timers."""

    class World:
        directory = tmp_path / "sources" / "nga"
        data = OpenData()
        clock = Clock()
        timers = Timers()

        def catalogue(self) -> NgaCatalogue:
            return NgaCatalogue(
                directory=self.directory,
                user_agent="arrt-tests/0",
                transport=httpx.MockTransport(self.data.handler),
                clock=self.clock,
                schedule=self.timers,
            )

    return World()


def a_finder(catalogue: NgaCatalogue, pages: dict, preview=None) -> NgaFinder:
    transport = httpx.MockTransport(preview or (lambda r: httpx.Response(200, content=b"jpeg")))
    return NgaFinder(catalogue=catalogue, registry=FakeRegistry(pages=pages), user_agent="arrt-tests/0", transport=transport)


# -- claims ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "number"),
    [
        (MURILLO_PAGE, 1185),
        ("http://www.nga.gov/content/ngaweb/Collection/art-object-page.1185.html", 1185),
        ("https://www.nga.gov/content/ngaweb/Collection/art-object-page.46482.html", 46482),
        ("https://www.nga.gov/artworks/1185-two-women-window", 1185),
    ],
)
def test_the_plugin_claims_ngas_artwork_pages_in_the_shapes_wikidata_records(url, number):
    assert claims(url)
    assert object_id(url) == number


@pytest.mark.parametrize(
    "url",
    [
        "https://www.nga.gov.example.com/collection/art-object-page.1185.html",
        "https://nga.gov/collection/art-object-page.1185.html",
        "https://www.nga.gov:8443/collection/art-object-page.1185.html",
        "ftp://www.nga.gov/collection/art-object-page.1185.html",
        "https://www.nga.gov/collection/art-object-page.1185.html?x=1",
        "https://www.nga.gov/collection/art-object-page.1185.html#top",
        "https://www.nga.gov/collection/provenance-info.1185.html",
        "https://www.nga.gov/collection/artist-info.1185.html",
        "https://www.nga.gov/artworks/1185",
        "https://www.nga.gov/collection/art-object-page.0.html",
        "https://www.nga.gov/collection/art-object-page.abc.html",
        "https://kress.nga.gov/Detail/objects/1185",
        "https://api.nga.gov/iiif/099e8599-3242-46f4-bf5d-1a2e6032eb13/info.json",
        "not a url",
        "http://[::1",
    ],
)
def test_the_plugin_refuses_another_host_another_page_and_another_shape(url):
    assert not claims(url)


# -- the copy: downloaded once a day, kept gzipped, parsed when asked, released when idle --


def test_nothing_is_downloaded_or_read_until_a_query_asks(world):
    catalogue = world.catalogue()

    assert world.data.asked == []
    assert not catalogue.loaded
    assert not world.directory.exists()


def test_the_first_query_downloads_both_files_and_keeps_them_gzipped_as_served(world):
    catalogue = world.catalogue()

    entry = catalogue.entry(1185)

    assert sorted(world.data.files_asked()) == sorted(FILES)
    for name in FILES:
        stored = world.directory / f"{name}.gz"
        assert gzip.decompress(stored.read_bytes()) == world.data.bodies[name]
    assert {r.headers["User-Agent"] for r in world.data.asked} == {"arrt-tests/0"}
    assert (entry.title, entry.attribution) == ("Two Women at a Window", "Bartolomé Esteban Murillo")
    assert catalogue.loaded


def test_a_file_served_plain_is_kept_gzipped_all_the_same(world):
    world.data.gzipped = False

    world.catalogue().entry(1185)

    assert gzip.decompress((world.directory / "objects.csv.gz").read_bytes()) == world.data.bodies["objects.csv"]


def test_a_second_query_within_the_day_asks_nothing(world):
    catalogue = world.catalogue()
    catalogue.entry(1185)
    world.clock.advance(REFRESH_SECONDS - 1)

    catalogue.entry(46482)

    assert len(world.data.asked) == 2


def test_after_a_day_the_files_are_asked_for_conditionally_and_a_304_downloads_nothing(world):
    catalogue = world.catalogue()
    catalogue.entry(1185)
    index = catalogue._index
    world.clock.advance(REFRESH_SECONDS)

    catalogue.entry(1185)

    later = world.data.asked[2:]
    assert sorted(r.url.path.rsplit("/", 1)[1] for r in later) == sorted(FILES)
    for request in later:
        name = request.url.path.rsplit("/", 1)[1]
        assert request.headers["If-None-Match"] == world.data.etags[name]
        assert request.headers["If-Modified-Since"] == "Tue, 06 Oct 2026 10:00:47 GMT"
    assert catalogue._index is index, "a 304 keeps the parsed copy; nothing is read again"
    world.clock.advance(REFRESH_SECONDS - 1)
    catalogue.entry(1185)
    assert len(world.data.asked) == 4, "a 304 counts as the day's check"


def test_a_new_days_file_replaces_the_copy_and_is_read_again(world):
    catalogue = world.catalogue()
    assert catalogue.entry(1185).title == "Two Women at a Window"
    renamed = world.data.bodies["objects.csv"].replace(b"Two Women at a Window", b"Two Women at the Window")
    world.data.publish("objects.csv", renamed)
    world.clock.advance(REFRESH_SECONDS)

    assert catalogue.entry(1185).title == "Two Women at the Window"
    assert gzip.decompress((world.directory / "objects.csv.gz").read_bytes()) == renamed


@pytest.mark.parametrize(
    "failure",
    [
        lambda r: served(503, b"unavailable"),
        lambda r: served(302, Location="https://example.com/"),
        lambda r: served(200, b"<html>rate limited</html>"),
        lambda r: served(200, gzip.compress(b"a,b\n1,2\n"), Content_Encoding="gzip"),
        lambda r: served(200, b"not gzip", Content_Encoding="gzip"),
        lambda r: served(200, gzip.compress(Path(FIXTURES / "objects.csv").read_bytes())[:-40], Content_Encoding="gzip"),
        lambda r: (_ for _ in ()).throw(httpx.ConnectError("refused", request=r)),
    ],
    ids=["503", "redirect", "a page", "other columns", "broken gzip", "gzip cut short past its rows", "network"],
)
def test_a_failed_refresh_keeps_yesterdays_file_and_its_index_and_waits_a_day(world, failure):
    catalogue = world.catalogue()
    catalogue.entry(1185)
    yesterday = (world.directory / "objects.csv.gz").read_bytes()
    world.clock.advance(REFRESH_SECONDS)
    world.data.instead["objects.csv"] = failure

    entry = catalogue.entry(1185)

    assert entry.title == "Two Women at a Window"
    assert (world.directory / "objects.csv.gz").read_bytes() == yesterday
    assert not [p for p in world.directory.iterdir() if p.name.endswith(".part")], "no half-written file is left"
    asked = len(world.data.asked)
    world.clock.advance(60)
    catalogue.entry(1185)
    assert len(world.data.asked) == asked, "a failed day is not asked again until the next"


def test_with_no_copy_a_failed_download_could_not_be_asked_and_the_next_query_tries_again(world):
    world.data.instead["published_images.csv"] = lambda r: served(503)
    catalogue = world.catalogue()

    with pytest.raises(ImageSearchFailure, match="could not be got"):
        catalogue.entry(1185)
    assert not catalogue.loaded

    del world.data.instead["published_images.csv"]
    assert catalogue.entry(1185) is not None


def test_a_copy_on_disk_that_cannot_be_read_could_not_be_asked(world):
    world.catalogue().entry(1185)
    (world.directory / "published_images.csv.gz").write_bytes(b"damaged")

    with pytest.raises(ImageSearchFailure, match="on disk could not be read"):
        world.catalogue().entry(1185)


def test_a_state_file_that_cannot_be_written_leaves_the_copy_working(world, monkeypatch, caplog):
    """The next process then asks a day early, and no more."""

    def refuse(path, content):
        raise OSError("read-only")

    monkeypatch.setattr("arrt.library.sources.nga._write_atomically", refuse)

    entry = world.catalogue().entry(1185)

    assert entry.title == "Two Women at a Window"
    assert "nga.state_unwritten" in {getattr(record, "event", None) for record in caplog.records}


def test_a_restart_reads_the_copy_on_disk_without_downloading(world):
    world.catalogue().entry(1185)
    world.clock.advance(60)

    restarted = world.catalogue()
    entry = restarted.entry(1185)

    assert len(world.data.asked) == 2
    assert entry.uuid == "099e8599-3242-46f4-bf5d-1a2e6032eb13"
    state = json.loads((world.directory / "state.json").read_text())
    assert set(state) == set(FILES)


def test_the_copy_is_released_after_six_hours_with_no_query(world):
    catalogue = world.catalogue()
    catalogue.entry(1185)
    assert len(world.timers.armed) == 1

    world.clock.advance(IDLE_SECONDS)
    assert world.timers.fire() == IDLE_SECONDS

    assert not catalogue.loaded
    assert world.timers.armed == [], "a released copy arms nothing"
    catalogue.entry(1185)
    assert catalogue.loaded, "the next query reads it from disk again"
    assert len(world.data.asked) == 2, "and downloads nothing within the day"


def test_a_query_inside_the_six_hours_keeps_the_copy_and_the_timer_waits_out_the_rest(world):
    catalogue = world.catalogue()
    catalogue.entry(1185)
    world.clock.advance(IDLE_SECONDS - 3600)
    catalogue.entry(46482)
    assert len(world.timers.armed) == 1, "one timer, not one per query"

    world.clock.advance(3600)
    world.timers.fire()

    assert catalogue.loaded, "five hours since the last query is not six"
    delay, _ = world.timers.armed[0]
    assert delay == IDLE_SECONDS - 3600
    world.clock.advance(delay)
    world.timers.fire()
    assert not catalogue.loaded


def test_a_month_with_no_query_costs_no_download_and_no_memory(world):
    catalogue = world.catalogue()
    catalogue.entry(1185)
    world.clock.advance(IDLE_SECONDS)
    world.timers.fire()
    asked = len(world.data.asked)

    world.clock.advance(30 * 24 * 3600)

    assert not catalogue.loaded
    assert world.timers.armed == []
    assert len(world.data.asked) == asked


# -- what the copy says ------------------------------------------------------------------


def test_the_primary_image_is_read_and_an_alternate_listed_before_it_is_not(world):
    """Object 50023's alternate views sort before its primary image in the file."""
    entry = world.catalogue().entry(50023)

    assert entry.uuid == "b149b783-e9fb-44af-9cbb-3c3d2ee74f88"


def test_of_two_primary_images_of_one_object_the_first_in_the_file_is_read(world):
    """177 objects list more than one primary image, all at sequence 0; the file's first is taken, every day alike."""
    lines = world.data.bodies["published_images.csv"].decode().splitlines(keepends=True)
    murillo = next(line for line in lines if line.startswith("099e8599"))
    second = murillo.replace("099e8599-3242-46f4-bf5d-1a2e6032eb13", "ffffffff-3242-46f4-bf5d-1a2e6032eb13")
    world.data.publish("published_images.csv", "".join([*lines, second]).encode())

    assert world.catalogue().entry(1185).uuid == "099e8599-3242-46f4-bf5d-1a2e6032eb13"


def test_a_download_larger_than_the_bound_is_a_failed_refresh(world, monkeypatch):
    monkeypatch.setattr("arrt.library.sources.nga._MAX_DOWNLOAD_BYTES", 100)

    with pytest.raises(ImageSearchFailure, match="larger than 100 bytes"):
        world.catalogue().entry(1185)
    assert not world.directory.joinpath("published_images.csv.gz").exists()


def test_a_row_cut_short_is_skipped_and_the_rest_of_the_file_is_read(world):
    """A primary image's row ending before its sizes reads as None fields, never as a fault."""
    body = (
        world.data.bodies["published_images.csv"] + b"aaaaaaaa-0000-4000-8000-000000000000,https://api.nga.gov/iiif/x,,primary\n"
    )
    world.data.publish("published_images.csv", body)
    catalogue = world.catalogue()

    assert catalogue.entry(1185).title == "Two Women at a Window"


def test_a_download_the_last_process_did_not_finish_is_removed_at_the_first_query(world):
    world.directory.mkdir(parents=True)
    debris = world.directory / ".published_images.csv.gz.abc123.part"
    debris.write_bytes(b"half a download")

    world.catalogue().entry(1185)

    assert not debris.exists()
    assert sorted(p.name for p in world.directory.iterdir()) == ["objects.csv.gz", "published_images.csv.gz", "state.json"]


def test_each_request_for_the_open_data_is_logged_before_it_is_made(world, caplog):
    """The first download of a day holds the run asking; the journal says so before it starts."""
    caplog.set_level("INFO", logger="arrt.library.sources.nga")
    catalogue = world.catalogue()
    catalogue.entry(1185)
    world.clock.advance(REFRESH_SECONDS)
    catalogue.entry(1185)

    requested = [(r.file, r.conditional) for r in caplog.records if getattr(r, "event", None) == "nga.catalogue_requested"]
    assert sorted(requested) == sorted([(name, False) for name in FILES] + [(name, True) for name in FILES])


def test_an_object_with_no_image_in_the_open_data_has_no_entry(world):
    """*Metamorphosis II* (46828) has an objects row and no image."""
    assert world.catalogue().entry(46828) is None


# -- finding by Wikidata item ------------------------------------------------------------


def test_an_open_image_is_found_under_the_items_page_at_the_originals_size_through_the_tiles(world):
    pages = {MURILLO_ITEM: [WorkPage("https://www.moma.org/collection/works/1"), WorkPage(MURILLO_PAGE)]}

    (image,) = a_finder(world.catalogue(), pages).find_images(ImageQuery(title="Two Women at a Window", qid=MURILLO_ITEM))

    assert image.url == MURILLO_PAGE
    assert (image.provider, image.title, image.artist) == ("nga", "Two Women at a Window", "Bartolomé Esteban Murillo")
    assert (image.estimated_width, image.estimated_height) == (17385, 20855)
    assert image.acquisition_method is AcquisitionMethod.DEZOOMIFY
    assert image.rights_status is RightsStatus.PUBLIC_DOMAIN
    assert image.preview_url == f"{MURILLO_SERVICE}/full/!400,400/0/default.jpg"


def test_a_capped_image_is_the_placeholder_at_the_capped_services_size_and_its_rights_unknown(world):
    (image,) = a_finder(world.catalogue(), {ITEM: [WorkPage(SQUARE_LIMIT_PAGE)]}).find_images(ImageQuery(title="x", qid=ITEM))

    assert (image.estimated_width, image.estimated_height) == (887, 900)
    assert image.acquisition_method is AcquisitionMethod.DIRECT_HTTP
    assert image.rights_status is RightsStatus.UNKNOWN, "openaccess=0 is never recorded as in copyright"
    assert image.preview_url == f"{SQUARE_LIMIT_SERVICE}/full/!400,400/0/default.jpg"
    assert image.artist == "M.C. Escher"


def test_an_uncapped_image_that_is_not_open_access_is_served_in_full_with_its_rights_unknown(world):
    """159799 is `openaccess=0` with no `maxpixels`: served in full (measured), and it has no objects row."""
    catalogue = world.catalogue()

    entry = catalogue.entry(159799)

    assert (entry.maxpixels, entry.open_access, entry.served_size) == (None, False, (5404, 1164))
    assert NgaReader(catalogue=catalogue).read("https://www.nga.gov/collection/art-object-page.159799.html") == (
        FetchLocator.tiles("https://api.nga.gov/iiif/714dfad3-0508-4d48-82b8-6cb690c6164c/info.json")
    )


def test_an_object_whose_title_the_open_data_lacks_is_not_offered(world):
    """No title of NGA's own means nothing for the identity check to read, so no image."""
    page = WorkPage("https://www.nga.gov/collection/art-object-page.159799.html")

    assert a_finder(world.catalogue(), {ITEM: [page]}).find_images(ImageQuery(title="x", qid=ITEM)) == []


def test_the_items_page_identifies_the_work_through_the_identity_check_with_the_artist_matched(world):
    registry = FakeRegistry(pages={MURILLO_ITEM: [WorkPage(MURILLO_PAGE)]})
    finder = NgaFinder(catalogue=world.catalogue(), registry=registry, user_agent="t")
    box = ArtworkBox(width=3840, height=2160, pixels_per_inch=104.9, floor_inches=12.0)
    engine = PhaseTwoEngine(ImageSourcePool([finder]), box=box, registry=registry)

    # A title NGA does not use (the Spanish one), so only the item's link can identify it.
    resolution = engine.resolve(ImageQuery(title="Mujeres en la ventana", artist="Bartolomé Esteban Murillo", qid=MURILLO_ITEM))

    (entry,) = resolution.instances
    assert entry.found.url == MURILLO_PAGE
    assert entry.confidence == CONFIDENT
    assert "Wikidata item records" in entry.rationale
    assert not entry.below_floor


def test_another_artists_object_on_the_items_page_is_refused_by_the_identity_check(world):
    registry = FakeRegistry(pages={MURILLO_ITEM: [WorkPage(MURILLO_PAGE)]})
    finder = NgaFinder(catalogue=world.catalogue(), registry=registry, user_agent="t")
    box = ArtworkBox(width=3840, height=2160, pixels_per_inch=104.9, floor_inches=12.0)
    engine = PhaseTwoEngine(ImageSourcePool([finder]), box=box, registry=registry)

    resolution = engine.resolve(ImageQuery(title="Two Women at a Window", artist="Diego Velázquez", qid=MURILLO_ITEM))

    assert list(resolution.instances) == []
    assert UnresolvedReason.IDENTITY_REFUSED in resolution.refusals


def test_two_pages_for_one_object_read_it_once_under_the_first_the_registry_gives(world):
    other = WorkPage("https://www.nga.gov/content/ngaweb/Collection/art-object-page.1185.html")
    registry = FakeRegistry(pages={ITEM: [WorkPage(MURILLO_PAGE), other]})
    first = registry.pages_about(ITEM)[0]
    finder = NgaFinder(catalogue=world.catalogue(), registry=registry, user_agent="t")

    found = finder.find_images(ImageQuery(title="x", qid=ITEM))

    assert [image.url for image in found] == [first]


def test_an_item_naming_no_nga_page_holds_nothing_and_downloads_nothing(world):
    pages = {ITEM: [WorkPage("https://www.moma.org/collection/works/1")]}

    assert a_finder(world.catalogue(), pages).find_images(ImageQuery(title="x", qid=ITEM)) == []
    assert world.data.asked == [], "a work NGA is not asked about costs no download"


def test_an_item_recording_more_than_ten_nga_pages_reads_ten_objects(world):
    catalogue = world.catalogue()
    asked: list[int] = []
    real = catalogue.entry

    def counting(number: int):
        asked.append(number)
        return real(number)

    catalogue.entry = counting
    pages = {ITEM: [WorkPage(f"https://www.nga.gov/collection/art-object-page.{1000 + n}.html") for n in range(12)]}

    a_finder(catalogue, pages).find_images(ImageQuery(title="x", qid=ITEM))

    assert len(asked) == 10


@pytest.mark.parametrize(
    "query", [ImageQuery(title="Two Women at a Window"), ImageQuery(title="x", qid=MURILLO_ITEM)], ids=["no item", "no registry"]
)
def test_a_work_with_no_item_or_a_deployment_with_no_registry_cannot_be_asked(world, query):
    registry = FakeRegistry() if query.qid is None else None
    finder = NgaFinder(catalogue=world.catalogue(), registry=registry, user_agent="t")

    with pytest.raises(ImageQueryUnanswerable):
        finder.find_images(query)
    assert world.data.asked == []


def test_a_registry_that_cannot_be_asked_is_a_search_that_could_not_be_asked(world):
    finder = NgaFinder(catalogue=world.catalogue(), registry=FakeRegistry(failing=True), user_agent="t")

    with pytest.raises(ImageSearchFailure, match="Wikidata could not be asked"):
        finder.find_images(ImageQuery(title="x", qid=ITEM))


# -- previews ----------------------------------------------------------------------------


def test_a_preview_is_read_from_the_iiif_host_only_and_under_the_ceiling(world):
    preview = f"{MURILLO_SERVICE}/full/!400,400/0/default.jpg"
    big = httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * 100))
    catalogue = world.catalogue()

    small = NgaFinder(catalogue=catalogue, registry=None, user_agent="t", transport=big, preview_max_bytes=50)
    assert small.fetch_preview(preview) is None
    roomy = NgaFinder(catalogue=catalogue, registry=None, user_agent="t", transport=big)
    assert roomy.fetch_preview(preview) == b"x" * 100
    assert roomy.fetch_preview("https://example.com/iiif/x/full/!400,400/0/default.jpg") is None
    assert roomy.fetch_preview("http://api.nga.gov/iiif/x/full/!400,400/0/default.jpg") is None
    assert roomy.fetch_preview("https://api.nga.gov/elsewhere/x.jpg") is None


def test_a_preview_redirect_is_not_followed(world):
    asked: list[httpx.Request] = []

    def redirect(request: httpx.Request) -> httpx.Response:
        asked.append(request)
        return httpx.Response(303, headers={"Location": "https://example.com/x.jpg"})

    finder = NgaFinder(catalogue=world.catalogue(), registry=None, user_agent="t", transport=httpx.MockTransport(redirect))

    assert finder.fetch_preview(f"{MURILLO_SERVICE}/full/!400,400/0/default.jpg") is None
    assert {r.url.host for r in asked} == {"api.nga.gov"}


# -- reading -----------------------------------------------------------------------------


def test_the_reader_reads_an_open_image_to_its_tiles_and_a_capped_one_to_the_capped_copy(world):
    reader = NgaReader(catalogue=world.catalogue())

    assert reader.read(MURILLO_PAGE) == FetchLocator.tiles(f"{MURILLO_SERVICE}/info.json")
    assert reader.read(SQUARE_LIMIT_PAGE) == FetchLocator.direct(f"{SQUARE_LIMIT_SERVICE}/full/full/0/default.jpg")


def test_the_reader_says_none_for_an_object_with_no_image_and_refuses_a_url_it_does_not_claim(world):
    reader = NgaReader(catalogue=world.catalogue())

    assert reader.read("https://www.nga.gov/collection/art-object-page.46828.html").kind is LocatorKind.NONE
    with pytest.raises(ImageSearchFailure):
        reader.read("https://www.nga.gov/collection/provenance-info.1185.html")


# -- the plugin --------------------------------------------------------------------------


def test_the_plugin_declines_without_a_directory_of_its_own():
    answer = PLUGIN.create(SourceContext(environ={}, user_agent="t", preview_max_bytes=1, registry=FakeRegistry()))

    assert isinstance(answer, Declined)
    assert "1.2" in answer.reason


def test_the_plugin_finds_with_a_registry_reads_without_one_and_shares_one_copy(tmp_path):
    with_registry = PLUGIN.create(
        SourceContext(environ={}, user_agent="t", preview_max_bytes=1, registry=FakeRegistry(), data_dir=tmp_path)
    )
    without = PLUGIN.create(SourceContext(environ={}, user_agent="t", preview_max_bytes=1, data_dir=tmp_path))

    assert isinstance(with_registry, SourceParts)
    assert with_registry.finder.provider == "nga"
    assert with_registry.finder._catalogue is with_registry.reader._catalogue
    assert isinstance(without, SourceParts)
    assert without.finder is None, "with no registry it cannot find a work, so it is not an image source"
    assert without.reader is not None
    assert PLUGIN.claims is claims
    assert not tmp_path.joinpath("published_images.csv.gz").exists(), "building the plugin downloads nothing"
