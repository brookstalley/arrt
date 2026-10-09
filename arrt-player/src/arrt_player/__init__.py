"""The display plane: make the physical world match the manifest.

A Player is a **client** (`clients.md`): it asks the server which walls it
drives, pulls each wall's manifest and renders into its own cache, and shows
each wall from that cache on one of its outputs — the Frame, or a screen it draws
itself. It reaches the server only through the Player contract's routes, from
one module (`pull.py`), imports no curation module and queries no curation
database. That is a ratified norm rather than a convention, and
`tests/preferences/test_plane_isolation.py` enforces it mechanically, because the
violation it guards against ("just fetch the label text live") works perfectly in
development and in every test: the server is up in both, so a green suite is
exactly what the violation looks like.

The consequence worth knowing before reading further is that this plane keeps
working when the other one is gone. A cached manifest may be arbitrarily stale;
if the server stops, every wall goes on rotating its last theme forever, and that
is correct behaviour rather than degradation.
"""
