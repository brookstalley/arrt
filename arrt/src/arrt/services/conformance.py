"""The seam's stores, checked against their Protocols by the type checker rather than at a call site.

The Library and Programming each ask their storage through a structural
`Protocol` (`CatalogueStore`, `ProgrammingStore`, `DiscoveryStore`), and one open
SQLite file answers both sides (`OneCatalogueFile`). Nothing inherits from a
Protocol, so nothing at runtime says the adapter still satisfies it: a method
whose signature drifts on one side fails only when that method is called. Each
function below states one "satisfies" as a return the type checker must accept,
so a drift fails `uv run mypy` (`arrt/pyproject.toml` checks this module
strictly) and names the member that drifted. The facade is a class, not a
Protocol, and is checked strictly as itself (`arrt.library.facade`).

Nothing imports this module and nothing calls these functions: they exist to be
type-checked. A Protocol or adapter added to the seam gets its line here.
"""

from arrt.persistence.catalogue import CatalogueStore
from arrt.persistence.discovery import DiscoveryStore
from arrt.persistence.sqlite import SqliteCatalogue
from arrt.persistence.sqlite_discovery import SqliteDiscovery
from arrt.programming.store import ProgrammingStore
from arrt.services.container import OneCatalogueFile


def sqlite_catalogue_is_the_librarys_store(store: SqliteCatalogue) -> CatalogueStore:
    return store


def sqlite_catalogue_is_programmings_store(store: SqliteCatalogue) -> ProgrammingStore:
    return store


def sqlite_catalogue_is_one_catalogue_file(store: SqliteCatalogue) -> OneCatalogueFile:
    return store


def sqlite_discovery_is_the_discovery_store(store: SqliteDiscovery) -> DiscoveryStore:
    return store
