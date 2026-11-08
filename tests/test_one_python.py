"""Every project, every CI job and the NAS image run one Python, built by one uv.

**Why this is a guard.** On 2026-11-08 GitHub moved `ubuntu-latest` from 24.04
to 26.04. The new image ships a system Python 3.14.4, and uv preferred it over
downloading its own build, so CI ran Ubuntu's SQLite where it had run uv's. One
curation test that drops a column from a real catalogue failed there and nowhere
else. Nothing in the repository had changed. The cure has three parts, and each
part is a copy that can drift on its own:

- **One version, exact to the patch.** The root `.python-version` is the pin. A
  project may carry its own copy only where something cannot see the root (the
  NAS image is built from `arrt/` alone), and that copy must say the same.
- **Only a Python uv installed.** Every `pyproject.toml` sets
  `python-preference = "only-managed"`, so no machine's own Python, and no
  machine's own SQLite, is ever picked up.
- **One uv.** The uv that resolves the pin is the uv the Dockerfile pins by
  image tag. Every `setup-uv` step in CI, in a workflow or a composite action,
  names that version. Each uv release knows its own list of Python builds, so
  another uv may resolve the same patch to another build, with another SQLite;
  an unpinned one moves with the action.
"""

import pathlib
import re
import tomllib

import yaml
from repository import ROOT, projects

PIN = ROOT / ".python-version"
DOCKERFILE = ROOT / "arrt" / "Dockerfile"
GITHUB = ROOT / ".github"


def _ci_files() -> list[pathlib.Path]:
    """Every workflow and composite action, either extension: a step that pins nothing hides in the one not read."""
    found = [*GITHUB.glob("workflows/*.yml"), *GITHUB.glob("workflows/*.yaml"), *GITHUB.glob("actions/**/action.y*ml")]
    return sorted(found)


def _steps(document: dict) -> list[dict]:
    if "jobs" in document:
        return [step for job in document["jobs"].values() for step in job.get("steps", [])]
    return document.get("runs", {}).get("steps", [])


def _pin() -> str:
    return PIN.read_text(encoding="utf-8").strip()


def _dockerfile_uv() -> str:
    found = re.findall(r"^FROM ghcr\.io/astral-sh/uv:([^@\s]+)", DOCKERFILE.read_text(encoding="utf-8"), re.M)
    assert len(found) == 1, f"expected one uv image in {DOCKERFILE.name}, found {found}"
    return found[0]


def test_the_pin_names_one_exact_release():
    """`3.14` lets each machine take a different 3.14, which is the drift this file exists to stop."""
    assert re.fullmatch(r"\d+\.\d+\.\d+", _pin()), f".python-version is {_pin()!r}, not an exact X.Y.Z"


def test_every_projects_own_pin_says_what_the_root_says():
    """A project without a copy inherits the root's; one with a copy must not disagree with it."""
    for project in projects():
        own = ROOT / project / ".python-version"
        if own.exists():
            assert own.read_text(encoding="utf-8").strip() == _pin(), f"{project}/.python-version disagrees with the root"


def test_every_pyproject_takes_only_a_python_uv_installed():
    for directory in [".", *projects()]:
        path = ROOT / directory / "pyproject.toml"
        settings = tomllib.loads(path.read_text(encoding="utf-8")).get("tool", {}).get("uv", {})
        assert settings.get("python-preference") == "only-managed", f"{path.relative_to(ROOT)} lets uv take a system Python"


def test_the_image_installs_the_pinned_python_and_names_no_version_of_its_own():
    """The image copies the pin in and installs from it. A version written on the line would be a second pin."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    installs = re.findall(r"^RUN uv python install(.*)$", text, re.M)
    assert installs == [""], f"the image should run a bare `uv python install`, found {installs}"
    before_the_install = text.split("RUN uv python install")[0]
    assert "COPY .python-version" in before_the_install, "the pin is not in the image when Python is installed"
    assert (ROOT / "arrt" / ".python-version").exists(), "the image is built from arrt/, which then holds no pin"


def test_every_ci_job_runs_the_uv_the_image_runs():
    steps = [
        (path.relative_to(ROOT), step)
        for path in _ci_files()
        for step in _steps(yaml.safe_load(path.read_text(encoding="utf-8")))
        if str(step.get("uses", "")).startswith("astral-sh/setup-uv")
    ]
    assert steps, "no setup-uv step was found, so nothing here was checked"
    for name, step in steps:
        pinned = (step.get("with") or {}).get("version")
        assert pinned == _dockerfile_uv(), f"a setup-uv step in {name} pins uv {pinned}, not the image's {_dockerfile_uv()}"
