"""Wikidata, as a finder of the pages a work's item records, with no search at all.

A work's Wikidata item names where the work is described: MoMA's work ID (P2014)
put into its property's formatter URL gives MoMA's page, and "described at URL"
(P973) gives SFMOMA's. This plugin offers every such page for a work with an
item, as a `FoundPage`, and reads none of them. Arrt gives each to the installed
plugins' readers, and keeps one that none claims as a sighting
(`source-plugins.md` § The Wikidata finder).

**It offers pages, never images.** A page is known only by its address: whether
it shows the work, how large, and under what title are a reader's to say. The
item's own image (P18) is the Commons plugin's, which reads it as an image with
its size.

**It offers every page, holders' and anybody else's.** Items carry encyclopedias,
catalogues raisonnés and a Google search link beside holders' pages, and which of
them shows the work is what a reader recognises, not what this can tell.

It asks only the registry, which carries this deployment's
`WIKIDATA_USER_AGENT`, so it has no setting of its own.
"""

from collections.abc import Sequence
from typing import Final

from arrt.library.sources import (
    Declined,
    FoundPage,
    ImageQuery,
    ImageQueryUnanswerable,
    ImageSearchFailure,
    Registry,
    RegistryUnavailable,
    SourceContext,
    SourceParts,
    SourcePlugin,
)

#: The name this finder answers under.
PROVIDER: Final[str] = "wikidata"


class WikidataFinder:
    """The pages a work's Wikidata item records."""

    def __init__(self, *, registry: Registry) -> None:
        self._registry = registry

    @property
    def provider(self) -> str:
        return PROVIDER

    def find_images(self, query: ImageQuery) -> Sequence[FoundPage]:
        if query.qid is None:
            raise ImageQueryUnanswerable("Wikidata's pages are read from a work's item, and this work has none.")
        try:
            pages = self._registry.pages_about(query.qid)
        except RegistryUnavailable as exc:
            raise ImageSearchFailure(f"Wikidata could not be asked about {query.qid}: {exc}") from exc
        return tuple(FoundPage(url=page) for page in pages)

    def fetch_preview(self, url: str) -> bytes | None:
        """None: a page carries no preview, and this finder reports nothing else."""
        return None


def _create(context: SourceContext) -> SourceParts | Declined:
    """The finder, or why there is none: it reads a work's item, so it needs the registry."""
    if context.registry is None:
        return Declined("no registry is configured (WIKIDATA_USER_AGENT is unset), and pages are read from a work's item")
    return SourceParts(finder=WikidataFinder(registry=context.registry))


#: What the `wikidata` entry point names. Written for interface major 1 as a
#: literal, as a plugin outside this repository would write it.
PLUGIN: Final[SourcePlugin] = SourcePlugin(api_major=1, create=_create)
