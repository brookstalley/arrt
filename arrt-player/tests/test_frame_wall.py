"""The Frame, driven by the schedule: the timer is the feed's, and the television is whoever's using it.

The television's own slideshow can only be scoped to a whole category — no
content-id list, no album, no playlist — so it cannot be made to show a theme.
So this Player changes the picture itself, calling `select_image` when the
feed's schedule moves to another work, and switches the set's slideshow off once
so the two cannot fight.

The fixture feed (`conftest.Publisher`) puts its works in order, each up for
`interval_seconds` from the instant the test clock starts, so "the next slot" is
"the next work".

A curator's `show_now` and `next` arrive as a republished schedule whose
current slot names another work (`player-contract.md` § What happens to
`show_now` and `next`), so the tests at the end publish exactly that.
"""

import logging

from fakes import FakeTv

from arrt_player.displays.frame import frame_wall
from arrt_player.manifest import Watcher
from arrt_player.state import DisplayState
from arrt_player.wall import Wall


def _a_wall(settings, tv: FakeTv, state: DisplayState, clock) -> Wall:
    """A wall on the Frame as a restart builds one: a new loop over the same store and the same set."""
    return frame_wall(settings=settings, tv=tv, state=state, watcher=Watcher(settings.manifest_path), clock=clock.as_clock())


def _events(caplog, event: str) -> list[logging.LogRecord]:
    return [record for record in caplog.records if getattr(record, "event", None) == event]


async def test_it_shows_the_slots_work_immediately(daemon: Wall, tv: FakeTv, publish):
    publish(["w1", "w2"])

    await daemon.tick()

    assert publish.work_of(tv.on_the_wall) == "w1"


async def test_it_holds_a_work_until_its_slot_ends(daemon: Wall, tv: FakeTv, publish, clock):
    publish(["w1", "w2"], interval_seconds=180)
    await daemon.tick()

    clock.advance(179)
    await daemon.tick()
    assert len(tv.selected) == 1, "the wall moved before the slot was over"

    clock.advance(1)
    await daemon.tick()
    assert publish.work_of(tv.on_the_wall) == "w2"


async def test_the_schedule_comes_round_again(daemon: Wall, tv: FakeTv, publish, clock):
    publish(["w1", "w2"], interval_seconds=10)
    await daemon.tick()

    for _ in range(2):
        clock.advance(10)
        await daemon.tick()

    assert [publish.work_of(tv.holding[c]) for c in tv.selected] == ["w1", "w2", "w1"]


async def test_the_native_slideshow_is_disabled_once_and_survives_a_restart(
    settings, tv: FakeTv, state: DisplayState, clock, publish
):
    """Persisted rather than held in memory, because `Restart=always` makes
    restarts routine and the call is only correct to make once."""
    publish(["w1"])
    first = _a_wall(settings, tv, state, clock)
    await first.tick()
    await first.tick()
    assert tv.slideshow_disabled == 1

    await _a_wall(settings, tv, state, clock).tick()

    assert tv.slideshow_disabled == 1


async def test_a_work_whose_media_is_missing_is_passed_over_and_the_next_slot_shown(
    daemon: Wall, tv: FakeTv, publish, clock, caplog
):
    """Fatal-for-one-item. The wall going black is always worse than the wall
    being incomplete: it keeps the work it has through the missing one's slot."""
    publish(["w1", "w2", "w3"], interval_seconds=10)
    publish.withdraw("w2")
    await daemon.tick()

    clock.advance(10)
    with caplog.at_level(logging.WARNING):
        await daemon.tick()
    assert publish.work_of(tv.on_the_wall) == "w1", "the wall gave up its picture for a work it could not show"

    clock.advance(10)
    await daemon.tick()

    assert publish.work_of(tv.on_the_wall) == "w3", "the missing work stopped the schedule instead of being passed over"
    assert len(_events(caplog, "schedule.media_missing")) == 1


async def test_a_feed_whose_every_master_is_missing_selects_nothing_and_says_so_once(daemon: Wall, tv: FakeTv, publish, caplog):
    """A pass looks at one work, the slot's, so a feed that can show nothing ends
    every pass at once rather than spinning."""
    publish(["w1", "w2"], media=False)

    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            await daemon.tick()

    assert tv.selected == []
    assert len(_events(caplog, "schedule.media_missing")) == 1


async def test_a_feed_that_can_show_nothing_warns_once_a_work_not_once_a_second(daemon: Wall, tv: FakeTv, publish, clock, caplog):
    """journald rate-limits, and the lines it drops are the ERRORs that are this
    plane's only failure channel: a missing master is said once per work per
    feed, however long its slot lasts."""
    publish(["w1", "w2", "w3"], interval_seconds=60, media=False)

    with caplog.at_level(logging.WARNING):
        for _ in range(10):
            await daemon.tick()
            clock.advance(1)
    assert len(_events(caplog, "schedule.media_missing")) == 1, "the missing work was said again on every poll"

    with caplog.at_level(logging.WARNING):
        clock.advance(60)
        await daemon.tick()

    assert len(_events(caplog, "schedule.media_missing")) == 2


async def test_media_that_arrives_is_shown_at_once_rather_than_at_the_next_slot(daemon: Wall, tv: FakeTv, publish):
    """So a wall with nothing to show recovers when the pull brings its master."""
    publish(["w1"], interval_seconds=180, media=False)
    await daemon.tick()
    assert tv.selected == []

    publish(["w1"], interval_seconds=180)
    await daemon.tick()

    assert publish.work_of(tv.on_the_wall) == "w1"


async def test_a_restart_keeps_the_picture_and_then_carries_on_from_it(settings, tv: FakeTv, state: DisplayState, clock, publish):
    """A restart must not lose its place — and must not move the wall either.

    `Restart=always` makes restarts routine. Re-selecting what is already
    showing is idempotent and invisible, and the next slot is still the next work.
    """
    publish(["w1", "w2", "w3"], interval_seconds=10)
    first = _a_wall(settings, tv, state, clock)
    await first.tick()
    clock.advance(10)
    await first.tick()
    assert publish.work_of(tv.on_the_wall) == "w2"

    restarted = _a_wall(settings, tv, state, clock)
    await restarted.tick()
    assert publish.work_of(tv.on_the_wall) == "w2", "the restart moved the wall"

    clock.advance(10)
    await restarted.tick()
    assert publish.work_of(tv.on_the_wall) == "w3", "the restart lost its place in the schedule"


async def test_repeated_restarts_do_not_walk_the_wall_forward(settings, tv: FakeTv, state: DisplayState, clock, publish):
    """The crash-loop case stated on its own, because it is the one that is ugly
    in the room rather than merely wrong in the store."""
    publish(["w1", "w2", "w3"], interval_seconds=180)
    await _a_wall(settings, tv, state, clock).tick()

    for _ in range(10):
        await _a_wall(settings, tv, state, clock).tick()

    assert {publish.work_of(tv.holding[c]) for c in tv.selected} == {"w1"}


async def test_a_republish_mid_slot_does_not_hand_the_current_work_a_second_turn(daemon: Wall, tv: FakeTv, publish, clock):
    """The server republishes on every catalogue edit; the schedule's times are absolute, so the slot still ends when it did."""
    publish(["w1", "w2", "w3"], interval_seconds=100)
    await daemon.tick()
    assert publish.work_of(tv.on_the_wall) == "w1"

    clock.advance(50)
    publish(["w1", "w2", "w3"], interval_seconds=100)
    await daemon.tick()

    clock.advance(50)
    await daemon.tick()

    assert publish.work_of(tv.on_the_wall) == "w2", "a catalogue edit gave the current work a second slot"


# -- a television that takes selections and displays none of them --------------
#
# Observed on a real set on 2026-08-07 with its panel dark: `select_image`
# returned, raised nothing and emitted none of the three art-mode events, while
# what the set displayed did not change across repeated attempts over twelve
# seconds. Every call a wall can make succeeded; the only thing that failed was
# the picture changing. These tests exist because the failure is invisible from
# the call: nothing above the seam can infer it, and the set's silence — no
# `image_selected` announcement — is the only thing that distinguishes it from a
# change that worked.


async def test_a_selection_the_set_does_not_display_is_not_reported_as_shown(
    daemon: Wall, tv: FakeTv, state: DisplayState, publish, caplog
):
    publish(["w1", "w2"])
    tv.displays_nothing_selected = True

    with caplog.at_level(logging.INFO):
        await daemon.tick()

    assert tv.selected, "the wall never asked the set to show anything"
    assert tv.on_the_wall is None, "the fake put a picture up that the set never displayed"
    assert not _events(caplog, "rotation.selected"), "the wall reported a change the television did not perform"
    assert (
        state.last_selected_work_id is None
    ), "a work never displayed was recorded as the one on the wall, so a restart would re-show it"


async def test_a_wall_that_displays_nothing_ends_the_pass_rather_than_trying_other_works(daemon: Wall, tv: FakeTv, publish):
    """A missing master means pass this work over; a dark wall means try no work.

    Every other work would be attempted against a set that displays none of
    them, each waiting out the whole confirmation window.
    """
    publish(["w1", "w2", "w3", "w4"])
    tv.displays_nothing_selected = True

    await daemon.tick()

    assert len(tv.selected) == 1, f"the pass tried {len(tv.selected)} works against a wall that displays none"


async def test_it_says_the_wall_is_not_changing_once_not_once_a_slot(daemon: Wall, tv: FakeTv, publish, clock, caplog):
    """A panel stays dark for hours. One line per slot is a hundred a night
    saying the one thing that has not changed, and journald drops what it
    rate-limits — which would be the ERRORs this plane's only failure channel
    carries."""
    publish(["w1", "w2"], interval_seconds=10)
    # Art mode stays *on*: a set that says it is showing art and then does not
    # change is the only route left to this branch, now that a set reporting art
    # mode off is never asked to select at all.
    tv.displays_nothing_selected = True

    with caplog.at_level(logging.INFO):
        for _ in range(6):
            await daemon.tick()
            clock.advance(10)

    reports = _events(caplog, "rotation.wall_unchanged")
    assert len(reports) == 1, f"the still wall was reported {len(reports)} times"
    assert reports[0].art_mode == "on", "the one line an operator reads does not say what the set claims about itself"


async def test_the_wall_coming_back_is_reported_and_the_schedule_resumes(daemon: Wall, tv: FakeTv, publish, clock, caplog):
    publish(["w1", "w2"], interval_seconds=10)
    tv.displays_nothing_selected = True
    await daemon.tick()

    with caplog.at_level(logging.INFO):
        tv.displays_nothing_selected = False
        clock.advance(10)
        await daemon.tick()

    assert tv.on_the_wall is not None, "the schedule did not resume when the set started displaying again"
    assert _events(
        caplog, "rotation.wall_recovered"
    ), "the wall came back and nothing said so, so the WARNING above it stands unresolved in the log"


async def test_a_wall_that_comes_back_shows_the_slots_work_now(daemon: Wall, tv: FakeTv, publish, clock):
    """Neither the work it could not show nor a catch-up through the slots it missed.

    The schedule is state, not a queue: the wall coming back shows what the
    schedule says now, in one selection. Four works and two dark passes, so the
    work now (w3) is neither the first nor the one deferred.
    """
    publish(["w1", "w2", "w3", "w4"], interval_seconds=10)
    tv.displays_nothing_selected = True

    for _ in range(2):
        await daemon.tick()
        clock.advance(10)

    tv.displays_nothing_selected = False
    attempts = len(tv.selected)
    await daemon.tick()

    assert publish.work_of(tv.on_the_wall) == "w3", "an evening of a dark panel left the wall on the wrong work"
    assert len(tv.selected) == attempts + 1, "the wall walked the slots it missed"


async def test_a_set_that_says_it_took_the_image_and_is_not_showing_it_is_believed(daemon: Wall, tv: FakeTv, publish, caplog):
    """The set has two ways of not moving the wall, and both mean the same thing.

    It can stay silent, which is the dark panel, or it can announce the selection
    while saying `is_shown: "No"`. The second is the one a wall that merely
    counted announcements would get wrong, reporting a change from the set's own
    word that it had not performed one.
    """
    publish(["w1", "w2"])
    tv.admits_not_showing = {"MY-F0001"}

    with caplog.at_level(logging.INFO):
        await daemon.tick()

    assert tv.selected, "the wall never asked the set to show anything"
    assert not _events(caplog, "rotation.selected"), "the set said it was not showing the image and the wall reported it as shown"
    assert _events(caplog, "rotation.wall_unchanged")


# -- the television belongs to whoever is using it -----------------------------
#
# Measured on a real set on 2026-08-07, with the operator watching a programme: a
# due change sent `select_image`, the set **switched itself into art mode**, and
# the picture they were watching was gone. It is not a polite refusal like the
# dark state's, and somebody watching television is a daily event rather than an
# edge case. So nothing reaches the wall unless the set says it is showing art —
# and `get_artmode` is what says so, reading `off` for both a dark panel and a
# programme, and `on` only for art mode.


async def test_a_television_somebody_is_watching_is_left_alone(daemon: Wall, tv: FakeTv, publish, caplog):
    publish(["w1", "w2"])
    tv.art_mode = "off"

    with caplog.at_level(logging.INFO):
        await daemon.tick()

    assert tv.selected == [], "the wall took the screen off whoever was watching"
    assert _events(caplog, "rotation.wall_not_ours")


async def test_an_evening_of_television_ends_on_the_slots_work_in_one_selection(daemon: Wall, tv: FakeTv, publish, clock):
    """Nothing is walked against a wall nobody could see.

    Five works and four passes of television, so the work the schedule names
    when the set comes back (w5) is not the first one.
    """
    publish(["w1", "w2", "w3", "w4", "w5"], interval_seconds=10)
    tv.art_mode = "off"

    for _ in range(4):
        await daemon.tick()
        clock.advance(10)

    tv.art_mode = "on"
    await daemon.tick()

    assert [publish.work_of(tv.holding[c]) for c in tv.selected] == ["w5"], "an evening of television walked the schedule"


async def test_the_wall_comes_back_the_moment_the_set_announces_art_mode(daemon: Wall, tv: FakeTv, publish, clock, caplog):
    """Recovery is by the set's own announcement, not by waiting out the backoff.

    Without this, switching off a programme would leave the wall blank for the
    remainder of a wait that has doubled its way up to five minutes — and unlike
    a panel left dark overnight, this transition happens every time somebody
    finishes watching something.
    """
    publish(["w1", "w2"], interval_seconds=180)
    tv.art_mode = "off"
    for _ in range(6):
        await daemon.tick()
        clock.advance(5)
    assert tv.selected == []

    # The set says it has changed, and the clock barely moves: the point is that
    # none of the remaining wait — the backoff — has to elapse before the picture
    # comes back.
    tv.art_mode = "on"
    tv.art_mode_announced = True
    with caplog.at_level(logging.INFO):
        await daemon.tick()

    assert publish.work_of(tv.on_the_wall) == "w1", "the wall waited out a backoff the set had already ended"
    assert _events(caplog, "rotation.wall_returned")


async def test_it_says_the_wall_is_not_ours_once_not_once_a_slot(daemon: Wall, tv: FakeTv, publish, clock, caplog):
    """Somebody watches television for hours. A line per attempt would bury the
    ERRORs that are this plane's only failure channel."""
    publish(["w1", "w2"], interval_seconds=10)
    tv.art_mode = "off"

    with caplog.at_level(logging.INFO):
        for _ in range(6):
            await daemon.tick()
            clock.advance(10)

    reports = _events(caplog, "rotation.wall_not_ours")
    assert len(reports) == 1, f"a television in use was reported {len(reports)} times"


async def test_asking_whether_the_wall_is_ours_is_not_done_once_a_second(daemon: Wall, tv: FakeTv, publish, clock):
    """The check costs a request, and the poll interval is one second.

    Backing off is what makes a gate on every change affordable; without it an
    evening of television is tens of thousands of round trips at the set.
    """
    publish(["w1", "w2"], interval_seconds=10)
    tv.art_mode = "off"

    for _ in range(30):
        await daemon.tick()
        clock.advance(1)

    assert tv.art_mode_reads < 10, f"the set was asked {tv.art_mode_reads} times in thirty seconds"


async def test_the_backoff_starts_over_once_the_set_behaves_again(daemon: Wall, tv: FakeTv, publish, clock):
    """Otherwise unrelated dark spells compound.

    The wait doubles while the set ignores selections, which is right for one
    evening with the panel off. Carrying the grown wait past a recovery would
    mean the third brief spell in a week backing off five minutes — a wall that
    takes longer and longer to come back for no reason anyone could observe.

    One-second slots over thirty works, so no slot names the work already up,
    which the schedule rightly leaves alone without asking the set.
    """
    publish([f"w{n}" for n in range(30)], interval_seconds=1)
    tv.displays_nothing_selected = True

    await daemon.tick()  # attempt, then wait 5
    clock.advance(5)
    await daemon.tick()  # attempt, then wait 10

    tv.displays_nothing_selected = False
    clock.advance(10)
    await daemon.tick()
    assert tv.on_the_wall is not None, "the set started behaving and the wall did not come back"

    tv.displays_nothing_selected = True
    clock.advance(1)
    await daemon.tick()  # attempt, and the wait must be the floor again
    attempts = len(tv.selected)

    clock.advance(5)
    await daemon.tick()

    assert len(tv.selected) > attempts, "the wait carried its grown value across a recovery"


async def test_a_new_slot_does_not_re_ask_a_wall_the_backoff_is_holding_off(daemon: Wall, tv: FakeTv, publish, clock):
    """The other half of the wait, and the half that bites in the deployment.

    The two clocks are independent: the schedule moves on at its slots, the
    wall's wait on a ladder that doubles to five minutes. Once the ladder is
    longer than a slot, every slot in between would ask a television already
    known to be ignoring selections, which is the flood the ladder exists to stop.
    """
    publish(["w1", "w2"], interval_seconds=1)
    tv.displays_nothing_selected = True

    await daemon.tick()  # attempt, then wait 5
    clock.advance(5)
    await daemon.tick()  # attempt, then wait 10
    attempts = len(tv.selected)
    assert attempts == 2, "the ladder did not let the second attempt through"

    # A new slot on every one of these; the wall's wait is not up until t=15.
    for _ in range(9):
        clock.advance(1)
        await daemon.tick()

    assert len(tv.selected) == attempts, "a new slot asked a wall the backoff was holding off"


# -- a republished schedule: how `show_now` and `next` arrive --------------------
#
# A curator's `show_now` or `next` reaches the wall as a new feed whose slot now
# names another work. It is state, not a command: nothing is consumed, so a
# change the wall could not make is still owed on the next pass, and is made
# once the wall can — never lost, and never asked for once a second.


async def test_a_republished_schedule_reaches_the_wall_at_once(daemon: Wall, tv: FakeTv, publish):
    publish(["w1", "w2", "w3"])
    await daemon.tick()

    publish(["w3", "w1", "w2"])
    await daemon.tick()

    assert publish.work_of(tv.on_the_wall) == "w3"


async def test_a_republished_schedule_is_not_lost_while_the_television_is_asleep(
    daemon: Wall, tv: FakeTv, publish, state: DisplayState, clock
):
    """An outage delays the change, never eats it."""
    publish(["w1", "w2", "w3"], interval_seconds=3600)
    await daemon.tick()

    tv.unavailable = True
    publish(["w3", "w1", "w2"], interval_seconds=3600)
    await daemon.tick()
    assert state.last_selected_work_id == "w1"

    tv.unavailable = False
    clock.advance(301)
    await daemon.tick()

    assert publish.work_of(tv.on_the_wall) == "w3"
    assert state.last_selected_work_id == "w3"


async def test_a_change_is_not_lost_when_the_set_drops_mid_selection(daemon: Wall, tv: FakeTv, publish, state: DisplayState):
    """The set answers at the top of the pass and is gone by the selection.

    The wall's memory is written only once the set has shown the work, so the
    next pass, with the set back, still owes it.
    """
    publish(["w1", "w2", "w3"])
    await daemon.tick()
    assert publish.work_of(tv.on_the_wall) == "w1"
    await daemon.tick()  # the pass that uploads w2, one upload per pass
    doomed = state.binding_for("w2").tv_content_id

    tv.refuse_selection_of.add(doomed)
    publish(["w2", "w3", "w1"])
    await daemon.tick()
    assert state.last_selected_work_id == "w1", "a change the set never performed was recorded as made"

    tv.refuse_selection_of.clear()
    for _ in range(3):
        await daemon.tick()

    assert publish.work_of(tv.on_the_wall) == "w2", "the change was lost to a momentary drop"


async def test_a_republished_schedule_is_not_put_on_a_television_somebody_is_watching(
    daemon: Wall, tv: FakeTv, publish, state: DisplayState
):
    """A change is still a selection, and a selection takes the screen. Held, and delivered when the set returns to art mode."""
    publish(["w1", "w2", "w3"])
    await daemon.tick()
    tv.art_mode = "off"
    publish(["w3", "w1", "w2"])
    await daemon.tick()
    assert [publish.work_of(tv.holding[c]) for c in tv.selected] == ["w1"], "the wall took the screen off whoever was watching"

    tv.art_mode = "on"
    tv.art_mode_announced = True
    await daemon.tick()

    assert publish.work_of(tv.on_the_wall) == "w3", "the change was lost while the television was in use"


async def test_a_held_back_change_does_not_ask_the_set_once_a_second(daemon: Wall, tv: FakeTv, publish, clock):
    """A change still owed is still owed on the next poll, so the wait has to be read before the ask.

    Asking whether the wall is ours costs a real request — putting it in front
    of the backoff spends thousands of them across one programme.
    """
    publish(["w1", "w2", "w3"])
    await daemon.tick()

    tv.art_mode = "off"
    publish(["w3", "w1", "w2"])
    before = tv.art_mode_reads
    for _ in range(30):
        await daemon.tick()
        clock.advance(1)

    asked = tv.art_mode_reads - before
    assert asked < 10, f"a change held back asked the set {asked} times in thirty seconds"


async def test_a_change_against_a_dark_wall_is_not_re_attempted_every_poll(daemon: Wall, tv: FakeTv, publish, clock):
    """Each attempt is a selection the television is going to ignore, followed by
    the whole confirmation window spent waiting for an announcement that will
    never come — all night, at one second apart, without the ladder."""
    publish(["w1", "w2", "w3"])
    await daemon.tick()

    tv.displays_nothing_selected = True
    publish(["w3", "w1", "w2"])
    before = len(tv.selected)
    for _ in range(10):
        await daemon.tick()
        clock.advance(1)

    # Ten polls, and the retry floor is five seconds: two attempts, not ten. The
    # assertion is against the *ladder* rather than a number of seconds, because
    # what is being fixed is the cadence being the poll's.
    attempts = len(tv.selected) - before
    assert attempts == 2, f"the change was attempted {attempts} times in ten one-second polls"
