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
    monkeypatch.setattr(sys, "path", [str(tmp_path / "site"), *sys.path])
    for name in [name for name in sys.modules if name == "arrt_contract"]:
        monkeypatch.delitem(sys.modules, name)

    import arrt_contract as bare  # noqa: PLC0415 -- imported from the copy, after the path is changed

    assert Path(bare.__file__).is_relative_to(tmp_path)
    with pytest.raises(bare.ContractNotFoundError):
        bare.root()


def test_the_specification_is_the_player_contract():
    assert arrt_contract.specification().read_text(encoding="utf-8").startswith("---\nartifact: player-contract\n")


def test_every_route_is_a_method_and_a_path():
    assert arrt_contract.routes()
    for route in arrt_contract.routes().values():
        assert route["method"] in {"GET", "POST"}
        assert route["path"].startswith("/")


@pytest.mark.skipif(shutil.which("uv") is None, reason="building the wheel needs uv")
def test_the_wheel_carries_the_data_inside_the_package(tmp_path):
    """What a Player installs from a tag is a wheel, and a wheel without its data is the broken build `root()` refuses.

    Built the way a package index or installer may build it: an sdist first,
    then the wheel from the sdist. A file reached from outside this directory
    survives a direct wheel build and is lost on this path.
    """
    subprocess.run(["uv", "build", "--out-dir", str(tmp_path), str(CHECKOUT)], check=True, capture_output=True)
    wheel = next(tmp_path.glob("arrt_contract-*.whl"))
    names = set(zipfile.ZipFile(wheel).namelist())

    on_disk = {
        f"arrt_contract/{path.relative_to(CHECKOUT)}"
        for kind in ("schemas", "fixtures", "vectors")
        for path in (CHECKOUT / kind).rglob("*.json")
    } | {"arrt_contract/routes.json", "arrt_contract/player-contract.md"}
    assert on_disk <= names, sorted(on_disk - names)
