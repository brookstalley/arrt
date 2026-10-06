"""The picture store: its key, its tiers, what it keeps and refuses, and that it never forgets.

The owner's norm (`data-model.md` § Direction, 2026-10-06) is that a picture
fetched from outside is kept forever and an ask of 2,048 px or less is answered
from it, never from the source again. So the cases that matter are the ones that
would quietly break that: two spellings of one URL fetched twice, two works
answered with one picture, a small source refused a large ask, a bomb written to
disk, a half-written file served, and anything deleted.
"""

import logging
import threading
from io import BytesIO

import pytest
from PIL import Image

from arrt.library.services.pictures import (
    TIERS,
    PictureRefused,
    PictureStore,
    _normalise,
    import_previews,
    picture_key,
)
from arrt.services.errors import ServiceError

URL = "https://api.artic.edu/api/v1/artworks/27992"
PREVIEW_URL = "https://www.artic.edu/iiif/2/b272df73-a965-ac37-4172-be4e99483637/full/843,/0/default.jpg"


def a_picture(width: int = 3000, height: int = 2000, *, fmt: str = "JPEG", mode: str = "RGB") -> bytes:
    buffer = BytesIO()
    colour = (90, 70, 140, 128) if mode == "RGBA" else (90, 70, 140)
    Image.new(mode, (width, height), colour).save(buffer, format=fmt)
    return buffer.getvalue()


class CountingSource:
    """A source that serves one picture and counts every ask, by provider and preview URL."""

    def __init__(self, payload: bytes | None = None, *, raises: Exception | None = None) -> None:
        self.payload = a_picture() if payload is None else payload
        self.raises = raises
        self.asked: list[tuple[str, str]] = []

    def fetch_preview(self, provider: str, url: str) -> bytes | None:
        self.asked.append((provider, url))
        if self.raises is not None:
            raise self.raises
        return self.payload


@pytest.fixture
def art_root(tmp_path):
    return tmp_path / "art"


def a_store(art_root, source=None) -> PictureStore:
    return PictureStore(art_root / "pictures", art_root=art_root, sources=source)


def long_edge(path) -> int:
    with Image.open(path) as image:
        return max(image.size)


def every_file(art_root) -> set:
    return {path for path in (art_root / "pictures").rglob("*") if path.is_file()}


# -- the key ----------------------------------------------------------------------


def test_two_spellings_of_one_url_are_one_key():
    """Case of scheme and host, a default port, query order and escape case are spelling, not identity."""
    assert picture_key("artic", "HTTPS://API.Artic.EDU:443/api/v1/artworks/27992?b=2&a=1") == picture_key(
        "artic", "https://api.artic.edu/api/v1/artworks/27992?a=1&b=2"
    )
    assert _normalise("https://example.org/a%7eb/c%2fd") == "https://example.org/a~b/c%2Fd"
    assert _normalise("http://example.org:80") == "http://example.org/"
    assert _normalise("http://example.org:8080/x") == "http://example.org:8080/x"


def test_two_smk_collection_pages_are_two_keys_because_the_object_is_in_the_fragment():
    """`collection.smk.dk` names its object only after the `#` (`smk.py`).

    Dropping the fragment, as the plan first said, gives every such work one key,
    and the second work's card would be answered with the first work's painting.
    """
    first = picture_key("smk", "https://collection.smk.dk/#/en/detail/KMS8010")
    second = picture_key("smk", "https://collection.smk.dk/#/en/detail/KMS1")

    assert first != second
    # And one page in two spellings of its escapes is still one key, while an
    # encoded slash is not decoded into a different fragment.
    assert picture_key("smk", "https://collection.smk.dk/#/en/detail/KKS12485%2f6") == picture_key(
        "smk", "https://collection.smk.dk/#/en/detail/KKS12485%2F6"
    )
    assert _normalise("https://collection.smk.dk/#/en/detail/KKS12485%2F6").endswith("KKS12485%2F6")


def test_no_query_parameter_is_dropped():
    """SMK's API spelling carries the object in its query."""
    assert picture_key("smk", "https://api.smk.dk/api/v1/art?object_number=KMS1") != picture_key(
        "smk", "https://api.smk.dk/api/v1/art?object_number=KMS2"
    )


def test_the_provider_is_part_of_the_key():
    assert picture_key("artic", URL) != picture_key("met", URL)


# -- tiers --------------------------------------------------------------------------


def test_an_ask_is_answered_from_the_smallest_tier_at_or_above_it(art_root):
    store = a_store(art_root)
    store.put("artic", URL, a_picture(3000, 2000))

    assert long_edge(store.find_for("artic", URL, max_edge=400)) == 480
    assert long_edge(store.find_for("artic", URL, max_edge=480)) == 480
    assert long_edge(store.find_for("artic", URL, max_edge=481)) == 2048
    assert long_edge(store.find_for("artic", URL, max_edge=2048)) == 2048
    # Beyond the largest tier, and the source served more than it: not thumbnail size.
    assert store.find_for("artic", URL, max_edge=4000) is None


def test_a_source_smaller_than_a_tier_is_kept_at_its_own_size_and_answers_a_larger_ask(art_root):
    """Never enlarged; and a file smaller than its tier is all the source served."""
    store = a_store(art_root)
    largest = store.put("artic", URL, a_picture(843, 600))

    assert long_edge(largest) == 843
    assert long_edge(store.find_for("artic", URL, max_edge=480)) == 480
    assert store.find_for("artic", URL, max_edge=4000) == largest

    # A tiny source: with the larger tier gone, the smaller one is its full size.
    tiny = "https://api.artic.edu/api/v1/artworks/1"
    store.put("artic", tiny, a_picture(300, 200))
    (art_root / store.relative(store.find_for("artic", tiny, max_edge=2048))).unlink()
    assert long_edge(store.find_for("artic", tiny, max_edge=2048)) == 300


def test_an_unreadable_smaller_tier_is_never_taken_for_the_sources_full_size(art_root):
    """A file whose header will not read cannot prove it is smaller than its tier.

    With nothing at 2,048, a 480 file smaller than 480 would answer a larger
    ask. One that will not read must not: it is not served, and keeping the
    picture fetches it again rather than trusting the damaged file.
    """
    source = CountingSource(a_picture(843, 600))
    store = a_store(art_root, source)
    key_path = art_root / store.keep("artic", URL, PREVIEW_URL)
    small = store.find_for("artic", URL, max_edge=480)
    key_path.unlink()
    small.write_bytes(b"not a JPEG header at all")

    assert store.find_for("artic", URL, max_edge=2048) is None, "the damaged file was served for a larger ask"

    again = store.keep("artic", URL, PREVIEW_URL)

    assert len(source.asked) == 2, "the picture was fetched again"
    assert long_edge(art_root / again) == 843
    assert long_edge(store.find_for("artic", URL, max_edge=480)) == 480


def test_a_path_the_store_did_not_hand_out_finds_nothing(art_root):
    store = a_store(art_root)
    stored = store.relative(store.put("artic", URL, a_picture()))

    assert store.find(stored, max_edge=480) is not None
    assert store.key_of(stored) == picture_key("artic", URL)
    assert store.find("previews/0123.jpg", max_edge=480) is None
    # The right name in the wrong bucket is not the store's either.
    misplaced = stored.replace(f"/{stored.split('/')[1]}/", "/zz/")
    assert store.find(misplaced, max_edge=480) is None
    assert store.owns(misplaced)
    assert not store.owns("previews/0123.jpg")


# -- re-encoding --------------------------------------------------------------------


def test_every_kept_file_is_a_jpeg_whatever_the_source_served(art_root):
    store = a_store(art_root)
    store.put("artic", URL, a_picture(500, 400, fmt="PNG", mode="RGBA"))

    for tier in TIERS:
        path = store.find_for("artic", URL, max_edge=tier)
        with Image.open(path) as image:
            assert image.format == "JPEG"
            assert image.mode == "RGB"


def test_bytes_that_are_not_a_picture_are_refused_and_nothing_is_written(art_root):
    store = a_store(art_root)

    with pytest.raises(PictureRefused, match="could not be read"):
        store.put("artic", URL, b"<html>not a picture</html>")

    assert every_file(art_root) == set()


def test_a_decompression_bomb_is_refused_and_nothing_is_written(art_root, monkeypatch):
    """Pillow raises past twice its pixel limit; the limit is lowered so the bomb is small."""
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1_000)
    store = a_store(art_root)

    with pytest.raises(PictureRefused, match="too large to open safely"):
        store.put("artic", URL, a_picture(100, 100))

    assert every_file(art_root) == set()


# -- writing --------------------------------------------------------------------------


def test_a_kept_picture_lands_inside_art_root_at_a_relative_path(art_root):
    path = a_store(art_root, CountingSource()).keep("artic", URL, PREVIEW_URL)

    assert path is not None
    assert not path.startswith("/")
    assert path.startswith("pictures/")
    assert path.endswith(f".{TIERS[-1]}.jpg")
    assert (art_root / path).is_file()


def test_the_source_is_asked_for_the_preview_url_and_told_which_source_found_it(art_root):
    source = CountingSource()
    a_store(art_root, source).keep("commons", URL, PREVIEW_URL)

    assert source.asked == [("commons", PREVIEW_URL)]


def test_a_kept_picture_is_never_fetched_again_however_it_is_spelt(art_root):
    source = CountingSource()
    store = a_store(art_root, source)

    first = store.keep("artic", URL, PREVIEW_URL)
    second = store.keep("artic", URL.replace("https://api.artic.edu", "HTTPS://API.ARTIC.EDU:443"), PREVIEW_URL)

    assert first == second
    assert len(source.asked) == 1


def test_two_concurrent_asks_for_one_key_make_one_fetch(art_root):
    """The second ask waits for the first, then finds what it wrote."""
    entered, release = threading.Event(), threading.Event()
    asked: list[str] = []

    class SlowSource:
        def fetch_preview(self, provider: str, url: str) -> bytes:
            asked.append(url)
            entered.set()
            release.wait(5)
            return a_picture(800, 600)

    store = a_store(art_root, SlowSource())
    answers: list[str | None] = []
    first = threading.Thread(target=lambda: answers.append(store.keep("artic", URL, PREVIEW_URL)))
    first.start()
    assert entered.wait(5)
    second = threading.Thread(target=lambda: answers.append(store.keep("artic", URL, PREVIEW_URL)))
    second.start()
    # Without the per-key lock the second ask reaches the source within this wait.
    second.join(0.2)
    release.set()
    first.join(5)
    second.join(5)

    assert len(asked) == 1
    assert len(answers) == 2
    assert answers[0] == answers[1] is not None


def test_nothing_temporary_is_left_after_a_write(art_root):
    a_store(art_root, CountingSource()).keep("artic", URL, PREVIEW_URL)

    assert [path for path in every_file(art_root) if path.name.endswith(".tmp")] == []
    assert len(every_file(art_root)) == len(TIERS)


def test_a_rename_that_fails_leaves_no_temporary_file_and_no_picture(art_root, monkeypatch):
    def explode(self, _target):
        raise OSError("no space left on device")

    monkeypatch.setattr("pathlib.Path.replace", explode)

    assert a_store(art_root, CountingSource()).keep("artic", URL, PREVIEW_URL) is None
    assert every_file(art_root) == set()


def test_an_empty_largest_tier_is_not_a_kept_picture(art_root):
    """A zero-byte file is fetched again rather than served as a picture forever."""
    source = CountingSource()
    store = a_store(art_root, source)
    path = store.keep("artic", URL, PREVIEW_URL)
    (art_root / path).write_bytes(b"")

    again = store.keep("artic", URL, PREVIEW_URL)

    assert again == path
    assert (art_root / path).stat().st_size > 0
    assert len(source.asked) == 2


# -- never raises -------------------------------------------------------------------
#
# A picture is a card's, never a run's: every way `keep` can fail returns `None`
# with its own reason, because a run that found its images must not die over one.


def test_a_source_that_returns_nothing_is_absence_and_no_file(art_root):
    source = CountingSource()
    source.payload = b""
    assert a_store(art_root, source).keep("artic", URL, PREVIEW_URL) is None
    assert every_file(art_root) == set()


def test_a_source_raising_past_its_contract_is_absorbed(art_root):
    """`httpx.InvalidURL` is not an `HTTPError`, so the seam's `None` is not enough."""
    assert a_store(art_root, CountingSource(raises=ValueError("not a valid URL"))).keep("artic", URL, PREVIEW_URL) is None


def test_a_source_raising_oserror_is_reported_as_the_source_not_the_store(art_root, caplog):
    """The two `OSError`s are different diagnoses: the network's, and this disk's."""
    with caplog.at_level(logging.INFO):
        assert a_store(art_root, CountingSource(raises=OSError("connection reset"))).keep("artic", URL, PREVIEW_URL) is None

    reasons = [record.reason for record in caplog.records if hasattr(record, "reason")]
    assert any("the provider raised" in reason for reason in reasons)
    assert not any("the store could not be read" in reason for reason in reasons)


def test_an_unreadable_store_degrades_the_card_rather_than_failing_the_run(art_root, monkeypatch, caplog):
    def explode(self, *args, **kwargs):
        raise PermissionError("permission denied")

    monkeypatch.setattr("pathlib.Path.stat", explode)
    source = CountingSource()

    with caplog.at_level(logging.INFO):
        assert a_store(art_root, source).keep("artic", URL, PREVIEW_URL) is None

    assert source.asked == [], "a store it cannot read is not a reason to ask the museum"
    assert any("the store could not be read" in getattr(record, "reason", "") for record in caplog.records)


def test_bytes_that_cannot_be_written_degrade_the_card_rather_than_failing_the_run(art_root, monkeypatch):
    def explode(self, _data):
        raise OSError("no space left on device")

    monkeypatch.setattr("pathlib.Path.write_bytes", explode)

    assert a_store(art_root, CountingSource()).keep("artic", URL, PREVIEW_URL) is None


def test_a_preview_that_is_not_a_picture_is_absence(art_root):
    assert a_store(art_root, CountingSource(b"\xff\xd8\xff\xe0 not really")).keep("artic", URL, PREVIEW_URL) is None
    assert every_file(art_root) == set()


def test_a_store_with_no_source_answers_from_what_it_keeps_and_fetches_nothing(art_root):
    a_store(art_root).put("artic", URL, a_picture())

    assert a_store(art_root).keep("artic", URL, PREVIEW_URL) is not None
    assert a_store(art_root).keep("artic", URL + "/other", PREVIEW_URL) is None


def test_a_store_outside_the_art_tree_is_refused_at_wiring_time(tmp_path):
    with pytest.raises(ServiceError, match="must sit inside ART_ROOT"):
        PictureStore(tmp_path / "elsewhere", art_root=tmp_path / "art")


def test_pictures_are_kept_apart_from_thumbnails_and_the_old_previews(settings):
    assert settings.pictures_path.is_relative_to(settings.art_root)
    assert len({settings.pictures_path, settings.thumbnails_path, settings.previews_path}) == 3


# -- deletion: temporary files at startup, and nothing else -----------------------------


def test_startup_cleaning_removes_temporary_files_only(art_root):
    store = a_store(art_root, CountingSource())
    kept = art_root / store.keep("artic", URL, PREVIEW_URL)
    stray = kept.with_name(f"{kept.name}.0123abcd.tmp")
    stray.write_bytes(b"half a picture")
    other = kept.parent / "notes.txt"
    other.write_bytes(b"not the store's to judge")

    assert store.clean() == 1

    assert not stray.exists()
    assert kept.exists()
    assert other.exists()
    assert len(every_file(art_root)) == len(TIERS) + 1


def test_nothing_the_store_does_deletes_a_picture(art_root, discovery, propose, add_image):
    """Keep, keep again, put again, clean, and import: every picture written is still there."""
    source = CountingSource()
    store = a_store(art_root, source)
    store.keep("artic", URL, PREVIEW_URL)
    store.keep("artic", URL, PREVIEW_URL)
    store.put("artic", URL + "/2", a_picture(400, 300))
    written = every_file(art_root)

    store.put("artic", URL + "/2", a_picture(600, 300))
    store.clean()
    store.find_for("artic", URL, max_edge=4000)
    add_image(propose(), url=URL, preview_path="previews/gone.jpg")
    import_previews(store, discovery, legacy=art_root / "previews")

    assert written <= every_file(art_root)


# -- the import of `previews/` ----------------------------------------------------------


@pytest.fixture
def legacy(settings):
    directory = settings.art_root / "previews"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


@pytest.fixture
def picture_store(settings) -> PictureStore:
    return PictureStore(settings.pictures_path, art_root=settings.art_root)


def test_the_import_moves_named_files_in_leaves_unnamed_ones_and_reports_counts(
    picture_store, discovery, propose, add_image, legacy, caplog
):
    (legacy / "named.jpg").write_bytes(a_picture(843, 600))
    (legacy / "unnamed.jpg").write_bytes(a_picture(843, 600))
    (legacy / "not-a-picture.jpg").write_bytes(b"<html>")
    named = add_image(propose("Named"), url="https://museum.example/named", preview_path="previews/named.jpg")
    gone = add_image(propose("Gone"), url="https://museum.example/gone", preview_path="previews/gone.jpg")
    junk = add_image(propose("Junk"), url="https://museum.example/junk", preview_path="previews/not-a-picture.jpg")
    elsewhere = add_image(propose("Never cached"), url="https://museum.example/none")

    with caplog.at_level(logging.INFO):
        report = import_previews(picture_store, discovery, legacy=legacy)

    assert (report.imported, report.missing, report.refused, report.failed, report.unnamed) == (1, 1, 1, 0, 1)
    assert report.done
    moved = discovery.get_candidate_image(named.id).preview_path
    assert moved == picture_store.relative(picture_store.find_for("artic", "https://museum.example/named", max_edge=2048))
    assert picture_store.find(moved, max_edge=480) is not None
    # Rows the import could not serve are left exactly as they were.
    assert discovery.get_candidate_image(gone.id).preview_path == "previews/gone.jpg"
    assert discovery.get_candidate_image(junk.id).preview_path == "previews/not-a-picture.jpg"
    assert discovery.get_candidate_image(elsewhere.id).preview_path is None
    # Nothing in the old directory is touched.
    assert {path.name for path in legacy.iterdir()} == {"named.jpg", "unnamed.jpg", "not-a-picture.jpg"}
    (line,) = [record for record in caplog.records if getattr(record, "event", None) == "pictures.imported"]
    assert (line.imported, line.missing, line.refused, line.failed, line.unnamed, line.done) == (1, 1, 1, 0, 1, True)


def test_the_import_is_idempotent_and_a_rerun_with_a_new_row_imports_only_it(
    picture_store, discovery, propose, add_image, legacy
):
    (legacy / "one.jpg").write_bytes(a_picture(843, 600))
    first = add_image(propose("One"), url="https://museum.example/one", preview_path="previews/one.jpg")
    import_previews(picture_store, discovery, legacy=legacy)
    files = every_file(picture_store.art_root)
    moved = discovery.get_candidate_image(first.id).preview_path

    again = import_previews(picture_store, discovery, legacy=legacy)

    assert (again.imported, again.unnamed) == (0, 1), "the row moved, so its old file is now unnamed"
    assert discovery.get_candidate_image(first.id).preview_path == moved
    assert every_file(picture_store.art_root) == files

    # A second row naming the same old file, under the same picture, is
    # repointed without the file being read again.
    (legacy / "one.jpg").write_bytes(b"changed since, and no longer a picture")
    second = add_image(propose("One again"), url="https://museum.example/one", preview_path="previews/one.jpg")
    third = import_previews(picture_store, discovery, legacy=legacy)

    assert (third.imported, third.refused) == (1, 0)
    assert discovery.get_candidate_image(second.id).preview_path == moved


def test_the_import_repoints_a_decided_works_row_too(picture_store, discovery, propose, add_image, legacy):
    """Retroactive: every preview a row names is kept, whatever became of its work."""
    from arrt.persistence.discovery_records import Verdict

    (legacy / "decided.jpg").write_bytes(a_picture(843, 600))
    work = propose("Decided")
    image = add_image(work, url="https://museum.example/decided", preview_path="previews/decided.jpg")
    discovery.set_verdict(work.id, Verdict.REJECTED)

    assert import_previews(picture_store, discovery, legacy=legacy).imported == 1
    assert picture_store.owns(discovery.get_candidate_image(image.id).preview_path)


def test_the_container_cleans_and_imports_when_the_plane_starts(services, propose, add_image, settings):
    """`reconcile` is the one call a process start makes; the import has to be inside it."""
    legacy = settings.art_root / "previews"
    legacy.mkdir(parents=True, exist_ok=True)
    (legacy / "memory.jpg").write_bytes(a_picture(843, 600))
    image = add_image(propose(), url="https://museum.example/memory", preview_path="previews/memory.jpg")
    stray = settings.pictures_path / "ab" / "stray.jpg.0000.tmp"
    stray.parent.mkdir(parents=True)
    stray.write_bytes(b"half")

    services.reconcile()

    assert services.pictures.owns(services.discovery.get_candidate_image(image.id).preview_path)
    assert not stray.exists()


# -- the health panel's count -------------------------------------------------------


def test_the_size_counts_every_tier_file_and_its_bytes_and_no_temporary_file(art_root):
    store = a_store(art_root)
    store.put("artic", URL, a_picture(843, 600))
    store.put("artic", URL + "/2", a_picture(300, 200))
    stray = next((art_root / "pictures").rglob("*.jpg"))
    stray.with_name(f"{stray.name}.0123.tmp").write_bytes(b"x" * 1000)
    kept = [path for path in every_file(art_root) if path.suffix == ".jpg"]

    size = store.size()

    assert size.pictures_files == 2 * len(TIERS) == len(kept)
    assert size.pictures_bytes == sum(path.stat().st_size for path in kept)


def test_an_empty_or_absent_store_counts_nothing(art_root):
    size = a_store(art_root).size()

    assert (size.pictures_files, size.pictures_bytes) == (0, 0)


def test_one_walk_answers_for_ten_minutes_and_then_the_store_is_walked_again(art_root):
    """The store has no ceiling, so the walk is reused; the reading's time is the walk's, not the ask's."""
    from datetime import UTC, datetime, timedelta

    clock = [datetime(2026, 10, 6, 12, 0, tzinfo=UTC)]
    store = PictureStore(art_root / "pictures", art_root=art_root, now=lambda: clock[0])
    store.put("artic", URL, a_picture())
    first = store.size()

    store.put("artic", URL + "/2", a_picture())
    clock[0] += timedelta(minutes=9, seconds=59)
    assert store.size() == first, "a walk under ten minutes old answers again"

    clock[0] += timedelta(seconds=1)
    walked = store.size()
    assert walked.pictures_files == first.pictures_files + len(TIERS)
    assert walked.measured_at == clock[0]
