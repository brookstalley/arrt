"""The museum or archive behind a source plugin, by the name a curator knows it by.

A plugin records what it finds under its plugin id (`artic`, `smk`), which is a
key and not a name: a sentence saying "smk holds this as…" tells somebody who
knows the National Gallery of Denmark nothing. So every sentence the server
composes about a source names it through `museum_name`.

**Each built-in plugin declares its own name**, as `MUSEUM` beside its
`PROVIDER`, so the name lives with the code that answers under it and a new
built-in is named where it is written. This module only gathers them. The
client's `MUSEUM_NAMES` (`http/static/core/providers.js`) is held to the same
pairs by `tests/unit/test_client_vocabulary.py`, so the browser and the server
cannot come to name one museum two ways.

**A plugin installed from elsewhere names itself** with `SourcePlugin.museum`
(interface 1.4). The loader declares those names here each time it loads
(`declare_museums`), so they are the names of the plugins installed now. One that
declares none is named by its id, which is still what it called itself. The
browser learns the same names from `GET /api/sources`.
"""

import importlib
import pkgutil
from collections.abc import Mapping
from functools import cache
from types import MappingProxyType


@cache
def built_in_museums() -> Mapping[str, str]:
    """Every built-in plugin's `PROVIDER`, mapped to its `MUSEUM`.

    Gathered on first use rather than at import, because the plugin modules
    import the discovery types and the discovery code asks for names: reading
    them here at import would make that a cycle.
    """
    from arrt.library import sources

    names = {}
    for found in pkgutil.iter_modules(sources.__path__):
        module = importlib.import_module(f"{sources.__name__}.{found.name}")
        provider = getattr(module, "PROVIDER", None)
        museum = getattr(module, "MUSEUM", None)
        if isinstance(provider, str) and isinstance(museum, str):
            names[provider] = museum
    return MappingProxyType(names)


#: The names the installed plugins declared at the latest load, by plugin name.
#: Replaced whole by each load, never added to, so a plugin since uninstalled is
#: not named by a name it once gave.
_declared: dict[str, str] = {}


def declare_museums(names: Mapping[str, str]) -> None:
    """Record the museum names the installed plugins declared, replacing the last load's."""
    _declared.clear()
    _declared.update(names)


def museum_name(provider: str, declared: str | None = None) -> str:
    """The name a curator knows this source by, or its plugin id when it declares none.

    `declared` is the plugin's own declaration where the caller holds it (a
    plugin's reading carries it), so a surface listing the plugins reads each
    one's name from its own reading; without it, the latest load's.
    """
    return built_in_museums().get(provider) or declared or _declared.get(provider) or provider
