"""No test that CI runs may skip for want of something CI never provides.

`.github/scripts/assert_tests_ran.py` fails the required check on any skip that is
not an expected failure, by design: in CI a skip means a dependency was not
provisioned. So a test whose skip is *legitimate* somewhere CI runs, because CI
never has what it needs, turns the check red while every test passes. That is how
the comparison of each frozen contract release with its git tag reached a pull
request: it skipped wherever the tags were absent, which is the pool (sent the tree
without tags) and GitHub's checkout (which fetches none), and no suite run before
the pull request read its report with the guard.

This reads every skip site (`pytest.skip`, `pytest.importorskip`, `pytest.mark.skip`,
`pytest.mark.skipif`) in the files each suite CI runs collects, from `.testament.toml`,
and requires each to be either

- **behind a marker that suite deselects** (on the test, its class, or the module's
  `pytestmark`), so no CI run collects it: the form of a check run by hand, like the
  live markers and `release_tags`; or
- **on `PROVISIONED` below**, with the reason CI's runs have what the skip waits
  for, so the skip can only fire when provisioning failed, which is the guard's
  finding and the right one.

It is a static read, so it sees only what the source says: a skip reached through a
helper defined elsewhere, or a marker added by a collection hook, is invisible to it.
The one hook-added marker that matters (the browser directory's) is listed by
directory, with the hook's line held below.
"""

import ast
import importlib.util
import pathlib
import re
import shlex
import sys
import tomllib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = REPO / ".testament.toml"

#: Skips that are allowed in a file CI runs, by path (a directory covers every file under
#: it), each with how many sites it holds and why CI's runs have what each waits for.
#: The count is held exactly, so a new skip in a listed file needs its own decision.
PROVISIONED: dict[str, tuple[int, str]] = {
    "arrt/tests/browser/": (
        77,
        "Playwright and Chromium: the browser suite runs only on the pool, whose setup syncs `--group browser` "
        "on runners labelled `chrome`; the fallback never runs it. A skip here is the provisioning failure the guard "
        "exists to catch.",
    ),
    "arrt/tests/unit/test_ages.py": (
        1,
        "node: the project's image copies it in (`.devcontainer/Dockerfile`), and GitHub's runner has it.",
    ),
    "arrt/tests/unit/test_route_parsing.py": (1, "node, as above."),
    "arrt/tests/unit/test_client_vocabulary.py": (1, "node, as above."),
    "arrt/tests/unit/test_one_date_formatter.py": (1, "node, as above."),
    "arrt/tests/unit/test_pre_migration_snapshot.py": (
        1,
        "skips only as root: the image runs as an unprivileged user it creates (`.devcontainer/Dockerfile`), "
        "and so does GitHub's runner.",
    ),
    "contract/tests/test_package.py": (1, "uv: every suite's command is `uv run`, so a run without uv never starts."),
    "contract/tests/test_typed.py": (1, "uv, as above."),
    "tests/preferences/test_citations_resolve.py": (
        1,
        "skips a live record present but not tracked: a clean checkout holds only tracked records, and the pool is "
        "sent no ignored file.",
    ),
    "tests/preferences/test_deployment_values.py": (
        1,
        "skips only with no `.env` and no `$HOME`; the image's user and GitHub's runner each have a home.",
    ),
}


def _decider():
    spec = importlib.util.spec_from_file_location("pool_or_fallback", REPO / ".github" / "scripts" / "pool_or_fallback.py")
    module = importlib.util.module_from_spec(spec)
    # Its dataclasses resolve their annotations through `sys.modules`.
    sys.modules.setdefault("pool_or_fallback", module)
    spec.loader.exec_module(module)
    return module


def _marker_expression(command: list[str]) -> str:
    """The `-m` a suite's run uses: its command's own, else its project's addopts'."""
    if "-m" in command:
        return command[command.index("-m") + 1]
    config = REPO / command[command.index("-c") + 1] if "-c" in command else REPO / "pyproject.toml"
    addopts = tomllib.loads(config.read_text(encoding="utf-8")).get("tool", {}).get("pytest", {}).get("ini_options", {})
    words = shlex.split(addopts.get("addopts", ""))
    return words[words.index("-m") + 1] if "-m" in words else ""


def deselected_by(expression: str) -> set[str]:
    """The markers an expression of the form `not a and not b` leaves out; anything else leaves out none."""
    return set(re.findall(r"\bnot\s+(\w+)", expression))


def ci_files() -> dict[pathlib.Path, set[str]]:
    """Each Python file a suite CI runs collects, with the markers every such suite deselects."""
    manifest = tomllib.loads(MANIFEST.read_text(encoding="utf-8"))
    not_ci = _decider().NOT_CI
    files: dict[pathlib.Path, set[str]] = {}
    for name, suite in manifest["suites"].items():
        if name in not_ci:
            continue
        deselected = deselected_by(_marker_expression(suite["command"]))
        for selected in suite["default_selection"]:
            path = REPO / selected
            found = sorted(path.rglob("*.py")) if path.is_dir() else [path]
            # A conftest above the selection runs too.
            found += [parent / "conftest.py" for parent in path.parents if REPO in parent.parents or parent == REPO]
            for file in found:
                if file.is_file():
                    files[file] = files[file] & deselected if file in files else set(deselected)
    return files


def _mark_names(decorators: list[ast.expr]) -> set[str]:
    names = set()
    for decorator in decorators:
        for node in ast.walk(decorator):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute) and node.value.attr == "mark":
                names.add(node.attr)
    return names


def _is_skip(node: ast.AST) -> bool:
    if isinstance(node, ast.Attribute):
        if node.attr in {"skip", "importorskip"} and isinstance(node.value, ast.Name) and node.value.id == "pytest":
            return True
        return node.attr in {"skip", "skipif"} and isinstance(node.value, ast.Attribute) and node.value.attr == "mark"
    if isinstance(node, ast.ImportFrom) and node.module == "pytest":
        return any(alias.name in {"skip", "importorskip"} for alias in node.names)
    return False


def unmarked_skips(source: str, deselected: set[str]) -> list[int]:
    """The line of each skip site in `source` not behind one of the `deselected` markers."""
    tree = ast.parse(source)
    module_marks: set[str] = set()
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in statement.targets):
            module_marks |= _mark_names([statement.value])
    if module_marks & deselected:
        return []
    lines = []

    def visit(node: ast.AST, marks: set[str]) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            marks = marks | _mark_names(node.decorator_list)
        if _is_skip(node) and not marks & deselected:
            lines.append(node.lineno)
        for child in ast.iter_child_nodes(node):
            visit(child, marks)

    visit(tree, set())
    return lines


def _listed_as(file: pathlib.Path) -> str | None:
    relative = file.relative_to(REPO).as_posix()
    for listed in PROVISIONED:
        if relative == listed or (listed.endswith("/") and relative.startswith(listed)):
            return listed
    return None


def test_the_scan_reads_every_suite_ci_runs():
    """A scan over no files passes by checking nothing."""
    files = ci_files()
    for project in ("tests", "arrt/tests", "contract/tests"):
        assert any(f.is_relative_to(REPO / project) for f in files), project
    assert len(files) > 300, len(files)


def test_no_skip_in_a_file_ci_runs_waits_for_something_ci_never_provides():
    counts: dict[str, int] = {}
    unlisted = []
    for file, deselected in sorted(ci_files().items()):
        lines = unmarked_skips(file.read_text(encoding="utf-8"), deselected)
        if not lines:
            continue
        listed = _listed_as(file)
        if listed is None:
            unlisted += [f"{file.relative_to(REPO)}:{line}" for line in lines]
        else:
            counts[listed] = counts.get(listed, 0) + len(lines)
    assert not unlisted, (
        "these skips can fire in a suite CI runs, and CI's guard fails the required check on any skip: put the test "
        "behind a marker its project deselects by default and run it by hand (as `release_tags` and the live markers are), "
        f"or list it in PROVISIONED with why CI has what it waits for: {unlisted}"
    )
    assert counts == {
        listed: count for listed, (count, _) in PROVISIONED.items()
    }, "a listed file's skips changed in number, or a listed entry holds none: each skip needs its own reason"


def test_the_browser_directory_is_marked_by_its_conftest():
    """The one marker this scan cannot see, because a collection hook adds it, is held here instead."""
    conftest = (REPO / "arrt" / "tests" / "browser" / "conftest.py").read_text(encoding="utf-8")
    assert "item.add_marker(pytest.mark.browser)" in conftest


# -- the scan itself -------------------------------------------------------------------

DESELECTED = {"release_tags"}


@pytest.mark.parametrize(
    ("source", "found"),
    [
        ("import pytest\ndef test_a():\n    pytest.skip('no tag')\n", [3]),
        ("import pytest\nx = pytest.importorskip('playwright')\n", [2]),
        ("import pytest\n@pytest.mark.skipif(True, reason='r')\ndef test_a():\n    pass\n", [2]),
        ("import pytest\npytestmark = [pytest.mark.skipif(True, reason='r')]\n", [2]),
        ("from pytest import skip\n", [1]),
        ("import pytest\n@pytest.mark.release_tags\ndef test_a():\n    pytest.skip('no tag')\n", []),
        ("import pytest\n@pytest.mark.release_tags\nclass TestA:\n    def test_a(self):\n        pytest.skip('x')\n", []),
        ("import pytest\npytestmark = pytest.mark.release_tags\ndef test_a():\n    pytest.skip('no tag')\n", []),
        ("import pytest\n@pytest.mark.other\ndef test_a():\n    pytest.skip('no tag')\n", [4]),
        ("import pytest\ndef test_a():\n    pytest.fail('no tag')\n", []),
    ],
)
def test_the_scan_finds_a_skip_unless_a_deselected_marker_covers_it(source, found):
    assert unmarked_skips(source, DESELECTED) == found


def test_a_marker_expression_leaves_out_only_what_it_negates():
    assert deselected_by("not llm_eval and not browser") == {"llm_eval", "browser"}
    assert deselected_by("browser") == set()
    assert deselected_by("") == set()


def test_each_suite_reads_its_own_marker_expression():
    """The browser suite selects `browser`, so its own skips are not excused by the curation plane's addopts."""
    manifest = tomllib.loads(MANIFEST.read_text(encoding="utf-8"))
    assert "browser" in deselected_by(_marker_expression(manifest["suites"]["curation"]["command"]))
    assert deselected_by(_marker_expression(manifest["suites"]["browser"]["command"])) == set()
    assert deselected_by(_marker_expression(manifest["suites"]["contract"]["command"])) == {"release_tags"}
