"""The schedule's rules, as properties over every set of walls and as the cases that name them.

The properties are the contract's own (`player-contract.md` § Rules a schema
cannot state, § Time) plus the two this module adds: the household rule and
stability. Each example below pins a case the properties reach only by luck, so
none of them is left undefended by a run that happened not to draw it.
"""

from datetime import UTC, datetime, timedelta
from itertools import pairwise

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from arrt.programming.schedule import (
    HORIZON,
    Keep,
    Slot,
    StartFresh,
    build,
    household_pass,
    movable_walls,
    run_household_pass,
)

NOW = datetime(2026, 10, 9, 18, 30, 15, 123456, tzinfo=UTC)
AT = NOW.replace(microsecond=0)


def _wall(work_ids, *, slot_seconds=180, shuffle=False, now=NOW, start=None, previous=(), elsewhere=None, seed="w", also=()):
    return build(
        wall_id="here",
        work_ids=work_ids,
        slot_seconds=slot_seconds,
        shuffle=shuffle,
        now=now,
        start=start if start is not None else StartFresh(),
        published={**(elsewhere or {}), "here": previous},
        seed=seed,
        also_showable=also,
    )


def _shown_elsewhere(slot, others):
    return any(o.work_id == slot.work_id and o.overlaps(slot.start, slot.until) for o in others)


works = st.lists(st.sampled_from([f"w{i}" for i in range(8)]), min_size=1, max_size=8, unique=True)
# Fifteen minutes up: a shorter slot adds slots, not cases, and the checks below
# are quadratic in them.
seconds = st.integers(min_value=900, max_value=6 * 3600)


def _contract_rules_hold(schedule):
    assert (schedule.horizon_until - schedule.horizon_from) % timedelta(days=1) == timedelta(0)
    assert schedule.horizon_until - schedule.horizon_from == HORIZON
    for slot in schedule.slots:
        assert slot.start < slot.until
        assert schedule.horizon_from <= slot.start
        assert slot.until <= schedule.horizon_until
    for earlier, later in pairwise(schedule.slots):
        # Abutting, not merely ordered: the schedule has no dark hours yet, and a
        # gap would tell a Player with power control to send the set to sleep.
        assert earlier.until == later.start


@settings(max_examples=150, deadline=None)
@given(work_ids=works, slot_seconds=seconds, shuffle=st.booleans(), seed=st.text(max_size=4))
def test_every_schedule_keeps_the_contract_rules(work_ids, slot_seconds, shuffle, seed):
    schedule = _wall(work_ids, slot_seconds=slot_seconds, shuffle=shuffle, seed=seed)

    _contract_rules_hold(schedule)
    assert schedule.horizon_from == AT
    assert schedule.slots[-1].until == schedule.horizon_until


@settings(max_examples=150, deadline=None)
@given(work_ids=works, slot_seconds=seconds, shuffle=st.booleans(), seed=st.text(max_size=4))
def test_every_work_comes_up_once_before_any_repeats_and_never_twice_running(work_ids, slot_seconds, shuffle, seed):
    shown = [slot.work_id for slot in _wall(work_ids, slot_seconds=slot_seconds, shuffle=shuffle, seed=seed).slots]

    n = len(work_ids)
    whole_cycles = len(shown) // n
    for k in range(whole_cycles):
        assert sorted(shown[k * n : (k + 1) * n]) == sorted(work_ids)
    if n > 1:
        assert all(a != b for a, b in pairwise(shown))


@settings(max_examples=150, deadline=None)
@given(
    mine=works,
    theirs=works,
    mine_seconds=seconds,
    theirs_seconds=seconds,
    shuffle=st.booleans(),
    seed=st.text(max_size=4),
    later=st.none() | st.integers(min_value=0, max_value=int(HORIZON.total_seconds()) - 1),
)
def test_a_work_is_on_two_walls_at_once_only_as_a_named_clash(mine, theirs, mine_seconds, theirs_seconds, shuffle, seed, later):
    other = _wall(theirs, slot_seconds=theirs_seconds, shuffle=shuffle, seed="other")
    schedule = _wall(mine, slot_seconds=mine_seconds, shuffle=shuffle, seed=seed, elsewhere={"other": other.slots})
    if later is not None:
        # A keep rebuild carries a slot over; the rule must hold for it as well
        # as for the slots built fresh around it.
        schedule = _wall(
            mine,
            slot_seconds=mine_seconds,
            shuffle=shuffle,
            seed=seed,
            now=NOW + timedelta(seconds=later),
            start=Keep(),
            previous=schedule.slots,
            elsewhere={"other": other.slots},
        )

    named = {(c.work_id, c.start, c.until) for c in schedule.clashes}
    for slot in schedule.slots:
        if _shown_elsewhere(slot, other.slots):
            assert (slot.work_id, slot.start, slot.until) in named
    for clash in schedule.clashes:
        assert clash.other_wall_id == "other"
        # The rule's real claim: a clash only where no work of this wall could
        # have gone in that slot without one.
        for candidate in mine:
            assert any(o.work_id == candidate and o.overlaps(clash.start, clash.until) for o in other.slots)
    _contract_rules_hold(schedule)


@settings(max_examples=150, deadline=None)
@given(
    work_ids=works,
    slot_seconds=seconds,
    shuffle=st.booleans(),
    later=st.integers(min_value=0, max_value=int(HORIZON.total_seconds()) - 1),
)
def test_a_kept_rebuild_leaves_the_slot_on_the_wall_untouched(work_ids, slot_seconds, shuffle, later):
    first = _wall(work_ids, slot_seconds=slot_seconds, shuffle=shuffle)
    then = NOW + timedelta(seconds=later)
    on_the_wall = next(slot for slot in first.slots if slot.covers(then.replace(microsecond=0)))

    rebuilt = _wall(work_ids, slot_seconds=slot_seconds, shuffle=shuffle, now=then, start=Keep(), previous=first.slots)

    assert rebuilt.slots[0] == on_the_wall
    assert rebuilt.horizon_from == on_the_wall.start
    _contract_rules_hold(rebuilt)
    if len(work_ids) > 1:
        assert rebuilt.slots[1].work_id != on_the_wall.work_id


@settings(max_examples=100, deadline=None)
@given(work_ids=works, slot_seconds=seconds, shuffle=st.booleans(), data=st.data())
def test_starting_fresh_begins_now_with_the_work_asked_for(work_ids, slot_seconds, shuffle, data):
    first = data.draw(st.sampled_from([*work_ids, "not-in-the-theme"]))
    previous = _wall(work_ids, slot_seconds=slot_seconds, shuffle=shuffle, now=NOW - timedelta(hours=1)).slots

    schedule = _wall(work_ids, slot_seconds=slot_seconds, shuffle=shuffle, start=StartFresh(first), previous=previous)

    assert schedule.slots[0] == Slot(first, AT, AT + timedelta(seconds=slot_seconds))
    assert schedule.horizon_from == AT
    _contract_rules_hold(schedule)


def test_one_work_hanging_on_two_walls_is_shown_on_both_and_the_clash_is_named():
    other = _wall(["solo"], seed="other")

    schedule = _wall(["solo"], elsewhere={"living-room": other.slots})

    assert {slot.work_id for slot in schedule.slots} == {"solo"}
    assert len(schedule.clashes) == len(schedule.slots)
    assert {clash.other_wall_id for clash in schedule.clashes} == {"living-room"}


def test_a_shared_work_is_passed_over_while_another_work_can_go_there():
    other = _wall(["shared", "theirs"], seed="other")

    schedule = _wall(["shared", "mine"], elsewhere={"living-room": other.slots})

    assert schedule.clashes == ()
    for slot in schedule.slots:
        assert not _shown_elsewhere(slot, other.slots)


def test_walls_with_different_slot_lengths_still_never_overlap_a_work():
    other = _wall(["a", "b", "c"], slot_seconds=300, seed="other")

    schedule = _wall(["a", "b", "c"], slot_seconds=180, elsewhere={"study": other.slots})

    assert schedule.clashes == ()
    for slot in schedule.slots:
        assert not _shown_elsewhere(slot, other.slots)


def test_an_empty_theme_publishes_a_horizon_with_no_slots():
    schedule = _wall([])

    assert schedule.slots == ()
    assert schedule.horizon_until - schedule.horizon_from == HORIZON


def test_a_kept_rebuild_starts_fresh_when_the_work_on_the_wall_has_left_it():
    first = _wall(["gone", "stays"])
    assert first.slots[0].work_id == "gone"

    rebuilt = _wall(["stays"], now=NOW + timedelta(seconds=10), start=Keep(), previous=first.slots)

    assert rebuilt.slots[0].work_id == "stays"
    assert rebuilt.horizon_from == AT + timedelta(seconds=10)


def test_a_kept_rebuild_with_nothing_on_the_wall_starts_at_now():
    rebuilt = _wall(["a", "b"], start=Keep(), previous=())

    assert rebuilt.horizon_from == AT
    assert rebuilt.slots[0].start == AT


def test_a_rotation_carries_on_from_the_kept_work_rather_than_from_the_top():
    first = _wall(["a", "b", "c", "d"])
    on_the_wall = first.slots[2]
    assert on_the_wall.work_id == "c"

    rebuilt = _wall(["a", "b", "c", "d"], now=on_the_wall.start + timedelta(seconds=1), start=Keep(), previous=first.slots)

    assert [slot.work_id for slot in rebuilt.slots[:4]] == ["c", "d", "a", "b"]


def test_the_last_slot_is_cut_at_the_horizon():
    # A seven-hour slot does not divide three days, so the last one is short.
    schedule = _wall(["a", "b"], slot_seconds=7 * 3600)

    assert schedule.slots[-1].until == schedule.horizon_until
    assert schedule.slots[-1].until - schedule.slots[-1].start < timedelta(hours=7)


def test_the_same_inputs_give_the_same_shuffle_and_another_seed_another():
    many = [f"w{i}" for i in range(8)]

    one = _wall(many, shuffle=True, seed="x")
    again = _wall(many, shuffle=True, seed="x")
    other = _wall(many, shuffle=True, seed="y")

    assert one == again
    assert [s.work_id for s in one.slots] != [s.work_id for s in other.slots]


def test_instants_are_whole_seconds():
    schedule = _wall(["a"])

    assert all(slot.start.microsecond == 0 and slot.until.microsecond == 0 for slot in schedule.slots)


@pytest.mark.parametrize("slot_seconds", [0, -5])
def test_a_slot_must_last_a_positive_time(slot_seconds):
    with pytest.raises(ValueError, match="positive"):
        _wall(["a"], slot_seconds=slot_seconds)


def test_now_must_be_absolute():
    with pytest.raises(ValueError, match="time zone"):
        _wall(["a"], now=datetime(2026, 10, 9, 18, 30))  # noqa: DTZ001 -- the naive instant is the case under test


def test_a_wall_naming_a_work_twice_is_refused():
    with pytest.raises(ValueError, match="once"):
        _wall(["a", "b", "a"])


def test_a_first_slot_longer_than_the_horizon_is_cut_at_it():
    schedule = _wall(["a", "b"], slot_seconds=4 * 24 * 3600, start=StartFresh("a"))

    assert schedule.slots == (Slot("a", AT, AT + HORIZON),)


def test_showing_a_work_another_wall_shows_now_names_the_clash():
    other = _wall(["shared", "theirs"], seed="other")
    assert other.slots[0].work_id == "shared"

    schedule = _wall(["shared", "mine"], start=StartFresh("shared"), elsewhere={"living-room": other.slots})

    assert schedule.slots[0].work_id == "shared"
    assert [(c.work_id, c.start, c.other_wall_id) for c in schedule.clashes] == [("shared", AT, "living-room")]


def test_a_rotation_carries_on_after_the_work_shown_now():
    schedule = _wall(["a", "b", "c", "d"], start=StartFresh("b"))

    assert [slot.work_id for slot in schedule.slots[:5]] == ["b", "c", "d", "a", "b"]


def test_a_rebuild_at_the_instant_a_slot_ends_keeps_the_slot_that_begins_there():
    first = _wall(["a", "b", "c"])
    boundary = first.slots[1].start

    rebuilt = _wall(["a", "b", "c"], now=boundary, start=Keep(), previous=first.slots)

    assert rebuilt.slots[0] == first.slots[1]
    assert rebuilt.horizon_from == boundary


def test_a_shuffled_cycle_after_a_kept_work_shows_each_other_work_once_first():
    many = [f"w{i}" for i in range(6)]
    first = _wall(many, shuffle=True)
    kept = first.slots[0]

    rebuilt = _wall(many, shuffle=True, now=NOW + timedelta(seconds=5), start=Keep(), previous=first.slots, seed="z")

    assert rebuilt.slots[0] == kept
    assert sorted(slot.work_id for slot in rebuilt.slots[1:6]) == sorted(set(many) - {kept.work_id})


def test_when_the_cycle_cannot_fit_a_work_shown_earlier_comes_up_before_the_one_just_shown():
    # a, then b; then c is shown elsewhere, and both a and b are free. The work
    # shown longer ago goes up, not the one that has just come down.
    busy = {"study": [Slot("c", AT + timedelta(seconds=200), AT + timedelta(seconds=300))]}

    schedule = _wall(["a", "b", "c"], slot_seconds=100, elsewhere=busy)

    assert [slot.work_id for slot in schedule.slots[:3]] == ["a", "b", "a"]
    assert schedule.clashes == ()


def test_a_kept_slot_still_names_its_clash():
    other = _wall(["solo"], seed="other")
    first = _wall(["solo"], elsewhere={"living-room": other.slots})

    rebuilt = _wall(
        ["solo"], now=NOW + timedelta(seconds=5), start=Keep(), previous=first.slots, elsewhere={"living-room": other.slots}
    )

    assert rebuilt.slots[0] == first.slots[0]
    assert (rebuilt.slots[0].start, "living-room") in {(c.start, c.other_wall_id) for c in rebuilt.clashes}


def test_a_work_shown_now_from_outside_the_theme_survives_a_kept_rebuild():
    first = _wall(["a", "b"], start=StartFresh("guest"))

    rebuilt = _wall(["a", "b"], now=NOW + timedelta(seconds=5), start=Keep(), previous=first.slots, also={"guest"})
    cut = _wall(["a", "b"], now=NOW + timedelta(seconds=5), start=Keep(), previous=first.slots)

    assert rebuilt.slots[0] == first.slots[0] == Slot("guest", AT, AT + timedelta(seconds=180))
    assert cut.slots[0].work_id != "guest"


def test_a_wall_never_clashes_with_its_own_published_slots():
    first = _wall(["solo"])

    rebuilt = _wall(["solo"], now=NOW + timedelta(seconds=5), start=Keep(), previous=first.slots)

    assert rebuilt.clashes == ()


# -- a household pass: the wall republished, then the walls sharing a work with it ---------
#
# What `DisplayService` does when it writes a wall: the wall is built against only
# the slot covering now on each neighbour, and each neighbour is then rebuilt,
# keeping that slot, against the walls already rebuilt and lined up with the wall
# just built. Without the pass, two walls sharing two works lock: each is built
# against the other's single-work schedule, and the only schedule the household
# rule then allows is the mirror image.


HOUR = 3600


def _household_pass(walls, *, target, now, published, start=None, refused=()):
    """Rebuild `target` and every other wall in `walls` as one pass, through the pass the service runs.

    `run_household_pass` makes the builds; this says only how one wall is built,
    in the theme's order from its id as seed. A wall in `refused` cannot be
    rebuilt, as when its theme cannot be read, and keeps its published slots.
    Returns every wall's schedule that was rebuilt.
    """
    neighbours = sorted(wall for wall in walls if wall != target)
    works = {wall_id: work_ids for wall_id, (work_ids, _) in walls.items()}

    def _build(wall_id, view, *, start, also=()):
        work_ids, slot_seconds = walls[wall_id]
        return build(
            wall_id=wall_id,
            work_ids=work_ids,
            slot_seconds=slot_seconds,
            shuffle=False,
            now=now,
            start=start,
            published=view.published,
            seed=wall_id,
            also_showable=also,
            movable=view.movable,
            align_to=view.align_to,
        )

    return run_household_pass(
        target,
        neighbours,
        start=start or Keep(),
        movable=movable_walls(target, neighbours, works),
        slot_seconds={wall_id: seconds for wall_id, (_, seconds) in walls.items()},
        works=works,
        published=published,
        build_republished=lambda view, start, also: _build(target, view, start=start, also=also),
        build_neighbour=lambda wall_id, view: None if wall_id in refused else _build(wall_id, view, start=Keep()),
    )


def _single_work(wall_id, work_id, *, offset, slot_seconds=HOUR):
    """A wall locked onto one work for a horizon, its slots starting `offset` seconds after NOW."""
    start = AT + timedelta(seconds=offset)
    length = timedelta(seconds=slot_seconds)
    slots = [Slot(work_id, start + i * length, start + (i + 1) * length) for i in range(HORIZON // length + 1)]
    return [Slot(work_id, start - length, start), *slots]


@settings(max_examples=150, deadline=None)
@given(
    hall_offset=st.integers(min_value=1, max_value=HOUR),
    study_offset=st.integers(min_value=1, max_value=HOUR),
    target=st.sampled_from(["hall", "study"]),
)
def test_two_walls_locked_on_one_work_each_are_unlocked_by_one_pass(hall_offset, study_offset, target):
    """#350: the walls share only `a` and `b`, one shows `a` throughout and the other `b`."""
    walls = {"hall": (["a", "b"], HOUR), "study": (["a", "b"], HOUR)}
    locked = {"hall": _single_work("hall", "a", offset=hall_offset), "study": _single_work("study", "b", offset=study_offset)}

    built = _household_pass(walls, target=target, now=NOW, published=locked)

    for schedule in built.values():
        assert {slot.work_id for slot in schedule.slots} == {"a", "b"}
        assert schedule.clashes == ()
        _contract_rules_hold(schedule)
    for slot in built["hall"].slots:
        assert not _shown_elsewhere(slot, built["study"].slots)


@settings(max_examples=100, deadline=None)
@given(
    hall_offset=st.integers(min_value=1, max_value=HOUR),
    study_offset=st.integers(min_value=1, max_value=HOUR),
    targets=st.lists(st.sampled_from(["hall", "study"]), min_size=2, max_size=6),
    gaps=st.lists(st.integers(min_value=1, max_value=4 * HOUR), min_size=6, max_size=6),
)
def test_repeated_passes_from_either_wall_never_lock_again(hall_offset, study_offset, targets, gaps):
    """Multi-hop: a roll, a hang, a step on either wall, each a pass of its own, later each time."""
    walls = {"hall": (["a", "b"], HOUR), "study": (["a", "b"], HOUR)}
    published = {"hall": _single_work("hall", "a", offset=hall_offset), "study": _single_work("study", "b", offset=study_offset)}
    now = NOW
    for target, gap in zip(targets, gaps, strict=False):
        now += timedelta(seconds=gap)
        published = {wall: s.slots for wall, s in _household_pass(walls, target=target, now=now, published=published).items()}
        for slots in published.values():
            assert {slot.work_id for slot in slots} == {"a", "b"}
        for slot in published["hall"]:
            assert not _shown_elsewhere(slot, published["study"])


@settings(max_examples=150, deadline=None)
@given(
    walls=st.dictionaries(
        st.sampled_from(["hall", "study", "kitchen"]),
        st.tuples(works, st.sampled_from([900, 1800, HOUR, 2 * HOUR])),
        min_size=2,
        max_size=3,
    ),
    data=st.data(),
)
def test_after_a_pass_every_overlap_between_walls_is_a_named_clash(walls, data):
    """The household rule across the pass: whatever the wall just built did not see, its neighbour names."""
    target = data.draw(st.sampled_from(sorted(walls)))
    first = {
        wall_id: build(
            wall_id=wall_id,
            work_ids=work_ids,
            slot_seconds=slot_seconds,
            shuffle=False,
            now=NOW - timedelta(seconds=data.draw(st.integers(min_value=0, max_value=4 * HOUR))),
            start=StartFresh(),
            published={},
            seed=wall_id,
        ).slots
        for wall_id, (work_ids, slot_seconds) in walls.items()
    }

    built = _household_pass(walls, target=target, now=NOW, published=first)

    for wall_id, schedule in built.items():
        _contract_rules_hold(schedule)
        named = {(c.work_id, c.start, c.other_wall_id) for c in schedule.clashes}
        for other_id, other in built.items():
            if other_id == wall_id:
                continue
            for slot in schedule.slots:
                if _shown_elsewhere(slot, other.slots):
                    # Named on one side or the other: by the later-built wall, which saw the earlier one whole.
                    theirs = {(c.work_id, c.start, c.other_wall_id) for c in other.clashes}
                    assert (slot.work_id, slot.start, other_id) in named or any(
                        w == slot.work_id and o == wall_id and _overlapping(other.slots, s, slot) for w, s, o in theirs
                    )


def _overlapping(slots, start, slot):
    return any(s.start == start and s.overlaps(slot.start, slot.until) for s in slots)


def _fresh(walls, offsets):
    """Each wall's schedule as if published on its own `offsets[wall]` seconds before NOW, against nothing."""
    return {
        wall_id: build(
            wall_id=wall_id,
            work_ids=work_ids,
            slot_seconds=slot_seconds,
            shuffle=False,
            now=NOW - timedelta(seconds=offsets[wall_id]),
            start=StartFresh(),
            published={},
            seed=wall_id,
        ).slots
        for wall_id, (work_ids, slot_seconds) in walls.items()
    }


def _apart_after_now(built, now):
    """Every overlap between two walls' slots, leaving out only a pair both on their walls at `now`.

    Two pictures up now are kept whatever either shows, so their clash is no
    pass's to avoid; a slot to come on either wall meeting one of them is.
    """
    return [
        (wall_id, slot)
        for wall_id, schedule in built.items()
        for other_id, other in built.items()
        if other_id != wall_id
        for slot in schedule.slots
        if any(
            s.work_id == slot.work_id and s.overlaps(slot.start, slot.until) and not (slot.covers(now) and s.covers(now))
            for s in other.slots
        )
    ]


@settings(max_examples=150, deadline=None)
@given(
    hall_offset=st.integers(min_value=0, max_value=2 * HOUR),
    study_offset=st.integers(min_value=0, max_value=2 * HOUR),
    hall_seconds=st.sampled_from([900, 1800, HOUR]),
    times=st.sampled_from([2, 3, 4]),
)
def test_a_wall_quicker_than_its_neighbour_takes_turns_inside_the_neighbours_slots(
    hall_offset, study_offset, hall_seconds, times
):
    """#374, case A: republished at a quicker pace than the study, the two sharing only `a` and `b`.

    Built first, the hall alternated the two at its own pace, and each of the
    study's longer slots then spanned one of each. A clash-free schedule exists:
    the hall shows one work for as many of its slots as fit in one of the
    study's, while the study shows the other.
    """
    walls = {"hall": (["a", "b"], hall_seconds), "study": (["a", "b"], hall_seconds * times)}
    first = _fresh(walls, {"hall": hall_offset, "study": study_offset})

    built = _household_pass(walls, target="hall", now=NOW, published=first)

    assert _apart_after_now(built, AT) == []
    for schedule in built.values():
        _contract_rules_hold(schedule)
        assert {slot.work_id for slot in schedule.slots} == {"a", "b"}
    on_the_study = next(slot for slot in first["study"] if slot.covers(AT))
    kept = built["study"].slots[0]
    assert (kept.work_id, kept.start) == (on_the_study.work_id, on_the_study.start)
    assert kept.until - kept.start < 2 * timedelta(seconds=hall_seconds * times)


@settings(max_examples=200, deadline=None)
@given(
    hall=st.lists(st.sampled_from(["p", "q", "r", "s"]), min_size=2, max_size=4, unique=True),
    study=st.lists(st.sampled_from(["p", "q", "r", "s"]), min_size=2, max_size=4, unique=True),
    base=st.sampled_from([900, 1800, HOUR]),
    times=st.sampled_from([1, 2, 3, 4]),
    quicker=st.sampled_from(["hall", "study"]),
    target=st.sampled_from(["hall", "study"]),
    offsets=st.fixed_dictionaries({wall: st.integers(min_value=0, max_value=2 * HOUR) for wall in ("hall", "study")}),
)
def test_two_walls_each_with_two_works_never_clash_after_a_pass_when_one_pace_divides_the_other(
    hall, study, base, times, quicker, target, offsets
):
    """Some schedule always keeps two such walls apart, so a pass from either wall finds one."""
    seconds = {"hall": base, "study": base * times} if quicker == "hall" else {"hall": base * times, "study": base}
    walls = {"hall": (hall, seconds["hall"]), "study": (study, seconds["study"])}

    built = _household_pass(walls, target=target, now=NOW, published=_fresh(walls, offsets))

    assert _apart_after_now(built, AT) == []


def _case_b(three):
    """#374, case B: `a` holds x and y; the neighbour `three` holds x, w and v; the other y and w."""
    two = "n2" if three == "n1" else "n1"
    return {"a": (["x", "y"], HOUR), three: (["x", "w", "v"], HOUR), two: (["y", "w"], HOUR)}


@pytest.mark.parametrize("three", ["n1", "n2"])
@pytest.mark.parametrize(
    "offsets",
    [
        # Published together, and four households found clashing when built in id order.
        {"a": 0, "n1": 0, "n2": 0},
        {"a": 1857, "n1": 3034, "n2": 3075},
        {"a": 1351, "n1": 3424, "n2": 5650},
        {"a": 634, "n1": 1749, "n2": 1184},
        {"a": 1719, "n1": 2127, "n2": 3157},
    ],
)
def test_a_neighbour_with_a_work_to_spare_leaves_the_shared_one_to_the_neighbour_without(offsets, three):
    """Rebuilt in id order, the neighbour with three works could take `w` while `a` showed `y`, leaving the other nothing.

    Whichever comes first by id, the neighbour with fewer works to go to is
    built first. Not a property over every offset: see the case below.
    """
    walls = _case_b(three)

    built = _household_pass(walls, target="a", now=NOW, published=_fresh(walls, offsets))

    assert _apart_after_now(built, AT) == []
    for schedule in built.values():
        _contract_rules_hold(schedule)


@settings(max_examples=150, deadline=None)
@given(
    offsets=st.fixed_dictionaries({wall: st.integers(min_value=0, max_value=2 * HOUR) for wall in ("a", "n1", "n2")}),
    three=st.sampled_from(["n1", "n2"]),
)
def test_a_wall_republished_with_a_work_to_spare_is_built_after_the_neighbour_without(offsets, three):
    """Case B republished from the wall with three works: the neighbour with two to go to is built before it."""
    walls = _case_b(three)

    built = _household_pass(walls, target=three, now=NOW, published=_fresh(walls, offsets))

    assert _apart_after_now(built, AT) == []


#: Case B with `a` republished, in a household the pass cannot keep apart though some schedule would.
#: `a` keeps `x` until :41. `n2` shows `w` now; so does `n1`, until :42. At :41
#: `a` goes on to `y`, built against only the slot now on each neighbour, and
#: `n2`, built next, can show neither `y` nor `w` from :41 to :42. Had `a`
#: shown `x` again, `n2` could have shown `y`, and `n1` `v`.
_CASE_B_UNKEPT = {"a": 1100, "n1": 4662, "n2": 6942}


@pytest.mark.xfail(
    strict=True,
    reason=(
        "#374's limit, #436: the pass builds one wall at a time and looks no further ahead than the slot now on "
        "the walls to come, so three walls coupled through it can clash where some schedule would not"
    ),
)
def test_three_walls_a_pass_cannot_keep_apart_though_some_schedule_would():
    """The household `_CASE_B_UNKEPT` names. Strict, so a pass that keeps it apart says so by failing here."""
    walls = _case_b("n1")

    built = _household_pass(walls, target="a", now=NOW, published=_fresh(walls, _CASE_B_UNKEPT))

    assert _apart_after_now(built, AT) == []


def test_where_a_pass_cannot_keep_three_walls_apart_the_wall_built_later_names_the_clash():
    """The same household: each overlap past the pictures now is a clash the later-built of its two walls names.

    Not the clash between two pictures up now, which every pass names and none
    can avoid, but each one a pass made: so a pass that stops saying where the
    rule gives way fails here, and one that keeps these walls apart passes.
    """
    walls = _case_b("n1")
    works = {wall_id: work_ids for wall_id, (work_ids, _) in walls.items()}
    neighbours = ["n1", "n2"]
    order = [
        step.wall_id
        for step in household_pass(
            "a",
            neighbours,
            movable=movable_walls("a", neighbours, works),
            slot_seconds=dict.fromkeys(walls, HOUR),
            works=works,
        )
    ]

    built = _household_pass(walls, target="a", now=NOW, published=_fresh(walls, _CASE_B_UNKEPT))

    for wall_id, slot in _apart_after_now(built, AT):
        named = {(c.work_id, c.start, c.other_wall_id) for c in built[wall_id].clashes}
        for earlier in order[: order.index(wall_id)]:
            if any(
                s.work_id == slot.work_id and s.overlaps(slot.start, slot.until) and not (slot.covers(AT) and s.covers(AT))
                for s in built[earlier].slots
            ):
                assert (slot.work_id, slot.start, earlier) in named


@settings(max_examples=100, deadline=None)
@given(
    offsets=st.fixed_dictionaries({wall: st.integers(min_value=0, max_value=2 * HOUR) for wall in ("hall", "kitchen", "study")})
)
def test_two_slower_neighbours_sharing_works_line_up_with_each_other(offsets):
    """The hall changes every quarter hour; the kitchen hourly and the study every two hours, sharing `a` and `b`.

    Each slower wall is built before the hall, and the kitchen's slots must
    fall inside the study's: lined up with the hall's quarter hours alone, they
    could start a quarter hour off the study's and span both its works.
    """
    walls = {"hall": (["a", "b", "c"], 900), "kitchen": (["a", "b"], HOUR), "study": (["a", "b"], 2 * HOUR)}
    first = _fresh(walls, offsets)

    built = _household_pass(walls, target="hall", now=NOW, published=first)

    assert _apart_after_now(built, AT) == []


@settings(max_examples=150, deadline=None)
@given(
    hall=st.permutations(["x", "y"]),
    study=st.permutations(["x", "y"]),
    base=st.sampled_from([900, 1800, HOUR]),
    times=st.sampled_from([2, 3, 4]),
    study_offset=st.integers(min_value=0, max_value=4 * HOUR),
    start=st.sampled_from([Keep(), StartFresh(), StartFresh("x"), StartFresh("y")]),
)
def test_a_slower_neighbour_that_cannot_be_rebuilt_is_stepped_aside_from_by_the_wall_republished(
    hall, study, base, times, study_offset, start
):
    """The study, slower, is built first and refused; it keeps its published slots, and the hall steps aside from them.

    The two were published at different moments, as two walls hung by hand
    always are, so the study's slots start `study_offset` seconds off the
    hall's. Built against them with its own slots out of step, every hall slot
    spanning one of the study's boundaries meets both works the two share, and
    there is no stepping aside: half the hall's horizon clashes. Lined up with
    the study's published slots (`run_household_pass`), the hall's slot now
    runs on to the study's next boundary, and each slot after falls inside one
    of the study's. The hall's slot now is left out, as its picture is the
    act's to choose. Slower only: a neighbour at the hall's own pace is built
    after it, against its whole schedule, so its refusal leaves the hall built
    as if it would step aside (the kind of limit the pass has, not this one).
    """
    walls = {"hall": (hall, base), "study": (study, base * times)}
    published = _fresh(walls, {"hall": HOUR // 7, "study": study_offset})

    built = _household_pass(walls, target="hall", now=NOW, published=published, start=start, refused={"study"})

    assert set(built) == {"hall"}
    _contract_rules_hold(built["hall"])
    assert [
        slot
        for slot in built["hall"].slots
        if not slot.covers(AT)
        and any(s.work_id == slot.work_id and s.overlaps(slot.start, slot.until) for s in published["study"])
    ] == []


@settings(max_examples=100, deadline=None)
@given(hall_offset=st.integers(min_value=0, max_value=2 * HOUR), study_offset=st.integers(min_value=0, max_value=2 * HOUR))
def test_a_quicker_wall_with_one_work_is_built_first_and_the_slower_one_steps_aside(hall_offset, study_offset):
    """The hall can show only `a`, so it has nowhere to step aside to; the study, slower, shows `b` instead.

    Built before the hall against its slot now alone, the study would take
    turns with `a`, and the hall, with nothing else, would clash at every turn.
    The study's picture now is the one exception: kept, it may show `a` past
    the end of the hall's slot now, and the hall has nothing else to show then,
    so that clash is no pass's to avoid, and the hall names it.
    """
    walls = {"hall": (["a"], 1800), "study": (["a", "b"], HOUR)}
    first = _fresh(walls, {"hall": hall_offset, "study": study_offset})

    built = _household_pass(walls, target="hall", now=NOW, published=first)

    kept = built["study"].slots[0]
    named = {(clash.start, clash.other_wall_id) for clash in built["hall"].clashes}
    for wall_id, slot in _apart_after_now(built, AT):
        if wall_id == "study":
            assert slot == kept
        else:
            assert slot.overlaps(kept.start, kept.until)
            assert (slot.start, "study") in named


@pytest.mark.parametrize(
    ("seconds", "works", "order", "align_with"),
    [
        # One pace: the wall republished, then the neighbour with fewer works to go to.
        (
            {"here": 60, "n1": 60, "n2": 60},
            {"here": {"x", "y"}, "n1": {"x", "w", "v"}, "n2": {"y", "w"}},
            ["here", "n2", "n1"],
            [None, "here", "here"],
        ),
        # Slower walls first, slowest first, each lined up with the one before it.
        (
            {"here": 15, "n1": 60, "n2": 120, "n3": 15},
            {"here": {"a", "b"}, "n1": {"a", "b"}, "n2": {"a", "b"}, "n3": {"a", "b"}},
            ["n2", "n1", "here", "n3"],
            ["here", "n2", None, "here"],
        ),
        # A wall with one work to go to has no room to step aside, so it is built first.
        (
            {"here": 15, "n1": 60},
            {"here": {"a"}, "n1": {"a", "b"}},
            ["here", "n1"],
            [None, "here"],
        ),
    ],
)
def test_a_pass_builds_the_slowest_walls_first_when_the_wall_republished_can_step_aside(seconds, works, order, align_with):
    neighbours = [wall for wall in works if wall != "here"]
    movable = movable_walls("here", neighbours, works)

    steps = household_pass("here", neighbours, movable=movable, slot_seconds=seconds, works=works)

    assert [step.wall_id for step in steps] == order
    assert [step.align_with for step in steps] == align_with
    for at, step in enumerate(steps):
        assert step.movable == frozenset(order[at + 1 :]) & movable


def test_a_neighbour_with_no_room_counts_its_own_works_as_movable_walls_does():
    """`n1` can go only to `x`, `n2` to nothing, since `c`, outside the pass, always holds `w`.

    Neither is movable, and neither has the republished wall room either, so
    it is built first; then the neighbour with fewer works to go to. Counting a
    wall's own works as fixed against it would score both nothing and fall
    back to id order.
    """
    works = {"here": {"x", "y"}, "n1": {"x"}, "n2": {"w"}, "c": {"w"}}
    movable = movable_walls("here", ["n1", "n2"], works)

    steps = household_pass("here", ["n1", "n2"], movable=movable, slot_seconds=dict.fromkeys(works, 60), works=works)

    assert movable == frozenset()
    assert [step.wall_id for step in steps] == ["here", "n2", "n1"]


def test_a_movable_walls_slots_to_come_do_not_count_against_this_one():
    """The other wall shows `b` now and `a` next, and both reach into this wall's first slot."""
    other = [
        Slot("b", AT - timedelta(minutes=1), AT + timedelta(minutes=2)),
        Slot("a", AT + timedelta(minutes=2), AT + timedelta(minutes=5)),
    ]

    fixed = _wall(["a", "b"], elsewhere={"other": other})
    movable = build(
        wall_id="here",
        work_ids=["a", "b"],
        slot_seconds=180,
        shuffle=False,
        now=NOW,
        start=StartFresh(),
        published={"other": other, "here": ()},
        seed="w",
        movable={"other"},
    )

    assert fixed.clashes != ()
    assert movable.slots[0].work_id == "a"
    assert movable.clashes == ()


def test_the_kept_slot_runs_on_into_step_with_the_wall_just_built():
    previous = [Slot("b", AT - timedelta(minutes=1), AT + timedelta(minutes=2))]
    boundaries = [AT - timedelta(minutes=2) + timedelta(minutes=3) * i for i in range(10)]

    schedule = build(
        wall_id="here",
        work_ids=["a", "b"],
        slot_seconds=180,
        shuffle=False,
        now=NOW,
        start=Keep(),
        published={"here": previous},
        seed="w",
        align_to=boundaries,
    )

    assert schedule.slots[0] == Slot("b", AT - timedelta(minutes=1), AT + timedelta(minutes=4))
    assert all(slot.start in boundaries for slot in schedule.slots[1:] if slot.start <= boundaries[-1])
    assert schedule.slots[1].start == boundaries[2]


def test_the_kept_slot_is_not_lengthened_into_a_clash():
    previous = [Slot("b", AT - timedelta(minutes=1), AT + timedelta(minutes=2))]
    boundaries = [AT - timedelta(minutes=2) + timedelta(minutes=3) * i for i in range(10)]
    elsewhere = [Slot("b", AT + timedelta(minutes=3), AT + timedelta(minutes=6))]

    schedule = build(
        wall_id="here",
        work_ids=["a", "b"],
        slot_seconds=180,
        shuffle=False,
        now=NOW,
        start=Keep(),
        published={"here": previous, "other": elsewhere},
        seed="w",
        align_to=boundaries,
    )

    assert schedule.slots[0] == previous[0]


def test_the_kept_slot_steps_into_line_with_a_wall_changing_on_the_hour():
    """The next boundary is 58 minutes off, but a three-minute wall falls in step with it one minute on."""
    previous = [Slot("b", AT - timedelta(minutes=1), AT + timedelta(minutes=2))]
    boundaries = [AT + timedelta(hours=1) * i for i in range(-1, 4)]

    schedule = build(
        wall_id="here",
        work_ids=["a", "b"],
        slot_seconds=180,
        shuffle=False,
        now=NOW,
        start=Keep(),
        published={"here": previous},
        seed="w",
        align_to=boundaries,
    )

    assert schedule.slots[0] == Slot("b", AT - timedelta(minutes=1), AT + timedelta(minutes=3))
    assert {slot.start for slot in schedule.slots} >= set(boundaries[2:])


def test_a_slot_lengthened_once_is_not_lengthened_past_two_intervals():
    """Every step on the other wall is a pass, and each moves its boundaries."""
    already = [Slot("b", AT - timedelta(minutes=4), AT + timedelta(minutes=1))]
    boundaries = [AT + timedelta(seconds=150) + timedelta(minutes=3) * i for i in range(-2, 4)]

    schedule = build(
        wall_id="here",
        work_ids=["a", "b"],
        slot_seconds=180,
        shuffle=False,
        now=NOW,
        start=Keep(),
        published={"here": already},
        seed="w",
        align_to=boundaries,
    )

    assert schedule.slots[0] == already[0]


def test_a_kept_slot_already_clashing_is_run_on_into_step():
    """Both walls kept on `b`, the one work both could show: in step, the walls part after it."""
    previous = [Slot("b", AT - timedelta(minutes=1), AT + timedelta(minutes=2))]
    boundaries = [AT - timedelta(minutes=2) + timedelta(minutes=3) * i for i in range(10)]
    elsewhere = [Slot("b", AT - timedelta(minutes=2), AT + timedelta(minutes=4))]

    schedule = build(
        wall_id="here",
        work_ids=["a", "b"],
        slot_seconds=180,
        shuffle=False,
        now=NOW,
        start=Keep(),
        published={"here": previous, "other": elsewhere},
        seed="w",
        align_to=boundaries,
    )

    assert schedule.slots[0] == Slot("b", AT - timedelta(minutes=1), AT + timedelta(minutes=4))


# -- which neighbours can step aside ----------------------------------------------


@pytest.mark.parametrize(
    ("works", "movable"),
    [
        # Each holds both, so each can show the other.
        ({"here": {"x", "y"}, "n": {"x", "y"}}, {"n"}),
        # One work: nothing to step aside to.
        ({"here": {"x", "y"}, "n": {"x"}}, set()),
        # Two works, but a wall outside the pass always holds the other.
        ({"here": {"x", "y"}, "n": {"x", "z"}, "c": {"z"}}, set()),
        # The same, with the other held by a neighbour that is itself fixed.
        ({"here": {"x", "y"}, "n": {"x", "z"}, "m": {"z", "x"}, "c": {"z"}}, set()),
        # Found only by asking again: `m` can show only `y`, since `c` holds `w`,
        # and so `n` can show only `x`.
        ({"here": {"x", "y"}, "n": {"x", "y"}, "m": {"y", "w"}, "c": {"w"}}, set()),
        # A third work left free keeps it movable.
        ({"here": {"x", "y"}, "n": {"x", "z", "w"}, "c": {"z"}}, {"n"}),
        # The republished wall's own works never fix a neighbour.
        ({"here": {"x", "y", "z"}, "n": {"y", "z"}}, {"n"}),
    ],
)
def test_a_neighbour_is_movable_only_with_two_works_no_fixed_wall_holds(works, movable):
    neighbours = {wall for wall in works if wall not in ("here", "c")}

    assert movable_walls("here", neighbours, works) == movable
