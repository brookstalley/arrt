"""Deleting a wall: every row that names it, decided (`build-plan-delete-a-wall.md` § Goals).

The owner's rulings of 2026-10-30: the delete is permanent and the wall's history
stays; a wall in the live scene leaves it and the scene goes on; a theme hanging
on it does not stop the delete; the last wall may go. Each test below holds one
row of the plan's table, with a second wall that keeps its own of the same thing,
so a delete that took both walls' rows would fail.
"""

import json
from datetime import UTC, datetime

import pytest

from arrt.persistence.file import open_catalogue_file
from arrt.persistence.records import EventKind, RenditionKind, Showing
from arrt.persistence.sqlite import SqliteCatalogue
from arrt.services.errors import ServiceError

HOUR = 3600

_REPORT = {
    "reported_at": "2026-10-30T12:00:00+00:00",
    "outputs": [
        {"name": "hdmi-a-1", "kind": "framebuffer", "connected": True, "screen": [1920, 1080]},
        {"name": "hdmi-a-2", "kind": "framebuffer", "connected": True, "screen": [1920, 1080]},
    ],
    "label_outputs": [
        {"name": "epd-0", "kind": "epaper", "connected": True, "size": [800, 480]},
        {"name": "epd-1", "kind": "epaper", "connected": True, "size": [800, 480]},
    ],
}


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
def two_walls(display, mastered, wall_id):
    """The hall and the study, each hanging a theme of its own, an hour a work."""
    study = display.add_wall(name="Study").id
    for wall, names in ((wall_id, ("H1", "H2")), (study, ("S1", "S2"))):
        theme = display.add_theme(name=f"Theme of {names[0]}")
        for position, work in enumerate(mastered(name) for name in names):
            display.add_to_theme(theme_id=theme.id, artwork_id=work.id, position=position)
        display.set_playback(wall, rotation_interval_seconds=HOUR, shuffle=False)
        display.activate_theme(theme.id, wall_id=wall)
    return wall_id, study


@pytest.fixture
def pi(services):
    """A Player with two screens and two label panels, showing nothing yet."""
    client = services.clients.add_client(name="The Pi in the hall")
    services.clients.record_heartbeat(client.id, _REPORT)
    return client


# -- the wall itself ---------------------------------------------------------------------


def test_a_deleted_wall_is_gone_and_the_other_stays(display, two_walls):
    hall, study = two_walls

    display.delete_wall(study)

    assert [view.wall.id for view in display.survey_walls()] == [hall]
    with pytest.raises(ServiceError, match="No wall with id"):
        display.get_wall(study)


def test_an_unknown_wall_is_refused_by_id(display):
    with pytest.raises(ServiceError, match="No wall with id 'nowhere'"):
        display.delete_wall("nowhere")


def test_its_name_is_free_again(display, two_walls):
    _, study = two_walls
    display.delete_wall(study)

    assert display.add_wall(name="Study").name == "Study"


# -- what hangs on it -------------------------------------------------------------------


def test_what_it_hangs_comes_down_and_the_theme_stays(display, two_walls):
    hall, study = two_walls
    theme = display.hanging_on(study)

    display.delete_wall(study)

    assert display.get_theme(theme.id).name == theme.name, "the theme is not the wall's to take"
    assert display.hanging_on(hall) is not None, "the other wall still hangs its own"


def test_a_selection_only_it_hung_is_retired_and_one_another_wall_hangs_is_kept(display, mastered, two_walls):
    hall, study = two_walls
    landing = display.add_wall(name="Landing").id
    selection = display.hang_selection([mastered("Shared").id], wall_id=study).theme
    # The same selection on a second wall: the route `clear_wall` keeps it by.
    display.activate_theme(selection.id, wall_id=landing)
    alone = display.hang_selection([mastered("Alone").id], wall_id=hall).theme

    display.delete_wall(study)
    display.delete_wall(hall)

    assert display._store.get_theme(alone.id) is None, "a selection nothing hangs any more is retired"
    assert display._store.get_theme(selection.id) is not None, "a selection another wall still hangs is kept"
    assert display.hanging_on(landing).id == selection.id


# -- its Player, screen and label panels -------------------------------------------------


def test_its_screen_is_freed_and_the_other_walls_placement_stays(services, display, two_walls, pi):
    hall, study = two_walls
    services.clients.assign_wall(study, client_id=pi.id, output="hdmi-a-1")
    services.clients.assign_wall(hall, client_id=pi.id, output="hdmi-a-2")

    display.delete_wall(study)

    assert [wall.id for wall in services.clients.walls_of(pi.id)] == [hall]
    landing = display.add_wall(name="Landing")
    services.clients.assign_wall(landing.id, client_id=pi.id, output="hdmi-a-1")
    assert {wall.name for wall in services.clients.walls_of(pi.id)} == {"Landing", services.display.get_wall(hall).name}


def test_its_label_panel_stays_recorded_captions_nothing_and_the_others_keeps_captioning(services, store, display, two_walls, pi):
    hall, study = two_walls
    on_study = services.clients.add_label(study, client_id=pi.id, output="epd-0").label
    on_hall = services.clients.add_label(hall, client_id=pi.id, output="epd-1").label

    display.delete_wall(study)

    labels = {label.id: label.wall_id for label in store.list_label_outputs()}
    assert labels == {on_study.id: None, on_hall.id: hall}
    # And it can caption another wall.
    landing = display.add_wall(name="Landing")
    assert services.clients.add_label(landing.id, client_id=pi.id, output="epd-0").label.id == on_study.id


def test_the_player_document_no_longer_lists_it(services, display, two_walls, pi):
    hall, study = two_walls
    services.clients.assign_wall(study, client_id=pi.id, output="hdmi-a-1")
    services.clients.assign_wall(hall, client_id=pi.id, output="hdmi-a-2")

    display.delete_wall(study)

    document = json.loads(services.clients.client_document(pi.id))
    assert [wall["wall_id"] for wall in document["walls"]] == [hall]


# -- its files ---------------------------------------------------------------------------


def test_its_feed_and_heartbeat_files_go_and_the_others_stay(display, wall_settings, two_walls):
    hall, study = two_walls
    for wall in (hall, study):
        wall_settings.heartbeat_path(wall).write_text("{}", encoding="utf-8")
        assert wall_settings.manifest_v2_path(wall).exists()

    display.delete_wall(study)

    assert not wall_settings.manifest_v2_path(study).exists()
    assert not wall_settings.heartbeat_path(study).exists()
    assert wall_settings.manifest_v2_path(hall).exists()
    assert wall_settings.heartbeat_path(hall).exists()


# -- scenes ------------------------------------------------------------------------------


def test_its_pick_in_the_scene_being_assembled_goes_and_the_draft_can_still_be_applied(display, mastered, two_walls):
    hall, study = two_walls
    draft = display.draft_scene().scene.id
    display.pin_scene(draft, study, mastered("Golconda").id)
    display.pin_scene(draft, hall, mastered("Persistence").id)

    display.delete_wall(study)

    assert [pin.wall_id for pin in display.scene_draft().pins] == [hall]
    applied = display.apply_scene(draft, lifetime="preview", minutes=20)
    assert [pin.wall_id for pin in applied.pins] == [hall]


def test_a_live_scene_goes_on_for_the_other_wall_and_its_record_keeps_both_pins(display, mastered, two_walls, store):
    hall, study = two_walls
    draft = display.draft_scene().scene.id
    display.pin_scene(draft, study, mastered("Golconda").id)
    display.pin_scene(draft, hall, mastered("Persistence").id)
    display.apply_scene(draft, lifetime="preview", minutes=20)

    display.delete_wall(study)

    live = display.live_scene()
    assert live is not None
    assert live.scene.id == draft
    assert {wall.wall_id for wall in display.scene_walls(live)} == {hall}
    assert {pin.wall_id for pin in store.list_pins(draft)} == {hall, study}, "the applied scene's record is kept"
    display.release_scene(draft)
    assert display.live_scene() is None


def test_a_live_scene_released_after_its_wall_is_deleted_names_only_the_walls_left(
    services, display, mastered, two_walls, store, caplog
):
    hall, study = two_walls
    draft = display.draft_scene().scene.id
    display.pin_scene(draft, study, mastered("Golconda").id)
    display.pin_scene(draft, hall, mastered("Persistence").id)
    display.apply_scene(draft, lifetime="hold")
    display.delete_wall(study)

    with caplog.at_level("WARNING", logger="arrt.programming.display"):
        display.release_scene(draft)

    ended = services.catalogue.list_events(kinds=[EventKind.SCENE_ENDED]).events
    assert [event.wall_id for event in ended] == [hall]
    assert ended[0].detail["wall_name"] == display.get_wall(hall).name
    assert not [record for record in caplog.records if "has no feed" in record.getMessage()]


# -- its history -------------------------------------------------------------------------


def test_its_showings_stay(display, store, two_walls):
    hall, study = two_walls
    moment = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
    for wall in (hall, study):
        store.save_showing(Showing(wall_id=wall, work_id=f"work-on-{wall}", started_at=moment, last_seen_at=moment))

    display.delete_wall(study)

    assert store.latest_showing(study).work_id == f"work-on-{study}"
    assert set(store.last_shown_by_work()) == {f"work-on-{hall}", f"work-on-{study}"}


def test_its_history_stays_and_names_it(services, display, mastered, two_walls):
    _, study = two_walls
    name = display.get_wall(study).name
    theme = display.hanging_on(study)
    member = display._store.list_memberships(theme.id)[0].artwork_id
    display.leave_theme(member, wall_id=study)
    display.exclude_work(mastered("Kept off").id, wall_id=study)

    display.delete_wall(study)

    events = services.catalogue.list_events(wall_id=study).events
    kinds = {event.kind for event in events}
    assert {EventKind.HUNG, EventKind.LEFT_THEME, EventKind.EXCLUDED} <= kinds
    for event in events:
        if event.kind in (EventKind.HUNG, EventKind.LEFT_THEME, EventKind.EXCLUDED):
            assert event.detail.get("wall_name") == name, event.kind


# -- the last wall, and the file ---------------------------------------------------------


def test_the_last_wall_can_be_deleted_and_stays_deleted_when_the_file_is_opened_again(tmp_path):
    path = tmp_path / "catalogue.sqlite"
    first = open_catalogue_file(path, wall_name="Living room")
    catalogue = SqliteCatalogue(first)
    (wall,) = catalogue.list_walls()
    catalogue.remove_wall(wall.id)
    first.close()

    again = open_catalogue_file(path, wall_name="Living room")
    try:
        assert SqliteCatalogue(again).list_walls() == []
    finally:
        again.close()


def test_a_new_file_still_gets_its_wall(tmp_path):
    opened = open_catalogue_file(tmp_path / "new.sqlite", wall_name="Living room")
    try:
        assert [wall.name for wall in SqliteCatalogue(opened).list_walls()] == ["Living room"]
    finally:
        opened.close()


def test_deleting_the_last_wall_through_the_service_leaves_none(display, wall_id):
    display.delete_wall(wall_id)

    assert display.survey_walls() == []
