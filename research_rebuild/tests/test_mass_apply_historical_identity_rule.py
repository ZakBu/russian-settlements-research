from research_rebuild.mass_linkage.apply_historical_identity_rule import typed_source_label_matches


def test_typed_label_matches_unicode_nfkc_yo_and_whitespace_variants():
    assert typed_source_label_matches("  ПОСЁЛОК   Горец ", "поселок", "Горец")
    assert typed_source_label_matches("п. Горец", "посёлок", "Горец")
    assert typed_source_label_matches("поселок И\u0306ошкар-Ола", "поселок", "Йошкар-Ола")


def test_type_prefixes_require_a_complete_prefix_token():
    assert typed_source_label_matches("поселок Горец", "посёлок", "Горец")
    assert not typed_source_label_matches("поселоково Горец", "посёлок", "Горец")
    assert not typed_source_label_matches("пгт Горец", "посёлок", "Горец")
    assert not typed_source_label_matches("поселок Горец", "город", "Горец")
    assert typed_source_label_matches("город Городец", "город", "Городец")


def test_repeated_type_prefix_remains_unresolved():
    assert not typed_source_label_matches("посёлок поселок Горец", "посёлок", "Горец")
    assert not typed_source_label_matches("село с. Горец", "село", "Горец")
