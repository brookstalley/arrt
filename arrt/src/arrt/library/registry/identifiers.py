"""The museum identifiers a held work's sources carry, read from their URLs.

**A work is matched to a registry only through one of these, never through its
title** (`wikidata-findings.md` § The match rate): a museum's identifier names
one object, while a title like *Chicago* or *Target* names several works by the
same artist, and a generic title that happens to match once cannot be checked.

The patterns admit only the characters each museum uses in its identifiers,
which also means a value can never close the quoted string it is placed in when
a query is built from it.
"""

import re
from enum import StrEnum
from typing import Final


class IdentifierScheme(StrEnum):
    """A museum's identifier, named by the Wikidata property that records it."""

    #: The Art Institute of Chicago's artwork ID.
    ARTIC = "P4610"
    #: A Google Arts & Culture asset ID.
    GOOGLE_ARTS = "P4701"


#: `https://www.artic.edu/artworks/102581/painting`: the number is the ID, the
#: slug after it is decoration the museum may change.
_ARTIC: Final[re.Pattern[str]] = re.compile(r"^https?://(?:www\.)?artic\.edu/artworks/(\d+)(?:[/?#]|$)")

#: `https://artsandculture.google.com/asset/ion-11-victor-vasarely/zAGDIJRNphFaPw`:
#: the last segment is the ID, the slug before it optional.
_GOOGLE_ARTS: Final[re.Pattern[str]] = re.compile(
    r"^https?://artsandculture\.google\.com/asset/(?:[^/?#]+/)?([A-Za-z0-9_-]+)(?:[/?#]|$)"
)


def museum_identifier(url: str) -> tuple[IdentifierScheme, str] | None:
    """The museum identifier a source URL carries, or None if it carries none this knows."""
    for scheme, pattern in ((IdentifierScheme.ARTIC, _ARTIC), (IdentifierScheme.GOOGLE_ARTS, _GOOGLE_ARTS)):
        found = pattern.match(url)
        if found:
            return scheme, found.group(1)
    return None
