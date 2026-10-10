"""Programming: themes, walls, what hangs where, and each wall's feed.

It reads the Library only through `arrt.library.facade`, and holds work ids
as references that may one day fail to resolve. Its tables are reached through
`store.py`'s protocol, so that giving them their own file later changes one
implementation and no caller.
"""
