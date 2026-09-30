"""The Library's facade: what Programming may ask, and the shape of every answer.

`architecture.md` § Direction, the Library/Programming seam, rule 2: the facade is
written as if the Library were already remote. So these tests hold the answer's
*shape* as well as its content. Every id asked about is answered, the answers are
plain frozen data, and asking twice gives the same answer. Each refusal reason is
reached through the real catalogue, one case per reason, so a reason added later
without a case fails here by name.
"""

import dataclasses
from collections.abc import Callable

import pytest

from curatarr.library.facade import PlayableWork, Unplayable, UnplayableReason
from curatarr.persistence.records import FetchStatus


def _archived(service, ready_work) -> str:
    work = ready_work()
    service.archive_artwork(work.id)
    return work.id


def _re_acquired_since_render(service, ready_work) -> str:
    work = ready_work()
    source = service.list_sources(work.id)[0]
    service.record_original(
        artwork_id=work.id,
        source_id=source.id,
        path=f"raw/{work.id}.tif",
        width=6000,
        height=4000,
        byte_size=90_000_000,
        content_hash="a-later-acquisition",
        fetch_status=FetchStatus.OK,
    )
    return work.id


#: How to make a work the Library refuses for each reason, and a word its
#: sentence must carry. Keyed by the enum, so the parametrisation below is derived
#: from it rather than copied, and a reason with no row here is a failure.
_CASES: dict[UnplayableReason, tuple[Callable[..., str], str]] = {
    UnplayableReason.ARCHIVED: (_archived, "archived"),
    UnplayableReason.NO_ORIGINAL: (lambda service, ready_work: ready_work(original=False).id, "master image"),
    UnplayableReason.NO_MAT_COLOR: (lambda service, ready_work: ready_work(mat=False).id, "mat colour"),
    UnplayableReason.NO_RENDITION: (lambda service, ready_work: ready_work(rendition=False).id, "rendered"),
    UnplayableReason.STALE_RENDITION: (_re_acquired_since_render, "earlier acquisition"),
    UnplayableReason.NOT_IN_CATALOGUE: (lambda service, ready_work: "no-such-work", "No artwork with id"),
}


def test_every_reason_has_a_case():
    assert set(_CASES) == set(UnplayableReason)


@pytest.mark.parametrize("reason", list(UnplayableReason), ids=str)
def test_each_reason_is_the_answer_for_the_state_it_names(library, service, ready_work, reason):
    make, words = _CASES[reason]
    work_id = make(service, ready_work)

    answer = library.playable([work_id])[work_id]

    assert isinstance(answer, Unplayable)
    assert answer.reason is reason
    assert answer.work_id == work_id
    assert words in answer.detail


def test_a_refusal_names_the_work_it_refuses(library, ready_work):
    work = ready_work(title="Chop Suey", original=False)

    assert library.playable([work.id])[work.id].title == "Chop Suey"


def test_an_id_the_catalogue_does_not_hold_has_no_title(library):
    """There is no title to give, and making one up would put a false name on a report."""
    assert library.playable(["no-such-work"])["no-such-work"].title is None


def test_a_ready_work_is_answered_with_what_the_wall_is_told(library, service, ready_work):
    work = ready_work(title="Nighthawks")
    render = next(view.rendition for view in service.list_renditions(work.id))

    answer = library.playable([work.id])[work.id]

    assert isinstance(answer, PlayableWork)
    assert answer.work_id == work.id
    assert answer.title == "Nighthawks"
    assert answer.render_path == render.relative_path
    assert answer.label["title"] == "Nighthawks"
    assert answer.label["date_created"] == "1942"


def test_every_id_asked_about_is_answered_in_the_order_asked(library, ready_work):
    """One dangling reference must not make a whole theme unanswerable."""
    first = ready_work(title="Nighthawks")
    second = ready_work(title="Automat", mat=False)

    answers = library.playable([second.id, "no-such-work", first.id])

    assert list(answers) == [second.id, "no-such-work", first.id]
    assert [type(answer) for answer in answers.values()] == [Unplayable, Unplayable, PlayableWork]


def test_an_id_asked_twice_is_answered_once(library, ready_work):
    work = ready_work()

    assert list(library.playable([work.id, work.id])) == [work.id]


def test_asking_twice_gives_the_same_answer(library, ready_work):
    """Idempotent, which is what lets a remote caller retry."""
    ready = ready_work(title="Nighthawks")
    refused = ready_work(title="Automat", original=False)
    ids = [ready.id, refused.id, "no-such-work"]

    assert library.playable(ids) == library.playable(ids)


def test_an_empty_question_gets_an_empty_answer(library):
    assert library.playable([]) == {}


def test_the_answers_are_plain_frozen_data(library, ready_work):
    """No store record and no live handle crosses the seam.

    Checked field by field against the types a JSON body could carry, because
    this is the shape that has to survive becoming one.
    """
    ready = ready_work()
    refused = ready_work(original=False)

    for answer in library.playable([ready.id, refused.id, "no-such-work"]).values():
        assert dataclasses.is_dataclass(answer)
        with pytest.raises(dataclasses.FrozenInstanceError):
            answer.work_id = "changed"
        for field in dataclasses.fields(answer):
            value = getattr(answer, field.name)
            if field.name == "label":
                assert all(isinstance(key, str) and (text is None or isinstance(text, str)) for key, text in value.items())
                with pytest.raises(TypeError):
                    value["title"] = "changed"
            else:
                assert value is None or isinstance(value, str), f"{type(answer).__name__}.{field.name} is {type(value)}"
