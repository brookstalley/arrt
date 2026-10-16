"""The acquisition queue over real HTTP: a work's state, Retry, and Activity › Queue's listing.

The queue's rules are held by `tests/unit/test_acquisition_queue.py`. What none
of them touches is the routes the browser calls: `GET /api/works/{id}` carrying
the work's state, `POST /api/works/{id}/acquisition/retry`, and
`GET /api/acquisitions`. The suite's application runs no queue worker, so states
are written to the queue's table as a worker would have left them, and the one
pass a test needs is run by hand.
"""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from arrt.persistence.records import AcquisitionMethod, QueuedAcquisition, RightsStatus, SourceClass


@pytest.fixture
def http(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


@pytest.fixture
def accepted(service):
    def _accepted(title="Hunters in the Snow"):
        work = service.add_artwork(title=title)
        service.add_source(
            artwork_id=work.id,
            url=f"https://museum.example/{work.id}.jpg",
            provider="gallery_site",
            source_class=SourceClass.CONTEMPORARY_WEB,
            acquisition_method=AcquisitionMethod.DIRECT_HTTP,
            rights_status=RightsStatus.UNKNOWN,
            is_primary=True,
        )
        return work

    return _accepted


def test_a_work_with_no_image_carries_its_place_in_the_queue(http, accepted):
    work = accepted()

    body = http.get(f"/api/works/{work.id}").json()

    assert body["acquisition"]["artwork_id"] == work.id
    assert body["acquisition"]["phase"] == "queued"


def test_a_work_holding_its_image_carries_no_acquisition(http, ready_work):
    work = ready_work()

    assert http.get(f"/api/works/{work.id}").json()["acquisition"] is None


def test_retry_resets_a_work_the_queue_gave_up_on_and_fetches_nothing(http, accepted, store):
    work = accepted()
    store.set_queued_acquisition(QueuedAcquisition(artwork_id=work.id, failures=4, detail="the museum answered 404."))
    assert http.get(f"/api/works/{work.id}").json()["acquisition"]["phase"] == "gave_up"

    answer = http.post(f"/api/works/{work.id}/acquisition/retry")

    assert answer.status_code == 200
    assert (answer.json()["phase"], answer.json()["failures"]) == ("queued", 0)
    assert store.get_original(work.id) is None, "Retry fetched in the request"


def test_retry_on_a_work_with_no_source_is_refused_with_why(http, service):
    work = service.add_artwork(title="Untraceable")

    answer = http.post(f"/api/works/{work.id}/acquisition/retry")

    assert answer.status_code >= 400
    assert "no source" in answer.text


def test_the_listing_names_each_work_owed_in_the_order_tried_with_retry_first(http, accepted, services):
    accepted("Accepted first")
    retried = accepted("Retried")
    services.acquisition_queue.retry(retried.id)

    body = http.get("/api/acquisitions").json()

    titles = [entry["title"] for entry in body["works"]]
    assert titles.index("Retried") < titles.index("Accepted first"), "a Retry goes to the front"
    assert body["pause"] is None
    assert {entry["acquisition"]["phase"] for entry in body["works"] if entry["title"] in ("Retried", "Accepted first")} == {
        "queued"
    }


def test_the_listing_carries_a_failure_s_next_try_and_a_pause_s_remedy(http, accepted, store, services, monkeypatch):
    failed = accepted("Failed once")
    # Due now, so the pass reaches the disk check on it and pauses.
    accepted("Due now")
    next_try = datetime.now(UTC) + timedelta(hours=1)
    store.set_queued_acquisition(QueuedAcquisition(artwork_id=failed.id, failures=1, next_try_at=next_try, detail="reset."))
    from dataclasses import replace

    monkeypatch.setattr(services.acquisition, "_settings", replace(services.acquisition._settings, min_free_bytes=2**62))
    services.acquisition_queue.run()

    body = http.get("/api/acquisitions").json()
    # A failed work is listed under its cause, not among the works in line.
    members = http.get("/api/acquisitions/causes/works", params={"cause": "reset."}).json()

    assert body["pause"]["condition"] == "NotEnoughSpace"
    assert "MIN_FREE_BYTES" in body["pause"]["remedy"]
    assert [entry["acquisition"]["phase"] for entry in body["works"] if entry["title"] == "Due now"] == ["paused"]
    entry = next(entry for entry in members["works"] if entry["title"] == "Failed once")
    assert entry["acquisition"]["phase"] == "failed"
    assert entry["acquisition"]["next_try_at"] == next_try.isoformat()


def test_a_failed_work_is_counted_on_the_listing_and_listed_under_its_cause_not_in_line(http, accepted, store):
    # The served catalogue's seeded works are owed their images too.
    already = http.get("/api/acquisitions").json()["total"]
    accepted("Waiting")
    failed = [accepted(f"Failed {number}") for number in range(3)]
    for work in failed:
        store.set_queued_acquisition(
            QueuedAcquisition(artwork_id=work.id, failures=1, next_try_at=datetime.now(UTC) + timedelta(hours=1), detail="reset.")
        )

    listing = http.get("/api/acquisitions").json()
    causes = http.get("/api/acquisitions/causes").json()

    titles = [entry["title"] for entry in listing["works"]]
    assert "Waiting" in titles
    assert not any(title.startswith("Failed") for title in titles), "a failed work was listed in line"
    assert (listing["total"], listing["failing"], listing["causes"]) == (already + 1, 3, 1)
    assert causes["causes"] == [{"cause": "reset.", "works": 3, "failed": 3, "gave_up": 0}]
    assert causes["total"] == 1


def test_works_failing_for_one_refusal_are_one_cause_and_each_is_named_by_title(http, service, store):
    """The refusal quotes each work's id, so only a cause with the id taken out is one cause."""
    works = [service.add_artwork(title=f"Sourceless {number}") for number in range(3)]
    for work in works:
        store.set_queued_acquisition(
            QueuedAcquisition(
                artwork_id=work.id,
                failures=1,
                next_try_at=datetime.now(UTC) + timedelta(hours=1),
                detail=f"Artwork {work.id!r} has no source to acquire from.",
            )
        )

    causes = http.get("/api/acquisitions/causes").json()["causes"]
    members = http.get("/api/acquisitions/causes/works", params={"cause": causes[0]["cause"]}).json()

    assert [(each["cause"], each["works"]) for each in causes] == [("The work has no source to acquire from.", 3)]
    details = [entry["acquisition"]["detail"] for entry in members["works"]]
    assert details[0] == "“Sourceless 0” has no source to acquire from."
    assert not any(work.id in detail for work in works for detail in details)


def test_the_in_line_works_and_a_cause_s_works_page_at_the_service_s_default(http, accepted, store):
    already = http.get("/api/acquisitions").json()["total"]
    for number in range(30):
        accepted(f"Waiting {number:02}")
    for number in range(30):
        work = accepted(f"Failed {number:02}")
        store.set_queued_acquisition(
            QueuedAcquisition(artwork_id=work.id, failures=1, next_try_at=datetime.now(UTC) + timedelta(hours=1), detail="reset.")
        )

    first = http.get("/api/acquisitions").json()
    second = http.get("/api/acquisitions", params={"offset": 25}).json()
    members = http.get("/api/acquisitions/causes/works", params={"cause": "reset.", "offset": 25}).json()

    assert (len(first["works"]), first["limit"], first["total"]) == (25, 25, already + 30)
    paged = [entry["title"] for entry in first["works"] + second["works"]]
    assert len(paged) == already + 30
    assert [title for title in paged if title.startswith("Waiting")] == [f"Waiting {number:02}" for number in range(30)]
    assert (members["total"], members["limit"]) == (30, 25)
    assert [entry["title"] for entry in members["works"]] == [f"Failed {number:02}" for number in range(25, 30)]


def test_a_page_beyond_the_cap_is_refused_by_name(http):
    answer = http.get("/api/acquisitions", params={"limit": 101})

    assert answer.status_code == 400
    assert "limit must be between 1 and 100" in answer.json()["error"]


def test_retry_all_retries_every_work_of_a_cause_in_one_request_and_fetches_nothing(http, accepted, service, store):
    gave_up = [accepted(f"Given up {number}") for number in range(3)]
    sourceless = service.add_artwork(title="Sourceless")
    for work in (*gave_up, sourceless):
        store.set_queued_acquisition(QueuedAcquisition(artwork_id=work.id, failures=4, detail="the museum answered 404."))

    answer = http.post("/api/acquisitions/causes/retry", json={"cause": "the museum answered 404."})

    assert answer.status_code == 200
    assert answer.json() == {
        "cause": "the museum answered 404.",
        "retried": 3,
        "refused": [{"reason": "The work has no source to acquire from.", "works": 1}],
    }
    assert {store.get_queued_acquisition(work.id).failures for work in gave_up} == {0}
    assert all(store.get_original(work.id) is None for work in gave_up), "a cause's Retry fetched in the request"


def test_retry_all_on_a_cause_no_work_holds_is_refused_with_why(http, accepted):
    accepted("Waiting")

    answer = http.post("/api/acquisitions/causes/retry", json={"cause": "the museum answered 404."})

    assert answer.status_code == 400
    assert "No work in the queue failed for that reason now" in answer.json()["error"]
