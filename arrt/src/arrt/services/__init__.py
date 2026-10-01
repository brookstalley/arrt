"""What both sides of the Library/Programming seam share, and what composes them.

`errors.py`, `store.py` and `fields.py` are a shared kernel either side may
import. `container.py` and `health.py` compose both sides and are imported by
neither. The operation logic itself lives in `arrt.library.services` and
`arrt.programming`, and the surfaces are bindings over those.
"""
