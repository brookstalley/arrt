"""The Library's facade: what Programming may ask, and the shape of every answer.

`architecture.md` § Direction, the Library/Programming seam, rule 2: the facade is
written as if the Library were already remote. So these tests hold the answer's
*shape* as well as its content. Every id asked about is answered, the answers are
plain frozen data, and asking twice gives the same answer. Each refusal reason is
reached through the real catalogue, one case per reason, so a reason added later
without a case fails here by name.
"""

import dataclasses
import hashlib
import logging
from collections.abc import Callable

import pytest
from PIL import Image

from arrt.library.facade import PlayableWork, Unplayable, UnplayableReason
from arrt.library.services.discovery import ChosenWork
from arrt.persistence.discovery_records import InitiatedBy, Verdict
from arrt.persistence.records import FetchStatus, RenditionKind


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
    UnplayableReason.NO_RENDITION: (lambda service, ready_work: ready_work(master=False).id, "presentation master"),
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
    master = _master_of(service, work.id)

    answer = library.playable([work.id])[work.id]

    assert isinstance(answer, PlayableWork)
    assert answer.work_id == work.id
    assert answer.title == "Nighthawks"
    assert answer.master.media.sha256 == master.content_sha256
    assert (answer.master.width, answer.master.height) == (400, 300), "the file's own size, not the cap"
    assert answer.mat_color == "#27285b"
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
    answers = library.playable([ready.id, refused.id, "no-such-work"])
    assert answers[ready.id].master is not None, "the ready work has no master, so the nested shape goes unchecked"

    for answer in answers.values():
        _assert_plain(answer, type(answer).__name__)


def _assert_plain(value, where: str) -> None:
    """A frozen dataclass of strings, whole numbers, None, read-only text mappings and more of the same."""
    assert dataclasses.is_dataclass(value), where
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(value, dataclasses.fields(value)[0].name, "changed")
    for field in dataclasses.fields(value):
        inner = getattr(value, field.name)
        here = f"{where}.{field.name}"
        if field.name == "label":
            assert all(isinstance(key, str) and (text is None or isinstance(text, str)) for key, text in inner.items())
            with pytest.raises(TypeError):
                inner["title"] = "changed"
        elif dataclasses.is_dataclass(inner):
            _assert_plain(inner, here)
        else:
            assert inner is None or (isinstance(inner, str | int) and not isinstance(inner, bool)), f"{here} is {type(inner)}"


# -- the master's content hash, as stored -----------------------------------------------


def _master_of(service, work_id):
    return next(
        view.rendition for view in service.list_renditions(work_id) if view.rendition.kind is RenditionKind.PRESENTATION_MASTER
    )


def _record_master(service, work_id, path):
    service.record_rendition(
        artwork_id=work_id, kind=RenditionKind.PRESENTATION_MASTER, target_width=7680, target_height=7680, path=path
    )
    return _master_of(service, work_id)


def test_recording_a_master_whose_file_exists_stores_its_hash_and_a_remake_stores_the_new_one(service, ready_work, wall_settings):
    work = ready_work(master=False)
    path = f"presentation/{work.id}.jpg"
    target = wall_settings.art_root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"first master")

    first = _record_master(service, work.id, path)
    assert (first.content_sha256, first.byte_size) == (hashlib.sha256(b"first master").hexdigest(), 12)

    target.write_bytes(b"a second, longer master")
    second = _record_master(service, work.id, path)
    assert (second.content_sha256, second.byte_size) == (hashlib.sha256(b"a second, longer master").hexdigest(), 23)


def test_a_master_recorded_before_its_file_is_hashed_and_stored_on_first_need(
    library, service, ready_work, wall_settings, decodable_jpeg
):
    """Stored, so the next ask does not re-read a few megabytes to learn the same thing."""
    work = ready_work(master=False)
    path = f"presentation/{work.id}.jpg"
    assert _record_master(service, work.id, path).content_sha256 is None, "the master had a file after all"
    decodable_jpeg(wall_settings.art_root / path, width=400, height=300)

    answer = library.playable([work.id])[work.id]

    stored = _master_of(service, work.id)
    data = (wall_settings.art_root / path).read_bytes()
    assert stored.content_sha256 == hashlib.sha256(data).hexdigest()
    assert stored.byte_size == len(data)
    assert answer.master.media.sha256 == stored.content_sha256


def test_a_master_that_cannot_be_read_is_recorded_without_a_hash_and_says_where(service, ready_work, wall_settings, caplog):
    """Unreadable, not missing: a directory stands where the file should be, which fails the same way on every host."""
    work = ready_work(master=False)
    path = f"presentation/{work.id}.jpg"
    (wall_settings.art_root / path).mkdir(parents=True)

    with caplog.at_level(logging.WARNING, logger="arrt.library.services.catalogue"):
        stored = _record_master(service, work.id, path)

    assert (stored.content_sha256, stored.byte_size) == (None, None)
    assert any(path in record.getMessage() for record in caplog.records)


def test_a_hashed_master_that_becomes_unreadable_is_not_served(service, ready_work, wall_settings, caplog):
    """`/media` answers 404 for it rather than 500: the Player skips a work, it does not decide the server is down."""
    work = ready_work(master=False)
    path = f"presentation/{work.id}.jpg"
    target = wall_settings.art_root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"a master")
    sha = _record_master(service, work.id, path).content_sha256
    assert service.read_media(sha) is not None, "the master was never servable, so this checks nothing"
    target.unlink()
    target.mkdir()

    with caplog.at_level(logging.WARNING, logger="arrt.library.services.catalogue"):
        assert service.read_media(sha) is None

    assert any(path in record.getMessage() for record in caplog.records)


# -- where an accepted work was sent ---------------------------------------------


def _accepted_from_a_get(discovery, add_image, title: str, *, destination: str | None) -> str:
    """Accept the one work a Get named, and return the artwork it became."""
    run = discovery.start_get_run(
        works=[ChosenWork(qid=f"Q{abs(hash(title)) % 10_000}", title=title)],
        initiated_by=InitiatedBy.MCP_CLIENT,
        destination_theme_id=destination,
    )
    (work,) = discovery.list_candidate_works(run.id)
    add_image(work)
    return discovery.set_verdict(work.id, Verdict.ACCEPTED).work.artwork_id


def test_destinations_answer_every_id_with_the_theme_its_get_named(library, discovery, add_image, propose, seeded_service):
    """Joined work → candidate → run, per work: two Gets naming two themes keep them apart.

    A work from an Ask, one added by hand, and one the catalogue does not hold
    all answer None, which Programming reads as the default theme.
    """
    to_winter = _accepted_from_a_get(discovery, add_image, "The Elephants", destination="theme-winter")
    to_spring = _accepted_from_a_get(discovery, add_image, "Swans Reflecting Elephants", destination="theme-spring")
    to_default = _accepted_from_a_get(discovery, add_image, "Sleep", destination=None)
    asked = propose("The Burning Giraffe")
    add_image(asked)
    from_an_ask = discovery.set_verdict(asked.id, Verdict.ACCEPTED).work.artwork_id
    by_hand = seeded_service.list_artworks().entries[0].artwork.id

    answer = library.destinations([to_winter, to_spring, to_default, from_an_ask, by_hand, "no-such-work", to_winter])

    assert answer == {
        to_winter: "theme-winter",
        to_spring: "theme-spring",
        to_default: None,
        from_an_ask: None,
        by_hand: None,
        "no-such-work": None,
    }
    assert list(answer) == [to_winter, to_spring, to_default, from_an_ask, by_hand, "no-such-work"], "in the order asked"
    assert library.destinations([to_winter, to_default]) == {to_winter: "theme-winter", to_default: None}, "and again"


def test_a_master_that_reads_but_cannot_be_served_is_refused_by_name(library, service, ready_work, wall_settings):
    """A master at a type the media route will not serve (a TIFF here) has a size and no media.

    Preparation only writes JPEG masters, but a row written any other way must
    be refused in a curator's words, not reach the feed's build and raise there.
    """
    work = ready_work(master=False)
    path = f"presentation/{work.id}.tif"
    (wall_settings.art_root / path).parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (400, 300)).save(wall_settings.art_root / path, format="TIFF")
    _record_master(service, work.id, path)

    answer = library.playable([work.id])[work.id]

    assert isinstance(answer, Unplayable)
    assert answer.reason is UnplayableReason.NO_RENDITION
    assert "cannot be read" in answer.detail
