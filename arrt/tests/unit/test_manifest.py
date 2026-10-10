"""The build behind a wall's feed — what reaches the wall, what does not, and why.

Membership in the feed *is* catalogue readiness, so this file is where that
rule is pinned. The exclusion assertions carry the weight: a builder that only
returned a list would pass every entry-count check here and still be an
incomplete implementation of the design it comes from, because a work can sit in
a theme and never reach the wall with nothing saying so.
"""

import json
from dataclasses import replace

import pytest

from arrt.library import readiness
from arrt.library.dimensions import Units
from arrt.library.facade import UnplayableReason
from arrt.library.readiness import not_in_catalogue
from arrt.persistence.records import (
    FetchStatus,
    RenditionKind,
)
from arrt.programming.display import DisplayService
from arrt.programming.manifest import builder
from arrt.programming.manifest.builder import write_atomically
from arrt.programming.manifest.v2 import SCHEMA_MAJOR, read_published
from arrt.services.errors import ServiceError


@pytest.fixture
def feed(wall_settings):
    """A wall's feed as last published, read back."""

    def _feed(wall_id):
        return read_published(wall_settings.manifest_v2_path(wall_id))

    return _feed


@pytest.fixture
def theme_of(display):
    """A theme holding the given works, in the order given."""

    def _theme(*works, name="Late night"):
        theme = display.add_theme(name=name)
        for position, work in enumerate(works):
            display.add_to_theme(theme_id=theme.id, artwork_id=work.id, position=position)
        return theme

    return _theme


# -- readiness, one cause at a time --------------------------------------------


def test_a_work_with_everything_it_needs_reaches_the_wall(display, ready_work, theme_of, wall_id):
    work = ready_work()
    theme = theme_of(work)

    build = display.build_manifest(wall_id, theme.id)

    assert [entry.work_id for entry in build.entries] == [work.id]
    assert build.exclusions == []


def test_an_archived_work_leaves_the_manifest_but_stays_in_the_theme(service, display, ready_work, theme_of, wall_id):
    """Theme membership is curatorial; readiness is technical. Archiving moves one, not the other."""
    work = ready_work()
    theme = theme_of(work)
    service.archive_artwork(work.id)

    build = display.build_manifest(wall_id, theme.id)

    assert build.entries == []
    assert [exclusion.reason for exclusion in build.exclusions] == [UnplayableReason.ARCHIVED]
    # Still a member — the curator said it belongs here and nothing has unsaid it.
    assert list(display.theme_work_ids(theme.id)) == [work.id]


def test_a_work_with_no_acquired_original_is_excluded_and_named(display, ready_work, theme_of, wall_id):
    theme = theme_of(ready_work(original=False))

    build = display.build_manifest(wall_id, theme.id)

    assert build.entries == []
    assert [exclusion.reason for exclusion in build.exclusions] == [UnplayableReason.NO_ORIGINAL]
    assert "acquired" in build.exclusions[0].detail


class _ForgetsOneWork:
    """The real facade, except that one work has gone from the catalogue.

    Foreign keys stop that happening today, and they go when Programming's
    tables move to a file of their own. The facade is the only thing Programming
    asks, so standing in for it is the whole of the arrangement.
    """

    def __init__(self, library, forgotten: str) -> None:
        self._library = library
        self._forgotten = forgotten

    def playable(self, work_ids):
        ids = list(work_ids)
        answers = self._library.playable(id_ for id_ in ids if id_ != self._forgotten)
        return {id_: not_in_catalogue(id_) if id_ == self._forgotten else answers[id_] for id_ in ids}


def test_a_work_the_catalogue_no_longer_holds_is_excluded_and_named_by_its_id(
    store, library, wall_settings, ready_work, theme_of, wall_id
):
    """A dangling reference costs the wall one work, not the whole theme.

    Named by its id, because there is no title to give and every row of the
    exclusion report is read by a curator looking for which one.
    """
    kept = ready_work(title="Nighthawks")
    gone = ready_work(title="Automat")
    theme = theme_of(kept, gone)
    display = DisplayService(store, _ForgetsOneWork(library, gone.id), wall_settings)

    build = display.build_manifest(wall_id, theme.id)

    assert [entry.work_id for entry in build.entries] == [kept.id]
    assert [(exclusion.work_id, exclusion.title, exclusion.reason) for exclusion in build.exclusions] == [
        (gone.id, gone.id, UnplayableReason.NOT_IN_CATALOGUE)
    ]
    assert build.exclusions[0].detail == f"No artwork with id {gone.id!r} is in the catalogue."
    assert build.summarise().startswith("1 of 2 works")


def test_a_work_that_has_not_been_rendered_is_excluded_and_named(display, ready_work, theme_of, wall_id):
    theme = theme_of(ready_work(master=False))

    build = display.build_manifest(wall_id, theme.id)

    assert [exclusion.reason for exclusion in build.exclusions] == [UnplayableReason.NO_RENDITION]


def test_a_work_with_no_current_mat_colour_is_excluded_and_named(display, ready_work, theme_of, wall_id):
    theme = theme_of(ready_work(mat=False))

    build = display.build_manifest(wall_id, theme.id)

    assert [exclusion.reason for exclusion in build.exclusions] == [UnplayableReason.NO_MAT_COLOR]


def test_a_render_made_from_an_earlier_acquisition_is_excluded_as_stale(service, display, ready_work, theme_of, wall_id):
    """Re-acquiring leaves the old render in place, and showing it would put the previous image on the wall."""
    work = ready_work()
    theme = theme_of(work)
    source = service.list_sources(work.id)[0]
    service.record_original(
        artwork_id=work.id,
        source_id=source.id,
        path=f"raw/{work.id}.tif",
        width=6000,
        height=4000,
        byte_size=90_000_000,
        content_hash="hash-2",
        fetch_status=FetchStatus.OK,
    )

    build = display.build_manifest(wall_id, theme.id)

    assert build.entries == []
    assert [exclusion.reason for exclusion in build.exclusions] == [UnplayableReason.STALE_RENDITION]


def test_making_the_master_again_returns_the_work_to_the_wall(service, display, ready_work, theme_of, wall_id):
    """The exclusion is a state, not a verdict — the multi-hop step that proves it clears."""
    work = ready_work()
    theme = theme_of(work)
    source = service.list_sources(work.id)[0]
    service.record_original(
        artwork_id=work.id,
        source_id=source.id,
        path=f"raw/{work.id}.tif",
        width=6000,
        height=4000,
        byte_size=90_000_000,
        content_hash="hash-2",
        fetch_status=FetchStatus.OK,
    )
    assert display.build_manifest(wall_id, theme.id).entries == []

    service.record_rendition(
        artwork_id=work.id,
        kind=RenditionKind.PRESENTATION_MASTER,
        target_width=7680,
        target_height=7680,
        path=f"masters/{work.id}.jpg",
    )

    build = display.build_manifest(wall_id, theme.id)
    assert [entry.work_id for entry in build.entries] == [work.id]
    assert build.exclusions == []


def test_a_thumbnail_is_not_a_television_render(service, display, ready_work, theme_of, wall_id):
    """The wall needs the 4K presentation with the mat composed in, not any derived image."""
    work = ready_work(master=False)
    theme = theme_of(work)
    service.record_rendition(
        artwork_id=work.id,
        kind=RenditionKind.THUMBNAIL,
        target_width=400,
        target_height=300,
        path=f"tv-thumbs/{work.id}.jpg",
    )

    build = display.build_manifest(wall_id, theme.id)

    assert [exclusion.reason for exclusion in build.exclusions] == [UnplayableReason.NO_RENDITION]


def test_every_member_is_accounted_for_as_an_entry_or_an_exclusion(display, ready_work, theme_of, wall_id):
    """The property that makes the report trustworthy: nothing is silently dropped."""
    theme = theme_of(ready_work("Nighthawks"), ready_work("Chop Suey", original=False), ready_work("Automat", mat=False))

    build = display.build_manifest(wall_id, theme.id)

    assert len(build.entries) == 1
    assert len(build.exclusions) == 2
    assert build.considered == 3
    assert {exclusion.title for exclusion in build.exclusions} == {"Chop Suey", "Automat"}


def test_an_exclusion_names_the_work_a_curator_would_look_for(display, ready_work, theme_of, wall_id):
    """A reason nobody can act on is the silence this report exists to break."""
    work = ready_work("Chop Suey", original=False)
    theme = theme_of(work)

    exclusion = display.build_manifest(wall_id, theme.id).exclusions[0]

    assert exclusion.work_id == work.id
    assert exclusion.title == "Chop Suey"
    assert exclusion.detail.endswith(".")


# -- the document ---------------------------------------------------------------


def test_the_manifest_carries_the_label_text_but_no_label_geometry(service, display, ready_work, theme_of, wall_id):
    """Label text crosses to the display plane; how it is set does not."""
    hopper = service.add_artist(
        name="Edward Hopper", nationality="American", born=1882, died=1967, family_name="Hopper", given_name="Edward"
    )
    theme = theme_of(ready_work(artist_id=hopper.id, commentary="Painted in a Greenwich Village studio."))

    label = display.build_manifest(wall_id, theme.id).entries[0].label

    assert label["title"] == "Nighthawks"
    assert label["artist"] == "Edward Hopper"
    # The whole name AND its parts: a panel setting the family name in bold
    # capitals needs the parts, and a work whose artist has none has only the
    # whole — so dropping either shape makes one of the two unlabelable.
    assert label["artist_family_name"] == "Hopper"
    assert label["artist_given_name"] == "Edward"
    assert label["artist_nationality"] == "American"
    assert label["artist_dates"] == "1882–1967"
    assert label["date_created"] == "1942"
    assert label["medium"] == "Oil on canvas"
    assert label["commentary"] == "Painted in a Greenwich Village studio."
    assert not any(key in label for key in ("font", "font_size", "panel_width", "panel_height"))


def test_the_manifest_carries_the_short_nationality_when_a_curator_has_set_one(service, display, ready_work, theme_of, wall_id):
    """**The resolution happens here, not at the panel.** The manifest is what the
    display plane parses rather than a catalogue export, so it carries the string
    the label should set; choosing between two recorded strings is a question
    about content, and content is this plane's. A display told to choose would be
    re-deciding curation policy from the far side of the seam.
    """
    kandinsky = service.add_artist(
        name="Vasily Kandinsky",
        nationality="Born Moscow (formerly Russian Empire, now Russia)",
        display_nationality="Russian",
        born=1866,
        died=1944,
    )
    theme = theme_of(ready_work(artist_id=kandinsky.id))

    label = display.build_manifest(wall_id, theme.id).entries[0].label

    assert label["artist_nationality"] == "Russian"


def test_the_manifest_carries_the_recorded_nationality_when_nobody_has_shortened_it(
    service, display, ready_work, theme_of, wall_id
):
    """Null means "set what the catalogue recorded", so a record nobody has
    shortened reads exactly as it did before the column existed. Most of this
    corpus is already a demonym and needs nothing."""
    moche = service.add_artist(name="Moche", nationality="North coast, Peru")
    theme = theme_of(ready_work(artist_id=moche.id))

    label = display.build_manifest(wall_id, theme.id).entries[0].label

    assert label["artist_nationality"] == "North coast, Peru"


def test_a_work_with_no_artist_still_produces_a_legible_label(display, ready_work, theme_of, wall_id):
    """Unattributed works are real; a label that failed on one would take it off the wall."""
    theme = theme_of(ready_work())

    label = display.build_manifest(wall_id, theme.id).entries[0].label

    assert label["title"] == "Nighthawks"
    assert label["artist"] is None
    assert label["artist_dates"] is None


def test_the_written_feed_is_json_a_player_can_parse(display, ready_work, theme_of, wall_settings, wall_id):
    work = ready_work()
    theme = theme_of(work)

    display.sync(wall_id, theme.id)

    document = json.loads(wall_settings.manifest_v2_path(wall_id).read_text())
    assert document["schema"]["major"] == SCHEMA_MAJOR
    assert document["playlist"]["name"] == theme.name
    assert list(document["works"]) == [work.id]


def test_the_feed_does_not_carry_the_exclusions(display, ready_work, theme_of, wall_settings, wall_id):
    """They are curation's report about its own catalogue, not something a Player can use."""
    shown = ready_work("Nighthawks")
    theme = theme_of(shown, ready_work("Chop Suey", original=False))

    build = display.sync(wall_id, theme.id)

    assert len(build.exclusions) == 1
    document = json.loads(wall_settings.manifest_v2_path(wall_id).read_text())
    assert "exclusions" not in document
    assert list(document["works"]) == [shown.id]


def test_entries_follow_the_curated_order(display, ready_work, theme_of, wall_id):
    first = ready_work("Nighthawks")
    second = ready_work("Chop Suey")
    theme = theme_of(first, second)

    build = display.build_manifest(wall_id, theme.id)

    assert [entry.work_id for entry in build.entries] == [first.id, second.id]


# -- rotation settings ----------------------------------------------------------


def test_a_theme_that_expressed_no_pace_inherits_the_deployment_default(display, ready_work, theme_of, wall_settings, wall_id):
    theme = theme_of(ready_work())

    build = display.build_manifest(wall_id, theme.id)

    assert build.rotation_interval_seconds == wall_settings.rotation_interval_seconds
    assert build.shuffle == wall_settings.shuffle


def test_a_themes_own_pace_wins_over_the_default(store, display, ready_work, theme_of, wall_settings, wall_id):
    """Seeded through the store: nothing writes these yet, and the manifest is their only reader."""
    theme = theme_of(ready_work())
    # Values no default could produce, so a field read from the wrong place shows.
    store.update_theme(replace(theme, rotation_interval_seconds=931, shuffle=not wall_settings.shuffle))

    build = display.build_manifest(wall_id, theme.id)

    assert build.rotation_interval_seconds == 931
    assert build.shuffle is (not wall_settings.shuffle)


# -- writing ---------------------------------------------------------------------


def test_no_reader_ever_observes_a_partial_manifest(tmp_path, monkeypatch):
    """Atomicity is the whole concurrency-control story between the planes.

    Observed *during* the write rather than between writes, which is the only
    version of this that can fail: reading before and after would pass just as
    happily against a write straight to the destination. The hook fires while
    the new document is being serialised, and at that moment the destination must
    still hold the previous one whole — a reader polling this path can never be
    handed a truncated file, which would parse as invalid JSON rather than as
    absent and leave the display plane with no good answer.
    """
    path = tmp_path / "theme-manifest.json"
    write_atomically(path, {"entries": [{"work_id": "first"}]})

    observed = []
    real_dump = builder.json.dump

    def dump_and_peek(document, stream, **kwargs):
        # Mid-write: whatever a poller reads right now.
        observed.append(path.read_text())
        return real_dump(document, stream, **kwargs)

    monkeypatch.setattr(builder.json, "dump", dump_and_peek)
    write_atomically(path, {"entries": [{"work_id": "x" * 5000}]})

    assert observed, "the write did not go through the hook, so this asserted nothing"
    assert json.loads(observed[0])["entries"] == [{"work_id": "first"}]
    # And once the rename lands, the new document is there whole.
    assert json.loads(path.read_text())["entries"] == [{"work_id": "x" * 5000}]


def test_writing_leaves_no_temporary_files_behind(tmp_path):
    """A temp file per sync in ART_ROOT would accumulate where the display plane polls."""
    path = tmp_path / "theme-manifest.json"

    for _ in range(5):
        write_atomically(path, {"entries": []})

    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["theme-manifest.json"]


def test_a_failed_write_leaves_the_previous_manifest_in_place(tmp_path):
    """The wall keeps running off the last good manifest; a half-written one would stop it."""
    path = tmp_path / "theme-manifest.json"
    write_atomically(path, {"entries": [{"work_id": "first"}]})

    class Unserialisable:
        pass

    with pytest.raises(TypeError):
        write_atomically(path, {"entries": Unserialisable()})

    assert json.loads(path.read_text())["entries"] == [{"work_id": "first"}]
    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["theme-manifest.json"]


def test_the_manifest_directory_is_created_if_it_does_not_exist(tmp_path):
    """A fresh deployment has no ART_ROOT yet, and a sync must not be the thing that fails."""
    path = tmp_path / "art" / "theme-manifest.json"

    write_atomically(path, {"entries": []})

    assert json.loads(path.read_text()) == {"entries": []}


# -- refusals ---------------------------------------------------------------------


def test_showing_a_work_that_cannot_reach_the_wall_is_refused_with_its_reason(
    display, ready_work, theme_of, wall_settings, wall_id
):
    """The one path that could publish a work nothing can show.

    Answering "done" and then never moving the wall is the silence the
    exclusion report exists to break, arriving through the action that did not
    consult readiness. The refusal carries the same sentence the build would
    have given, so the curator learns what to fix.
    """
    display.activate_theme(theme_of(ready_work("Automat")).id, wall_id=wall_id)
    published = wall_settings.manifest_v2_path(wall_id).read_bytes()
    work = ready_work(master=False)

    with pytest.raises(ServiceError, match="no presentation master has been made"):
        display.show_work_now(wall_id, work.id)

    # And nothing was published: a refused show-now leaves the wall's feed as it was.
    assert wall_settings.manifest_v2_path(wall_id).read_bytes() == published


def test_a_work_can_be_shown_once_it_is_displayable(
    display, service, ready_work, theme_of, feed, wall_id, wall_settings, decodable_jpeg
):
    """The refusal is a state, not a verdict about the work."""
    display.activate_theme(theme_of(ready_work("Automat")).id, wall_id=wall_id)
    work = ready_work(master=False)
    with pytest.raises(ServiceError):
        display.show_work_now(wall_id, work.id)

    decodable_jpeg(wall_settings.art_root / f"masters/{work.id}.jpg", width=400, height=300)
    service.record_rendition(
        artwork_id=work.id,
        kind=RenditionKind.PRESENTATION_MASTER,
        target_width=7680,
        target_height=7680,
        path=f"masters/{work.id}.jpg",
    )

    assert display.show_work_now(wall_id, work.id) == work.id
    assert feed(wall_id).slots[0].work_id == work.id


def test_a_work_with_no_master_cannot_be_made_into_an_entry(service):
    """The guard on the one path that would put a broken entry in the feed.

    `assess` is what keeps this unreachable; the raise is what makes a caller
    that skipped it fail loudly here rather than leave a wall a work short later.
    """
    work = service.add_artwork(title="Nighthawks")
    inputs = readiness.WorkInputs(artwork=work, artist=None, original=None, mat_color=None)

    with pytest.raises(ValueError, match="no master to send"):
        readiness.playable_from(inputs, units=Units.IMPERIAL)


def test_building_for_a_wall_with_nothing_hanging_is_refused_rather_than_writing_an_empty_feed(display, wall_id):
    """An empty feed would read as "show nothing", which is not what "nothing hung yet" means.

    The refusal names the wall, because with two of them "nothing is hanging" is
    not an answer a curator can act on without knowing where.
    """
    with pytest.raises(ServiceError, match="Nothing is hanging on"):
        display.build_manifest(wall_id)


def test_building_for_an_unknown_wall_names_the_id_it_could_not_find(display):
    with pytest.raises(ServiceError, match="No wall with id 'nope'"):
        display.build_manifest("nope")


def test_building_an_unknown_theme_names_the_id_it_could_not_find(display, wall_id):
    with pytest.raises(ServiceError, match="No theme with id 'nope'"):
        display.build_manifest(wall_id, "nope")


# -- one feed per wall -----------------------------------------------------------


class TestOneFeedPerWall:
    """Each wall gets its own document, and one room's rewrite leaves the rest alone.

    **This is the property the per-file decision was made for.** A Player polls
    its wall's feed by ETag about once a second, so a shared file would change
    every wall's ETag on every other wall's change, and wake each Player for a
    change that was never about it. Per file also leaves a Player unable to read
    a wall it does not serve.
    """

    @pytest.fixture
    def two_walls(self, display, wall_id):
        """The wall a fresh catalogue holds, and a second the curator recorded."""
        return wall_id, display.add_wall(name="The study").id

    def test_each_wall_gets_its_own_document(self, display, ready_work, theme_of, wall_settings, two_walls):
        living_room, study = two_walls
        theirs = theme_of(ready_work("Nighthawks"), name="Late night")
        ours = theme_of(ready_work("The Elephants"), name="Surrealists")

        display.activate_theme(theirs.id, wall_id=living_room)
        display.activate_theme(ours.id, wall_id=study)

        assert json.loads(wall_settings.manifest_v2_path(living_room).read_text())["playlist"]["name"] == "Late night"
        assert json.loads(wall_settings.manifest_v2_path(study).read_text())["playlist"]["name"] == "Surrealists"

    def test_one_walls_rewrite_does_not_touch_another_walls_file(self, display, ready_work, theme_of, wall_settings, two_walls):
        """**The bytes and the mtime, not just the parse.** A step or a sync in the
        living room is a republish of the living room alone; touching the study's
        file at all would change its ETag and wake its Player for nothing."""
        living_room, study = two_walls
        theme = theme_of(ready_work("Nighthawks"), ready_work("Automat"))
        display.activate_theme(theme.id, wall_id=living_room)
        display.activate_theme(theme.id, wall_id=study)
        untouched = wall_settings.manifest_v2_path(study)
        before = (untouched.stat().st_mtime_ns, untouched.read_bytes())

        for _ in range(3):
            display.step_display(living_room)
            display.sync(living_room)

        assert (untouched.stat().st_mtime_ns, untouched.read_bytes()) == before

    def test_showing_a_work_now_reaches_one_wall_and_not_the_other(self, display, ready_work, theme_of, feed, two_walls):
        """Multi-hop: the work is published first on one wall, and the neighbour's schedule is as it was."""
        living_room, study = two_walls
        first, second = ready_work("Nighthawks"), ready_work("Automat")
        theme = theme_of(first, second)
        display.activate_theme(theme.id, wall_id=living_room)
        display.activate_theme(theme.id, wall_id=study)
        study_before = feed(study).slots

        display.show_work_now(living_room, second.id)

        assert feed(living_room).slots[0].work_id == second.id
        assert feed(study).slots == study_before

    def test_the_one_wall_case_is_named_by_its_file(self, display, ready_work, theme_of, wall_settings, wall_id):
        """The document itself carries no wall: the *filename* names it, which keeps
        a Player unable to open a room it does not serve rather than merely
        unwilling to act on it. Two answers to "which wall is this" could
        disagree; one cannot.
        """
        theme = theme_of(ready_work("Nighthawks"))

        display.activate_theme(theme.id, wall_id=wall_id)

        published = wall_settings.manifest_v2_path(wall_id)
        assert published.name == f"theme-manifest-{wall_id}.v2.json"
        document = json.loads(published.read_text())
        assert "wall" not in document
        assert wall_id not in json.dumps(document)
        assert list(document["works"]) == [theme_works(display, theme.id)[0]]

    def test_the_heartbeat_is_read_per_wall_too(self, display, wall_settings, two_walls):
        """Health has to be able to name which wall is silent.

        One shared heartbeat could not: the second display would overwrite the
        first's report every minute, so a wall that had gone dark would read
        exactly like a wall that was fine.
        """
        living_room, study = two_walls
        wall_settings.heartbeat_path(living_room).write_text(
            json.dumps({"reported_at": "2026-08-12T00:00:00+00:00"}), encoding="utf-8"
        )

        reported = {reading.wall.id: reading.heartbeat.absent for reading in display.survey_wall_status()}

        assert reported == {living_room: False, study: True}


def theme_works(display, theme_id) -> list[str]:
    return list(display.theme_work_ids(theme_id))
