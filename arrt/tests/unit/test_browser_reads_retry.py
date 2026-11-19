"""The browser suite reads the page through Playwright's retrying assertions.

A one-shot read (`loc.inner_text()`, `loc.count()`, `loc.is_visible()`, …)
returns what the page holds at the instant it is called, and an `assert` on it
passes or fails on whichever side of a repaint that instant fell. That is the
mechanism behind most of this suite's flakes (audit 7, S1a; #441, #442, #371),
and a prose rule in `tests/browser/conftest.py` did not stop new ones being
written. `expect(loc).to_have_text(…)` asks the same question and keeps asking
until the page agrees or the timeout passes.

This guard reads every file in `tests/browser/` and counts two things:

- **one-shot reads**: a call of one of `READS` anywhere in the file, unless its
  statement carries `# one-shot: <why>` on one of its lines. The reason is for a
  read that computes a value rather than asserts one (a title to click, a count
  to compare later), placed after a wait or an `expect` of the state it reads;
- **fixed sleeps**: `wait_for_timeout`, `time.sleep`, `asyncio.sleep`, or an
  `evaluate` whose script waits on `setTimeout`, unless its statement carries
  `# sleep: <why>`: one that proves nothing happens for a while, which no
  condition can stand for.

A file not in `UNCONVERTED` must count zero of both. A file in it must count
exactly what it is listed with: higher is a new one-shot read, lower is a
conversion that did not lower the list, and zero is a converted file still on
it. So the list only shrinks, and it cannot go stale. Chunks 13–19 of
`build-plan-audit-wave-2.md` each take their files off it. The conversion
table that says what each read becomes is `docs/testing.md` § "Assertions read
the page through `expect`".
"""

import ast
import io
import pathlib
import re
import tokenize

import pytest

BROWSER_DIR = pathlib.Path(__file__).resolve().parents[1] / "browser"

#: Playwright's one-shot reads, by method name, each with the positional
#: argument counts its Locator and Page forms take. A count outside them is
#: another object's method of the same name (`str.count("x")`, `str.title()`
#: takes none and so is counted: none occurs in this suite). `text` is the
#: suite's own `Ui.text()`, the view's `innerText`.
READS = {
    "all_inner_texts": {0},
    "all_text_contents": {0},
    "bounding_box": {0, 1},
    "count": {0},
    "get_attribute": {1, 2},
    "inner_html": {0, 1},
    "inner_text": {0, 1},
    "input_value": {0, 1},
    "is_checked": {0, 1},
    "is_disabled": {0, 1},
    "is_editable": {0, 1},
    "is_enabled": {0, 1},
    "is_hidden": {0, 1},
    "is_visible": {0, 1},
    "text": {0},
    "text_content": {0, 1},
    "title": {0},
}

#: Calls that wait a fixed time rather than for a condition.
SLEEPS = {"wait_for_timeout", "sleep"}

#: A marker that names a reason: the word, a colon, and at least one word after it.
ONE_SHOT_MARK = re.compile(r"#.*\bone-shot:\s*\S")
SLEEP_MARK = re.compile(r"#.*\bsleep:\s*\S")

#: The files not yet converted, each with its count of (one-shot reads, fixed
#: sleeps) at the commit that wrote this guard. Sorted; each chunk of 13-19
#: deletes its own rows as it converts them.
UNCONVERTED: dict[str, tuple[int, int]] = {
    "test_acquisition_states.py": (40, 0),
    "test_activity.py": (14, 0),
    "test_archiving_a_work.py": (35, 0),
    "test_asking.py": (50, 2),
    "test_clean_up_facets.py": (19, 0),
    "test_component_rules.py": (7, 0),
    "test_copy_says_it_once.py": (21, 0),
    "test_displays_and_labels.py": (18, 0),
    "test_editing_a_wall.py": (36, 1),
    "test_fact_lists_on_a_phone.py": (1, 0),
    "test_general_settings.py": (31, 0),
    "test_getting.py": (46, 0),
    "test_keyboard_and_phone.py": (9, 0),
    "test_names_that_link.py": (23, 0),
    "test_no_machine_dates.py": (2, 1),
    "test_one_selection_model.py": (45, 0),
    "test_pages_for_what_is_not_held.py": (32, 0),
    "test_pictures_where_a_person_decides.py": (11, 0),
    "test_review_folds.py": (21, 0),
    "test_review_trust.py": (32, 4),
    "test_reviewing_a_get.py": (48, 1),
    "test_scenes_on_walls.py": (23, 0),
    "test_search_and_artist_states.py": (22, 0),
    "test_search_in_two_scopes.py": (26, 2),
    "test_setting_up_a_wall.py": (6, 0),
    "test_shared_rules_and_phone.py": (4, 0),
    "test_similar_artists_and_identity.py": (23, 1),
    "test_spend.py": (7, 0),
    "test_taste_and_reactions.py": (18, 0),
    "test_the_artist_page.py": (51, 0),
    "test_the_brand_goes_home.py": (7, 0),
    "test_the_clients.py": (75, 0),
    "test_the_collection.py": (107, 1),
    "test_the_confirmation.py": (9, 0),
    "test_the_controls.py": (8, 0),
    "test_the_debug_view.py": (14, 0),
    "test_the_grid.py": (24, 2),
    "test_the_health_panel.py": (9, 0),
    "test_the_history.py": (21, 0),
    "test_the_look.py": (26, 1),
    "test_the_review_grid.py": (84, 0),
    "test_the_run_view.py": (65, 8),
    "test_the_search_results_page.py": (39, 0),
    "test_the_settings_index.py": (11, 0),
    "test_the_shell.py": (2, 1),
    "test_the_sidebar.py": (73, 0),
    "test_the_sources_page.py": (19, 0),
    "test_the_status_sources_table.py": (4, 0),
    "test_the_theme_page_shows_its_art.py": (17, 0),
    "test_the_theme_screen.py": (66, 1),
    "test_the_themes_index.py": (33, 2),
    "test_the_toolbar.py": (21, 0),
    "test_the_walls.py": (91, 1),
    "test_the_way_back.py": (20, 0),
    "test_the_work_page.py": (50, 0),
    "test_tiles_show_the_art.py": (2, 0),
    "test_to_review.py": (9, 0),
    "test_topics.py": (70, 1),
    "test_wanted.py": (33, 4),
    "test_watches_screen.py": (16, 0),
}


def _is_read(call: ast.Call) -> bool:
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr not in READS:
        return False
    return len(call.args) in READS[func.attr]


def _is_sleep(call: ast.Call) -> bool:
    func = call.func
    name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
    if name in SLEEPS:
        return True
    if name == "evaluate":
        return any(
            isinstance(arg, ast.Constant) and isinstance(arg.value, str) and "setTimeout(" in arg.value for arg in call.args
        )
    return False


def _comments(source: str) -> dict[int, str]:
    found: dict[int, str] = {}
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            found[token.start[0]] = token.string
    return found


def _statement_lines(tree: ast.AST) -> dict[int, range]:
    """Each line, mapped to the lines of the innermost statement holding it.

    A marker belongs to a statement, not a line, so a call on the third line of
    a wrapped `assert` is excused by a reason written on its first.
    """
    spans: dict[int, range] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.stmt):
            span = range(node.lineno, (node.end_lineno or node.lineno) + 1)
            for line in span:
                held = spans.get(line)
                if held is None or len(span) < len(held):
                    spans[line] = span
    return spans


def counts(path: pathlib.Path) -> tuple[list[int], list[int]]:
    """The lines of `path`'s unexcused one-shot reads and fixed sleeps."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    comments = _comments(source)
    spans = _statement_lines(tree)

    def marked(line: int, mark: re.Pattern) -> bool:
        return any(mark.search(comments.get(each, "")) for each in spans.get(line, range(line, line + 1)))

    reads, sleeps = [], []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _is_read(node) and not marked(node.lineno, ONE_SHOT_MARK):
            reads.append(node.lineno)
        elif _is_sleep(node) and not marked(node.lineno, SLEEP_MARK):
            sleeps.append(node.lineno)
    return sorted(reads), sorted(sleeps)


def _converted(name: str, reads: list[int], sleeps: list[int]) -> list[str]:
    """What a file off the list may not hold: any unexcused read or sleep."""
    found = []
    if reads:
        found.append(
            f"{name} reads the page once at lines {reads}: assert through expect() (docs/testing.md), "
            "or say why on the statement with '# one-shot: <why>'"
        )
    if sleeps:
        found.append(
            f"{name} sleeps a fixed time at lines {sleeps}: wait for the condition it stands for, "
            "or say why on the statement with '# sleep: <why>'"
        )
    return found


def _listed(name: str, reads: list[int], sleeps: list[int], listed: tuple[int, int]) -> list[str]:
    """What a file on the list must hold: exactly its counts, and something left to convert."""
    if not reads and not sleeps:
        return [f"{name} is converted: take it off UNCONVERTED"]
    listed_reads, listed_sleeps = listed
    found = []
    if len(reads) != listed_reads:
        change = "a new one-shot read" if len(reads) > listed_reads else "converted reads the list still counts"
        found.append(f"{name} has {len(reads)} one-shot reads, listed with {listed_reads} ({change}): lines {reads}")
    if len(sleeps) != listed_sleeps:
        change = "a new fixed sleep" if len(sleeps) > listed_sleeps else "replaced sleeps the list still counts"
        found.append(f"{name} has {len(sleeps)} fixed sleeps, listed with {listed_sleeps} ({change}): lines {sleeps}")
    return found


def problems(directory: pathlib.Path, unconverted: dict[str, tuple[int, int]]) -> list[str]:
    """Every way `directory` disagrees with `unconverted`, in words that name the file."""
    found = ["UNCONVERTED is not sorted"] if list(unconverted) != sorted(unconverted) else []
    present = {path.name: path for path in sorted(directory.glob("*.py"))}
    found += [
        f"{name} is listed as not converted and does not exist: take it off the list"
        for name in unconverted
        if name not in present
    ]
    for name, path in present.items():
        reads, sleeps = counts(path)
        found += _listed(name, reads, sleeps, unconverted[name]) if name in unconverted else _converted(name, reads, sleeps)
    return found


def test_the_browser_suite_reads_the_page_through_retrying_assertions():
    assert problems(BROWSER_DIR, UNCONVERTED) == []


def test_the_guard_reads_the_suite_it_is_about():
    """A guard over an empty glob is green and guards nothing."""
    names = {path.name for path in BROWSER_DIR.glob("*.py")}
    assert {"conftest.py", "test_navigation.py", "test_walls_last_and_next.py"} <= names


# -- the guard's own behaviour, on planted files -------------------------------


def _plant(directory: pathlib.Path, name: str, body: str) -> None:
    (directory / name).write_text(body, encoding="utf-8")


def test_a_one_shot_read_in_a_converted_file_is_refused_by_name_and_line(tmp_path):
    _plant(tmp_path, "test_a.py", "def test_x(ui):\n    assert ui.page.locator('h1').inner_text() == 'Walls'\n")
    assert problems(tmp_path, {}) == [
        (
            "test_a.py reads the page once at lines [2]: assert through expect() (docs/testing.md), "
            "or say why on the statement with '# one-shot: <why>'"
        )
    ]


@pytest.mark.parametrize(
    "read",
    [
        "loc.inner_text()",
        "loc.text_content()",
        "loc.inner_html()",
        "loc.all_inner_texts()",
        "loc.all_text_contents()",
        "loc.count()",
        "loc.is_visible()",
        "loc.is_hidden()",
        "loc.is_checked()",
        "loc.is_disabled()",
        "loc.is_enabled()",
        "loc.is_editable()",
        "loc.get_attribute('href')",
        "loc.input_value()",
        "loc.bounding_box()",
        "page.title()",
        "ui.text()",
        "page.inner_text('#view')",
        "page.get_attribute('a', 'href')",
        "page.is_visible('h1')",
    ],
)
def test_each_read_is_counted_wherever_it_stands(tmp_path, read):
    """In an assert, assigned and asserted later, or inside a comprehension: all one-shot."""
    _plant(
        tmp_path,
        "test_a.py",
        f"def test_x(ui, loc, page):\n    assert {read}\n    seen = {read}\n    assert [x for x in [{read}]]\n",
    )
    assert counts(tmp_path / "test_a.py") == ([2, 3, 4], [])


def test_a_method_of_the_same_name_on_another_object_is_not_a_read(tmp_path):
    _plant(tmp_path, "test_a.py", "def test_x(text):\n    assert text.count('screen off') == 1\n")
    assert counts(tmp_path / "test_a.py") == ([], [])


def test_a_read_with_a_reason_is_excused_and_one_without_is_not(tmp_path):
    _plant(
        tmp_path,
        "test_a.py",
        "def test_x(loc):\n"
        "    title = loc.inner_text()  # one-shot: the title to click, read after the grid painted\n"
        "    other = loc.inner_text()  # one-shot:\n"
        "    assert (\n"
        "        loc.count()\n"
        "        == 3\n"
        "    )  # one-shot: a wrapped statement is excused by a reason on any of its lines\n",
    )
    assert counts(tmp_path / "test_a.py") == ([3], [])


@pytest.mark.parametrize(
    "sleep",
    [
        "ui.page.wait_for_timeout(500)",
        "time.sleep(0.5)",
        "asyncio.sleep(1)",
        "sleep(1)",
        "ui.page.evaluate('() => new Promise((resolve) => setTimeout(resolve, 100))')",
    ],
)
def test_a_fixed_sleep_is_refused_unless_its_line_says_why(tmp_path, sleep):
    _plant(tmp_path, "test_a.py", f"def test_x(ui):\n    {sleep}\n    {sleep}  # sleep: two polls pass and nothing is sent\n")
    assert problems(tmp_path, {}) == [
        (
            "test_a.py sleeps a fixed time at lines [2]: wait for the condition it stands for, "
            "or say why on the statement with '# sleep: <why>'"
        )
    ]


def test_an_evaluate_that_does_not_wait_is_not_a_sleep(tmp_path):
    _plant(tmp_path, "test_a.py", "def test_x(ui):\n    assert ui.page.evaluate('() => window.scrollY') == 0\n")
    assert counts(tmp_path / "test_a.py") == ([], [])


def test_a_listed_file_must_count_exactly_what_it_is_listed_with(tmp_path):
    _plant(tmp_path, "test_a.py", "def test_x(loc):\n    assert loc.count() == 1\n    assert loc.is_visible()\n")
    assert problems(tmp_path, {"test_a.py": (2, 0)}) == []
    assert problems(tmp_path, {"test_a.py": (1, 0)}) == [
        "test_a.py has 2 one-shot reads, listed with 1 (a new one-shot read): lines [2, 3]"
    ]
    assert problems(tmp_path, {"test_a.py": (3, 0)}) == [
        "test_a.py has 2 one-shot reads, listed with 3 (converted reads the list still counts): lines [2, 3]"
    ]
    assert problems(tmp_path, {"test_a.py": (2, 1)}) == [
        "test_a.py has 0 fixed sleeps, listed with 1 (replaced sleeps the list still counts): lines []"
    ]


def test_a_listed_file_with_nothing_left_to_convert_must_leave_the_list(tmp_path):
    _plant(tmp_path, "test_a.py", "def test_x(loc):\n    expect(loc).to_have_count(1)\n")
    assert problems(tmp_path, {"test_a.py": (1, 0)}) == ["test_a.py is converted: take it off UNCONVERTED"]


def test_a_listed_file_that_does_not_exist_must_leave_the_list(tmp_path):
    assert problems(tmp_path, {"test_gone.py": (1, 0)}) == [
        "test_gone.py is listed as not converted and does not exist: take it off the list"
    ]


def test_the_list_is_sorted(tmp_path):
    _plant(tmp_path, "test_a.py", "x = loc.count()\n")
    _plant(tmp_path, "test_b.py", "x = loc.count()\n")
    assert problems(tmp_path, {"test_b.py": (1, 0), "test_a.py": (1, 0)}) == ["UNCONVERTED is not sorted"]
