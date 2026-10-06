"""Only the picture store asks a source for a preview.

The owner's norm (`data-model.md` § Direction, 2026-10-06) is that a picture
fetched from outside is kept and every ask of thumbnail size is answered from the
store, never from the source again. That holds only while the store is the one
place a preview is fetched: a second caller of `fetch_preview` would go to the
museum behind the store's back and keep nothing.

So this reads every module under `arrt/src` and fails on any reference to an
attribute named `fetch_preview` — a call, or the bound method handed to someone
else to call — outside `pictures.py`. The one exception is the seam's own
forwarding: a method that is itself named `fetch_preview` (the pool, and the
loader's wrapper around a plugin) passes the ask one hop further down, and is
reached only through the store.
"""

import ast
import pathlib

SOURCE_ROOT = pathlib.Path(__file__).resolve().parents[2] / "src" / "arrt"
STORE = SOURCE_ROOT / "library" / "services" / "pictures.py"


def references_outside_the_store(tree: ast.AST) -> list[int]:
    """Line numbers of `.fetch_preview` references not inside a method that is itself `fetch_preview`."""
    found: list[int] = []

    def walk(node: ast.AST, *, forwarding: bool) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            forwarding = node.name == "fetch_preview"
        if isinstance(node, ast.Attribute) and node.attr == "fetch_preview" and not forwarding:
            found.append(node.lineno)
        for child in ast.iter_child_nodes(node):
            walk(child, forwarding=forwarding)

    walk(tree, forwarding=False)
    return found


def test_only_the_picture_store_reaches_a_sources_fetch_preview():
    modules = sorted(SOURCE_ROOT.rglob("*.py"))
    assert STORE in modules, "the store moved, so this guard would exempt nothing and scan a tree without it"
    offenders = {
        str(path.relative_to(SOURCE_ROOT)): lines
        for path in modules
        if path != STORE and (lines := references_outside_the_store(ast.parse(path.read_text(encoding="utf-8"))))
    }
    assert not offenders, (
        f"only `pictures.py` may ask a source for a preview, and these modules reach `fetch_preview`: {offenders}. "
        "Ask the picture store instead (`PictureStore.keep`), which answers from what it keeps."
    )
    # Guards the guard: the store itself must still be found making the call,
    # or a renamed attribute would leave this scanning for a name nothing uses.
    assert references_outside_the_store(ast.parse(STORE.read_text(encoding="utf-8")))


def test_the_scan_sees_a_planted_call_and_a_handed_off_method():
    planted = ast.parse(
        "def fetch(pool, cache):\n"
        "    pool.fetch_preview('artic', 'https://x')\n"
        "    return cache(pool.fetch_preview)\n"
        "class Wrapper:\n"
        "    def fetch_preview(self, url):\n"
        "        return self._inner.fetch_preview(url)\n"
    )
    assert references_outside_the_store(planted) == [2, 3]
