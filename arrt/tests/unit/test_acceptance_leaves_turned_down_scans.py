"""Accepting a work promotes the scans its curator kept and none of the scans they turned down.

A `Source` has no field to carry a rejection, so a turned-down scan promoted on
acceptance came back as an ordinary alternate: `retry_acquisition` and any
better-image flow offered it beside the real ones, and constraint 7b
(`data-model.md`: a rejection stands for the work) stopped holding at the
catalogue boundary. The candidate rows keep the rejection; the catalogue never
hears of the scan.
"""

from arrt.persistence.discovery_records import Verdict


def _accepted_sources(discovery, service, work):
    outcome = discovery.set_verdict(work.id, Verdict.ACCEPTED)
    return outcome, service.list_sources(outcome.work.artwork_id)


def test_a_scan_turned_down_beside_a_kept_one_is_not_promoted(discovery, service, resolved_work, add_image):
    work = resolved_work("Nighthawks")
    [kept] = discovery.list_candidate_images(work.id)
    turned_down = add_image(work, url="https://museum.example/turned-down", confidence=0.4)
    discovery.reject_image(turned_down.id)
    assert (
        discovery.get_candidate_work(work.id).verdict is not Verdict.WANTED
    ), "an alternate's rejection leaves the work as it was"

    _, sources = _accepted_sources(discovery, service, work)

    assert [source.url for source in sources] == [kept.url]
    assert [source.is_primary for source in sources] == [True]


def test_a_kept_alternate_is_still_promoted_beside_the_primary(discovery, service, resolved_work, add_image):
    """The fix skips the turned-down scan, not every non-primary one."""
    work = resolved_work("Nighthawks")
    [primary] = discovery.list_candidate_images(work.id)
    alternate = add_image(work, url="https://museum.example/alternate", confidence=0.4)
    turned_down = add_image(work, url="https://museum.example/turned-down", confidence=0.3)
    discovery.reject_image(turned_down.id)

    _, sources = _accepted_sources(discovery, service, work)

    assert {source.url: source.is_primary for source in sources} == {primary.url: True, alternate.url: False}


def test_the_scan_that_was_on_offer_and_then_turned_down_is_not_promoted_when_a_survivor_is_accepted(
    discovery, service, resolved_work, add_image
):
    """Turning down the selected scan moves the selection to a survivor; the one turned down stays out."""
    work = resolved_work("Nighthawks")
    [on_offer] = discovery.list_candidate_images(work.id)
    survivor = add_image(work, url="https://museum.example/survivor", confidence=0.5)
    discovery.reject_image(on_offer.id)
    discovery.record_resolution(work.id)

    _, sources = _accepted_sources(discovery, service, work)

    assert [(source.url, source.is_primary) for source in sources] == [(survivor.url, True)]


def test_the_turned_down_scan_is_still_a_candidate_after_acceptance(discovery, service, resolved_work, add_image):
    """Skipped in the catalogue, kept as a candidate: what the curator decided is not erased."""
    work = resolved_work("Nighthawks")
    turned_down = add_image(work, url="https://museum.example/turned-down", confidence=0.4)
    discovery.reject_image(turned_down.id)

    _accepted_sources(discovery, service, work)

    stored = {image.id: image for image in discovery.list_candidate_images(work.id)}
    assert stored[turned_down.id].rejected_at is not None
