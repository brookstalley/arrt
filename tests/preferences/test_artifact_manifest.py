"""Every artifact on disk is in `artifact_manifest`, and every manifest entry is on disk.

`.prawduct/project-state.yaml`'s `artifact_manifest` is what a dependency walk
reads: a sweep for what a changed decision touches enumerates its entries and
follows their `depends_on` edges. An artifact missing from it is invisible to that
walk, and the sweep reports a clean pass over a document it never saw. Every
registration was made by hand, and so was every correction, four times over.

Membership only. Whether the `depends_on` edges are right or complete is a
judgement about each document's content, which this guard does not attempt.

Disk side: the top level of `.prawduct/artifacts/`, less `build-plan-*.md`. A live
build plan is registered by nobody, because it is archived when its scope releases.
`archive/`, `prototypes/` and `procurement-corpus-research/` are subdirectories,
so the glob does not reach them. Manifest side: every `file_path` under
`artifacts` and `findings`, which must exist wherever it points, `archive/`
included.
"""

import pathlib

import yaml

_REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]
_STATE = _REPOSITORY_ROOT / ".prawduct" / "project-state.yaml"
_ARTIFACTS = _REPOSITORY_ROOT / ".prawduct" / "artifacts"


def _on_disk(artifacts: pathlib.Path) -> set[str]:
    return {
        path.relative_to(artifacts.parents[1]).as_posix()
        for path in artifacts.glob("*.md")
        if not path.name.startswith("build-plan-")
    }


def _registered(state: dict) -> list[str]:
    manifest = state["artifact_manifest"]
    return [entry["file_path"] for section in ("artifacts", "findings") for entry in manifest[section]]


def _membership_faults(state: dict, root: pathlib.Path) -> list[str]:
    registered = _registered(state)
    twice = sorted({path for path in registered if registered.count(path) > 1})
    unregistered = sorted(_on_disk(root / ".prawduct" / "artifacts") - set(registered))
    missing = sorted(path for path in set(registered) if not (root / path).is_file())
    return (
        [f"{path}: registered twice" for path in twice]
        + [f"{path}: on disk, missing from artifact_manifest" for path in unregistered]
        + [f"{path}: in artifact_manifest, no such file" for path in missing]
    )


def test_the_manifest_and_the_artifacts_directory_agree():
    state = yaml.safe_load(_STATE.read_text(encoding="utf-8"))
    assert _membership_faults(state, _REPOSITORY_ROOT) == []


def _tree(tmp_path: pathlib.Path, *names: str) -> pathlib.Path:
    artifacts = tmp_path / ".prawduct" / "artifacts"
    (artifacts / "archive").mkdir(parents=True)
    for name in names:
        (artifacts / name).write_text("# x\n", encoding="utf-8")
    return tmp_path


def _state(artifacts: list[str], findings: list[str]) -> dict:
    return {
        "artifact_manifest": {
            "artifacts": [{"name": p, "file_path": f".prawduct/artifacts/{p}", "depends_on": []} for p in artifacts],
            "findings": [{"file_path": f".prawduct/artifacts/{p}", "depends_on": []} for p in findings],
        }
    }


def test_a_file_on_disk_the_manifest_does_not_name_fails_by_name(tmp_path):
    root = _tree(tmp_path, "brief.md", "x-findings.md", "stray.md")
    assert _membership_faults(_state(["brief.md"], ["x-findings.md"]), root) == [
        ".prawduct/artifacts/stray.md: on disk, missing from artifact_manifest"
    ]


def test_a_manifest_entry_with_no_file_fails_by_name_in_either_section(tmp_path):
    root = _tree(tmp_path, "brief.md")
    assert _membership_faults(_state(["brief.md", "gone.md"], ["gone-findings.md"]), root) == [
        ".prawduct/artifacts/gone-findings.md: in artifact_manifest, no such file",
        ".prawduct/artifacts/gone.md: in artifact_manifest, no such file",
    ]


def test_live_build_plans_and_subdirectories_are_outside_the_disk_side(tmp_path):
    root = _tree(tmp_path, "brief.md", "build-plan-next.md", "archive/old.md")
    assert _membership_faults(_state(["brief.md"], []), root) == []


def test_an_archived_entry_is_checked_for_existence(tmp_path):
    root = _tree(tmp_path, "brief.md", "archive/build-plan.md")
    assert _membership_faults(_state(["brief.md", "archive/build-plan.md", "archive/gone.md"], []), root) == [
        ".prawduct/artifacts/archive/gone.md: in artifact_manifest, no such file"
    ]


def test_a_file_registered_in_both_sections_fails_by_name(tmp_path):
    root = _tree(tmp_path, "brief.md")
    assert _membership_faults(_state(["brief.md"], ["brief.md"]), root) == [".prawduct/artifacts/brief.md: registered twice"]
