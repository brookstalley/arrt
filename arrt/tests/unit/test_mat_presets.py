"""The one-press mats obey the same bounds every mat does (#91).

Parametrised over `MAT_PRESETS` itself, so a preset added later is held to the
floor and the ceiling the day it is added.
"""

import pytest

from arrt.library.acquisition.color import parse_hex, rgb_to_lab
from arrt.library.acquisition.mat import CORPUS_MAX_LIGHTNESS, MAT_LIGHTNESS_FLOOR, MAT_PRESETS, below_the_floor


def test_there_are_presets():
    assert MAT_PRESETS


@pytest.mark.parametrize("preset", MAT_PRESETS, ids=lambda p: p.key)
def test_a_preset_clears_the_floor_and_sits_under_the_corpus_bar(preset):
    """Under the requirement's bar, `CORPUS_MAX_LIGHTNESS`, not under the
    derivation's tighter ceiling: `#6b6b6b` is the corpus's lightest mat itself,
    at L* 45.22, which that ceiling quotes rounded down to 45.2."""
    lightness = rgb_to_lab(parse_hex(preset.hex_rgb)).l
    assert not below_the_floor(preset.hex_rgb)
    assert MAT_LIGHTNESS_FLOOR <= lightness <= CORPUS_MAX_LIGHTNESS


def test_preset_keys_are_distinct_and_not_the_derivations():
    keys = [preset.key for preset in MAT_PRESETS]
    assert len(keys) == len(set(keys))
    # `derived` names the derivation on the agent's tool, beside the presets.
    assert "derived" not in keys
