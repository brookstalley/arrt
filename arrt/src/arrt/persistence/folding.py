"""The form library text is compared in when a curator searches it.

Pure, and in its own module because two layers use it: the SQLite adapter
defines it as a SQL function on both sides of every search clause, and the
artist index filters names with it in Python. Either importing it from the
other would be a service reaching into an adapter, or the reverse.
"""

import functools
import re
import unicodedata
from typing import Final

#: Letters a curator types without their mark that Unicode does not decompose,
#: so dropping combining marks leaves them as they were: `hammershoi` has to
#: find Hammershøi, and `oedipe` Œdipe. Lowercase only, because the fold
#: casefolds first.
_UNDECOMPOSED: Final[dict[int, str]] = str.maketrans(
    {"ø": "o", "æ": "ae", "œ": "oe", "ł": "l", "đ": "d", "ð": "d", "þ": "th", "ı": "i"}
)


_NON_ASCII: Final[re.Pattern[str]] = re.compile(r"[^\x00-\x7f]+")

#: How many folded texts are remembered: one per work, plus the terms typed.
#: A request evaluates the search clause once for the page, once for its total
#: and once per facet count, over the same works, and the next keystroke does it
#: again, so after the first evaluation the fold is a lookup. Measured over
#: 4,000 works whose text is shaped like the owner's (about 650 characters, a
#: few curly quotes and accents each), eight evaluations took about 470 ms
#: unremembered and 36 ms remembered. **It has to exceed the catalogue**: every
#: search walks the works in the same order, and a least-recently-used cache
#: smaller than that walk evicts each entry just before it is asked for again,
#: so it would never hit. The NFR's target is thousands of works; this is room
#: for several times that, at about a kilobyte and a half an entry.
_FOLDS_REMEMBERED: Final[int] = 32_768


@functools.lru_cache(maxsize=_FOLDS_REMEMBERED)
def search_fold(text: str) -> str:
    """`text` as search compares it: without case, accents or ligatures.

    Applied to the stored column and to the typed term alike, so `dali` and
    `Dalí` meet in the middle whichever of them carries the mark, and a name a
    source stored decomposed matches the composed one a keyboard sends.
    Casefolded first, because that is what turns ß into ss; then decomposed
    with NFKD, which splits an accented letter from its accent and spells out a
    compatibility ligature, and the accents dropped. Punctuation and spacing are
    kept, unlike the dedup key's fold: a search is a contains-match on what the
    curator typed, and dropping characters from one side only would stop it
    finding what it shows.

    It over-matches where an accent makes a different letter rather than
    decorating one (Russian й and и fold together). In a contains-search that
    costs an extra result, never a missing one.
    """
    folded = text.casefold()
    # Only non-ASCII characters carry anything to drop, and NFKD decomposes one
    # character at a time, so folding each non-ASCII run alone gives the answer
    # folding the whole string would. It is cheaper by the length of the ASCII
    # around it: this runs once per work for every search, and a description is
    # mostly ASCII.
    return folded if folded.isascii() else _NON_ASCII.sub(_fold_run, folded)


def _fold_run(run: re.Match[str]) -> str:
    decomposed = unicodedata.normalize("NFKD", run.group())
    return "".join(character for character in decomposed if not unicodedata.combining(character)).translate(_UNDECOMPOSED)
