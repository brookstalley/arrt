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
    FoundImage,
    ImageQuery,
    ImageQueryUnanswerable,
    OfferedGroup,
    SourceClass,
    SourceContext,
    SourceParts,
    SourcePlugin,
)


class FakeFinder:
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

    def tile_url(self, url: str) -> str:
        if self._raises is not None:
            raise self._raises
        return url


class FakeCollection:
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
    return SourceParts(finder=FakeFinder("good"), collection=FakeCollection("good"))


def _other(context: SourceContext) -> SourceParts:
    return SourceParts(finder=FakeFinder("other"))


def _faulty(context: SourceContext) -> SourceParts:
    return SourceParts(finder=FakeFinder("faulty", raises=KeyError("a field the page no longer has")))


def _unanswerable(context: SourceContext) -> SourceParts:
    return SourceParts(finder=FakeFinder("unanswerable", raises=ImageQueryUnanswerable("only by item")))


def _configured(context: SourceContext) -> SourceParts | Declined:
    if not context.environ.get("FAKE_SOURCE_KEY"):
        return Declined("FAKE_SOURCE_KEY is unset")
    return SourceParts(finder=FakeFinder("configured"))


def _raising(context: SourceContext) -> SourceParts:
    raise RuntimeError("the factory could not reach its service")


def _misnamed(context: SourceContext) -> SourceParts:
    return SourceParts(finder=FakeFinder("somebody-else"))


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
