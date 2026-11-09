"""The scheduler and its Watch job, through the real container with a scripted engine.

Each test drives a pass itself (`services.scheduler.run_pass()`), as the app's
lifespan does on its thread; the runs a pass starts run on the runner's own
threads, as they do when deployed, and are waited for by their status.
"""

import dataclasses
import logging
import threading
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

import pytest
from fakes import GATE_SECONDS

from arrt.app import create_app
from arrt.library.discovery.engine import EngineFailure
from arrt.library.discovery.openrouter import KeyStatus
from arrt.library.services.scheduler import SCHEDULER_THREAD_NAME, PassResult, Scheduler
from arrt.library.services.watches import WatchRefusal
from arrt.persistence.discovery_records import InitiatedBy, RunStatus, Verdict

WORDS = "new abstract expressionist paintings in museum collections"
UNATTENDED_MODEL = "some-lab/a-cheaper-model"


@pytest.fixture
def key_status():
    """A key, so unattended work has something to spend with, unless a test says otherwise."""
    return lambda: KeyStatus(limit_usd=Decimal(20), usage_usd=Decimal(1), remaining_usd=Decimal(19))


def switch_on(services, allowance: str = "5") -> None:
    services.settings.set("unattended_work", "on", surface=InitiatedBy.WEB_UI)
    services.settings.set("unattended_allowance_usd", allowance, surface=InitiatedBy.WEB_UI)


def a_watch(services, **fields):
    return services.watches.create(intent_text=WORDS, surface=InitiatedBy.WEB_UI, **fields)


def settled(services, run_id: str):
    """The run once this process has stopped working on it, waiting on its status as a client does.

    The suite's container wires no image search, so a run that proposed works
    rests in `resolving_images` with nothing advancing it, as on a deployment
    with no image provider.
    """
    for _ in range(40):
        view = services.runner.run_status(run_id, wait=True)
        if not services.runner.is_working_on(run_id):
            return view.run
    pytest.fail(f"run {run_id} was never let go")


def tried_ago(services, watch_id: str, ago: timedelta) -> None:
    """Move a Watch's last attempt into the past, and when it was written with it, as time passing would."""
    store = services.watches._store
    watch = store.get_watch(watch_id)
    then = datetime.now(UTC) - ago
    store.update_watch(
        dataclasses.replace(
            watch, last_attempt_at=then, created_at=min(watch.created_at, then), updated_at=min(watch.updated_at, then)
        )
    )


def below_one_run(settings) -> Decimal:
    """An amount with room left in it, but less than one run's estimate.

    Above nothing, so what refuses is the look-ahead (spent plus the estimate
    would pass it) and not the rule that a spent amount refuses everything.
    """
    estimate = settings.discovery_settings.phase1_estimate_usd
    short = estimate.quantize(Decimal("0.01"), rounding=ROUND_FLOOR)
    assert Decimal(0) < short < estimate, f"the suite's estimate {estimate} leaves no such amount"
    return short


def runs_of(services, watch_id: str):
    """The Watch's runs, oldest first: `list_runs` answers newest first."""
    return sorted((run for run in services.discovery.list_runs() if run.watch_id == watch_id), key=lambda run: run.started_at)


# -- what a due Watch starts ------------------------------------------------------


def test_a_due_watch_starts_one_run_attributed_unattended_on_the_unattended_model(services, engine):
    switch_on(services)
    services.settings.set("unattended_model", UNATTENDED_MODEL, surface=InitiatedBy.WEB_UI)
    watch = a_watch(services)

    result = services.scheduler.run_pass()

    assert result["watches"] == PassResult(due=1, started=1, refused=0)
    [run] = runs_of(services, watch.id)
    assert (run.initiated_by, run.intent_text) == (InitiatedBy.UNATTENDED, WORDS)
    assert settled(services, run.id).status is RunStatus.RESOLVING_IMAGES, "phase 1 ran; the suite wires no phase 2"
    assert engine.requests[-1].model == UNATTENDED_MODEL
    recorded = services.watches.get(watch.id)
    assert (recorded.last_run_id, recorded.last_refusal) == (run.id, None)
    assert recorded.updated_by is InitiatedBy.WEB_UI, "the scheduler's bookkeeping is not a household edit"


def test_an_empty_unattended_model_runs_on_the_engines_own(services, engine):
    switch_on(services)
    watch = a_watch(services)

    services.scheduler.run_pass()

    settled(services, runs_of(services, watch.id)[0].id)
    assert engine.requests[-1].model is None


def test_a_watch_runs_spend_counts_against_the_allowance_and_its_cap_and_an_asks_does_not(services, discovery_store):
    switch_on(services)
    watch = a_watch(services)
    asked = services.runner.start(intent_text="something a person asked", initiated_by=InitiatedBy.WEB_UI)
    settled(services, asked.id)

    services.scheduler.run_pass()
    run = settled(services, runs_of(services, watch.id)[0].id)

    billed = sum(record.cost_usd for record in discovery_store.list_spend_records() if record.discovery_run_id == run.id)
    assert billed > 0, "the scripted engine bills, or nothing below is tested"
    assert services.unattended.spent_this_month() == billed
    assert services.watches.standing(services.watches.get(watch.id)).spent_usd == billed


def test_a_watch_with_a_run_in_flight_is_not_started_again(services, engine):
    switch_on(services)
    watch = a_watch(services)
    engine.gate = threading.Event()
    try:
        services.scheduler.run_pass()
        tried_ago(services, watch.id, timedelta(days=30))

        again = services.scheduler.run_pass()

        assert again["watches"] == PassResult(due=0, started=0, refused=0)
        assert len(runs_of(services, watch.id)) == 1
        assert services.watches.standing(services.watches.get(watch.id)).sentence == "Running now."
    finally:
        engine.gate.set()
    settled(services, runs_of(services, watch.id)[0].id)


def test_a_watch_off_is_never_due_and_one_on_again_is(services):
    switch_on(services)
    watch = a_watch(services, enabled=False)

    assert services.scheduler.run_pass()["watches"] == PassResult()
    services.watches.update(watch.id, enabled=True, surface=InitiatedBy.WEB_UI)
    assert services.scheduler.run_pass()["watches"].started == 1
    settled(services, runs_of(services, watch.id)[0].id)


# -- why a due Watch does not start ----------------------------------------------------


def test_with_unattended_work_off_a_due_watch_is_refused_and_nothing_is_asked(services, engine):
    watch = a_watch(services)

    result = services.scheduler.run_pass()

    assert result["watches"] == PassResult(due=1, started=0, refused=1)
    assert engine.requests == []
    standing = services.watches.standing(services.watches.get(watch.id))
    assert standing.watch.last_refusal == WatchRefusal.OFF
    assert standing.sentence == "Not run: unattended work is off in Settings › General."


class TestWithNoKey:
    @pytest.fixture
    def key_status(self):
        return None

    def test_a_due_watch_is_refused_for_the_key(self, services, engine):
        switch_on(services)
        watch = a_watch(services)

        services.scheduler.run_pass()

        assert services.watches.get(watch.id).last_refusal == WatchRefusal.NO_KEY
        assert engine.requests == []


def test_an_allowance_too_small_for_a_run_refuses_it(services, settings, engine):
    short = below_one_run(settings)
    switch_on(services, allowance=f"{short:.2f}")
    watch = a_watch(services)

    services.scheduler.run_pass()

    assert services.watches.get(watch.id).last_refusal == WatchRefusal.ALLOWANCE_SPENT
    assert engine.requests == []


def test_a_cap_too_small_for_a_run_refuses_it_while_the_allowance_would_allow_it(services, settings, engine):
    switch_on(services, allowance="5")
    watch = a_watch(services, monthly_cap_usd=f"{below_one_run(settings):.2f}")
    roomy = a_watch(services)

    result = services.scheduler.run_pass()

    assert result["watches"] == PassResult(due=2, started=1, refused=1)
    assert services.watches.get(watch.id).last_refusal == WatchRefusal.CAP_SPENT
    assert services.watches.get(roomy.id).last_refusal is None
    settled(services, runs_of(services, roomy.id)[0].id)


def test_two_due_watches_on_room_for_one_run_start_one_and_refuse_the_other(services, settings, engine):
    estimate = settings.discovery_settings.phase1_estimate_usd
    room = estimate.quantize(Decimal("0.01"), rounding=ROUND_CEILING)
    assert estimate <= room < 2 * estimate, f"the suite's estimate {estimate} leaves no room for exactly one"
    switch_on(services, allowance=f"{room:.2f}")
    first = a_watch(services)
    second = a_watch(services)
    # Held at the gate, so the first run has billed nothing while the second is
    # weighed: what refuses it is the pass counting what it has started.
    engine.gate = threading.Event()
    try:
        result = services.scheduler.run_pass()
    finally:
        engine.gate.set()

    assert result["watches"] == PassResult(due=2, started=1, refused=1)
    assert services.watches.get(first.id).last_refusal is None
    assert services.watches.get(second.id).last_refusal == WatchRefusal.ALLOWANCE_SPENT
    settled(services, runs_of(services, first.id)[0].id)


def test_a_cap_spent_by_the_watchs_own_runs_refuses_the_next(services, settings):
    estimate = settings.discovery_settings.phase1_estimate_usd
    switch_on(services, allowance="5")
    # Room for exactly one run: the estimate, rounded up to the cent.
    watch = a_watch(services, monthly_cap_usd=f"{estimate.quantize(Decimal('0.01'), rounding=ROUND_CEILING):.2f}")
    services.scheduler.run_pass()
    settled(services, runs_of(services, watch.id)[0].id)
    tried_ago(services, watch.id, timedelta(days=2))

    services.scheduler.run_pass()

    assert services.watches.get(watch.id).last_refusal == WatchRefusal.CAP_SPENT
    assert len(runs_of(services, watch.id)) == 1


def test_a_run_that_cannot_start_is_recorded_as_such_and_the_pass_goes_on(services, engine):
    switch_on(services)
    engine.reason = "phase 1 is not wired"
    first = a_watch(services)
    second = a_watch(services)

    result = services.scheduler.run_pass()

    assert result["watches"] == PassResult(due=2, started=0, refused=2)
    assert {services.watches.get(watch.id).last_refusal for watch in (first, second)} == {WatchRefusal.COULD_NOT_START}


# -- when a Watch is next due ---------------------------------------------------------


def test_a_server_down_for_days_runs_a_watch_once_not_once_per_missed_slot(services):
    switch_on(services)
    watch = a_watch(services, cadence="hourly")
    services.scheduler.run_pass()
    settled(services, runs_of(services, watch.id)[0].id)
    tried_ago(services, watch.id, timedelta(days=3))

    assert services.scheduler.run_pass()["watches"].started == 1
    settled(services, runs_of(services, watch.id)[-1].id)
    assert services.scheduler.run_pass()["watches"] == PassResult()
    assert len(runs_of(services, watch.id)) == 2


def test_a_finished_run_waits_its_cadence_and_a_failed_one_an_hour_not_a_pass(services, engine):
    switch_on(services)
    finished = a_watch(services, cadence="daily")
    services.scheduler.run_pass()
    settled(services, runs_of(services, finished.id)[0].id)
    services.watches.update(finished.id, enabled=False, surface=InitiatedBy.WEB_UI)

    engine.error = EngineFailure("the provider answered nonsense")
    failing = a_watch(services, cadence="daily")
    services.scheduler.run_pass()
    assert settled(services, runs_of(services, failing.id)[0].id).status is RunStatus.FAILED

    assert services.scheduler.run_pass()["watches"] == PassResult(), "a failed run is not retried at the very next pass"
    tried_ago(services, failing.id, timedelta(minutes=61))
    assert services.scheduler.run_pass()["watches"].started == 1, "a failed run is retried after an hour, not a day"
    settled(services, runs_of(services, failing.id)[-1].id)

    services.watches.update(finished.id, enabled=True, surface=InitiatedBy.WEB_UI)
    tried_ago(services, finished.id, timedelta(minutes=61))
    assert all(standing.watch.id != finished.id for standing in services.watches.due()), "a finished run waits a day"


def test_a_watch_due_for_over_an_hour_with_nothing_tried_is_overdue_while_work_is_on(services):
    switch_on(services)
    watch = a_watch(services, cadence="daily")
    services.scheduler.run_pass()
    settled(services, runs_of(services, watch.id)[0].id)

    tried_ago(services, watch.id, timedelta(days=1, minutes=30))
    assert services.watches.standing(services.watches.get(watch.id)).overdue is False, "due, not yet overdue"

    tried_ago(services, watch.id, timedelta(days=1, hours=2))
    late = services.watches.standing(services.watches.get(watch.id))
    assert late.overdue is True
    assert late.sentence.startswith("Overdue")

    services.settings.set("unattended_work", "off", surface=InitiatedBy.WEB_UI)
    assert services.watches.standing(services.watches.get(watch.id)).overdue is False, "nothing is late while work is off"


# -- what a Watch's finds may shape --------------------------------------------------------


def test_an_unreviewed_find_is_absent_from_the_next_runs_request_and_a_rejected_one_present(services, engine):
    switch_on(services)
    watch = a_watch(services, cadence="hourly")
    services.scheduler.run_pass()
    run = settled(services, runs_of(services, watch.id)[0].id)
    [found, *_] = services.discovery.list_candidate_works(run.id)

    tried_ago(services, watch.id, timedelta(hours=2))
    services.scheduler.run_pass()
    settled(services, runs_of(services, watch.id)[-1].id)
    assert found.proposed_title not in {work.title for work in engine.requests[-1].rejected}

    services.discovery.set_verdict(found.id, Verdict.REJECTED)
    tried_ago(services, watch.id, timedelta(hours=2))
    services.scheduler.run_pass()
    settled(services, runs_of(services, watch.id)[-1].id)
    assert found.proposed_title in {work.title for work in engine.requests[-1].rejected}


# -- the scheduler itself -------------------------------------------------------------


def test_every_pass_logs_one_line_per_job_even_when_nothing_is_due(services, caplog):
    with caplog.at_level(logging.INFO, logger="arrt.library.services.scheduler"):
        services.scheduler.run_pass()

    [line] = [record for record in caplog.records if getattr(record, "event", None) == "scheduler.pass"]
    assert (line.job, line.due, line.started, line.refused) == ("watches", 0, 0, 0)


def test_a_job_that_raises_is_logged_and_the_next_job_still_runs(caplog):
    class Broken:
        name = "broken"

        def run_pass(self) -> PassResult:
            raise RuntimeError("a bug in a job")

    class Fine:
        name = "fine"

        def run_pass(self) -> PassResult:
            return PassResult(due=1, started=1)

    with caplog.at_level(logging.INFO, logger="arrt.library.services.scheduler"):
        results = Scheduler([Broken(), Fine()]).run_pass()

    assert results == {"fine": PassResult(due=1, started=1)}
    assert any(getattr(record, "event", None) == "scheduler.pass_failed" for record in caplog.records)


def _scheduler_threads() -> list[threading.Thread]:
    return [thread for thread in threading.enumerate() if thread.name == SCHEDULER_THREAD_NAME]


async def test_the_application_schedules_only_when_asked_and_stops_when_it_stops(services):
    app = create_app(services)
    async with app.router.lifespan_context(app):
        assert not _scheduler_threads(), "a test harness acquired a thread that spends by building the app"

    scheduling = create_app(services, schedule=True)
    async with scheduling.router.lifespan_context(scheduling):
        assert _scheduler_threads(), "asked to schedule, the application started no scheduler"
    for thread in _scheduler_threads():
        thread.join(timeout=GATE_SECONDS)
    assert not _scheduler_threads()


def test_a_started_run_whose_record_fails_is_counted_named_in_the_log_and_the_pass_goes_on(services, monkeypatch, caplog):
    """The run is under way and will spend, so it counts as started; only its note failed, and the log names it."""
    from arrt.services.errors import ServiceError

    switch_on(services)
    first = a_watch(services)
    second = a_watch(services)
    recorded = services.watches.record_started

    def failing_for_the_first(watch_id: str, run_id: str) -> None:
        if watch_id == first.id:
            raise ServiceError("the catalogue refused the write")
        recorded(watch_id, run_id)

    monkeypatch.setattr(services.watches, "record_started", failing_for_the_first)

    with caplog.at_level(logging.INFO, logger="arrt.library.services.scheduler"):
        result = services.scheduler.run_pass()

    assert result["watches"] == PassResult(due=2, started=2, refused=0)
    [unrecorded] = [record for record in caplog.records if getattr(record, "event", None) == "watch.unrecorded_start"]
    [first_run] = runs_of(services, first.id)
    assert (unrecorded.watch_id, unrecorded.run_id) == (first.id, first_run.id)
    assert services.watches.get(second.id).last_run_id == runs_of(services, second.id)[0].id
    for run in (first_run, *runs_of(services, second.id)):
        settled(services, run.id)
