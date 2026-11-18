---
schema: 1
type: fix
scope: household-mixed-paces
date: 2026-11-18
title: A household pass builds its walls slowest first, so walls at mixed paces keep apart
closes: [brookstalley/arrt#374]
---
A republish used to build the republished wall first, against only each neighbour's slot now,
then rebuild the neighbours. Where the republished wall was quicker than a neighbour and the two
shared two works, the neighbour's long slot spanned both works and they clashed (#374, case A).
In the three-wall case (A {x, y}, N1 {x, w, v}, N2 {y, w}), N1 could take `w` and leave N2
nothing (case B).

`schedule.household_pass` now orders a pass:
- slowest wall first;
- among walls at one pace, the one with fewest works to go to first;
- a tie goes to the republished wall.

A wall built ahead of the republished one is built against that wall's first slot.
`DisplayService._write_v2` builds the republished wall once to fix that slot, then again after the
walls ahead of it, keeping the slot, and writes it once.

These still hold:
- the slot on each wall now never changes, and the picture now lingers under one more interval
  at most (the owner, 2026-10-13 and 2026-10-14);
- each wall is written at most once per write;
- a clash nothing could avoid is named in the journal;
- a neighbour that cannot be rebuilt keeps its schedule.

Both cases are tests that were red on the old order and pass now. On random households in the
pure pass, clashes fell from 258–273 of 300 to 54–76 of 300 for three walls at mixed paces, and
from 36 of 200 to 3 of 200 for case B. The module docstring's "What a pass cannot do" names what
remains: intervals that are not multiples, and three coupled walls where only a joint search
would find the schedule. One such case is pinned as a strict xfail.

## Consumer note
none: the feed's shape is unchanged; which work a wall's slots to come hold after a republish can differ.
