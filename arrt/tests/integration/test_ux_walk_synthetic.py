"""`tools/ux_walk.py --synthetic`: a throwaway Arrt over the suite's corpus, booted and stopped.

It is the first of the walk's two scales (`docs/ux-walkthrough.md`), and it
reaches into the suite for its corpus (`conftest._open_seeded_catalogue`) and
into the config for the catalogue's filename. Either can move under it while
every other suite stays green, so this boots the real entry point on a small
corpus and asks it what it holds.
"""

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import ux_walk  # tools/ is not a package; the path is inserted above


def test_it_boots_on_the_seeded_corpus_serves_it_and_cleans_up():
    server, base_url, root = ux_walk.boot_synthetic(24)
    try:
        works = httpx.get(f"{base_url}/api/works", params={"limit": 1}, timeout=10).json()
        shell = httpx.get(f"{base_url}/", timeout=10)
    finally:
        ux_walk.stop_synthetic(server, root)

    assert works["total"] == 24
    assert shell.status_code == 200
    assert server.returncode is not None
    assert not root.exists()
