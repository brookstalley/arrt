"""The two planes agree on the key a heartbeat's instant is reported under.

**This is the one agreement whose violation looks like the opposite of itself.**
Curation's reader treats a document without a `reported_at` key as an unreadable
heartbeat and says so on the health panel. A display plane that spelled the field
`timestamp` would therefore be reported as *down* while running perfectly — this
product's defining failure mode, manufactured by the mechanism built to detect it.

**The heartbeat's filename was compared here too, and left on 2026-10-05.** A
Player POSTs its heartbeat (`player-contract.md` § Transport): it writes its own
file under its own cache and Arrt writes what it receives under its own art root,
so neither plane reads a file the other named, and the Norm Health sweep found the
comparison guarding nothing that crosses. The key still crosses, in two bodies (a
wall's heartbeat and a client's), and the contract's schemas require it in both.

**The manifest's name was here too, and left on 2026-10-02.** The display plane
read each wall's manifest from a file curation wrote under a shared art root, so
the two had to agree on its name. A Player is now a client that pulls each
wall's manifest over HTTP into its own cache (`clients.md`), so the display plane
declares no manifest filename and there is no pair left to compare. What
replaced the file — the routes both sides spell — is agreed through
`contract/routes.json`, which `test_plane_isolation.py` holds the pull to and
each plane's own suite holds its routes to.

Neither plane can import the other — the isolation norm forbids display reaching
into curation, and they are separate projects with separate interpreters — so the
constants are declared twice on purpose. That duplication is safe only if
something compares them, and nothing did until this file. It reads both sources
rather than importing either, which is the same technique `test_plane_isolation.py`
uses and works from the repository root with no environment of either plane's.

The guard is proven able to fail below, because a check nobody has watched go red
is a check nobody knows is wired up.
"""

import ast
import json
import pathlib

import pytest

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
WRITER = REPOSITORY_ROOT / "arrt-player" / "src" / "arrt_player" / "heartbeat.py"
READER = REPOSITORY_ROOT / "arrt" / "src" / "arrt" / "programming" / "manifest" / "heartbeat.py"
CLIENT_READER = REPOSITORY_ROOT / "arrt" / "src" / "arrt" / "programming" / "client_heartbeat.py"
SCHEMAS = REPOSITORY_ROOT / "contract" / "schemas"

#: Every declaration both planes make separately and must spell identically, as
#: `(constant, display's copy, curation's copy)`. The Player writes both bodies'
#: key from one constant (`arrt_player/heartbeat.py`), and Arrt reads each body with
#: its own, so each of Arrt's copies is compared with the Player's.
SHARED_CONSTANTS = (
    ("REPORTED_AT_KEY", WRITER, READER),
    ("REPORTED_AT_KEY", WRITER, CLIENT_READER),
)


def string_constants(source: pathlib.Path) -> dict[str, str]:
    """Every module-level `NAME: ... = "literal"` in a file, without importing it.

    Both spellings are read: an annotated assignment, which is how both modules
    declare these today (`Final[str]`), and a plain one, so a module that drops
    its annotation does not silently fall out of the comparison. Only single-name
    targets count — a tuple unpack holding one of these would be a shape neither
    module uses and guessing at it would be worse than missing it.
    """
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    found: dict[str, str] = {}
    for node in tree.body:
        target = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
        if target is not None and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            found[target] = node.value.value
    return found


def test_both_modules_exist_to_be_compared():
    """The vacuity check: this whole file passes trivially over missing files."""
    for constant, in_display, in_curation in SHARED_CONSTANTS:
        assert in_display.is_file(), f"nothing at {in_display} to read {constant} from"
        assert in_curation.is_file(), f"nothing at {in_curation} to read {constant} from"


@pytest.mark.parametrize(("constant", "in_display", "in_curation"), SHARED_CONSTANTS)
def test_the_planes_agree(constant: str, in_display: pathlib.Path, in_curation: pathlib.Path):
    display = string_constants(in_display)
    curation = string_constants(in_curation)

    assert constant in display, f"{_relative(in_display)} declares no {constant}"
    assert constant in curation, f"{_relative(in_curation)} declares no {constant}"
    assert display[constant] == curation[constant], (
        f"the planes disagree about {constant}: "
        f"{_relative(in_display)} says {display[constant]!r}, "
        f"{_relative(in_curation)} says {curation[constant]!r}. "
        "A mismatch here is a running plane reported as down, or a wall that never changes."
    )


def test_the_agreed_value_is_the_one_the_contract_requires():
    """Pinned to the contract, because both sides moving together is still a break.

    A rename that updated both planes would pass the comparison above while every
    Player built from the published contract, which requires `reported_at`, was
    refused or read as down.
    """
    key = string_constants(WRITER)["REPORTED_AT_KEY"]
    for schema in ("heartbeat.v1.schema.json", "client-heartbeat.v1.schema.json"):
        required = json.loads((SCHEMAS / schema).read_text(encoding="utf-8"))["required"]
        assert key in required, f"contract/schemas/{schema} does not require {key!r}"


def _relative(path: pathlib.Path) -> str:
    return str(path.relative_to(REPOSITORY_ROOT))


class TestTheGuardCanFail:
    def test_it_catches_a_disagreement(self, tmp_path: pathlib.Path):
        agreeing = tmp_path / "reader.py"
        agreeing.write_text('REPORTED_AT_KEY: Final[str] = "reported_at"\n')
        disagreeing = tmp_path / "writer.py"
        disagreeing.write_text('REPORTED_AT_KEY: Final[str] = "timestamp"\n')

        assert string_constants(agreeing)["REPORTED_AT_KEY"] != string_constants(disagreeing)["REPORTED_AT_KEY"]

    def test_it_reads_a_plain_assignment_too(self, tmp_path: pathlib.Path):
        """So a module dropping its `Final[str]` annotation does not go unread."""
        plain = tmp_path / "plain.py"
        plain.write_text('HEARTBEAT_FILENAME_TEMPLATE = "display-heartbeat-{wall_id}.json"\n')

        assert string_constants(plain)["HEARTBEAT_FILENAME_TEMPLATE"] == "display-heartbeat-{wall_id}.json"

    def test_it_does_not_invent_constants_that_are_not_there(self, tmp_path: pathlib.Path):
        empty = tmp_path / "empty.py"
        empty.write_text('"""No constants here."""\n\nINTERVAL = 60\n')

        assert string_constants(empty) == {}
