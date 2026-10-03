"""What a source plugin hands Arrt, and what Arrt hands it back.

A plugin is a Python distribution that registers one entry point in the
`arrt.sources` group. The entry point's name is the plugin's name, and the object
it names is a `SourcePlugin`: the interface major it was written for, and a
factory. Arrt calls the factory once at startup with a `SourceContext`, and the
factory answers with the plugin's parts or declines with a reason
(`source-plugins.md` § Loading).

The types are frozen and carry no behaviour, because they are the part of the
interface a plugin author reads first, and everything Arrt does with them belongs
to the loader.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final

from arrt.library.discovery.browse import CollectionBrowse
from arrt.library.discovery.images import Finder
from arrt.library.registry import Registry
from arrt.library.sources.reading import Reader

#: The interface version this Arrt provides, as `(major, minor)`. A plugin
#: declares the major it was written for, and one written for any other major is
#: refused by name rather than loaded: an in-process interface that changed shape
#: under a plugin fails inside a run, where nobody is looking. A minor release
#: only adds optional capabilities, so a plugin written for an older minor loads.
API_VERSION: Final[tuple[int, int]] = (1, 0)


@dataclass(frozen=True, slots=True)
class SourceContext:
    """What Arrt gives a plugin's factory.

    **The environment is the plugin's own configuration**, read-only. Arrt's
    settings cannot carry a field for a plugin nobody here has written, so a
    plugin documents the variables it reads and reads them from here. Passed in,
    rather than read from `os.environ`, so a plugin can be built for a test
    against a deployment that is not the process's own.
    """

    environ: Mapping[str, str]
    #: How this deployment names itself to the sites it fetches from
    #: (`ACQUISITION_USER_AGENT`, with a truthful default). A plugin whose site
    #: asks callers to identify themselves with a contact address reads its own
    #: variable instead, as the Art Institute's does, and declines without it.
    user_agent: str
    #: The largest preview body a finder may read before refusing it. A plugin's
    #: `fetch_preview` must bound what it reads (the `Finder` protocol says why),
    #: and this is the bound this deployment chose.
    preview_max_bytes: int
    #: Wikidata, when this deployment has named itself to it, else `None`. A
    #: plugin that needs the registry declines without one.
    registry: Registry | None = None


@dataclass(frozen=True, slots=True)
class SourceParts:
    """What a loaded plugin provides: any of a finder, a reader, and a collection to browse.

    **The finder's `provider` must be the plugin's name.** It is what every image
    the finder reports is recorded under, so a stored source row names the plugin
    that found it, and a deployment that uninstalls that plugin can be told which
    one its rows need.
    """

    finder: Finder | None = None
    #: Reads the URLs the plugin claims (`SourcePlugin.claims`). A plugin with a
    #: reader declares what it claims, and one that claims URLs provides a reader.
    reader: Reader | None = None
    collection: CollectionBrowse | None = None

    def __post_init__(self) -> None:
        if self.finder is None and self.reader is None and self.collection is None:
            # A plugin with nothing to offer that still loads would read as a
            # source on every startup line and answer nothing. Declining says why.
            raise ValueError("A plugin's parts need a finder, a reader or a collection; decline with a reason instead.")


@dataclass(frozen=True, slots=True)
class Declined:
    """A factory's answer when this deployment has not configured the plugin.

    Not a failure. The Art Institute's plugin declines when `ARTIC_USER_AGENT` is
    unset, because asking the museum anonymously would misrepresent whoever runs
    this. The reason is logged at startup, so "why is this source missing" is
    answered where the operator first looks.
    """

    reason: str


#: The factory an entry point's `SourcePlugin` carries. It may raise; the loader
#: leaves a plugin whose factory raises out, and says so.
SourceFactory = Callable[[SourceContext], SourceParts | Declined]


@dataclass(frozen=True, slots=True)
class SourcePlugin:
    """The object an `arrt.sources` entry point names."""

    #: The interface major this plugin was written for (`API_VERSION[0]`).
    api_major: int
    create: SourceFactory
    #: Whether a URL is one this plugin's reader reads. **Static: no I/O, and no
    #: configuration**, because Arrt asks it of plugins that declined as well as of
    #: those that loaded. A source this plugin must read, recorded while it was
    #: configured, then reaches a deployment fault naming the plugin and its
    #: reason, rather than a fetch of a page no fetcher can read.
    claims: Callable[[str], bool] | None = None
