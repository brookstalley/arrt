"""What the product has accumulated about the curator, and the rules for writing it.

An affinity is a standing judgment about a thing — an artist, a movement, an era,
a subject, a medium, a palette — retained over time and consulted when
discovery proposes. It is the product's memory of its operator, which is why the
whole of this module is about *provenance*: a taste model that cannot say where a
judgment came from is one the curator can only argue with, never fix.

**Every invariant here is enforced on the write path and none of them is stored**,
so a rule can refuse a new *write* without saying anything about a row that
already exists.

**No caller can write an `inferred` judgment now.** One was a model's reading of
something the curator said, and it had to cite the stored turn it was read out
of. Conversations are no longer stored (Ask's threads live in memory), so there
is nothing to cite. The `inferred` rows already in the catalogue stay, with their
`rationale` as the evidence they have left. The wave that saves Ask's threads
decides how a judgment cites one.

**`rationale` is required for `inferred` and `observed`**, because neither cites
anything stored, and a judgment with no account is one the product can neither
explain nor revisit.
"""

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from arrt.persistence.discovery import DiscoveryStore
from arrt.persistence.discovery_records import Affinity, AffinityDerivation, AffinitySentiment
from arrt.persistence.records import VocabularyKind
from arrt.services.errors import ServiceError
from arrt.services.fields import require_member, require_text
from arrt.services.store import store_write

log = logging.getLogger(__name__)

#: The derivations that must carry a rationale, and why the set is these two.
#: `stated` has the curator's own words as its account and needs no second one;
#: the other two are claims *about* the curator, and the rationale is the only
#: evidence either of them has.
NEEDS_RATIONALE: Final[frozenset[AffinityDerivation]] = frozenset({AffinityDerivation.INFERRED, AffinityDerivation.OBSERVED})


@dataclass(frozen=True, slots=True)
class AffinityWrite:
    """One judgment as a caller offers it, before anything has been stored.

    Its own type rather than a bag of keyword arguments because two callers — the
    HTTP route and the MCP binding — assemble the identical thing, and the
    validation below is what both of them are for.
    """

    kind: VocabularyKind
    value: str
    sentiment: AffinitySentiment
    open_to_more: bool
    derivation: AffinityDerivation
    rationale: str | None = None
    artist_id: str | None = None


def validated_write(
    *,
    kind: object,
    value: str,
    sentiment: object,
    open_to_more: object,
    derivation: object,
    rationale: str | None = None,
    artist_id: str | None = None,
) -> AffinityWrite:
    """Turn what a caller sent into a judgment that may be stored, or refuse it.

    **This is the write path the derivation rules live on**, and the only one.
    It is a function rather than a method so that every future
    writer — the review path that will one day assert `observed`, a rebuild that
    re-derives judgments when the eliciting prompt improves — goes through the
    same checks without having to be a caller of `set_affinity`.

    `sentiment` and `open_to_more` are both required, with no default for either.
    They are two fields precisely so "meh on Magritte, but open to learning more"
    is writable, and the default that reads as safe — do not offer more — is the
    one that silently blacklists an artist the curator asked to keep hearing about.
    """
    chosen_kind = require_member(kind, enum=VocabularyKind, field="kind")
    chosen_sentiment = require_member(sentiment, enum=AffinitySentiment, field="sentiment")
    chosen_derivation = require_member(derivation, enum=AffinityDerivation, field="derivation")
    if not isinstance(open_to_more, bool):
        raise ServiceError(
            f"open_to_more must be true or false, got {open_to_more!r}. It is a separate fact from sentiment: "
            "a lukewarm judgment that is still open to more is the case the two fields exist for."
        )
    named = require_text(value, field="value")

    if chosen_derivation is AffinityDerivation.INFERRED:
        raise ServiceError(
            "A judgment cannot be written as 'inferred' now: it would have to cite the conversation it was "
            "read out of, and conversations are not stored. Write it as 'stated' if the curator said it "
            "themselves, since their own words are the provenance."
        )
    account = None if rationale is None or not rationale.strip() else rationale.strip()
    if chosen_derivation in NEEDS_RATIONALE and account is None:
        raise ServiceError(
            f"An {chosen_derivation!r} judgment needs a rationale — the account of the judgment in the "
            "curator's terms, which is the only evidence such a row has."
        )
    return AffinityWrite(
        kind=chosen_kind,
        value=named,
        sentiment=chosen_sentiment,
        open_to_more=open_to_more,
        derivation=chosen_derivation,
        rationale=account,
        artist_id=artist_id,
    )


#: How many judgments a prompt is told. A household's taste is tens of rows, so
#: this binds only on a taste far past what `list_affinities` was sized for, and
#: then the brief says how many it left out rather than dropping them silently.
TASTE_TOLD: Final[int] = 200

#: The longest a judgment's name or rationale is told, in characters. Both are
#: stored unbounded and resent with every Ask reply and every phase 1 run, so a
#: name pasted at length, or written by a steered agent, is cut here rather than
#: carried whole into every prompt. Real names and rationales fit with room.
TASTE_TEXT_TOLD: Final[int] = 160

#: Strongest feeling first, so a brief cut at `TASTE_TOLD` keeps the judgments
#: that most change what a model should offer.
_SENTIMENT_ORDER: Final[tuple[AffinitySentiment, ...]] = (
    AffinitySentiment.LOVES,
    AffinitySentiment.DECLINES,
    AffinitySentiment.LIKES,
    AffinitySentiment.COOL,
)


def describe_taste(affinities: Sequence[Affinity], *, limit: int = TASTE_TOLD) -> str:
    """The curator's taste as lines a model is told, or an empty string when there is none.

    One rendering for every prompt that carries taste (Ask's and discovery's
    phase 1), so the two agents are told the same thing in the same words.

    `open_to_more` is spelled out on every line rather than left to be inferred
    from the sentiment: "cool on Magritte, but keep offering" is the case the two
    fields exist for, and a model reading only the sentiment would stop offering.
    A judgment that is not `stated` names its derivation and its rationale,
    because a model should weigh the curator's words above the product's reading
    of them.
    """
    if not affinities:
        return ""
    rank = {sentiment: index for index, sentiment in enumerate(_SENTIMENT_ORDER)}
    ordered = sorted(affinities, key=lambda each: (rank.get(each.sentiment, len(rank)), str(each.kind), each.value.casefold()))
    lines = [_taste_line(each) for each in ordered[:limit]]
    left_out = len(ordered) - len(lines)
    if left_out > 0:
        lines.append(f"- ({left_out} more judgments are not listed.)")
    return "\n".join(lines)


def _taste_line(affinity: Affinity) -> str:
    more = "keep offering more" if affinity.open_to_more else "offer no more"
    line = f"- {affinity.sentiment} {affinity.kind} “{_told(affinity.value)}”: {more}"
    if affinity.derivation is not AffinityDerivation.STATED:
        account = f": {_told(affinity.rationale)}" if affinity.rationale else ""
        line += f" ({affinity.derivation}{account})"
    return line


def _told(text: str) -> str:
    """`text` on one line and at most `TASTE_TEXT_TOLD` characters, an ellipsis marking a cut."""
    flat = " ".join(text.split())
    return flat if len(flat) <= TASTE_TEXT_TOLD else flat[: TASTE_TEXT_TOLD - 1] + "…"


class TasteService:
    """The curator's standing judgments: reading them, correcting them, forgetting one."""

    def __init__(self, store: DiscoveryStore) -> None:
        self._store = store

    # -- reads ----------------------------------------------------------------

    def list_affinities(
        self,
        *,
        kind: object = None,
        sentiment: object = None,
        derivation: object = None,
    ) -> Sequence[Affinity]:
        """Every judgment, narrowed by any of the three things worth narrowing by.

        Unpaged, and that is a decision rather than an omission: this returns a
        household's entire taste, which is tens of rows. The moment it stops being
        tens, `api-contract.md` § Conditional Patterns' limit-and-report-the-total
        rule is what bounds it, and this method is where that lands.
        """
        return self._store.list_affinities(
            kind=None if kind is None else require_member(kind, enum=VocabularyKind, field="kind"),
            sentiment=None if sentiment is None else require_member(sentiment, enum=AffinitySentiment, field="sentiment"),
            derivation=(None if derivation is None else require_member(derivation, enum=AffinityDerivation, field="derivation")),
        )

    def brief(self) -> str:
        """The household's taste as every prompt is told it: `describe_taste` over `list_affinities`.

        The one owner of the brief, so Ask's prompt and phase 1's read the taste
        by the same path and cannot diverge when that read is bounded.
        """
        return describe_taste(self.list_affinities())

    def get_affinity(self, affinity_id: str) -> Affinity:
        found = self._store.get_affinity(affinity_id)
        if found is None:
            raise ServiceError(f"No affinity with id {affinity_id!r}.")
        return found

    # -- writes ---------------------------------------------------------------

    def set_affinity(
        self,
        *,
        kind: object,
        value: str,
        sentiment: object,
        open_to_more: object,
        derivation: object = AffinityDerivation.STATED,
        rationale: str | None = None,
    ) -> Affinity:
        """Write one judgment over whatever was there, or write the first one.

        **An upsert, and named `set` for that reason.** A judgment is unique on
        (`kind`, `value`) — one live opinion per thing, corrected in place rather
        than accumulating contradictions the product would then have to arbitrate
        between. `create` would be a lie on the second call and `update` on the
        first.

        **A caller may not write `observed`.** That value means the product read
        the judgment out of accept-and-reject behaviour in review, and only the
        review path can assert it truthfully. An `observed` row written by a
        caller is a fabricated observation, indistinguishable afterwards from one
        the product earned — and Q14's rebuild would then have nothing to rebuild
        from.

        **The upsert replaces the provenance with its own**, derivation and
        rationale together, so a row never carries an account that did not
        produce the judgment stored on it. Only `stated` can be written, the
        strongest claim there is, so a write never weakens what a row says
        about where it came from.
        """
        write = validated_write(
            kind=kind,
            value=value,
            sentiment=sentiment,
            open_to_more=open_to_more,
            derivation=derivation,
            rationale=rationale,
        )
        if write.derivation is AffinityDerivation.OBSERVED:
            raise ServiceError(
                "A judgment cannot be set as 'observed'. That means the product read it out of what was "
                "accepted and rejected in review, which only the review path can say truthfully. Write "
                "'stated' if the curator said it."
            )

        now = datetime.now(UTC)
        standing = self._store.find_affinity(kind=write.kind, value=write.value)
        if standing is None:
            fresh = Affinity(
                id=str(uuid.uuid4()),
                kind=write.kind,
                value=write.value,
                sentiment=write.sentiment,
                open_to_more=write.open_to_more,
                derivation=write.derivation,
                created_at=now,
                updated_at=now,
                rationale=write.rationale,
            )
            store_write(self._store.add_affinity, fresh)
            log.info(
                "a taste was recorded",
                extra={"event": "taste.set", "kind": str(fresh.kind), "derivation": str(fresh.derivation)},
            )
            return fresh

        corrected = Affinity(
            id=standing.id,
            kind=standing.kind,
            value=standing.value,
            sentiment=write.sentiment,
            open_to_more=write.open_to_more,
            # Provenance is replaced wholesale: derivation and rationale together.
            derivation=write.derivation,
            created_at=standing.created_at,
            updated_at=now,
            rationale=write.rationale,
            artist_id=standing.artist_id,
        )
        store_write(self._store.update_affinity, corrected)
        log.info(
            "a taste was corrected",
            extra={"event": "taste.set", "kind": str(corrected.kind), "derivation": str(corrected.derivation)},
        )
        return corrected

    def delete_affinity(self, affinity_id: str) -> Affinity:
        """Forget one judgment, and return what was forgotten.

        Returned rather than acknowledged with an id, because this is not
        recoverable and the confirmation a surface reports should name the thing
        that is gone rather than the handle it was addressed by.
        """
        going = self.get_affinity(affinity_id)
        store_write(self._store.delete_affinity, affinity_id)
        log.info("a taste was forgotten", extra={"event": "taste.deleted", "kind": str(going.kind)})
        return going
