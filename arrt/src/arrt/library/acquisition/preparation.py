"""Turning a held original into what a wall needs, and deciding when to.

Acquisition ends with bytes on disk and a row naming them. This is what happens
next: the work gets a presentation master, the unmatted picture every Player
composes from, and a mat colour with recorded provenance, which the feed sends
beside it. Everything policy-shaped lives here — when a mat is worth paying for,
when a master is stale, what a failure costs — while `mat.py` knows how to
choose a colour and `master.py` how to make a master. Nothing here knows any
screen's geometry: the Player that owns the screen draws the mat.

**Preparation is idempotent, and free to re-run once a work has a mat.** The
expensive half is the model call, so a work that already has a mat keeps it.

**The first preparation of a work is not free, and every result says so.** A work
that has never had a mat cannot be shown without choosing one, and `acquire()`
does not prepare — so the first call on a freshly acquired work is a paid vision
call, which is the normal case rather than an edge. `PreparationResult.cost_usd`
carries it, the tool surface reports it, and a `mat_color_vision` spend row records
it against the work, so the month's total includes what the acquisition queue
spends unattended. The tempting sentence was "regenerate never spends"; it is
false on exactly the call a curator makes first.

**Staleness is a comparison, not a flag.** A rendition records the
`content_hash` of the original it was drawn from, so "is this current" is
answered by reading both rather than by trusting something set at write time. The
2024 code expressed the same intent imperatively — clearing the television's
state whenever it regenerated an image — which held only at the one site that
remembered to do it.
"""

import logging
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum, StrEnum
from pathlib import Path
from typing import Final, Protocol

from arrt.library.acquisition.color import ColorError, format_hex, parse_hex
from arrt.library.acquisition.master import MASTER_RULE, MASTERS_DIRNAME, make_master, master_path
from arrt.library.acquisition.mat import (
    MAT_LIGHTNESS_FLOOR,
    MAT_PRESETS,
    MatChoice,
    MatEngine,
    MatPreset,
    below_the_floor,
    derive,
)
from arrt.library.services.catalogue import CatalogueService
from arrt.library.services.quality import PRESENTATION_MASTER_LONG_EDGE_PX
from arrt.persistence.discovery_records import CostStatus, SpendCategory
from arrt.persistence.records import MatColor, MatMethod, RenditionKind
from arrt.services.errors import ServiceError

log = logging.getLogger(__name__)


class PreparationOutcome(Enum):
    """What preparing a work amounted to."""

    #: A master was made, or a mat chosen, and recorded.
    PREPARED = "prepared"
    #: The work was already current and nothing needed doing.
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class PreparationResult:
    """What happened, in terms a curator or an agent can act on."""

    artwork_id: str
    outcome: PreparationOutcome
    detail: str
    mat_hex: str
    mat_method: str
    #: The presentation master, relative to `ART_ROOT`.
    relative_path: str | None = None
    #: What the mat choice cost, zero when no model was asked. A curator
    #: authorising a remake is entitled to know whether it spends anything.
    cost_usd: Decimal = Decimal(0)
    #: Why the mat came from the fallback, when it did. `None` otherwise.
    #:
    #: **Both outcomes leave the work ready for the wall**, so there is no
    #: `prepared` flag to read: `unchanged` means the work was already current,
    #: not that anything failed. Failures raise, because every one of them —
    #: no original, an original missing from disk, a master that would not
    #: encode — needs a different thing done about it, and a caller handed a
    #: false-valued result would have to re-derive which.
    mat_fallback_detail: str | None = None


class MatWay(StrEnum):
    """How a mat is asked for: the four ways the one mat act takes (`PreparationService.set_work_mat`)."""

    #: One of the one-press mats (`MAT_PRESETS`), by its key. Free.
    PRESET = "preset"
    #: A colour of the asker's own, as a hex triplet. Free.
    COLOUR = "colour"
    #: The work's own dominant colour, worked out mechanically. Free.
    DERIVED = "derived"
    #: The vision model's choice. The one way that spends.
    MODEL = "model"


#: What asking for a mat more than one way at once is refused with, on every surface.
MORE_THAN_ONE_MAT: Final[str] = "Choose the mat one way, not both: a colour, a preset, or the colour derived from the picture."

#: What asking for no mat is refused with, where naming none asks for nothing (the browser's control).
NO_MAT_NAMED: Final[str] = "Choose the mat: a colour, a preset, or the colour derived from the picture."


@dataclass(frozen=True, slots=True)
class MatRequest:
    """One mat asked for, one way (`MatWay`), with the preset's key or the colour where the way has one.

    **Built by `named` from whatever a surface was sent**, so which
    combinations are refused, and in what words, is decided here once: HTTP
    and MCP each map their own arguments onto it and judge nothing themselves.
    """

    way: MatWay
    #: The preset's key or the colour's hex triplet; None for the derived mat and the model's.
    value: str | None = None

    @classmethod
    def named(
        cls,
        *,
        hex_rgb: str | None = None,
        preset: str | None = None,
        derived: bool = False,
        otherwise: MatRequest | None = None,
    ) -> MatRequest:
        """The one mat a caller named, or `otherwise` when it named none.

        A caller naming two ways is refused (`MORE_THAN_ONE_MAT`). Naming none
        is refused (`NO_MAT_NAMED`) unless `otherwise` says what naming none
        asks for: over MCP, the model's choice (`ASK_THE_MODEL`), which is the
        one that spends, so a surface that passes no `otherwise` can never
        reach it. A value is named when it is given at all, an empty one
        included, so an empty colour is refused as a colour and never read as
        a request for the model.
        """
        asked = [
            *([cls(MatWay.COLOUR, hex_rgb)] if hex_rgb is not None else []),
            *([cls(MatWay.PRESET, preset)] if preset is not None else []),
            *([cls(MatWay.DERIVED)] if derived else []),
        ]
        if len(asked) > 1:
            raise ServiceError(MORE_THAN_ONE_MAT)
        if asked:
            return asked[0]
        if otherwise is None:
            raise ServiceError(NO_MAT_NAMED)
        return otherwise


@dataclass(frozen=True, slots=True)
class MatOffer:
    """A work's mat and the choices a curator has for it, before and after a choice: what the Work page's control shows."""

    #: The mat in force, or None while the work has none.
    current: MatColor | None
    presets: Sequence[MatPreset]
    #: What the derived mat would be, worked out and not recorded; None when the
    #: work has no readable original to derive it from.
    derived_hex_rgb: str | None


#: Naming no mat over MCP: ask the vision model, which spends.
ASK_THE_MODEL: Final[MatRequest] = MatRequest(MatWay.MODEL)


@dataclass(frozen=True, slots=True)
class PreparationSettings:
    """Where preparation writes. A master names no geometry, so this is the root and nothing else."""

    art_root: Path

    @property
    def masters_path(self) -> Path:
        """Where presentation masters are written. Fixed under `ART_ROOT`: a master
        names no deployment value, so there is nothing about its home to configure."""
        return self.art_root / MASTERS_DIRNAME


class SpendLedger(Protocol):
    """Where a paid mat choice is recorded: the one method preparation needs of the ledger.

    `DiscoveryService` is the ledger today. Taken through this one method rather
    than whole, so preparation reaches accounting without reaching discovery, and
    moving the ledger out of discovery changes the wiring and nothing here.
    """

    def record_spend(
        self,
        *,
        category: SpendCategory,
        cost_usd: Decimal,
        artwork_id: str | None = None,
        model_id: str | None = None,
        units: int | None = None,
        cost_status: CostStatus = CostStatus.KNOWN,
    ) -> object: ...


class PreparationService:
    """Give a work a presentation master and a mat colour."""

    def __init__(
        self, catalogue: CatalogueService, mat_engine: MatEngine, settings: PreparationSettings, *, spend: SpendLedger
    ) -> None:
        self._catalogue = catalogue
        self._mat = mat_engine
        self._settings = settings
        #: Required rather than defaulted to a ledger that records nothing: a
        #: default that silently drops spend looks exactly like working wiring,
        #: and the month total would omit every mat call without anything failing.
        self._spend = spend
        #: One lock per work being prepared, and how many callers hold or await it,
        #: so the entry goes when the last one leaves. `_guard` only protects this
        #: table; it is never held while a work is being prepared.
        self._guard = threading.Lock()
        self._in_flight: dict[str, tuple[threading.Lock, int]] = {}
        #: The same, for recording a work's mat (`_deciding_the_mat`): held only
        #: around a read and a write, never across a call to the model.
        self._deciding: dict[str, tuple[threading.Lock, int]] = {}

    @contextmanager
    def _one_at_a_time(self, artwork_id: str) -> Iterator[None]:
        """Hold this work's lock: a second preparation of it waits, and another work's does not.

        **Per work, because the queue's `prepare` and an MCP or HTTP `regenerate`
        of the same work can otherwise run at once**, and both would ask the
        model for the same mat and pay for it twice, and make the same master
        twice. A lock over every work would make a curator's remake wait behind
        the whole queue.
        """
        with self._held(self._in_flight, artwork_id):
            yield

    @contextmanager
    def _deciding_the_mat(self, artwork_id: str) -> Iterator[None]:
        """Hold this work's mat while one is recorded, so the check of what is current and the write are one step.

        Separate from `_one_at_a_time`, which a preparation holds while the
        model is asked: a curator's own colour would otherwise wait out the
        model's whole answer before it was taken.
        """
        with self._held(self._deciding, artwork_id):
            yield

    @contextmanager
    def _held(self, table: dict[str, tuple[threading.Lock, int]], artwork_id: str) -> Iterator[None]:
        """Hold `table`'s lock for this work, counting who holds or awaits it so the entry goes with the last."""
        with self._guard:
            lock, holders = table.get(artwork_id, (threading.Lock(), 0))
            table[artwork_id] = (lock, holders + 1)
        try:
            with lock:
                yield
        finally:
            with self._guard:
                lock, holders = table[artwork_id]
                if holders == 1:
                    del table[artwork_id]
                else:
                    table[artwork_id] = (lock, holders - 1)

    def prepare(self, artwork_id: str, *, force: bool = False) -> PreparationResult:
        """Make this work ready for the wall, doing only what is not already done.

        `force` makes the master again even when a current one is on disk. It
        does **not** re-choose the mat: a colour is a judgement with history, and
        replacing one because someone asked for a remake would spend money to
        overwrite a decision they did not mention. Choosing again is
        `choose_mat`, a separate request, because it is a separate intent.

        **This is free for a work that already has a mat it may keep, and only
        for one.** A mat below `MAT_LIGHTNESS_FLOOR` is not one it may keep: it
        predates the floor, and is chosen again here. A work that has never had a
        mat cannot be shown without choosing one, so the first preparation of a
        freshly acquired work asks the vision model, and `acquire()` does not
        prepare, so that first call is the normal case rather than an edge. The
        cost comes back on `cost_usd` and the caller reports it.

        **One work is prepared by one caller at a time**; a second `prepare` of the
        same work waits for the first and then finds it current.
        """
        with self._one_at_a_time(artwork_id):
            return self._prepare(artwork_id, force=force)

    def _prepare(self, artwork_id: str, *, force: bool) -> PreparationResult:
        original = self._catalogue.get_original(artwork_id)
        if original is None:
            raise ServiceError(f"Artwork {artwork_id!r} has no acquired original to prepare; acquire it first.")

        source = self._settings.art_root / original.relative_path
        if not source.is_file():
            # The row says the work holds an image and the disk disagrees. Worth
            # its own message: this is what a restored catalogue looks like before
            # re-acquisition refills the tree, and "no such file" from deep inside
            # Pillow would send whoever reads it to the wrong place entirely.
            raise ServiceError(
                f"Artwork {artwork_id!r} records an original at {original.relative_path!r} that is not on disk. "
                "Re-acquire it before preparing."
            )

        made = self._make_master_if_owed(artwork_id, source=source, force=force)
        mat, chosen, kept = self._current_or_chosen_mat(artwork_id, source=source)
        done = [
            part
            for part, did in (
                ("its presentation master was made", made),
                ("its mat was chosen", chosen is not None and not kept),
                ("the mat a person chose while the model was asked was kept", kept),
            )
            if did
        ]
        return PreparationResult(
            artwork_id=artwork_id,
            outcome=PreparationOutcome.PREPARED if done else PreparationOutcome.UNCHANGED,
            detail="; ".join(done) if done else "its presentation master and mat were already current",
            mat_hex=mat.hex_rgb,
            mat_method=mat.method.value,
            relative_path=self._master_path(artwork_id),
            cost_usd=Decimal(0) if chosen is None else chosen.cost_usd,
            mat_fallback_detail=None if chosen is None else chosen.fallback_detail,
        )

    def set_work_mat(self, artwork_id: str, request: MatRequest) -> PreparationResult:
        """Give a work the mat asked for: the one mat act both surfaces call.

        Each way keeps what its own method guarantees: a preset and a colour
        are recorded as the curator's (`manual`), the derived mat as `derived`,
        and the model's choice records its spend before its colour; each
        refuses a work the Library does not hold by its id (`NotFound`) before
        anything is asked or spent. Every way keeps the previous colour.
        """
        match request.way:
            case MatWay.PRESET:
                return self.set_mat_preset(artwork_id, str(request.value))
            case MatWay.COLOUR:
                return self.set_mat(artwork_id, str(request.value))
            case MatWay.DERIVED:
                return self.derive_mat(artwork_id)
            case MatWay.MODEL:
                return self.choose_mat(artwork_id)

    def choose_mat(self, artwork_id: str) -> PreparationResult:
        """Ask the vision model for this work's mat colour again.

        Its own operation rather than a flag on `prepare`, because it is the one
        that spends money and the one that supersedes a judgement. The previous
        colour is kept — `record_mat_color` never overwrites — so a worse choice
        is reversible. Under the work's lock, as `prepare` is: both ask the model.
        """
        with self._one_at_a_time(artwork_id):
            return self._choose_mat(artwork_id)

    def _choose_mat(self, artwork_id: str) -> PreparationResult:
        source = self._source_for_a_mat(artwork_id)
        asked_over = self._catalogue.current_mat_color(artwork_id)
        choice = self._mat.choose(source)
        # Spend first: the call is billed whether or not the colour is accepted, and
        # a refused write (a darker colour than the floor, a full disk) must not
        # lose the cost the month's total is owed.
        self._record_spend(artwork_id, choice)
        standing = self._record_the_models_mat(artwork_id, choice, asked_over=asked_over)
        if standing is not None:
            return PreparationResult(
                artwork_id=artwork_id,
                outcome=PreparationOutcome.UNCHANGED,
                detail=f"a person chose {standing.hex_rgb} while the model was asked, and their mat stands",
                mat_hex=standing.hex_rgb,
                mat_method=standing.method.value,
                relative_path=self._master_path(artwork_id),
                cost_usd=choice.cost_usd,
                mat_fallback_detail=choice.fallback_detail,
            )
        # Nothing to redraw: the colour rides each wall's feed, which is
        # republished when the Library announces the change.
        return PreparationResult(
            artwork_id=artwork_id,
            outcome=PreparationOutcome.PREPARED,
            detail=f"its mat is now {choice.hex_rgb}",
            mat_hex=choice.hex_rgb,
            mat_method=choice.method.value,
            relative_path=self._master_path(artwork_id),
            cost_usd=choice.cost_usd,
            mat_fallback_detail=choice.fallback_detail,
        )

    def _source_for_a_mat(self, artwork_id: str) -> Path:
        """The work's original image on disk, which every mat is judged from, or a
        refusal that says what to do instead."""
        original = self._catalogue.get_original(artwork_id)
        if original is None:
            raise ServiceError(f"Artwork {artwork_id!r} has no acquired original to choose a mat for.")
        source = self._settings.art_root / original.relative_path
        if not source.is_file():
            raise ServiceError(
                f"Artwork {artwork_id!r} records an original at {original.relative_path!r} that is not on disk. "
                "Re-acquire it before choosing a mat."
            )
        return source

    def derived_mat(self, artwork_id: str) -> str:
        """The colour *Re-derive* would record for this work, recording nothing.

        Asked so a control can offer the derivation only when it would change the
        mat, and preview it before it is chosen. Free: no model is asked.
        """
        return derive(self._source_for_a_mat(artwork_id), recording=False).hex_rgb

    def mat_offer(self, artwork_id: str) -> MatOffer:
        """The work's mat, the presets and what deriving would give, recording nothing (`MatOffer`).

        Refused for a work the Library does not hold, rather than answered with
        an empty control. A work with nothing to derive from (no original
        recorded, none on disk, or one that will not decode) is offered the
        presets alone, and why is logged, since a broken image otherwise only
        loses an option silently.
        """
        self._catalogue.get_artwork(artwork_id)
        current = self._catalogue.current_mat_color(artwork_id)
        try:
            derived: str | None = self.derived_mat(artwork_id)
        except ServiceError as refusal:
            log.info(
                "no derived mat offered for %s: %s",
                artwork_id,
                refusal,
                extra={"event": "mat.derivation_unavailable", "artwork_id": artwork_id},
            )
            derived = None
        return MatOffer(current=current, presets=MAT_PRESETS, derived_hex_rgb=derived)

    def derive_mat(self, artwork_id: str) -> PreparationResult:
        """Record the mechanical mat, the work's own dominant colour, at a person's request.

        Recorded as `derived`, not as the fallback: no model was asked and none
        failed. Free, and the previous colour is kept, as every choice keeps it.
        """
        choice = derive(self._source_for_a_mat(artwork_id))
        with self._deciding_the_mat(artwork_id):
            recorded = self._catalogue.record_mat_color(
                artwork_id=artwork_id,
                hex_rgb=choice.hex_rgb,
                method=choice.method,
                lab_l=choice.lab_l,
                lab_a=choice.lab_a,
                lab_b=choice.lab_b,
                reason=choice.reason,
            )
        return PreparationResult(
            artwork_id=artwork_id,
            outcome=PreparationOutcome.PREPARED,
            detail=f"its mat is now {recorded.hex_rgb}, derived from the picture",
            mat_hex=recorded.hex_rgb,
            mat_method=recorded.method.value,
            relative_path=self._master_path(artwork_id),
        )

    def set_mat_preset(self, artwork_id: str, key: str) -> PreparationResult:
        """Record one of the one-press mats (`MAT_PRESETS`), as a person's choice."""
        preset = next((preset for preset in MAT_PRESETS if preset.key == key), None)
        if preset is None:
            known = ", ".join(repr(preset.key) for preset in MAT_PRESETS)
            raise ServiceError(f"There is no mat preset {key!r}; the presets are {known}.")
        return self.set_mat(artwork_id, preset.hex_rgb, reason=f"The {preset.label.lower()} preset.")

    def set_mat(self, artwork_id: str, hex_rgb: str, *, reason: str | None = None) -> PreparationResult:
        """Record a mat colour the curator chose.

        Recorded as `manual`, which is the same provenance the 41 legacy colours
        carry: a person decided this one. It supersedes whatever the model chose
        without discarding it.

        **The curator's spelling is normalised through the same reader the model's
        answer goes through**, so the product gives one answer to "what is a hex
        colour". Without this the two disagreed in the direction nobody would
        defend: `parse_hex` is deliberately lenient about shorthand, a missing `#`
        and upper case — measured leniency, a probed model really did return
        `3F6F7A` — while the catalogue's own check takes only lower-case
        `#rrggbb`. So `#ABC` was accepted from a model and refused from a person,
        on a tool whose parameter says only "a hex triplet".

        A malformed value is still refused, and the translation is not incidental:
        `parse_hex` raises `ColorError`, which is a `ValueError` and not a
        `ServiceError`, so letting it out would turn what had been a clean refusal
        with a message fit to return into an unhandled error at the surface. Only
        the parse is wrapped — a `ServiceError` from the write below must reach the
        caller as itself.

        **A colour darker than `MAT_LIGHTNESS_FLOOR` is refused**, a person's as
        much as the engine's, by `record_mat_color`. Accepting it would put a mat
        on the wall that the owner's ruling forbids, and preparation would then
        choose it again over the person's head.
        """
        try:
            normalised = format_hex(parse_hex(hex_rgb))
        except ColorError as exc:
            raise ServiceError(str(exc)) from exc
        with self._deciding_the_mat(artwork_id):
            recorded = self._catalogue.record_mat_color(
                artwork_id=artwork_id, hex_rgb=normalised, method=MatMethod.MANUAL, reason=reason
            )
        return PreparationResult(
            artwork_id=artwork_id,
            outcome=PreparationOutcome.PREPARED,
            detail=f"its mat is now {recorded.hex_rgb}",
            mat_hex=recorded.hex_rgb,
            mat_method=recorded.method.value,
            relative_path=self._master_path(artwork_id),
        )

    def _current_or_chosen_mat(self, artwork_id: str, *, source: Path) -> tuple[MatColor, MatChoice | None, bool]:
        """The mat in force, choosing one only if the work has none it may keep.

        **The reason a remake is free for a work that already has a mat.** A
        mat is a judgement, and re-asking a model for one the work already has
        would both spend money and quietly replace a decision — including a
        curator's own manual choice, which is the worst version of it.

        Returns the choice alongside the record, and the second element is the
        whole point: `None` means nothing was asked and nothing was spent, while a
        `MatChoice` carries what the call cost and whether the model actually
        answered. Without it the caller cannot tell a free call from a paid one,
        and would have to either report every preparation as free — which is
        false on a work's first — or report a cost it never incurred. The third
        says the model's answer was not recorded, because a person chose a mat
        while it was asked (`_record_the_models_mat`); the record is then theirs.

        **A mat below the floor is not kept**, whoever chose it: nothing can record
        one now (`CatalogueService.record_mat_color` refuses it), so it is a
        colour from before the owner's ruling, and it is chosen again.
        """
        current = self._catalogue.current_mat_color(artwork_id)
        if current is not None and not below_the_floor(current.hex_rgb):
            return current, None, False
        if current is not None:
            log.info(
                "the mat of %s, %s, is below the floor of L* %g; choosing again",
                artwork_id,
                current.hex_rgb,
                MAT_LIGHTNESS_FLOOR,
                extra={"event": "preparation.mat_below_floor", "artwork_id": artwork_id, "hex_rgb": current.hex_rgb},
            )
        choice = self._mat.choose(source)
        # Before the colour is written, so a refused write keeps the billed cost
        # (and the queue's retry, which asks the model again, is a second row).
        self._record_spend(artwork_id, choice)
        standing = self._record_the_models_mat(artwork_id, choice, asked_over=current)
        if standing is not None:
            return standing, choice, True
        recorded = self._catalogue.current_mat_color(artwork_id)
        if recorded is None:
            raise ServiceError(f"Artwork {artwork_id!r} has no mat after one was recorded for it.")
        return recorded, choice, False

    def _record_the_models_mat(self, artwork_id: str, choice: MatChoice, *, asked_over: MatColor | None) -> MatColor | None:
        """Record the model's colour unless the mat changed while it was asked; else return the mat that stands.

        **A person's choice wins.** The model takes seconds to answer, and a
        curator who presses a preset or types a colour meanwhile has decided:
        recording the model's answer after theirs would put back a colour they
        had just replaced, with nothing said. So the mat in force is compared
        with the one the model was asked over, by its record (the same colour
        chosen again is still a decision), and the answer is recorded only if
        they are one. The check and the write are one step under the work's mat
        lock, which every mat this service records takes. Its cost is recorded
        either way, by the caller: it was billed.
        """
        with self._deciding_the_mat(artwork_id):
            now = self._catalogue.current_mat_color(artwork_id)
            if (now.id if now else None) != (asked_over.id if asked_over else None):
                log.info(
                    "kept the mat chosen for %s while the model was asked, rather than the model's %s",
                    artwork_id,
                    choice.hex_rgb,
                    extra={"event": "preparation.mat_kept_over_model", "artwork_id": artwork_id},
                )
                return now
            self._catalogue.record_mat_color(
                artwork_id=artwork_id,
                hex_rgb=choice.hex_rgb,
                method=choice.method,
                lab_l=choice.lab_l,
                lab_a=choice.lab_a,
                lab_b=choice.lab_b,
                reason=choice.reason or None,
                model_id=choice.model_id,
            )
        return None

    def _record_spend(self, artwork_id: str, choice: MatChoice) -> None:
        """Record what asking the model for this work's mat cost, when the model answered or billed.

        **Here, beside the choice, so the record follows the call and not the
        route in.** Every path that asks — a first preparation, from the
        acquisition queue or from MCP's `regenerate`, and `choose_mat` — passes
        through one of the two methods that call this.

        A fallback can be billed: the model answered with something unusable, and
        `cost_usd` carries what that answer cost while `model_id` is None, because
        no model chose the colour. The row names the model that was asked all the
        same, since that is who billed it. A call that never reached the model
        (no key, or a refused request) cost nothing and records nothing.

        A call sent that never said what it cost (`MatChoice.unknown_cost_calls`)
        is a row of its own, at 0 with its cost unknown, beside any row for what
        an earlier call of the same choice was billed.
        """
        if choice.method is MatMethod.VISION_MODEL or choice.cost_usd != 0:
            self._spend.record_spend(
                category=SpendCategory.MAT_COLOR_VISION,
                cost_usd=choice.cost_usd,
                artwork_id=artwork_id,
                model_id=choice.model_id or self._mat.model_id,
                units=1,
            )
        for _ in range(choice.unknown_cost_calls):
            self._spend.record_spend(
                category=SpendCategory.MAT_COLOR_VISION,
                cost_usd=Decimal(0),
                artwork_id=artwork_id,
                model_id=self._mat.model_id,
                units=1,
                cost_status=CostStatus.UNKNOWN,
            )

    def _make_master_if_owed(self, artwork_id: str, *, source: Path, force: bool = False) -> bool:
        """Make the work's presentation master unless a current one is on disk, or always when forced. True if made.

        Current means what it means for every Rendition — recorded from the
        Original the work holds now — and made by today's `MASTER_RULE`, and the
        file is on disk: a row whose file
        is gone is the state a restored catalogue leaves, and a Player asking for
        it by hash would be refused. Recorded after the file exists, never
        before, so no row names a master that was never written.
        """
        for view in self._catalogue.list_renditions(artwork_id):
            rendition = view.rendition
            if (
                not force
                and rendition.kind is RenditionKind.PRESENTATION_MASTER
                and not view.stale
                and rendition.layout == MASTER_RULE
                and (self._settings.art_root / rendition.relative_path).is_file()
            ):
                return False
        destination = master_path(self._settings.masters_path, artwork_id)
        master = make_master(source, destination=destination)
        self._catalogue.record_rendition(
            artwork_id=artwork_id,
            kind=RenditionKind.PRESENTATION_MASTER,
            # The cap, not the size produced: the row is keyed on its target, so
            # a work's master keeps one row however its Original changes size.
            target_width=PRESENTATION_MASTER_LONG_EDGE_PX,
            target_height=PRESENTATION_MASTER_LONG_EDGE_PX,
            path=str(destination.relative_to(self._settings.art_root)),
            layout=MASTER_RULE,
        )
        log.info(
            "made the presentation master for %s at %sx%s",
            artwork_id,
            master.width,
            master.height,
            extra={"event": "preparation.master_made", "artwork_id": artwork_id, "width": master.width, "height": master.height},
        )
        return True

    def _master_path(self, artwork_id: str) -> str | None:
        """The work's presentation master, relative to `ART_ROOT`, or None if it has none."""
        for view in self._catalogue.list_renditions(artwork_id):
            if view.rendition.kind is RenditionKind.PRESENTATION_MASTER:
                return view.rendition.relative_path
        return None


__all__ = [
    "PreparationOutcome",
    "PreparationResult",
    "PreparationService",
    "PreparationSettings",
    "SpendLedger",
]
