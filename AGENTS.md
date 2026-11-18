# AGENTS.md

Instructions for any coding agent working here. Prawduct's governance pointer is at the
end of this file; `CLAUDE.md` holds the rest: the change of direction, the three
projects and their commands.

## Running tests

Run tests with `testament run`, not `pytest` directly. It sends this worktree (uncommitted
and untracked files included; ignored files such as `.env` never leave the machine) to
testament's runners and streams the results back. If no coordinator answers, it runs the same
tests here under this machine's test-slot cap and says so.

If `testament` isn't installed: `uv tool install --python 3.14
git+ssh://git@github.com/brookstalley/testament@main` (or `git+https://…`), then
`testament guide client`. Until it is, run `pytest` as before. To set testament up here,
ask the person for their pool's console address and follow `<console>/public/docs/start`
(a pool too old to serve that page has `<console>/public/docs/client` instead).

    testament run --json -- tests/unit/test_foo.py -k bar   # any pytest selection
    testament run --json                                     # the project's default suite

Read the JSON on stdout:

- `exit_code`: 0 all passed; 1 tests failed (a real red: fix it); 5 nothing collected
  (an existing selection; a path that does not exist is 2, `path_not_found`);
  75 the pool could not give a verdict and no test failed (a later run may); 2 anything else:
  a refusal or usage error, or a test that failed before the pool cut the run short. Read
  `verdict` first: when it is `unavailable` and `error.retryable` is true, run again; a
  `failed` verdict is a result and never retryable, so fix it rather than rerun it away.
  130 is an interrupt (no verdict). These codes are frozen: none changes meaning, a new one
  is announced a release ahead, and any other code is a failure (never fall back on it).
- `verdict`: `passed`, `failed` or `unavailable`, with `verdict_reason` (`passed`, `tests_failed`,
  `no_tests` or the `error.code`). A failed or errored test makes it `failed` whatever ended the
  run; `unavailable` (exit 75) is only the pool's own trouble, never a refusal.
  Key a script on `verdict` (and `error.retryable`) rather than `exit_code`: `verdict` carries
  the reason, and 0.46 moved "the pool could not decide" from 2 to 75 before the codes froze.
- `report.items[]`: one per test, with `outcome` (`passed`, `failed`, `error`, `skipped`,
  or `not_run`), `message` (pytest's failure text for a failed or errored test, or why a
  skipped test skipped) and `runner`.
- `report.missing`: tests that were requested but never reported. A non-empty list is never a
  pass: `population_mismatch`, exit 2, verdict `failed` (a test of the project's own that hung past its timeout ends this way too, so it never falls back). When every missing test is also in `report.given_up`
  (the pool gave it up after the batches holding it were lost or crashed three times: runners
  dropped, or pytest died), the code is `batches_lost` instead, and it is retryable unless a
  test failed.
- `report.counts`: how many tests ended each way, over the whole run.
- `report.stopped`: present when `-x` or `--maxfail N` stopped the run on the pool after N
  failures (`limit`, `failures`, `not_run`; counted per suite). The tests it never started
  are `not_run`, never `missing`, and the run is a red: exit 1, verdict `failed`.
- `report.last_failed`: present when `--lf` or `--ff` ran on the pool, from the failures
  this machine recorded for this worktree's last runs (`recorded`, `matched` of `collected`,
  and what `ran`: `failed`, `failed_first`, `all` or `none`), as pytest would choose.
- `fallback`: present when the tests ran on this machine instead of the runners. Flags
  that need one local pytest process (`--sw`, `--nf`) always run here;
  `fallback.reason` names the flag. `-n` doesn't: the pool is sent the selection without
  it, since it splits the tests itself, and `notes` says so. Flags that need a terminal
  (`--pdb`, `-s`, `--co`) are refused under `--json`.
- `setup`: present when testament isn't fully set up for this repo or machine. The tests
  still ran; tell the person, and point them to the `guide` command it names.
- `report.advice[]`: what the run advises, none of it a test result. Kind `cache` (also
  `report.cache.advice`): what keeps the most tests from ever being reused, each cause with
  its `share` of the run and a one-line `fix`. Kind `slow_test`: one test that delayed the
  run, with its `delay_s`; split or parametrize it, or make it cheaper. Kind `slow_batch`:
  the batch that ended the run late, with its `cause` (`group`, `slow_test`, `pool` or none);
  for a group, give its tests finer group keys. Kind `upgrade`: the pool runs a newer
  testament than this machine (`coordinator_version`, `client_version`); run its `command`,
  which replaces only the testament tool, and the next run uses it. Kind `areas`:
  more than 5,000 of a suite's tests ran in no area (`tests`, `declared`); declare areas
  (`testament guide project`, "Areas within a suite") when that is your task, or tell
  the person. Kind `agent_block`: this repo's copy of these instructions is older than the
  client's (`files`, `block_version`, `current_version`); replace it with what
  `testament guide agent-block` prints, keeping the repo's own additions, when that is
  your task, or tell the person. Every entry has an `id`
  (its kind and eight hex digits, stable while what it names is unchanged), a `severity` and
  a one-line `headline`; entries are ordered `upgrade`, then the other important ones by
  delay, then `info` (cache, slow tests, slow batch). `important` is every `upgrade`, every `areas` and every `agent_block`, a
  `slow_test` that delayed the run over 30 s, a `slow_batch` that did, from a group, and the `cache`
  advice when at least a quarter of a full run's tests are uncacheable and not declined; a batch slow from a slow test is `info` (its test's entry carries it), and one slow from the
  pool is no advice at all, only a figure (the pool's operator hears of it). Important entries are the last lines of the run's output (stderr
  under `--json`), at most three, as `testament ADVICE [<id>]: <headline>`, then `testament
  ADVICE: <n> more in report.advice`; they print on every run while they hold, because a
  wrapper's log tail is often all that gets read. When you see one, run the upgrade, or fix
  the test, group or cache cause or refresh the block it names when that is your task, or
  tell the person. The rest (`info`,
  smaller cache causes included) appears about once a day per project, and again at once when it
  names something new; `report.advice_state` is `throttled` on the runs in between. When it's
  non-empty, tell the person, and act on it only when that is your task, except `upgrade`,
  which you run. `--advice always` (or `TESTAMENT_ADVICE=always`) shows every entry on every
  run while you work through fixes, and `never` hides all of it. The same text goes to stderr
  for whoever watches.
- `report.durations`: every run, the shape of its test time (mean, stdev, median, p90,
  p99, max, the five longest and their share) for its tests, files and groups, and how
  parallel it ran. `report.slow_tests` and `report.slow_batches` are the figures behind the
  slow-test and slow-batch advice, on every run and never throttled: how much later the run
  ended because of each (`delay_s`), at most five tests and one batch. `report.long_poles`
  is the older long-pole figure, kept for older clients.

Progress (request accepted, tests collected, each failure) arrives on stderr as the run
goes; stdout is the envelope alone. A run that ends `upgrade_required` with a message
naming an install command comes from a testament too old to have `upgrade` advice,
which the pool no longer serves: run that command, then run again (one that names
none means the coordinator is the older side: tell the person). Keep one envelope per run, in a file of its own in a temp
directory that you age out, so a failure can be re-read without running again. Give each run
a fresh file name (`mktemp`): agents running at once on one machine, or sharing one scratch
directory, otherwise overwrite each other's envelopes, and the one read back is another run's.
Before acting on an envelope read from a file, check it is your run's: its `request_id`
holds the ids your run named on stderr (`request <id> accepted`, one per suite the pool ran;
several are joined with commas). A run that fell back to this machine names none. When you
need only the verdict and the tests that didn't pass, run `testament run --json=summary`:
the same envelope, but `report.items` lists only the tests that failed, errored, skipped or
never reported, each with its `outcome` and `message` (a skip is not a failure: read
`outcome`; `report.detail` is `"summary"`); `report.counts`, `report.missing` and
`error.ran` still describe the whole run.

A test that fails and then passes when you run it again may be flaky, not fixed. Before
deciding, `testament history '<test id>' --json` shows its past runs here and on the
pool, newest first, each with its outcome, runner, commit and failure text, and how often
it flipped on one tree. `testament report --json` ranks the project's slowest and flakiest
tests and those failing only on some runners.

`testament status` shows the runners and what's queued.

This is testament agent block v3. When a newer testament changes it, `testament run`
says so on every run, and `testament guide agent-block` prints the current one.

<!-- PRAWDUCT:ANCHOR — governance pointer managed by the prawduct plugin; keep it small and version-free. -->

## Governance (Prawduct)

This repo is governed by **Prawduct**, through your agent host's integration.

**Check first: is it loaded?** If not, or if you can't tell,
**governance is OFF** — no Stop gate, no Critic, nothing below enforced. Tell
the user before any work; don't proceed as if governed or imitate its gates from
its files.

- **Claude Code:** loaded if its session banner appeared; if not, run
  `claude plugin install prawduct@prawduct` and restart.

**Then, before writing any code, STOP and read the build cycle**
(Claude Code: `/prawduct:methodology building`). Skipping it is the #1 governance
failure.

Hardest rules:

- **Tests are contracts** — fix the code, never weaken a test.
- **No "pre-existing" exception** — fix what you find, or flag why you can't.
  The fix half is bounded to BLOCKING; below it, the flag is the whole answer.
- **Never silently drop a requirement** — say so explicitly.
- **Run the Critic after medium+ work** — never write findings yourself; the
  independence is the value. Rigor is stage-keyed: a mid-build review blocks
  only on what would ship broken, the review at the merge boundary runs
  everything and is never skipped, and unsure defaults to the cheaper mid-build
  review.

**Enforcement is structural — while the integration is loaded:** its Stop hook
**blocks** at session end if code changed against an active build plan with no
Critic findings.
