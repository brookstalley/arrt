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

`schedule.run_household_pass` makes every build in a pass, so the service and the tests run the
same steps. A wall built ahead of the republished one is built against that wall's first slot
and held in memory. It is written only after the republished wall's own write succeeds, so a
failed republish leaves every neighbour as it was.

These still hold:
- the slot on each wall now never changes, and the picture now lingers under one more interval
  at most (the owner, 2026-10-13 and 2026-10-14);
- each wall is written at most once per write;
- a clash nothing could avoid is named in the journal by the wall built later;
- a neighbour that cannot be rebuilt, or whose write fails, keeps its feed.

Both cases are tests that were red on the old order and pass now. Measured on random households
in the pure pass, with a check that counts every overlap after now except two pictures both up now:

| Household | Old order | New order |
|---|---|---|
| Case A, the quicker wall republished | 300/300 | 0/300 |
| Two walls with two or more works, one pace dividing the other | 188/1953 | 0/1953 |
| Case B, `a` republished | 50/200 | 24/200 |
| Case B, `n1` republished | 37/200 | 0/200 |
| Three walls at 1800/3600/7200 | 275/300 | 77/300 |

The module docstring's "What a pass cannot do" names what remains: intervals that are not
multiples, and three coupled walls where only a joint search would find the schedule. Keeping
those apart is proposed as #436 (stage requirements, for the owner). One such household is
pinned as a strict xfail that fails if a later change keeps it apart.

## Consumer note
none: the feed's shape is unchanged; which work a wall's slots to come hold after a republish can differ.
