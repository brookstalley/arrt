"""What this plane will and will not act on, and what it keeps when it refuses."""

import json
import logging
import os
from pathlib import Path

import pytest
from conftest import WALL_ID, write_manifest

from arrt_player.config import CACHED_MANIFEST_FILENAME
from arrt_player.manifest import (
    REQUESTED_MAJORS,
    SUPPORTED_SCHEMA_MAJORS,
    ManifestUnreadable,
    ManifestVersionUnsupported,
    Watcher,
    parse,
)

CONTRACT = Path(__file__).resolve().parents[2] / "contract"

#: A media hash for the builder's one work: well-formed, and nothing to fetch.
_SHA = "a" * 64


def a_document(**overrides: object) -> dict:
    """A major 2 feed of one work in one slot, valid as it stands, to change one thing of."""
    document: dict = {
        "schema": {"major": 2, "minor": 0},
        "playlist": {"id": "t1", "name": "A theme"},
        "works": {
            "w1": {"media": {"url": f"/media/sha256-{_SHA}", "sha256": _SHA}, "mat_color": "#222222", "label": {"title": "One"}}
        },
        "schedule": {
            "horizon": {"from": "2026-06-21T00:00:00+00:00", "until": "2026-06-22T00:00:00+00:00"},
            "slots": [{"work_id": "w1", "from": "2026-06-21T08:00:00+00:00", "until": "2026-06-21T18:00:00+00:00"}],
        },
    }
    document.update(overrides)
    return document


def a_watcher(wall_dir: Path, wall_id: str = WALL_ID) -> Watcher:
    """A watcher over one wall's cached manifest — the only file it will ever open."""
    return Watcher(wall_dir.parent / wall_id / CACHED_MANIFEST_FILENAME)


def _named(name: str) -> dict:
    """The builder's document under another playlist name, which is how these tests tell two documents apart."""
    return a_document(playlist={"id": "t1", "name": name})


class TestParsing:
    def test_it_reads_what_the_server_writes(self):
        feed = parse(json.dumps(a_document()))

        assert feed.schema_major == 2
        assert feed.playlist_name == "A theme"
        assert list(feed.works) == ["w1"]
        assert feed.works["w1"].label == {"title": "One"}
        assert [slot.work_id for slot in feed.slots] == ["w1"]

    def test_an_unknown_major_is_refused_by_version_and_not_by_shape(self):
        """A future major is *expected* to be shaped differently.

        Reporting "works is missing" for a document whose own version says this
        reader should not be reading it sends whoever finds the line looking for a
        bug in the writer.
        """
        future = {"schema": {"major": max(SUPPORTED_SCHEMA_MAJORS) + 1, "minor": 0}, "everything": "else"}

        with pytest.raises(ManifestVersionUnsupported) as refusal:
            parse(json.dumps(future))

        assert refusal.value.major == max(SUPPORTED_SCHEMA_MAJORS) + 1

    def test_a_major_1_document_is_refused_by_version(self):
        """This Player reads major 2 only (`player-contract.md` § The cutover), so the
        major it used to read is a version it refuses, like any other it does not read."""
        document = json.loads((CONTRACT / "fixtures" / "manifest.v2" / "invalid" / "major-1.json").read_text())

        with pytest.raises(ManifestVersionUnsupported) as refusal:
            parse(json.dumps(document))

        assert refusal.value.major == 1
        assert SUPPORTED_SCHEMA_MAJORS == (2,)

    def test_an_unknown_minor_is_accepted_because_additive_changes_are_free(self):
        document = a_document(schema={"major": 2, "minor": 99})
        document["works"]["w1"]["something_new"] = "ignored"

        feed = parse(json.dumps(document))

        assert feed.schema_minor == 99
        assert list(feed.works) == ["w1"]

    @pytest.mark.parametrize(
        "document",
        [
            pytest.param("not json at all", id="not-json"),
            pytest.param(json.dumps([1, 2, 3]), id="not-an-object"),
            pytest.param(json.dumps({"works": {}}), id="no-schema"),
            pytest.param(json.dumps(a_document(works="lots")), id="works-not-an-object"),
            pytest.param(json.dumps(a_document(works={"w1": {"label": {"title": "One"}}})), id="work-without-media"),
            pytest.param(json.dumps(a_document(schedule={"slots": []})), id="schedule-without-horizon"),
        ],
    )
    def test_a_malformed_manifest_is_refused_rather_than_guessed_at(self, document):
        with pytest.raises(ManifestUnreadable):
            parse(document)


class TestWatching:
    def test_it_reports_a_manifest_once_and_then_stays_quiet(self, wall_dir: Path):
        write_manifest(wall_dir, a_document())
        watcher = a_watcher(wall_dir)

        assert watcher.poll() is not None
        assert watcher.poll() is None
        assert watcher.poll() is None

    def test_a_rewrite_is_picked_up(self, wall_dir: Path):
        write_manifest(wall_dir, a_document())
        watcher = a_watcher(wall_dir)
        watcher.poll()

        write_manifest(wall_dir, _named("Another theme"))

        adopted = watcher.poll()
        assert adopted is not None
        assert adopted.playlist_name == "Another theme"

    def test_a_refused_manifest_leaves_the_last_good_one_in_place(self, wall_dir: Path, caplog):
        write_manifest(wall_dir, a_document())
        watcher = a_watcher(wall_dir)
        good = watcher.poll()

        write_manifest(wall_dir, {"schema": {"major": 99, "minor": 0}})

        with caplog.at_level(logging.ERROR):
            assert watcher.poll() is None
        assert watcher.current is good
        assert "manifest.version_refused" in {record.__dict__.get("event") for record in caplog.records}

    def test_a_refusal_is_logged_once_per_file_rather_than_once_per_poll(self, wall_dir: Path, caplog):
        """At one poll a second, a repeated refusal would write 86,400 identical
        ERROR lines a day — which is how the *next* fault becomes unfindable."""
        write_manifest(wall_dir, {"schema": {"major": 99, "minor": 0}})
        watcher = a_watcher(wall_dir)

        with caplog.at_level(logging.ERROR):
            for _ in range(5):
                watcher.poll()

        refusals = [record for record in caplog.records if record.__dict__.get("event") == "manifest.version_refused"]
        assert len(refusals) == 1

    def test_a_manifest_that_is_not_valid_utf8_is_refused_rather_than_fatal(self, wall_dir: Path, caplog):
        """`UnicodeDecodeError` is a `ValueError`, not an `OSError`.

        So it escaped the read's own except clause and every frame above it,
        taking the daemon down over exactly the kind of malformed file this
        module exists to refuse — a truncated write from a filesystem that lost
        power mid-`replace` produces it.
        """
        write_manifest(wall_dir, a_document())
        watcher = a_watcher(wall_dir)
        good = watcher.poll()

        (wall_dir / CACHED_MANIFEST_FILENAME).write_bytes(b'{"schema": {"major": 2}, "works": {}, "\xff\xfe": 1}')

        with caplog.at_level(logging.ERROR):
            assert watcher.poll() is None
        assert watcher.current is good
        assert "manifest.not_text" in {r.__dict__.get("event") for r in caplog.records}

    def test_a_manifest_that_has_never_appeared_is_not_an_error(self, wall_dir: Path, caplog):
        """A plane that has not published yet is a normal state on a fresh install,
        and this one holding still until it does is the availability norm working."""
        watcher = a_watcher(wall_dir)

        with caplog.at_level(logging.DEBUG):
            for _ in range(3):
                assert watcher.poll() is None

        levels = {record.levelno for record in caplog.records}
        assert logging.WARNING not in levels
        assert logging.ERROR not in levels
        assert len([r for r in caplog.records if r.__dict__.get("event") == "manifest.absent"]) == 1

    def test_two_writes_in_the_same_filesystem_tick_are_both_seen(self, wall_dir: Path):
        """`sync` and a `next` can land inside one second, and a coarse mtime would
        hide the second one forever — the wall would stop responding with nothing
        in the journal to say why."""
        target = wall_dir / CACHED_MANIFEST_FILENAME
        write_manifest(wall_dir, a_document())
        watcher = a_watcher(wall_dir)
        watcher.poll()
        before = target.stat()

        second = _named("A second theme")
        second["works"]["w2"] = {**second["works"]["w1"], "label": {"title": "Two"}}
        write_manifest(wall_dir, second)
        # Put the mtime back where it was, which is what a filesystem with
        # one-second resolution does to two writes inside one tick.
        os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))

        adopted = watcher.poll()
        assert adopted is not None
        assert adopted.playlist_name == "A second theme"


class TestAnUnreadableManifestIsSaidOnce:
    """The third instance of a class this plane has fixed twice already.

    The faults that reach the `OSError` arm do not clear on their own — EIO from a
    failing card, EACCES, ESTALE on a dropped mount — so at a one-second poll an
    unguarded WARNING is 86,400 identical lines a day, into a journal that
    rate-limits and whose dropped lines are the ERRORs this plane depends on.
    """

    def test_a_persistent_stat_failure_is_reported_once(self, tmp_path, caplog, monkeypatch):
        path = tmp_path / "theme-manifest.json"
        path.write_text("{}")
        watcher = Watcher(path)

        def unreadable(*_args, **_kwargs):
            raise OSError(5, "Input/output error")

        monkeypatch.setattr(Path, "stat", unreadable)
        with caplog.at_level(logging.WARNING):
            for _ in range(20):
                watcher.poll()

        reports = [r for r in caplog.records if getattr(r, "event", None) == "manifest.unstatable"]
        assert len(reports) == 1, f"an unreadable manifest was reported {len(reports)} times"

    def test_the_recovery_is_said_too(self, tmp_path, caplog, monkeypatch):
        """Otherwise the WARNING stands unresolved in the journal for ever."""
        path = tmp_path / "theme-manifest.json"
        path.write_text("{}")
        watcher = Watcher(path)

        real_stat = Path.stat
        broken = True

        def sometimes(self, *args, **kwargs):
            if broken:
                raise OSError(5, "Input/output error")
            return real_stat(self, *args, **kwargs)

        monkeypatch.setattr(Path, "stat", sometimes)
        watcher.poll()
        broken = False
        with caplog.at_level(logging.INFO):
            watcher.poll()

        assert [r for r in caplog.records if getattr(r, "event", None) == "manifest.statable"]


class TestOneManifestPerWall:
    """A wall's worker serves one room, and cannot read another's — even on one client.

    **The mechanism is the path, not a check.** Each wall's manifest is cached in
    its own directory, `CACHE_DIR/<wall id>/manifest.json`, and a worker stats
    exactly the one its wall's id names — so the other rooms' documents, though
    the same client pulls them, are files it never opens. That is what makes "the
    wall shows another room's pictures" structurally impossible rather than
    defended against.

    It matters because a shared file's failure was silent in both directions:
    one wall's manifest would overwrite another's, and the second wall's worker
    had no way to notice that the file it was reading had stopped being about it.
    """

    def test_it_adopts_the_manifest_for_the_wall_it_serves(self, wall_dir: Path):
        write_manifest(wall_dir, a_document(), wall_id=WALL_ID)

        adopted = a_watcher(wall_dir, WALL_ID).poll()

        assert adopted is not None
        assert adopted.playlist_name == "A theme"

    def test_a_manifest_for_a_wall_it_does_not_serve_is_not_acted_on(self, wall_dir: Path, caplog):
        """Published for the study; this device serves the living room.

        Not adopted, and — the half that matters — reported as *absent* rather
        than as anything having gone wrong. A device waiting for a manifest that
        has not been published yet is an ordinary state, and another room's file
        sitting beside it does not change what this one is waiting for.
        """
        write_manifest(wall_dir, a_document(), wall_id="study")

        with caplog.at_level(logging.INFO):
            assert a_watcher(wall_dir, WALL_ID).poll() is None

        assert "manifest.absent" in {record.__dict__.get("event") for record in caplog.records}

    def test_a_rewrite_of_another_wall_does_not_wake_this_one(self, wall_dir: Path):
        """The reason the decision names the mtime poll.

        A shared file would make every wall's display re-read and re-derive on
        every other wall's change, at a poll a second.
        """
        write_manifest(wall_dir, a_document(), wall_id=WALL_ID)
        watcher = a_watcher(wall_dir, WALL_ID)
        watcher.poll()

        for number in range(8, 12):
            write_manifest(wall_dir, _named(f"The study's theme {number}"), wall_id="study")

        assert watcher.poll() is None
        assert watcher.current is not None
        assert watcher.current.playlist_name == "A theme"


async def test_the_daemon_shows_its_own_walls_theme_and_ignores_another_walls(daemon, tv, publish):
    """End to end over the double: two walls' manifests on one client, one directory each.

    The living room's display is driven by the living room's document and by
    nothing else — the study's is present, newer, and names entirely different
    works, and none of them reach the television.
    """
    publish(["mine"], wall_id=WALL_ID)
    publish(["not-mine"], wall_id="study")

    await daemon.tick()

    assert publish.work_of(tv.on_the_wall) == "mine"
    assert [publish.work_of(tv.holding[content]) for content in tv.selected] == ["mine"]


async def test_a_daemon_whose_wall_has_no_manifest_shows_nothing_rather_than_someone_elses(daemon, tv, publish):
    """A manifest for an unknown wall is not acted on — it is not a fallback.

    A device pointed at a wall nothing has published for waits, exactly as it
    waits on a fresh install. Reaching for whatever manifest *is* there would
    turn a wall the server has not yet published for into a wall showing
    another room's pictures, which is the failure that has no symptom.
    """
    publish(["not-mine"], wall_id="study")

    await daemon.tick()

    assert tv.selected == []


# -- major 2: the rules a Player acts on that no contract fixture breaks ----------------


def _a_feed() -> dict:
    """The contract's scene-preview feed: a valid major 2 document to break one rule of."""
    return json.loads((CONTRACT / "fixtures" / "manifest.v2" / "valid" / "scene-preview.json").read_text(encoding="utf-8"))


def _parse_feed(document: dict):
    return parse(json.dumps(document))


def test_a_feed_with_an_instant_of_no_offset_is_refused():
    """A time with no offset is the one a Player could only guess the zone of (`player-contract.md` § Time)."""
    document = _a_feed()
    slot = document["schedule"]["slots"][0]
    slot["from"] = slot["from"].removesuffix("+00:00").removesuffix("Z")
    assert _parse_feed(_a_feed()) is not None, "the untouched fixture is not a valid feed"

    with pytest.raises(ManifestUnreadable, match="offset"):
        _parse_feed(document)


def test_a_scene_that_does_not_say_until_is_refused_and_one_held_with_null_is_not():
    """Null holds the scene until it is released; a missing `until` is a document that forgot to say."""
    held = _a_feed()
    held["scene"]["until"] = None
    assert _parse_feed(held).scene.until is None

    forgot = _a_feed()
    del forgot["scene"]["until"]
    with pytest.raises(ManifestUnreadable, match="until"):
        _parse_feed(forgot)


def test_this_player_asks_only_for_majors_it_can_read():
    """Asking for one it cannot read would fetch a document only to refuse it, on every poll."""
    assert REQUESTED_MAJORS
    assert set(REQUESTED_MAJORS) <= set(SUPPORTED_SCHEMA_MAJORS)
