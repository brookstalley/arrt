"""Source plugins for the loader's tests, each named by an entry point the tests build.

Importable as `plugin_fakes` for the reason `fakes` is: the tests directory is on
the path, so an `EntryPoint` value such as `plugin_fakes:GOOD` loads exactly as an
installed plugin's would, through `EntryPoint.load`.
"""

from collections.abc import Sequence

from arrt.library.sources import (
    AcquisitionMethod,
    BrowseQuery,
    Declined,
    FetchLocator,
    FoundImage,
    ImageQuery,
    ImageQueryUnanswerable,
    OfferedGroup,
    SourceClass,
    SourceContext,
    SourceParts,
    SourcePlugin,
)


class StubFinder:
    """A finder that answers one image per query, or raises what it is told to."""

    def __init__(self, provider: str, *, raises: BaseException | None = None) -> None:
        self._provider = provider
        self._raises = raises

    @property
    def provider(self) -> str:
        return self._provider

    def find_images(self, query: ImageQuery) -> Sequence[FoundImage]:
        if self._raises is not None:
            raise self._raises
        return [
            FoundImage(
                url=f"https://{self._provider}.example/{query.title}",
                provider=self._provider,
                source_class=SourceClass.INSTITUTIONAL,
                acquisition_method=AcquisitionMethod.DIRECT_HTTP,
                title=query.title,
                artist=query.artist,
            )
        ]

    def fetch_preview(self, url: str) -> bytes | None:
        if self._raises is not None:
            raise self._raises
        return b"preview"


class StubReader:
    """A reader that answers a direct locator for any URL, or raises what it is told to."""

    def __init__(self, *, raises: BaseException | None = None, answer: object = None) -> None:
        self._raises = raises
        self._answer = answer

    def read(self, url: str) -> FetchLocator:
        if self._raises is not None:
            raise self._raises
        return self._answer if self._answer is not None else FetchLocator.direct(url)


def claims_example(url: str) -> bool:
    """The stub plugins' claims: anything on `example.org`."""
    return url.startswith("https://example.org/")


class StubCollection:
    """A collection that offers nothing, or raises what it is told to."""

    def __init__(self, provider: str, *, raises: BaseException | None = None) -> None:
        self._provider = provider
        self._raises = raises

    @property
    def provider(self) -> str:
        return self._provider

    def browse(self, queries: Sequence[BrowseQuery], *, per_query: int) -> Sequence[OfferedGroup]:
        if self._raises is not None:
            raise self._raises
        return []


def _good(context: SourceContext) -> SourceParts:
    return SourceParts(finder=StubFinder("good"), collection=StubCollection("good"))


def _other(context: SourceContext) -> SourceParts:
    return SourceParts(finder=StubFinder("other"))


def _faulty(context: SourceContext) -> SourceParts:
    return SourceParts(finder=StubFinder("faulty", raises=KeyError("a field the page no longer has")))


def _unanswerable(context: SourceContext) -> SourceParts:
    return SourceParts(finder=StubFinder("unanswerable", raises=ImageQueryUnanswerable("only by item")))


def _configured(context: SourceContext) -> SourceParts | Declined:
    if not context.environ.get("FAKE_SOURCE_KEY"):
        return Declined("FAKE_SOURCE_KEY is unset")
    return SourceParts(finder=StubFinder("configured"))


def _raising(context: SourceContext) -> SourceParts:
    raise RuntimeError("the factory could not reach its service")


def _misnamed(context: SourceContext) -> SourceParts:
    return SourceParts(finder=StubFinder("somebody-else"))


def _not_parts(context: SourceContext) -> object:
    return "a string"


GOOD = SourcePlugin(api_major=1, create=_good)
OTHER = SourcePlugin(api_major=1, create=_other)
FAULTY = SourcePlugin(api_major=1, create=_faulty)
UNANSWERABLE = SourcePlugin(api_major=1, create=_unanswerable)
CONFIGURED = SourcePlugin(api_major=1, create=_configured)
RAISING = SourcePlugin(api_major=1, create=_raising)
MISNAMED = SourcePlugin(api_major=1, create=_misnamed)
NOT_PARTS = SourcePlugin(api_major=1, create=_not_parts)
FUTURE = SourcePlugin(api_major=2, create=_good)
NOT_A_PLUGIN = object()


class RaisingProvider(StubFinder):
    """A finder whose `provider` raises: reading it runs the plugin's code."""

    @property
    def provider(self) -> str:
        raise RuntimeError("the provider property broke")


class Answers(StubFinder):
    """A finder that answers whatever it was built with, shape and all."""

    def __init__(self, provider: str, answer: object) -> None:
        super().__init__(provider)
        self._answer = answer

    def find_images(self, query: ImageQuery) -> object:
        return self._answer


def _raising_provider(context: SourceContext) -> SourceParts:
    return SourceParts(finder=RaisingProvider("x"))


def _not_a_finder(context: SourceContext) -> SourceParts:
    return SourceParts(finder="a string, not a finder")


def _reader_without_claims(context: SourceContext) -> SourceParts:
    return SourceParts(reader=StubReader())


def _claims_without_reader(context: SourceContext) -> SourceParts:
    return SourceParts(finder=StubFinder("claimer"))


def _leaky(context: SourceContext) -> SourceParts:
    raise RuntimeError("401 for url https://api.example.net/v1/search?key=sk-live-123&q=x")


RAISING_PROVIDER = SourcePlugin(api_major=1, create=_raising_provider)
NOT_A_FINDER = SourcePlugin(api_major=1, create=_not_a_finder)
READER_WITHOUT_CLAIMS = SourcePlugin(api_major=1, create=_reader_without_claims)
CLAIMS_WITHOUT_READER = SourcePlugin(api_major=1, create=_claims_without_reader, claims=claims_example)
LEAKY = SourcePlugin(api_major=1, create=_leaky)
