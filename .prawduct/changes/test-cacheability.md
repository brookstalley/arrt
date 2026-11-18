---
schema: 1
type: perf
scope: test-cacheability
date: 2026-11-18
title: More tests are reusable from testament's cache
closes: [brookstalley/arrt#435]
---
Testament reuses a passing test's result only when the test reads no clock, randomness,
subprocess or socket. Counted by `testament cacheability --offline` on a full run: the governance
suite went from 0 of 486 cacheable to 422 of 487, and the curation suite from 2718 of 5758 to
3040 of 5767, with 118 more declined on purpose (owner's priority, 2026-11-18).

- **Governance:** `tests/repository.py:projects` and the citation scan no longer run git at
  import, which tainted every test in the process. Collection lists cases from the files on
  disk, git is asked inside the tests, and a guard per parametrised check asserts its cases
  cover every tracked project or record.
- **Curation:** the clock and randomness that tests read through production code are passed in,
  with today's behaviour as the default:
  - `open_catalogue_file` and the catalogue-file migrations (`now=`, `new_id=`), the largest
    cause;
  - `PictureStore(staging_token=)`;
  - `CatalogueBackup(clock=)`;
  - `observe` reads the clock only when it has a timestamp to age.
  
  The shared `kept` fixture uses a fixed clock.
- **Declined:** the tests that run node or dezoomify-rs carry `@pytest.mark.uncacheable(why)`,
  registered in `arrt/tests/conftest.py`.

Not done here:
- the services' own clocks and ids (`CatalogueService`, `DiscoveryService`, built in
  `services/container.py`);
- programming's (`schedule.build`, after #374);
- the browser suite, which is a live server by design.

## Consumer note
none: no route, schema or behaviour changes; the new parameters default to what the code did before.
