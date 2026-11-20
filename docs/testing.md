# Testing: the default suites, the browser suite and the live suites

`CLAUDE.md` holds the dev-command table and the testing rules, one instruction a
line. This file holds why each rule holds, and the commands and setup for the two
opt-in tiers, the browser suite and the live suites.

## The default suites

**A plain `uv sync` uninstalls the optional groups.** uv treats anything outside
the default groups as extraneous and removes it, so after a bare `uv sync` in
`arrt/` the browser suite skips itself. The suite stays green and quietly
shrinks. Sync with the groups the run needs: `uv sync --group browser`.

The curation suite boots a real uvicorn server per test class of surface work.
Do not replace that with an in-process ASGI transport: Starlette does not run a
mounted sub-app's lifespan, and the lifespan is what makes the MCP mount work,
so an in-process test would pass against an app that fails every real request.

**`arrt/tests/system/` runs the product as it is assembled, in the curation
suite and in the image's test stage.** `test_migration_chain.py` opens a
catalogue each past release left (`arrt/tests/fixtures/catalogues/`, one SQL dump
per release whose schema changed, made by that release's own code, from its git
tag, by `arrt/tools/old_catalogue.py`) through the call the server makes, and
asserts what survived, what was dropped, and the copy taken first;
`test_restore.py` takes a backup generation from a running server, restores it by
the runbook's steps (written as code in that file) in the same art root and in a
new one, and starts the server on it. Nothing there reads git or the network at
test time; a new release whose schema changed gets its dump by adding its tag to
the tool and running it where the tags are. The tests start the server as a
process, so they hold what an in-process fixture cannot: that a stale
`-journal` beside a restored catalogue silently undoes the restore
(`test_a_restore_that_leaves_the_stale_journal_is_silently_undone`). The real
Player's test is another marker of the same directory
(§ The real-Player test).

**That suite runs across cores** — `-n auto` is in the curation plane's
`addopts`, so `uv run pytest` is already parallel (118s → 21s, measured
2026-08-05). **To debug a failure, run it here with `uv run pytest … -n0`**:
workers interleave output and a `pdb` breakpoint has no terminal to stop in.
Not through testament, which drops `-n` and sends the selection to the pool. The root suite runs in a fraction of
a second and is left serial.

**The root suite holds no product code, and it is not optional.** It carries
`tests/preferences/`, where this repo's artifact-versus-code contracts
live — the Library/Programming seam, the norm index, deployment values, and the
screen tables — and the repository-wide scans, which cover every project its
tracked `pyproject.toml` files name. Agreements with Arrt Player (the
heartbeat, the timing, the label corpus) are held by each side's own suite
against the contract package, never by a test that reads both. The screen tables
span two homes by design: `test_screen_tables.py` reads
the *curation* plane's `http/static/app.js` against
`.prawduct/artifacts/information-architecture.md`, and the server's own suite
does not read the artifacts. So a change made entirely inside `arrt/` — routing a screen,
editing those IA tables — is guarded by a leg in the repo root.

## The browser suite

The client under `arrt/src/arrt/http/static/` is the product's only
human interface, and neither Python suite executes a line of it. **It is a tree
of ES modules, not one file**: `app.js` is the boot and the route table,
`core/*.js` is what every screen shares, and `screens/*.js` is one module per
screen. `-m browser` runs it, in a real Chromium against a real booted server:

```sh
cd arrt && uv sync --group browser        # once
cd arrt && uv run playwright install chromium   # once, ~200MB
cd arrt && uv run pytest -m browser -n0
```

**Deselected by default for the browser download, not for anything about the
tests** — they are deterministic, free, and reach no foreign API. When you touch
anything under `static/` (`app.js`, a `core/` module or a `screens/` one), run
the files for the screens you changed. The whole suite, the command above, runs
once on the integrated branch (`project-preferences.md`, `Delegate
verification`). `.github/workflows/tests.yml` runs it on testament's pool on
every pull request. Without the group the modules skip with the command
that fixes it, so a default `uv sync` is unaffected.

**When the pool cannot answer, CI falls back, and the browser suite is what it
gives up.** `tests.yml` hands the pool run to `.github/scripts/pool_or_fallback.py`.
If the console will not serve the client (no connection, a 5xx, a 408 or 429),
`testament run` ends `verdict: unavailable` (exit 75), or the pool does not accept
the run within two minutes, it retries with backoff for up to ten minutes; a run the
pool accepted and still holds at the pool step's twenty-minute deadline (about three
times a healthy full run) is stopped. Either way it then runs the governance,
curation and contract suites on GitHub's runner with uv, by the commands in
CLAUDE.md, after the lint the job always runs there. Two suites do not run there: the
browser suite needs Chrome, which only the pool's runners carry, and the real-Player
suite is the pool's alone by the owner's ruling of 2026-11-20 (`POOL_ONLY` in
`pool_or_fallback.py`; § The real-Player test). The job summary opens "The pool was
unavailable; ran here, on GitHub's runner, without the browser and real-Player
suites" and names each as not run, with why.
The required check, "Lint, then every suite", is then green on what ran, so the
outage blocks no merge. The second check, **"The browser suite ran on the pool"**,
is not required: it is green when the pool gave the verdict and red after a
fallback, the mark that this tree has no browser or real-Player verdict (its name
still says the browser suite alone; its message names both). Nothing gives them one
later on its own (no workflow runs on a push to `develop` or `main`): re-run all of
the workflow's jobs once the pool is back, or run `testament run --json=summary
--suite browser --suite player` on the branch's head and put its request ids on the
pull request.
The trade: an outage of the pool no longer blocks every merge (ruling 4 of
2026-11-19), and GitHub's minutes are spent on suites only during one (the
2026-11-18 ruling). A `failed` verdict is a result and never falls back, nor does a
refused key, a wheel that fails its digest, an envelope of a shape the driver cannot
read, or a run stopped after the pool reported a failing test: those end "Nothing
ran." `assert_tests_ran.py --decision` re-checks the record, times included (one
retryable blip earns no fallback), and `tests/test_ci_fallback.py` holds the
decision, the deadline and the workflow's shape.

**The type check runs on the pool, once per change.** CI's lint step runs ruff and
black only, with `--only-group dev`. mypy runs in the governance suite
(`tests/preferences/test_type_gate.py`), in `arrt/` and in `contract/` with each
project's own configuration, and fails naming the modules with errors. It runs
mypy without syncing, so on a fresh clone it fails until the environments exist,
and says so: `cd arrt && uv sync --group dev --group browser` and `cd contract &&
uv sync --group dev`. The fallback's governance step syncs both first.

**`-n0` matters here.** These tests time real two-second poll intervals, and
`-n auto` — which a command-line `-m` leaves in place — turns those windows into
flakes when workers contend for cores.

**A behaviour is not covered because a browser test exercises it.** Prove it with
`tools/mutation_sweep.py`, which drives a JavaScript module as happily as a
Python file: delete the branch and watch a test go red.

**Sweeping this suite needs the marker passed through:**

```sh
cd arrt && uv run python tools/mutation_sweep.py m.json tests/browser/test_x.py -- -m browser
```

Without it pytest collects nothing and exits 5. The tool refuses to sweep unless
the chosen tests run and pass unmutated, so forgetting the marker now fails
loudly instead of reporting every mutation caught by runs that executed no test.
(`-n0` is the tool's own default — see the sweep paragraph below.)

### Assertions read the page through `expect`

A one-shot read — `loc.inner_text()`, `loc.count()`, `loc.is_visible()` — returns
what the page holds at the instant it is called, and an `assert` on it passes or
fails on whichever side of a repaint that instant fell. Playwright's `expect(loc)`
asks the same question and keeps asking until the page agrees or the timeout
passes. That difference is most of this suite's flakes (audit 7, S1a: twelve
issues between August and November).

**`arrt/tests/unit/test_browser_reads_retry.py` holds it.** It reads every file in
`arrt/tests/browser/` and refuses a one-shot read or a fixed sleep in any file
not on its `UNCONVERTED` list. Every file is converted, so the list is empty. A
file listed with more or fewer than it has fails, and so does a converted file
still on the list; adding a row with a file's exact counts is the one way past
the guard, which it does not refuse, so it is a decision to argue in review. Two
markers excuse one statement each, and
each needs its reason after the colon:

- `# one-shot: <why>` — a read that computes a value rather than asserting one
  (the title to click next, the count to compare after a reload), placed after a
  wait or an `expect` of the state it reads;
- `# sleep: <why>` — a fixed wait that proves nothing happens for a while, which
  no condition can stand for.

**`expect` waits as long as a locator does.** `tests/browser/conftest.py` sets
`expect`'s timeout to 30 seconds, Playwright's default for an action and for
`wait_for`, where its own default is 5. A converted read then fails no sooner
than the wait it replaced. Pass a shorter `timeout=` only where the bound is
the claim, and say so.

**The view is `ui.view`**, the `#view` locator, so `ui.text()` (the view's
`innerText`, read once) has a retrying form: `expect(ui.view)`.

#### The table

Each row is one shape as it stands in an `assert`, with how many there were at
the commit that wrote the guard (2,046 reads across the suite, 1,723 of them
inside an `assert`). `s` is a string, `n` a number, `loc` a Locator. Every text
row passes `use_inner_text=True`, because these tests read `innerText` and
`expect` compares `textContent` without it: `textContent` includes text that
CSS hides and ignores `text-transform`, so a bare conversion changes what the
assertion means. An `expect` written before this table without it is left as it
was written.

| One-shot read | Count | Retrying form |
|---|---:|---|
| `assert loc.inner_text() == s` | 264 | `expect(loc).to_have_text(s, use_inner_text=True)` |
| `assert " ".join(loc.inner_text().split()) == s` | 24 | `expect(loc).to_have_text(s, use_inner_text=True)`: a string is compared whitespace-normalised, which is what the join did |
| `assert loc.inner_text().strip() == s` | 10 | the same: normalising trims |
| `assert s in loc.inner_text()` | 129 | `expect(loc).to_contain_text(s, use_inner_text=True)` |
| `assert s not in loc.inner_text()` | 62 | `expect(loc).not_to_contain_text(s, use_inner_text=True)`, under the anchor rule below |
| `assert s in ui.text()` / `not in` | 103 / 64 | `expect(ui.view).to_contain_text(s, use_inner_text=True)` / `not_to_contain_text` |
| `assert loc.inner_text().startswith(s)` | 35 | `expect(loc).to_have_text(re.compile("^" + re.escape(s)), use_inner_text=True)` |
| `assert loc.inner_text().endswith(s)` | 13 | `expect(loc).to_have_text(re.compile(re.escape(s) + "$"), use_inner_text=True)` |
| `assert loc.inner_text().strip().startswith(s)` / `.endswith(s)` | 14 | the same, with the strip in the pattern: `r"^\s*" + re.escape(s)` / `re.escape(s) + r"\s*$"` |
| `assert s not in loc.inner_text().lower()` | 2 | `not_to_contain_text(s, use_inner_text=True, ignore_case=True)` |
| `loc.text_content()` in any of the above | 6 | the same row **without** `use_inner_text`: it was `textContent` |
| `assert loc.all_inner_texts() == [..]` | 51 | `expect(loc).to_have_text([..], use_inner_text=True)` |
| `assert loc.all_text_contents() == [..]` | 9 | `expect(loc).to_have_text([..])` |
| `assert loc.count() == n`, `n` > 0 | 244 | `expect(loc).to_have_count(n)` |
| `assert loc.count() == 0` | 289 | `expect(loc).to_have_count(0)`, under the anchor rule |
| `assert loc.count() >= n` / `> 0` / truthy | 6 | `expect(loc.nth(n - 1)).to_be_attached()` / `expect(loc.first).to_be_attached()` |
| `assert loc.get_attribute(a) == v` | 118 | `expect(loc).to_have_attribute(a, v)` |
| `assert loc.get_attribute(a).startswith(s)` / `.endswith(s)` | 15 | `expect(loc).to_have_attribute(a, re.compile("^" + re.escape(s)))` / `re.escape(s) + "$"` |
| `assert s in loc.get_attribute(a)` | 15 | `expect(loc).to_have_attribute(a, re.compile(re.escape(s)))`: a substring, as `in` was |
| `assert s not in (loc.get_attribute(a) or "")` | 2 | `expect(loc).not_to_have_attribute(a, re.compile(re.escape(s)))`, under the anchor rule; it passes when the attribute is absent, as `or ""` did |
| `assert loc.get_attribute(a) is None` / `is not None` | 11 | `expect(loc).not_to_have_attribute(a)` / `expect(loc).to_have_attribute(a)`: both take no value (measured on 1.62: present passes `to_have_attribute`, absent passes `not_to_have_attribute`) |
| `assert s in loc.all_inner_texts()` / `not in`, one item of a list | — | `expect(loc).to_contain_text([re.compile("^" + re.escape(s) + "$")], use_inner_text=True)` / `not_to_contain_text([…])`: hazard 11 |
| a class tested for, `"x" in (loc.get_attribute("class") or "").split()` | — | `expect(loc).to_have_class(re.compile(r"(^\|\s)x(\s\|$)"))`: hazard 12 |
| `assert loc.is_visible()` / `not loc.is_visible()` | 59 / 19 | `expect(loc).to_be_visible()` / `expect(loc).to_be_hidden()`, under the anchor rule |
| `assert loc.is_hidden()` | 35 | `expect(loc).to_be_hidden()`, under the anchor rule |
| `assert loc.is_checked()` / `is_disabled()` / `is_enabled()`, and `not` | 4 / 11 / 8 / 1 | `to_be_checked()` / `to_be_disabled()` / `to_be_enabled()`; `not_to_be_checked()`, and `not is_disabled()` is `to_be_enabled()` — the two agree on `aria-disabled` (hazard 19) |
| boxes read into a dict by their labels, `{label.inner_text(): box.is_checked()}` | — | the boxes' count with `to_have_count(n)`, then `expect(dialog.get_by_label(name, exact=True)).to_be_checked(checked=…)` per name: hazard 17, since a label is matched by its text content, not its `innerText` |
| `assert loc.input_value() == v` | 39 | `expect(loc).to_have_value(v)` |
| a tuple of reads compared to a tuple: `assert (a.input_value(), b.is_disabled()) == (x, True)` | 13 | one `expect` per element, each by its own row |
| `assert page.title() == s` / `.startswith(s)` / `re.match(r"^s\b", …)` / `s not in` | 6 | `expect(page).to_have_title(s)` / `re.compile("^" + re.escape(s))` / `re.compile(r"^s\b")` / `not_to_have_title(re.compile(re.escape(s)))` |
| `assert page.url.endswith(s)` (not counted: an attribute, read after the wait that moved it) | — | `expect(page).to_have_url(re.compile(re.escape(s) + "$"))` |
| `page.inner_text(sel)`, `page.get_attribute(sel, a)`, `page.is_visible(sel)` | — | `page.locator(sel).first`, then the row above: a Page read takes the first match, and `expect` refuses a locator that matches several |
| `text = loc.inner_text()` then `assert … in text` | 105 (+ 27 of `ui.text()`) | one `expect(loc)` per assertion, and the assignment goes |
| a read that computes (a title to click, a count to compare later) | — | stays, after an `expect` of the state it reads, with `# one-shot: <why>` |
| `bounding_box()` | 44 | stays, after an `expect` of the state it measures, with `# one-shot: <why>` (geometry, as `evaluate` is) |
| `page.evaluate(…)`, `loc.evaluate(…)` | not counted | out of scope (the plan's decision): a computed value no `expect` retries. Placed after an `expect` of the state it reads; `wait_for_function` is its retrying form where the claim is a predicate |
| `ui.page.wait_for_timeout(ms)`, a `setTimeout` promise | 39 | a wait on the condition it stood for; one that proves nothing happens for a while stays, with `# sleep: <why>` |
| `assert s.count(w) == 1` on a whole card or page ("said once") | — | `to_have_text(re.compile(r"^(?:(?!w).)*w(?:(?!w).)*$", re.IGNORECASE \| re.DOTALL), use_inner_text=True)`: hazard 18 |

#### The hazards, each with the wrong conversion and the right one

Each was measured on Playwright 1.62 (a page set with `set_content`, each form
asserted against it).

1. **`innerText` and `textContent`.** `to_have_text` without `use_inner_text`
   reads `textContent`: a `display: none` child's words count, and
   `text-transform: uppercase` does not. Wrong: `to_contain_text("Hidden")` where
   the test read `inner_text()`; right: `use_inner_text=True`. An element that
   is *itself* hidden is another matter: its `innerText` is its text content,
   both as a read and through `use_inner_text`, so a text assertion on it
   passes as the read did and says nothing about whether it shows. Where the
   claim is that it shows, add `to_be_visible()`; never assume one from the
   other.
2. **Whitespace.** A *string* is compared normalised on both sides: runs of
   whitespace, newlines and non-breaking spaces become one space, the ends are
   trimmed and zero-width spaces dropped. So `to_contain_text("a\nb")` matches
   `a b` on one line, and `to_have_text("11 am")` matches `11 am`. A test
   whose claim is the line break or the non-breaking space is weaker as a
   string. Right: a *regular expression*, which is matched against the raw
   `innerText`: `to_have_text(re.compile(r"a\nb"))`.
3. **Exact and substring.** `to_have_text(s)` is the whole text; `to_contain_text(s)`
   is a substring. `==` is the first, `in` the second; `startswith` is neither,
   and is a regex anchored with `^`.
4. **Lists.** `to_have_text([..])` is the whole list, in order, each item whole.
   `to_contain_text([..])` passes on any subset in order: wrong for `==`.
5. **Several matches.** Text, attribute, value and state assertions refuse a
   locator matching more than one element, as `loc.inner_text()` did. A Page
   read (`page.inner_text(sel)`) took the first match silently: convert it with
   `.first`, or narrow the selector. `to_have_count` counts every match, hidden
   ones included, as `count()` did: never swap it for `to_be_visible`.
6. **Absence passes at once.** `to_have_count(0)`, `to_be_hidden()`,
   `not_to_contain_text` and `not_to_have_attribute` are true of a page that has
   not painted yet, so they pass before the write they are about has happened.
   The one-shot form had the same weakness, and it was covered by the wait above
   it. **The anchor rule:** a negative assertion stands after a positive wait or
   `expect` on something only the settled state has; keep that anchor, and put
   the negative after it, never first. (A text negative on an element that is
   *absent* fails rather than passes, as the one-shot read did.)
7. **Inequality.** `assert loc.inner_text() != before` becomes
   `not_to_have_text(before)`, which passes on any intermediate paint, the
   empty one included. Right: assert the value it changes *to*.
8. **Snapshots.** Several assertions over one read saw one instant; converted,
   each sees its own. For a settled screen that is the same claim. Where the
   claim is that one moment held all of them together, a person must think.
9. **Time.** `expect` gives up after the suite's 30 seconds, where the read
   gave up never. Do not add `timeout=` to make a converted test faster.
10. **`has_text` is not `innerText`.** `locator(sel, has_text=…)` and
    `filter(has_text=…)` match the raw text content: a pattern there sees
    hidden words and unnormalised whitespace (`re.compile(r"^16th century$")`
    does not find `<li>  16th   century </li>`). Wrong: turning
    `s not in loc.all_inner_texts()` into a `has_text` pattern with
    `to_have_count(0)`, which passes on an item whose words are `s`. Right:
    hazard 11's anchored regex, or the set read kept after its anchor with
    `# one-shot:`. A `has_text` *string* is a case-insensitive substring and is
    fine for choosing a row to assert on.
11. **Membership of one item among several.** `to_contain_text([..])` on a locator
    that matches several elements passes when the list's items are found, in order,
    among the elements, and a *string* in the list is a substring: `["16th"]`
    passes on an item `16th century`, where `==` on the item would not. Right:
    one anchored regex, `to_contain_text([re.compile("^" + re.escape(s) + "$")],
    use_inner_text=True)`; and `not_to_contain_text([…])` for absence, under the
    anchor rule. With `use_inner_text=True` the regex sees what a person reads
    (a `text-transform: uppercase` item matches `^OIL PAINT$`, and a
    `display: none` child's words are not in it); without it, the text content.
    The same call on a *bare string* and several elements fails, so it is a list
    or a narrower locator. Measured on 1.62 in a page set with `set_content`.
12. **A class.** `to_have_class("x")` is the *whole* attribute (`card selected`
    is not `selected`), and `re.compile(r"selected")` also passes on
    `unselected`. `\b` treats `-` as a boundary, so `\bquiet\b` passes on
    `quiet-hover`. Right: `re.compile(r"(^|\s)quiet(\s|$)")`, which fails on
    `quiet-hover` and on `unselected`; its negation is `not_to_have_class` of
    the same pattern, under the anchor rule.
13. **`:text-is()` matches the deepest element.** `h2:text-is('Walls')` finds no
    element when the heading wraps its words in a `<span>` (the span is the one
    that matches), where `get_by_role("heading", name="Walls", exact=True)` does.
    A `wait_for_selector("h2:text-is('Walls')")` on such a heading waits out its
    timeout: select by role, or by the span.
14. **A row picked by its title.** `get_by_text(title)` is a case-insensitive
    substring match over the text content, hidden words included, so a title that
    is part of another row's title (or of a hidden year or subtitle in its cell)
    picks several rows and `expect` refuses it. `get_by_text(title, exact=True)`
    picks the element whose whole text is the title, and the whole text still
    counts the cell's hidden words: a cell `Water <span hidden>Lilies</span>` is
    not `Water`. Narrow to the column (`td:nth-of-type(2)`) first, as the Artist
    page's row helper does.
15. **A No is read once the page is quiet.** After a dialog is declined, the
    client's request, if it wrongly sends one, goes out a moment later, so a read
    of the server's state straight after the dialog closes sees the state before
    it and passes by timing. Measured: a client that removes whether or not it
    was confirmed, a read at once says "kept", a read after
    `wait_for_load_state("networkidle")` says "removed". Right: `expect(dialog)
    .to_be_hidden()` (the positive anchor), then `networkidle`, then the read.
    Old tests of this kind (Watches, Players) passed under a client that removed on Cancel.
16. **A list a request handler fills.** Where a test collects requests in a
    Python list from a `page.on("request", …)` handler and reads it after
    `with page.expect_request(…)`, one converting delegate found the list short
    at the read and made one further awaited call (a Playwright call, any) before
    it. That was not reproduced in a bare page (300 trials of a click that sends
    one request, list full at the exit every time), so treat it as a reported
    hazard of the wiring, not a measured rule: if such a test ever flips, look
    here first.
17. **A label is matched by its text content.** `get_by_label(name, exact=True)`
    on a `<label>` compares `name` with the label's whole text content,
    whitespace-normalised and trimmed, and case-sensitively: words CSS hides
    (`hidden`, `display: none`, `aria-hidden`) count, and `text-transform` does
    not, where `innerText` is the other way round on both. A control with an
    `aria-label` is found by that and no longer by its label's words. Measured on
    1.62 in a page set with `set_content`, eight labels: `Study <span
    hidden>(current)</span>` is found as `Study (current)` and not as `Study`; an
    uppercased `Hall` as `Hall`, not `HALL`; `Kitchen` with an `aria-label` of
    `Kitchen wall` only as the latter. So the conversion of a dict of label texts
    is right for a label whose words all show, which *Hang…*'s are
    (`screens/theme.js`: each label's text is the wall's name, its box has no
    `aria-label`, and no rule transforms it); a label that carries hidden words
    is found by them, not by its `innerText`.
18. **"Said once" as one pattern.** `re.compile(r"^(?:(?!w).)*w(?:(?!w).)*$",
    re.IGNORECASE | re.DOTALL)` with `use_inner_text=True` passes on exactly one
    `w` and fails on none or two, across lines (measured on 1.62: zero, one, two
    on one line, two on separate lines, one hidden copy beside one shown). It
    needs `re.DOTALL`: Playwright passes the flag through, and without it a text
    of several lines fails even when it holds `w` once. It sees the raw
    `innerText`, so `screen&nbsp;off` is not `screen off`, and a `w` that wraps
    across two elements (`screen` in one, `off` in the next) is not found.
    Without `use_inner_text`, a hidden copy counts.
19. **`aria-disabled` is disabled to both reads.** `is_disabled()` and
    `to_be_disabled()` agree in every case measured on 1.62: a native `disabled`
    button, a button in a disabled `<fieldset>`, and `aria-disabled="true"` on a
    button, an `<input>`, a `role=button`, or on an ancestor of the button (a
    plain `div` or a `role=group`) are disabled to both; `aria-disabled="false"`,
    and `aria-disabled="true"` on a `span` with no role, are enabled to both. So
    converting one to the other changes nothing; what neither says is whether
    the control ignores a press, which is the client's to do.
20. **A window is the page's clock.** A count over a window ("one request per
    poll") read after a fixed sleep counts whatever the runner managed in that
    time. Right: `page.clock.install()` before the page loads, then
    `page.clock.run_for(interval)` one interval at a time, each followed by a
    wait on what that interval's paint leaves behind, so the count is per tick.
    An init script added *after* the install wraps the clock's `setTimeout`, so
    a test can count the timers the page sets (`test_the_run_view.py`,
    `COUNT_POLL_TIMERS`). Added before it, the wrapper is replaced: measured on
    1.62, it then saw none of the page's two-second timers in five seconds,
    only shorter ones (100 ms, 5 ms).
21. **An absence that settles by a callback.** A fitting scroll box carries no
    `tabindex`, both before the client's `ResizeObserver` has reported and
    after, so `not_to_have_attribute` passes on its first poll whether or not
    the observer has run. Anchor it on an observer of the test's own, made
    after the client's: within one rendering step observers report in the
    order they were made, so once the test's has reported, the client's has
    settled the box (`test_a_table_wider_than_its_box_takes_the_keyboard`).

#### Where there is no mechanical form

These are left for a person, and the chunk that meets one says in its report
what it did (counts at the commit that wrote the guard):

- **Something has not happened yet** — an `assert` that the old value is still
  there between an act and its effect ("until the Player reports, the card
  still leads with Nighthawks"). A retrying positive of the old value passes at
  once, as the read did; it cannot tell "not yet" from "changed and changed
  back". Keep it as the retrying positive, and anchor it after something that
  shows the act was received (the act's own notice). Not countable by shape.
- **A count expected to change** — a count read, then an act, then a comparison
  (`count() >= loaded`): the first read computes (`# one-shot:`), the second
  becomes `expect(loc.nth(loaded - 1)).to_be_attached()`. Twenty-two
  `count()` reads are assigned or returned.
- **A read used to compute** — 259 reads are assigned and 40 returned by a
  helper; each is either the snapshot of an assertion (convert it per the table)
  or a value the test uses (keep it, `# one-shot:`). Telling which is reading
  the test.
- **Simultaneity** — a read taken at the moment something else appeared,
  because the claim is that both changed together ("the watch replaces the
  lead and Next together"). A retrying `expect` after the notice would pass on
  a list that caught up later. Keep the read, at the notice, with
  `# one-shot:`; it is not a race when the client writes both in one turn.
- **Text arithmetic** — `.split(" · ")[0]`, `.replace(…)`, `.count(s) == 1` ("said
  once"), `sorted(…)`, `len(…)`, comprehensions over `all_inner_texts()`
  (`all(t.startswith("From ") for t in …)`), and `<` or `<=` on a count: 47.
  (Membership of one item in a list has a retrying form, hazard 11.) Where
  the length is known, a list of anchored regexes keeps it
  (`to_have_text([re.compile("^From ")] * 3, use_inner_text=True)`); "said
  once" is a regex with a negative lookahead or a count of matching elements,
  chosen for what the test means.
- **Markup** — `inner_html()`: 1. There is no retrying read of markup; assert the
  element the markup would hold instead (`to_have_count(0)` on
  `a[href*='<id>']`), which is narrower, and say so.
- **Geometry** — 44 `bounding_box()` reads. `to_be_in_viewport()` is an
  intersection test, not the inequality the tests write.
- **The request log** — `ui.requests_matching(…)` reads Python's list, not the
  page (49). A request that must happen is `with page.expect_request(…)`; one
  that must not is a claim over time, held open by the anchor rule or by a
  `# sleep:` that says how long nothing happened.
- **Elapsed time from the machine's clock** — a test that seeds a time from
  `datetime.now` and asserts on elapsed time is listed for wave 2b's Chunk 43
  (clocks), not changed here.

## The real-Player test

**`player_e2e` runs the shipped pair: `python -m arrt` and a real Arrt Player,
two processes over HTTP** (`arrt/tests/system/test_a_real_player.py`). The Player
is the commit `arrt/tests/system/player-ref.txt` names, fetched from GitHub with
`git` and synced from its own lockfile with `uv sync --frozen --no-dev` (as a Pi
installs it, on uv's Python 3.13) into a cache outside the repository, by commit
(`~/.cache/arrt/player-e2e`, or `ARRT_PLAYER_E2E_CACHE`). So it needs the network
to GitHub, `git` and `uv`, checks for the last two first and fails by name without
them; it reaches nothing else, and no paid service: the server runs with every
name `.env.example` declares set blank and no `.env` read (`arrt/tests/system/conftest.py`
starts it through `arrt/tools/ux_walk.py`'s `synthetic_environment` and launcher, which
`arrt/tests/unit/test_ux_walk_isolation.py` holds), and the Player inherits nothing but
`PATH`. That is why the curation plane's addopts deselect it, with the live suites'
reason, and why **it is a testament suite of its own, `player`** (`.testament.toml`:
the curation suite's command with `-m player_e2e`, selecting the one file).

- **On every pull request**, inside the required check: `tests.yml` runs every suite
  the manifest declares, so the pair is tested on every server change, beside the
  other suites (65-80 s warm, 210 s cold on the first run after the pin moves; the
  pool runs the suites at once, so it lengthens the run only when it is the slowest).
  A Player pin that will not install, or a fetch from GitHub that fails, is a red,
  never a fallback.
- **On the pool, by hand:** `testament run --json=summary --suite player`. Every
  runner may take it: it runs in the project's container, which carries `git` and
  `uv`, and needs from the host only the network to GitHub and to uv's Python
  downloads. It passed on five of the six runners, both architectures, on 2026-11-19
  and -20. If a runner without that network joins, its operator labels the runners
  that have it, and the suite `requires` the label.
- **Here:** `cd arrt && uv run pytest -m player_e2e -n0 tests/system/test_a_real_player.py`
  (about 65 s warm, two of the Player's 30 s client polls; the first run also fetches
  and builds the Player).
- **Never on GitHub's runner:** when the pool cannot answer, CI's fallback leaves the
  suite out and says so by name, as it does the browser suite (§ The browser suite; the
  owner's ruling of 2026-11-20: "We should minimize CI and prioritize local tests. We are
  almost out of ci minutes.").

Every curation run says what it did with the test: its header names where the test
runs and how to run it, and its last line says whether this run selected it,
deselected it, or never collected it (`arrt/tests/player_e2e_header.py`, decided from
what pytest collected and deselected, through public hooks only). The image's test
stage deselects it (no git there), and `.github/workflows/image.yml` runs it against
the built app image (`ARRT_SERVER_IMAGE`) on a pull request into `main`. Moving the
Player's pin is a one-line change to `player-ref.txt`, and the first run after it is a
cold one.

## The live suites

Four markers — `live_museum`, `live_binary`, `live_api`, `llm_eval` — all
deselected by default. They are not correctness tests; the fakes cover that.
They are the durable form of the `*-api-findings.md` documents, and they fail
when a foreign API stops matching what the product was built against.

**Always pass `-n0` when you run one.** A `-m` on the command line replaces the
marker expression but leaves `-n auto` in place, so `-m live_museum` alone fires
concurrent requests at a public museum API — which comes back as a rate limit and
is indistinguishable from the contract change you were looking for.

```sh
cd arrt && uv run pytest -m live_museum -n0     # free, needs the network
cd arrt && uv run pytest -m live_binary -n0     # free, needs dezoomify-rs
cd arrt && uv run pytest -m live_api -n0        # SPENDS REAL MONEY
```

**A museum marker may run beside an OpenRouter marker, each serial within**
(the owner, 2026-11-09). `live_museum` and `live_binary` both reach museums (both
the Art Institute of Chicago, measured from `tests/live/` on 2026-11-09), and
`live_api` and `llm_eval` both reach OpenRouter on the one key, so running two
from the same pair at once is the concurrency the rate limit punishes, one level
up. One of each pair side by side shares no service. They stay on this machine:
`live_api` and `llm_eval` need the key, and none of them is on the testament pool
(`.testament.toml`).

**Locally the marker alone is enough; in CI it is not.** These commands collect
the whole tree and the opt-in modules `importorskip`, which is a skip you can
ignore at a terminal. In a workflow that same skip fails the job through
`assert_tests_ran.py` while every probe passed, so **a CI invocation scopes the
path as well** — `uv run pytest tests/live -m live_museum …`. That is asserted by
`tests/test_assert_tests_ran.py`, which reads the workflow files, so a new job
written from the line above fails at home rather than on a schedule.

Run one when your work touches that client. Otherwise leave the **three
`live_*` markers** to `.github/workflows/api-drift.yml`, which runs the two free
tiers weekly and the paid one monthly — drift is on the provider's schedule, not
on our commit rate.

**A probe red for a cause nobody has established is listed, not left to turn the
alarm permanently red.** `.github/known-blocked.json` has one row per probe (its
test, the issue where the cause is worked, an expiry no more than 60 days out,
and the reason, which says "not established" where it is not);
`.github/scripts/known_blocked.py` owns the shape. `judge_drift_probes.py`, not
pytest's exit code, decides whether the drift job fails: a red probe that is
listed is excused and named in the job summary with its expiry; a red probe that
is not listed fails the job; a listed probe that is green fails it, telling
whoever reads it to delete the row; an expired or malformed row fails by name.
A probe that never ran (skipped for want of a key, no report, nothing collected)
is never excused: that is `assert_tests_ran.py`'s finding, and no row covers it.
`drift-freshness.yml` counts a tier fresh when its only red probes are unexpired
rows, and checks every row's expiry on each push to `main`.
`tests/test_known_blocked.py`, `tests/test_judge_drift_probes.py` and
`tests/test_check_drift_freshness.py` hold this at the repository root.

**`llm_eval` is not in that workflow and is not meant to be.** It drives the
surface with a real model, so it spends and it can reach the same goal by a
different route next time; a non-deterministic check on a schedule either flakes
or gets loosened until it asserts nothing. It measures, and the contract level
gates. Run it by hand before shipping a tool-surface change — nothing else will.

**Every one of these tests skips itself when its dependency is missing**, which
is right locally and a trap in CI, where a green run that made no request looks
identical to a passing one. `.github/scripts/assert_tests_ran.py` is what closes
that: it fails the job on any skip and names which dependency was absent.

**Touching `library/acquisition/mat.py` or `library/acquisition/color.py`? Run the masters by
hand** — `cd arrt && uv run python tools/mat_masters.py ../all.json`. The
corpus's colours are in the repo but the paintings are the operator's masters, so
every test here uses synthetic flats, which have no cluster competition and no
pale regions; a near-white mat over a Mondrian shipped green for exactly that.
Needs `ART_ROOT`, spends nothing, writes nothing.

**A green suite says nothing about a branch no test reaches.** Before believing
new branches are covered, break them on purpose:
`cd arrt && uv run python tools/mutation_sweep.py <mutations.json> <test paths>`.
Its docstring has the format. It has found something on every change it has been
run on, and it is the check that a diff review does not substitute for — the
undefended branches all looked right when read.

Budget `(mutations + 1) x the time your chosen test paths take`. **The sweep runs
serial by the tool's own doing** — it passes `-n0` ahead of your arguments, so a
`-n` of your own still wins. That is correctness, not speed: with `-x` under
xdist a failing test ends the session as INTERRUPTED and pytest exits **2**, not
1, so every *caught* mutation looked like the unclassifiable exit the tool
refuses to guess at. Serial costs nothing worth having here — 67s against 65s for
ten mutations over two files, a slice being dominated by per-run worker startup.
