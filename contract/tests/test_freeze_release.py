"""The writer of a frozen release copy is in the repository, and it reproduces the copies that are.

`contract/released/<version>/` is copied from the release's tag once, when it is cut
(`player-contract.md` § The package), and `test_released.py` holds HEAD to the copies.
Until `contract/tools/freeze_release.py` the writer of a copy was a script in someone's
scratch directory, so nothing said how a copy was made or that a second writer would
make the same bytes. Two things are held here:

- **The tool, on a repository made for the test**, which runs wherever the suite does:
  what it copies and what it leaves out, that it reads the tag and not the working tree,
  what `sha256.json` records and in what order, and each refusal by name.
- **The tool, on the real tags**: each committed copy is written again from its tag and
  compared byte for byte, `sha256.json` included. That needs the tag. A checkout that has
  not fetched tags, and a runner sent only this tree's files, do not have it; the test
  then **skips by name** (`contract-v1.0.0 is not in this repository`), so a run without
  the comparison says so in its report and never passes as if it had made it.
"""

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

import arrt_contract

CHECKOUT = Path(__file__).resolve().parents[1]
TOOL = CHECKOUT / "tools" / "freeze_release.py"


def _load_tool() -> ModuleType:
    specification = importlib.util.spec_from_file_location("freeze_release", TOOL)
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


freeze_release = _load_tool()

#: A git that reads nothing of the machine's own configuration, and signs nothing.
_GIT_ENVIRONMENT = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
}


def _git(repo: Path, *arguments: str) -> str:
    done = subprocess.run(["git", *arguments], cwd=repo, env=_GIT_ENVIRONMENT, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def _tree(directory: Path) -> dict[str, bytes]:
    return {str(path.relative_to(directory)): path.read_bytes() for path in sorted(directory.rglob("*")) if path.is_file()}


# -- the tool, on a repository made for the test ------------------------------------

INDEX = b'{"fixtures": []}\n'
VALID = b'{"valid": true}\n'
INVALID = b'{"valid": false}\r\n  \xc3\xa9'  # bytes a text round trip would change
ROUTES = b'{"routes": {}}\n'
TRANSPORT = b'{"routes": {"a": 1}}\n'
VOCABULARY = b'{"display_states": {}}\n'


def _contract(repo: Path, *, with_table: bool) -> None:
    """A `contract/` holding what a release has and some files a frozen copy leaves out."""
    for relative, content in {
        "fixtures/index.json": INDEX,
        "fixtures/manifest.v2/valid/a.json": VALID,
        "fixtures/manifest.v2/invalid/b.json": INVALID,
        "routes.json": ROUTES,
        "schemas/manifest.v2.schema.json": b"{}\n",
        "vectors/v.json": b"{}\n",
        "timing.json": b"{}\n",
    }.items():
        (repo / "contract" / relative).parent.mkdir(parents=True, exist_ok=True)
        (repo / "contract" / relative).write_bytes(content)
    (repo / "contract" / "player-contract.md").symlink_to("../elsewhere.md")
    if with_table:
        (repo / "contract" / "transport.json").write_bytes(TRANSPORT)
        (repo / "contract" / "vocabulary.json").write_bytes(VOCABULARY)


def _tagged(path: Path, version: str, *, with_table: bool) -> Path:
    """A repository with one commit holding `contract/` and an annotated tag `contract-v<version>` on it."""
    path.mkdir()
    _git(path, "init", "--quiet")
    _contract(path, with_table=with_table)
    _git(path, "add", "--all")
    _git(path, "commit", "--quiet", "--message", "the release")
    _git(path, "-c", "tag.gpgsign=false", "tag", "--annotate", "--message", f"release {version}", f"contract-v{version}")
    return path


def test_a_release_is_copied_from_its_tag_with_what_a_copy_holds_and_nothing_else(tmp_path):
    repo = _tagged(tmp_path / "repo", "2.0.0", with_table=True)

    directory = freeze_release.freeze(repo, "2.0.0", tmp_path / "released")

    assert directory == tmp_path / "released" / "2.0.0"
    written = _tree(directory)
    assert written.pop("sha256.json")
    assert written == {
        "fixtures/index.json": INDEX,
        "fixtures/manifest.v2/valid/a.json": VALID,
        "fixtures/manifest.v2/invalid/b.json": INVALID,
        "routes.json": ROUTES,
        "transport.json": TRANSPORT,
        "vocabulary.json": VOCABULARY,
    }


def test_a_tag_without_the_table_and_the_words_gives_a_copy_without_them(tmp_path):
    """1.0.0 and 1.1.0 have neither file: the copy does not invent them, and does not fail for their absence."""
    repo = _tagged(tmp_path / "repo", "1.5.0", with_table=False)

    directory = freeze_release.freeze(repo, "1.5.0", tmp_path / "released")

    assert not (directory / "transport.json").exists()
    assert not (directory / "vocabulary.json").exists()
    assert sorted(_tree(directory)) == [
        "fixtures/index.json",
        "fixtures/manifest.v2/invalid/b.json",
        "fixtures/manifest.v2/valid/a.json",
        "routes.json",
        "sha256.json",
    ]


def test_sha256_records_the_tag_its_commit_and_each_file_by_path_in_order(tmp_path):
    repo = _tagged(tmp_path / "repo", "2.0.0", with_table=True)

    directory = freeze_release.freeze(repo, "2.0.0", tmp_path / "released")

    text = (directory / "sha256.json").read_text(encoding="utf-8")
    recorded = json.loads(text)
    assert recorded["version"] == "2.0.0"
    assert recorded["tag"] == "contract-v2.0.0"
    assert recorded["commit"] == _git(repo, "rev-parse", "HEAD")
    assert recorded["files"] == {
        "fixtures/index.json": hashlib.sha256(INDEX).hexdigest(),
        "fixtures/manifest.v2/invalid/b.json": hashlib.sha256(INVALID).hexdigest(),
        "fixtures/manifest.v2/valid/a.json": hashlib.sha256(VALID).hexdigest(),
        "routes.json": hashlib.sha256(ROUTES).hexdigest(),
        "transport.json": hashlib.sha256(TRANSPORT).hexdigest(),
        "vocabulary.json": hashlib.sha256(VOCABULARY).hexdigest(),
    }
    # The order is part of the bytes a copy is held to, so it is the sorted order, not git's or the filesystem's.
    assert list(recorded["files"]) == sorted(recorded["files"])
    assert text.endswith("}\n")
    assert text.startswith('{\n  "_about": ')


def test_the_tag_is_what_is_copied_never_the_working_tree(tmp_path):
    """A release is what a Player installs from the tag, however the checkout has moved since."""
    repo = _tagged(tmp_path / "repo", "2.0.0", with_table=True)
    (repo / "contract" / "routes.json").write_bytes(b'{"routes": {"later": 1}}\n')
    (repo / "contract" / "fixtures" / "manifest.v2" / "valid" / "new.json").write_bytes(b"{}\n")
    (repo / "contract" / "fixtures" / "manifest.v2" / "valid" / "a.json").unlink()
    _git(repo, "add", "--all")
    _git(repo, "commit", "--quiet", "--message", "after the release")

    directory = freeze_release.freeze(repo, "2.0.0", tmp_path / "released")

    assert (directory / "routes.json").read_bytes() == ROUTES
    assert (directory / "fixtures" / "manifest.v2" / "valid" / "a.json").read_bytes() == VALID
    assert not (directory / "fixtures" / "manifest.v2" / "valid" / "new.json").exists()


@pytest.mark.parametrize("version", ["1.2", "v1.2.0", "01.2.0", "1.2.0-rc1", "1.2.0 ", "", "../1.2.0", "1.2.x"])
def test_a_version_that_is_not_three_whole_numbers_is_refused_and_nothing_is_written(tmp_path, version):
    repo = _tagged(tmp_path / "repo", "1.2.0", with_table=True)

    with pytest.raises(freeze_release.FreezeError, match="is not a version"):
        freeze_release.freeze(repo, version, tmp_path / "released")

    assert not (tmp_path / "released").exists()


def test_a_tag_that_is_not_there_is_refused_by_name(tmp_path):
    repo = _tagged(tmp_path / "repo", "1.2.0", with_table=True)

    with pytest.raises(freeze_release.FreezeError, match=r"contract-v9\.9\.9"):
        freeze_release.freeze(repo, "9.9.9", tmp_path / "released")

    assert not (tmp_path / "released").exists()


def test_a_branch_named_like_the_tag_is_not_the_tag(tmp_path):
    """A copy is made from a release, which a branch is not: `refs/tags/` is asked for, not any name that resolves."""
    repo = _tagged(tmp_path / "repo", "1.2.0", with_table=True)
    _git(repo, "branch", "contract-v3.0.0")

    with pytest.raises(freeze_release.FreezeError, match=r"contract-v3\.0\.0"):
        freeze_release.freeze(repo, "3.0.0", tmp_path / "released")


def test_a_directory_that_is_not_a_repository_is_refused_by_name(tmp_path, monkeypatch):
    (tmp_path / "plain").mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))

    with pytest.raises(freeze_release.FreezeError, match=r"contract-v1\.2\.0"):
        freeze_release.freeze(tmp_path / "plain", "1.2.0", tmp_path / "released")


@pytest.mark.parametrize("missing", ["routes.json", "fixtures/index.json"])
def test_a_tag_without_what_every_release_has_is_refused_and_nothing_is_written(tmp_path, missing):
    repo = _tagged(tmp_path / "repo", "1.2.0", with_table=True)
    (repo / "contract" / missing).unlink()
    _git(repo, "add", "--all")
    _git(repo, "commit", "--quiet", "--message", "without it")
    _git(repo, "-c", "tag.gpgsign=false", "tag", "--annotate", "--message", "release", "contract-v1.3.0")

    with pytest.raises(freeze_release.FreezeError, match=missing):
        freeze_release.freeze(repo, "1.3.0", tmp_path / "released")

    assert not (tmp_path / "released").exists()


def test_a_release_is_copied_once_and_never_again(tmp_path):
    """Re-copying a release is editing it into agreement with HEAD, so a directory that is there is left as it is."""
    repo = _tagged(tmp_path / "repo", "2.0.0", with_table=True)
    released = tmp_path / "released"
    freeze_release.freeze(repo, "2.0.0", released)
    (released / "2.0.0" / "routes.json").write_bytes(b"edited\n")

    with pytest.raises(freeze_release.FreezeError, match="already exists"):
        freeze_release.freeze(repo, "2.0.0", released)

    assert (released / "2.0.0" / "routes.json").read_bytes() == b"edited\n"


def test_a_copy_is_one_released_would_list_by_version(tmp_path):
    """The directory the tool names is one `released()` reads: the version pattern is the package's, said once and held equal."""
    packages_pattern = arrt_contract._VERSION.pattern  # noqa: SLF001 -- the package's own pattern is what is held
    assert freeze_release.VERSION.pattern == packages_pattern
    repo = _tagged(tmp_path / "repo", "10.0.0", with_table=True)

    directory = freeze_release.freeze(repo, "10.0.0", tmp_path / "released")

    assert arrt_contract._version_of(directory) == (10, 0, 0)  # noqa: SLF001 -- held to the package's own reading of a name


# -- the command line -----------------------------------------------------------------


def test_the_command_line_writes_a_copy_and_says_how_many_files(tmp_path):
    repo = _tagged(tmp_path / "repo", "2.0.0", with_table=True)
    command = [sys.executable, "-I", str(TOOL), "2.0.0", "--repo", str(repo), "--out", str(tmp_path / "released")]

    done = subprocess.run(command, capture_output=True, text=True, check=False, env=_GIT_ENVIRONMENT)

    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == f"{tmp_path / 'released' / '2.0.0'}: 6 files"
    assert (tmp_path / "released" / "2.0.0" / "sha256.json").is_file()


def test_the_command_line_refuses_with_a_message_and_a_failing_status(tmp_path):
    repo = _tagged(tmp_path / "repo", "2.0.0", with_table=True)
    command = [sys.executable, "-I", str(TOOL), "9.9.9", "--repo", str(repo), "--out", str(tmp_path / "released")]

    done = subprocess.run(command, capture_output=True, text=True, check=False, env=_GIT_ENVIRONMENT)

    assert done.returncode == 1
    assert "contract-v9.9.9" in done.stderr
    assert done.stdout == ""
    assert not (tmp_path / "released").exists()


def test_the_command_line_defaults_to_this_checkout_and_its_released_directory():
    """Run with no `--repo` and no `--out`, a release already copied is refused: the defaults are this checkout's own."""
    version = next(iter(arrt_contract.released()))
    command = [sys.executable, "-I", str(TOOL), version]

    done = subprocess.run(command, capture_output=True, text=True, check=False)

    assert done.returncode == 1
    assert str(CHECKOUT / "released" / version) in done.stderr
    assert "already exists" in done.stderr


# -- the tool, on the real tags -------------------------------------------------------


def _repository() -> Path | None:
    """The repository this checkout is in, when it is one and git can be run in it."""
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=CHECKOUT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return Path(top)


def _has_tag(repo: Path, tag: str) -> bool:
    done = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}"], cwd=repo, capture_output=True, check=False
    )
    return done.returncode == 0


@pytest.mark.parametrize("version", sorted(arrt_contract.released()))
def test_each_committed_copy_is_the_bytes_the_tool_writes_from_its_tag(version, tmp_path):
    """The three copies in `released/`, written again by the committed tool from their tags, byte for byte.

    **Where this runs.** Where the repository's tags are fetched: a developer's checkout
    (`git fetch origin --tags`) and any CI checkout that fetches them. A runner that is sent
    this tree's files and no tags skips each case by name, and the report says which tag was
    missing: the comparison was not made there, and no run reports that it was.
    """
    repo = _repository()
    tag = f"contract-v{version}"
    if repo is None or not _has_tag(repo, tag):
        pytest.skip(
            f"{tag} is not in this repository, so the copy of {version} was not compared with it (git fetch origin --tags)"
        )

    written = freeze_release.freeze(repo, version, tmp_path)

    committed = arrt_contract.released()[version]
    assert _tree(written) == _tree(committed)
