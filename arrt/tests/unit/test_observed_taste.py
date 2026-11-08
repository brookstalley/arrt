"""Review's verdicts become taste: the owner's rule, through the verdict that applies it.

The rule (2026-11-08, `agents-and-memory.md` open question 1): by artist, at least
5 verdicts one way and at least 90% of the artist's verdicts. Rejections write an
observed `declines`, acceptances an observed `likes`. A `stated` judgment is never
overwritten. Driven through `set_verdict`, the caller that applies it, so a rule
nobody calls fails here.
"""

from datetime import UTC, datetime

import pytest

from arrt.library.services.taste import observed_sentiment
from arrt.persistence.discovery_records import Affinity, AffinityDerivation, AffinitySentiment, Verdict
from arrt.persistence.records import VocabularyKind

KLIMT = "Gustav Klimt"


@pytest.mark.parametrize(
    ("accepted", "rejected", "expected"),
    [
        (0, 4, None),
        (0, 5, AffinitySentiment.DECLINES),
        (1, 9, AffinitySentiment.DECLINES),  # exactly 90%
        (2, 9, None),  # 82%
        # The owner's own example: never a dislike. By the mirror rule, 100 of 105 accepted is a like.
        (100, 5, AffinitySentiment.LIKES),
        (4, 0, None),
        (5, 0, AffinitySentiment.LIKES),
        (9, 1, AffinitySentiment.LIKES),
        (9, 2, None),
        (0, 0, None),
    ],
)
def test_the_rule_at_its_edges(accepted, rejected, expected):
    assert observed_sentiment(accepted=accepted, rejected=rejected) is expected


@pytest.fixture
def decide(discovery, resolved_work, propose):
    """Decide `count` works by `artist` with `verdict`, each a distinct work."""
    made = [0]

    def _decide(verdict: Verdict, count: int, artist: str | None = KLIMT) -> None:
        for _ in range(count):
            made[0] += 1
            title = f"Work {made[0]}"
            if verdict is Verdict.ACCEPTED:
                work = resolved_work(title, proposed_artist=artist)
                discovery.set_verdict(work.id, Verdict.ACCEPTED)
            elif verdict is Verdict.WANTED:
                discovery.want(propose(title, proposed_artist=artist).id)
            else:
                discovery.set_verdict(propose(title, proposed_artist=artist).id, verdict)

    return _decide


def artist_taste(services) -> list[Affinity]:
    return list(services.taste.list_affinities(kind="artist"))


def test_five_rejections_write_an_observed_dislike_that_offers_no_more(services, decide):
    decide(Verdict.REJECTED, 5)

    [judgment] = artist_taste(services)
    assert (judgment.value, judgment.sentiment, judgment.open_to_more, judgment.derivation) == (
        KLIMT,
        AffinitySentiment.DECLINES,
        False,
        AffinityDerivation.OBSERVED,
    )
    assert judgment.rationale == f"Rejected 5 of the 5 works by {KLIMT} decided in review."


def test_four_rejections_write_nothing(services, decide):
    decide(Verdict.REJECTED, 4)

    assert artist_taste(services) == []


def test_five_acceptances_write_an_observed_like_that_stays_open(services, decide):
    decide(Verdict.ACCEPTED, 5)

    [judgment] = artist_taste(services)
    assert (judgment.sentiment, judgment.open_to_more, judgment.derivation) == (
        AffinitySentiment.LIKES,
        True,
        AffinityDerivation.OBSERVED,
    )
    assert judgment.rationale == f"Accepted 5 of the 5 works by {KLIMT} decided in review."


def test_a_falling_share_withdraws_the_judgment_and_a_turn_writes_the_other(services, decide):
    """The row reflects the verdicts as they stand: written, withdrawn, then the other way."""
    decide(Verdict.REJECTED, 5)
    decide(Verdict.ACCEPTED, 1)  # 5 of 6 rejected: 83%
    assert artist_taste(services) == []

    decide(Verdict.ACCEPTED, 54)  # 54 of 60 accepted: 90%
    [judgment] = artist_taste(services)
    assert judgment.sentiment is AffinitySentiment.LIKES


def test_a_stated_judgment_under_another_spelling_is_never_overwritten(services, decide):
    services.taste.set_affinity(kind="artist", value="gustav klimt", sentiment="loves", open_to_more=True)

    decide(Verdict.REJECTED, 6)

    [judgment] = artist_taste(services)
    assert (judgment.value, judgment.sentiment, judgment.derivation) == (
        "gustav klimt",
        AffinitySentiment.LOVES,
        AffinityDerivation.STATED,
    )


def an_inferred_klimt(discovery_store, value: str = "Gustav Klímt") -> Affinity:
    now = datetime.now(UTC)
    row = Affinity(
        id="inferred-klimt",
        kind=VocabularyKind.ARTIST,
        value=value,
        sentiment=AffinitySentiment.LIKES,
        open_to_more=True,
        derivation=AffinityDerivation.INFERRED,
        created_at=now,
        updated_at=now,
        rationale="they asked for gold",
    )
    discovery_store.add_affinity(row)
    return row


def test_an_inferred_judgment_of_the_same_artist_is_left_alone(services, decide, discovery_store):
    """Nothing can write an inferred row any more, so replacing one would lose it for good."""
    inferred = an_inferred_klimt(discovery_store)

    decide(Verdict.REJECTED, 5)

    assert artist_taste(services) == [inferred]


def test_an_inferred_judgment_of_another_artist_does_not_stop_this_one(services, decide, discovery_store):
    """ "Klimt, Gustav" is not the same key as "Gustav Klimt", so it is another thing and both stand."""
    other = an_inferred_klimt(discovery_store, value="Klimt, Gustav")

    decide(Verdict.REJECTED, 5)

    judgments = artist_taste(services)
    assert other in judgments
    [observed] = [each for each in judgments if each.derivation is AffinityDerivation.OBSERVED]
    assert observed.value == KLIMT


def test_a_stated_judgment_made_after_an_observed_one_withdraws_it(services, decide):
    """Under another spelling the two are separate rows; the observed one goes, so they never contradict."""
    decide(Verdict.REJECTED, 5)
    services.taste.set_affinity(kind="artist", value="gustav klimt", sentiment="loves", open_to_more=True)

    decide(Verdict.REJECTED, 1)

    [judgment] = artist_taste(services)
    assert (judgment.value, judgment.derivation) == ("gustav klimt", AffinityDerivation.STATED)


def test_each_verdict_brings_the_counts_up_to_date(services, decide):
    decide(Verdict.REJECTED, 5)
    [first] = artist_taste(services)

    decide(Verdict.REJECTED, 1)

    [judgment] = artist_taste(services)
    assert judgment.id == first.id, "corrected in place"
    assert judgment.rationale == f"Rejected 6 of the 6 works by {KLIMT} decided in review."


def test_wanted_works_and_unattributed_works_say_nothing(services, decide):
    decide(Verdict.WANTED, 5)
    decide(Verdict.REJECTED, 5, artist=None)

    assert artist_taste(services) == []


def test_artists_are_counted_apart(services, decide):
    decide(Verdict.REJECTED, 4)
    decide(Verdict.REJECTED, 4, artist="Egon Schiele")

    assert artist_taste(services) == []


# -- existing verdicts, at startup ----------------------------------------------


def test_reobserving_writes_what_the_existing_verdicts_show(services, decide, discovery_store):
    decide(Verdict.REJECTED, 5)
    decide(Verdict.ACCEPTED, 5, artist="Egon Schiele")
    for judgment in artist_taste(services):
        discovery_store.delete_affinity(judgment.id)  # a catalogue from before review wrote taste

    assert services.taste.reobserve() == 2

    by_artist = {judgment.value: judgment.sentiment for judgment in artist_taste(services)}
    assert by_artist == {KLIMT: AffinitySentiment.DECLINES, "Egon Schiele": AffinitySentiment.LIKES}


def test_reobserving_again_changes_nothing_and_follows_new_verdicts(services, decide):
    decide(Verdict.REJECTED, 5)
    services.taste.reobserve()
    first = artist_taste(services)

    services.taste.reobserve()
    assert artist_taste(services) == first, "an unchanged catalogue is left exactly as it was"

    decide(Verdict.ACCEPTED, 1)  # varied between runs: the share falls to 83%
    services.taste.reobserve()
    assert artist_taste(services) == []


def test_reobserving_withdraws_an_observed_judgment_with_no_verdicts_behind_it(services, discovery_store):
    now = datetime.now(UTC)
    discovery_store.add_affinity(
        Affinity(
            id="orphan",
            kind=VocabularyKind.ARTIST,
            value="Nobody",
            sentiment=AffinitySentiment.DECLINES,
            open_to_more=False,
            derivation=AffinityDerivation.OBSERVED,
            created_at=now,
            updated_at=now,
            rationale="Rejected 5 of the 5 works by Nobody decided in review.",
        )
    )

    assert services.taste.reobserve() == 0
    assert artist_taste(services) == []


def test_startup_reconcile_reobserves(services, decide, discovery_store):
    """Through the call a process start makes, so a pass nobody calls fails here."""
    decide(Verdict.REJECTED, 5)
    for judgment in artist_taste(services):
        discovery_store.delete_affinity(judgment.id)

    services.reconcile()

    [judgment] = artist_taste(services)
    assert judgment.sentiment is AffinitySentiment.DECLINES
