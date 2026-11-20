"""Copy a released version's frozen files from its tag into `contract/released/<version>/` and hash them.

Run once, in the commit that follows a release's tag (`player-contract.md` § The
package), from a checkout that has the tag::

    git fetch origin --tags
    python3 contract/tools/freeze_release.py 1.3.0

and then, in the same checkout, compare every committed copy with what this writes
from its tag, byte for byte::

    cd contract && uv run pytest -m release_tags

No other run makes that comparison: the pool and CI have no tags, so the marker is
deselected by default, and selected where a tag is missing it fails naming the tag.

It reads the tag through `git archive`, never the working tree, so what is copied
is what a Player pinned to the tag installs. A copy holds the fixtures with their
index, `routes.json`, and the files the tag has of `transport.json` and
`vocabulary.json` (1.2.0 introduced them, so an earlier tag has neither), and a
`sha256.json` of each file's hash. A copy is written once and never again: a
directory that already holds one is refused, because a release re-copied is a
release edited into agreement with HEAD, which `contract/tests/test_released.py`
exists to refuse.

Standard library only, so it runs under `python3 -I` from anywhere. The same
function is what `contract/tests/test_freeze_release.py` calls.
"""

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path

#: A release's version: three whole numbers, none with a leading zero. The package states the
#: same pattern for `released()`; `test_freeze_release.py` holds the two equal.
VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")

#: The tag a version is released under.
TAG = "contract-v{version}"

#: What a frozen copy takes from the tag: everything under `fixtures/`, and these files when the tag has them.
FIXTURES = "fixtures/"
FILES = ("routes.json", "transport.json", "vocabulary.json")

#: What a tag must hold for a copy of it to mean anything.
REQUIRED = ("fixtures/index.json", "routes.json")


class FreezeError(RuntimeError):
    """A copy that cannot be written, named: the version, the tag, the directory or the file at fault."""


def freeze(repo: Path, version: str, out: Path) -> Path:
    """Write `out/<version>/` from `contract-v<version>` in the repository at `repo`; return that directory.

    `out/<version>/sha256.json` records the tag, the commit it names and each
    copied file's SHA-256, sorted by path. A version that is not three whole
    numbers, a tag that is not in the repository, a tag lacking `fixtures/index.json`
    or `routes.json`, and a directory that already exists are each refused by name
    (`FreezeError`) before anything is written.
    """
    if VERSION.fullmatch(version) is None:
        raise FreezeError(f"{version!r} is not a version (major.minor.patch)")
    tag = TAG.format(version=version)
    directory = out / version
    if directory.exists():
        raise FreezeError(f"{directory} already exists: a release is copied once and never again")
    commit = _git(repo, "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}", what=f"the tag {tag}").decode().strip()
    copied = _read_tag(repo, tag)
    missing = [name for name in REQUIRED if name not in copied]
    if missing:
        raise FreezeError(f"{tag} holds no {', '.join(missing)}: it is not a release this tool can freeze")
    for relative, content in copied.items():
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    document = {
        "_about": (
            f"The SHA-256 of every file in this frozen copy of {tag}, written once when it was copied "
            "from the tag. contract/tests/test_released.py holds the copy to it, so an edit to a released file is "
            "seen, and a release is never re-copied."
        ),
        "version": version,
        "tag": tag,
        "commit": commit,
        "files": {relative: hashlib.sha256(copied[relative]).hexdigest() for relative in sorted(copied)},
    }
    (directory / "sha256.json").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return directory


def _git(repo: Path, *arguments: str, what: str) -> bytes:
    """One git command's output; a failure is `FreezeError` naming `what` it was asked for."""
    command = ["git", *arguments]
    try:
        # git, with arguments this module composes from a validated version.
        done = subprocess.run(command, cwd=repo, capture_output=True, check=False)  # noqa: S603 -- git, our arguments
    except OSError as error:
        raise FreezeError(f"cannot run git for {what} in {repo}: {error}") from error
    if done.returncode != 0:
        detail = done.stderr.decode(errors="replace").strip()
        raise FreezeError(f"{what} is not in {repo}: git {arguments[0]} said {detail or 'nothing'} (git fetch origin --tags?)")
    return done.stdout


def _read_tag(repo: Path, tag: str) -> dict[str, bytes]:
    """The files a copy takes from `contract/` at the tag, by path under `contract/`."""
    archive = _git(repo, "archive", f"refs/tags/{tag}", "contract/", what=f"the files of {tag}")
    copied: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            relative = member.name.removeprefix("contract/")
            if not member.isfile() or not (relative.startswith(FIXTURES) or relative in FILES):
                continue
            stream = tar.extractfile(member)
            if stream is None:
                raise FreezeError(f"{tag}: {member.name} cannot be read from the archive")
            copied[relative] = stream.read()
    return copied


def main(argv: list[str] | None = None) -> int:
    """The command line: `freeze_release.py <version> [--repo DIR] [--out DIR]`; 0 when written, 1 when refused."""
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Freeze a released contract version from its tag.")
    parser.add_argument("version", help="the release to copy, such as 1.3.0, from the tag contract-v<version>")
    parser.add_argument(
        "--repo", type=Path, default=here.parents[1], help="the repository holding the tag (default: this checkout)"
    )
    parser.add_argument(
        "--out", type=Path, default=here.parent / "released", help="where <version>/ is written (default: contract/released)"
    )
    arguments = parser.parse_args(argv)
    try:
        directory = freeze(arguments.repo, arguments.version, arguments.out)
    except FreezeError as error:
        print(f"freeze_release: {error}", file=sys.stderr)  # noqa: T201 -- a command line tool's message
        return 1
    files = json.loads((directory / "sha256.json").read_text(encoding="utf-8"))["files"]
    print(f"{directory}: {len(files)} files")  # noqa: T201 -- a command line tool's result
    return 0


if __name__ == "__main__":
    sys.exit(main())
