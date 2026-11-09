"""`.env.example` sets no household setting, so copying it locks none.

A household setting given in the environment is locked: Settings › General and
MCP show it and refuse to change it (`arrt/src/arrt/library/services/settings.py`).
The README's first step is `cp .env.example .env`, so a setting the example gave
would arrive locked on every installation, and its control would never work.
The example may document one, commented out.
"""

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SETTINGS_MODULE = _ROOT / "arrt/src/arrt/library/services/settings.py"
_EXAMPLE = _ROOT / ".env.example"

#: How the settings module names a setting's variable, read rather than copied,
#: so a setting added there is covered here with no edit.
_DECLARED = re.compile(r'environment_variable="([A-Z][A-Z0-9_]*)"')


def _setting_variables() -> set[str]:
    return set(_DECLARED.findall(_SETTINGS_MODULE.read_text(encoding="utf-8")))


def _assigned(text: str) -> set[str]:
    return {line.split("=", 1)[0].strip() for line in text.splitlines() if "=" in line and not line.lstrip().startswith("#")}


def test_the_settings_variables_are_found_where_they_are_declared():
    """Without this, a change to how settings are declared would leave the check below comparing nothing.

    One variable per `Setting(` declared, so a setting declared some other way
    fails here by name rather than slipping past the check below.
    """
    source = _SETTINGS_MODULE.read_text(encoding="utf-8")
    assert "LABEL_UNITS" in _setting_variables()
    assert len(_DECLARED.findall(source)) == len(re.findall(r"\bSetting\(", source))


def test_the_example_env_file_sets_no_household_setting():
    locked = _setting_variables() & _assigned(_EXAMPLE.read_text(encoding="utf-8"))

    assert not locked, (
        f".env.example sets {sorted(locked)}, which would lock it on every installation copied from it. "
        "Comment it out and say it is chosen in Settings › General."
    )


def test_a_setting_the_example_assigns_is_caught():
    """The check's own falsifier: an uncommented assignment is found, a commented one is not."""
    assert _assigned("LABEL_UNITS=imperial\n# OTHER=1\n") == {"LABEL_UNITS"}
