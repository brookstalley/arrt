"""Wikidata's query service, asked the questions a `Registry` answers.

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

from arrt.library.registry import (
    QID,
    CommonsFile,
    ItemId,
    MuseumIdentifier,
    RegistryArtist,
    RegistryHolding,
    RegistryPerson,
    RegistryUnavailable,
    RegistryWorkEntry,
)
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


#: Visual artist (`Q3391743`): the occupation painters, sculptors and
#: photographers sit under.
_VISUAL_ARTIST: Final[str] = "Q3391743"

#: Label languages, in order. `mul` is Wikidata's language-neutral label, which
#: some items (the National Gallery of Art among them) now carry instead of an
#: English one; without it their QID comes back as the name.
_LABELS: Final[str] = "en,mul"

#: Joins an artist's movements in one result. A character no movement's name holds.
_SEPARATOR: Final[str] = "\u241e"

#: The only image URLs passed on: a Commons file, by name.
_COMMONS_FILE: Final[re.Pattern[str]] = re.compile(r"^https?://commons\.wikimedia\.org/wiki/Special:FilePath/([^?#\s]+)$")


class WikidataRegistry:
    """The `Registry` over Wikidata's query service."""

    def __init__(self, *, user_agent: str, client: httpx.Client | None = None) -> None:
        self._headers = {"User-Agent": user_agent, "Accept": "application/sparql-results+json"}
        self._http = client or httpx.Client(timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=10.0), follow_redirects=False)

    def works_by_identifier(
        self, scheme: IdentifierScheme, values: Sequence[str]
    ) -> Mapping[MuseumIdentifier, frozenset[ItemId]]:
        found: dict[MuseumIdentifier, set[ItemId]] = {}
        for batch in _batches(sorted(set(values))):
            asked = set(batch)
            listed = " ".join(_literal(value) for value in batch)
            rows = self._select(f"SELECT ?id ?item WHERE {{ VALUES ?id {{ {listed} }} ?item wdt:{scheme.value} ?id . }}")
            for row in rows:
                # The answer names the identifier it matched; one that was not asked
                # about is the service's mistake, or someone else's text, and not a key.
                value = _value(row, "id")
                if value in asked:
                    found.setdefault(MuseumIdentifier(value), set()).add(_qid(row, "item"))
        return {value: frozenset(items) for value, items in found.items()}

    def creators_of(self, work_qids: Sequence[str]) -> Mapping[ItemId, frozenset[ItemId]]:
        found: dict[ItemId, set[ItemId]] = {}
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
                born=_integer(row, "bornYear"),
                died=_integer(row, "diedYear"),
            )
            for row in rows
        ]

    def artist(self, qid: str, *, works: int, holdings: int, include: Sequence[str] = ()) -> RegistryArtist:
        item = _require_qid(qid)
        profile = self._select(
            f"""SELECT ?description (GROUP_CONCAT(DISTINCT ?movementLabel; separator="{_SEPARATOR}") AS ?movements) WHERE {{
              OPTIONAL {{ wd:{item} schema:description ?description FILTER(LANG(?description) = "en") }}
              OPTIONAL {{ wd:{item} wdt:P135 ?movement . ?movement rdfs:label ?movementLabel
                         FILTER(LANG(?movementLabel) = "en") }}
            }} GROUP BY ?description"""
        )
        listed = self._select(
            f"""SELECT ?work ?workLabel ?links (MIN(YEAR(?inception)) AS ?year) (SAMPLE(?image) AS ?img) WHERE {{
              ?work wdt:P170 wd:{item} ; wikibase:sitelinks ?links .
              OPTIONAL {{ ?work wdt:P571 ?inception }}
              OPTIONAL {{ ?work wdt:P18 ?image }}
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{_LABELS}". }}
            }} GROUP BY ?work ?workLabel ?links ORDER BY DESC(?links) ?workLabel LIMIT {int(works)}"""
        )
        listed_qids = {_qid(row, "work") for row in listed}
        wanted = sorted({_require_qid(extra) for extra in include} - listed_qids)
        if wanted:
            listed = listed + self._select(
                f"""SELECT ?work ?workLabel ?links (MIN(YEAR(?inception)) AS ?year) (SAMPLE(?image) AS ?img) WHERE {{
                  VALUES ?work {{ {" ".join(f"wd:{extra}" for extra in wanted)} }}
                  ?work wikibase:sitelinks ?links .
                  OPTIONAL {{ ?work wdt:P571 ?inception }}
                  OPTIONAL {{ ?work wdt:P18 ?image }}
                  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{_LABELS}". }}
                }} GROUP BY ?work ?workLabel ?links ORDER BY DESC(?links) ?workLabel"""
            )
        total = self._select(f"SELECT (COUNT(DISTINCT ?work) AS ?n) WHERE {{ ?work wdt:P170 wd:{item} . }}")
        held_by = self._select(f"""SELECT ?collection ?collectionLabel (COUNT(DISTINCT ?work) AS ?n) WHERE {{
              ?work wdt:P170 wd:{item} ; wdt:P195 ?collection .
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{_LABELS}". }}
            }} GROUP BY ?collection ?collectionLabel ORDER BY DESC(?n) LIMIT {int(holdings)}""")
        first = profile[0] if profile else {}
        return RegistryArtist(
            qid=item,
            description=first["description"]["value"] if "description" in first else None,
            movements=tuple(name for name in first.get("movements", {}).get("value", "").split(_SEPARATOR) if name),
            works=tuple(
                RegistryWorkEntry(
                    qid=_qid(row, "work"),
                    title=_value(row, "workLabel"),
                    sitelinks=_integer(row, "links") or 0,
                    year=_integer(row, "year"),
                    image=_commons_file(row.get("img", {}).get("value")),
                )
                for row in listed
            ),
            works_total=(_integer(total[0], "n") or 0) if total else 0,
            holdings=tuple(
                RegistryHolding(qid=_qid(row, "collection"), name=_value(row, "collectionLabel"), works=_integer(row, "n") or 0)
                for row in held_by
            ),
        )

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
    if not QID.match(qid):
        raise ValueError(f"{qid!r} is not a Wikidata item id.")
    return qid


def _value(row: Mapping[str, Any], name: str) -> str:
    try:
        return str(row[name]["value"])
    except (KeyError, TypeError) as exc:
        raise RegistryUnavailable(f"A Wikidata result had no {name!r}.") from exc


def _qid(row: Mapping[str, Any], name: str, *, required: bool = True) -> ItemId | None:
    """The QID at the end of an entity URI, or None for a value that is not an item (an unknown creator)."""
    if not required and name not in row:
        return None
    candidate = _value(row, name).rsplit("/", 1)[-1]
    if QID.match(candidate):
        return ItemId(candidate)
    if required:
        raise RegistryUnavailable(f"A Wikidata result's {name!r} was not an item: {candidate!r}.")
    return None


def _commons_file(url: str | None) -> CommonsFile | None:
    """A Commons file URL, made `https`, or None for anything else the registry offered as an image."""
    found = _COMMONS_FILE.match(url or "")
    return None if found is None else CommonsFile(f"https://commons.wikimedia.org/wiki/Special:FilePath/{found.group(1)}")


def _integer(row: Mapping[str, Any], name: str) -> int | None:
    if name not in row:
        return None
    try:
        return int(float(_value(row, name)))
    except ValueError:
        return None
