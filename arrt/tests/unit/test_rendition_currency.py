"""One rule for "is this rendition still current", and every surface following it.

The rule decides things a curator sees side by side: whether the catalogue calls
a work's presentation master current, and whether the work reaches the wall or is
excluded as `stale_rendition`. It was once written twice, so a change to what
"current" means would have landed in one place and not the other, and a work
would have read as current while the wall silently dropped it.

So these tests do not assert the rule's *content*. They assert that the two
surfaces cannot disagree about it, across every state a work can be in.
"""

from arrt.library.facade import PlayableWork, UnplayableReason
from arrt.library.readiness import master_rendition_of
from arrt.persistence.records import FetchStatus, is_current


def _catalogue_says_current(service, artwork_id) -> bool:
    """The catalogue's own verdict on the master the wall would be sent."""
    views = {view.rendition.id: view for view in service.list_renditions(artwork_id)}
    chosen = master_rendition_of([view.rendition for view in views.values()], service.get_original(artwork_id))
    return chosen is not None and not views[chosen.id].stale


def _wall_says_current(library, artwork_id) -> bool:
    """What the feed's build would decide: no exclusion, or one that is not staleness.

    Asked of the Library's facade, which is where the build asks it.
    """
    answer = library.playable([artwork_id])[artwork_id]
    return isinstance(answer, PlayableWork) or answer.reason is not UnplayableReason.STALE_RENDITION


class TestTheGridAndTheWallCannotDisagree:
    """The matrix, driven through both real surfaces rather than through the rule."""

    def test_a_freshly_prepared_work_is_current_to_both(self, service, library, ready_work):
        work = ready_work()

        assert _catalogue_says_current(service, work.id) is True
        assert _wall_says_current(library, work.id) is True

    def test_a_work_re_acquired_since_its_render_is_stale_to_both(self, service, library, ready_work):
        """The case the rule exists for: the master describes an image no longer held."""
        work = ready_work()
        source = service.list_sources(work.id)[0]
        service.record_original(
            artwork_id=work.id,
            source_id=source.id,
            path=f"raw/{work.id}.tif",
            width=6000,
            height=4000,
            byte_size=90_000_000,
            content_hash="a-later-acquisition",
            fetch_status=FetchStatus.OK,
        )

        assert _catalogue_says_current(service, work.id) is False
        assert _wall_says_current(library, work.id) is False

    def test_a_work_with_no_master_at_all_is_current_to_neither(self, service, library, ready_work):
        """The neighbouring exclusion, kept apart from staleness on both surfaces.

        `no_rendition` and `stale_rendition` are acted on differently — make it,
        versus make it again — so a surface that collapsed them would send a
        curator after the wrong thing.
        """
        work = ready_work(master=False)

        assert _catalogue_says_current(service, work.id) is False
        assert library.playable([work.id])[work.id].reason is UnplayableReason.NO_RENDITION


class TestTheRuleItself:
    """The predicate's own contract, so its callers are testing agreement and not it."""

    def test_a_master_made_from_the_held_image_is_current(self, service, ready_work):
        work = ready_work()
        rendition = service.list_renditions(work.id)[0].rendition

        assert is_current(rendition, service.get_original(work.id)) is True

    def test_a_master_with_no_original_at_all_is_not_current(self, service, ready_work):
        work = ready_work()
        rendition = service.list_renditions(work.id)[0].rendition

        assert is_current(rendition, None) is False

    def test_a_stale_master_is_still_returned_when_no_current_one_is_held(self, service, ready_work):
        """Currency is not a filter here, and that is load-bearing.

        `assess` needs a stale master in hand to say "needs making again"
        (`stale_rendition`) rather than "never made" (`no_rendition`) — two
        exclusions a curator acts on differently. A lookup that dropped stale
        rows would tell them to make a master that has been made.
        """
        work = ready_work()
        source = service.list_sources(work.id)[0]
        service.record_original(
            artwork_id=work.id,
            source_id=source.id,
            path=f"raw/{work.id}.tif",
            width=6000,
            height=4000,
            byte_size=90_000_000,
            content_hash="a-later-acquisition",
            fetch_status=FetchStatus.OK,
        )
        renditions = [view.rendition for view in service.list_renditions(work.id)]

        assert master_rendition_of(renditions, service.get_original(work.id)) is not None
