"""A word that agrees with a count is chosen by `arrt.counting`, never by a test of one in the sentence's own module.

Everywhere the server says how many of something there are, the noun and the verb around the
number have to agree with it, and the number reads one way (`2,000 works`, not `2000 works`).
`counting.py` is that rule, once: `counted`, `noun`, `agree`, `agree_partitive`, `figure`,
`times`. A sentence that chooses its own word (`"work" if n == 1 else "works"`) copies the rule,
and a copy is what was wrong in six lines of one function before the helper existed
(`counting.py`'s docstring). This refuses the copy, in every module under `arrt/src/arrt`, read
from the directory, so a module added tomorrow is read tomorrow
(`test_one_cost_formatter.py` does the same for a dollar).

**What it refuses:** a conditional expression whose test is a comparison of something with the
number one (`== 1`, `!= 1`, either side), or a name that was assigned such a comparison in the
same function (`one = len(walls) == 1`), where a branch is text: a string, an f-string or text
joined with `+`.

**What it does not refuse, and the limits that follow:**

* A test that is not of one: `> 1`, `>= 2`, `== 0`. A list is joined with "and" after its
  second name by a test of two or more (`_listed`), which is punctuation, not agreement;
  `x if len(a) > 1 else y` over text is not read.
* An `if` statement that says a whole other sentence for one (`if len(shown) == 1: return "'A' last
  reported…"`): that is a different sentence, not a word that agrees, and a statement is too
  wide a net: it also holds a validation of "major version 1".
* A conditional whose branches are not text: `model if len(models) == 1 else None` picks a
  value, not a word.
* A word chosen from a count the guard cannot see the test of: one computed in another
  function and passed in as a boolean, a lookup table, `"s" * (n != 1)`, `ngettext`.
* `counting.py`, which is the writer: its own tests of one are the rule.
* Whether a digit is grouped: a measure (bytes, characters, pixels, dollars) groups its own
  digits where it is said, and is not a count of things.
"""

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

import arrt

SRC = Path(arrt.__file__).resolve().parent

#: The one module that decides how a count is spelled.
WRITER = SRC / "counting.py"


def modules_under(root: Path) -> list[Path]:
    """Every module under `root` that is not the writer, found by a glob so a module added later is read."""
    return sorted(path for path in root.rglob("*.py") if path != root / "counting.py")


MODULES = modules_under(SRC)


def _is_one(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value == 1 and not isinstance(node.value, bool)


def _compares_with_one(node: ast.expr) -> bool:
    """`n == 1`, `n != 1`, `1 == n`, `1 != n`, and a chain holding one of them."""
    if not isinstance(node, ast.Compare):
        return False
    operands = [node.left, *node.comparators]
    return any(
        isinstance(op, ast.Eq | ast.NotEq) and (_is_one(left) or _is_one(right))
        for op, left, right in zip(node.ops, operands, operands[1:], strict=False)
    )


def _is_text(node: ast.expr | None) -> bool:
    """A string, an f-string, or text joined onto with `+`."""
    if node is None:
        return False
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _is_text(node.left) or _is_text(node.right)
    return False


def _tests_one(test: ast.expr, ones: set[str]) -> bool:
    """A comparison with one, a name assigned one, either negated, or either inside `and`/`or`."""
    if _compares_with_one(test):
        return True
    if isinstance(test, ast.Name):
        return test.id in ones
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        return _tests_one(test.operand, ones)
    if isinstance(test, ast.BoolOp):
        return any(_tests_one(value, ones) for value in test.values)
    return False


def _within(scope: ast.AST) -> Iterator[ast.AST]:
    """The nodes of one scope: a function's own, or the module's own, without those of a function inside it."""
    pending = list(ast.iter_child_nodes(scope))
    while pending:
        node = pending.pop()
        yield node
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            pending.extend(ast.iter_child_nodes(node))


def _ones_in(scope: ast.AST) -> set[str]:
    """The names this function (or the module) assigns the result of a comparison with one."""
    names: set[str] = set()
    for node in _within(scope):
        if isinstance(node, ast.Assign) and _compares_with_one(node.value):
            names |= {target.id for target in node.targets if isinstance(target, ast.Name)}
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
            and _compares_with_one(node.value)
        ):
            names.add(node.target.id)
    return names


def chosen_words(source: str) -> list[tuple[int, str]]:
    """Each line of `source` that chooses text by a test of one: its number and its text."""
    lines = source.splitlines()
    tree = ast.parse(source)
    found: dict[int, str] = {}
    scopes = [tree, *(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef))]
    for scope in scopes:
        ones = _ones_in(scope)
        for node in _within(scope):
            chose = False
            if isinstance(node, ast.IfExp):
                chose = _tests_one(node.test, ones) and (_is_text(node.body) or _is_text(node.orelse))
            if chose:
                found[node.lineno] = lines[node.lineno - 1].strip()
    return sorted(found.items())


@pytest.mark.parametrize("module", MODULES, ids=lambda module: module.relative_to(SRC).as_posix())
def test_no_module_but_counting_chooses_a_word_by_a_test_of_one(module):
    found = chosen_words(module.read_text(encoding="utf-8"))
    assert found == [], (
        f"{module.relative_to(SRC)} chooses a word by a test of one: say the count through arrt.counting "
        f"(counted, noun, agree, agree_partitive, figure, times): {found}"
    )


def test_the_modules_are_read_from_the_directory():
    """The parametrisation is not empty, and reaches the modules that once chose their own words."""
    names = {module.relative_to(SRC).as_posix() for module in MODULES}
    assert {
        "services/health.py",
        "library/sources/loading.py",
        "library/discovery/pool.py",
        "observations.py",
        "persistence/file.py",
    } <= names
    assert len(names) > 100, "the glob found a tree, not a file"
    assert "counting.py" not in names


def test_the_check_reads_the_writer_it_exempts():
    """Falsifiable: the writer itself tests for one, so the pattern is not one that matches nothing."""
    assert chosen_words(WRITER.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "planted",
    [
        'return "work" if count == 1 else "works"',
        'return "works" if count != 1 else "work"',
        'return "work" if 1 == count else "works"',
        "return f\"{count} {'copy' if count == 1 else 'copies'}\"",
        'said = "the work waits for " + ("it." if len(owed) == 1 else "them.")',
        'said = f"{count:,} works" if count != 1 else "1 work"',
        'said = "has" if len(quiet) == 1 and not loud else "have"',
        'said = "is" if not count == 1 else "are"',
        'said = "is" if 0 < count == 1 else "are"',
    ],
)
def test_a_planted_word_chosen_by_a_test_of_one_is_found(planted):
    found = chosen_words(f"def sentence(count, owed=(), quiet=(), loud=False):\n    {planted}\n")
    assert [line for _, line in found] == [planted]


def test_a_word_chosen_by_a_flag_that_holds_a_test_of_one_is_found():
    """`one = len(walls) == 1` and then `"waits" if one else "wait"`: the test is two lines apart."""
    source = (
        "def words(walls):\n"
        "    one = len(walls) == 1\n"
        '    return "waits" if one else "wait"\n'
        "def unrelated(walls, one):\n"
        '    return "waits" if one else "wait"\n'
    )
    assert chosen_words(source) == [(3, 'return "waits" if one else "wait"')]


@pytest.mark.parametrize(
    "innocent",
    [
        "model = next(iter(models)) if len(models) == 1 else None",
        "version = versions.pop() if len(versions) == 1 else None",
        'said = "none" if count == 0 else "some"',
        'said = ", so the wall is dark" if placed == 0 else ""',
        'said = " and " if len(names) > 1 else ""',
        "text = counted(count, 'work')",
        'said = "yes" if flag else "no"',
        'said = "a" if count == 1.5 else "b"',
        "number = 1 if count == 1 else 2",
        'if count == 1:\n        said = "one work"\n    else:\n        said = "some works"',
    ],
)
def test_what_does_not_choose_a_word_by_a_test_of_one_is_not_found(innocent):
    assert chosen_words(f"def f(count, models=(), versions=(), placed=0, names=(), flag=False):\n    {innocent}\n") == []


def test_a_word_chosen_in_a_module_the_guard_had_not_seen_is_found(tmp_path):
    """A module added tomorrow is read tomorrow: the glob finds it, and the check names its line."""
    (tmp_path / "counting.py").write_text('def noun():\n    return "a" if 1 == 1 else "b"\n', encoding="utf-8")
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "a_module_added_later.py").write_text(
        "def sentence(count):\n    return f\"{count} {'item' if count == 1 else 'items'}\"\n", encoding="utf-8"
    )
    found = {
        module.relative_to(tmp_path).as_posix(): chosen_words(module.read_text(encoding="utf-8"))
        for module in modules_under(tmp_path)
    }
    assert found == {"elsewhere/a_module_added_later.py": [(2, "return f\"{count} {'item' if count == 1 else 'items'}\"")]}
