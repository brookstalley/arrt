"""The package says it is typed, so a consumer's type checker reads its annotations.

The package's source checks clean under `mypy --strict` (`[tool.mypy]`), and what it hands a
consumer is annotated. Without the `py.typed` marker (PEP 561) a type checker importing the
installed package reports "missing library stubs or py.typed marker" and treats everything
from it as `Any`, so the server's own type check needed an allowance to import it. These
tests hold the marker in the wheel, and hold what it is for: a checker run in an environment
that installed the wheel sees the types.
"""

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

CHECKOUT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def wheel(tmp_path_factory) -> Path:
    """The wheel built the way an installer may build it: an sdist first, then the wheel from the sdist."""
    if shutil.which("uv") is None:
        pytest.skip("building the wheel needs uv")
    out = tmp_path_factory.mktemp("dist")
    subprocess.run(["uv", "build", "--out-dir", str(out), str(CHECKOUT)], check=True, capture_output=True)
    return next(out.glob("arrt_contract-*.whl"))


def test_the_source_ships_the_marker():
    assert (CHECKOUT / "src" / "arrt_contract" / "py.typed").is_file()


def test_the_wheel_carries_the_marker_inside_the_package(wheel):
    assert "arrt_contract/py.typed" in set(zipfile.ZipFile(wheel).namelist())


def test_a_type_checker_in_an_environment_that_installed_the_wheel_reads_the_package_as_typed(wheel, tmp_path):
    """What the marker is for: a consumer's wrong use of `routes()` is an error about its type, not a missing-stubs refusal."""
    environment = tmp_path / "environment"
    subprocess.run(["uv", "venv", "--quiet", "--python", sys.executable, str(environment)], check=True, capture_output=True)
    python = environment / ("Scripts" if sys.platform == "win32" else "bin") / "python"
    subprocess.run(
        ["uv", "pip", "install", "--quiet", "--no-deps", "--python", str(python), str(wheel)], check=True, capture_output=True
    )
    consumer = tmp_path / "consumer.py"
    consumer.write_text("from arrt_contract import routes\n\nwrong: int = routes()\n", encoding="utf-8")
    (tmp_path / "mypy.ini").write_text("[mypy]\n", encoding="utf-8")

    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--config-file",
            str(tmp_path / "mypy.ini"),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--python-executable",
            str(python),
            str(consumer),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert "py.typed" not in done.stdout, done.stdout
    assert 'variable has type "int"' in done.stdout, done.stdout
    assert "dict[str, dict[str, str]]" in done.stdout, done.stdout
