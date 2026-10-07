"""The persistence contract over the catalogue's records.

`StorageError` and `StoreMisuseError` are importable from here and **declared in
`errors.py`**, which neither domain owns — the distinction the note beside the
re-export at the foot of this file exists to make. This sentence read "and its
two errors" until 2026-08-06, which was the claim the move was correcting.

The store is a `Protocol` rather than a base class so that the layers above it
bind to what the catalogue can be asked, not to how one file answers. Persistence
is reached only through the service layer, so naming the contract here is what
keeps the backing technology a local concern. The records themselves are in
`records.py`, and `discovery.py` is the matching contract over the pipeline
before acceptance. Both are served by one open file, which `file.py` opens.

Implementations own persistence and nothing else: no validation, no derived
values, no ordering decisions beyond a deterministic sort. Every rule about what
a valid catalogue looks like belongs to the service layer, which is the only
caller — a store that also enforced would be a second place for those rules to
live, and the two would disagree.
"""

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field, replace
from typing import Protocol

from arrt.persistence.errors import StorageError, StoreMisuseError
from arrt.persistence.records import (
    Artist,
    Artwork,
    ArtworkPage,
    ArtworkStatus,
    MatColor,
    Original,
    QueuedAcquisition,
    Rendition,
    Source,
    VocabularyKind,
    WorkFacet,
    WorkOrder,
)


@dataclass(frozen=True, slots=True)
class TopicTally:
    """One registry item the catalogue's facets name, under one kind, and how many works carry it."""

    kind: VocabularyKind
    #: The item, as `WorkFacet.value_qid` holds it.
    qid: str
    #: Its name, as the facet rows hold it.
    label: str
    works: int


@dataclass(frozen=True, slots=True)
class WorkToAcquire:
    """One accepted work the acquisition queue may owe something: a fetch, or the preparation after one."""

    artwork_id: str
    #: Whether the work holds a master image already. True only for a work with a
    #: queue row, which is one fetched and still owing its preparation, or one a
    #: Retry named a source to fetch again from.
    holds_original: bool
    #: The queue's row for it, or None for a work it has not yet tried.
    queued: QueuedAcquisition | None


@dataclass(frozen=True, slots=True)
class WorkQuery:
    """Which works a listing is about, before paging.

    Three independent narrowings, and they are one object rather than three
    parameters because the same set has to be described **four different ways in
    one response** — the page, its total, and a count per facet kind. Passing them
    separately would let the page and the counts it is labelled with disagree
    about which works they are talking about, which is the one defect a facet
    control cannot survive: the numbers would be right about a set nobody is
    looking at.
    """

    #: Accepted, archived, or both. The one axis that is not a facet, and the one
    #: that is applied to every read here including the facet vocabulary.
    status: ArtworkStatus | None = None
    #: Free-text terms, already split. **Every term must match somewhere** — they
    #: are ANDed across the work's text and its artist's name, so a second word
    #: narrows rather than widens. Empty means no text narrowing at all.
    terms: Sequence[str] = ()
    #: Chosen values per facet kind. **Values within one kind are ORed and kinds
    #: are ANDed**: two movements means either movement, a movement and an era
    #: means both. That asymmetry is what makes a facet control behave the way a
    #: person expects, and it is stated here because it is invisible at the call
    #: site.
    facets: Mapping[VocabularyKind, Sequence[str]] = field(default_factory=dict)
    #: One artist's works, by the catalogue's own link rather than by the artist
    #: facet: the facet is a derived claim a catalogue may not carry at all (the
    #: owner's holds none), while every attributed work names its artist.
    artist_id: str | None = None
    #: Only these works, by id. A theme's members arrive this way: themes are
    #: Programming's, so the Library is handed their ids as opaque references and
    #: learns nothing about themes. **Empty selects nothing; `None` restricts
    #: nothing** — an empty theme is an empty grid, never the whole catalogue. An
    #: id the catalogue does not hold is passed over, since Programming's
    #: references may fail to resolve.
    within: frozenset[str] | None = None

    def without(self, kind: VocabularyKind) -> WorkQuery:
        """The same query with one facet kind's own selection dropped.

        **This is the retrieval rule the collection stands on.** A facet's counts
        are computed over the results filtered by every *other* facet, never by
        its own: including its own collapses the control to the single value
        already chosen, and the curator cannot change their mind without first
        clearing the filter they want to change.

        Invisible at 41 works, where every option has a count either way. At
        thousands it is the difference between a working control and one that
        can only be escaped from.
        """
        return replace(self, facets={other: chosen for other, chosen in self.facets.items() if other is not kind})


class CatalogueStore(Protocol):
    """Everything the catalogue can be asked of its storage."""

    # -- atomicity ------------------------------------------------------------

    def transaction(self) -> AbstractContextManager[None]:
        """Group several writes so they commit together or not at all.

        Several of the catalogue's rules span rows — exactly one mat colour is
        current, at most one source is primary. Each is applied as a
        clear-then-set pair, and a pair that can be interrupted between its
        halves leaves the catalogue in a state the rule forbids: a work with no
        mat colour in force, and so nothing to compose its canvas against.
        Nesting is permitted and joins the outer group, so a service operation
        composed of others still commits once.

        **"Exactly one theme is active" was the third example here until
        2026-08-12**, and it went away rather than being restated per wall:
        `ThemeAssignment` is keyed by the wall alone, so what replaced it is a
        primary key and not a pair of writes that has to be atomic.
        """
        ...

    def reading(self) -> AbstractContextManager[None]:
        """Group several reads so they answer about one instant of the catalogue.

        `transaction`'s counterpart, and it exists for the same class of defect
        read the other way round. A listing that returns rows, a total and a set
        of facet counts assembles them from several calls; a write landing
        between two of them yields a page whose parts were never simultaneously
        true — counts that do not add up to the total, or an option offered at a
        count the click would not reproduce. Handlers are synchronous `def` and
        run in a worker thread, so "between two of them" is a real window rather
        than a theoretical one.

        Nesting joins the outer scope, and a read scope inside a transaction is
        permitted.
        """
        ...

    def after_commit(self, callback: Callable[[], None]) -> None:
        """Run `callback` once the writes made so far are committed, and not before.

        Inside `transaction()` it waits for the outermost block to commit and is
        discarded on rollback; outside one it runs at once. The Library announces
        its changes this way, so no announcement describes a write that was
        rolled back.
        """
        ...

    def close(self) -> None:
        """Release the underlying resources."""
        ...

    # -- artists --------------------------------------------------------------

    def add_artist(self, artist: Artist) -> None:
        """Persist an artist. Raises if the id is already present."""
        ...

    def get_artist(self, artist_id: str) -> Artist | None:
        """Return the artist, or None if no such id is stored."""
        ...

    def update_artist(self, artist: Artist) -> None:
        """Overwrite a stored artist with this one. Raises if the id is absent."""
        ...

    def list_artists(self) -> Sequence[Artist]:
        """Every artist held, in a stable order.

        Unpaged, unlike works: this answers "which painter is this", which is a
        question about the whole set — a page of it would match against whichever
        artists happened to sort first. The table grows by one row per painter
        the catalogue has never seen, against a collection sized by one wall.
        """
        ...

    # -- artworks -------------------------------------------------------------

    def add_artwork(self, artwork: Artwork) -> None:
        """Persist a work. Raises if the id is already present."""
        ...

    def get_artwork(self, artwork_id: str) -> Artwork | None:
        """Return the work, or None if no such id is stored."""
        ...

    def update_artwork(self, artwork: Artwork) -> None:
        """Overwrite a stored work with this one. Raises if the id is absent."""
        ...

    def list_artworks(self, query: WorkQuery, *, limit: int, offset: int, order: WorkOrder = WorkOrder.TITLE) -> ArtworkPage:
        """Return a page of works matching `query` in `order`, stable across pages, with the unpaged total."""
        ...

    def artwork_ids_matching(self, query: WorkQuery) -> frozenset[str]:
        """Every work `query` selects, by id, unpaged and unordered.

        For a caller that counts the selection against a grouping the catalogue
        does not hold — a theme's members — and so needs the set, not a page.
        """
        ...

    def held_artists(self) -> Sequence[tuple[Artist, int, str]]:
        """Every artist with at least one work in circulation, how many, and the first accepted of them, by name.

        The first accepted work is the one the Artists index pictures the artist
        by: no artist has a picture of their own, and the earliest acquisition is
        a stable choice that does not change as more works arrive.
        """
        ...

    def circulating_ids_by_qid(self) -> Mapping[str, Sequence[str]]:
        """Every work in circulation that carries a Wikidata QID, keyed by it; several where works share one."""
        ...

    def circulating_without_qid(self) -> Sequence[tuple[str, str, str | None]]:
        """Every work in circulation that carries no Wikidata QID and is open to one: id, title and artist id, oldest first.

        What a registry row is matched against by title and artist where no QID
        can match it. A work the curator said has no item is left out: they said
        it is no registry row.
        """
        ...

    def accepted_artwork_ids(self) -> Sequence[str]:
        """Every work in circulation, by id, oldest first."""
        ...

    # -- what a work is, and what a filter would select -----------------------

    def add_facet(self, facet: WorkFacet) -> None:
        """Persist a facet. Raises if the id, or the work's (kind, value), is already present."""
        ...

    def remove_facet(self, facet_id: str) -> None:
        """Delete a facet. Removing an absent one is not an error."""
        ...

    def list_facets(self, artwork_id: str) -> Sequence[WorkFacet]:
        """Return a work's facets in a stable order, grouped by kind."""
        ...

    def facet_vocabulary(self, *, status: ArtworkStatus | None) -> Mapping[VocabularyKind, Sequence[str]]:
        """Every value each kind holds anywhere in the catalogue, in a stable order.

        The whole vocabulary rather than the matching part of it, because **a
        zero-count option is disabled and not hidden**: a list that shrank as
        filters were applied would read as data loss rather than as an empty
        intersection. What the counts are computed over is a separate question,
        answered by `count_facet_values`.
        """
        ...

    def count_facet_values(self, kinds: Sequence[VocabularyKind], query: WorkQuery) -> Mapping[VocabularyKind, Mapping[str, int]]:
        """How many works `query` selects for each value the named kinds hold.

        Values with no matching work are simply absent — the caller pairs this
        against `facet_vocabulary` to decide which options are offered at zero.
        Every named kind gets an entry, empty when it selects nothing.

        **Several kinds at once because they usually share a query.** Nothing here
        knows the exclusion rule; the caller passes the query it wants counted,
        which for a facet's own counts is `query.without(kind)` — and that is the
        same object for every kind the curator has not filtered on. Counting those
        together is one statement instead of five, which is what keeps the
        collection's default screen from paying for six near-identical scans.
        """
        ...

    def topic_tallies(self, *, status: ArtworkStatus | None, qid: str | None = None) -> Sequence[TopicTally]:
        """Every item a facet names by QID, per kind, with how many of the selected works carry it.

        Only rows with a `value_qid` are counted: a value nobody tied to an item
        has no page to open. `qid` narrows to that one item. Ordered by kind,
        then label ignoring case, then QID.
        """
        ...

    def works_with_topic(self, qid: str, *, status: ArtworkStatus | None, kinds: Sequence[VocabularyKind]) -> Sequence[str]:
        """The ids of the selected works with a facet of one of `kinds` naming this item, each once, by title."""
        ...

    # -- sources --------------------------------------------------------------

    def add_source(self, source: Source) -> None:
        """Persist a source. Raises if the id is already present."""
        ...

    def get_source(self, source_id: str) -> Source | None:
        """Return the source, or None if no such id is stored."""
        ...

    def update_source(self, source: Source) -> None:
        """Overwrite a stored source with this one. Raises if the id is absent."""
        ...

    def list_sources(self, artwork_id: str) -> Sequence[Source]:
        """Return a work's sources in a stable order, the primary one first."""
        ...

    # -- originals ------------------------------------------------------------

    def add_original(self, original: Original) -> None:
        """Persist the master image. Raises if the work already has one."""
        ...

    def get_original(self, artwork_id: str) -> Original | None:
        """Return the work's master image, or None if none has been acquired."""
        ...

    def update_original(self, original: Original) -> None:
        """Overwrite a stored master image with this one. Raises if the id is absent."""
        ...

    # -- renditions -----------------------------------------------------------

    def add_rendition(self, rendition: Rendition) -> None:
        """Persist a derived output. Raises if the id is already present."""
        ...

    def update_rendition(self, rendition: Rendition) -> None:
        """Overwrite a stored rendition with this one. Raises if the id is absent."""
        ...

    def find_renditions_by_content(self, content_sha256: str) -> Sequence[Rendition]:
        """Every rendition whose file hashed to this, in a stable order. Usually one."""
        ...

    def list_renditions(self, artwork_id: str) -> Sequence[Rendition]:
        """Return a work's renditions in a stable order."""
        ...

    # -- mat colours ----------------------------------------------------------

    def add_mat_color(self, mat_color: MatColor) -> None:
        """Persist a mat colour choice. Raises if the id is already present."""
        ...

    def update_mat_color(self, mat_color: MatColor) -> None:
        """Overwrite a stored mat colour with this one. Raises if the id is absent."""
        ...

    def list_mat_colors(self, artwork_id: str) -> Sequence[MatColor]:
        """Return a work's mat colours newest first, which is its history."""
        ...

    # -- the acquisition queue ------------------------------------------------

    def works_to_acquire(self) -> Sequence[WorkToAcquire]:
        """Every accepted work holding no original or holding a queue row, oldest acceptance first.

        Archived works are left out whatever their row says: the queue fetches
        only what is in circulation, and a restored work comes back with its row.
        """
        ...

    def works_with_canvas_outside_layout(self, layout: str) -> Sequence[str]:
        """Accepted works holding a television canvas, none of them drawn at `layout`, oldest acceptance first."""
        ...

    def current_mats_of_works_with_canvas(self) -> Sequence[tuple[str, str | None]]:
        """(work, current mat hex or None) for every accepted work holding a television canvas, oldest acceptance first."""
        ...

    def get_queued_acquisition(self, artwork_id: str) -> QueuedAcquisition | None:
        """Return the queue's row for this work, or None if it has none."""
        ...

    def set_queued_acquisition(self, entry: QueuedAcquisition) -> None:
        """Write the queue's row for this work, replacing any it had."""
        ...

    def remove_queued_acquisition(self, artwork_id: str) -> None:
        """Delete the queue's row for this work. A missing row is not an error."""
        ...


#: Re-exported, not declared here. Both live in `persistence/errors.py`, which
#: neither domain owns — `durable.py` and `sqlite_discovery.py` need them and
#: reaching through this module for them made the generic tier depend on one of
#: the two domains it serves. They stay importable from here because
#: `CatalogueStore`'s own methods raise them, and a caller holding a catalogue
#: store should not have to know which module declared the class to catch it.
__all__ = ["CatalogueStore", "StorageError", "StoreMisuseError", "WorkQuery", "WorkToAcquire"]
