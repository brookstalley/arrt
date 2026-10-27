"""The Player's label corpus is the contract's, record for record.

`arrt_player.panel.corpus` holds real records so the label engine and the
preview tool (`tools/label_preview.py`) measure against the words the wall
carries. They are a copy, because the preview tool runs on a Player with no
contract package installed; the contract's `vectors/label-corpus.json` is the
original, and Arrt holds that to the name splits and nationalities it seeds. So
this copy is held to the contract here, and the chain from the seed tables to
the panel is checked at both links.

**The keys are pinned as well as the records.** The artifacts quote the
constants (measurements in `accessibility-spec.md`) and the operator's commands
quote the keys (`--record hokusai`), so each contract key must have its
constant, spelled as the key in capitals.
"""

import json

import pytest
from arrt_contract import root

from arrt_player.panel import corpus

CONTRACT = json.loads((root() / "vectors" / "label-corpus.json").read_text(encoding="utf-8"))["records"]


def test_the_corpus_is_the_contracts():
    assert dict(corpus.CORPUS) == CONTRACT


@pytest.mark.parametrize("key", sorted(CONTRACT))
def test_each_record_has_the_constant_the_artifacts_quote(key):
    constant = key.upper().replace("-", "_")

    assert getattr(corpus, constant, None) == CONTRACT[key], f"{constant} is quoted by the artifacts and no longer holds {key}"


def test_the_corpus_was_read():
    assert len(CONTRACT) >= 8
