"""The taste as a prompt is told it: one rendering, shared by Ask and discovery's phase 1."""

from datetime import UTC, datetime

import pytest

from arrt.library.services.taste import TASTE_TEXT_TOLD, describe_taste
from arrt.persistence.discovery_records import Affinity, AffinityDerivation, AffinitySentiment
from arrt.persistence.records import VocabularyKind

NOW = datetime(2026, 11, 8, tzinfo=UTC)


def judgment(
    value: str,
    sentiment: AffinitySentiment = AffinitySentiment.LIKES,
    *,
    open_to_more: bool = True,
    kind: VocabularyKind = VocabularyKind.ARTIST,
    derivation: AffinityDerivation = AffinityDerivation.STATED,
    rationale: str | None = None,
) -> Affinity:
    return Affinity(
        id=f"affinity-{value}",
        kind=kind,
        value=value,
        sentiment=sentiment,
        open_to_more=open_to_more,
        derivation=derivation,
        created_at=NOW,
        updated_at=NOW,
        rationale=rationale,
    )


def test_no_taste_is_an_empty_brief_so_a_prompt_can_leave_the_section_out():
    assert describe_taste([]) == ""


@pytest.mark.parametrize("sentiment", list(AffinitySentiment))
@pytest.mark.parametrize(("open_to_more", "said"), [(True, "keep offering more"), (False, "offer no more")])
def test_every_line_says_the_sentiment_and_whether_to_offer_more(sentiment, open_to_more, said):
    """`open_to_more` is spelled out, never left to be read off the sentiment."""
    brief = describe_taste([judgment("Magritte", sentiment, open_to_more=open_to_more)])

    assert brief == f"- {sentiment} artist “Magritte”: {said}"


def test_the_strongest_feelings_come_first():
    brief = describe_taste(
        [
            judgment("Cool one", AffinitySentiment.COOL),
            judgment("Liked one", AffinitySentiment.LIKES),
            judgment("Declined one", AffinitySentiment.DECLINES, open_to_more=False),
            judgment("Loved one", AffinitySentiment.LOVES),
        ]
    )

    named = [line.split("“")[1].split("”")[0] for line in brief.splitlines()]
    assert named == ["Loved one", "Declined one", "Liked one", "Cool one"]


def test_a_judgment_the_curator_did_not_state_says_where_it_came_from():
    brief = describe_taste(
        [
            judgment("Agnes Martin", derivation=AffinityDerivation.INFERRED, rationale="they asked for stillness"),
            judgment("Kandinsky"),
        ]
    )

    assert "- likes artist “Agnes Martin”: keep offering more (inferred: they asked for stillness)" in brief.splitlines()
    assert "- likes artist “Kandinsky”: keep offering more" in brief.splitlines()


def test_a_brief_past_its_limit_says_how_many_it_left_out_and_keeps_the_strongest():
    taste = [judgment(f"Cool {index}", AffinitySentiment.COOL) for index in range(3)] + [
        judgment("Loved", AffinitySentiment.LOVES)
    ]

    lines = describe_taste(taste, limit=2).splitlines()

    assert lines[0].startswith("- loves artist “Loved”")
    assert len(lines) == 3
    assert lines[-1] == "- (2 more judgments are not listed.)"


def test_a_brief_at_its_limit_claims_nothing_left_out():
    lines = describe_taste([judgment("A"), judgment("B")], limit=2).splitlines()

    assert len(lines) == 2
    assert not any("not listed" in line for line in lines)


def test_a_name_or_rationale_past_its_length_is_cut_and_says_so():
    """Both are stored unbounded and resent with every prompt, so the brief bounds each line, not only the count."""
    long = "Klimt " * 100
    brief = describe_taste([judgment(long, derivation=AffinityDerivation.INFERRED, rationale="gold\n" * 100)])

    named = brief.split("“")[1].split("”")[0]
    account = brief.split("(inferred: ")[1].rstrip(")")
    assert len(named) == len(account) == TASTE_TEXT_TOLD
    assert named.endswith("…")
    assert account.endswith("…")
    assert "\n" not in brief, "a judgment is told on one line"


def test_a_name_at_its_length_is_told_whole():
    exact = "x" * TASTE_TEXT_TOLD

    assert f"“{exact}”" in describe_taste([judgment(exact)])
