"""The type gate: mypy over the curation plane, its ratchet, its strict seam, and where it runs.

`arrt/pyproject.toml`'s `[tool.mypy]` checks the tree at mypy's defaults plus five
flags and checks the seam between the Library and Programming strictly. The plan
that built it is `build-plan-audit-wave-2.md` (Chunks 09 to 11, and its DECISION
lines). The ratchet, an `ignore_errors` override naming the modules that did not
yet check clean, was emptied by Chunk 11 and its block removed: every module is
checked.

**What the ratchet test does now.** It runs mypy once with any `ignore_errors`
override taken out of the configuration and compares the modules that report
errors with the modules such an override lists. With none listed, **any module
with an error fails it by name**, as it fails `uv run mypy`. A listed module that
checks clean fails it too. On its own that comparison would let an override be
put back that lists exactly the modules that fail, which silences mypy; so a
second test refuses any `ignore_errors` override at all. The list was emptied
once, and a type error is fixed, never excused.

Reads `arrt/pyproject.toml`, `arrt/uv.lock`, `.github/workflows/tests.yml` and
`CLAUDE.md`, and runs mypy in `arrt/`'s own environment (`uv run --no-sync`, so a
run never re-syncs that environment and drops a group the pool installed).
"""

import fnmatch
import pathlib
import re
import subprocess
import tomllib

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
ARRT = ROOT / "arrt"
PYPROJECT = ARRT / "pyproject.toml"

#: The seam's modules, which run strict: the plan's DECISION names them.
#: `arrt.services.conformance` states, in types, that the adapters satisfy the
#: seam's Protocols, so it is checked as strictly as they are.
SEAM_MODULES = (
    "arrt.library.events",
    "arrt.library.facade",
    "arrt.library.readiness",
    "arrt.persistence.catalogue",
    "arrt.programming.store",
    "arrt.services.conformance",
    "arrt.services.container",
)

#: `--strict`'s flags that the tree's own settings do not already turn on. Named
#: one by one in the override, because `strict = true` there applies globally.
STRICT_FLAGS = (
    "disallow_any_generics",
    "disallow_subclassing_any",
    "disallow_untyped_calls",
    "disallow_untyped_defs",
    "disallow_incomplete_defs",
    "disallow_untyped_decorators",
    "warn_return_any",
    "extra_checks",
)

#: The tree's flags beyond mypy's defaults (the DECISION's five).
TREE_FLAGS = ("check_untyped_defs", "warn_unused_ignores", "warn_redundant_casts", "strict_equality", "no_implicit_reexport")

_ERROR_LINE = re.compile(r"^(src/arrt/[^:]+\.py):\d+: error:", re.MULTILINE)


def _mypy_config() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["tool"]["mypy"]


def _overrides(*, ratchet: bool) -> list[dict]:
    found = [o for o in _mypy_config().get("overrides", []) if bool(o.get("ignore_errors")) == ratchet]
    return found


def _ratchet() -> list[str]:
    found = _overrides(ratchet=True)
    assert len(found) <= 1, "more than one ignore_errors override; the ratchet is one list"
    return list(found[0]["module"]) if found else []


def _strict_override() -> dict:
    found = [o for o in _overrides(ratchet=False) if o.get("disallow_untyped_defs")]
    assert len(found) == 1, f"expected one strict override for the seam, found {len(found)}"
    return found[0]


def _module_of(path: str) -> str:
    name = path.removeprefix("src/").removesuffix(".py").replace("/", ".")
    return name.removesuffix(".__init__")


def _listed(module: str, patterns: list[str]) -> bool:
    # mypy's `pkg.*` names the package and everything under it.
    return any(module == p or (p.endswith(".*") and (module == p[:-2] or fnmatch.fnmatch(module, p))) for p in patterns)


def _modules_with_errors(tmp_path: pathlib.Path) -> set[str]:
    """Every module mypy reports an error in, with the ratchet taken out of the configuration."""
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    mypy = config["tool"]["mypy"]
    mypy["overrides"] = [o for o in mypy.get("overrides", []) if not o.get("ignore_errors")]
    unratcheted = tmp_path / "pyproject.toml"
    unratcheted.write_text(_to_toml(mypy), encoding="utf-8")
    done = subprocess.run(
        # A cache of its own: options differ from the plain run's, and sharing one
        # cache would make each invalidate the other's (measured here: 22 s warm, minutes cold).
        [
            "uv",
            "run",
            "--no-sync",
            "mypy",
            "--config-file",
            str(unratcheted),
            "--cache-dir",
            ".mypy_cache/unratcheted",
            "--no-error-summary",
        ],
        cwd=ARRT,
        capture_output=True,
        text=True,
        check=False,
    )
    # 0 clean, 1 errors found; anything else is mypy not running, which is never a pass.
    assert done.returncode in {0, 1}, f"mypy did not run (exit {done.returncode}):\n{done.stdout}\n{done.stderr}"
    return {_module_of(path) for path in _ERROR_LINE.findall(done.stdout)}


def _to_toml(mypy: dict) -> str:
    """The `[tool.mypy]` table back as TOML, for the handful of value types it holds.

    Written as a `pyproject.toml`: mypy reads a `.toml` config file only in that shape.
    """

    def value(v: object) -> str:
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, str):
            return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
        if isinstance(v, list):
            return "[" + ", ".join(value(x) for x in v) + "]"
        raise TypeError(f"[tool.mypy] holds a {type(v).__name__}; teach _to_toml it")

    lines = ["[tool.mypy]"]
    lines += [f"{k} = {value(v)}" for k, v in mypy.items() if k != "overrides"]
    for override in mypy.get("overrides", []):
        lines.append("[[tool.mypy.overrides]]")
        lines += [f"{k} = {value(v)}" for k, v in override.items()]
    return "\n".join(lines) + "\n"


def test_the_ratchet_lists_exactly_the_modules_that_fail(tmp_path):
    listed = _ratchet()
    failing = _modules_with_errors(tmp_path)
    clean_but_listed = sorted(p for p in listed if not any(_listed(m, [p]) for m in failing))
    failing_unlisted = sorted(m for m in failing if not _listed(m, listed))
    assert not clean_but_listed, (
        f"these modules check clean and are still on the ratchet in arrt/pyproject.toml: {clean_but_listed}. "
        "Take them off the list, so they stay clean."
    )
    assert not failing_unlisted, (
        f"these modules have type errors and are not on the ratchet: {failing_unlisted}. "
        "Fix the errors (`cd arrt && uv run mypy`); never add a module to the list."
    )


def test_no_module_is_excused_from_the_type_check():
    listed = _ratchet()
    assert not listed, (
        f"arrt/pyproject.toml has an ignore_errors override again, naming {listed}. Every module is "
        "checked: fix the errors (`cd arrt && uv run mypy`) and take the override out."
    )


def test_the_ratchet_is_sorted_and_names_each_module_once():
    listed = _ratchet()
    assert listed == sorted(set(listed)), f"the ratchet is not sorted or repeats a module: {listed}"


def test_the_seam_is_checked_strictly_and_never_excused():
    strict = _strict_override()
    missing = sorted(set(SEAM_MODULES) - set(strict["module"]))
    assert not missing, f"seam modules missing from the strict override: {missing}"
    off = [flag for flag in STRICT_FLAGS if strict.get(flag) is not True]
    assert not off, f"the strict override does not set {off}"
    excused = sorted(m for m in SEAM_MODULES if _listed(m, _ratchet()))
    assert not excused, f"seam modules on the ratchet, so nothing checks them: {excused}"
    absent = [m for m in SEAM_MODULES if not (ARRT / "src" / (m.replace(".", "/") + ".py")).is_file()]
    assert not absent, f"seam modules that no longer exist where the override names them: {absent}"


def test_the_tree_runs_the_decisions_flags_over_the_source():
    config = _mypy_config()
    off = [flag for flag in TREE_FLAGS if config.get(flag) is not True]
    assert not off, f"[tool.mypy] does not set {off}"
    assert config.get("files") == ["src/arrt"], f"[tool.mypy] checks {config.get('files')}, not the plane's source"


def test_mypy_is_in_the_dev_group_and_the_lockfile():
    dev = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["dependency-groups"]["dev"]
    assert any(re.match(r"mypy\b", d) for d in dev), "mypy is not in arrt's dev group, so `uv run mypy` cannot find it"
    lock = tomllib.loads((ARRT / "uv.lock").read_text(encoding="utf-8"))
    assert any(p["name"] == "mypy" for p in lock["package"]), "arrt/uv.lock pins no mypy"


def _lint_step() -> str:
    workflow = yaml.safe_load((ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8"))
    steps = [s for job in workflow["jobs"].values() for s in job.get("steps", [])]
    lint = [s["run"] for s in steps if s.get("name", "").startswith("Lint and format")]
    assert len(lint) == 1, f"expected one lint step in tests.yml, found {len(lint)}"
    return lint[0]


@pytest.mark.parametrize("project", ["arrt", "contract"])
def test_ci_lint_step_runs_mypy_in_each_project(project):
    lines = [line.strip() for line in _lint_step().splitlines()]
    cd = {"arrt": "cd arrt", "contract": "cd ../contract"}[project]
    assert cd in lines, f"the lint step never enters {project}"
    start = lines.index(cd)
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("cd ")), len(lines))
    assert "uv run --frozen mypy" in lines[start:end], f"the lint step runs no mypy in {project}"


@pytest.mark.parametrize("project", ["arrt", "contract"])
def test_claude_md_table_names_the_type_check(project):
    rows = [line for line in (ROOT / "CLAUDE.md").read_text(encoding="utf-8").splitlines() if line.startswith("| Type-check |")]
    assert len(rows) == 1, "CLAUDE.md's dev-command table has no Type-check row"
    assert f"`cd {project} && uv run mypy`" in rows[0], f"CLAUDE.md's Type-check row names no mypy for {project}"
