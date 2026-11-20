"""A backup generation the real writer made, restored by the runbook's steps, and the server started on it.

`operational-spec.md` § Backup and Restore says a backup path never restored
from is a hope. This is the restore, run: the server process takes its
start-up generation, the household changes after it, the server stops (and, in
one case, a writer dies mid-transaction beside it, as a crash would leave the
file), the generation is put back by `restore`, the runbook's steps as code,
and the server is started on it. What it then answers over HTTP is compared
with what it answered when the generation was taken, **the household whole**:
every work and its record, every theme and the works it holds in order, every
wall with what hangs on it, its client, output, labels and pace, and every
client; and each wall's published feed as its Player fetches it, with the token
issued before the backup.

**Two places to restore to, so the steps are not tuned to one:** the same art
root, over a catalogue a crash left with a hot journal; and a new art root on
another machine, given the image tree's three directories and the generation and
nothing else.

**What a restore puts back, and what it deliberately does not.** Back: the
catalogue (the newest generation), and from the art root's own snapshot the image
tree the catalogue's rows point into, `raw/` (the originals), `presentation/`
(the masters a feed sends) and `thumbs/`. Not: anything the server makes again
by itself, each wall's feed and heartbeat (republished at start, reported again
by the Player), `kept-answers.sqlite`, `tile-cache/`, `sources/`; and not
`pictures/`, which the owner's ruling of 2026-10-06 leaves out of the backup and
a restore without which is a degraded review surface, not a loss
(`operational-spec.md` § Backup and Restore). **And it restores within a
catalogue shape generation**: the generation put back records the shape
generation of the release that took it, and a release opens a file at its own
generation or a lower one (`arrt.persistence.file`); a restore across a raised
generation is the older image's, by the same steps, and is not this test's.
"""

import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from arrt.config import ORIGINALS_DIRNAME, PICTURES_DIRNAME, SOURCE_DATA_DIRNAME, THUMBNAILS_DIRNAME
from arrt.library.acquisition.master import MASTERS_DIRNAME
from arrt.persistence import backup, file
from arrt.persistence.records import RenditionKind
from arrt.programming.manifest.v2 import manifest_v2_path_in

#: Where the generations are, beside nothing the art root holds: the name `backup` writes them under.
GENERATIONS = "catalogue-*Z.sqlite"
#: The image tree a restore puts back, by the names the server reads them under.
IMAGE_TREE = (ORIGINALS_DIRNAME, MASTERS_DIRNAME, THUMBNAILS_DIRNAME)
#: Under the art root, and deliberately not restored (the module docstring says why).
NOT_RESTORED = (PICTURES_DIRNAME, SOURCE_DATA_DIRNAME)


def test_the_generations_are_found_by_the_name_the_writer_gives_them():
    assert GENERATIONS == backup._GENERATION_GLOB


def restore(backup_dir: Path, catalogue: Path, *, image_tree_from: Path | None = None) -> Path:
    """Put the newest generation back as the catalogue: the runbook's steps, with the server already stopped. Returns it.

    1. (The server is stopped: the caller's step.)
    2. Remove what SQLite keeps beside the catalogue (`-journal`, and a `-wal`
       and `-shm` if a hand or a later release left them). A journal a server
       left when it died mid-write is *hot*: the next open plays it into
       whatever file is at the catalogue's path, so a restored file opened beside
       one is silently rolled back to the dead server's last commit, which is
       the catalogue the restore was meant to replace.
    3. Take the newest generation, by name, which is its instant; copy it in
       beside the catalogue's path and rename it over the catalogue, so the path
       holds the old file or the whole generation.
    4. Put back `raw/`, `presentation/` and `thumbs/` from the snapshot at
       `image_tree_from`, when the art root is a new one; in place they are
       already there.
    5. (Start: the caller's step.)
    """
    for suffix in ("-journal", "-wal", "-shm"):
        catalogue.with_name(catalogue.name + suffix).unlink(missing_ok=True)
    newest = max(backup_dir.glob(GENERATIONS))
    staged = catalogue.with_name(catalogue.name + ".restoring")
    shutil.copyfile(newest, staged)
    staged.replace(catalogue)
    if image_tree_from is not None:
        for tree in IMAGE_TREE:
            if (image_tree_from / tree).is_dir():
                shutil.copytree(image_tree_from / tree, catalogue.parent / tree)
    return newest


_KILLED_MID_WRITE = """
import os, sqlite3, sys
connection = sqlite3.connect(sys.argv[1])
connection.execute("PRAGMA cache_size = 1")
connection.execute("BEGIN")
connection.execute("UPDATE themes SET name = name || ' (half written)'")
connection.execute("CREATE TABLE ballast (x)")
connection.executemany("INSERT INTO ballast VALUES (?)", [(str(i) * 50,) for i in range(5000)])
os._exit(0)
"""


def _wait_for(condition, what: str, seconds: float = 30.0) -> None:
    deadline = time.monotonic() + seconds
    while not condition():
        if time.monotonic() > deadline:
            pytest.fail(f"{what} did not happen within {seconds:.0f} s")
        time.sleep(0.1)


def _feed(base_url: str, wall_id: str, token: str) -> dict:
    response = httpx.get(f"{base_url}/walls/{wall_id}/manifest/v2", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, f"the wall's feed answered {response.status_code}: {response.text}"
    return response.json()


def _get(base_url: str, path: str, **params) -> dict:
    response = httpx.get(f"{base_url}/api{path}", params=params)
    assert response.status_code == 200, f"{path} answered {response.status_code}: {response.text}"
    return response.json()


#: What a wall's record holds that the household set, as against what the server
#: observes or schedules from the clock (its screen's state, what plays next).
_WALL_FIELDS = ("wall_id", "name", "created_at", "client_id", "output", "display_id", "labels", "mat_mode")
_WALL_PACE = ("rotation_interval_seconds", "shuffle", "tallest", "widest")


def _household(base_url: str) -> dict:
    """Everything the household set, as the server answers it."""
    works = _get(base_url, "/works", limit=100)["works"]
    themes = _get(base_url, "/themes")["themes"]
    walls = _get(base_url, "/walls")["walls"]
    clients = _get(base_url, "/clients")["clients"]
    return {
        "works": sorted(works, key=lambda work: work["artwork_id"]),
        "themes": {
            entry["theme"]["theme_id"]: {
                "theme": entry["theme"],
                "hanging_on": sorted(wall["wall_id"] for wall in entry["hanging_on"]),
                "works": [work["artwork_id"] for work in _get(base_url, f"/themes/{entry['theme']['theme_id']}")["works"]],
            }
            for entry in themes
        },
        "walls": {
            wall["wall_id"]: {
                **{key: wall[key] for key in (*_WALL_FIELDS, *_WALL_PACE)},
                "theme": (wall["theme"] or {}).get("theme_id"),
            }
            for wall in walls
        },
        "clients": sorted(
            ({key: client[key] for key in ("client_id", "name")} for client in clients), key=lambda c: c["client_id"]
        ),
    }


@pytest.fixture
def mastered(services, service, ready_work, settings, decodable_jpeg):
    """A ready work, its master under `presentation/` and its original a file under `raw/`, as acquisition leaves them."""

    def make(title: str, colour: tuple[int, int, int]):
        work = ready_work(title, content_hash=f"hash-{title}", master=False)
        (settings.art_root / ORIGINALS_DIRNAME).mkdir(exist_ok=True)
        (settings.art_root / ORIGINALS_DIRNAME / f"{work.id}.tif").write_bytes(title.encode())
        path = f"{MASTERS_DIRNAME}/{work.id}.jpg"
        decodable_jpeg(settings.art_root / path, width=400, height=300, color=colour)
        service.record_rendition(
            artwork_id=work.id,
            kind=RenditionKind.PRESENTATION_MASTER,
            target_width=7680,
            target_height=7680,
            path=path,
        )
        return work

    return make


@pytest.fixture
def household(services, mastered, wall_id, settings):
    """Two themes over three ready works, one hung on the wall, the wall's Player with a token and a label, before any start."""
    nighthawks = mastered("Nighthawks", (160, 40, 40))
    automat = mastered("Automat", (40, 120, 160))
    sunday = mastered("Early Sunday Morning", (200, 180, 60))
    late = services.display.add_theme(name="Late night")
    mornings = services.display.add_theme(name="Mornings")
    for work in (nighthawks, automat):
        services.display.add_to_theme(theme_id=late.id, artwork_id=work.id)
    services.display.add_to_theme(theme_id=mornings.id, artwork_id=sunday.id)
    services.display.activate_theme(late.id, wall_id=wall_id)
    services.display.set_playback(wall_id, rotation_interval_seconds=3600)
    client = services.clients.add_client(name="The Pi in the hall")
    services.clients.assign_wall(wall_id, client_id=client.id, output="hdmi-a-1")
    token = services.access.issue(client.id).token
    # What a restore leaves out, so that leaving it out is seen to cost nothing the server needs.
    for tree in NOT_RESTORED:
        (settings.art_root / tree).mkdir(exist_ok=True)
        (settings.art_root / tree / "kept.bin").write_bytes(b"not restored")
    return {
        "wall_id": wall_id,
        "token": token,
        "late": late.id,
        "mornings": mornings.id,
        "late_works": {nighthawks.id, automat.id},
        "sunday": sunday.id,
    }


def _recorded_generation(catalogue: Path) -> int | None:
    connection = sqlite3.connect(f"file:{catalogue}?mode=ro", uri=True)
    try:
        return connection.execute("SELECT schema_generation FROM catalogue_opened").fetchone()[0]
    finally:
        connection.close()


@pytest.mark.uncacheable("starts the server as a process twice and kills a writer mid-transaction")
@pytest.mark.parametrize("where", ["in place, over a crashed catalogue", "on a new art root"])
def test_a_generation_restored_by_the_runbook_s_steps_serves_the_household_as_it_was(
    tmp_path_factory, settings, household, arrt_process, where
):
    art_root = settings.art_root
    catalogue = settings.catalogue_path
    backups = tmp_path_factory.mktemp("backups")
    arrt_process.environment = {"BACKUP_DIR": str(backups)}

    # The server takes its start-up generation of the household as seeded.
    base_url = arrt_process.start()
    _wait_for(lambda: any(backups.glob(GENERATIONS)), "the start-up backup")
    before = _household(base_url)
    assert before["walls"][household["wall_id"]]["theme"] == household["late"]
    assert before["themes"][household["mornings"]]["works"] == [household["sunday"]]

    # After the backup: a theme the restore must lose, a work joining a theme, and another theme hung.
    created = httpx.post(f"{base_url}/api/themes", json={"name": "After the backup"})
    assert created.status_code == 200, created.text
    joined = httpx.post(
        f"{base_url}/api/themes/{household['mornings']}/works", json={"artwork_id": next(iter(household["late_works"]))}
    )
    assert joined.status_code == 200, joined.text
    hung = httpx.post(f"{base_url}/api/themes/{household['mornings']}/activate", json={"wall_id": household["wall_id"]})
    assert hung.status_code == 200, hung.text
    assert household["sunday"] in _feed(base_url, household["wall_id"], household["token"])["works"]
    assert _household(base_url) != before, "nothing changed after the backup, so the comparison below says nothing"
    arrt_process.stop()

    if where.startswith("in place"):
        # A writer that dies mid-transaction, as a server killed mid-write leaves the file.
        child = [sys.executable, "-c", _KILLED_MID_WRITE, str(catalogue)]
        subprocess.run(child, check=True)  # noqa: S603 -- this interpreter, running the fixed script above
        assert catalogue.with_name(catalogue.name + "-journal").exists(), "no journal was left to restore beside"
        restored_from = restore(backups, catalogue)
    else:
        # Another machine: the generation and the image tree from the art root's own snapshot, and nothing else of it.
        arrt_process.art_root = tmp_path_factory.mktemp("restored-root")
        restored_from = restore(backups, arrt_process.art_root / catalogue.name, image_tree_from=art_root)
        assert not [tree for tree in NOT_RESTORED if (arrt_process.art_root / tree).exists()]
        assert not list(arrt_process.art_root.glob("theme-manifest-*")), "a feed was carried to the new root"

    assert _recorded_generation(restored_from) == file.SCHEMA_GENERATION, "the generation is not of this release's shape"
    base_url = arrt_process.start()
    assert _household(base_url) == before
    feed = _feed(base_url, household["wall_id"], household["token"])
    assert feed["playlist"]["id"] == household["late"]
    assert set(feed["works"]) == household["late_works"]
    assert restored_from.exists(), "the generation restored from was pruned by the restored server's start"


@pytest.mark.uncacheable("starts the server as a process twice")
def test_a_feed_a_hang_wrote_after_the_backup_names_nothing_the_restored_catalogue_lacks(
    tmp_path_factory, settings, services, household, mastered, arrt_process
):
    """The feed is not restored, so the one on disk at start may name a work the generation never held; the start replaces it.

    Measured 2026-11-20: the start's reconcile republishes each wall's feed from
    the catalogue it opened, so the work added after the backup is gone from the
    feed both on disk and as the Player fetches it.
    """
    backups = tmp_path_factory.mktemp("backups")
    arrt_process.environment = {"BACKUP_DIR": str(backups)}
    arrt_process.start()
    _wait_for(lambda: any(backups.glob(GENERATIONS)), "the start-up backup")
    arrt_process.stop()

    # After the backup, and with the server stopped: a work the generation lacks joins the hung theme and is published.
    later = mastered("Room in New York", (90, 30, 120))
    services.display.add_to_theme(theme_id=household["late"], artwork_id=later.id)
    services.display.activate_theme(household["late"], wall_id=household["wall_id"])
    feed_on_disk = manifest_v2_path_in(settings.art_root, household["wall_id"])
    assert later.id in feed_on_disk.read_text(encoding="utf-8"), "the feed left beside the restore does not name the new work"

    restore(backups, settings.catalogue_path)
    base_url = arrt_process.start()

    assert set(_feed(base_url, household["wall_id"], household["token"])["works"]) == household["late_works"]
    assert later.id not in feed_on_disk.read_text(encoding="utf-8")


def test_a_restore_that_leaves_the_stale_journal_is_silently_undone(tmp_path):
    """Why step 2 is a step: measured on this interpreter's SQLite, the hot journal is played into the restored file.

    Integrity holds afterwards, so nothing reports it: the file opens as the dead
    server's last commit, not as the generation. If SQLite ever stops doing
    this, this fails, and the step can be reconsidered.
    """
    catalogue = tmp_path / "catalogue.sqlite"
    connection = sqlite3.connect(catalogue)
    connection.execute("CREATE TABLE themes (id INTEGER PRIMARY KEY, name TEXT)")
    connection.executemany("INSERT INTO themes (name) VALUES (?)", [(f"before {i}",) for i in range(200)])
    connection.commit()
    backups = tmp_path / "backups"
    backups.mkdir()
    connection.execute("VACUUM INTO ?", (str(backups / "catalogue-20261119T090000Z.sqlite"),))
    connection.execute("DELETE FROM themes")
    connection.executemany("INSERT INTO themes (name) VALUES (?)", [(f"after {i}",) for i in range(300)])
    connection.commit()
    connection.close()
    subprocess.run([sys.executable, "-c", _KILLED_MID_WRITE, str(catalogue)], check=True)  # noqa: S603 -- the fixed script above
    journal = catalogue.with_name(catalogue.name + "-journal")
    assert journal.exists()

    shutil.copyfile(max(backups.glob(GENERATIONS)), catalogue)  # the restore without step 2
    reopened = sqlite3.connect(catalogue)
    names = {name for (name,) in reopened.execute("SELECT name FROM themes")}
    verdict = reopened.execute("PRAGMA integrity_check").fetchone()[0]
    reopened.close()

    assert verdict == "ok"
    assert names == {f"after {i}" for i in range(300)}, "the journal was not played into the restored file"
