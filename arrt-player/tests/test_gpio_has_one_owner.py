"""Nothing the panel installs puts a second `RPi/GPIO/__init__.py` on the Pi.

`jetson-gpio` ships a one-line `RPi/GPIO/__init__.py` (`from Jetson.GPIO import *`)
at the path `rpi-gpio` installs the real one, and two packages owning one file
leave whichever installed last. On the wall that was the Jetson shim, and the
panel stopped opening with "Could not determine Jetson model" (#181). The
`[tool.uv]` override in `pyproject.toml` removes `jetson-gpio`; this holds the
lockfile to that, since a dependency added later could bring it back.
"""

import tomllib
from pathlib import Path

LOCK = Path(__file__).resolve().parents[1] / "uv.lock"
NEVER = "sys_platform == 'never'"


def _packages() -> list[dict]:
    return tomllib.loads(LOCK.read_text(encoding="utf-8"))["package"]


def test_every_requirement_of_jetson_gpio_is_one_no_platform_installs():
    requirers = [
        (package["name"], dependency.get("marker"))
        for package in _packages()
        for dependency in package.get("dependencies", [])
        if dependency["name"] == "jetson-gpio"
    ]

    assert requirers, "nothing requires jetson-gpio, so this checks nothing; delete the override and this test"
    assert all(marker == NEVER for _, marker in requirers), requirers


def test_rpi_gpio_is_still_what_the_panel_driver_installs():
    """The other half: removing the shim must not remove the real one."""
    names = {package["name"] for package in _packages()}

    assert "rpi-gpio" in names
