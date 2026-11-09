---
schema: 1
type: fix
scope: flaky-tests
closes: [brookstalley/arrt#57, brookstalley/arrt#397, brookstalley/arrt#376, brookstalley/arrt#402, brookstalley/arrt#372]
date: 2026-11-09
title: Tests that failed now and then under the parallel suite, and one product race behind two of them
---

**A product race, fixed (#57, #397).** `DiscoveryRunner.run_status` read a run
and then asked whether it was still in flight. A worker finishing between the
two left the caller a mid-run reading presented as final: status
`resolving_works` and no phase-2 estimate. It now asks first, then reads.
Measured with injected delays; a unit test forces the finish into the window and
fails against the old order.

**Test defects:**
- **#376:** the shapes-republish test compared the wrong pair of feeds and passed only when three publishes fell in one wall-clock second. It now moves a test clock and compares the right pair.
- **#402:** browser tests that left Ask for Walls waited for any page heading, which Ask's own met. They now wait for Walls' heading. A fourth test with the same wait got the same fix.
- **#372:** the suite's one-shot HTTP requests had httpx's 5 s default, which a loaded run reaches (measured: 4.4 s worst at three suites at once). They now take 30 s, set once in `arrt/tests/serving.py`, with a guard that the bound applies and that product code never calls the test-only default.
- A wall-gone browser test deleted its wall before the page had drawn it. It now waits for the wall's card.
- The back-button test in `test_the_sidebar.py` waited for any heading after opening a work, which Walls' own met, so back could run from Walls and pass. It now waits for the Work page's own `← Walls` link, and for it to go after back.

**#371 stays open.** Its second case is probably #372's timeout, unconfirmed.
Its first did not reproduce in four loaded runs, and its cause is not known.

## Consumer note

Nothing changes for a household except one fix: a discovery run's status no
longer reports a run as still working, with no estimate, at the moment it
finished.
