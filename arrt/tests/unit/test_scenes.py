"""Scenes and staging in each wall's feed (`player-contract.md` § Scenes, § Staging).

A scene is a work per wall, applied together over each wall's schedule; while
it is a draft, each pin stages its work on its wall. The server writes both
keys into a wall's private feed from the store at every write, through the one
writer (`DisplayService._publish_feed`), so the tests below drive every path
that writes a feed and assert the control layer survives it. Every feed any
test here publishes is also checked against the contract as it is built
(`feed_guard.py`, wrapped round every test by `conftest.py`).
"""

import ast
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from feed_guard import problems

from arrt.persistence.file import open_catalogue_file
from arrt.persistence.records import MatMethod, RenditionKind, SceneLifetime, SceneStatus
from arrt.persistence.sqlite import SqliteCatalogue
from arrt.programming import display as display_module
from arrt.programming.display import PREVIEW_MINUTES
from arrt.programming.manifest.v2 import read_published
from arrt.services.errors import ServiceError

#: Long enough that no test here crosses a slot boundary while it runs.
HOUR = 3600


@pytest.fixture
def mastered(services, ready_work, wall_settings, decodable_jpeg):
    """A work ready for the wall, with a presentation master on disk."""

    def _work(title):
        work = ready_work(title, master=False)
        path = f"masters/{work.id}.jpg"
        decodable_jpeg(wall_settings.art_root / path, width=4000, height=3000)
        services.catalogue.record_rendition(
            artwork_id=work.id, kind=RenditionKind.PRESENTATION_MASTER, target_width=7680, target_height=7680, path=path
        )
        return work

    return _work


@pytest.fixture
def feed(wall_settings):
    def _feed(wall_id):
        return read_published(wall_settings.manifest_v2_path(wall_id))

    return _feed


@pytest.fixture
def document(wall_settings):
    def _document(wall_id):
        return json.loads(wall_settings.manifest_v2_path(wall_id).read_text(encoding="utf-8"))

    return _document


@pytest.fixture
def two_walls(display, mastered, wall_id):
    """The hall and the study, each hanging a theme of its own, in order, an hour a work."""
    study = display.add_wall(name="Study").id
    for wall, names in ((wall_id, ("H1", "H2", "H3")), (study, ("S1", "S2", "S3"))):
        theme = display.add_theme(name=f"Theme of {names[0]}")
        for position, work in enumerate(mastered(name) for name in names):
            display.add_to_theme(theme_id=theme.id, artwork_id=work.id, position=position)
        display.set_playback(wall, rotation_interval_seconds=HOUR, shuffle=False)
        display.activate_theme(theme.id, wall_id=wall)
    return wall_id, study


def _now():
    return datetime.now(UTC)


# -- a draft stages ---------------------------------------------------------------------


def test_a_pin_stages_the_work_on_its_wall_and_no_other(display, mastered, two_walls, feed, document):
    hall, study = two_walls
    dali = mastered("Dalí")
    before = feed(hall)
    scene = display.draft_scene().scene

    display.pin_scene(scene.id, hall, dali.id)

    assert document(hall)["staging"] == [dali.id]
    assert dali.id in document(hall)["works"]
    assert "scene" not in document(hall)
    assert "staging" not in document(study)
    assert dali.id not in document(study)["works"]
    # Staging shows nothing: the schedule is republished exactly as it stood.
    assert feed(hall).slots == before.slots
    # Nor is a staged work part of the wall's cycle as read back.
    assert dali.id not in feed(hall).works


def test_a_second_pick_for_a_wall_replaces_the_first(display, mastered, two_walls, document):
    hall, _ = two_walls
    first, second = mastered("Dalí"), mastered("Magritte")
    scene = display.draft_scene().scene
    display.pin_scene(scene.id, hall, first.id)

    display.pin_scene(scene.id, hall, second.id)

    assert document(hall)["staging"] == [second.id]
    assert first.id not in document(hall)["works"]


def test_unpinning_stops_staging_and_discarding_forgets_the_draft(display, mastered, two_walls, document):
    hall, study = two_walls
    scene = display.draft_scene().scene
    display.pin_scene(scene.id, hall, mastered("Dalí").id)
    display.pin_scene(scene.id, study, mastered("Magritte").id)

    display.unpin_scene(scene.id, hall)
    assert "staging" not in document(hall)
    assert "staging" in document(study)

    display.discard_scene(scene.id)
    assert "staging" not in document(study)
    assert display.scene_draft() is None


def test_drafting_again_returns_the_draft_being_assembled(display):
    first = display.draft_scene().scene

    assert display.draft_scene().scene.id == first.id


def test_a_pin_the_library_refuses_is_refused_as_show_now_refuses_and_the_draft_is_unchanged(
    display, mastered, ready_work, two_walls, document
):
    hall, study = two_walls
    plain = ready_work("Plain", master=False)
    scene = display.draft_scene().scene
    display.pin_scene(scene.id, study, mastered("Dalí").id)
    with pytest.raises(ServiceError) as shown:
        display.show_work_now(hall, plain.id)

    with pytest.raises(ServiceError) as pinned:
        display.pin_scene(scene.id, hall, plain.id)

    assert str(pinned.value) == str(shown.value)
    assert [pin.wall_id for pin in display.get_scene(scene.id).pins] == [study]
    assert "staging" not in document(hall)


def test_a_pin_of_a_work_kept_off_every_wall_is_refused_and_the_draft_is_unchanged(display, mastered, two_walls):
    hall, _ = two_walls
    dali = mastered("Dalí")
    display.exclude_work(dali.id)
    scene = display.draft_scene().scene

    with pytest.raises(ServiceError, match="kept off every wall"):
        display.pin_scene(scene.id, hall, dali.id)

    assert display.get_scene(scene.id).pins == ()


def test_a_pin_to_a_wall_with_no_feed_is_refused_by_name(display, mastered):
    bare = display.add_wall(name="Landing").id
    scene = display.draft_scene().scene

    with pytest.raises(ServiceError, match="'Landing'"):
        display.pin_scene(scene.id, bare, mastered("Dalí").id)

    assert display.get_scene(scene.id).pins == ()


# -- apply, release, expiry -------------------------------------------------------------


@pytest.fixture
def staged(display, mastered, two_walls):
    """A draft pinning a work to each wall."""
    hall, study = two_walls
    scene = display.draft_scene().scene
    works = {hall: mastered("Dalí"), study: mastered("Magritte")}
    for wall, work in works.items():
        display.pin_scene(scene.id, wall, work.id)
    return scene, works


def test_apply_puts_the_same_scene_on_every_pinned_wall_and_clears_staging(display, staged, document):
    scene, works = staged
    started = _now()

    applied = display.apply_scene(scene.id, lifetime="preview", minutes=5)

    for wall, work in works.items():
        published = document(wall)
        assert published["scene"]["id"] == scene.id
        assert published["scene"]["work_id"] == work.id
        assert "staging" not in published
        assert published["scene"]["from"] < published["scene"]["until"]
        assert work.id in published["works"]
    assert applied.scene.until - applied.scene.starts_at == timedelta(minutes=5)
    assert applied.scene.starts_at >= started
    assert display.live_scene().scene.id == scene.id
    assert display.scene_draft() is None


def test_a_preview_with_no_length_lasts_the_default(display, staged):
    scene, _ = staged

    applied = display.apply_scene(scene.id, lifetime=SceneLifetime.PREVIEW)

    assert applied.scene.until - applied.scene.starts_at == timedelta(minutes=PREVIEW_MINUTES)


def test_a_hold_has_no_end(display, staged, document):
    scene, works = staged

    display.apply_scene(scene.id, lifetime="hold")

    for wall in works:
        assert document(wall)["scene"]["until"] is None


@pytest.mark.parametrize(
    ("lifetime", "minutes", "match"),
    [("hold", 5, "takes no length"), ("preview", 0, "at least a minute"), ("keep", None, "lifetime")],
)
def test_a_lifetime_that_cannot_be_applied_is_refused_and_the_draft_stays(display, staged, document, lifetime, minutes, match):
    scene, works = staged

    with pytest.raises(ServiceError, match=match):
        display.apply_scene(scene.id, lifetime=lifetime, minutes=minutes)

    assert display.get_scene(scene.id).scene.status is SceneStatus.DRAFT
    assert all("scene" not in document(wall) for wall in works)


def test_an_empty_draft_cannot_be_applied(display):
    scene = display.draft_scene().scene

    with pytest.raises(ServiceError, match="no walls in it"):
        display.apply_scene(scene.id, lifetime="hold")


def test_a_pin_whose_work_was_archived_since_refuses_apply_naming_the_wall(services, display, staged, document):
    scene, works = staged
    hall = next(iter(works))
    services.catalogue.archive_artwork(works[hall].id)

    with pytest.raises(ServiceError, match=rf"^{display.get_wall(hall).name}: .*archived"):
        display.apply_scene(scene.id, lifetime="hold")

    assert display.live_scene() is None
    assert all("scene" not in document(wall) for wall in works)


def test_release_takes_the_scene_off_and_keeps_the_slot_on_the_wall(display, staged, feed, document):
    scene, works = staged
    display.apply_scene(scene.id, lifetime="hold")
    before = {wall: feed(wall).slots for wall in works}

    display.release_scene(scene.id)

    for wall in works:
        assert "scene" not in document(wall)
        assert feed(wall).slots == before[wall]
        assert works[wall].id not in document(wall)["works"]
    assert display.live_scene() is None
    assert display.get_scene(scene.id).scene.status is SceneStatus.ENDED


def test_releasing_what_is_not_live_is_refused(display, staged):
    scene, _ = staged

    with pytest.raises(ServiceError, match="nothing to release"):
        display.release_scene(scene.id)


def _expire(store, scene_id):
    """Move an applied scene back in time so its preview has run out."""
    scene = store.get_scene(scene_id)
    shift = scene.until - _now() + timedelta(seconds=1)
    store.update_scene(type(scene)(**{**_fields(scene), "starts_at": scene.starts_at - shift, "until": scene.until - shift}))


def _fields(scene):
    return {name: getattr(scene, name) for name in scene.__slots__}


def test_an_expired_preview_is_not_live_and_the_next_feed_carries_no_scene(store, display, staged, feed, document):
    scene, works = staged
    display.apply_scene(scene.id, lifetime="preview", minutes=5)
    _expire(store, scene.id)
    hall = next(iter(works))
    before = feed(hall).slots

    assert display.live_scene() is None
    assert display.get_scene(scene.id).scene.status is SceneStatus.ENDED

    display.set_mat_mode(hall, "full")

    assert "scene" not in document(hall)
    assert feed(hall).slots == before


def test_a_heartbeat_writes_down_that_a_preview_ran_out(store, display, staged, wall_id, caplog):
    scene, _ = staged
    display.apply_scene(scene.id, lifetime="preview", minutes=5)
    _expire(store, scene.id)
    until = store.get_scene(scene.id).until

    with caplog.at_level("INFO", logger=display_module.__name__):
        display.record_heartbeat(wall_id, {"schema": {"major": 1, "minor": 1}, "reported_at": _now().isoformat()})

    stored = store.get_scene(scene.id)
    assert (stored.status, stored.ended_at) == (SceneStatus.ENDED, until)
    (expired,) = [record for record in caplog.records if getattr(record, "event", None) == "scene.expired"]
    assert sorted(expired.wall_ids) == sorted(pin.wall_id for pin in display.get_scene(scene.id).pins)


def test_applying_while_another_scene_is_live_ends_it(display, mastered, staged, document):
    first, works = staged
    display.apply_scene(first.id, lifetime="hold")
    hall, study = works
    second = display.draft_scene().scene
    picasso = mastered("Picasso")
    display.pin_scene(second.id, hall, picasso.id)

    display.apply_scene(second.id, lifetime="hold")

    assert display.get_scene(first.id).scene.status is SceneStatus.ENDED
    assert display.live_scene().scene.id == second.id
    assert document(hall)["scene"]["id"] == second.id
    assert document(hall)["scene"]["work_id"] == picasso.id
    # The study was only in the first scene, so its next feed carries none.
    assert "scene" not in document(study)


# -- every writer carries the control layer --------------------------------------------


def _callers_of(name: str) -> set[str]:
    """The functions in `programming/display.py` that call `self.<name>`, derived from its source."""
    tree = ast.parse(Path(display_module.__file__).read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for call in ast.walk(node):
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == name:
                    found.add(node.name)
    return found


def test_one_function_writes_a_feed():
    """The control layer is added in `_publish_feed`; a second writer would be a path that could drop a live scene."""
    tree = ast.parse(Path(display_module.__file__).read_text(encoding="utf-8"))
    spellers = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        for call in ast.walk(node)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "as_v2_document"
    }
    assert spellers == {"_publish_feed"}


def _sync(display, hall, study, mastered, wall_settings, services):
    display.activate_theme(display.hanging_on(hall).id, wall_id=hall)


def _step(display, hall, study, mastered, wall_settings, services):
    display.step_display(hall)


def _show_now(display, hall, study, mastered, wall_settings, services):
    display.show_work_now(hall, mastered("Guest").id)


def _pace(display, hall, study, mastered, wall_settings, services):
    display.set_playback(hall, rotation_interval_seconds=HOUR * 2)


def _roll(display, hall, study, mastered, wall_settings, services):
    path = wall_settings.manifest_v2_path(hall)
    published = json.loads(path.read_text(encoding="utf-8"))
    for span in [published["schedule"]["horizon"], *published["schedule"]["slots"]]:
        for key in ("from", "until"):
            span[key] = (datetime.fromisoformat(span[key]) - timedelta(days=1, hours=1)).isoformat()
    path.write_text(json.dumps(published), encoding="utf-8")
    display.record_heartbeat(hall, {"schema": {"major": 1, "minor": 1}, "reported_at": _now().isoformat()})


def _withdraw(display, hall, study, mastered, wall_settings, services):
    services.catalogue.archive_artwork(display.theme_work_ids(display.hanging_on(hall).id)[-1])


def _beside(display, hall, study, mastered, wall_settings, services):
    """The study hangs a theme sharing a work with the hall, so the hall is rebuilt beside it."""
    shared = display.theme_work_ids(display.hanging_on(hall).id)[0]
    theme = display.add_theme(name="Shared")
    display.add_to_theme(theme_id=theme.id, artwork_id=shared)
    display.activate_theme(theme.id, wall_id=study)


def _mat_mode(display, hall, study, mastered, wall_settings, services):
    display.set_mat_mode(hall, "full")


def _mat_colour(display, hall, study, mastered, wall_settings, services):
    work = display.theme_work_ids(display.hanging_on(hall).id)[0]
    services.catalogue.record_mat_color(artwork_id=work, hex_rgb="#3b2f2a", method=MatMethod.MANUAL)


#: Each function that hands a schedule to `_publish_feed`, with the acts that reach it.
WRITERS = {
    "_write_v2": [_sync, _step, _show_now, _pace, _roll, _withdraw, _beside],
    "_patch_v2_works": [_mat_mode, _mat_colour],
}


def test_the_writers_driven_below_are_every_function_that_publishes_a_feed():
    assert _callers_of("_publish_feed") == set(WRITERS)


@pytest.mark.parametrize("act", [act for acts in WRITERS.values() for act in acts], ids=lambda act: act.__name__.strip("_"))
def test_every_publish_path_carries_the_live_scene_and_the_drafts_staging(
    display, mastered, two_walls, wall_settings, services, document, act
):
    hall, study = two_walls
    live = display.draft_scene().scene
    shown = mastered("Dalí")
    display.pin_scene(live.id, hall, shown.id)
    display.apply_scene(live.id, lifetime="hold")
    draft = display.draft_scene().scene
    staged = mastered("Magritte")
    display.pin_scene(draft.id, hall, staged.id)
    before = document(hall)["generated_at"]

    act(display, hall, study, mastered, wall_settings, services)

    published = document(hall)
    assert published["generated_at"] != before, "the act did not write the hall's feed"
    assert published["scene"]["id"] == live.id
    assert published["scene"]["work_id"] == shown.id
    assert published["staging"] == [staged.id]
    assert {shown.id, staged.id} <= set(published["works"])
    assert problems(published) == []


# -- a pinned work the walls can no longer show ---------------------------------------


def test_a_live_scenes_work_kept_off_every_wall_leaves_the_feed(display, staged, document):
    scene, works = staged
    display.apply_scene(scene.id, lifetime="hold")
    hall = next(iter(works))

    display.exclude_work(works[hall].id)

    assert "scene" not in document(hall)
    assert works[hall].id not in document(hall)["works"]


def test_a_live_scenes_work_archived_leaves_the_feed(services, display, staged, document):
    scene, works = staged
    display.apply_scene(scene.id, lifetime="hold")
    hall = next(iter(works))

    services.catalogue.archive_artwork(works[hall].id)

    assert "scene" not in document(hall)


def test_a_scenes_work_with_a_new_mat_colour_is_republished_with_it(services, display, staged, document):
    scene, works = staged
    display.apply_scene(scene.id, lifetime="hold")
    hall = next(iter(works))

    services.catalogue.record_mat_color(artwork_id=works[hall].id, hex_rgb="#3b2f2a", method=MatMethod.MANUAL)

    assert document(hall)["works"][works[hall].id]["mat_color"] == "#3b2f2a"


def test_a_wall_showing_its_scenes_work_keeps_a_showing_of_it(display, staged):
    scene, works = staged
    display.apply_scene(scene.id, lifetime="hold")
    hall = next(iter(works))
    beat = {
        "schema": {"major": 1, "minor": 2},
        "reported_at": _now().isoformat(),
        "current_work_id": works[hall].id,
        "display_state": {"state": "showing_art", "work_id": works[hall].id, "since": _now().isoformat()},
        "scene_id": scene.id,
    }

    display.record_heartbeat(hall, beat)

    assert display.last_showing(hall).work_id == works[hall].id


# -- the store -------------------------------------------------------------------------


def test_a_catalogue_file_from_before_scenes_gains_them(tmp_path):
    path = tmp_path / "catalogue.sqlite"
    open_catalogue_file(path, wall_name="Hall").close()
    connection = sqlite3.connect(path)
    try:
        connection.execute("DROP TABLE scene_pins")
        connection.execute("DROP TABLE scenes")
        connection.commit()
    finally:
        connection.close()

    store = SqliteCatalogue(open_catalogue_file(path))
    try:
        assert store.list_scenes() == []
        assert store.list_pins("anything") == []
    finally:
        store.close()


def test_two_live_scenes_on_one_wall_publish_the_one_applied_last_and_say_so(store, display, staged, mastered, document, caplog):
    """Apply ends every other live scene, so only a store written by something else holds two; the wall still reads one."""
    first, works = staged
    display.apply_scene(first.id, lifetime="hold")
    hall = next(iter(works))
    second = display.draft_scene().scene
    later = mastered("Picasso")
    display.pin_scene(second.id, hall, later.id)
    earlier = store.get_scene(first.id)
    store.update_scene(
        type(earlier)(
            **{
                **_fields(earlier),
                "id": second.id,
                "created_at": store.get_scene(second.id).created_at,
                "starts_at": earlier.starts_at + timedelta(seconds=1),
            }
        )
    )

    with caplog.at_level("WARNING", logger=display_module.__name__):
        display.set_mat_mode(hall, "full")

    assert document(hall)["scene"]["id"] == second.id
    assert document(hall)["scene"]["work_id"] == later.id
    assert display.live_scene().scene.id == second.id
    assert any("2 live scenes" in record.getMessage() for record in caplog.records)


# -- the feed's own refusals ------------------------------------------------------------


def _feed_with(**control):
    from arrt.programming.manifest.v2 import Feed
    from arrt.programming.schedule import Schedule

    now = _now()
    return Feed("p", "Playlist", Schedule(now, now + timedelta(days=3), (), ()), works={"w": {}}, **control)


def test_a_feed_refuses_a_scene_that_ends_before_it_starts():
    from arrt.programming.manifest.v2 import SceneEntry

    at = _now()
    with pytest.raises(ValueError, match="ends before it starts"):
        _feed_with(scene=SceneEntry(id="s", work_id="w", starts_at=at, until=at))


@pytest.mark.parametrize("control", ["scene", "staging"])
def test_a_feed_refuses_a_scene_or_staged_work_it_does_not_carry(control):
    from arrt.programming.manifest.v2 import SceneEntry

    at = _now()
    named = {"scene": SceneEntry(id="s", work_id="absent", starts_at=at, until=None), "staging": ("absent",)}
    with pytest.raises(ValueError, match="does not carry: absent"):
        _feed_with(**{control: named[control]})


# -- the journal --------------------------------------------------------------------------


def _events(caplog, name):
    return [record for record in caplog.records if getattr(record, "event", None) == name]


def test_each_act_on_a_scene_is_said_with_its_walls(display, mastered, two_walls, caplog):
    hall, study = two_walls
    with caplog.at_level("INFO", logger=display_module.__name__):
        first = display.draft_scene().scene
        display.pin_scene(first.id, hall, mastered("Dalí").id)
        display.pin_scene(first.id, study, mastered("Magritte").id)
        display.unpin_scene(first.id, study)
        display.apply_scene(first.id, lifetime="hold")
        second = display.draft_scene().scene
        display.pin_scene(second.id, study, mastered("Picasso").id)
        display.apply_scene(second.id, lifetime="hold")
        display.release_scene(second.id)
        third = display.draft_scene().scene
        display.pin_scene(third.id, hall, mastered("Ernst").id)
        display.discard_scene(third.id)

    def said(name):
        return [(record.scene_id, record.wall_ids) for record in _events(caplog, name)]

    assert said("scene.staged") == [(first.id, [hall]), (first.id, [study]), (second.id, [study]), (third.id, [hall])]
    assert said("scene.unstaged") == [(first.id, [study])]
    assert said("scene.applied") == [(first.id, [hall]), (second.id, [study])]
    # The first ended when the second was applied, and the second when released.
    assert sorted(said("scene.released")) == sorted([(first.id, [hall]), (second.id, [study])])
    assert said("scene.discarded") == [(third.id, [hall])]


@pytest.mark.parametrize("act", ["pin", "unpin", "discard", "apply"])
def test_a_scene_no_longer_being_assembled_cannot_be_changed(display, staged, mastered, act):
    scene, works = staged
    display.apply_scene(scene.id, lifetime="hold")
    hall = next(iter(works))
    acts = {
        "pin": lambda: display.pin_scene(scene.id, hall, mastered("Late").id),
        "unpin": lambda: display.unpin_scene(scene.id, hall),
        "discard": lambda: display.discard_scene(scene.id),
        "apply": lambda: display.apply_scene(scene.id, lifetime="hold"),
    }

    with pytest.raises(ServiceError, match="is live, not being assembled"):
        acts[act]()

    assert display.live_scene().scene.id == scene.id
    assert {pin.wall_id: pin.work_id for pin in display.get_scene(scene.id).pins} == {
        wall: work.id for wall, work in works.items()
    }


def test_a_scenes_work_leaving_its_theme_stays_on_the_wall_and_is_not_said_to_leave(display, two_walls, document, caplog):
    hall, _ = two_walls
    theme = display.hanging_on(hall)
    pinned = display.theme_work_ids(theme.id)[-1]
    scene = display.draft_scene().scene
    display.pin_scene(scene.id, hall, pinned)
    display.apply_scene(scene.id, lifetime="hold")

    with caplog.at_level("INFO", logger=display_module.__name__):
        display.leave_theme(pinned, wall_id=hall)

    assert document(hall)["scene"]["work_id"] == pinned
    assert not [record.getMessage() for record in caplog.records if "off the feed" in record.getMessage()]


def test_only_the_draft_being_assembled_stages(store, display, mastered, two_walls, document):
    """The store would hold two drafts; the builder shows the newest, so only it stages."""
    from arrt.persistence.records import Scene, ScenePin

    hall, _ = two_walls
    current = display.draft_scene().scene
    display.pin_scene(current.id, hall, mastered("Shown").id)
    older = Scene(id="older", status=SceneStatus.DRAFT, created_at=current.created_at - timedelta(hours=1))
    store.add_scene(older)
    store.set_pin(ScenePin(scene_id="older", wall_id=hall, work_id=mastered("Hidden").id))

    display.set_mat_mode(hall, "full")

    assert display.scene_draft().scene.id == current.id
    assert document(hall)["staging"] == [display.get_scene(current.id).pins[0].work_id]


def test_a_failure_writing_a_previews_end_does_not_cost_the_wall_its_roll(
    store, display, staged, wall_settings, monkeypatch, caplog
):
    scene, works = staged
    hall = next(iter(works))
    display.apply_scene(scene.id, lifetime="preview", minutes=5)
    _expire(store, scene.id)
    path = wall_settings.manifest_v2_path(hall)
    published = json.loads(path.read_text(encoding="utf-8"))
    for span in [published["schedule"]["horizon"], *published["schedule"]["slots"]]:
        for key in ("from", "until"):
            span[key] = (datetime.fromisoformat(span[key]) - timedelta(days=1, hours=1)).isoformat()
    path.write_text(json.dumps(published), encoding="utf-8")

    def refuse(*_args, **_kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(store, "update_scene", refuse)
    with caplog.at_level("ERROR", logger=display_module.__name__):
        display.record_heartbeat(hall, {"schema": {"major": 1, "minor": 1}, "reported_at": _now().isoformat()})

    assert read_published(path).horizon_until - _now() > timedelta(days=2, hours=23)
    assert _events(caplog, "scene.not_settled")


# -- History ----------------------------------------------------------------------------


def _history(store, kind):
    from arrt.persistence.records import EventKind

    page = store.list_events(kinds=[EventKind(kind)], limit=50, offset=0)
    return {(event.wall_id, event.work_id): dict(event.detail or {}) for event in page.events}


def test_history_says_a_scene_was_applied_on_each_wall_with_its_work(store, display, staged):
    scene, works = staged

    display.apply_scene(scene.id, lifetime="preview", minutes=5)

    lines = _history(store, "scene.applied")
    assert set(lines) == {(wall, work.id) for wall, work in works.items()}
    for (wall, _), detail in lines.items():
        assert detail["scene_id"] == scene.id
        assert detail["lifetime"] == "preview"
        assert detail["until"] is not None
        assert detail["wall_name"] == display.get_wall(wall).name
    assert {detail["title"] for detail in lines.values()} == {"Dalí", "Magritte"}
    assert _history(store, "scene.ended") == {}


@pytest.mark.parametrize("how", ["released", "replaced", "ran_out"])
def test_history_says_how_a_scene_ended_on_each_wall(store, display, staged, mastered, wall_id, how):
    scene, works = staged
    display.apply_scene(scene.id, lifetime="preview", minutes=5)
    if how == "released":
        display.release_scene(scene.id)
    elif how == "replaced":
        other = display.draft_scene().scene
        display.pin_scene(other.id, next(iter(works)), mastered("Picasso").id)
        display.apply_scene(other.id, lifetime="hold")
    else:
        _expire(store, scene.id)
        display.record_heartbeat(wall_id, {"schema": {"major": 1, "minor": 1}, "reported_at": _now().isoformat()})

    lines = _history(store, "scene.ended")
    assert set(lines) == {(wall, work.id) for wall, work in works.items()}
    assert {(detail["scene_id"], detail["how"]) for detail in lines.values()} == {(scene.id, how)}


def test_nothing_reaches_history_for_a_draft(store, display, staged):
    scene, _ = staged

    display.discard_scene(scene.id)

    assert _history(store, "scene.applied") == {} == _history(store, "scene.ended")


# -- which walls reached it -------------------------------------------------------------


def _beat(scene_id, state="showing_art", work_id=None):
    return {
        "schema": {"major": 1, "minor": 3},
        "reported_at": _now().isoformat(),
        "current_work_id": work_id,
        "scene_id": scene_id,
        "display_state": {"state": state, "work_id": work_id if state == "showing_art" else None, "since": _now().isoformat()},
    }


def test_a_wall_has_reached_a_scene_when_its_heartbeat_names_it(services, display, staged):
    from arrt.programming.display_state import ScreenState

    scene, works = staged
    hall, study = works
    client = services.clients.add_client(name="Pi")
    services.clients.assign_wall(hall, client_id=client.id, output="hdmi-a-1")
    services.clients.assign_wall(study, client_id=client.id, output="hdmi-a-2")
    applied = display.apply_scene(scene.id, lifetime="hold")
    display.record_heartbeat(hall, _beat(scene.id, work_id=works[hall].id))
    display.record_heartbeat(study, _beat(None, state="in_use"))

    reach = {wall.wall_id: wall for wall in display.scene_walls(applied)}

    assert reach[hall].reached is True
    assert reach[hall].work_id == works[hall].id
    assert reach[study].reached is False
    assert reach[study].wall_name == "Study"
    assert (reach[hall].screen, reach[study].screen) == (ScreenState.SHOWING_ART, ScreenState.IN_USE)


def test_a_wall_whose_heartbeat_names_another_scene_has_not_reached_this_one(display, staged):
    scene, works = staged
    hall = next(iter(works))
    applied = display.apply_scene(scene.id, lifetime="hold")
    display.record_heartbeat(hall, _beat("an-earlier-scene", work_id=works[hall].id))

    assert {wall.wall_id: wall.reached for wall in display.scene_walls(applied)}[hall] is False
