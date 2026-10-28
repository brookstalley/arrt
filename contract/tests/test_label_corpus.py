"""The label corpus is label text a server may send.

`vectors/label-corpus.json` is what every renderer measures itself against, and
what the server's suite holds to the tables it seeds names and nationalities
from. A record that no server could send would measure a renderer against a
wall that cannot exist, so each one, with its absent keys as null, is a label
block the manifest's schema accepts.
"""

import json

import pytest
from jsonschema import Draft202012Validator

from arrt_contract import registry, root, schema

CORPUS = json.loads((root() / "vectors" / "label-corpus.json").read_text(encoding="utf-8"))["records"]
LABEL = {"$ref": "https://github.com/brookstalley/arrt/contract/schemas/manifest.v2.schema.json#/$defs/label"}
KEYS = schema("schemas/manifest.v2.schema.json")["$defs"]["label"]["properties"]

#: Records that break the schema on purpose, each with the key it breaks and why.
#: `anonymous` has no title, which a server never sends (major 2 requires a string,
#: and Arrt writes the catalogue's title); it is kept because measurements the
#: accessibility spec quotes were taken against it, until #385 decides what the
#: untitled case is on the wire.
KNOWN_UNSENDABLE = {"anonymous": "title"}


@pytest.mark.parametrize("key", sorted(CORPUS))
def test_each_record_is_a_label_block_with_its_nulls_left_out(key):
    record = CORPUS[key]

    assert set(record) <= set(KEYS), sorted(set(record) - set(KEYS))
    whole = {name: record.get(name) for name in KEYS}
    errors = [list(error.absolute_path) for error in Draft202012Validator(LABEL, registry=registry()).iter_errors(whole)]
    assert errors == ([[KNOWN_UNSENDABLE[key]]] if key in KNOWN_UNSENDABLE else [])


def test_the_corpus_was_read():
    assert len(CORPUS) >= 8
