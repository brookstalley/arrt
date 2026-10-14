"""A wall's schedule: which work is on it, from when until when, over the next three days.

Major 2 replaces the Player's own rotation with this (`player-contract.md`
§ Major 2). The Player shows whichever slot covers its clock and replays the
horizon if no fresh schedule arrives, so everything that used to be decided at the
wall — the order, the shuffle, how long a work stays — is decided here, once,
where every wall can be seen at the same moment.

**Pure.** Walls, works, the last published slots and *now* go in, slots come out.
No store, no clock, no Library: the household rule and the stability rule are
invariants over every set of walls, and a function with no I/O is what lets the
suite state them as properties rather than sampling them.

**Stability: a republish keeps the slot on the wall now** (`Keep`). Editing a
theme or rolling the horizon forward must not swap the picture mid-slot, so the
slot covering *now* in the last published schedule is carried over, its work and
its start unchanged, and the new schedule starts where it ends (a household pass
may run it on a little; below). The acts that *mean* "change what is on the
wall" — showing a work now, skipping on, hanging a theme — start fresh at *now*
instead (`StartFresh`).

**The household rule: no work on two walls at the same moment** (the owner,
2026-10-08, `re-architecture.md` § Order of work). One wall is built at a time,
against the slots every other wall has published: never choose a work whose span
overlaps that work's span on another wall, if any other work is available. When
none is, as with one work hanging on two walls, the wall shows it anyway and the
clash is returned by name. A wall left dark to satisfy a rule about variety would
be the worse failure, and a clash nobody hears about would be the silent one.

**A wall sharing works with the one republished is rebuilt with it** (the owner,
2026-10-13). Built against the other walls' whole schedules, two walls sharing
two works lock: one shows the first throughout because the other shows the
second throughout, and each rebuild of either answers the other with its mirror
image. So the caller rebuilds them as a pass. The wall republished is built
against only the slot covering now on each wall about to be rebuilt (`movable`),
since nothing after it is fixed yet; each of those is then rebuilt keeping that
slot, against the walls already rebuilt, with its slot now lengthened to the next
boundary of the wall just built, in step with its slots, where that is cheap and
clashes with nothing (`align_to`). Two walls whose slots start seconds apart
could otherwise not alternate two works at all: every slot of one would overlap
one of each on the other. Nothing on any screen changes: the slot covering now
keeps its work and its start, and may stay up under one interval longer (the
owner, 2026-10-14).

**What a pass cannot do.** It lines walls up only where one interval is a
multiple of the other. And it builds the republished wall first, so where that
wall's slots are shorter than a neighbour's and the two share nothing else, a
neighbour's long slot spans both works and the clash is named: the rule is kept
on the house's ordinary case, walls at one pace, and said where it gives way.
"""

import random
from bisect import bisect_left
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

#: How far ahead a home wall's schedule reaches (`player-contract.md` § Settled
#: before wave 4: the owner, 2026-10-08). Long enough to ride out a weekend with
#: the server down before the Player's replay takes over. The contract requires
#: whole days, because replay shifts by whole horizons and each slot has to keep
#: its time of day.
HORIZON: Final[timedelta] = timedelta(days=3)


@dataclass(frozen=True, slots=True)
class Slot:
    """One work on one wall over a half-open span: shown from `start`, gone at `until`."""

    work_id: str
    start: datetime
    until: datetime

    def covers(self, instant: datetime) -> bool:
        return self.start <= instant < self.until

    def overlaps(self, start: datetime, until: datetime) -> bool:
        return self.start < until and start < self.until


@dataclass(frozen=True, slots=True)
class Keep:
    """Carry the slot on the wall now over, and schedule from its end."""


@dataclass(frozen=True, slots=True)
class StartFresh:
    """Start the schedule at *now*, with this work first when one is named.

    The named work need not be one of the wall's works: showing a work that is not
    in the theme is allowed (`DisplayService.show_work_now`), and the document
    carries it because the schedule names it.
    """

    first_work_id: str | None = None


Start = Keep | StartFresh


@dataclass(frozen=True, slots=True)
class Clash:
    """A slot that shows a work while another wall shows it too, because nothing else could go there."""

    work_id: str
    start: datetime
    until: datetime
    #: The wall already showing it then.
    other_wall_id: str


@dataclass(frozen=True, slots=True)
class Schedule:
    horizon_from: datetime
    horizon_until: datetime
    slots: tuple[Slot, ...]
    clashes: tuple[Clash, ...]


def build(
    *,
    wall_id: str,
    work_ids: Sequence[str],
    slot_seconds: int,
    shuffle: bool,
    now: datetime,
    start: Start,
    published: Mapping[str, Sequence[Slot]],
    seed: str,
    also_showable: Collection[str] = (),
    movable: Collection[str] = (),
    align_to: Sequence[datetime] = (),
) -> Schedule:
    """One wall's schedule from `now` (or from the kept slot) to the end of the horizon.

    `work_ids` is the wall's works in the theme's order, each once. `published`
    is every wall's published slots by wall id, this wall's included: this wall's
    are what `Keep` keeps, and every other wall's are what the household rule is
    checked against. One map rather than two, so a caller cannot hand a wall its
    own slots as another wall's and have it clash with itself. `also_showable`
    names works a kept slot may hold although the cycle does not (a work shown
    now from outside the theme), so a theme edit does not cut it short. `seed`
    makes the shuffle reproducible, so a test and a rebuild from the same inputs
    agree.

    `movable` names other walls about to be rebuilt after this one, so only the
    slot covering now on each counts against this wall. `align_to` is the slot
    starts of the wall just built: a kept slot is lengthened to the first of them
    at or after its end, when that is less than one slot away and its work is
    shown nowhere else meanwhile, so the slots after it line up with that wall's.

    The last slot ends at the horizon even when that cuts it short: every slot
    must lie inside the horizon (`player-contract.md` § Rules a schema cannot
    state), and a replayed horizon starts again from its first slot anyway.
    """
    if slot_seconds <= 0:
        raise ValueError(f"A slot must last a positive number of seconds, not {slot_seconds}.")
    if now.tzinfo is None:
        raise ValueError("The schedule's instants are absolute, so now must carry a time zone.")
    if len(set(work_ids)) != len(work_ids):
        # A theme holds a work once (its memberships' key), so a repeat here is a
        # caller's bug, and a cycle built from it would show that work twice a turn.
        raise ValueError("A wall's works are each named once.")
    # Whole seconds: the document is compared by its bytes, and microseconds would
    # make two builds of the same schedule differ.
    now = now.replace(microsecond=0)
    length = timedelta(seconds=slot_seconds)
    rng = random.Random(seed)  # noqa: S311 -- an order for pictures, not a secret
    busy = _Busy(
        {
            other: [slot for slot in slots if slot.covers(now)] if other in movable else slots
            for other, slots in published.items()
            if other != wall_id
        }
    )

    slots: list[Slot] = []
    clashes: list[Clash] = []
    kept = _kept(published.get(wall_id, ()), now, {*work_ids, *also_showable}) if isinstance(start, Keep) else None
    if kept is not None:
        kept = _lengthened(kept, align_to, length, busy)
        horizon_from = kept.start
        slots.append(kept)
        # Checked again, not trusted: the other walls may have been rebuilt since
        # this slot was published, and a clash the last build named is still one.
        clashes.extend(busy.clashes(kept.work_id, kept.start, kept.until))
    else:
        horizon_from = now
    horizon_until = horizon_from + HORIZON

    order = _Order(work_ids, shuffle=shuffle, rng=rng)
    if kept is not None:
        order.after(kept.work_id)
    elif isinstance(start, StartFresh) and start.first_work_id is not None:
        first = start.first_work_id
        until = min(now + length, horizon_until)
        slots.append(Slot(first, now, until))
        clashes.extend(busy.clashes(first, now, until))
        order.after(first)

    cursor = slots[-1].until if slots else horizon_from
    if not work_ids:
        return Schedule(horizon_from, horizon_until, tuple(slots), tuple(clashes))
    while cursor < horizon_until:
        until = min(cursor + length, horizon_until)
        work_id = order.take(lambda candidate, s=cursor, u=until: not busy.clashes(candidate, s, u))
        slots.append(Slot(work_id, cursor, until))
        clashes.extend(busy.clashes(work_id, cursor, until))
        cursor = until
    return Schedule(horizon_from, horizon_until, tuple(slots), tuple(clashes))


def movable_walls(wall_id: str, neighbours: Collection[str], works: Mapping[str, Collection[str]]) -> frozenset[str]:
    """Which of a republished wall's neighbours have room to step aside, so only their slot now counts against it.

    A neighbour moves aside by showing another work, so it is movable only if
    it holds at least two works that no fixed wall holds: one wall with a single
    work, or whose others another wall always shows, has nowhere to go, and
    discounting its slots to come would send the republished wall onto the one
    work it can show and leave the two clashing. Fixed is every wall outside
    the pass, and any neighbour found not movable, asked again until nothing
    changes. Held is any work a wall's feed carries, at any time; that is coarse
    in the safe direction, since a wall wrongly thought fixed is built as it
    was before a pass existed.
    """
    movable = set(neighbours)
    while True:
        fixed = {work_id for other, held in works.items() if other != wall_id and other not in movable for work_id in held}
        still = {neighbour for neighbour in movable if len(set(works.get(neighbour, ())) - fixed) > 1}
        if still == movable:
            return frozenset(movable)
        movable = still


def _kept(previous: Sequence[Slot], now: datetime, held: Collection[str]) -> Slot | None:
    """The published slot on the wall now, if its work may still be shown there.

    A work that has left the wall's works (taken out of the theme, refused by the
    Library) is not kept: keeping it would publish a schedule naming a work the
    rebuild no longer carries.
    """
    for slot in previous:
        if slot.covers(now) and slot.work_id in held:
            return slot
    return None


def _lengthened(kept: Slot, align_to: Sequence[datetime], length: timedelta, busy: _Busy) -> Slot:
    """The kept slot, run on until the slots after it are in step with the other wall's, where that is cheap.

    In step: the slots after it end on that wall's boundaries, the first boundary
    at or after its end being reached a whole number of this wall's slots on. So
    it moves by less than one slot, and walls whose intervals are equal, or one a
    multiple of the other, change pictures together. Cheap is the whole slot
    staying under two of this wall's intervals. Bounded by its start rather than
    by how far it moves: a pass comes with every step on the other wall, and
    each could otherwise lengthen the same slot again.

    It clashes with no wall it was not already clashing with as it ended. One
    it was is a clash nothing could have avoided (two walls kept on the one
    work both could show), and running it on under one slot is the lesser
    failure: left out of step, the next slot would overlap both of that wall's
    works when the two walls share only two.
    """
    boundary = next((at for at in sorted(align_to) if at >= kept.until), None)
    if boundary is None:
        return kept
    until = kept.until + (boundary - kept.until) % length
    if until - kept.start >= 2 * length:
        return kept
    already = {clash.other_wall_id for clash in busy.clashes(kept.work_id, kept.until - _INSTANT, kept.until)}
    if {clash.other_wall_id for clash in busy.clashes(kept.work_id, kept.until, until)} - already:
        return kept
    return Slot(kept.work_id, kept.start, until)


#: The smallest span the schedule names: its instants are whole seconds.
_INSTANT: Final[timedelta] = timedelta(seconds=1)


class _Busy:
    """Every other wall's slots, by work, for the one question the rule asks: is this work shown elsewhere then?

    Each wall's slots for one work are disjoint and in order, so of those starting
    before a span ends only the last can reach into it. One bisection per wall
    answers the question, where a scan would cost every slot of a three-day
    horizon at every slot of another.
    """

    def __init__(self, elsewhere: Mapping[str, Sequence[Slot]]) -> None:
        by_work: dict[str, dict[str, list[Slot]]] = {}
        for wall_id in sorted(elsewhere):
            for slot in sorted(elsewhere[wall_id], key=lambda s: s.start):
                by_work.setdefault(slot.work_id, {}).setdefault(wall_id, []).append(slot)
        self._by_work = {
            work_id: [(wall_id, [s.start for s in slots], slots) for wall_id, slots in walls.items()]
            for work_id, walls in by_work.items()
        }

    def clashes(self, work_id: str, start: datetime, until: datetime) -> list[Clash]:
        found = []
        for wall_id, starts, slots in self._by_work.get(work_id, ()):
            at = bisect_left(starts, until)
            if at and slots[at - 1].until > start:
                found.append(Clash(work_id, start, until, other_wall_id=wall_id))
        return found


class _Order:
    """The order works come up in: every work once per cycle, never the same work twice running.

    In the theme's order, or a fresh shuffle per cycle. A work the household rule
    passes over keeps its place in the cycle and comes up at the next slot it fits.
    Both preferences hold exactly on a wall that shares no work with another; where
    the household rule needs it, they bend (`take`).
    """

    def __init__(self, work_ids: Sequence[str], *, shuffle: bool, rng: random.Random) -> None:
        self._works = list(work_ids)
        self._shuffle = shuffle
        self._rng = rng
        self._remaining: list[str] = []
        self._last: str | None = None

    def after(self, work_id: str) -> None:
        """Begin the cycle as if `work_id` had just been shown."""
        self._last = work_id
        if not self._shuffle and work_id in self._works:
            # A rotation carries on from where it is, rather than going back to the
            # top of the theme each time the schedule is rebuilt.
            at = self._works.index(work_id)
            self._remaining = self._works[at + 1 :]
        else:
            self._remaining = [w for w in self._cycle() if w != work_id] if self._shuffle else []

    def take(self, fits: Callable[[str], bool]) -> str:
        """The next work, giving way to the household rule first and to this order's own preferences after.

        In order of preference: the next work in the cycle that is not the one just
        shown; then the one just shown, if only it fits; then a work from outside
        the cycle, which comes up early, the one just shown last of all. Only when
        no work at all fits does the cycle's next work go up anyway, and the caller
        names the clash. The owner
        ruled the household rule; the cycle and the no-repeat are this module's own
        choices, so they are the ones that bend.
        """
        if not self._remaining:
            self._remaining = self._cycle()
        candidates = [w for w in self._remaining if w != self._last] or self._remaining
        for pool in (candidates, self._remaining):
            chosen = next((w for w in pool if fits(w)), None)
            if chosen is not None:
                self._remaining.remove(chosen)
                break
        else:
            outside = [w for w in self._works if w not in self._remaining]
            outside.sort(key=lambda w: w == self._last)
            early = next((w for w in outside if fits(w)), None)
            if early is not None:
                chosen = early
            else:
                chosen = candidates[0]
                self._remaining.remove(chosen)
        self._last = chosen
        return chosen

    def _cycle(self) -> list[str]:
        cycle = list(self._works)
        if self._shuffle:
            self._rng.shuffle(cycle)
        return cycle
