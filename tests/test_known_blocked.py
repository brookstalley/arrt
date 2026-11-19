"""`.github/known-blocked.json`, the file itself: its shape, and that every row of it holds today.

The judge and the freshness check read the file through `known_blocked.py`; their
tests cover what they do with a row. This covers the rows that are actually in the
repository, because a row that names a renamed probe, or whose expiry was typed a
year out, excuses nothing or everything and nothing else would say so.

This reads `arrt/tests/live/` (the probes the rows name) from the repository root:
the server image's test stage carries only some repository-root files, and this is
a root governance test, which runs from a checkout, not from that image.
"""

import importlib.util
import json
import pathlib
import sys
from datetime import date, timedelta

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".github" / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("known_blocked", SCRIPTS / "known_blocked.py")
known_blocked = importlib.util.module_from_spec(spec)
spec.loader.exec_module(known_blocked)

#: The day the rows were written, from the owner's ruling. The real file is checked as of this
#: day, not today: a row that has since expired is the judge's finding, not a failing test.
WRITTEN = date(2026, 11, 19)


def test_the_rows_in_the_repository_all_hold_on_the_day_they_were_written():
    rows, problems = known_blocked.check(known_blocked.BLOCKED_FILE, WRITTEN)

    assert problems == []
    assert len(rows) == 6


def test_every_row_names_a_probe_that_exists_in_the_live_suite():
    document = json.loads(known_blocked.BLOCKED_FILE.read_text(encoding="utf-8"))
    live = ROOT / "arrt" / "tests" / "live"

    for row in document["blocked"]:
        file = row["test"].split("::")[0]
        assert (ROOT / "arrt" / file).parent == live, f"{row['test']} is not under arrt/tests/live"
        assert known_blocked.test_exists(ROOT / "arrt", row["test"]) is None, row["test"]


def test_no_row_is_more_than_sixty_days_past_the_day_it_was_written():
    """The plan's `[DECISION]`: an expiry no more than 60 days out, so blocked cannot become permanent."""
    rows, _ = known_blocked.check(known_blocked.BLOCKED_FILE, WRITTEN)

    assert known_blocked.MAX_DAYS == 60
    assert all(row.expires <= WRITTEN + timedelta(days=60) for row in rows)


def test_every_row_names_one_of_the_three_issues_the_ruling_covers():
    """#109 and #110 are the two red jobs. #150 is the OpenRouter job, whose probes skip, and a row excuses only red."""
    rows, _ = known_blocked.check(known_blocked.BLOCKED_FILE, WRITTEN)

    assert {row.issue for row in rows} == {109, 110}


def test_the_dezoomify_and_museum_rows_are_the_probes_the_2026_11_16_run_failed():
    """What the record shows red: three in each of the two free jobs, by the names in run 43902569784's log."""
    rows, _ = known_blocked.check(known_blocked.BLOCKED_FILE, WRITTEN)

    assert sorted(row.test.split("::")[1] for row in rows) == sorted(
        [
            "test_a_real_tiled_fetch_produces_a_readable_image",
            "test_the_staged_name_keeps_an_extension_the_binary_can_encode_to",
            "test_the_tile_cache_is_populated_when_the_directory_exists",
            "test_the_search_response_still_carries_the_masters_dimensions_not_the_previews",
            "test_every_iiif_response_is_still_843_pixels_wide",
            "test_the_resolved_image_service_is_really_a_iiif_endpoint",
        ]
    )


def test_a_reason_never_states_a_cause_the_record_does_not():
    """Where the cause is unestablished the reason says so, so a guess cannot get into the file unmarked."""
    rows, _ = known_blocked.check(known_blocked.BLOCKED_FILE, WRITTEN)

    for row in rows:
        assert "not established" in row.reason or "inference" in row.reason, row.test


# -- the refusals, one input each ----------------------------------------------------------------


@pytest.fixture
def tree(tmp_path):
    live = tmp_path / "arrt" / "tests" / "live"
    live.mkdir(parents=True)
    (live / "test_x.py").write_text("def test_a(): pass\n\nclass TestC:\n    def test_m(self): pass\n")
    return tmp_path / "arrt"


def _file(tmp_path, document) -> pathlib.Path:
    path = tmp_path / "known-blocked.json"
    path.write_text(document if isinstance(document, str) else json.dumps(document))
    return path


GOOD = {"test": "tests/live/test_x.py::test_a", "issue": 7, "expires": "2026-12-01", "reason": "why"}


def test_a_good_row_is_returned(tmp_path, tree):
    rows, problems = known_blocked.check(_file(tmp_path, {"blocked": [GOOD]}), WRITTEN, tree)

    assert problems == []
    assert rows[0].issue == 7 and rows[0].expires == date(2026, 12, 1)


@pytest.mark.parametrize(
    ("over", "words"),
    [
        ({"issue": "110"}, "has no issue"),
        ({"issue": True}, "has no issue"),
        ({"expires": "next month"}, "not a YYYY-MM-DD date"),
        ({"expires": None}, "not a YYYY-MM-DD date"),
        ({"expires": "2026-11-18"}, "expired on 2026-11-18"),
        ({"expires": "2027-01-19"}, "more than 60 days"),
        ({"test": "tests/live/test_x.py::test_b"}, "does not define"),
        ({"test": "tests/live/test_x.py::test_a[1]"}, "parametrization"),
        ({"test": "tests/live/test_x.py"}, "is not `<file>.py::<function>`"),
        ({"test": "tests/live/test_x.py::NoClass::test_m"}, "does not define"),
        ({"test": "../outside.py::test_a"}, "not a file under arrt/"),
        ({"surprise": 1}, "unknown field(s) surprise"),
        ({"reason": ""}, "empty reason"),
    ],
)
def test_a_refused_row_is_named_and_not_returned(tmp_path, tree, over, words):
    row = {**GOOD, **over}

    rows, problems = known_blocked.check(_file(tmp_path, {"blocked": [row]}), WRITTEN, tree)

    assert rows == []
    assert len(problems) == 1 and words in problems[0], problems
    assert problems[0].startswith(f"known-blocked {row['test']}:")


def test_a_class_method_row_is_found(tmp_path, tree):
    row = {**GOOD, "test": "tests/live/test_x.py::TestC::test_m"}

    assert known_blocked.check(_file(tmp_path, {"blocked": [row]}), WRITTEN, tree)[1] == []


def test_a_row_with_no_expiry_at_all_is_named(tmp_path, tree):
    row = {k: v for k, v in GOOD.items() if k != "expires"}

    assert "has no expires" in known_blocked.check(_file(tmp_path, {"blocked": [row]}), WRITTEN, tree)[1][0]


def test_a_probe_listed_twice_is_named(tmp_path, tree):
    problems = known_blocked.check(_file(tmp_path, {"blocked": [GOOD, GOOD]}), WRITTEN, tree)[1]

    assert any("is listed twice" in p for p in problems)


@pytest.mark.parametrize(
    ("document", "words"),
    [("{not json", "is not JSON"), ({"rows": []}, 'must be an object with a "blocked" list'), ([GOOD], "must be an object")],
)
def test_a_file_that_is_not_the_shape_is_one_problem(tmp_path, tree, document, words):
    rows, problems = known_blocked.check(_file(tmp_path, document), WRITTEN, tree)

    assert rows == [] and len(problems) == 1 and words in problems[0]


def test_a_missing_file_is_a_problem_not_an_empty_list(tmp_path, tree):
    """No file would otherwise read as 'nothing is blocked', which is a quiet success for a deleted file."""
    rows, problems = known_blocked.check(tmp_path / "known-blocked.json", WRITTEN, tree)

    assert rows == [] and "does not exist" in problems[0]
