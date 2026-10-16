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
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Protocol

from arrt.library.acquisition.color import ColorError, format_hex, parse_hex
from arrt.library.acquisition.master import MASTER_RULE, MASTERS_DIRNAME, make_master, master_path
from arrt.library.acquisition.mat import MAT_LIGHTNESS_FLOOR, MatChoice, MatEngine, below_the_floor
from arrt.library.services.catalogue import CatalogueService
from arrt.library.services.quality import PRESENTATION_MASTER_LONG_EDGE_PX
from arrt.persistence.discovery_records import SpendCategory
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
        """
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
        mat, chosen = self._current_or_chosen_mat(artwork_id, source=source)
        done = [part for part, did in (("its presentation master was made", made), ("its mat was chosen", chosen)) if did]
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

    def choose_mat(self, artwork_id: str) -> PreparationResult:
        """Ask the vision model for this work's mat colour again.

        Its own operation rather than a flag on `prepare`, because it is the one
        that spends money and the one that supersedes a judgement. The previous
        colour is kept — `record_mat_color` never overwrites — so a worse choice
        is reversible.
        """
        original = self._catalogue.get_original(artwork_id)
        if original is None:
            raise ServiceError(f"Artwork {artwork_id!r} has no acquired original to choose a mat for.")
        source = self._settings.art_root / original.relative_path
        if not source.is_file():
            raise ServiceError(
                f"Artwork {artwork_id!r} records an original at {original.relative_path!r} that is not on disk. "
                "Re-acquire it before choosing a mat."
            )

        choice = self._mat.choose(source)
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
        self._record_spend(artwork_id, choice)
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

    def set_mat(self, artwork_id: str, hex_rgb: str) -> PreparationResult:
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
        recorded = self._catalogue.record_mat_color(artwork_id=artwork_id, hex_rgb=normalised, method=MatMethod.MANUAL)
        return PreparationResult(
            artwork_id=artwork_id,
            outcome=PreparationOutcome.PREPARED,
            detail=f"its mat is now {recorded.hex_rgb}",
            mat_hex=recorded.hex_rgb,
            mat_method=recorded.method.value,
            relative_path=self._master_path(artwork_id),
        )

    def _current_or_chosen_mat(self, artwork_id: str, *, source: Path) -> tuple[MatColor, MatChoice | None]:
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
        false on a work's first — or report a cost it never incurred.

        **A mat below the floor is not kept**, whoever chose it: nothing can record
        one now (`CatalogueService.record_mat_color` refuses it), so it is a
        colour from before the owner's ruling, and it is chosen again.
        """
        current = self._catalogue.current_mat_color(artwork_id)
        if current is not None and not below_the_floor(current.hex_rgb):
            return current, None
        if current is not None:
            log.info(
                "the mat of %s, %s, is below the floor of L* %g; choosing again",
                artwork_id,
                current.hex_rgb,
                MAT_LIGHTNESS_FLOOR,
                extra={"event": "preparation.mat_below_floor", "artwork_id": artwork_id, "hex_rgb": current.hex_rgb},
            )
        choice = self._mat.choose(source)
        recorded = self._catalogue.record_mat_color(
            artwork_id=artwork_id,
            hex_rgb=choice.hex_rgb,
            method=choice.method,
            lab_l=choice.lab_l,
            lab_a=choice.lab_a,
            lab_b=choice.lab_b,
            reason=choice.reason or None,
            model_id=choice.model_id,
        )
        self._record_spend(artwork_id, choice)
        return recorded, choice

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
        """
        if choice.method is not MatMethod.VISION_MODEL and choice.cost_usd == 0:
            return
        self._spend.record_spend(
            category=SpendCategory.MAT_COLOR_VISION,
            cost_usd=choice.cost_usd,
            artwork_id=artwork_id,
            model_id=choice.model_id or self._mat.model_id,
            units=1,
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
