"""Print the browser-suite files one CI shard runs, so the shards share the suite.

The browser suite runs serially (`-n0`): its tests time real poll windows, and
parallel workers contending for a CI runner's cores turn those windows into
flakes. So its wall clock is cut by running several serial jobs side by side,
each on a share of the files, rather than by parallelism inside one job.

**Every test module lands in exactly one shard**, found as pytest finds them. The partition is computed from the
directory each time, never from a list kept here, so a new test file is run by
some shard the day it is added. `tests/test_browser_shards.py` holds that across
the shard count the workflow uses.

**Shares are balanced by test count**, greedily, largest file first, onto the
lightest shard so far. Counting `def test_` lines ignores parametrisation, which
is close enough to even the shards out without collecting the suite (collecting
would need the browser group installed before the shard is chosen).

Usage: browser_shard.py <tests/browser directory> <shard count> <shard index>
"""

import pathlib
import re
import sys

_TEST = re.compile(r"^\s*def test_", re.MULTILINE)


#: What pytest collects as a test module, by its own defaults (Arrt's `pyproject.toml`
#: sets no `python_files`): `test_*.py` and `*_test.py`, in any subdirectory.
_PATTERNS = ("test_*.py", "*_test.py")


def weights(directory: pathlib.Path) -> dict[str, int]:
    """Each test module's path under `directory`, and how many tests it defines (at least one)."""
    modules = {path for pattern in _PATTERNS for path in directory.rglob(pattern) if "__pycache__" not in path.parts}
    return {
        path.relative_to(directory).as_posix(): max(1, len(_TEST.findall(path.read_text(encoding="utf-8"))))
        for path in sorted(modules)
    }


def partition(files: dict[str, int], count: int) -> list[list[str]]:
    """The files split into `count` shares of near-equal weight; deterministic for one input."""
    if count < 1:
        raise ValueError(f"A suite needs at least one shard, got {count}.")
    shares: list[list[str]] = [[] for _ in range(count)]
    loads = [0] * count
    # Heaviest first, then by name, so equal weights always fall the same way.
    for name, weight in sorted(files.items(), key=lambda item: (-item[1], item[0])):
        lightest = min(range(count), key=lambda index: (loads[index], index))
        shares[lightest].append(name)
        loads[lightest] += weight
    return [sorted(share) for share in shares]


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    directory, count, index = pathlib.Path(argv[1]), int(argv[2]), int(argv[3])
    if not 0 <= index < count:
        print(f"Shard {index} is not one of 0..{count - 1}.", file=sys.stderr)
        return 2
    share = partition(weights(directory), count)[index]
    if not share:
        # An empty shard would run nothing and the guard after it would fail the job:
        # say why here instead.
        print(f"Shard {index} of {count} has no files: there are fewer test files than shards.", file=sys.stderr)
        return 1
    print(" ".join(str(directory / name) for name in share))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
