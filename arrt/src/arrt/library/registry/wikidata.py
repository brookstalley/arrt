"""Wikidata's query service, asked the three questions a `Registry` answers.

Every shape here was measured before this module existed; the measurements are
`wikidata-findings.md`. Three of them decide how it is written:

**The User-Agent is the deployment's and has no default.** Wikimedia refuses or
blocks requests without a descriptive agent and contact details, and inventing
one would misrepresent whoever runs this, the same reasoning `ARTIC_USER_AGENT`
follows. The caller passes it, and nothing here constructs one.

**The endpoint is a constant, and redirects are not followed.** Nothing a curator
or a museum wrote ever becomes a URL here, so the source-URL guard
(`security-model.md`) has nothing to check; refusing redirects outright is the
stricter half of it, and the service has never been seen to send one.

**"Visual artist" no longer sits under "artist" in Wikidata's occupation tree**, so
`people_named` filters on the occupation that does reach painters, or on having
created something at all, and not on the root that once covered both.
"""

import json
import logging
import re
from collections.abc import Iterator, Mapping, Sequence
from typing import Any, Final

import httpx

from arrt.library.registry import RegistryPerson, RegistryUnavailable
from arrt.library.registry.identifiers import IdentifierScheme

log = logging.getLogger(__name__)

#: The query service. A constant: see the module docstring on redirects.
SPARQL_ENDPOINT: Final[str] = "https://query.wikidata.org/sparql"

#: Values per query. The service's limit is on the query's running time, not its
#: text, and a batch this size of exact-identifier lookups measured well under a
#: second; a POST body carries it, so URL length does not bound it.
BATCH: Final[int] = 200

#: Seconds. A query that has not answered in this long is one the service is
#: about to time out itself (its limit is 60 s).
TIMEOUT_SECONDS: Final[float] = 60.0

#: A QID as the service writes it, which is also what keeps one from closing a
#: query when it is placed into one.
_QID: Final[re.Pattern[str]] = re.compile(r"^Q[1-9][0-9]*$")

#: Visual artist (`Q3391743`): the occupation painters, sculptors and
#: photographers sit under.
_VISUAL_ARTIST: Final[str] = "Q3391743"


class WikidataRegistry:
    """The `Registry` over Wikidata's query service."""

    def __init__(self, *, user_agent: str, client: httpx.Client | None = None) -> None:
        self._headers = {"User-Agent": user_agent, "Accept": "application/sparql-results+json"}
        self._http = client or httpx.Client(timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=10.0), follow_redirects=False)

    def works_by_identifier(self, scheme: IdentifierScheme, values: Sequence[str]) -> Mapping[str, frozenset[str]]:
        found: dict[str, set[str]] = {}
        for batch in _batches(sorted(set(values))):
            listed = " ".join(_literal(value) for value in batch)
            rows = self._select(f"SELECT ?id ?item WHERE {{ VALUES ?id {{ {listed} }} ?item wdt:{scheme.value} ?id . }}")
            for row in rows:
                found.setdefault(_value(row, "id"), set()).add(_qid(row, "item"))
        return {value: frozenset(items) for value, items in found.items()}

    def creators_of(self, work_qids: Sequence[str]) -> Mapping[str, frozenset[str]]:
        found: dict[str, set[str]] = {}
        for batch in _batches(sorted({_require_qid(qid) for qid in work_qids})):
            listed = " ".join(f"wd:{qid}" for qid in batch)
            rows = self._select(f"SELECT ?item ?creator WHERE {{ VALUES ?item {{ {listed} }} ?item wdt:P170 ?creator . }}")
            for row in rows:
                creator = _qid(row, "creator", required=False)
                if creator is not None:
                    found.setdefault(_qid(row, "item"), set()).add(creator)
        return {item: frozenset(creators) for item, creators in found.items()}

    def people_named(self, name: str) -> Sequence[RegistryPerson]:
        rows = self._select(f"""SELECT ?item ?itemLabel (MIN(YEAR(?born)) AS ?bornYear) (MIN(YEAR(?died)) AS ?diedYear) WHERE {{
              SERVICE wikibase:mwapi {{
                bd:serviceParam wikibase:endpoint "www.wikidata.org"; wikibase:api "EntitySearch";
                  mwapi:search {_literal(name)}; mwapi:language "en" .
                ?item wikibase:apiOutputItem mwapi:item .
              }}
              ?item wdt:P31 wd:Q5 .
              FILTER EXISTS {{ {{ ?item wdt:P106/wdt:P279* wd:{_VISUAL_ARTIST} }} UNION {{ ?made wdt:P170 ?item }} }}
              OPTIONAL {{ ?item wdt:P569 ?born }}
              OPTIONAL {{ ?item wdt:P570 ?died }}
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
            }} GROUP BY ?item ?itemLabel""")
        return [
            RegistryPerson(
                qid=_qid(row, "item"),
                label=_value(row, "itemLabel"),
                born=_year(row, "bornYear"),
                died=_year(row, "diedYear"),
            )
            for row in rows
        ]

    def close(self) -> None:
        self._http.close()

    def _select(self, query: str) -> list[Mapping[str, Any]]:
        """Run one SELECT and return its bindings, or say why it could not be run."""
        try:
            response = self._http.post(SPARQL_ENDPOINT, data={"query": query}, headers=self._headers)
        except httpx.HTTPError as exc:
            raise RegistryUnavailable(f"Wikidata could not be reached: {exc}") from exc
        if response.status_code != 200:
            # A redirect lands here too, deliberately: see the module docstring.
            raise RegistryUnavailable(f"Wikidata answered HTTP {response.status_code}.")
        try:
            bindings = response.json()["results"]["bindings"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise RegistryUnavailable("Wikidata's answer was not the JSON results shape it documents.") from exc
        if not isinstance(bindings, list):
            raise RegistryUnavailable("Wikidata's answer carried no list of results.")
        return bindings


def _batches(values: Sequence[str]) -> Iterator[Sequence[str]]:
    for start in range(0, len(values), BATCH):
        yield values[start : start + BATCH]


def _literal(text: str) -> str:
    """`text` as a SPARQL string literal: quoted, with what could end it escaped."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
    return f'"{escaped}"'


def _require_qid(qid: str) -> str:
    if not _QID.match(qid):
        raise ValueError(f"{qid!r} is not a Wikidata item id.")
    return qid


def _value(row: Mapping[str, Any], name: str) -> str:
    try:
        return str(row[name]["value"])
    except (KeyError, TypeError) as exc:
        raise RegistryUnavailable(f"A Wikidata result had no {name!r}.") from exc


def _qid(row: Mapping[str, Any], name: str, *, required: bool = True) -> str | None:
    """The QID at the end of an entity URI, or None for a value that is not an item (an unknown creator)."""
    if not required and name not in row:
        return None
    candidate = _value(row, name).rsplit("/", 1)[-1]
    if _QID.match(candidate):
        return candidate
    if required:
        raise RegistryUnavailable(f"A Wikidata result's {name!r} was not an item: {candidate!r}.")
    return None


def _year(row: Mapping[str, Any], name: str) -> int | None:
    if name not in row:
        return None
    try:
        return int(float(_value(row, name)))
    except ValueError:
        return None
