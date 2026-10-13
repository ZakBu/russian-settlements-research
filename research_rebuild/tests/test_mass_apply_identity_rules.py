from types import SimpleNamespace

from research_rebuild.mass_linkage.apply_identity_rules import (
    _candidate_graph_outcome,
    _pair_competitors,
    _screen_candidate_pair,
    _traceable_district,
    _verified_direct_context,
)
from research_rebuild.mass_linkage.candidate_graph_checks import YearConstrainedUnionFind


def node(year, *, name="березовка", place_type="деревня", region="тверская",
         district="калининский", municipality="", aggregate=False,
         legacy_conflict=False, legacy_collision=False, grain=None,
         component=None, district_raw=None):
    return SimpleNamespace(
        census_year=year, region_norm=region, type_norm=place_type,
        district_norm=district, district_raw=district if district_raw is None else district_raw, municipality_raw=municipality,
        municipality_norm=municipality, aggregate=aggregate,
        legacy_identity_conflict=legacy_conflict,
        legacy_same_year_collision=legacy_collision,
        entity_grain_status=grain,
        source_selection_component=component or ("karelia_2010_primary_r5" if year == 2010 else None),
    )


def meta(year, *, name="березовка", context_source=True, additive=True,
         scope="settlement"):
    return {
        "name_norm": name, "is_additive_settlement_record": additive,
        "population_scope": scope, "source_file": f"{year}.xls",
        "source_sha256": "a" * 64 if context_source else "",
        "source_sheet": "Sheet1" if context_source else "",
        "source_row": 12 if context_source else None, "source_locator": None,
    }


def candidate(left, right, *, family="region_district_name_type", kind_values=None):
    kv = {"region_norm": "тверская", "name_norm": "березовка", "type_norm": "деревня"}
    if family == "region_district_name_type":
        kv["district_norm"] = "калининский"
    if kind_values:
        kv.update(kind_values)
    return {
        "from_id": left, "to_id": right, "year_from": 2002, "year_to": 2010,
        "families": {family}, "candidate_ids": {"CAND-x"},
        "key_values_by_family": {family: kv}, "candidate_unique": True,
        "federal_aggregate_block": False, "legacy_identity_conflict_present": False,
        "legacy_same_year_collision_present": False,
        "legacy_ordinal_route_present_not_acceptance_signal": False,
        "region_mismatch": False, "type_change_or_mismatch": False,
    }


def test_district_rule_requires_traceable_parent_context_on_both_rows_and_normalizes_suffix():
    pair = candidate("a", "b")
    nodes = {"a": node(2002), "b": node(2010, district_raw="Калининский район")}
    metadata = {"a": meta(2002), "b": meta(2010)}
    rule, reasons = _screen_candidate_pair(pair, nodes, metadata, {}, set())
    assert rule == "exact_region_district_name_type_with_traceable_context"
    assert reasons == []

    nodes["b"].source_selection_component = "karelia_2010_primary_r5"
    metadata["b"]["raw_explicit_district_values"] = []
    rule, reasons = _screen_candidate_pair(pair, nodes, metadata, {}, set())
    assert rule == "exact_region_district_name_type_with_traceable_context"
    assert reasons == []

    nodes["b"].source_selection_component = "karelia_2010_primary_r5"
    metadata["b"]["raw_explicit_district_values"] = []
    rule, reasons = _screen_candidate_pair(pair, nodes, metadata, {}, set())
    assert rule == "exact_region_district_name_type_with_traceable_context"
    assert reasons == []

    metadata["b"] = meta(2010, context_source=False)
    rule, reasons = _screen_candidate_pair(pair, nodes, metadata, {}, set())
    assert rule is None
    assert "source_origin_or_row_locator_not_traceable" in reasons


def test_2021_mun_upper_is_a_matching_context_not_a_historical_boundary():
    pair = candidate("a", "b")
    nodes = {"a": node(2010), "b": node(2021, district="гиагинский", municipality="Гиагинский муниципальный район")}
    nodes["a"] = node(2010, district="гиагинский")
    pair = candidate("a", "b", kind_values={"district_norm": "гиагинский"})
    nodes["b"].district_raw = "Гиагинский муниципальный район"
    metadata = {"a": meta(2010), "b": meta(2021)}
    rule, reasons = _screen_candidate_pair(pair, nodes, metadata, {}, set())
    assert rule == "exact_region_district_name_type_with_traceable_context"
    assert reasons == []
    # The rule output is identity-only; the 2021 parent field is never relabelled
    # as a historical district by this test or by the application.


def test_2010_row_cell_context_is_required_unless_primary_context_was_reviewed():
    pair = candidate("a", "b", kind_values={"district_norm": "гиагинский"})
    nodes = {"a": node(2002, district="гиагинский"), "b": node(2010, district="гиагинский", component="unreviewed_legacy_selection",
                                         district_raw="Гиагинский район")}
    metadata = {"a": meta(2002), "b": meta(2010)}
    rule, reasons = _screen_candidate_pair(pair, nodes, metadata, {}, set())
    assert rule is None
    assert "no_scoped_rule_applies_or_parent_context_untraceable" in reasons

    metadata["b"]["raw_explicit_district_values"] = ["Гиагинский"]
    rule, reasons = _screen_candidate_pair(pair, nodes, metadata, {}, set())
    assert rule == "exact_region_district_name_type_with_traceable_context"
    assert reasons == []


def test_direct_2010_context_requires_same_row_label_population_region_and_nonblank_district():
    profile = {"name_cols": [4], "district_cols": [3], "population_col": 5, "region_col": 2}
    selected = {"source_name_raw": "пгт Крестцы", "settlement_name": "Крестцы",
                "population": 2200, "region_raw": "новгородская"}
    # The documented NW row 9323 has a blank D cell. An earlier Батецкий
    # label must not be inherited into this exact settlement row.
    raw_krestsy = [9322, "Новгородская область", "Новгородская область", "",
                   "пгт Крестцы", 2200]
    direct, error = _verified_direct_context(selected, profile, raw_krestsy)
    assert direct == [] and error is None
    selected["raw_explicit_district_values"] = direct
    assert not _traceable_district(node(2010, district="батецкий", district_raw="Батецкий", component="unreviewed"),
                                   {**meta(2010), **selected}, "батецкий")

    row = [1170, "Краснодарский край", "Славянский район", "Славянский район",
           "станица Петровская", 1000]
    profile = {"name_cols": [4], "district_cols": [2, 3], "population_col": 5,
               "region_constant_cell": [2, 0]}
    selected = {"source_name_raw": "станица Петровская", "population": 1000,
                "region_raw": "краснодарский"}
    direct, error = _verified_direct_context(selected, profile, row, "Краснодарский край")
    assert direct == ["Славянский район", "Славянский район"] and error is None

    bad_label = dict(selected, source_name_raw="станица Петровская иная")
    assert _verified_direct_context(bad_label, profile, row, "Краснодарский край")[1] == "raw_label_mismatch"
    bad_pop = dict(selected, population=999)
    assert _verified_direct_context(bad_pop, profile, row, "Краснодарский край")[1] == "raw_population_mismatch"
    bad_region = dict(selected, region_raw="адыгея")
    assert _verified_direct_context(bad_region, profile, row, "Краснодарский край")[1] == "raw_region_mismatch"

def test_city_rule_is_city_only_and_does_not_waive_other_grain_screens():
    pair = candidate("a", "b", family="region_name_type")
    pair["key_values_by_family"]["region_name_type"]["type_norm"] = "город"
    nodes = {"a": node(2002, place_type="город", district=""),
             "b": node(2010, place_type="город", district="")}
    metadata = {"a": meta(2002), "b": meta(2010)}
    rule, reasons = _screen_candidate_pair(pair, nodes, metadata, {}, set())
    assert rule == "unique_exact_region_city_name_type"
    assert reasons == []

    nodes["b"] = node(2010, place_type="пгт", district="")
    rule, reasons = _screen_candidate_pair(pair, nodes, metadata, {}, set())
    assert rule is None
    assert "type_mismatch_or_missing" in reasons

    nodes["b"] = node(2010, place_type="город", district="", aggregate=True)
    rule, reasons = _screen_candidate_pair(pair, nodes, metadata, {}, set())
    assert rule is None
    assert "aggregate_or_nonsettlement_scope" in reasons


def test_ambiguity_competitors_and_legacy_flags_are_conservative_holds():
    pair = candidate("a", "b")
    nodes = {"a": node(2002), "b": node(2010, legacy_conflict=True)}
    metadata = {"a": meta(2002), "b": meta(2010)}
    rule, reasons = _screen_candidate_pair(pair, nodes, metadata,
                                           {"region_district_name_type": {"a"}},
                                           {"region_district_name_type"})
    assert rule is None
    assert "district_key_ambiguous_competing_group" in reasons
    assert "competing_endpoint_alternative_within_applicable_key_family" in reasons
    assert "unresolved_legacy_identity_or_same_year_flag" in reasons


def test_weaker_region_name_ambiguity_does_not_veto_unique_traceable_district_rule():
    pair = candidate("a", "b")
    # The broad region+name+type family can have homonyms in different
    # districts; exact, source-traceable district keys disambiguate this pair.
    pair["families"].add("region_name_type")
    pair["key_values_by_family"]["region_name_type"] = {
        "region_norm": "тверская", "name_norm": "березовка", "type_norm": "деревня",
    }
    nodes = {"a": node(2002), "b": node(2010)}
    metadata = {"a": meta(2002), "b": meta(2010)}
    rule, reasons = _screen_candidate_pair(pair, nodes, metadata,
                                           {"region_name_type": {"a", "b"}},
                                           {"region_name_type"})
    assert rule == "exact_region_district_name_type_with_traceable_context"
    assert reasons == []


def test_legacy_ordinal_route_is_not_an_acceptance_signal_but_not_a_veto():
    pair = candidate("a", "b")
    pair["legacy_ordinal_route_present_not_acceptance_signal"] = True
    nodes = {"a": node(2002), "b": node(2010)}
    metadata = {"a": meta(2002), "b": meta(2010)}
    rule, reasons = _screen_candidate_pair(pair, nodes, metadata, {}, set())
    assert rule == "exact_region_district_name_type_with_traceable_context"
    assert reasons == []


def test_pair_competitors_are_counted_after_family_pair_dedup_and_graph_blocks_year_overlap():
    first = candidate("a", "b")
    duplicate_family = candidate("a", "b", family="region_name_type")
    other = candidate("a", "c")
    pairs = {("a", "b"): first, ("a", "c"): other}
    # A duplicate support family for the same pair does not manufacture a
    # second endpoint alternative; a genuinely distinct counterpart does.
    nodes = {"a": node(2002), "b": node(2010), "c": node(2010)}
    result = _pair_competitors(pairs, nodes)
    assert set(result) == {("a", "b"), ("a", "c")}
    assert result[("a", "b")] == {"region_district_name_type"}
    assert duplicate_family["to_id"] == first["to_id"]

    graph_nodes = {"a": node(2002), "b": node(2010), "c": node(2002)}
    graph = YearConstrainedUnionFind(graph_nodes)
    assert graph.add_edge("a", "b")[0] == "proposed_component_merge"
    status, overlap, _, _ = graph.add_edge("b", "c")
    assert status == "blocked_same_year_component_collision"
    assert overlap == (2002,)


def test_baseline_pair_is_corroborated_without_duplicate_admission_and_transitive_pair_is_labelled():
    graph_nodes = {"a": node(2002), "b": node(2010), "c": node(2021)}
    graph = YearConstrainedUnionFind(graph_nodes)
    graph.initialize_edges([("a", "b")])
    status, overlap, effect = _candidate_graph_outcome(("a", "b"), graph, {("a", "b")})
    assert (status, overlap, effect) == (
        "corroborates_reviewed_baseline_pair", (), "existing_baseline_pair_no_new_edge"
    )
    graph.add_edge("b", "c")
    status, _, effect = _candidate_graph_outcome(("a", "c"), graph, {("a", "b")})
    assert status == "already_connected"
    assert effect == "redundant_graph_connectivity_effect"
