"""The synthetic walk's server is a throwaway: it inherits nothing from the operator (`tools/ux_walk.py`).

The "throwaway" server was once started with
the whole of the operator's environment and, through `load_dotenv()`, their `.env`:
the paid OpenRouter key, the museums' user agents, and the real month's balance
shown in the sidebar of every capture. **Each case plants a sentinel where a key
lives and asks what the server's environment holds**, so a name the walk leaves
inherited fails by its sentinel, not by a list of names kept here.

The harness itself is never run: `boot_synthetic` seeds a catalogue and starts a
server, and this holds what it hands that server.
"""

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import ux_walk  # tools/ is not a package; the path is inserted above

SENTINEL = "sk-or-SENTINEL-must-not-reach-the-synthetic-server"

#: What the walk itself sets, so a declared name it sets is not asked to be blank.
SET_BY_THE_WALK = {"ART_ROOT", "CURATION_HOST", "CURATION_PORT"}

#: Names no setting of Arrt's declares, which an operator's shell or `.env` may
#: still hold: other paid services' keys and the credentials of whatever else
#: runs on the machine. None may reach the server.
STRANGERS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY", "TV_TOKEN", "TESTAMENT_KEY")


#: Read as the harness reads it, so a missing or foreign file is refused by name at
#: collection rather than parametrising every case below over nothing.
DECLARED = sorted(ux_walk.names_to_blank())


def _the_server_is_given(parent: dict[str, str]) -> dict[str, str]:
    return ux_walk.synthetic_environment(parent, art_root=Path("/scratch/art"), port=4321, declared=DECLARED)


def test_the_example_declares_the_names_this_reads():
    """Vacuity: a parametrisation over an empty file passes every case below, so the file and its paid key must be found."""
    assert "OPENROUTER_API_KEY" in DECLARED, f"{ux_walk.ENV_EXAMPLE} was not read, or no longer declares the key"
    assert "BACKUP_DIR" in DECLARED, "a commented-out optional setting must count as declared"
    assert set(DECLARED) >= SET_BY_THE_WALK


@pytest.mark.parametrize("name", DECLARED)
def test_every_name_the_example_declares_is_set_by_the_walk_or_blank(name):
    """Parametrised over `.env.example`, so a setting added tomorrow is covered by the file that declares it."""
    environment = _the_server_is_given(dict.fromkeys(DECLARED, SENTINEL))

    assert name in environment, f"{name} is declared but absent, so `.env` would fill it"
    if name in SET_BY_THE_WALK:
        assert SENTINEL not in environment[name]
    else:
        assert environment[name] == ""


def test_the_paid_key_in_the_parent_is_empty_in_the_server():
    environment = _the_server_is_given({"OPENROUTER_API_KEY": SENTINEL, "PATH": "/usr/bin"})

    assert environment["OPENROUTER_API_KEY"] == ""
    assert SENTINEL not in json.dumps(environment)


@pytest.mark.parametrize("name", STRANGERS)
def test_a_credential_arrt_does_not_declare_is_not_inherited(name):
    environment = _the_server_is_given({name: SENTINEL, "PATH": "/usr/bin"})

    assert name not in environment


def test_what_a_python_process_needs_is_inherited():
    environment = _the_server_is_given({"PATH": "/usr/bin", "HOME": "/home/walker", "LANG": "C.UTF-8", "FOO": "bar"})

    assert environment["PATH"] == "/usr/bin"
    assert environment["HOME"] == "/home/walker"
    assert environment["LANG"] == "C.UTF-8"
    assert "FOO" not in environment


def test_the_walks_own_settings_win_over_the_parents():
    environment = _the_server_is_given(
        {"ART_ROOT": "/the/real/library", "CURATION_PORT": "8770", "CURATION_HOST": "192.0.2.1"}  # a documentation address
    )

    assert environment["ART_ROOT"] == "/scratch/art"
    assert environment["CURATION_PORT"] == "4321"
    assert environment["CURATION_HOST"] == "127.0.0.1"


# -- The list of names itself: refused by name, never read as "nothing to blank" ---


def test_a_missing_example_is_refused_by_name(tmp_path):
    absent = tmp_path / ".env.example"

    with pytest.raises(RuntimeError, match="could not be read") as refused:
        ux_walk.names_to_blank(absent)

    assert str(absent) in str(refused.value)


@pytest.mark.parametrize("text", ["", "# nothing here\n", "ART_ROOT=\nCURATION_HOST=\nCURATION_PORT=\n"])
def test_an_example_without_the_paid_key_is_refused_by_name(tmp_path, text):
    example = tmp_path / ".env.example"
    example.write_text(text, encoding="utf-8")

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        ux_walk.names_to_blank(example)


def test_the_boot_refuses_before_it_seeds_anything_when_the_example_is_missing(tmp_path, monkeypatch):
    """Through the caller: without the list the server is never started and no scratch library is made."""
    monkeypatch.setattr(ux_walk, "ENV_EXAMPLE", tmp_path / "absent" / ".env.example")
    made = []
    monkeypatch.setattr(ux_walk.tempfile, "mkdtemp", lambda *a, **k: made.append(a) or str(tmp_path / "made"))
    monkeypatch.setattr(ux_walk.subprocess, "Popen", lambda *a, **k: pytest.fail("the server was started"))

    with pytest.raises(RuntimeError, match="absent"):
        ux_walk.boot_synthetic(1)

    assert made == []


def test_the_declared_names_are_read_from_commented_lines_too():
    text = "ART_ROOT=\n# A comment about it.\n#BACKUP_DIR=\n# LABEL_UNITS=imperial\nlowercase=no\n"

    assert ux_walk.declared_names(text) == {"ART_ROOT", "BACKUP_DIR", "LABEL_UNITS"}


# -- .env: the file `load_dotenv()` finds, whatever the environment says ---------


def _probe_module(env_file: Path) -> str:
    """A stand-in for the server's entry point: loads a `.env` the way its configuration does, then reports what it holds."""
    return textwrap.dedent(f"""
        import json, os
        from dotenv import load_dotenv

        load_dotenv({str(env_file)!r})
        print(json.dumps({{name: value for name, value in os.environ.items() if {SENTINEL!r} in value}}))
        """)


def _run_probe(command: list[str], *, cwd: Path, environment: dict[str, str]) -> dict[str, str]:
    result = subprocess.run(  # noqa: S603 -- this interpreter, a launcher and a module the test wrote
        command, cwd=cwd, env=environment, capture_output=True, text=True, timeout=60, check=False
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.fixture
def dotenv_holding_a_key(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """A `.env` that names a declared key and one nobody declares, and the environment the walk gives its server."""
    env_file = tmp_path / ".env"
    env_file.write_text(f"OPENROUTER_API_KEY={SENTINEL}\nSOME_OTHER_PAID_KEY={SENTINEL}\n", encoding="utf-8")
    (tmp_path / "probe_env.py").write_text(_probe_module(env_file), encoding="utf-8")
    environment = ux_walk.synthetic_environment(
        {"PATH": "/usr/bin:/bin", "OPENROUTER_API_KEY": SENTINEL}, art_root=tmp_path / "art", port=4321, declared=DECLARED
    )
    return tmp_path, environment


def test_the_control_a_plain_start_reads_the_dotenv_for_a_name_nobody_blanked(dotenv_holding_a_key):
    """Without the launcher the probe sees the key the allowlist could not know to blank: the case the launcher exists for."""
    tmp_path, environment = dotenv_holding_a_key

    seen = _run_probe([sys.executable, "-m", "probe_env"], cwd=tmp_path, environment=environment)

    assert seen == {
        "SOME_OTHER_PAID_KEY": SENTINEL
    }, "the probe must see the undeclared key, or this proves nothing about the launcher"


def test_the_launched_server_reads_no_dotenv_at_all(dotenv_holding_a_key):
    tmp_path, environment = dotenv_holding_a_key

    seen = _run_probe(ux_walk.synthetic_command("probe_env"), cwd=tmp_path, environment=environment)

    assert seen == {}


def test_the_launcher_runs_the_module_as_main_with_no_arguments(tmp_path):
    (tmp_path / "echo_main.py").write_text(
        "import json, sys\nif __name__ == '__main__':\n    print(json.dumps(sys.argv[1:]))\n", encoding="utf-8"
    )

    shown = _run_probe(ux_walk.synthetic_command("echo_main"), cwd=tmp_path, environment={"PATH": "/usr/bin:/bin"})

    assert shown == []
