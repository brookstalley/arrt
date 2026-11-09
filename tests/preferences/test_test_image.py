"""The test image's Playwright is the one the curation plane's lockfile pins.

`.devcontainer/Dockerfile` installs Chromium with a pinned Playwright, so the
browser suite on testament's runners has its browser before any tree arrives.
The suite then runs the Playwright `arrt/uv.lock` installs. Each Playwright
release drives one Chromium build, and a mismatch makes every browser test fail
to launch on the runners while passing on a machine that installed its own.
"""

import pathlib
import re
import tomllib

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_DOCKERFILE = _ROOT / ".devcontainer" / "Dockerfile"
_LOCK = _ROOT / "arrt" / "uv.lock"


def _image_playwright() -> str | None:
    found = re.search(r"^ARG PLAYWRIGHT_VERSION=(\S+)$", _DOCKERFILE.read_text(encoding="utf-8"), re.MULTILINE)
    return found.group(1) if found else None


def _locked_playwright() -> str | None:
    packages = tomllib.loads(_LOCK.read_text(encoding="utf-8")).get("package", [])
    return next((package["version"] for package in packages if package.get("name") == "playwright"), None)


def test_both_versions_are_found_where_they_are_declared():
    """Without this, a reworded ARG or a dropped browser group would leave the check below comparing two Nones."""
    assert _image_playwright(), "no `ARG PLAYWRIGHT_VERSION=` line in .devcontainer/Dockerfile"
    assert _locked_playwright(), "no playwright package in arrt/uv.lock"


def test_the_image_installs_the_playwright_the_lockfile_pins():
    assert _image_playwright() == _locked_playwright(), (
        f".devcontainer/Dockerfile installs Playwright {_image_playwright()}, and arrt/uv.lock pins "
        f"{_locked_playwright()}. Set the Dockerfile's ARG PLAYWRIGHT_VERSION to the locked one."
    )
