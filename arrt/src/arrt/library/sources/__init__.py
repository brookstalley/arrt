"""The interface a source plugin is written against, and the only one.

A plugin imports from here and nowhere else in `arrt`. Everything below is
re-exported from where Arrt keeps it, and anything a plugin reaches for elsewhere
in `arrt` is not part of the interface and may change in any release
(`source-plugins.md` § Versioning and errors). The built-in plugins beside this
file are held to the same rule by a test, because they are the examples an author
copies; the guide for writing one is `docs/source-plugins.md`.

The contracts each type carries are in its own docstring, not here: a copy here
would be a second statement free to disagree with the first.
"""

from arrt.library.discovery.browse import (
    BrowseQuery,
    CollectionBrowse,
    CollectionBrowseFailure,
    OfferedGroup,
)
from arrt.library.discovery.images import (
    DEFAULT_PREVIEW_MAX_BYTES,
    Finder,
    FoundImage,
    FoundPage,
    ImageQuery,
    ImageQueryUnanswerable,
    ImageSearchFailure,
)
from arrt.library.registry import ItemId, Registry, RegistryUnavailable
from arrt.library.sources.iiif import CanvasImage, ImageService, manifest_images, manifest_metadata
from arrt.library.sources.plugin import (
    API_VERSION,
    Declined,
    SourceContext,
    SourceFactory,
    SourceParts,
    SourcePlugin,
)
from arrt.library.sources.reading import FetchLocator, LocatorKind, Reader
from arrt.persistence.records import AcquisitionMethod, RightsStatus, SourceClass

__all__ = [
    "API_VERSION",
    "DEFAULT_PREVIEW_MAX_BYTES",
    "AcquisitionMethod",
    "BrowseQuery",
    "CanvasImage",
    "CollectionBrowse",
    "CollectionBrowseFailure",
    "Declined",
    "FetchLocator",
    "Finder",
    "FoundImage",
    "FoundPage",
    "ImageQuery",
    "ImageQueryUnanswerable",
    "ImageSearchFailure",
    "ImageService",
    "ItemId",
    "LocatorKind",
    "OfferedGroup",
    "Reader",
    "Registry",
    "RegistryUnavailable",
    "RightsStatus",
    "SourceClass",
    "SourceContext",
    "SourceFactory",
    "SourceParts",
    "SourcePlugin",
    "manifest_images",
    "manifest_metadata",
]
