"""The browser suite's CI shards run every browser test file exactly once.

`.github/workflows/browser.yml` splits the serial browser suite across parallel
jobs, each running the share `.github/scripts/browser_shard.py` computes. A file
in no share would never run in CI while the checks stayed green, and a file in two
would run twice; both are judged here against the real directory and the count
the workflow actually uses, read from the workflow rather than copied.
"""

import importlib.util
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO / ".github" / "scripts" / "browser_shard.py"
WORKFLOW = REPO / ".github" / "workflows" / "browser.yml"
BROWSER_TESTS = REPO / "arrt" / "tests" / "browser"


def _load():
    """Import the script, which lives outside any package and has no importable name."""
    spec = importlib.util.spec_from_file_location("browser_shard", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _workflow_counts() -> dict[str, int]:
    """The shard count as each of the workflow's three places states it."""
    text = WORKFLOW.read_text(encoding="utf-8")
    matrix = re.search(r"^\s*shard:\s*\[([^\]]*)\]", text, re.MULTILINE)
    named = re.search(r"\(\$\{\{ matrix\.shard \}\} of (\d+)\)", text)
    argued = re.search(r"browser_shard\.py tests/browser (\d+) ", text)
    assert matrix and named and argued, "the workflow no longer states its shard count where this test reads it"
    shards = [int(value) for value in matrix.group(1).split(",")]
    assert shards == list(range(1, len(shards) + 1)), f"the matrix should count 1..N, got {shards}"
    return {"matrix": len(shards), "name": int(named.group(1)), "argument": int(argued.group(1))}


def test_the_workflow_states_one_shard_count():
    counts = _workflow_counts()
    assert len(set(counts.values())) == 1, f"the workflow's shard counts disagree: {counts}"


def test_every_browser_test_file_runs_in_exactly_one_shard():
    module = _load()
    count = _workflow_counts()["matrix"]
    files = module.weights(BROWSER_TESTS)
    shares = module.partition(files, count)

    assigned = [name for share in shares for name in share]
    assert sorted(assigned) == sorted(files), "a browser test file is in no shard, or in two"
    assert len(assigned) == len(set(assigned))
    assert all(shares), "a shard with no files would run nothing"


def test_the_shards_are_balanced_within_one_file():
    module = _load()
    files = module.weights(BROWSER_TESTS)
    shares = module.partition(files, _workflow_counts()["matrix"])
    loads = [sum(files[name] for name in share) for share in shares]
    assert max(loads) - min(loads) <= max(files.values()), loads


def test_a_new_file_is_run_by_some_shard(tmp_path):
    module = _load()
    for name, body in {"test_a.py": "def test_one(): ...\n" * 5, "test_b.py": "def test_two(): ...\n"}.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    before = module.partition(module.weights(tmp_path), 2)
    (tmp_path / "test_new.py").write_text("def test_new(): ...\n", encoding="utf-8")
    after = module.partition(module.weights(tmp_path), 2)

    assert "test_new.py" not in [name for share in before for name in share]
    assert "test_new.py" in [name for share in after for name in share]


def test_the_partition_is_the_same_every_time():
    module = _load()
    files = module.weights(BROWSER_TESTS)
    assert module.partition(files, 4) == module.partition(dict(reversed(list(files.items()))), 4)


def test_the_script_prints_its_share_and_refuses_a_shard_out_of_range(tmp_path, capsys):
    module = _load()
    (tmp_path / "test_only.py").write_text("def test_it(): ...\n", encoding="utf-8")

    assert module.main(["browser_shard.py", str(tmp_path), "1", "0"]) == 0
    assert capsys.readouterr().out.strip() == str(tmp_path / "test_only.py")
    assert module.main(["browser_shard.py", str(tmp_path), "2", "1"]) == 1, "an empty shard is a failure, said"
    assert module.main(["browser_shard.py", str(tmp_path), "2", "2"]) == 2


def test_no_shard_count_below_one():
    with pytest.raises(ValueError):
        _load().partition({"test_a.py": 1}, 0)
