"""The package finds its data, or says it cannot.

A consumer reads the contract through `root()`, and most of what it reads is
parametrised over the files found there. A `root()` that resolved to an empty
directory would give every one of those tests zero cases, and a run of zero
cases reads as a pass. So a layout without the data is refused by name.
"""

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import arrt_contract

CHECKOUT = Path(__file__).resolve().parents[1]


def test_root_holds_the_four_kinds_of_file_the_specification_names():
    root = arrt_contract.root()

    assert (root / "schemas").is_dir()
    assert (root / "fixtures" / "index.json").is_file()
    assert (root / "vectors").is_dir()
    assert (root / "routes.json").is_file()


def test_a_package_without_its_data_refuses_by_name(tmp_path, monkeypatch):
    package = tmp_path / "site" / "arrt_contract"
    shutil.copytree(CHECKOUT / "src" / "arrt_contract", package, ignore=shutil.ignore_patterns("__pycache__"))
    bare = _import_from(tmp_path / "site", monkeypatch)

    with pytest.raises(bare.ContractNotFoundError):
        bare.root()


def test_the_specification_is_the_player_contract():
    assert arrt_contract.specification().read_text(encoding="utf-8").startswith("---\nartifact: player-contract\n")


def test_every_route_is_a_method_and_a_path():
    assert arrt_contract.routes()
    for route in arrt_contract.routes().values():
        assert route["method"] in {"GET", "POST"}
        assert route["path"].startswith("/")


def _import_from(site: Path, monkeypatch: pytest.MonkeyPatch):
    """`arrt_contract` imported from `site`, ahead of this checkout's editable install."""
    monkeypatch.setattr(sys, "path", [str(site), *sys.path])
    for name in [name for name in sys.modules if name == "arrt_contract"]:
        monkeypatch.delitem(sys.modules, name)
    import arrt_contract as installed  # noqa: PLC0415 -- imported from `site`, after the path is changed

    assert Path(installed.__file__).is_relative_to(site)
    return installed


@pytest.fixture(scope="module")
def wheel(tmp_path_factory) -> Path:
    """The wheel built the way a package index or installer may build it: an sdist first, then the wheel from the sdist.

    A file reached from outside this directory survives a direct wheel build and
    is lost on this path.
    """
    if shutil.which("uv") is None:
        pytest.skip("building the wheel needs uv")
    out = tmp_path_factory.mktemp("dist")
    subprocess.run(["uv", "build", "--out-dir", str(out), str(CHECKOUT)], check=True, capture_output=True)
    return next(out.glob("arrt_contract-*.whl"))


def test_the_wheel_carries_the_data_inside_the_package(wheel):
    """What a Player installs from a tag is a wheel, and a wheel without its data is the broken build `root()` refuses."""
    names = set(zipfile.ZipFile(wheel).namelist())
    on_disk = {
        f"arrt_contract/{path.relative_to(CHECKOUT)}"
        for kind in ("schemas", "fixtures", "vectors")
        for path in (CHECKOUT / kind).rglob("*.json")
    } | {"arrt_contract/routes.json", "arrt_contract/timing.json", "arrt_contract/player-contract.md"}
    assert on_disk <= names, sorted(on_disk - names)


def test_an_installed_wheel_reads_its_own_data(wheel, tmp_path, monkeypatch):
    """The other suites run on the editable install, finding the data in this checkout; a Player finds it in the package."""
    site = tmp_path / "site"
    zipfile.ZipFile(wheel).extractall(site)
    installed = _import_from(site, monkeypatch)
    package = site / "arrt_contract"

    assert installed.root() == package
    assert installed.specification() == package / "player-contract.md"
    assert installed.specification().read_text(encoding="utf-8").startswith("---\nartifact: player-contract\n")
    assert len(installed.fixtures()) == len(arrt_contract.fixtures())
    assert installed.routes() == arrt_contract.routes()
    assert installed.validator("schemas/label.v1.schema.json").schema["$id"].endswith("label.v1.schema.json")


def test_an_installed_wheel_without_the_specification_refuses_by_name(wheel, tmp_path, monkeypatch):
    site = tmp_path / "site"
    zipfile.ZipFile(wheel).extractall(site)
    (site / "arrt_contract" / "player-contract.md").unlink()
    installed = _import_from(site, monkeypatch)

    with pytest.raises(installed.ContractNotFoundError):
        installed.specification()


HEARTBEATS = ("schemas/heartbeat.v1.schema.json", "schemas/client-heartbeat.v1.schema.json")


def test_both_heartbeats_report_their_instant_under_one_key():
    """A Player writes both bodies' instant from one constant, so the two schemas must name the same key."""
    assert {arrt_contract.instant_key(name) for name in HEARTBEATS} == {"reported_at"}


def test_a_schema_with_two_candidate_instants_is_refused(monkeypatch):
    two = {
        "required": ["at", "also_at"],
        "properties": {"at": {"format": "date-time"}, "also_at": {"format": "date-time"}},
    }
    monkeypatch.setattr(arrt_contract, "schema", lambda _relative: two)

    with pytest.raises(ValueError, match="2 required date-time"):
        arrt_contract.instant_key("schemas/anything.json")


def test_the_timing_is_what_the_specification_says():
    """The numbers and the prose that states them, held together so neither moves alone."""
    text = arrt_contract.specification().read_text(encoding="utf-8")
    timing = arrt_contract.timing()

    assert f"**Written every {timing['heartbeat_interval_seconds']} seconds.**" in text
    assert "older than three heartbeat intervals" in text
    assert timing["stale_after_intervals"] == 3
