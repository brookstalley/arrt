"""Source plugins that misbehave on purpose, and one that does not, for `test_a_misbehaving_plugin.py`.

Written against `arrt.library.sources` alone, as a plugin from outside this
repository is. What `misbehaving` does on each call is `CONTROL.mode`, set by the
test; `steady` answers for the titles in `CONTROL.steady_holds`. A call that takes
time takes it on `CONTROL.clock`, the test's simulated time, so a deadline of
minutes is never waited out.
"""

import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Final, Protocol
from urllib.parse import quote, urlsplit

import arrt.library.sources
from arrt.library.sources import (
    AcquisitionMethod,
    FetchLocator,
    FoundImage,
    ImageQuery,
    ImageSearchFailure,
    RightsStatus,
    SourceClass,
    SourceContext,
    SourceParts,
    SourcePlugin,
)

#: How a plugin that must also load on an Arrt older than 1.6 takes `LinkGone`
#: (`docs/source-plugins.md` § Answers): there, a dead link reads as could not be asked.
LinkGone = getattr(arrt.library.sources, "LinkGone", ImageSearchFailure)

MISBEHAVING_HOST: Final = "misbehaving.example.org"
STEADY_HOST: Final = "steady.example.org"
PATIENT_HOST: Final = "patient.example.org"
GONE_HOST: Final = "gone.example.org"

#: The finder deadline `misbehaving` declares. Not the host's default (60 s, the
#: steady plugin's), so the test's clock can tell its calls from steady's by the
#: deadline it is asked to wait.
MISBEHAVING_FINDER_SECONDS: Final = 90.0
#: How long `misbehaving` takes when it hangs: past its deadline.
HANG_SECONDS: Final = 600.0
#: What `patient` declares, and takes: the host's ceiling, all of it.
PATIENT_FINDER_SECONDS: Final = 3600.0
#: What `overdue` declares: one second past the ceiling.
OVERDUE_FINDER_SECONDS: Final = 3601.0
#: A master size every wall accepts.
WIDTH: Final = 6949
HEIGHT: Final = 8400


class Clock(Protocol):
    def take(self, seconds: float) -> None:
        """Return once `seconds` have passed on the test's clock, or once the host has stopped waiting and the test lets go."""


@dataclass
class Control:
    """What the test steers, and what it reads back."""

    #: `answers`, `nothing`, `raises`, `hangs`, `wrong_type`, `oversized`, `not_a_list`,
    #: or `dead_link`: a dead link said the 1.5 way, as could-not-be-asked.
    mode: str = "answers"
    clock: Clock | None = None
    steady_holds: set[str] = field(default_factory=set)
    #: The titles `misbehaving` holds, in the modes that answer.
    misbehaving_holds: set[str] = field(default_factory=set)
    preview: bytes = b""
    #: Called by steady's finder on each call, before it answers: how a test acts in the middle of a run.
    on_steady_find: Callable[[ImageQuery], None] | None = None
    #: `misbehaving`'s finder calls that began, and those that came back (late ones included).
    entered: int = 0
    returned: int = 0
    #: `misbehaving`'s reader calls.
    reads: int = 0
    #: The titles whose every page `gone`'s finder says is gone; the rest it finds,
    #: on pages its reader then says are gone.
    gone_for: set[str] = field(default_factory=set)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def count(self, name: str) -> None:
        with self.lock:
            setattr(self, name, getattr(self, name) + 1)


CONTROL: Final = Control()


def _image(provider: str, host: str, query: ImageQuery, *, path: str = "works") -> FoundImage:
    url = f"https://{host}/{path}/{quote(query.title)}.jpg"
    return FoundImage(
        url=url,
        provider=provider,
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DIRECT_HTTP,
        title=query.title,
        artist=query.artist,
        preview_url=f"{url}?preview",
        estimated_width=WIDTH,
        estimated_height=HEIGHT,
        rights_status=RightsStatus.PUBLIC_DOMAIN,
    )


def _on(host: str) -> Callable[[str], bool]:
    def claims(url: str) -> bool:
        try:
            return (urlsplit(url).hostname or "") == host
        except ValueError:
            return False

    return claims


class _Reader:
    def __init__(self, *, raises: bool) -> None:
        self._raises = raises

    def read(self, url: str) -> FetchLocator:
        if self._raises:
            CONTROL.count("reads")
            message = "the page has no 'image' key"
            raise RuntimeError(message)
        return FetchLocator.direct(url)


class MisbehavingFinder:
    """Does what `CONTROL.mode` says, on every call."""

    @property
    def provider(self) -> str:
        return "misbehaving"

    def find_images(self, query: ImageQuery) -> object:  # noqa: PLR0911 -- one return per way of misbehaving
        CONTROL.count("entered")
        try:
            mode = CONTROL.mode
            if mode == "raises":
                raise KeyError("a field the page no longer has")
            if mode == "nothing":
                return []
            if mode == "hangs":
                if CONTROL.clock is None:
                    message = "the test gave the plugin no clock"
                    raise AssertionError(message)
                CONTROL.clock.take(HANG_SECONDS)
                # The late answer: an image, which nothing must ever record.
                return [_image("misbehaving", MISBEHAVING_HOST, query, path="late")]
            if mode == "wrong_type":
                found = _image("misbehaving", MISBEHAVING_HOST, query)
                return [FoundImage(**{**_fields(found), "estimated_width": str(WIDTH)})]
            if mode == "oversized":
                found = _image("misbehaving", MISBEHAVING_HOST, query)
                return [FoundImage(**{**_fields(found), "title": "x" * 5_000})]
            if mode == "not_a_list":
                return None
            if mode == "dead_link":
                # What a 1.5 plugin raises for a dead link: could not be asked.
                message = "every page the item links at the gallery answered 404"
                raise ImageSearchFailure(message)
            if query.title in CONTROL.misbehaving_holds:
                return [_image("misbehaving", MISBEHAVING_HOST, query)]
            return []
        finally:
            CONTROL.count("returned")

    def fetch_preview(self, url: str) -> bytes | None:
        return CONTROL.preview


def _fields(found: FoundImage) -> dict[str, object]:
    return {name: getattr(found, name) for name in FoundImage.__dataclass_fields__}


class SteadyFinder:
    """Answers at once, in the interface's own terms."""

    @property
    def provider(self) -> str:
        return "steady"

    def find_images(self, query: ImageQuery) -> Sequence[FoundImage]:
        if CONTROL.on_steady_find is not None:
            CONTROL.on_steady_find(query)
        return [_image("steady", STEADY_HOST, query)] if query.title in CONTROL.steady_holds else []

    def fetch_preview(self, url: str) -> bytes | None:
        return CONTROL.preview


class PatientFinder:
    """Takes the whole of its declared deadline, then answers."""

    @property
    def provider(self) -> str:
        return "patient"

    def find_images(self, query: ImageQuery) -> Sequence[FoundImage]:
        if CONTROL.clock is None:
            message = "the test gave the plugin no clock"
            raise AssertionError(message)
        CONTROL.clock.take(PATIENT_FINDER_SECONDS)
        return [_image("patient", PATIENT_HOST, query)]

    def fetch_preview(self, url: str) -> bytes | None:
        return CONTROL.preview


class GoneFinder:
    """Says every linked page is gone for the titles in `CONTROL.gone_for`; finds the rest."""

    @property
    def provider(self) -> str:
        return "gone"

    def find_images(self, query: ImageQuery) -> Sequence[FoundImage]:
        if query.title in CONTROL.gone_for:
            message = "every page the item links at the Gone Archive answered 404"
            raise LinkGone(message)
        return [_image("gone", GONE_HOST, query)]

    def fetch_preview(self, url: str) -> bytes | None:
        return CONTROL.preview


class _GoneReader:
    def read(self, url: str) -> FetchLocator:
        message = f"{url} answered 410"
        raise LinkGone(message)


def _misbehaving(context: SourceContext) -> SourceParts:
    # Its reader raises: a fault, outside the interface, on every read.
    return SourceParts(finder=MisbehavingFinder(), reader=_Reader(raises=True))


def _steady(context: SourceContext) -> SourceParts:
    return SourceParts(finder=SteadyFinder(), reader=_Reader(raises=False))


def _patient(context: SourceContext) -> SourceParts:
    return SourceParts(finder=PatientFinder())


def _overdue(context: SourceContext) -> SourceParts:
    message = "a plugin refused at load had its factory called"
    raise AssertionError(message)


def _gone(context: SourceContext) -> SourceParts:
    return SourceParts(finder=GoneFinder(), reader=_GoneReader())


MISBEHAVING: Final = SourcePlugin(
    api_major=1,
    api_minor=5,
    create=_misbehaving,
    claims=_on(MISBEHAVING_HOST),
    museum="Misbehaving Gallery",
    deadlines={"finder": MISBEHAVING_FINDER_SECONDS},
)
STEADY: Final = SourcePlugin(api_major=1, api_minor=4, create=_steady, claims=_on(STEADY_HOST), museum="Steady Museum")
PATIENT: Final = SourcePlugin(
    api_major=1, api_minor=5, create=_patient, museum="Patient Collection", deadlines={"finder": PATIENT_FINDER_SECONDS}
)
OVERDUE: Final = SourcePlugin(
    api_major=1, api_minor=5, create=_overdue, museum="Overdue Archive", deadlines={"finder": OVERDUE_FINDER_SECONDS}
)
GONE: Final = SourcePlugin(api_major=1, api_minor=6, create=_gone, claims=_on(GONE_HOST), museum="Gone Archive")
NEWER: Final = SourcePlugin(api_major=1, api_minor=7, create=_overdue, museum="Newer Archive")
