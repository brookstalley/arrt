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
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from fractions import Fraction
from typing import Final

from arrt.library.discovery.dedup import artist_key, artist_prefix
from arrt.persistence.discovery import DiscoveryStore
from arrt.persistence.discovery_records import Affinity, AffinityDerivation, AffinitySentiment, Verdict
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
    It is a function rather than a method so that every
    writer — the review path that asserts `observed` (`observe_artist`), a rebuild that
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


# -- observed taste ---------------------------------------------------------

#: The fewest verdicts one way before review's decisions say anything about an
#: artist, and the share of the artist's verdicts they must be. The owner's rule
#: (2026-11-08, `agents-and-memory.md` open question 1): "at least 5, but with at
#: least 90% rejections (100 approvals and 5 rejections is fine)", and the same
#: rule for approvals.
OBSERVED_AT_LEAST: Final[int] = 5
OBSERVED_SHARE: Final[Fraction] = Fraction(9, 10)


def observed_sentiment(*, accepted: int, rejected: int) -> AffinitySentiment | None:
    """What an artist's verdicts say about them, or None when they say nothing yet.

    `declines` for a run of rejections, `likes` for a run of acceptances, never
    `loves`, which only the curator states. Both thresholds are inclusive, and the
    share is compared as a fraction so 9 of 10 is exactly 90%.
    """
    total = accepted + rejected
    if rejected >= OBSERVED_AT_LEAST and Fraction(rejected, total) >= OBSERVED_SHARE:
        return AffinitySentiment.DECLINES
    if accepted >= OBSERVED_AT_LEAST and Fraction(accepted, total) >= OBSERVED_SHARE:
        return AffinitySentiment.LIKES
    return None


def observe_artist(store: DiscoveryStore, artist: str | None) -> Affinity | None:
    """Re-derive the observed judgment of one artist from every verdict on their works, and store it.

    **What review's decisions write, and the only writer of `observed`.** Called
    for the work's artist on every accept and reject, and for every artist at
    startup, so the row always reflects the verdicts as they stand: written when
    the rule holds, corrected when it holds the other way, removed when it stops.

    **An artist is their `artist_key`**, the identity that already makes "Dali"
    and "Dalí" one artist when deciding whether two proposals are one work. So a
    judgment about the same artist under another spelling is the same judgment:
    a `stated` one anywhere under the key leaves the artist alone (the curator's
    words outrank their verdicts), and an `inferred` one is replaced, since a
    model's reading of the curator's words is weaker than their decisions.

    Returns the observed judgment now stored, or None when there is none.
    """
    prefix = None if artist is None else artist_prefix(artist)
    if artist is None or prefix is None:
        # Unattributed works are nobody's, so they say nothing about anybody.
        return None
    key = artist_key(artist)
    works = store.list_decided_works(prefix)
    accepted = sum(work.verdict is Verdict.ACCEPTED for work in works)
    rejected = sum(work.verdict is Verdict.REJECTED for work in works)
    sentiment = observed_sentiment(accepted=accepted, rejected=rejected)

    same_artist = [
        affinity for affinity in store.list_affinities(kind=VocabularyKind.ARTIST) if artist_key(affinity.value) == key
    ]
    if any(affinity.derivation is AffinityDerivation.STATED for affinity in same_artist):
        return None
    observed = [affinity for affinity in same_artist if affinity.derivation is AffinityDerivation.OBSERVED]
    if sentiment is None:
        for stale in observed:
            store_write(store.delete_affinity, stale.id)
            log.info("an observed taste was withdrawn", extra={"event": "taste.unobserved", "kind": str(stale.kind)})
        return None

    # Named as the latest verdict named them; works are read oldest decision first.
    named = next((work.proposed_artist for work in reversed(works) if work.proposed_artist), artist)
    decided = accepted + rejected
    rationale = (
        f"Rejected {rejected} of the {decided} works by {named} decided in review."
        if sentiment is AffinitySentiment.DECLINES
        else f"Accepted {accepted} of the {decided} works by {named} decided in review."
    )
    write = validated_write(
        kind=VocabularyKind.ARTIST,
        value=named,
        sentiment=sentiment,
        open_to_more=sentiment is AffinitySentiment.LIKES,
        derivation=AffinityDerivation.OBSERVED,
        rationale=rationale,
    )
    now = datetime.now(UTC)
    # Corrected in place where a judgment of this artist exists, under the name it
    # already has: the unique index is on the name, and renaming it is not this
    # rule's business.
    standing = observed or [affinity for affinity in same_artist if affinity.derivation is AffinityDerivation.INFERRED]
    if standing:
        current = standing[0]
        if (current.sentiment, current.open_to_more, current.derivation, current.rationale) == (
            write.sentiment,
            write.open_to_more,
            write.derivation,
            write.rationale,
        ):
            return current
        corrected = replace(
            current,
            sentiment=write.sentiment,
            open_to_more=write.open_to_more,
            derivation=write.derivation,
            rationale=write.rationale,
            updated_at=now,
        )
        store_write(store.update_affinity, corrected)
        log.info("an observed taste was corrected", extra={"event": "taste.observed", "sentiment": str(write.sentiment)})
        return corrected
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
    store_write(store.add_affinity, fresh)
    log.info("an observed taste was recorded", extra={"event": "taste.observed", "sentiment": str(write.sentiment)})
    return fresh


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

    def reobserve(self) -> int:
        """Re-derive every artist's observed judgment from the verdicts as they stand; how many are stored.

        Run at startup, so a catalogue holding verdicts from before review wrote
        taste gets its observed judgments, and a change to the rule reaches every
        row rather than only the artists decided on next. Each artist once, by
        `artist_key`, under the name of their first verdict read; `observe_artist`
        names the row from the latest.
        """
        seen: dict[str, str] = {}
        for work in self._store.list_decided_works():
            if work.proposed_artist and (key := artist_key(work.proposed_artist)):
                seen.setdefault(key, work.proposed_artist)
        # An observed row whose artist has no decided work left is withdrawn too.
        for affinity in self._store.list_affinities(kind=VocabularyKind.ARTIST, derivation=AffinityDerivation.OBSERVED):
            seen.setdefault(artist_key(affinity.value), affinity.value)
        return sum(observe_artist(self._store, artist) is not None for artist in seen.values())

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
