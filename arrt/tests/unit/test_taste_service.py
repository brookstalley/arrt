"""The rules a judgment about the curator has to satisfy before it can be stored.

Service level, over the real store, because every rule here is about what the
*file* is allowed to end up holding and a fake store would let this suite agree
with itself about a shape SQLite would refuse.

**Every check in this file is a check on the write path, and that is the point
rather than an implementation detail.** The catalogue holds `inferred` rows that
no caller can write any more, read out of conversations that are no longer
stored. The invariants therefore live where a *write* can be refused without
saying anything about a row already on disk, and the tests that prove they
exist have to be here rather than against the schema.
"""

from datetime import UTC, datetime

import pytest

from arrt.library.services.taste import NEEDS_RATIONALE, TasteService, validated_write
from arrt.persistence.discovery_records import Affinity, AffinityDerivation, AffinitySentiment
from arrt.persistence.records import VocabularyKind
from arrt.services.errors import ServiceError


@pytest.fixture
def taste(services):
    return services.taste


def an_inferred_row(discovery_store, *, value="Agnes Martin", rationale="they asked for stillness") -> Affinity:
    """An `inferred` judgment as the catalogue holds one: written before conversations stopped being stored.

    Through the store directly, because no caller can write one now.
    """
    now = datetime.now(UTC)
    row = Affinity(
        id=f"affinity-{value}",
        kind=VocabularyKind.ARTIST,
        value=value,
        sentiment=AffinitySentiment.LIKES,
        open_to_more=True,
        derivation=AffinityDerivation.INFERRED,
        created_at=now,
        updated_at=now,
        rationale=rationale,
    )
    discovery_store.add_affinity(row)
    return row


# -- what `set` refuses -------------------------------------------------------


def test_set_refuses_observed_and_names_the_path_that_can_write_it(taste):
    """`observed` is a claim only the review path can make truthfully.

    A row written by a caller claiming the product read the judgment out of
    accept-and-reject behaviour is a fabricated observation — indistinguishable
    afterwards from one the product earned, and with nothing behind it for a
    later rebuild to work from. The refusal has to *name the alternative*,
    because "not allowed" leaves a caller retrying blind.
    """
    with pytest.raises(ServiceError) as refused:
        taste.set_affinity(
            kind="artist",
            value="Kandinsky",
            sentiment="likes",
            open_to_more=True,
            derivation="observed",
            rationale="accepted four of their works",
        )

    assert "observed" in str(refused.value)
    assert "review" in str(refused.value)
    assert "stated" in str(refused.value)


@pytest.mark.parametrize("derivation", sorted(str(member) for member in NEEDS_RATIONALE))
def test_the_two_derivations_that_are_claims_about_the_curator_need_a_rationale(derivation):
    """Required for `inferred` and `observed`, because neither cites anything else.

    Driven through `validated_write` rather than through `set_affinity`, and
    deliberately: `set` refuses `observed` outright, so the rationale rule for
    that derivation is unreachable from it. The rule belongs to the write path —
    which is a function precisely so the review path that will one day assert
    `observed` goes through the same checks — and this is the test that says so.
    """
    with pytest.raises(ServiceError) as refused:
        validated_write(
            kind="artist",
            value="Kandinsky",
            sentiment="likes",
            open_to_more=True,
            derivation=derivation,
        )

    assert "rationale" in str(refused.value)
    # The reason, not just the requirement.
    assert "only evidence" in str(refused.value)


def test_a_stated_judgment_needs_no_rationale(taste):
    """The curator saying a thing is the whole provenance.

    The mirror of the test above, and it is not decoration: a rule applied to all
    three derivations would make the ordinary reaction — a curator pressing "not
    this" beside a picture — impossible to record without inventing an account of
    a judgment they made themselves.
    """
    written = taste.set_affinity(kind="artist", value="Kandinsky", sentiment="declines", open_to_more=False)

    assert written.derivation is AffinityDerivation.STATED
    assert written.rationale is None


def test_an_inferred_judgment_cannot_be_written_even_with_a_rationale(taste):
    """An inference had to cite the stored turn it was read out of, and none are stored.

    With a rationale, so the refusal is this rule's and not the rationale rule's.
    Writing one citing nothing would be a row claiming "the model read this out
    of what they said" with nothing behind it, and the refusal names the
    derivation a caller can write instead.
    """
    with pytest.raises(ServiceError) as refused:
        taste.set_affinity(
            kind="artist",
            value="Kandinsky",
            sentiment="likes",
            open_to_more=True,
            derivation="inferred",
            rationale="they asked for calm grids",
        )

    assert "inferred" in str(refused.value)
    assert "not stored" in str(refused.value)
    assert "stated" in str(refused.value)
    assert taste.list_affinities() == []


def test_openness_is_required_beside_sentiment_rather_than_defaulted(taste):
    """The two-fields rule, defended at the one place a default would creep in.

    The default that reads as safe — do not offer more — is the one that silently
    blacklists an artist the curator asked to keep hearing about, so there is no
    default at all.
    """
    with pytest.raises(ServiceError) as refused:
        taste.set_affinity(kind="artist", value="Kandinsky", sentiment="cool", open_to_more=None)

    assert "open_to_more" in str(refused.value)


def test_an_unknown_kind_is_refused_against_the_shared_vocabulary(taste):
    """`Affinity.kind` is `VocabularyKind` itself, not a matching copy of it.

    A free-text kind would turn a typo into a new dimension of taste, and nothing
    downstream could tell `subject` from `subjcet`.
    """
    with pytest.raises(ServiceError) as refused:
        taste.set_affinity(kind="mood", value="calm", sentiment="likes", open_to_more=True)

    assert "mood" in str(refused.value)
    for kind in VocabularyKind:
        assert str(kind) in str(refused.value)


# -- what `set` does to an existing row ---------------------------------------


def test_set_is_an_upsert_on_the_thing_rather_than_on_an_id(taste):
    """One live judgment per thing, corrected in place.

    `create` would be a lie on the second call and `update` on the first, which
    is why the verb is `set` and why a correction needs no id — the handle is the
    name a model has in a sentence.
    """
    first = taste.set_affinity(kind="artist", value="Kandinsky", sentiment="loves", open_to_more=True)

    second = taste.set_affinity(kind="artist", value="Kandinsky", sentiment="declines", open_to_more=False)

    assert second.id == first.id
    assert second.sentiment is AffinitySentiment.DECLINES
    assert second.open_to_more is False
    assert second.created_at == first.created_at
    assert len(taste.list_affinities()) == 1


def test_the_same_name_under_two_kinds_is_two_judgments(taste):
    """Uniqueness is on the pair, and it has to be: 'Baroque' is a movement and
    could equally be a subject, and one row for both would make correcting one
    silently rewrite the other."""
    taste.set_affinity(kind="movement", value="Baroque", sentiment="loves", open_to_more=True)
    taste.set_affinity(kind="subject", value="Baroque", sentiment="declines", open_to_more=False)

    assert len(taste.list_affinities()) == 2


def test_a_correction_replaces_the_provenance_and_keeps_no_old_rationale(taste, discovery_store):
    """A row must never carry an account that did not produce its judgment.

    Writing the fields given and leaving the rest is the cheap default, and it
    produces provenance that is a lie: the curator's own correction, still
    explained by the model's old reading of them.
    """
    standing = an_inferred_row(discovery_store, value="Kandinsky", rationale="they asked for calm grids")

    corrected = taste.set_affinity(kind="artist", value="Kandinsky", sentiment="declines", open_to_more=False)

    assert corrected.id == standing.id
    assert corrected.derivation is AffinityDerivation.STATED
    assert corrected.rationale is None


# -- reading and forgetting ---------------------------------------------------


def test_the_listing_narrows_by_each_of_the_three_things_worth_narrowing_by(taste, discovery_store):
    taste.set_affinity(kind="artist", value="Kandinsky", sentiment="loves", open_to_more=True)
    taste.set_affinity(kind="movement", value="Bauhaus", sentiment="declines", open_to_more=False)
    an_inferred_row(discovery_store, value="Agnes Martin")

    assert [affinity.value for affinity in taste.list_affinities(kind="artist")] == ["Agnes Martin", "Kandinsky"]
    assert [affinity.value for affinity in taste.list_affinities(sentiment="declines")] == ["Bauhaus"]
    assert [affinity.value for affinity in taste.list_affinities(derivation="inferred")] == ["Agnes Martin"]


def test_forgetting_answers_with_what_was_forgotten(taste):
    """Not recoverable, so the acknowledgement names the thing rather than the id.

    A confirmation reporting a handle the curator never saw cannot be checked
    against what they meant to do.
    """
    written = taste.set_affinity(kind="artist", value="Kandinsky", sentiment="declines", open_to_more=False)

    gone = taste.delete_affinity(written.id)

    assert gone.value == "Kandinsky"
    assert taste.list_affinities() == []


def test_forgetting_something_that_is_not_there_is_refused_by_name(taste):
    with pytest.raises(ServiceError) as refused:
        taste.delete_affinity("no-such-affinity")

    assert "no-such-affinity" in str(refused.value)


# -- the shape the file is allowed to hold ------------------------------------


def test_an_inferred_judgment_already_held_reads_back_with_its_rationale(discovery_store):
    """**The rows no caller can write still read.**

    The write path refuses `inferred` and the *file* must not, because the
    catalogue already holds such rows and they are the curator's history. Written
    through the store directly, which is the only way to express "a row that
    exists but could not have been written now", and read back through the
    service so the refusal cannot be hiding in the read either.
    """
    an_inferred_row(discovery_store, value="Kandinsky", rationale="they asked for calm grids")

    (read,) = TasteService(discovery_store).list_affinities()
    assert read.derivation is AffinityDerivation.INFERRED
    assert read.rationale == "they asked for calm grids"
