"""The Library: what the collection holds, and everything that fills it.

Catalogue, discovery, acquisition, preparation, taste and spend
live here. **Programming reaches it only through `facade.py`**, and nothing here
imports Programming, so that deploying Programming separately later is a
deployment change rather than a rewrite. `tests/preferences/test_seam_imports.py`
holds both halves of that rule.

Deliberately imports nothing: a Programming module importing the facade runs
this file too, and anything imported here would ride in past the seam.
"""
