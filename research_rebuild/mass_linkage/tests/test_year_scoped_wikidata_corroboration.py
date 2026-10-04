"""Regression checks for exact year-scoped name/ADM1 key matching."""
from collections import Counter
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_rebuild.mass_linkage.stage_year_scoped_wikidata_corroboration_mass_v2_20261004 import (
    exact_name_region_pair,
    norm,
    year_scoped_key_unique,
)


def test_official_region_suffix_is_not_a_cross_region_match():
    # Raw display labels can differ while the selected-source canonical region
    # token agrees; an actually different canonical province remains a reject.
    assert exact_name_region_pair('Урваново', 'Урваново', 'владимирская', 'Владимирская')
    assert not exact_name_region_pair('Урваново', 'Урваново', 'владимирская', 'ивановская')


def test_same_name_is_unique_per_year_not_across_years():
    counts = Counter({(2002, 'урваново', 'владимирская'): 1,
                      (2010, 'урваново', 'владимирская'): 1,
                      (2021, 'урваново', 'владимирская'): 1})
    assert year_scoped_key_unique(counts, 2002, 'Урваново', 'Владимирская')
    assert year_scoped_key_unique(counts, 2010, 'Урваново', 'Владимирская')
    counts[(2002, 'урваново', 'владимирская')] = 2
    assert not year_scoped_key_unique(counts, 2002, 'Урваново', 'Владимирская')
    assert year_scoped_key_unique(counts, 2010, 'Урваново', 'Владимирская')


def test_exact_locality_name_normalization_does_not_strip_name_prefixes():
    # A real locality beginning with this token must remain unchanged; type
    # prefixes are handled only by the authoritative source parser upstream.
    assert norm('Городец') == 'городец'
    assert norm('ё') == 'е'


def test_missing_region_stays_unknown():
    assert not exact_name_region_pair('Городец', 'Городец', None, 'нижегородская')
    assert not year_scoped_key_unique({}, 2002, 'Городец', None)
