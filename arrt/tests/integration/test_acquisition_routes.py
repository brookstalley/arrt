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

    assert body["pause"]["condition"] == "NotEnoughSpace"
    assert "MIN_FREE_BYTES" in body["pause"]["remedy"]
    entry = next(entry for entry in body["works"] if entry["title"] == "Failed once")
    assert entry["acquisition"]["phase"] == "failed"
    assert entry["acquisition"]["next_try_at"] == next_try.isoformat()
