"""Every file a live record cites is a file in this tree, or says which tree it is in.

Deleting or moving a file leaves every sentence that names it pointing at nothing,
and nothing about such a sentence looks wrong: it reads as an instruction
(`Install deploy/journald.conf.d/…`) or as an authority (`samsung-tv-state-findings.md
is the map`) whether or not the file is there. A sweep for the moved files'
directory finds only the citations spelled with that directory; the rest are
written by bare name. So the citations are resolved against the tree, which is
keyed on nothing the move keyed on.

A file in another repository is cited as `<repository>:<path>`, git's own form
(`arrt-player:deploy/display.service`), or by URL. Neither is resolved here.

**Records keep the names of their day** and are not scanned: the change log and
its archive, archived and released plans, build plans (bookkeeping of a change
that may itself remove what it cites), and the operator queue, whose dated
entries say so in their own heading.
"""

import pathlib
import re
import subprocess

import pytest
from repository import ROOT

#: Files whose prose is a record of its day rather than a description of now.
_RECORDS = re.compile(
    r"^\.prawduct/(change-log|artifacts/archive/|artifacts/release-plan-|artifacts/build-plan-|operator-verification\.md)"
)

#: The live records: the artifacts, the project's state, the runbooks, and the
#: instructions and documentation a reader acts on.
_LIVE = re.compile(
    r"^(\.prawduct/artifacts/[^/]+\.md|\.prawduct/project-state\.yaml|\.prawduct/runbooks/.+\.md"
    r"|CLAUDE\.md|README\.md|docs/.+\.md|deploy/.+|\.env\.example)$"
)

#: A path under the root's own directories, as a record writes one. Not after
#: `:` (another repository's path) or `/` (a URL, or the tail of a longer path),
#: and not under `.prawduct/.`, the gitignored machine state no clone carries.
#:
#: **A project's paths are not resolved here.** Records write them relative to
#: the project (`tests/live/…` for `arrt/tests/live/…`, `arrt/config.py` for
#: `arrt/src/arrt/config.py`), so resolving them needs each project's layout, and
#: a scan that guessed would cry wolf on every shorthand.
_PATH = re.compile(r"(?<![\w:/.*-])((?:\.prawduct/(?!\.)|\.claude/|\.github/|deploy/|docs/)[\w./-]*[\w-])")

#: A file cited by its bare name, in the extensions a moved or deleted file here
#: has carried. Not after `*` (a glob), `:` or `/`.
_BARE = re.compile(r"(?<![\w:/.*-])([\w][\w.-]*\.(?:md|service|txt|conf))\b")

#: An artifact named in a plan's or artifact's frontmatter.
_FRONTMATTER = re.compile(r"^\s*-\s*artifact:\s*([\w-]+)\s*$")

#: Names a live record cites that are deliberately not files here, each with why.
_NOT_FILES_HERE = {
    # Owed, and said so where it is cited: an artifact that does not exist yet.
    "test-specifications.md",
    # Prawduct's own specifications, cited where its behaviour is configured.
    "post-sync-advisory-spec.md",
    "backlog-service-requirements.md",
    # The learnings file before it was split into `.claude/rules/learnings/`,
    # named in `re-architecture.md` § Artifacts touched, a dated list.
    "learnings.md",
    # Prawduct's norms guide, which `project-state.yaml` cites for a key's meaning.
    "docs/norms.md",
    # A prefix, not a file: the UX walkthrough's reports are named by date.
    ".prawduct/artifacts/ux-review-",
    # A museum's or website's crawl rules, not a file of this repository.
    "robots.txt",
    # The 2024 plane's install list, deleted at wave 5 with nothing replacing it:
    # the live citation says it retired, and the rest sit in dated decisions.
    "requirements.txt",
}


def _tracked() -> list[str]:
    listed = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True, text=True).stdout
    return [name for name in listed.split("\0") if name]


def _live_records(tracked: list[str]) -> list[str]:
    return [name for name in tracked if _LIVE.match(name) and not _RECORDS.match(name)]


def dangling(text: str, tracked: list[str]) -> list[str]:
    """Each citation in `text` that names no tracked file or directory, as `line: citation`."""
    paths = set(tracked)
    directories = {str(parent) for name in tracked for parent in pathlib.PurePosixPath(name).parents}
    names = {pathlib.PurePosixPath(name).name for name in tracked}
    # An artifact is a document under `artifacts/`, or the project's state beside it.
    artifacts = {
        pathlib.PurePosixPath(name).stem
        for name in tracked
        if (name.startswith(".prawduct/artifacts/") and name.endswith(".md")) or name == ".prawduct/project-state.yaml"
    }
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        for match in _PATH.finditer(line):
            cited = match.group(1).rstrip(".")
            if cited not in paths and cited not in directories and cited not in _NOT_FILES_HERE:
                found.append(f"{number}: {cited}")
        for match in _BARE.finditer(line):
            cited = match.group(1)
            if cited not in names and cited not in _NOT_FILES_HERE:
                found.append(f"{number}: {cited}")
        frontmatter = _FRONTMATTER.match(line)
        if frontmatter and frontmatter.group(1) not in artifacts:
            found.append(f"{number}: artifact {frontmatter.group(1)}")
    return found


_TRACKED = _tracked()


def _gitignored(fault: str, root: pathlib.Path = ROOT) -> bool:
    """Whether a dangling path is one git ignores: machine state a record may name, which no clone carries.

    **Asked of the directory form too.** A directory-only rule (`backlog-export/`)
    matches a path git cannot see is a directory, which is every path no clone
    carries: `git check-ignore` answers it only when the directory is on disk, so
    the bare form passes on the machine that made it and fails on a fresh checkout.
    """
    cited = fault.split(": ", 1)[1]
    if "/" not in cited:
        return False
    # One path per call: `-q` refuses more than one, and its refusal exits non-zero
    # exactly as "not ignored" does.
    return any(
        subprocess.run(["git", "check-ignore", "-q", form], cwd=root, check=False).returncode == 0
        for form in (cited, cited + "/")
    )


def test_the_scan_has_records_to_read():
    """A parametrised guard over no files passes by checking nothing."""
    assert len(_live_records(_TRACKED)) > 20, _live_records(_TRACKED)


@pytest.mark.parametrize("record", _live_records(_TRACKED))
def test_every_file_a_live_record_cites_is_in_this_tree(record: str):
    faults = [fault for fault in dangling((ROOT / record).read_text(encoding="utf-8"), _TRACKED) if not _gitignored(fault)]
    assert not faults, (
        f"{record} cites files that are not in this tree: {faults}. If the file moved to another "
        "repository, cite it as `<repository>:<path>` or by URL; if it was deleted, say what replaced it."
    )


TRACKED_FIXTURE = [".prawduct/artifacts/kept-findings.md", "deploy/curation.service", "docs/testing.md"]


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("Install `deploy/display.service` first.", ["1: deploy/display.service"]),
        ("See `gone-findings.md` § The states.", ["1: gone-findings.md"]),
        ("for the reason spelled out in display.service: a", ["1: display.service"]),
        ("with pi-freeze-2024.txt recording what to vendor", ["1: pi-freeze-2024.txt"]),
        ("the 10-bound-the-journal.conf drop-in", ["1: 10-bound-the-journal.conf"]),
        ("  - artifact: gone-findings", ["1: artifact gone-findings"]),
        ("[x](gone-findings.md)", ["1: gone-findings.md"]),
        ("`arrt-player:deploy/display.service` and `arrt-player:.prawduct/artifacts/gone-findings.md`", []),
        ("https://github.com/o/arrt-player/blob/develop/deploy/README.md", []),
        ("`kept-findings.md`, `.prawduct/artifacts/kept-findings.md`, `deploy/curation.service`", []),
        ("the `*-api-findings.md` documents", []),
        ("  - artifact: kept-findings", []),
        ("`docs/` and `deploy/`", []),
        ("`.prawduct/.advisories.json`, written by the hook", []),
    ],
)
def test_the_scan_tells_a_dangling_citation_from_a_resolved_one(line: str, expected: list[str]):
    """Each form a citation takes, dangling and resolved, so a pattern that stops seeing one fails here."""
    assert dangling(line, TRACKED_FIXTURE) == expected


def test_a_directory_only_ignore_matches_a_directory_no_clone_carries(tmp_path: pathlib.Path):
    """The rule names a directory that is absent, as it is on every fresh checkout."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("state/export/\n", encoding="utf-8")
    assert not (tmp_path / "state" / "export").exists()

    assert _gitignored("1: state/export", tmp_path)
    assert not _gitignored("1: state/kept", tmp_path)
