"""The drift job's verdict: which red probes excuse, which fail it, and what "nothing ran" is.

`judge_drift_probes.py` replaces pytest's exit code as the thing that fails a
drift-probe job. Driven here through `judge` and `main` with JUnit reports built in
the shape pytest wrote on 2026-11-16 (run 43902569784, the last whose log was read),
because every decision worth pinning is in how a report is read against
`.github/known-blocked.json`: a red and listed probe excuses, a red and unlisted one
fails, a green and listed one fails, and a probe that did not run is never excused.

Each test that asserts a failure names the input that trips it, and the mutation
that would break it is in the test's docstring where it is not obvious.
"""

import importlib.util
import json
import pathlib
import subprocess
import sys
from datetime import date

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".github" / "scripts"
TODAY = date(2026, 11, 19)

ARTIC = "tests/live/test_artic_shapes_are_still_real.py"
BAD = "test_the_resolved_image_service_is_really_a_iiif_endpoint"
GOOD = "test_a_held_work_still_comes_back_with_the_fields_an_instance_needs"
OTHER = "test_a_browse_still_returns_per_facet_buckets_with_their_own_works"


def _load(name: str):
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


judge_mod = _load("judge_drift_probes")


def _report(tmp_path, *cases: tuple[str, str, str]) -> pathlib.Path:
    """A JUnit file of (classname, name, outcome) cases; outcome is passed, failed, skipped, error or xfail."""
    body = []
    for classname, name, outcome in cases:
        inner = {
            "passed": "",
            "failed": '<failure message="assert False">trace</failure>',
            "error": '<error message="collection">trace</error>',
            "skipped": '<skipped type="pytest.skip" message="OPENROUTER_API_KEY is not set">x</skipped>',
            "xfail": '<skipped type="pytest.xfail" message="expected">x</skipped>',
        }[outcome]
        body.append(f'<testcase classname="{classname}" name="{name}">{inner}</testcase>')
    path = tmp_path / "results.xml"
    path.write_text(f'<?xml version="1.0"?><testsuites><testsuite name="pytest">{"".join(body)}</testsuite></testsuites>')
    return path


ARTIC_CLASS = "tests.live.test_artic_shapes_are_still_real"


@pytest.fixture
def tests_root(tmp_path):
    """A tests tree with just the probes the rows below name, so the existence check has something to find."""
    live = tmp_path / "arrt" / "tests" / "live"
    live.mkdir(parents=True)
    (live / "test_artic_shapes_are_still_real.py").write_text(
        f"def {BAD}(): pass\n\ndef {GOOD}(): pass\n\ndef {OTHER}(): pass\n\n"
        "class TestShapes:\n    def test_a_method(self): pass\n"
    )
    return tmp_path / "arrt"


def _blocked(tmp_path, *rows: dict) -> pathlib.Path:
    path = tmp_path / "known-blocked.json"
    path.write_text(json.dumps({"blocked": list(rows)}))
    return path


def _row(test: str = f"{ARTIC}::{BAD}", **over) -> dict:
    return {"test": test, "issue": 110, "expires": "2027-01-18", "reason": "403 from the museum, cause not established", **over}


def _judge(tmp_path, tests_root, report, rows, exit_code="1"):
    return judge_mod.judge(report, _blocked(tmp_path, *rows), exit_code, TODAY, tests_root)


def test_a_red_probe_that_is_listed_does_not_fail_the_job(tmp_path, tests_root):
    report = _report(tmp_path, (ARTIC_CLASS, GOOD, "passed"), (ARTIC_CLASS, BAD, "failed"))

    failures, excused, passed = _judge(tmp_path, tests_root, report, [_row()])

    assert failures == []
    assert [row.test for row in excused] == [f"{ARTIC}::{BAD}"]
    assert passed == 1


def test_a_red_probe_that_is_not_listed_fails_the_job_by_name(tmp_path, tests_root):
    """Trips on OTHER: red, in the same file as a listed probe, and not itself listed."""
    report = _report(tmp_path, (ARTIC_CLASS, GOOD, "passed"), (ARTIC_CLASS, BAD, "failed"), (ARTIC_CLASS, OTHER, "failed"))

    failures, excused, _ = _judge(tmp_path, tests_root, report, [_row()])

    assert len(failures) == 1
    assert f"{ARTIC}::{OTHER} is red and is not in .github/known-blocked.json" in failures[0]
    assert [row.test for row in excused] == [f"{ARTIC}::{BAD}"], "the listed one is still excused beside it"


def test_a_listed_probe_that_has_turned_green_fails_the_job_telling_the_reader_to_delete_the_row(tmp_path, tests_root):
    """The stale excuse: BAD passes while its row is still there."""
    report = _report(tmp_path, (ARTIC_CLASS, GOOD, "passed"), (ARTIC_CLASS, BAD, "passed"))

    failures, excused, _ = _judge(tmp_path, tests_root, report, [_row()], exit_code="0")

    assert len(failures) == 1
    assert f"{ARTIC}::{BAD}" in failures[0]
    assert "turned green" in failures[0]
    assert "Delete the row from .github/known-blocked.json" in failures[0]
    assert excused == []


def test_a_row_covers_every_case_of_a_parametrised_probe_and_is_stale_only_when_all_are_green(tmp_path, tests_root):
    some_red = _report(tmp_path, (ARTIC_CLASS, f"{BAD}[a]", "passed"), (ARTIC_CLASS, f"{BAD}[b]", "failed"))
    assert _judge(tmp_path, tests_root, some_red, [_row()])[0] == []

    all_green = _report(tmp_path, (ARTIC_CLASS, f"{BAD}[a]", "passed"), (ARTIC_CLASS, f"{BAD}[b]", "passed"))
    failures = _judge(tmp_path, tests_root, all_green, [_row()], exit_code="0")[0]
    assert any("turned green" in each for each in failures)


def test_a_method_in_a_class_is_named_with_its_class(tmp_path, tests_root):
    report = _report(tmp_path, (f"{ARTIC_CLASS}.TestShapes", "test_a_method", "failed"))
    row = _row(f"{ARTIC}::TestShapes::test_a_method")

    assert _judge(tmp_path, tests_root, report, [row])[0] == []
    assert _judge(tmp_path, tests_root, report, [])[0] != [], "and with no row the same report fails"


def test_a_listed_probe_that_skipped_is_not_excused_because_it_never_ran(tmp_path, tests_root):
    """A row excuses a red probe, never one that did not run: BAD skipped, and is listed."""
    report = _report(tmp_path, (ARTIC_CLASS, GOOD, "passed"), (ARTIC_CLASS, BAD, "skipped"))

    failures, excused, _ = _judge(tmp_path, tests_root, report, [_row()], exit_code="0")

    assert any(f"{ARTIC}::{BAD} skipped, so it did not run" in each for each in failures)
    assert excused == []


def test_a_run_in_which_nothing_ran_fails_even_though_every_probe_is_listed(tmp_path, tests_root):
    """The #150 shape: every probe skipped. Listing them all must not turn that green."""
    report = _report(tmp_path, (ARTIC_CLASS, BAD, "skipped"), (ARTIC_CLASS, GOOD, "skipped"))
    rows = [_row(), _row(f"{ARTIC}::{GOOD}")]

    failures = _judge(tmp_path, tests_root, report, rows, exit_code="0")[0]

    assert any("nothing ran" in each for each in failures)


def test_a_report_with_no_test_in_it_fails(tmp_path, tests_root):
    report = _report(tmp_path)

    failures = _judge(tmp_path, tests_root, report, [], exit_code="5")[0]

    assert any("holds no test" in each for each in failures)


def test_a_missing_report_fails_as_the_probes_not_having_run(tmp_path, tests_root):
    failures, excused, _ = _judge(tmp_path, tests_root, tmp_path / "absent.xml", [_row()])

    assert any("never produced a report" in each for each in failures)
    assert excused == []


def test_a_report_that_is_not_xml_fails(tmp_path, tests_root):
    garbage = tmp_path / "results.xml"
    garbage.write_text("not xml at all")

    assert any("not a readable JUnit report" in each for each in _judge(tmp_path, tests_root, garbage, [])[0])


@pytest.mark.parametrize("code", ["2", "3", "4", "5", "", "137"])
def test_a_pytest_that_did_not_exit_zero_or_one_fails_even_with_a_clean_report(tmp_path, tests_root, code):
    """An interrupted run or a usage error can leave a report that looks fine."""
    report = _report(tmp_path, (ARTIC_CLASS, GOOD, "passed"))

    failures = _judge(tmp_path, tests_root, report, [], exit_code=code)[0]

    assert any("only 0 (all passed) and 1" in each for each in failures)


def test_pytest_exiting_one_with_no_red_probe_in_the_report_fails(tmp_path, tests_root):
    report = _report(tmp_path, (ARTIC_CLASS, GOOD, "passed"))

    failures = _judge(tmp_path, tests_root, report, [], exit_code="1")[0]

    assert any("exited 1 but the report holds no failing probe" in each for each in failures)


def test_a_collection_error_is_red_and_unlisted(tmp_path, tests_root):
    """A probe module that no longer imports shows as an error with no module to name."""
    report = _report(tmp_path, ("", "tests.live.test_broken", "error"), (ARTIC_CLASS, GOOD, "passed"))

    failures = _judge(tmp_path, tests_root, report, [_row()])[0]

    assert any("tests.live.test_broken is red and is not in" in each for each in failures)


@pytest.mark.parametrize(
    ("over", "words"),
    [
        ({"issue": None}, "no issue"),
        ({"issue": 0}, "no issue"),
        ({"expires": "2027-01-19"}, "more than 60 days"),
        ({"expires": "2026-11-18"}, "expired on 2026-11-18"),
        ({"test": f"{ARTIC}::test_that_was_renamed_away"}, "does not define"),
        ({"test": "tests/live/test_gone.py::test_x"}, "not a file"),
        ({"reason": "  "}, "empty reason"),
    ],
)
def test_a_refused_row_fails_the_job_by_name_and_excuses_nothing(tmp_path, tests_root, over, words):
    """Each refusal in turn, with the probe the row meant to excuse red: it must fail twice, not once."""
    row = _row(**over)
    report = _report(tmp_path, (ARTIC_CLASS, BAD, "failed"), (ARTIC_CLASS, GOOD, "passed"))

    failures, excused, _ = _judge(tmp_path, tests_root, report, [row])

    named = row["test"]
    assert any(each.startswith(f"known-blocked {named}:") and words in each for each in failures), failures
    assert excused == [], "a refused row excuses nothing"


def test_a_row_with_no_issue_field_at_all_is_refused(tmp_path, tests_root):
    row = _row()
    del row["issue"]
    report = _report(tmp_path, (ARTIC_CLASS, BAD, "failed"))

    failures = _judge(tmp_path, tests_root, report, [row])[0]

    assert any("has no issue" in each for each in failures)


def test_a_row_expiring_today_still_excuses_and_one_sixty_days_out_is_the_limit(tmp_path, tests_root):
    report = _report(tmp_path, (ARTIC_CLASS, BAD, "failed"))

    assert _judge(tmp_path, tests_root, report, [_row(expires="2026-11-19")])[0] == []
    assert _judge(tmp_path, tests_root, report, [_row(expires="2027-01-18")])[0] == []
    assert _judge(tmp_path, tests_root, report, [_row(expires="2027-01-19")])[0] != []


# -- the CLI, against the real rows and the shape of the 2026-11-16 reports ------------------------


DEZOOMIFY = "tests.live.test_dezoomify_contract_still_holds"
RECORDED_DEZOOMIFY = [
    "test_a_real_tiled_fetch_produces_a_readable_image",
    "test_the_staged_name_keeps_an_extension_the_binary_can_encode_to",
    "test_the_tile_cache_is_populated_when_the_directory_exists",
]
RECORDED_MUSEUM_RED = [
    "test_the_search_response_still_carries_the_masters_dimensions_not_the_previews",
    "test_every_iiif_response_is_still_843_pixels_wide",
    "test_the_resolved_image_service_is_really_a_iiif_endpoint",
]


def _main(tmp_path, report, exit_code, contract, monkeypatch, now="2026-11-19"):
    summary = tmp_path / "summary.md"
    verdict = tmp_path / "verdict.json"
    summary.write_text("")
    env = {"GITHUB_STEP_SUMMARY": str(summary), "PATH": "/usr/bin:/bin"}
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "judge_drift_probes.py"), str(report), "--pytest-exit", exit_code,
         "--contract", contract, "--verdict", str(verdict), "--now", now],
        capture_output=True, text=True, env=env, check=False,
    )  # fmt: skip
    return result, summary.read_text(), json.loads(verdict.read_text()) if verdict.exists() else None


def test_the_recorded_museum_run_passes_with_the_real_rows_and_the_summary_says_which_and_until_when(tmp_path, monkeypatch):
    """Run 43902569784's museum job: 84 passed, the three Art Institute probes red."""
    report = _report(
        tmp_path,
        (ARTIC_CLASS, GOOD, "passed"),
        *[(ARTIC_CLASS, name, "failed") for name in RECORDED_MUSEUM_RED],
        ("tests.live.test_met_shapes_are_still_real", "test_a_search_still_finds_by_title_narrowed_to_the_artist", "passed"),
    )

    result, summary, verdict = _main(tmp_path, report, "1", "Museum APIs (free)", monkeypatch)

    assert result.returncode == 0, result.stdout
    for name in RECORDED_MUSEUM_RED:
        assert f"{ARTIC}::{name}`: #110, until 2027-01-18" in summary
    assert verdict["failures"] == []
    assert sorted(row["test"].split("::")[1] for row in verdict["excused"]) == sorted(RECORDED_MUSEUM_RED)


def test_the_recorded_binary_run_passes_with_the_real_rows(tmp_path, monkeypatch):
    report = _report(tmp_path, *[(DEZOOMIFY, name, "failed") for name in RECORDED_DEZOOMIFY])

    result, summary, _ = _main(tmp_path, report, "1", "dezoomify-rs (free)", monkeypatch)

    assert result.returncode == 0, result.stdout
    assert "#109, until 2027-01-18" in summary


def test_a_new_red_beside_the_recorded_ones_fails_and_the_error_annotation_names_it(tmp_path, monkeypatch):
    """The point of the whole file: a probe that moved today, among the six that were already red."""
    report = _report(
        tmp_path,
        *[(ARTIC_CLASS, name, "failed") for name in RECORDED_MUSEUM_RED],
        ("tests.live.test_met_shapes_are_still_real", "test_wikidata_still_names_the_met_object_for_the_item", "failed"),
    )

    result, summary, verdict = _main(tmp_path, report, "1", "Museum APIs (free)", monkeypatch)

    assert result.returncode == 1
    met = "tests/live/test_met_shapes_are_still_real.py::test_wikidata_still_names_the_met_object_for_the_item"
    assert f"::error::Museum APIs (free): {met} is red" in result.stdout
    assert len(verdict["failures"]) == 1
    assert "Failing this job" in summary


def test_the_real_rows_stop_excusing_on_the_day_they_expire(tmp_path, monkeypatch):
    report = _report(tmp_path, *[(ARTIC_CLASS, name, "failed") for name in RECORDED_MUSEUM_RED])

    result, _, _ = _main(tmp_path, report, "1", "Museum APIs (free)", monkeypatch, now="2027-01-19")

    assert result.returncode == 1
    assert "expired on 2027-01-18" in result.stdout


def test_called_without_the_pytest_exit_it_refuses_rather_than_assuming_success(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "judge_drift_probes.py"), str(tmp_path / "results.xml"), "--contract", "x"],
        capture_output=True, text=True, check=False,
    )  # fmt: skip

    assert result.returncode == 2


# -- the workflow wires it ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def drift():
    return yaml.safe_load((ROOT / ".github" / "workflows" / "api-drift.yml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("job", ["museum", "binary"])
def test_the_free_probe_jobs_record_pytests_exit_and_let_the_judge_decide(drift, job):
    """If the probe step still fails on a red test the judge never gets a say, and a listed red fails the job.

    Re-break: put `set -e` back (drop `set +e`) in the probe step and this fails.
    """
    steps = drift["jobs"][job]["steps"]
    probe = next(s for s in steps if s.get("id") == "probes")
    judge = next(s for s in steps if "judge_drift_probes.py" in s.get("run", ""))
    report = next(s for s in steps if "report_drift_failure.py" in s.get("run", ""))

    assert "set +e" in probe["run"] and 'echo "exit_code=$?" >> "$GITHUB_OUTPUT"' in probe["run"]
    assert "continue-on-error" not in probe
    assert judge["if"] == "always()", "a probe step that never ran must still be judged, as a failure"
    assert judge["env"]["PYTEST_EXIT"] == "${{ steps.probes.outputs.exit_code }}"
    assert '--pytest-exit "$PYTEST_EXIT"' in judge["run"]
    assert "--verdict" in judge["run"] and "--verdict" in report["run"]
    assert steps.index(probe) < steps.index(judge) < steps.index(report)


def test_the_paid_job_is_not_given_a_way_to_excuse_a_skip(drift):
    """#150's probes skip for want of a key: that is a job that verified nothing, which no row excuses."""
    steps = drift["jobs"]["openrouter"]["steps"]

    assert not any("judge_drift_probes" in s.get("run", "") for s in steps)
    assert any("assert_tests_ran.py" in s.get("run", "") for s in steps)
