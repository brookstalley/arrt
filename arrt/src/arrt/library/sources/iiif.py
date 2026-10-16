"""Reading IIIF answers a plugin has fetched: an image service's `info.json`, and a manifest's canvases.

Part of the plugin interface since 1.3. Museums that publish IIIF reach their
image services by different roads (a manifest, a Linked Art record, a page), and
what they share is the last step: what the service says about the original, and
whether one request fetches it or its tiles must be walked
(`linked-art-findings.md`). These are that step.

**Nothing here does I/O.** A plugin fetches with its own bounded client, asks only
its own hosts, and checks that a service is on a host it trusts before reading
it: Arrt checks the address of the locator a reader returns, not the requests a
plugin makes (`docs/source-plugins.md` § What Arrt does for you). A parser that
fetched would put a request policy inside the interface.

A body that is not the shape expected raises `ImageSearchFailure`, because an
answer that is not a IIIF answer has said nothing about what the holder has.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from arrt.library.discovery.images import ImageSearchFailure
from arrt.library.sources.reading import FetchLocator

#: The two Image API versions read, which differ in how a service names itself,
#: where it declares its limits, and how it asks for the largest size.
_V2: Final[int] = 2
_V3: Final[int] = 3

_IMAGE_CONTEXTS: Final[Mapping[str, int]] = {
    "http://iiif.io/api/image/2/context.json": _V2,
    "http://iiif.io/api/image/3/context.json": _V3,
}

#: The services a canvas's image may name, by the `@type`/`type` each version writes.
_SERVICE_TYPES: Final[frozenset[str]] = frozenset({"ImageService2", "ImageService3", "iiif:ImageProfile"})


def _positive(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _http_url(value: object) -> str | None:
    return value if isinstance(value, str) and value.startswith(("https://", "http://")) else None


def _version(context: object) -> int | None:
    """The Image API version an `@context` names, alone or among others; None for any other."""
    contexts = context if isinstance(context, list) else [context]
    versions = {_IMAGE_CONTEXTS[c] for c in contexts if isinstance(c, str) and c in _IMAGE_CONTEXTS}
    return versions.pop() if len(versions) == 1 else None


@dataclass(frozen=True, slots=True)
class ImageService:
    """A IIIF image service as its `info.json` describes it: the original's size, and any cap it declares."""

    #: The service's base URI, as the service names itself (`@id` in version 2, `id` in 3).
    id: str
    #: The Image API version, 2 or 3.
    version: int
    #: The original's size, in pixels.
    width: int
    height: int
    #: The largest request the service declares it serves, where it declares one.
    max_width: int | None = None
    max_height: int | None = None
    max_area: int | None = None

    @classmethod
    def from_info(cls, info: object) -> ImageService:
        """The service an `info.json` body (already parsed from JSON) describes.

        Raises `ImageSearchFailure` when the body is not an Image API 2 or 3
        `info.json`, or does not state the original's size.
        """
        if not isinstance(info, Mapping):
            raise ImageSearchFailure("The IIIF image service's info.json is not a JSON object.")
        version = _version(info.get("@context"))
        if version is None:
            raise ImageSearchFailure("The IIIF image service's info.json names neither Image API 2 nor 3.")
        service = _http_url(info.get("@id" if version == _V2 else "id"))
        width, height = _positive(info.get("width")), _positive(info.get("height"))
        if service is None or width is None or height is None:
            raise ImageSearchFailure("The IIIF image service's info.json does not name itself and the original's size.")
        # Version 2 declares its limits inside `profile`, after the compliance
        # level; version 3 at the top. A limit stated twice keeps the smaller.
        declared: list[Mapping[str, object]] = [info]
        profile = info.get("profile")
        if version == _V2 and isinstance(profile, list):
            declared += [entry for entry in profile if isinstance(entry, Mapping)]
        max_width = _smallest(declared, "maxWidth")
        max_height = _smallest(declared, "maxHeight")
        if max_width is not None and max_height is None:
            # Both versions: a width limit alone limits the height to the same.
            max_height = max_width
        return cls(
            id=service.rstrip("/"),
            version=version,
            width=width,
            height=height,
            max_width=max_width,
            max_height=max_height,
            max_area=_smallest(declared, "maxArea"),
        )

    @property
    def info_url(self) -> str:
        """The service's `info.json`, which `dezoomify-rs` reads to walk its tiles."""
        return f"{self.id}/info.json"

    @property
    def full_url(self) -> str:
        """One request for the whole image at the largest size the service serves: `full/full` in 2, `full/max` in 3."""
        return f"{self.id}/full/{'full' if self.version == _V2 else 'max'}/0/default.jpg"

    @property
    def serves_original(self) -> bool:
        """Whether the service declares no limit below the original, so one request may return it whole."""
        return (
            (self.max_width is None or self.max_width >= self.width)
            and (self.max_height is None or self.max_height >= self.height)
            and (self.max_area is None or self.max_area >= self.width * self.height)
        )

    def preview_url(self, side: int) -> str:
        """A rendering no larger than `side` on either edge, for a preview."""
        return f"{self.id}/full/!{side},{side}/0/default.jpg"

    def locator(self, *, direct_max_side: int) -> FetchLocator:
        """How Arrt fetches the original: one request, or the tiles.

        One request when the service declares no limit below the original and
        its long side is at most `direct_max_side`; the tiles otherwise. The
        caller states `direct_max_side`, because some servers fail a large
        request they never declared a limit for (Yale's answered HTTP 500 for a
        46,800-pixel original), and how large is a fact about that server.
        """
        if self.serves_original and max(self.width, self.height) <= direct_max_side:
            return FetchLocator.direct(self.full_url)
        return FetchLocator.tiles(self.info_url)


def _smallest(declared: Sequence[Mapping[str, object]], key: str) -> int | None:
    limits = [limit for entry in declared if (limit := _positive(entry.get(key))) is not None]
    return min(limits) if limits else None


@dataclass(frozen=True, slots=True)
class CanvasImage:
    """One canvas of a IIIF manifest: its image, and what the canvas says about it."""

    #: The base URI of the canvas image's IIIF image service, or None when its
    #: image names none (a plain file, which is not IIIF).
    service: str | None
    #: The image resource's own URL, as the manifest names it, where it names one.
    image: str | None
    #: The canvas's size, as the manifest states it.
    width: int | None
    height: int | None
    #: The canvas's label, every value in every language, in the manifest's order.
    label: tuple[str, ...]
    #: The canvas's own metadata: each label, with its values (see `manifest_metadata`).
    metadata: Mapping[str, tuple[str, ...]]


def manifest_images(manifest: object) -> tuple[CanvasImage, ...]:
    """Each canvas's image, in the manifest's order, from a Presentation 2 or 3 manifest (already parsed).

    A canvas with no image is left out. A manifest with no canvases has none.
    Raises `ImageSearchFailure` when the body is not a Presentation manifest.
    """
    manifest, version = _manifest(manifest)
    if version == _V3:
        canvases = manifest.get("items", [])
    else:
        sequences = manifest.get("sequences", [])
        first = sequences[0] if isinstance(sequences, list) and sequences else {}
        canvases = first.get("canvases", []) if isinstance(first, Mapping) else None
    if not isinstance(canvases, list):
        raise ImageSearchFailure("The IIIF manifest's canvases are not a list.")
    found = []
    for canvas in canvases:
        if not isinstance(canvas, Mapping):
            raise ImageSearchFailure("A canvas in the IIIF manifest is not a JSON object.")
        resource = _canvas_resource(canvas, version=version)
        if resource is None:
            continue
        found.append(
            CanvasImage(
                service=_image_service(resource.get("service")),
                image=_http_url(resource.get("id" if version == _V3 else "@id")),
                width=_positive(canvas.get("width")),
                height=_positive(canvas.get("height")),
                label=_texts(canvas.get("label")),
                metadata=_metadata(canvas.get("metadata")),
            )
        )
    return tuple(found)


def manifest_metadata(manifest: object) -> Mapping[str, tuple[str, ...]]:
    """The manifest's own metadata, each label with its values, from a Presentation 2 or 3 manifest.

    Every language's values are kept, in the manifest's order; a label written
    twice gathers both entries' values. What the labels are is the holder's
    choice, so a plugin reads the ones it has measured.
    """
    manifest, _ = _manifest(manifest)
    return _metadata(manifest.get("metadata"))


def _manifest(manifest: object) -> tuple[Mapping[str, object], int]:
    """The manifest as a mapping, and its Presentation API version."""
    if not isinstance(manifest, Mapping):
        raise ImageSearchFailure("The IIIF manifest is not a JSON object.")
    contexts = manifest.get("@context")
    contexts = contexts if isinstance(contexts, list) else [contexts]
    if "http://iiif.io/api/presentation/3/context.json" in contexts and manifest.get("type") == "Manifest":
        return manifest, _V3
    if "http://iiif.io/api/presentation/2/context.json" in contexts and manifest.get("@type") == "sc:Manifest":
        return manifest, _V2
    raise ImageSearchFailure("The answer is not a IIIF Presentation 2 or 3 manifest.")


def _canvas_resource(canvas: Mapping[str, object], *, version: int) -> Mapping[str, object] | None:
    """The image a canvas paints: version 3's first annotation body, version 2's first image resource."""
    if version == _V3:
        pages = canvas.get("items")
        page = pages[0] if isinstance(pages, list) and pages and isinstance(pages[0], Mapping) else {}
        annotations = page.get("items")
        annotation = annotations[0] if isinstance(annotations, list) and annotations else None
        resource = annotation.get("body") if isinstance(annotation, Mapping) else None
    else:
        images = canvas.get("images")
        image = images[0] if isinstance(images, list) and images else None
        resource = image.get("resource") if isinstance(image, Mapping) else None
    return resource if isinstance(resource, Mapping) else None


def _image_service(services: object) -> str | None:
    """The image service a resource names: version 3 lists them, version 2 may name one alone."""
    for service in services if isinstance(services, list) else [services]:
        if not isinstance(service, Mapping):
            continue
        kind = service.get("type", service.get("@type"))
        profile = service.get("profile")
        profiles = profile if isinstance(profile, list) else [profile]
        is_image = kind in _SERVICE_TYPES or any(isinstance(p, str) and "iiif.io/api/image/" in p for p in profiles)
        url = _http_url(service.get("id", service.get("@id")))
        if is_image and url is not None:
            return url.rstrip("/")
    return None


def _texts(value: object) -> tuple[str, ...]:
    """Every string in a label or value: a version 3 language map, or version 2's string, list or `@value`s."""
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, Mapping):
        if "@value" in value:
            return _texts(value.get("@value"))
        return tuple(text for values in value.values() for text in _texts(values))
    if isinstance(value, list):
        return tuple(text for entry in value for text in _texts(entry))
    return ()


def _metadata(entries: object) -> Mapping[str, tuple[str, ...]]:
    gathered: dict[str, tuple[str, ...]] = {}
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, Mapping):
            continue
        for label in _texts(entry.get("label")):
            gathered[label] = gathered.get(label, ()) + _texts(entry.get("value"))
    return gathered
