"""The compose example keeps the hardening that was measured, and nothing it was not measured with.

`deploy/nas/compose.example.yaml` is what a household copies to deploy, and this
repository is public, so the example is the only place the container's shape is
written down. `test_deployment_values.py` keeps a real address out of it; it
cannot hold what the file *says*, and a line dropped from a YAML file leaves a
parseable, working compose file that is quietly less safe. This holds the shape.

**What was measured** (2026-11-19, `deploy/README.md` § Hardening the container):
the `app` image started as user 568 with every capability dropped and a read-only
root filesystem, served `/healthz`, took its start-up backup, wrote a feed when a
theme was hung, and stopped on SIGTERM with exit 0. Its writes were `/art` (the
catalogue and its journal, the kept-answers store, the backup status, each feed),
`/backups` (a generation), and nothing in the root filesystem. SQLite's spill of a
large sort needs a temporary directory (`/tmp`): about twenty thousand rows of a
sort fail read-only without one. `_MEASURED_WRITABLE` is that list. A path added
to it is a path somebody measured; a path in the example and not in it is a
claim nobody did.

The checks are written as `_problems(service)` over a parsed service, so each can
be shown to fail on a copy with its line removed
(`test_each_check_fails_on_the_input_it_exists_for`): a check that only ever sees
the real file passes when it checks nothing.
"""

import copy
import pathlib

import pytest
import yaml

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_EXAMPLE = _ROOT / "deploy/nas/compose.example.yaml"
_README = _ROOT / "deploy/README.md"

#: The places the server writes, as measured. Each is mounted writable, and no
#: other path is. The first two are the server's own settings (`ART_ROOT`,
#: `BACKUP_DIR`) and are checked against the environment below.
_MEASURED_WRITABLE = frozenset({"/art", "/backups", "/tmp"})


def _service(document: dict) -> dict:
    return document["services"]["arrt"]


def _load() -> dict:
    return yaml.safe_load(_EXAMPLE.read_text(encoding="utf-8"))


def _volume_mounts(service: dict) -> dict[str, bool]:
    """Each volume's container path, and whether it is writable.

    The short form is `<source>:<target>[:<options>]`, and the sources in the
    example are placeholders in angle brackets, which carry no colon.
    """
    mounts = {}
    for entry in service.get("volumes", []):
        if isinstance(entry, dict):
            mounts[entry["target"]] = not entry.get("read_only", False)
            continue
        parts = entry.split(":")
        options = parts[2].split(",") if len(parts) > 2 else []
        mounts[parts[1]] = "ro" not in options
    return mounts


def _tmpfs(service: dict) -> dict[str, list[str]]:
    """Each tmpfs path with its options (`/tmp:size=64m,mode=1777` is `/tmp` with two)."""
    mounted = {}
    for entry in service.get("tmpfs", []):
        path, _, options = entry.partition(":")
        mounted[path] = [option for option in options.split(",") if option]
    return mounted


def _writable(service: dict) -> set[str]:
    """What a container with a read-only root can write: its writable volumes and its tmpfs."""
    paths = {path for path, writable in _volume_mounts(service).items() if writable}
    return paths | set(_tmpfs(service))


def _problems(service: dict) -> list[str]:
    problems = []
    if [str(name).upper() for name in service.get("cap_drop", [])] != ["ALL"]:
        problems.append("cap_drop must be exactly [ALL]")
    if service.get("cap_add"):
        problems.append("cap_add must be absent")
    if service.get("read_only") is not True:
        problems.append("read_only must be true")
    if "no-new-privileges:true" not in service.get("security_opt", []):
        problems.append("security_opt must carry no-new-privileges:true")
    if not service.get("mem_limit"):
        problems.append("mem_limit must bound the container")
    if str(service.get("user", "")).split(":")[0] in {"", "0", "root"}:
        problems.append("user must name an unprivileged user, never root")
    writable = _writable(service)
    for path in sorted(_MEASURED_WRITABLE - writable):
        problems.append(f"{path} is written by the server and is not mounted writable")
    for path in sorted(writable - _MEASURED_WRITABLE):
        problems.append(f"{path} is mounted writable and was never measured as written")
    environment = service.get("environment", {})
    for variable in ("ART_ROOT", "BACKUP_DIR"):
        if environment.get(variable) not in writable:
            problems.append(f"{variable} names {environment.get(variable)!r}, which is not a writable mount")
    options = _tmpfs(service).get("/tmp", [])
    if "mode=1777" not in options:
        problems.append("/tmp needs mode=1777, or the unprivileged user cannot write it")
    if not any(option.startswith("size=") for option in options):
        problems.append("/tmp needs a size=, because a tmpfs counts against mem_limit")
    return problems


def test_the_example_keeps_the_hardening_that_was_measured():
    assert _problems(_service(_load())) == []


def test_the_example_names_its_service_and_parses_to_one_service():
    """Without this, a rename of the service reads as a KeyError rather than as the example moving."""
    assert list(_load()["services"]) == ["arrt"]


def test_the_retired_units_memory_comment_is_gone():
    """`MemoryMax` was the Pi unit's setting; the example's bound is `mem_limit`, and says so itself."""
    text = _EXAMPLE.read_text(encoding="utf-8")
    assert "MemoryMax" not in text
    assert "mem_limit" in text


def _without(key):
    def mutate(service):
        del service[key]

    return mutate


def _mutations():
    def drop_a_capability_drop(service):
        service["cap_drop"] = ["NET_RAW"]

    def add_a_capability(service):
        service["cap_add"] = ["CHOWN"]

    def writable_root(service):
        service["read_only"] = False

    def unmount_the_art_root(service):
        service["volumes"] = [v for v in service["volumes"] if not v.endswith(":/art")]

    def unmount_the_backups(service):
        service["volumes"] = [v for v in service["volumes"] if not v.endswith(":/backups")]

    def drop_the_tmpfs(service):
        del service["tmpfs"]

    def mount_the_art_root_read_only(service):
        service["volumes"] = [v + ":ro" if v.endswith(":/art") else v for v in service["volumes"]]

    def mount_something_unmeasured(service):
        service["volumes"] = [*service["volumes"], "<elsewhere>:/data"]

    def tmpfs_for_root_only(service):
        service["tmpfs"] = ["/tmp:size=64m"]

    def unbounded_tmpfs(service):
        service["tmpfs"] = ["/tmp:mode=1777"]

    def point_the_art_root_elsewhere(service):
        service["environment"]["ART_ROOT"] = "/srv/elsewhere"

    def run_as_root(service):
        service["user"] = "0:0"

    return [
        pytest.param(drop_a_capability_drop, "cap_drop must be exactly [ALL]", id="cap_drop-not-ALL"),
        pytest.param(_without("cap_drop"), "cap_drop must be exactly [ALL]", id="cap_drop-removed"),
        pytest.param(add_a_capability, "cap_add must be absent", id="cap_add"),
        pytest.param(writable_root, "read_only must be true", id="read_only-false"),
        pytest.param(_without("read_only"), "read_only must be true", id="read_only-removed"),
        pytest.param(unmount_the_art_root, "/art is written by the server", id="art-root-unmounted"),
        pytest.param(unmount_the_backups, "/backups is written by the server", id="backups-unmounted"),
        pytest.param(drop_the_tmpfs, "/tmp is written by the server", id="tmp-unmounted"),
        pytest.param(mount_the_art_root_read_only, "/art is written by the server", id="art-root-read-only"),
        pytest.param(mount_something_unmeasured, "/data is mounted writable", id="unmeasured-mount"),
        pytest.param(tmpfs_for_root_only, "/tmp needs mode=1777", id="tmp-mode"),
        pytest.param(unbounded_tmpfs, "/tmp needs a size=", id="tmp-size"),
        pytest.param(point_the_art_root_elsewhere, "ART_ROOT names '/srv/elsewhere'", id="art-root-elsewhere"),
        pytest.param(run_as_root, "user must name an unprivileged user", id="root-user"),
        pytest.param(_without("mem_limit"), "mem_limit must bound", id="mem_limit-removed"),
        pytest.param(_without("security_opt"), "no-new-privileges", id="no-new-privileges-removed"),
    ]


@pytest.mark.parametrize(("mutate", "expected"), _mutations())
def test_each_check_fails_on_the_input_it_exists_for(mutate, expected):
    """The real example is clean (above); each copy with one line changed is refused, by name."""
    service = copy.deepcopy(_service(_load()))
    assert _problems(service) == []
    mutate(service)
    problems = _problems(service)
    assert any(expected in problem for problem in problems), problems


def test_the_readme_names_every_path_the_example_mounts_writable():
    """`deploy/README.md` says what was measured; its § Hardening the container quotes the same paths."""
    text = _README.read_text(encoding="utf-8")
    start = text.index("### Hardening the container")
    end = min(i for i in (text.find("\n## ", start), text.find("\n### ", start + 1)) if i != -1)
    section = text[start:end]
    for path in sorted(_MEASURED_WRITABLE):
        assert f"`{path}`" in section, f"the README's hardening section does not name {path}"
    for word in ("cap_drop", "read_only"):
        assert word in section
