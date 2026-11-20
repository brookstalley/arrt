"""The check that notices the drift probes have stopped running at all.

`assert_tests_ran.py` covers the run that happened and verified nothing. This
covers the run that never happened, which produces no report to inspect and no
skip to count — it is pure absence, and absence is indistinguishable from health
unless something goes looking.

Driven through `main` with hand-built run lists rather than against the GitHub
API, because every decision worth pinning is in how those lists are read: which
job counts for which tier, what a skipped job means, and where the boundary
between fresh and stale falls.
"""

import importlib.util
import json
import pathlib
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / ".github" / "scripts" / "check_drift_freshness.py"

NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)

MUSEUM = "Museum APIs (free)"
BINARY = "dezoomify-rs (free)"
PAID = "OpenRouter (spends money)"


def _load():
    """Import the script, which lives outside any package and has no importable name."""
    spec = importlib.util.spec_from_file_location("check_drift_freshness", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(days_ago: float, *jobs: tuple[str, str | None]) -> dict:
    """One workflow run, `days_ago` before NOW, carrying the given (job, conclusion) pairs."""
    when = NOW - timedelta(days=days_ago)
    return {
        "createdAt": when.isoformat().replace("+00:00", "Z"),
        "jobs": [{"name": name, "conclusion": conclusion} for name, conclusion in jobs],
    }


def test_both_tiers_running_on_time_passes():
    guard = _load()
    runs = [
        _run(2, (MUSEUM, "success"), (BINARY, "success")),
        _run(5, (PAID, "success")),
    ]

    assert guard.main(runs, NOW) == 0


def test_a_free_tier_that_has_never_run_fails(capsys):
    """The current state of this repo, and the first fault the check exists for.

    GitHub fires `schedule` only for workflows on the default branch, so a drift
    workflow sitting on an unmerged branch has run zero times. Nothing about that
    is visible anywhere: no red check, no absent artifact, just a workflow nobody
    has thought about since writing it.
    """
    guard = _load()

    assert guard.main([], NOW) == 1

    printed = capsys.readouterr().out
    assert "free API-drift probes have never completed" in printed
    assert "default branch" in printed, "the message must name the cause it is most likely to be"
    assert "Run workflow" in printed, "and the remedy, or it sends the reader nowhere"
    assert "free: leave" in printed, "the remedy must say it costs nothing, or nobody will run it"


def test_a_paid_tier_that_has_never_run_is_not_a_fault(capsys):
    """A check whose green costs money is a check that gets ignored.

    The first version failed on both tiers, so the job went red the moment it
    reached `main` and the only ways to clear it were to wait for the first of
    the month or to spend real credit on a manual dispatch. An ignored check
    takes the free tier's finding down with it, which is the whole value.

    An un-started clock is silent; staleness is measured once it has started.
    """
    guard = _load()
    runs = [_run(1, (MUSEUM, "success"))]

    assert guard.main(runs, NOW) == 0

    printed = capsys.readouterr().out
    assert "paid: has never run" in printed, "silent is not the same as unreported — it must still say so"


def test_the_free_tier_going_quiet_is_caught_while_the_paid_one_is_fine(capsys):
    """The reason the tiers are measured apart rather than together.

    A single age threshold over "the newest run" would read the healthy monthly
    run as evidence the weekly probes are fine. They are not: three Mondays have
    passed with nothing.
    """
    guard = _load()
    runs = [_run(3, (PAID, "success")), _run(30, (MUSEUM, "success"))]

    assert guard.main(runs, NOW) == 1

    printed = capsys.readouterr().out
    assert "free API-drift probes last succeeded 30 days ago" in printed
    assert "paid: last succeeded 3 days ago" in printed, "the healthy tier must still report, not go silent"


def test_a_paid_tier_long_unrun_is_said_and_is_not_a_fault(capsys):
    """Chunk 66: the paid probe runs only when a person dispatches it, so its age is no schedule that stopped.

    Until then it ran monthly and went red at 75 days; with the monthly cron gone
    (the owner's ruling of 2026-11-20, CI makes no paid call), that alarm could
    be cleared only by spending money, so its age is said and never measured.
    """
    guard = _load()
    runs = [_run(1, (MUSEUM, "success")), _run(90, (PAID, "success"))]

    assert guard.main(runs, NOW) == 0

    printed = capsys.readouterr().out
    assert "paid: last succeeded 90 days ago" in printed
    assert "runs only when dispatched by hand" in printed
    assert "::error::" not in printed


def test_either_free_job_alone_proves_the_schedule_is_alive():
    """A museum outage must not read as a dead schedule.

    The free tier has two jobs against two unrelated dependencies. Whether a
    *probe* failed is a different question with a louder answer — an issue filed
    by `report_drift_failure.py`. This file only asks whether the cron still
    fires, and one succeeding job answers that.
    """
    guard = _load()
    runs = [_run(1, (MUSEUM, "failure"), (BINARY, "success")), _run(1, (PAID, "success"))]

    assert guard.main(runs, NOW) == 0


@pytest.mark.parametrize("conclusion", ["skipped", "failure", "cancelled", None])
def test_a_run_whose_tier_job_did_not_succeed_does_not_refresh_that_tier(conclusion, capsys):
    """`skipped` is the normal state of the other tier's job in any given run.

    A weekly run skips the paid job and a monthly run skips the free ones, so a
    run's mere existence says nothing about which tier it refreshed. Counting one
    would let a healthy monthly cadence vouch indefinitely for free probes that
    stopped firing weeks ago.

    Asserted on the *free* tier, and that is the correction rather than the
    original design: written against the paid one, it stopped proving anything
    the moment a never-run paid tier became silent, because then the run returns
    zero whether the rule holds or not. The free tier has a real success behind
    it here, so only the recent non-success being miscounted could make this
    pass.
    """
    guard = _load()
    runs = [_run(1, (MUSEUM, conclusion)), _run(30, (MUSEUM, "success")), _run(1, (PAID, "success"))]

    assert guard.main(runs, NOW) == 1
    assert "free API-drift probes last succeeded 30 days ago" in capsys.readouterr().out


def test_the_boundary_is_inclusive_of_the_stated_limit():
    """Exactly at the limit is fresh; past it is not.

    Pinned because the two sides are one `>` apart and the stated number is the
    contract: "21 days" must mean a probe 21 days old still passes, or the
    documented interval is off by one from the enforced one.
    """
    guard = _load()

    at_limit = [_run(21, (MUSEUM, "success")), _run(1, (PAID, "success"))]
    assert guard.main(at_limit, NOW) == 0

    past_limit = [_run(21.5, (MUSEUM, "success")), _run(1, (PAID, "success"))]
    assert guard.main(past_limit, NOW) == 1


def test_the_thresholds_match_the_cadences_they_are_derived_from():
    """The numbers are reasoned from the crons, so the crons are where they are checked.

    Each threshold is "N missed runs of that tier". If somebody changes a cron
    without revisiting the threshold, the tier either nags on a healthy cadence
    or sleeps through several misses — and both are silent. Read from the workflow
    rather than restated here, so the two cannot drift apart.
    """
    guard = _load()
    workflow = (SCRIPT.parents[2] / ".github" / "workflows" / "api-drift.yml").read_text(encoding="utf-8")

    assert 'cron: "17 6 * * 1"' in workflow, "the free tier is no longer weekly — revisit STALE_AFTER['free']"
    # Chunk 66: the paid tier has no cron, so it has no threshold; it is BY_HAND.
    assert workflow.count("cron:") == 1, "a second schedule: say which tier it runs, and give it a threshold"
    assert set(guard.STALE_AFTER) == set(guard.TIER_JOBS) == {"free"}
    assert set(guard.BY_HAND) == {"paid"}

    assert guard.STALE_AFTER["free"] > timedelta(days=14), "a weekly probe must survive two ordinary misses"


def test_every_job_named_in_the_tier_map_exists_in_the_workflow():
    """Job names are the join key, and they are matched as strings.

    Renaming a job in `api-drift.yml` would silently make its tier read as
    never-run — the check would go red for a reason that has nothing to do with
    the schedule, and the message would send the operator to dispatch a workflow
    that is running perfectly well.
    """
    guard = _load()
    workflow = (SCRIPT.parents[2] / ".github" / "workflows" / "api-drift.yml").read_text(encoding="utf-8")

    for tier, names in (guard.TIER_JOBS | guard.BY_HAND).items():
        for name in names:
            assert f'name: "{name}"' in workflow, f"{tier} maps to a job named {name!r}, which no longer exists"


def test_the_entry_point_reads_stdin_and_exits_nonzero():
    """The workflow pipes `gh` output in and reads the exit code — so drive both.

    Every test above calls `main` directly, which leaves the argument parsing,
    the stdin read and the `SystemExit` untested; a script whose logic is perfect
    and whose entry point is broken fails the job for no reason anyone can see in
    the output. Run as a subprocess because that is what CI does.
    """
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--now", "2026-08-06T12:00:00Z"],
        input="[]",
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "never completed successfully" in result.stdout


def test_the_entry_point_exits_zero_on_a_healthy_pair():
    """The other half: a passing check must not fail the job."""
    runs = json.dumps([_run(2, (MUSEUM, "success")), _run(2, (PAID, "success"))])

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--now", "2026-08-06T12:00:00Z"],
        input=runs,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


# -- known-blocked rows: the file's age is this check's; a blocked run's freshness is the job's -------

BLOCKED = SCRIPT.parents[1] / "known-blocked.json"
WRITTEN = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


def _healthy_at(now: datetime) -> list[dict]:
    """Both free jobs and the paid one succeeding recently, as of `now`."""
    return [
        {
            "createdAt": (now - timedelta(days=2)).isoformat().replace("+00:00", "Z"),
            "jobs": [{"name": MUSEUM, "conclusion": "success"}, {"name": BINARY, "conclusion": "success"}],
        },
        {
            "createdAt": (now - timedelta(days=5)).isoformat().replace("+00:00", "Z"),
            "jobs": [{"name": PAID, "conclusion": "success"}],
        },
    ]


def test_a_tier_whose_only_failures_are_unexpired_known_blocked_probes_counts_fresh(capsys):
    """The judge ends such a job `success`, so the tier is fresh by the conclusion it carries.

    With the real file, unexpired as of the day it was written, the check passes and says what is excused.
    """
    guard = _load()

    assert guard.main(_healthy_at(WRITTEN), WRITTEN, BLOCKED) == 0

    printed = capsys.readouterr().out
    assert printed.count("known-blocked: tests/live/") == 6
    assert "(#110) is excused until 2027-01-18" in printed and "(#109) is excused until 2027-01-18" in printed


def test_an_expired_row_fails_the_check_naming_it_though_every_tier_is_fresh(capsys):
    """Trips on the file alone: both tiers ran on time and succeeded; only the day after the expiry differs."""
    guard = _load()
    after = datetime(2027, 1, 19, 12, 0, tzinfo=UTC)

    assert guard.main(_healthy_at(after), after, BLOCKED) == 1

    printed = capsys.readouterr().out
    assert "::error::known-blocked tests/live/test_artic_shapes_are_still_real.py::" in printed
    assert "expired on 2027-01-18" in printed


def test_a_row_refused_for_its_expiry_or_its_probe_fails_the_check_by_name(tmp_path, capsys):
    guard = _load()
    live = tmp_path / "arrt" / "tests" / "live"
    live.mkdir(parents=True)
    (live / "test_p.py").write_text("def test_probe(): pass\n")
    path = tmp_path / "known-blocked.json"
    rows = [
        {"test": "tests/live/test_p.py::test_probe", "issue": 5, "expires": "2027-06-01", "reason": "r"},
        {"test": "tests/live/test_p.py::test_renamed", "issue": 5, "expires": "2026-12-01", "reason": "r"},
    ]
    path.write_text(json.dumps({"blocked": rows}))

    assert guard.blocked_rows(path, WRITTEN, tmp_path / "arrt") == 1

    printed = capsys.readouterr().out
    assert "test_probe: expires 2027-06-01, more than 60 days after 2026-11-19" in printed
    assert "test_renamed: names test_renamed, which tests/live/test_p.py does not define" in printed


def test_without_a_blocked_file_the_tiers_alone_decide_as_before():
    guard = _load()

    assert guard.main(_healthy_at(WRITTEN), WRITTEN) == 0
    assert guard.main([], WRITTEN) == 1


def test_a_blocked_probe_does_not_make_a_never_run_tier_fresh(capsys):
    """Excusing a probe is not evidence the schedule is alive: no successful run, still a failure."""
    guard = _load()

    assert guard.main([], WRITTEN, BLOCKED) == 1
    assert "have never completed successfully" in capsys.readouterr().out


def test_the_entry_point_checks_the_blocked_file_it_is_given():
    runs = json.dumps(_healthy_at(WRITTEN))

    fresh = subprocess.run(
        [sys.executable, str(SCRIPT), "--now", "2026-11-19T12:00:00Z", "--blocked", str(BLOCKED)],
        input=runs,
        capture_output=True,
        text=True,
    )
    expired = subprocess.run(
        [sys.executable, str(SCRIPT), "--now", "2027-01-19T12:00:00Z", "--blocked", str(BLOCKED)],
        input=json.dumps(_healthy_at(datetime(2027, 1, 19, 12, 0, tzinfo=UTC))),
        capture_output=True,
        text=True,
    )

    assert fresh.returncode == 0, fresh.stdout + fresh.stderr
    assert expired.returncode == 1
    assert "expired on 2027-01-18" in expired.stdout


def test_the_workflow_hands_the_freshness_check_the_blocked_file():
    workflow = (SCRIPT.parents[2] / ".github" / "workflows" / "drift-freshness.yml").read_text(encoding="utf-8")

    assert "check_drift_freshness.py --blocked .github/known-blocked.json" in workflow
