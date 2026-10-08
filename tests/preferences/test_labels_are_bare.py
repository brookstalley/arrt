"""Labels are bare nouns and verbs: *Works*, not *The works*.

`information-architecture.md` § Labels states the rule: navigation, headings,
column headers, buttons, field labels, return labels, panel titles and captions
name a thing or an act, and sentences stay sentences. The owner, 2026-10-07:
"there's a pervasive pattern of 'The works' or 'the sources' labeling that feels
affected. Why not just Works, Sources, etc."

**Form-agnostic on purpose.** A label reaches the page as a heading's `text`, a
button's, a route's `returnLabel`, a table's header list, a field's `<label>`, a
string handed to a helper that draws a panel title, or a caption. A guard keyed
on any one of those forms misses the rest, and about half the sites the owner's
complaint found were not headings. So this reads *every* string literal in the
client — and the text of `index.html` — and refuses a short one that opens with
"The ". Short is what tells a label from a sentence: a label is a few words, and
a sentence that opens with "The" ("The themes could not be read") runs longer.

Here rather than in the curation plane's suite because it is a contract between
an artifact and the code, as the other files in this directory are.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "arrt" / "src" / "arrt" / "http" / "static"

#: At most this many words, and a string opening "The " is a label rather than
#: a sentence. Measured against the client on 2026-10-07: every label the owner's
#: complaint and the issue's sweep named is four words or fewer ("The direction to
#: search for" is the longest, at five), and the shortest sentence opening "The"
#: is six ("The themes could not be read").
LABEL_WORDS = 5


def string_literals(source: str) -> list[tuple[int, str]]:
    """Every string literal in a JS module, with its line, comments excluded.

    A template literal's `${…}` holes are kept as one word each, so `The ${name}`
    is read as the two-word label it renders. A small scanner rather than a
    regex, because a comment can hold a quote and a string can hold `//`.
    """
    found: list[tuple[int, str]] = []
    index, line, length = 0, 1, len(source)
    while index < length:
        char = source[index]
        if char == "\n":
            line += 1
            index += 1
        elif source.startswith("//", index):
            index = source.find("\n", index)
            index = length if index == -1 else index
        elif source.startswith("/*", index):
            end = source.find("*/", index + 2)
            end = length if end == -1 else end + 2
            line += source.count("\n", index, end)
            index = end
        elif char in "\"'`":
            start_line, quote, index = line, char, index + 1
            text: list[str] = []
            depth = 0
            while index < length:
                char = source[index]
                if char == "\\":
                    text.append(source[index : index + 2])
                    index += 2
                    continue
                if quote == "`" and source.startswith("${", index) and depth == 0:
                    depth, index = 1, index + 2
                    text.append("${}")
                    continue
                if depth:
                    depth += {"{": 1, "}": -1}.get(char, 0)
                    index += 1
                    continue
                if char == quote:
                    index += 1
                    break
                if char == "\n":
                    line += 1
                text.append(char)
                index += 1
            found.append((start_line, "".join(text)))
        else:
            index += 1
    return found


def html_texts(source: str) -> list[tuple[int, str]]:
    """The text a page shows and the labels it carries: element text and the label attributes."""
    found = []
    for number, row in enumerate(source.splitlines(), start=1):
        found += [(number, text.strip()) for text in re.findall(r">([^<>]+)<", row) if text.strip()]
        found += [(number, text) for text in re.findall(r'(?:aria-label|placeholder|title)="([^"]+)"', row)]
    return found


def labels_opening_with_the(path: Path, texts: list[tuple[int, str]]) -> list[str]:
    offenders = []
    for line, text in texts:
        words = text.strip().lstrip("←").strip()
        if words.startswith("The ") and len(words.split()) <= LABEL_WORDS:
            offenders.append(f"{path.relative_to(ROOT)}:{line}: {text!r}")
    return offenders


def client_texts() -> dict[Path, list[tuple[int, str]]]:
    texts = {path: string_literals(path.read_text(encoding="utf-8")) for path in sorted(STATIC.rglob("*.js"))}
    for path in sorted(STATIC.rglob("*.html")):
        texts[path] = html_texts(path.read_text(encoding="utf-8"))
    return texts


def test_the_scanner_reads_every_label_form_it_claims_to():
    """The member that makes the guard falsifiable: each form, written the old way, is caught."""
    sample = """
      // The comment is not a label
      el("h3", { text: "The walls" });
      el("button", { text: "The search" });
      run: { returnLabel: "The review" },
      table("The works, one row each.", ["The title", "Year"], rows);
      el("label", { for: "x", text: "The direction to search for" });
      truncation(runs, "The finished ones");
      el("h2", { text: `The ${name}` });
      el("p", { text: "The themes could not be read" });
    """
    caught = [text for _, text in string_literals(sample) if text.startswith("The ") and len(text.split()) <= LABEL_WORDS]
    assert caught == [
        "The walls",
        "The search",
        "The review",
        "The works, one row each.",
        "The title",
        "The direction to search for",
        "The finished ones",
        "The ${}",
    ]


@pytest.mark.parametrize("path", sorted(client_texts()), ids=lambda path: path.name)
def test_no_label_opens_with_the(path):
    texts = client_texts()[path]
    offenders = labels_opening_with_the(path, texts)
    assert not offenders, "Labels are bare nouns and verbs (information-architecture.md § Labels). Rename:\n" + "\n".join(
        offenders
    )


def test_the_client_was_read():
    texts = client_texts()
    assert any(path.name == "app.js" for path in texts), "the client's boot module was not read"
    assert sum(len(found) for found in texts.values()) > 1000, "too few strings were read for this guard to mean anything"
