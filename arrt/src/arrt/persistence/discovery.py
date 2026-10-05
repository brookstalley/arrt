"""The persistence contract over the pre-acceptance pipeline's records.

The counterpart to `catalogue.py`, and a `Protocol` for the same reason: the
service above binds to what the pipeline can be asked, not to how one file
answers. The two contracts are separate because the concerns are, but they are
served by one open file — acceptance promotes a candidate's instances into a
work's sources, and that has to commit as one transaction.

Implementations own persistence and nothing else: no validation, no derived
values, no state-machine opinion. Every rule about what a valid run or candidate
looks like belongs to the service layer, which is the only caller.
"""

from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Protocol

from arrt.persistence.discovery_records import (
    Affinity,
    AffinityDerivation,
    AffinitySentiment,
    CandidateImage,
    CandidateWork,
    Conversation,
    ConversationTurn,
    DiscoveryRun,
    ResolveRunWork,
    RunKind,
    RunStatus,
    Sighting,
    SpendRecord,
)
from arrt.persistence.records import VocabularyKind


class DiscoveryStore(Protocol):
    """Everything the pre-acceptance pipeline can be asked of its storage."""

    # -- atomicity ------------------------------------------------------------

    def transaction(self) -> AbstractContextManager[None]:
        """Group several writes so they commit together or not at all.

        The same capability the catalogue store offers, and against the same open
        file: acceptance writes on both sides of the pipeline boundary, and a
        promotion interrupted halfway leaves a candidate marked accepted with no
        work to show for it.
        """
        ...

    def close(self) -> None:
        """Release the file. Every store over the same file is closed with it."""
        ...

    # -- runs -----------------------------------------------------------------

    def add_run(self, run: DiscoveryRun) -> None:
        """Persist a run. Raises if the id is already present."""
        ...

    def get_run(self, run_id: str) -> DiscoveryRun | None:
        """Return the run, or None if no such id is stored."""
        ...

    def update_run(self, run: DiscoveryRun) -> None:
        """Overwrite a stored run with this one. Raises if the id is absent."""
        ...

    def list_runs(self, *, status: RunStatus | None = None, kind: RunKind | None = None) -> Sequence[DiscoveryRun]:
        """Return matching runs newest first, which is the order they are read in."""
        ...

    # -- candidate works ------------------------------------------------------

    def add_candidate_work(self, work: CandidateWork) -> None:
        """Persist a proposed work. Raises if the id is already present."""
        ...

    def get_candidate_work(self, candidate_work_id: str) -> CandidateWork | None:
        """Return the proposed work, or None if no such id is stored."""
        ...

    def update_candidate_work(self, work: CandidateWork) -> None:
        """Overwrite a stored proposal with this one. Raises if the id is absent."""
        ...

    def list_candidate_works(self, run_id: str) -> Sequence[CandidateWork]:
        """Return a run's proposals in a stable order."""
        ...

    def list_works_awaiting_verdict(self) -> Sequence[CandidateWork]:
        """Every work, across runs, that found an image and has no verdict yet.

        The read behind *To review*: what a curator has still to judge, wherever
        it came from. A work with no image has nothing to accept, so it is not
        waiting on a verdict in the same sense and is left out.
        """
        ...

    def list_wanted_works(self) -> Sequence[CandidateWork]:
        """Every work, across runs, whose verdict is `wanted`.

        The read behind Activity › Wanted: what the curator wants and does not yet
        hold a scan of, wherever it came from. Ordered by title; the newest-first
        order a page shows is the service's, since it is decided by the runs.
        """
        ...

    def list_candidate_works_by_dedup_key(self, work_dedup_key: str) -> Sequence[CandidateWork]:
        """Return every proposal ever made for this work identity, across runs.

        This is the read behind work-scoped suppression, so it deliberately spans
        runs: a work declined in March must not come back in April.
        """
        ...

    def destinations_of_artworks(self, artwork_ids: Sequence[str]) -> Mapping[str, str]:
        """Each artwork's run's destination theme id, for the artworks whose run named one.

        Joined artwork → the candidate work acceptance minted it from
        (`candidate_works.artwork_id`) → that work's run. An artwork no
        candidate work became, and one whose run named no destination, is
        absent rather than mapped to None: the caller answers every id it asked.
        """
        ...

    # -- candidate images -----------------------------------------------------

    def add_candidate_image(self, image: CandidateImage) -> None:
        """Persist an image instance. Raises if the id is already present."""
        ...

    def get_candidate_image(self, candidate_image_id: str) -> CandidateImage | None:
        """Return the instance, or None if no such id is stored."""
        ...

    def update_candidate_image(self, image: CandidateImage) -> None:
        """Overwrite a stored instance with this one. Raises if the id is absent."""
        ...

    def list_candidate_images(self, candidate_work_id: str) -> Sequence[CandidateImage]:
        """Return a work's instances in a stable order, the selected one leading.

        Only where a selection exists: a work whose scans are all below the floor
        or all turned down has none, and the leading row is then the
        highest-ranked, which may be one already refused. `is_selected` answers
        which case this is; position does not.
        """
        ...

    # -- conversations --------------------------------------------------------

    def add_conversation(self, conversation: Conversation) -> None:
        """Persist a conversation. Raises if the id is already present."""
        ...

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        """Return the conversation, or None if no such id is stored."""
        ...

    def update_conversation(self, conversation: Conversation) -> None:
        """Overwrite a stored conversation with this one. Raises if the id is absent."""
        ...

    def list_conversations(self) -> Sequence[Conversation]:
        """Return every conversation, the most recently spoken in first."""
        ...

    def add_conversation_turn(self, turn: ConversationTurn) -> None:
        """Append a turn. Raises if the id, or the thread position, is taken."""
        ...

    def get_conversation_turn(self, turn_id: str) -> ConversationTurn | None:
        """Return the turn, or None if no such id is stored."""
        ...

    def list_conversation_turns(self, conversation_id: str) -> Sequence[ConversationTurn]:
        """Return a thread's turns in ordinal order, which is reading order."""
        ...

    def delete_conversation_turn(self, turn_id: str) -> None:
        """Remove a turn. A turn that is not stored is not an error.

        **Nothing here detaches what cited the turn.** The store deletes rows; the
        rule that a deleted conversation leaves affinities and ledger entries
        standing with null citations is the service layer's, and putting it here
        as an `ON DELETE` clause is the one shape the deletion ruling forbids.
        """
        ...

    def delete_conversation(self, conversation_id: str) -> None:
        """Remove a conversation. Its turns are the caller's to remove first."""
        ...

    # -- affinities -----------------------------------------------------------

    def add_affinity(self, affinity: Affinity) -> None:
        """Persist a judgment. Raises if the id, or the (kind, value) pair, is taken."""
        ...

    def get_affinity(self, affinity_id: str) -> Affinity | None:
        """Return the judgment, or None if no such id is stored."""
        ...

    def find_affinity(self, *, kind: VocabularyKind, value: str) -> Affinity | None:
        """Return the one live judgment about this thing, or None."""
        ...

    def update_affinity(self, affinity: Affinity) -> None:
        """Overwrite a stored judgment with this one. Raises if the id is absent."""
        ...

    def delete_affinity(self, affinity_id: str) -> None:
        """Forget a judgment. One that is not stored is not an error."""
        ...

    def list_affinities(
        self,
        *,
        kind: VocabularyKind | None = None,
        sentiment: AffinitySentiment | None = None,
        derivation: AffinityDerivation | None = None,
        source_turn_id: str | None = None,
    ) -> Sequence[Affinity]:
        """Return matching judgments, grouped by kind and then by name."""
        ...

    # -- spend ----------------------------------------------------------------

    def add_spend_record(self, record: SpendRecord) -> None:
        """Persist a cost. Raises if the id is already present."""
        ...

    def update_spend_record(self, record: SpendRecord) -> None:
        """Overwrite a stored cost. Raises if the id is absent.

        **Amounts are never revised.** This exists for the one edit that is not a
        revision — dropping a citation to a conversation turn that has been
        deleted — and a ledger that changed retroactively would make a month total
        fall because somebody tidied.
        """
        ...

    def list_spend_records(
        self,
        *,
        run_id: str | None = None,
        conversation_turn_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> Sequence[SpendRecord]:
        """Return matching costs newest first. Bounds are inclusive of `since`, exclusive of `until`."""
        ...

    # -- resolve-run coverage -------------------------------------------------

    def add_coverage(self, coverage: ResolveRunWork) -> None:
        """Record that a resolve run covers a work. Raises if the pair is already present."""
        ...

    def list_coverage_by_run(self, resolve_run_id: str) -> Sequence[ResolveRunWork]:
        """Return the works a resolve run covers, which is its scope."""
        ...

    def list_coverage_by_work(self, candidate_work_id: str) -> Sequence[ResolveRunWork]:
        """Return every resolve run that has ever covered this work.

        The read behind the double-spend guard: a work is refused to a new
        resolve run while any run covering it is still live.
        """
        ...

    # -- sightings --------------------------------------------------------------

    def add_sighting(self, sighting: Sighting) -> bool:
        """Record a sighting once. True when it was new; False, and nothing written, when it was already there."""
        ...

    def list_open_sightings(self) -> Sequence[Sighting]:
        """Every sighting of a work still open: wanted, or unresolved with no verdict yet.

        Whether the catalogue holds the work is not this store's to say; the
        caller asks the catalogue.
        """
        ...

    # -- citations --------------------------------------------------------------

    def add_run_citations(self, run_id: str, urls: Sequence[str]) -> None:
        """Record the pages a run's phase-1 search read, in the order given.

        A URL already recorded for the run keeps its first position: the search
        read it once, however often it was cited.
        """
        ...

    def list_run_citations(self, run_id: str) -> Sequence[str]:
        """The pages a run's phase-1 search read, in the search's order; empty for a run with none."""
        ...
