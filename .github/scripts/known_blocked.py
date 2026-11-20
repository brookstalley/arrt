"""What `.github/known-blocked.json` may say, and whether each row still deserves to.

**What the file is for.** The API-drift probes went red on every scheduled run for
seven weeks, for causes nobody had yet established (issues #109, #110, #150), and an
alarm that is always red tells nobody anything: a real drift in a museum's API would
have looked exactly like the day before. The owner's ruling of 2026-11-19 is to mark
the blocked probes as known-blocked, so that a *new* red shows again, rather than to
investigate each by hand first.

A row is the least that ruling can be, and every field of it is there to stop
"blocked" turning into permanent silence:

- ``test`` names the one probe it excuses, as ``<file under arrt/>::<function>``
  (``::<Class>::<function>`` for a method). It must exist: a row for a probe that was
  renamed excuses nothing and reads as if it did.
- ``issue`` is where the cause is being worked. No issue, no excuse.
- ``expires`` is a date no more than 60 days out. When it passes, the row fails the
  job by name rather than lapsing, so the choice to keep excusing a probe is made
  again, in writing, by someone who has looked.
- ``reason`` is what the record says about why, in the owner's words where they are
  known and "not established" where they are not. A cause guessed into this file is
  worse than none.

This module owns that shape. `judge_drift_probes.py` (the job's verdict) and
`check_drift_freshness.py` (the check that the schedule is alive) both read the file
through it, so the two cannot disagree about what a refusable row is.
"""

import ast
import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

#: The longest an excuse may run from the day it is checked. The same number the plan
#: records as its `[DECISION]`; the test for this module fails if the file's own rows
#: are further out than it.
MAX_DAYS = 60

#: Where the file lives in the repository, and where the probes' test ids are rooted.
#: The workflows run the probes with `arrt/` as the working directory, so a row's
#: ``tests/live/...`` is relative to it.
REPO = Path(__file__).resolve().parents[2]
BLOCKED_FILE = REPO / ".github" / "known-blocked.json"
TESTS_ROOT = REPO / "arrt"

_FIELDS = {"test", "issue", "expires", "reason"}


@dataclass(frozen=True)
class Row:
    test: str
    issue: int
    expires: date
    reason: str


def _defines(tree: ast.AST, path: list[str]) -> bool:
    """Whether `tree` has the function (or `Class` then method) that `path` names."""
    *classes, func = path
    scope = tree
    for name in classes:
        scope = next((n for n in getattr(scope, "body", []) if isinstance(n, ast.ClassDef) and n.name == name), None)
        if scope is None:
            return False
    return any(isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name == func for n in getattr(scope, "body", []))


def test_exists(tests_root: Path, test_id: str) -> str | None:
    """Why `test_id` names no test under `tests_root`, or None when it does.

    Read from the source rather than by collecting, because collecting imports the
    probe modules and this runs in a job that has installed nothing: a probe that
    cannot be imported is the probe's own finding, not a reason to be unable to
    read the file.
    """
    if "[" in test_id:
        return "names a parametrization; name the function, which covers every case of it"
    file, _, rest = test_id.partition("::")
    if not rest or not file.endswith(".py"):
        return "is not `<file>.py::<function>`"
    path = (tests_root / file).resolve()
    if tests_root.resolve() not in path.parents or not path.is_file():
        return f"names {file}, which is not a file under {tests_root.name}/"
    if not _defines(ast.parse(path.read_text(encoding="utf-8")), rest.split("::")):
        return f"names {rest}, which {file} does not define"
    return None


def check(path: Path, today: date, tests_root: Path = TESTS_ROOT) -> tuple[list[Row], list[str]]:
    """Every row that holds today, and one problem per thing wrong, each naming its row.

    A row with a problem is never returned as a row: a refused row excuses nothing.
    That is the direction that fails safe, since a probe it was meant to excuse then
    reads as red and unlisted, which fails the job by name.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [], [f"{path.name} does not exist; it must, even with no row in it"]
    except json.JSONDecodeError as error:
        return [], [f"{path.name} is not JSON: {error}"]
    rows_in = document.get("blocked") if isinstance(document, dict) else None
    if not isinstance(rows_in, list):
        return [], [f'{path.name} must be an object with a "blocked" list']

    rows: list[Row] = []
    problems: list[str] = []
    seen: set[str] = set()
    for index, raw in enumerate(rows_in, start=1):
        name = raw.get("test") if isinstance(raw, dict) and isinstance(raw.get("test"), str) else f"row {index}"
        found: list[str] = []
        if not isinstance(raw, dict):
            problems.append(f"known-blocked {name}: is not an object")
            continue
        if extra := sorted(set(raw) - _FIELDS):
            found.append(f"has unknown field(s) {', '.join(extra)}; the fields are {', '.join(sorted(_FIELDS))}")
        if missing := sorted(_FIELDS - set(raw) - {"test"}):
            found.append(f"has no {', '.join(missing)}")
        issue = raw.get("issue")
        if "issue" in raw and (not isinstance(issue, int) or isinstance(issue, bool) or issue < 1):
            found.append("has no issue (a positive issue number is what makes it an excuse and not a shrug)")
        reason = raw.get("reason")
        if "reason" in raw and not (isinstance(reason, str) and reason.strip()):
            found.append("has an empty reason")
        expires = None
        if "expires" in raw:
            try:
                expires = date.fromisoformat(raw["expires"])
            except (TypeError, ValueError):
                found.append(f"has an expiry {raw['expires']!r} that is not a YYYY-MM-DD date")
        if expires is not None:
            if expires < today:
                found.append(
                    f"expired on {expires.isoformat()}. Look at the probe again: fix it, or "
                    f"renew the row for at most {MAX_DAYS} days with the reason for renewing"
                )
            elif expires > today + timedelta(days=MAX_DAYS):
                found.append(f"expires {expires.isoformat()}, more than {MAX_DAYS} days after {today.isoformat()}")
        if isinstance(raw.get("test"), str):
            if why := test_exists(tests_root, raw["test"]):
                found.append(why)
            if raw["test"] in seen:
                found.append("is listed twice")
            seen.add(raw["test"])
        else:
            found.append("has no test (a string naming one probe)")

        if found:
            problems += [f"known-blocked {name}: {each}" for each in found]
        else:
            rows.append(Row(raw["test"], issue, expires, reason.strip()))
    return rows, problems
