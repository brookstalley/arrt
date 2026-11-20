"""The type gate: mypy over the curation plane and the contract package, its strict seam, and where it runs.

`arrt/pyproject.toml`'s `[tool.mypy]` checks the tree at mypy's defaults plus five
flags and checks the seam between the Library and Programming strictly;
`contract/pyproject.toml`'s checks the package's source `--strict`. The plan that
built it is `build-plan-audit-wave-2.md` (Chunks 09 to 11, and its DECISION lines).
The ratchet, an `ignore_errors` override naming the modules that did not yet check
clean, was emptied by Chunk 11 and its block removed: every module is checked.

**Where the type check runs: here, once per change, on the pool.** The test below
runs mypy in each project with that project's own configuration and fails, naming
the modules, on any error. The governance suite runs on testament's pool on every
pull request (`tests.yml`), and on GitHub's runner only when the pool cannot answer,
where the fallback's governance step syncs both environments first. CI's lint step
does not run mypy: it would need each project's whole runtime installed on GitHub's
runner for every pull request, which the 2026-11-18 ruling rules out. `cd arrt && uv
run mypy` and `cd contract && uv run mypy` are the same check, by hand (CLAUDE.md).

mypy runs in each project's own environment with `uv run --no-sync`, so a run never
re-syncs that environment and drops a group the pool installed. When that
environment does not exist (a fresh clone), the test fails saying what to run,
never as a type error.

What the type check needs installed in the fallback's environment is
`test_type_gate_in_the_fallback.py`'s (the pool's environment has the `browser` group; the
fallback's has `dev` only).

Reads `arrt/pyproject.toml`, `arrt/uv.lock`, `contract/pyproject.toml`,
`contract/src/arrt_contract/py.typed`, `.github/workflows/tests.yml` and `CLAUDE.md`.
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

#: The projects mypy checks, each with the command that makes its environment.
PROJECTS = {
    "arrt": "cd arrt && uv sync --group dev --group browser",
    "contract": "cd contract && uv sync --group dev",
}

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

#: What `[tool.mypy]` checks: the plane's source and, since 2026-11-20, the system
#: tests, which run the server as a process. Until then it
#: was `["src/arrt"]`, and the system tests held 26 errors nothing reported.
CHECKED_FILES = ["src/arrt", "tests/system"]

#: The tree's flags beyond mypy's defaults (the DECISION's five).
TREE_FLAGS = ("check_untyped_defs", "warn_unused_ignores", "warn_redundant_casts", "strict_equality", "no_implicit_reexport")

#: An error line as mypy prints it from a project's root: `<path>.py:<line>: error:`, under `src/`
#: or in another file it checks or follows (`tests/system/`, `tests/`, `tools/`).
_ERROR_LINE = re.compile(r"^([^:\s]+\.py):\d+: error:", re.MULTILINE)


def _mypy_config(project: str = "arrt") -> dict:
    return tomllib.loads((ROOT / project / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["mypy"]


def _overrides(*, ratchet: bool, project: str = "arrt") -> list[dict]:
    return [o for o in _mypy_config(project).get("overrides", []) if bool(o.get("ignore_errors")) == ratchet]


def _ratchet(project: str = "arrt") -> list[str]:
    """The modules any `ignore_errors` override excuses, in every such override."""
    modules = [o["module"] for o in _overrides(ratchet=True, project=project)]
    return [m for listed in modules for m in ([listed] if isinstance(listed, str) else listed)]


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


def mypy_verdict(project: str, done: subprocess.CompletedProcess) -> str | None:
    """What a mypy run in `project` says against the gate: None when it checked clean, else why it fails.

    0 is clean; 1 is errors, named by module; a run uv could not start is the missing
    environment, named with the command that makes it; anything else is mypy not
    running, which is never a pass.
    """
    if done.returncode == 0:
        return None
    if "Failed to spawn" in done.stderr:
        return (
            f"mypy could not be started in {project}/: its environment does not exist or has no dev group. "
            f"Run `{PROJECTS[project]}`, then this test again. This is not a type error.\n{done.stderr.strip()}"
        )
    if done.returncode == 1:
        modules = sorted({_module_of(path) for path in _ERROR_LINE.findall(done.stdout)})
        if modules:
            return (
                f"mypy reports type errors in {project}/, in {modules}. Fix them (`cd {project} && uv run mypy`); "
                f"no module is excused.\n{done.stdout[-4000:]}"
            )
    return f"mypy did not run in {project}/ (exit {done.returncode}):\n{done.stdout[-2000:]}\n{done.stderr[-2000:]}"


def _run_mypy(project: str) -> subprocess.CompletedProcess:
    return subprocess.run(["uv", "run", "--no-sync", "mypy"], cwd=ROOT / project, capture_output=True, text=True, check=False)


@pytest.mark.parametrize("project", sorted(PROJECTS))
def test_mypy_reports_no_error_in_any_module(project):
    verdict = mypy_verdict(project, _run_mypy(project))
    assert verdict is None, verdict


def _done(code: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(["uv", "run", "--no-sync", "mypy"], code, stdout, stderr)


def test_a_module_with_a_type_error_fails_the_gate_by_name():
    out = (
        'src/arrt/library/facade.py:12: error: Incompatible return value type (got "int", expected "str")  [return-value]\n'
        'src/arrt/library/__init__.py:3: error: Name "x" is not defined  [name-defined]\n'
    )
    verdict = mypy_verdict("arrt", _done(1, out))

    assert verdict and "['arrt.library', 'arrt.library.facade']" in verdict


def test_a_system_test_with_a_type_error_fails_the_gate_by_name():
    """The line is mypy's, copied from `cd arrt && uv run mypy src/arrt tests/system` at the 2026-11-20 reset point."""
    out = 'tests/system/test_a_real_player.py:695: error: Value of type "dict[Any, Any] | None" is not indexable  [index]\n'
    verdict = mypy_verdict("arrt", _done(1, out))

    assert verdict and "['tests.system.test_a_real_player']" in verdict


def test_a_missing_environment_says_what_to_run_not_a_type_error():
    stderr = "error: Failed to spawn: `mypy`\n  Caused by: No such file or directory (os error 2)\n"
    verdict = mypy_verdict("arrt", _done(2, stderr=stderr))

    assert verdict and "`cd arrt && uv sync --group dev --group browser`" in verdict and "not a type error" in verdict


@pytest.mark.parametrize("code,stdout", [(1, "Success: no issues found\n"), (2, "mypy: can't read file 'src'\n"), (-9, "")])
def test_a_mypy_that_did_not_check_is_never_a_pass(code, stdout):
    assert mypy_verdict("contract", _done(code, stdout))


@pytest.mark.parametrize("project", sorted(PROJECTS))
def test_no_module_is_excused_from_the_type_check(project):
    listed = _ratchet(project)
    assert not listed, (
        f"{project}/pyproject.toml has an ignore_errors override again, naming {listed}. Every module is "
        f"checked: fix the errors (`cd {project} && uv run mypy`) and take the override out."
    )


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
    assert config.get("files") == CHECKED_FILES, f"[tool.mypy] checks {config.get('files')}, not {CHECKED_FILES}"


def _allowance(config: dict) -> list[str]:
    """The modules `ignore_missing_imports` lets be missing, from every override that sets it."""
    return [
        module
        for override in config.get("overrides", [])
        if override.get("ignore_missing_imports")
        for module in ([override["module"]] if isinstance(override["module"], str) else override["module"])
    ]


def check_the_allowance_names_no_module_of_ours(named: list[str]) -> None:
    """Raise unless `named` is non-empty and none of it is this project's own code."""
    assert named, "no override skips a foreign package's imports, so this check reads nothing: drop it with the override"
    ours = [module for module in named if module == "arrt" or module.startswith("arrt.")]
    assert not ours, f"an ignore_missing_imports override names this project's modules {ours}"


def test_only_untyped_foreign_packages_may_skip_their_imports():
    """`ignore_missing_imports` lets a package without types be imported as `Any`; it never names this project's code."""
    check_the_allowance_names_no_module_of_ours(_allowance(_mypy_config()))


@pytest.mark.parametrize("named", [["jsonschema", "arrt.library.facade"], ["arrt"], ["arrt.*"]])
def test_an_allowance_naming_this_projects_code_is_refused(named):
    with pytest.raises(AssertionError, match="names this project's modules"):
        check_the_allowance_names_no_module_of_ours(named)


def test_the_contract_package_ships_its_type_marker_so_the_allowance_does_not_name_it():
    """The package ships `py.typed`; the type check is clean without an allowance for `arrt_contract` (measured on the pool's
    environment and on a fresh sync of the fallback's groups alone, 167 files), so one would only hide a lost marker."""
    marker = ROOT / "contract" / "src" / "arrt_contract" / "py.typed"
    assert marker.is_file(), f"{marker.relative_to(ROOT)} is gone, so `arrt_contract` is untyped to the type check again"
    named = [m for m in _allowance(_mypy_config()) if m == "arrt_contract" or m.startswith("arrt_contract.")]
    assert not named, f"the allowance names {named}: the package is typed, so take it out and fix what mypy then says"


def test_mypy_is_in_the_dev_group_and_the_lockfile():
    dev = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["dependency-groups"]["dev"]
    assert any(re.match(r"mypy\b", d) for d in dev), "mypy is not in arrt's dev group, so `uv run mypy` cannot find it"
    lock = tomllib.loads((ARRT / "uv.lock").read_text(encoding="utf-8"))
    assert any(p["name"] == "mypy" for p in lock["package"]), "arrt/uv.lock pins no mypy"


def _lint_step(workflow: dict | None = None) -> str:
    workflow = workflow or yaml.safe_load((ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8"))
    steps = [s for job in workflow["jobs"].values() for s in job.get("steps", [])]
    lint = [s["run"] for s in steps if s.get("name", "").startswith("Lint and format")]
    assert len(lint) == 1, f"expected one lint step in tests.yml, found {len(lint)}"
    return lint[0]


def check_the_lint_step_installs_only_the_linters(run: str) -> None:
    """Raise unless every `uv run` in the lint step installs the dev group alone, and none runs mypy."""
    lines = [line.strip() for line in run.splitlines() if line.strip() and not line.strip().startswith("#")]
    assert any("ruff check" in line for line in lines), "the lint step runs no ruff, so this check reads the wrong step"
    expanded = [line.replace("$lint", "uv run --frozen --only-group dev") for line in lines]
    heavy = [line for line in expanded if line.startswith("uv run") and "--only-group dev" not in line]
    assert not heavy, (
        f"the lint step runs {heavy}, which installs a project's whole runtime on GitHub's runner on every pull "
        "request; lint installs only ruff and black (`--only-group dev`), and the type check runs on the pool"
    )
    typed = [line for line in expanded if re.search(r"\bmypy\b", line)]
    assert not typed, f"the lint step runs {typed}; the type check runs once per change, in the governance suite on the pool"


def test_the_ci_lint_step_installs_only_the_linters_and_runs_no_mypy():
    check_the_lint_step_installs_only_the_linters(_lint_step())


@pytest.mark.parametrize("line", ["uv run --frozen mypy", "$lint mypy", "uv run --frozen ruff check ."])
def test_a_lint_step_that_installs_a_runtime_or_type_checks_is_refused(line):
    run = _lint_step() + f"\ncd ../arrt\n{line}\n"
    with pytest.raises(AssertionError, match="the lint step runs"):
        check_the_lint_step_installs_only_the_linters(run)


@pytest.mark.parametrize("project", sorted(PROJECTS))
def test_claude_md_table_names_the_type_check(project):
    rows = [line for line in (ROOT / "CLAUDE.md").read_text(encoding="utf-8").splitlines() if line.startswith("| Type-check |")]
    assert len(rows) == 1, "CLAUDE.md's dev-command table has no Type-check row"
    assert f"`cd {project} && uv run mypy`" in rows[0], f"CLAUDE.md's Type-check row names no mypy for {project}"
