"""A backup generation the real writer made, restored by the runbook's steps, and the server started on it.

`operational-spec.md` § Backup and Restore says a backup path never restored
from is a hope. This is the restore, run: the server process takes its
start-up generation, the household changes after it, the server stops (and, in
one case, a writer dies mid-transaction beside it, as a crash would leave the
file), the generation is put back by `restore`, the runbook's steps as code,
and the server is started on it. What it then answers over HTTP is read back:
the works, the themes, the walls and what hangs on each, and each wall's
published feed as its Player fetches it.

**Two places to restore to, so the steps are not tuned to one:** the same art
root, over a catalogue a crash left with a hot journal; and a new art root on
another machine, given the image tree and the generation and nothing else.
"""

import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

#: Where the generations are, beside nothing the art root holds.
GENERATIONS = "catalogue-*Z.sqlite"


def restore(backup_dir: Path, catalogue: Path) -> Path:
    """Put the newest generation back as the catalogue: the runbook's steps, with the server already stopped. Returns it.

    1. Take the newest generation, by name, which is its instant.
    2. Remove what SQLite keeps beside the catalogue (`-journal`, and a `-wal`
       and `-shm` if a hand or a later release left them). A journal a server
       left when it died mid-write is *hot*: the next open plays it into
       whatever file is at the catalogue's path, so a restored file opened beside
       one is silently rolled back to the dead server's last commit, which is
       the catalogue the restore was meant to replace.
    3. Copy the generation in beside the catalogue's path and rename it over
       the catalogue, so the path holds the old file or the whole generation.
    """
    newest = max(backup_dir.glob(GENERATIONS))
    for suffix in ("-journal", "-wal", "-shm"):
        catalogue.with_name(catalogue.name + suffix).unlink(missing_ok=True)
    staged = catalogue.with_name(catalogue.name + ".restoring")
    shutil.copyfile(newest, staged)
    staged.replace(catalogue)
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


def _household(base_url: str) -> dict:
    works = httpx.get(f"{base_url}/api/works", params={"limit": 100}).json()
    themes = httpx.get(f"{base_url}/api/themes").json()
    walls = httpx.get(f"{base_url}/api/walls").json()
    return {
        "works": sorted(work["title"] for work in works["works"]),
        "themes": sorted(entry["theme"]["name"] for entry in themes["themes"]),
        "hanging": {wall["name"]: (wall["theme"] or {}).get("name") for wall in walls["walls"]},
    }


@pytest.fixture
def household(services, ready_work, wall_id):
    """Two themes over three ready works, one hung on the wall, and the wall's Player with a token, before any start."""
    nighthawks = ready_work("Nighthawks", content_hash="hash-nighthawks")
    automat = ready_work("Automat", content_hash="hash-automat")
    sunday = ready_work("Early Sunday Morning", content_hash="hash-sunday")
    late = services.display.add_theme(name="Late night")
    mornings = services.display.add_theme(name="Mornings")
    for work in (nighthawks, automat):
        services.display.add_to_theme(theme_id=late.id, artwork_id=work.id)
    services.display.add_to_theme(theme_id=mornings.id, artwork_id=sunday.id)
    services.display.activate_theme(late.id, wall_id=wall_id)
    client = services.clients.add_client(name="The Pi in the hall")
    services.clients.assign_wall(wall_id, client_id=client.id, output="hdmi-a-1")
    token = services.access.issue(client.id).token
    return {
        "wall_id": wall_id,
        "token": token,
        "late": late.id,
        "mornings": mornings.id,
        "late_works": {nighthawks.id, automat.id},
        "sunday": sunday.id,
    }


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
    assert before["hanging"] == {"The wall": "Late night"}

    # After the backup: a theme the restore must lose, and another theme hung.
    created = httpx.post(f"{base_url}/api/themes", json={"name": "After the backup"})
    assert created.status_code == 200, created.text
    hung = httpx.post(f"{base_url}/api/themes/{household['mornings']}/activate", json={"wall_id": household["wall_id"]})
    assert hung.status_code == 200, hung.text
    assert set(_feed(base_url, household["wall_id"], household["token"])["works"]) == {household["sunday"]}
    arrt_process.stop()

    if where.startswith("in place"):
        # A writer that dies mid-transaction, as a server killed mid-write leaves the file.
        child = [sys.executable, "-c", _KILLED_MID_WRITE, str(catalogue)]
        subprocess.run(child, check=True)  # noqa: S603 -- this interpreter, running the fixed script above
        assert catalogue.with_name(catalogue.name + "-journal").exists(), "no journal was left to restore beside"
        target = catalogue
    else:
        # Another machine: the image tree from the art root's own snapshot, and nothing else of it.
        arrt_process.art_root = tmp_path_factory.mktemp("restored-root")
        for tree in (entry for entry in art_root.iterdir() if entry.is_dir()):
            shutil.copytree(tree, arrt_process.art_root / tree.name)
        target = arrt_process.art_root / catalogue.name

    restored_from = restore(backups, target)

    base_url = arrt_process.start()
    assert _household(base_url) == before
    feed = _feed(base_url, household["wall_id"], household["token"])
    assert feed["playlist"]["id"] == household["late"]
    assert set(feed["works"]) == household["late_works"]
    assert restored_from.exists(), "the generation restored from was pruned by the restored server's start"


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
