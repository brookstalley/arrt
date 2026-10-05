"""`search_fold`, the form both sides of a library search are compared in.

The route tests hold what a curator sees. These hold the two claims the
function makes about itself that no route test can see: it folds a non-ASCII
run at a time only because that gives the whole string's answer, and it
casefolds ASCII although `LIKE` would forgive it not doing so.
"""

import unicodedata

import pytest

from arrt.persistence.folding import search_fold


def folded_whole(text: str) -> str:
    """The fold done the slow way, over the whole string at once."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    stripped = "".join(character for character in decomposed if not unicodedata.combining(character))
    return stripped.translate(str.maketrans({"ø": "o", "æ": "ae", "œ": "oe", "ł": "l", "đ": "d", "ð": "d", "þ": "th", "ı": "i"}))


@pytest.mark.parametrize(
    "text",
    [
        "Salvador Dalí",
        "Jean-Léon Gérôme",  # stored decomposed: the mark follows an ASCII letter
        "Berliner Straßenszene",
        "Œdipe et le Sphinx — “a study”",
        "Ο Μέγας Αλέξανδρος",
        "葛飾北斎 ﬁn Й",
        "plain ASCII, nothing to fold",
        "",
    ],
)
def test_folding_run_by_run_gives_the_whole_strings_answer(text):
    assert search_fold(text) == folded_whole(text)


def test_ascii_is_casefolded_too():
    assert search_fold("Nighthawks AND Ostend") == "nighthawks and ostend"
