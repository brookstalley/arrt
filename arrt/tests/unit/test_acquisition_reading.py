"""Getting from the URL a Source carries to what is fetched, through the plugin that claims it.

The defect these descend from shipped because the two halves of that seam were
tested against different URL shapes and no test crossed between them: the fetch
path was exercised with an image-service URL nothing in the product ever records,
while the provider recorded object links nothing ever resolved. Every test here
is about the join: a recorded URL, the plugin that claims it, and what acquisition
then fetches.
"""

import logging
from contextlib import contextmanager
from io import BytesIO

import pytest
from fakes import FakeReader
from PIL import Image
from plugin_fakes import StubReader, claims_example

from arrt.library.acquisition.service import (
    AcquisitionOutcome,
    AcquisitionService,
    AcquisitionSettings,
    SourcePluginUnavailable,
)
from arrt.library.discovery.images import ImageSearchFailure
from arrt.library.sources import SourceContext
from arrt.library.sources.artic import claims as artic_claims
from arrt.library.sources.loading import SourceRoster, load_sources
from arrt.library.sources.reading import FetchLocator
from arrt.persistence.records import AcquisitionMethod, FetchStatus, RightsStatus, SourceClass

AN_OBJECT_PAGE = "https://www.artic.edu/artworks/91194/golden-bird"
AN_OBJECT_API_LINK = "https://api.artic.edu/api/v1/artworks/91194"
A_GOOGLE_PAGE = "https://artsandculture.google.com/asset/full-homage-to-the-square/abc"


def _jpeg() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (120, 80), (40, 40, 90)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _recording_stream(fetched: list[str], payload: bytes = b""):
    @contextmanager
    def open_stream(url: str):
        fetched.append(url)
        yield iter([payload])

    return open_stream


@pytest.fixture
def acq_settings(tmp_path) -> AcquisitionSettings:
    # A tile binary that does not exist, so nothing here can run the real
    # dezoomify-rs: a tiled fetch that gets as far as the binary is a deployment
    # fault, and these tests stop before it or assert that it was reached.
    return AcquisitionSettings(
        art_root=tmp_path,
        originals_path=tmp_path / "raw",
        tile_cache_path=tmp_path / "tile-cache",
        user_agent="arrt (test)",
        tile_binary="/nonexistent/dezoomify-rs",
        tile_max_pixels=8192,
        tile_timeout_seconds=30,
        max_image_bytes=10_000_000,
        min_free_bytes=1,
    )


def _acquisition(service, settings, roster: SourceRoster, *, fetched: list[str] | None = None, payload=b""):
    return AcquisitionService(
        service,
        settings,
        open_stream=_recording_stream([] if fetched is None else fetched, payload),
        route=roster.route,
        resolve=lambda _host: ["93.184.216.34"],
    )


def _work(service, *, url: str, provider: str = "artic", method=AcquisitionMethod.DEZOOMIFY):
    work = service.add_artwork(title="Golden Bird")
    source = service.add_source(
        artwork_id=work.id,
        url=url,
        provider=provider,
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=method,
        rights_status=RightsStatus.PUBLIC_DOMAIN,
        is_primary=True,
    )
    return work, source


# -- which plugin a URL needs ---------------------------------------------------


class TestTheArtInstitutesClaims:
    @pytest.mark.parametrize("url", [AN_OBJECT_PAGE, AN_OBJECT_API_LINK, "https://artic.edu/artworks/91194"])
    def test_both_shapes_it_records_are_claimed(self, url):
        """The declaration is the guard: without it the deployment fault below cannot fire."""
        assert artic_claims(url)

    @pytest.mark.parametrize(
        "url",
        [
            A_GOOGLE_PAGE,
            # Another site's artwork page: the path alone must not send its fetch to the museum.
            "https://gallery.example.com/artworks/91194",
            # An IIIF image service the tile fetcher reads as it is.
            "https://www.artic.edu/iiif/2/abc/info.json",
            "not a url",
        ],
    )
    def test_what_it_does_not_read_is_not_claimed(self, url):
        assert not artic_claims(url)


# -- acquisition through a reader ---------------------------------------------


class TestAClaimedUrlIsReadBeforeItIsFetched:
    def test_the_reader_is_asked_about_the_recorded_url(self, service, acq_settings):
        """The reader gets the source's URL, not the artwork or the source id."""
        reader = FakeReader(unreachable=True)
        roster = SourceRoster.of(readers={"artic": (artic_claims, reader)})
        work, _ = _work(service, url=AN_OBJECT_PAGE)

        _acquisition(service, acq_settings, roster).acquire(work.id)

        assert reader.asked == [AN_OBJECT_PAGE]

    def test_a_claimed_source_is_not_gated_on_its_recorded_url_being_reachable(self, service, acq_settings):
        """`Source.url` identifies the object. When a reader claims it, nothing fetches it.

        The recorded URL here resolves nowhere, and that must not stop the
        acquisition or be written against the source: its reachability says
        nothing about whether the image can be got. Gating on it produced a
        `failed` row naming a URL nobody would have fetched, and paid a DNS lookup
        per fetch to do it. Proven by reaching the reader, which is asked only
        after the dispatch; it then refuses, which keeps this off the network.
        """
        reader = FakeReader(unreachable=True)
        roster = SourceRoster.of(readers={"artic": (artic_claims, reader)})
        work, _ = _work(service, url=AN_OBJECT_API_LINK)

        def no_such_host(_host):
            raise OSError("no address associated with hostname")

        acquisition = AcquisitionService(
            service, acq_settings, open_stream=_recording_stream([]), route=roster.route, resolve=no_such_host
        )
        result = acquisition.acquire(work.id)

        assert reader.asked == [AN_OBJECT_API_LINK], "the unreachable recorded URL blocked the dispatch"
        assert "source URL was refused" not in (result.detail or "")

    def test_a_readers_words_reach_the_recorded_failure_without_their_query_string(self, service, acq_settings):
        failure = ImageSearchFailure("401 for url https://api.example.net/v1/x?key=sk-live-123")
        roster = SourceRoster.of(readers={"artic": (artic_claims, _Raises(failure))})
        work, _ = _work(service, url=AN_OBJECT_PAGE)

        result = _acquisition(service, acq_settings, roster).acquire(work.id)

        assert "api.example.net/v1/x?…" in result.detail
        assert "sk-live-123" not in result.detail

    def test_a_none_reason_carrying_a_key_reaches_neither_the_journal_nor_the_detail(self, service, acq_settings, caplog):
        reason = "no image at https://api.example.net/v1/object/7?key=sk-live-123"
        roster = SourceRoster.of(readers={"gallery": (claims_example, StubReader(answer=FetchLocator.none(reason)))})
        work, _ = _work(service, url="https://example.org/works/7", provider="gallery")

        with caplog.at_level(logging.INFO):
            result = _acquisition(service, acq_settings, roster).acquire(work.id)

        assert "api.example.net/v1/object/7?…" in result.detail
        assert "sk-live-123" not in result.detail
        assert not _records_mentioning("sk-live-123", caplog)

    def test_a_direct_url_carrying_a_key_is_fetched_whole_and_journalled_without_it(self, service, acq_settings, caplog):
        """The key is the fetch's business, so the fetch gets it; the journal and the detail do not."""
        fetched: list[str] = []
        url = "https://cdn.example.net/x.jpg?key=sk-live-123"
        roster = SourceRoster.of(readers={"gallery": (claims_example, StubReader(answer=FetchLocator.direct(url)))})
        work, _ = _work(service, url="https://example.org/works/7?key=sk-live-123", provider="gallery")

        with caplog.at_level(logging.INFO):
            ok = _acquisition(service, acq_settings, roster, fetched=fetched, payload=_jpeg()).acquire(work.id)
            refused = _acquisition(service, acq_settings, roster, fetched=[], payload=b"not an image").acquire(work.id)

        assert ok.outcome is AcquisitionOutcome.ACQUIRED
        assert fetched == [url]
        read = [r for r in caplog.records if getattr(r, "event", None) == "acquisition.source_read"]
        assert read and all(r.fetch_url == "https://cdn.example.net/x.jpg?…" for r in read)
        assert refused.outcome is not AcquisitionOutcome.ACQUIRED
        assert "sk-live-123" not in (refused.detail or "")
        assert not _records_mentioning("sk-live-123", caplog)

    def test_a_reader_that_could_not_ask_is_recorded_against_the_source(self, service, acq_settings):
        roster = SourceRoster.of(readers={"artic": (artic_claims, FakeReader(unreachable=True))})
        work, source = _work(service, url=AN_OBJECT_API_LINK)

        result = _acquisition(service, acq_settings, roster).acquire(work.id)

        assert result.outcome is AcquisitionOutcome.FAILED
        assert "the artic plugin could not read this source" in result.detail
        refreshed = next(s for s in service.list_sources(work.id) if s.id == source.id)
        assert refreshed.last_fetch_status is FetchStatus.FAILED

    def test_a_page_with_no_image_is_recorded_with_the_holders_reason(self, service, acq_settings):
        reader = FakeReader(answer=FetchLocator.none("the collection publishes no image of object 91194"))
        roster = SourceRoster.of(readers={"artic": (artic_claims, reader)})
        work, _ = _work(service, url=AN_OBJECT_PAGE)

        result = _acquisition(service, acq_settings, roster).acquire(work.id)

        assert result.outcome is AcquisitionOutcome.FAILED
        assert "found no image for this source: the collection publishes no image of object 91194" in result.detail

    def test_a_direct_answer_is_fetched_over_http_at_the_address_the_reader_gave(self, service, acq_settings):
        """Whatever method the source recorded: the reader decides how its page is fetched."""
        fetched: list[str] = []
        roster = SourceRoster.of(
            readers={"gallery": (claims_example, StubReader(answer=FetchLocator.direct("https://cdn.example.net/x.jpg")))}
        )
        work, _ = _work(service, url="https://example.org/works/7", provider="gallery")

        result = _acquisition(service, acq_settings, roster, fetched=fetched, payload=_jpeg()).acquire(work.id)

        assert result.outcome is AcquisitionOutcome.ACQUIRED
        assert fetched == ["https://cdn.example.net/x.jpg"]

    def test_an_address_the_reader_gave_is_checked_before_it_is_fetched(self, service, acq_settings):
        """An address this deployment did not record is exactly the kind to check."""
        fetched: list[str] = []
        roster = SourceRoster.of(
            readers={"gallery": (claims_example, StubReader(answer=FetchLocator.direct("http://127.0.0.1/admin")))}
        )
        work, _ = _work(service, url="https://example.org/works/7", provider="gallery")

        result = _acquisition(service, acq_settings, roster, fetched=fetched).acquire(work.id)

        assert result.outcome is AcquisitionOutcome.FAILED
        assert "the address the gallery plugin read was refused" in result.detail
        assert fetched == []

    @pytest.mark.plugin_fault_expected
    def test_a_reader_that_faults_is_recorded_and_never_falls_through_to_the_recorded_url(self, service, acq_settings):
        fetched: list[str] = []
        roster = SourceRoster.of(readers={"gallery": (claims_example, StubReader(raises=KeyError("img")))})
        work, _ = _work(service, url="https://example.org/works/7", provider="gallery", method=AcquisitionMethod.DIRECT_HTTP)

        result = _acquisition(service, acq_settings, roster, fetched=fetched).acquire(work.id)

        assert result.outcome is AcquisitionOutcome.FAILED
        assert "gallery plugin faulted" in result.detail
        assert fetched == [], "a faulting reader's URL was fetched as recorded"
        assert roster.observe()[0].faults == 1

    def test_the_first_plugin_in_order_reads_a_url_two_claim(self, service, acq_settings):
        first, second = FakeReader(unreachable=True), FakeReader(unreachable=True)
        roster = SourceRoster.of(readers={"first": (claims_example, first), "second": (claims_example, second)})
        work, _ = _work(service, url="https://example.org/works/7", provider="gallery")

        _acquisition(service, acq_settings, roster).acquire(work.id)

        assert (first.asked, second.asked) == (["https://example.org/works/7"], [])


class TestAUrlNobodyClaimsIsFetchedAsRecorded:
    def test_a_google_page_keeps_its_url(self, service, acq_settings, caplog):
        """Google Arts & Culture pages are readable by the tile fetcher as they are.

        Reaching the tile binary proves the dispatch handed it the recorded URL;
        the binary does not exist, which keeps this off the network.
        """
        roster = SourceRoster.of(readers={"artic": (artic_claims, FakeReader())})
        work, _ = _work(service, url=A_GOOGLE_PAGE, provider="google_arts_culture")

        with caplog.at_level(logging.INFO), pytest.raises(Exception, match="dezoomify"):
            _acquisition(service, acq_settings, roster).acquire(work.id)

        unclaimed = [r for r in caplog.records if getattr(r, "event", None) == "acquisition.unclaimed"]
        assert [r.provider for r in unclaimed] == ["google_arts_culture"]

    def test_a_direct_url_nobody_claims_is_fetched_as_it_stands(self, service, acq_settings):
        """A Commons image URL needs no plugin, configured or not."""
        fetched: list[str] = []
        url = "https://upload.wikimedia.org/wikipedia/commons/a/ab/Nighthawks.jpg"
        work, _ = _work(service, url=url, provider="commons", method=AcquisitionMethod.DIRECT_HTTP)

        result = _acquisition(service, acq_settings, SourceRoster.empty(), fetched=fetched, payload=_jpeg()).acquire(work.id)

        assert result.outcome is AcquisitionOutcome.ACQUIRED
        assert fetched == [url]


# -- a plugin that claims a URL and is not loaded -----------------------------


class TestAClaimedUrlWhosePluginIsNotLoaded:
    def test_is_a_deployment_fault_naming_the_plugin_and_its_reason(self, service, acq_settings):
        """The keyless deployment, which is what every seeded install starts as.

        Through the real loader and the real Art Institute plugin, declining for
        want of `ARTIC_USER_AGENT`, rather than a roster built to look like one.
        """
        roster = load_sources(SourceContext(environ={}, user_agent="arrt (test)", preview_max_bytes=1000))
        work, source = _work(service, url=AN_OBJECT_PAGE)

        with pytest.raises(SourcePluginUnavailable) as refusal:
            _acquisition(service, acq_settings, roster).acquire(work.id)

        assert "the artic source plugin is installed and not loaded" in str(refusal.value)
        assert "ARTIC_USER_AGENT is unset" in str(refusal.value)
        refreshed = next(s for s in service.list_sources(work.id) if s.id == source.id)
        assert refreshed.last_fetch_status is None, "a deployment fault must not be recorded against the source"

    def test_a_url_the_unloaded_plugin_does_not_claim_is_unaffected(self, service, acq_settings):
        """An IIIF service URL on the museum's host is read by the tile fetcher as it is."""
        roster = SourceRoster.of(unavailable={"artic": (artic_claims, "ARTIC_USER_AGENT is unset")})
        work, _ = _work(service, url="https://www.artic.edu/iiif/2/abc/info.json")

        with pytest.raises(Exception, match="dezoomify"):
            _acquisition(service, acq_settings, roster).acquire(work.id)


# -- the container's wiring ---------------------------------------------------


class TestTheContainerRoutesThroughItsRoster:
    """The wiring itself: the roster the container is given is the one acquisition routes through."""

    def test_the_services_reader_is_the_one_asked(self, services, sources):
        """`sources` is the shared fixture's roster; its Art Institute reader is a `FakeReader`.

        Made unreachable for this test, so the acquisition is recorded as failed
        without anything being fetched: the reader having been asked about the
        recorded URL is what shows the container routed through this roster.
        """
        reader = _fake_of(sources)
        reader.unreachable = True
        work, _ = _work(services.catalogue, url=AN_OBJECT_PAGE)

        result = services.acquisition.acquire(work.id)

        assert reader.asked == [AN_OBJECT_PAGE]
        assert result.outcome is AcquisitionOutcome.FAILED


def _records_mentioning(secret: str, caplog) -> list:
    """Every journal line carrying `secret`, in its message or in any field it was logged with."""
    return [record for record in caplog.records if secret in record.getMessage() or secret in repr(vars(record))]


class _Raises:
    def __init__(self, failure: Exception) -> None:
        self._failure = failure

    def read(self, url: str) -> FetchLocator:
        raise self._failure


def _fake_of(roster: SourceRoster) -> FakeReader:
    return roster.route(AN_OBJECT_PAGE).reader._inner  # the FakeReader behind the containment
