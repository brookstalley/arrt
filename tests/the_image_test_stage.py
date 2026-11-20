"""The server image's test stage, built on a runner's host: the whole of the `image` suite.

`arrt/Dockerfile`'s `test` stage runs the server's suite inside the image the NAS runs,
as the app's unprivileged user, over the files the stage copies in. This builds that
stage the way `.github/workflows/image.yml` does (target `test-report`, context `arrt/`,
the repository root as the `repo` context, `linux/amd64`), then reads the report it
exports with `.github/scripts/assert_tests_ran.py`, as that workflow does, so a red
suite, a skip and a suite that ran nothing all fail here.

**Not a `test_*.py`, on purpose.** The governance suite collects `tests/` and runs in
the pool's container and on GitHub's runner, neither of which has a Docker daemon.
pytest collects a file outside its `python_files` pattern only when it is named, and
only the image suite names this one (`.testament.toml`); `tests/test_ci_fallback.py`
holds that the governance suite never collects it.

**What it leaves on a runner's host** (a runner is someone's machine):

- a buildx builder of its own, `arrt-image-stage` (driver `docker-container`): one
  BuildKit container, `buildx_buildkit_arrt-image-stage0`, and its state volume, which
  holds this suite's build cache and nothing else's. The container is stopped after
  every build, so nothing of this suite runs between builds; the volume stays, so the
  next build is warm. The first build on a host pulls BuildKit's image
  (`moby/buildkit:buildx-stable-1`), which other builders share and this never removes.
- no image and no container of its own: the stage is exported as a file
  (`--output type=local`), never loaded or tagged.
- the build's whole log, in one file that each build overwrites (`LOG`).

What accumulates is the builder's cache, and after every build it is pruned to
`CACHE_CEILING` with `docker buildx prune --builder arrt-image-stage`, which reaches
that builder's cache alone, never the host's own or another builder's. To take all of
it away: `docker buildx rm arrt-image-stage`.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import tempfile
import time

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]

#: The builder this suite builds with, created on first use; its cache is this suite's alone.
BUILDER = "arrt-image-stage"
#: What the builder's cache is pruned to after each build. Measured 2026-11-20 on a runner
#: with Docker, after one cold build and three with the code changed: 3.37 GB, 2.0 GB of
#: it the test stage's environment, which only a lockfile change rebuilds. Room for two
#: generations of it: a warm build stays warm across one lockfile change, and a host's
#: disk gives no more than this to the suite however many builds it runs.
CACHE_CEILING = "8gb"
#: The build's whole log, overwritten by each build. The failure text carries its tail.
LOG = pathlib.Path(tempfile.gettempdir()) / "arrt-image-stage" / "last-build.log"
#: How many of the log's last lines the failure text carries.
TAIL = 80
#: A cold build took 4 to 6 minutes on a runner with Docker (2026-11-20); this is a hang.
BUILD_TIMEOUT_S = 1800


def build_command(out: pathlib.Path) -> list[str]:
    """`image.yml`'s build of the test stage, as a command on this host, exporting the report to `out`."""
    return [
        "docker",
        "buildx",
        "build",
        "--builder",
        BUILDER,
        "--platform",
        "linux/amd64",
        "--target",
        "test-report",
        "--build-context",
        f"repo={REPO}",
        "--file",
        str(REPO / "arrt" / "Dockerfile"),
        "--output",
        f"type=local,dest={out}",
        "--progress",
        "plain",
        str(REPO / "arrt"),
    ]


#: A line of pytest's progress inside the build (`#38 87.77 ......... [ 72%]`): thousands of
#: tests make dozens of them, which say nothing a failure needs and push it out of the tail.
_PROGRESS = re.compile(r"^(#\d+ [\d.]+ )?[.sxXFE]+ *\[ *\d+%\]$")


def tail(text: str, lines: int = TAIL) -> str:
    """The last `lines` lines of `text`, pytest's progress lines left out (they stay in the log)."""
    kept = [line for line in text.rstrip("\n").splitlines() if not _PROGRESS.match(line.strip())]
    return "\n".join(kept[-lines:])


def _docker(*args: str, timeout: float = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


def _ensure_builder() -> None:
    """Create the suite's builder if this host has none; a second run racing the first finds it made."""
    if _docker("buildx", "inspect", BUILDER).returncode == 0:
        return
    made = _docker("buildx", "create", "--name", BUILDER, "--driver", "docker-container")
    if made.returncode != 0 and _docker("buildx", "inspect", BUILDER).returncode != 0:
        pytest.fail(f"could not create the buildx builder {BUILDER}: {made.stderr.strip()}", pytrace=False)


def _tidy() -> str:
    """Prune the builder's cache to its ceiling and stop its container; what each said, for the record."""
    said = []
    for args in (
        ("buildx", "prune", "--builder", BUILDER, "--force", "--max-used-space", CACHE_CEILING),
        ("buildx", "stop", BUILDER),
    ):
        done = _docker(*args)
        said.append(f"docker {' '.join(args)}: exit {done.returncode} {done.stdout.strip()[-200:]} {done.stderr.strip()[-200:]}")
    return "\n".join(said)


def test_the_image_test_stage_builds_and_its_suite_ran(tmp_path):
    _ensure_builder()
    out = tmp_path / "report"
    command = build_command(out)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    began = time.monotonic()
    try:
        with LOG.open("w", encoding="utf-8") as log:
            log.write(f"$ {' '.join(command)}\n")
            log.flush()
            built = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=BUILD_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        built = None
    finally:
        tidied = _tidy()
    took = time.monotonic() - began
    text = LOG.read_text(encoding="utf-8", errors="replace")
    where = f"the whole log ({len(text.splitlines())} lines) is {LOG} on the runner that ran this test, until its next build"
    if built is None:
        pytest.fail(
            f"the image's test stage did not finish in {BUILD_TIMEOUT_S} s; {where}. Its last lines:\n{tail(text)}\n{tidied}",
            pytrace=False,
        )
    if built.returncode != 0:
        pytest.fail(
            f"the image's test stage failed to build (exit {built.returncode}, {took:.0f} s); {where}. "
            f"Its last {TAIL} lines, pytest's progress left out:\n{tail(text)}\n{tidied}",
            pytrace=False,
        )
    report = out / "results.xml"
    guard = subprocess.run(
        [sys.executable, str(REPO / ".github" / "scripts" / "assert_tests_ran.py"), str(report)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert (
        guard.returncode == 0
    ), f"the image's test stage built, and its report does not show its suite ran: {guard.stdout}{guard.stderr}\n{tidied}"
