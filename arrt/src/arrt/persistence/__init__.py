"""Storage for the catalogue, reached only through the service layer.

`catalogue.py` and `discovery.py` name the Library's two contracts, `records.py`
and `discovery_records.py` the records behind them, and `sqlite.py` and
`sqlite_discovery.py` the adapters that implement them over one open file.
Programming's contract is `arrt.programming.store`, and `sqlite.py`'s
adapter implements it too until Programming's tables get a file of their own.
Nothing above this package imports a backend directly, which is what keeps
replacing one a change confined to it.
"""
