"""One current-state entry point; frozen base plus explicit accepted deltas."""
from pathlib import Path

from current_chain_state_20261007 import State

ROOT = Path('/workspace/russian-settlements-research')
E = ROOT / "research_rebuild/evidence"
EARLY_EDGE_EXTRAS = [
    E / "refreshed_name_point_bridge_20261007/accepted_identity_edge_delta.csv",
    E / "large_missing_year_batch_20261007/accepted_identity_edge_delta.csv",
    E / "unique_county_name_bridge_20261007/accepted_identity_edge_delta.csv",
]
EARLY_POINT_EXTRAS = [
    E / "accepted_chain_point_transfer_20261007/accepted_point_use_delta.csv",
    E / "refreshed_name_point_bridge_20261007/accepted_point_use_delta.csv",
    E / "large_missing_year_application_20261007/accepted_point_use_delta.csv",
    E / "unique_county_name_bridge_20261007/accepted_point_use_delta.csv",
    E / "full_chain_missing_points_20261007/point_use_delta.csv",
]
PARTITION_MEMBERS = E / "complete_numbered_partition_batch_20261007/accepted_exclusive_member_projection.csv"
PARTITION_SERIES = E / "complete_numbered_partition_batch_20261007/accepted_three_census_whole_place_series.csv"


def apply_source_namespace_interpretations(state, path):
    """Correct a proved import namespace while preserving original source fields."""
    import pandas as pd
    import xlrd
    from current_chain_state_20261007 import sha

    delta = pd.read_csv(path, dtype=str, keep_default_na=False)
    if len(delta) != 98 or delta.source_record_id.duplicated().any():
        raise ValueError("EAO interpretation must contain exactly the 98 source leaves")
    witness = Path(delta.source_namespace_witness_file.iloc[0])
    expected = delta.source_namespace_witness_sha256.iloc[0]
    if delta.source_namespace_witness_file.nunique() != 1 or delta.source_namespace_witness_sha256.nunique() != 1 or sha(witness) != expected:
        raise ValueError("EAO raw source witness differs")
    book = xlrd.open_workbook(str(witness))
    if book.sheet_by_name("Sheet1").cell_value(0, 0) != "Еврейская АО":
        raise ValueError("EAO actual printed region header differs")
    book.release_resources()
    ids = set(delta.source_record_id)
    mask = state.obs.source_record_id.isin(ids)
    selected = state.obs.loc[mask].set_index("source_record_id")
    if len(selected) != 98 or int(selected.population.sum()) != 62556:
        raise ValueError("EAO selected leaf count or population differs")
    for row in delta.to_dict("records"):
        sid = row["source_record_id"]
        old = selected.loc[sid]
        if (int(old.census_year) != 2002 or old.region_norm != row["region_norm_original_import"]
                or old.source_file != row["source_file_original_import"]
                or row["effective_region_norm"] != "еврейская"
                or row["interpretation_status"] != "checked_source_header_interpretation_accepted"
                or row["source_population_modified"].lower() != "false"
                or row["raw_source_metadata_overwritten"].lower() != "false"):
            raise ValueError("Source namespace interpretation is outside the proved import subset")
    state.obs["region_norm_original_import"] = state.obs.region_norm
    state.obs["source_namespace_interpretation_status"] = "original_import_namespace"
    state.obs.loc[mask, "region_norm"] = "еврейская"
    state.obs.loc[mask, "source_namespace_interpretation_status"] = "checked_source_header_interpretation_accepted"
    state.by_id = state.obs.set_index("source_record_id", drop=False)
    state.inputs.extend([path, witness])
    return state


def load(stage=56):
    """Replay a fixed stage, so earlier applications remain reproducible.

    1: county rule + 99 GeoKLADR uses; 2: source brackets;
    3: Svetly identity and point supersession; 4: Moscow Troitskoye point;
    5: recovered complete source-cell ledgers; 6: printed type variants;
    7: source-context links permitting printed type variants;
    8: source-backed whole-locality points in existing complete chains;
    9: remaining sourceable points and four context-resolved proximity links.
    10: exact station-name designator aliases with printed county support.
    11: one source-region-resolved point on an existing complete identity.
    12: compatible native printed type prefixes, two complete trajectories.
    13: source-backed former names, with railway-feature candidates withheld.
    14: selected secondary 2010 XLS rows, two-sided accepted source context.
    15: eight complete triplets with printed historical county and source context.
    16: native missing-year links and independently sourced external own points.
    17: restricted name variants with unique independent own points within 5 km.
    18: neutral county-caption variants with uniquely bound historical own points.
    19: native-code and source-bound own Wikidata points for remaining current NPs.
    20: native 2002 source subdivisions mapped through accepted census anchors.
    21: documented former names and native printed urban or rural source context.
    22: resolved own locality points and source-bound follow-up histories.
    23: exact census-value bindings with printed or flanking-source county context.
    24: explicit rejection and recovery of contradicted modern provider points.
    25: own settlement-code/context bindings including populated railway localities.
    26: unique nearby own-point competitors, native Moscow bindings and modern mispoint recovery.
    27: printed standalone urban type suffixes, source-bound rename and explicit Dubrovka mispoint recovery.
    28: source-bound urban-to-rural native context for Nagorny, Sibirsky ZATO and Podgorny.
    29: refreshed two-sided source-context bindings and own points for 434 native 2010 rows.
    30: source-bound large native context follow-up and Shafranovo receiving-core point recovery.
    31: source-bound Chechnya printed-name variants, dated population witnesses and native county contexts.
    32: individually sourcecounty-resolved homonyms; no municipal point assignment to settlements.
    33: own-code/date-bound cached 2002 population witnesses with native source contexts.
    34: source-bound dated-count follow-up and explicit rejection of a contradicted historical Geo point.
    35: literal own-name aliases with native historical county and independently coded current points.
    36: printed county-qualified Tolka names and Seyakha aliases; source-derived stale county captions retained separately.
    37: source-bound native 2002 matches with narrow aggregate-caption suffix normalization for county context.
    38: literal native 2010 source county/urban-role bindings for existing 2002–2021 own-point components.
    39: native 2002 own-source aliases and current namesake exclusions, composed on actual stage38.
    40: literal whole-region unique native names with accepted 2010–2021 own-point continuity.
    41: source-bound declining native 2010 rows and literal railway locality descriptors.
    42: whole-region name/type uniqueness with other-class rivals retained explicitly.
    43: Aramil locality identity with independent own point and explicitly ambiguous publisher OKATO.
    44: source-bound own-code/classifier points for remaining native graph-compatible histories.
    45: whole-region literal native 2010 name/type bindings with source and all namesake controls.
    46: cached own 2010 census witnesses bound to five literal native source rows.
    47: uncached own 2010 census witnesses bound to two literal native source rows.
    48: accepted former-locality own points and native PGT two-census continuity, without invented current counts.
    49: literal source-bound native links for the largest remaining 2010 locality records.
    50: finite native histories from literal source-county brackets and own locality points.
    51: exact EAO source-header namespace interpretation and native rural continuity links.
    52: source-bound rural type and literal ownership-designator variants on current two-year components.
    53: mass rural singleton histories with printed county hierarchy and all physical competitors retained.
    54: cached own-name aliases bound to six native old census records.
    55: Donskoye native rural/PGT/rural continuity; complete parts and direct events remain separate report axes.
    56: accepted component literal-name variants bound to 53 native2010 source rows.
    """
    if not isinstance(stage, int) or not 1 <= stage <= 56:
        raise ValueError(f"Unsupported working stage: {stage}; implemented stages are 1–56")
    state = State()
    state.add_deltas(EARLY_EDGE_EXTRAS, EARLY_POINT_EXTRAS)
    if stage >= 2:
        state.add_deltas([E/"bracketed_2010_county_application_20261007/accepted_identity_edge_delta.csv"], [E/"bracketed_2010_county_application_20261007/accepted_point_use_delta.csv"])
    if stage >= 3:
        state.reject_point_uses(E/"large_residual_temporal_batch_20261007/point_rejections.csv")
        state.add_deltas([E/"large_residual_temporal_application_20261007/accepted_identity_edge_delta.csv"], [E/"large_residual_temporal_batch_20261007/reviewed_point_supersession_delta.csv"])
    if stage >= 4:
        state.add_deltas(point_paths=[E/"full_chain_missing_points_20261007/large_moscow_troitskoe_point_use_delta.csv"])
    if stage >= 5:
        state.add_deltas([E/"bracketed_2010_recovered_source_application_20261007/accepted_identity_edge_delta.csv"], [E/"bracketed_2010_recovered_source_application_20261007/accepted_point_use_delta.csv"])
    if stage >= 6:
        state.add_deltas([E/"county_type_change_application_20261007/accepted_identity_edge_delta.csv"], [E/"county_type_change_application_20261007/accepted_point_use_delta.csv"])
    if stage >= 7:
        state.add_deltas([E/"bracket_type_variant_application_20261007/accepted_identity_edge_delta.csv"], [E/"bracket_type_variant_application_20261007/accepted_point_use_delta.csv"])
    if stage >= 8:
        state.add_deltas(point_paths=[E/"top30_full_chain_points_application_20261007/accepted_point_use_delta.csv"])
    if stage >= 9:
        state.add_deltas([E/"remaining_points_and_reviewed_proximity_application_20261007/accepted_identity_edge_delta.csv"], [E/"remaining_points_and_reviewed_proximity_application_20261007/accepted_point_use_delta.csv"])
    if stage >= 10:
        state.add_deltas([E/"station_name_alias_application_20261007/accepted_identity_edge_delta.csv"], [E/"station_name_alias_application_20261007/accepted_point_use_delta.csv"])
    if stage >= 11:
        state.add_deltas(point_paths=[E/"auxiliary_observed_years_application_20261007/accepted_point_use_delta.csv"])
    if stage >= 12:
        state.add_deltas([E/"native_type_prefix_application_20261007/accepted_identity_edge_delta.csv"], [E/"native_type_prefix_application_20261007/accepted_point_use_delta.csv"])
    if stage >= 13:
        state.add_deltas([E/"wikidata_former_name_application_20261007/accepted_identity_edge_delta.csv"], [E/"wikidata_former_name_application_20261007/accepted_point_use_delta.csv"])
    if stage >= 14:
        state.add_deltas([E/"secondary_2010_county_context_application_20261007/accepted_identity_edge_delta.csv"], [E/"secondary_2010_county_context_application_20261007/accepted_point_use_delta.csv"])
    if stage >= 15:
        state.add_deltas([E/"secondary_2010_new_triplets_application_20261007/accepted_identity_edge_delta.csv"], [E/"secondary_2010_new_triplets_application_20261007/accepted_point_use_delta.csv"])
    if stage >= 16:
        state.add_deltas([E/"own_year_and_corrected_points_application_20261007/accepted_identity_edge_delta.csv"], [E/"own_year_and_corrected_points_application_20261007/accepted_point_use_delta.csv"])
    if stage >= 17:
        state.add_deltas([E/"near_name_coordinate_application_20261007/accepted_identity_edge_delta.csv"], [E/"near_name_coordinate_application_20261007/accepted_point_use_delta.csv"])
    if stage >= 18:
        state.add_deltas([E/"neutral_county_point_application_20261007/accepted_identity_edge_delta.csv"], [E/"neutral_county_point_application_20261007/accepted_point_use_delta.csv"])
    if stage >= 19:
        state.add_deltas(point_paths=[E/"current_unpointed_own_wiki_mass_application_20261007/accepted_point_use_delta.csv"])
    if stage >= 20:
        state.add_deltas([E/"mass_residual_native_context_application_20261007/accepted_identity_edge_delta.csv"], [E/"mass_residual_native_context_application_20261007/accepted_point_use_delta.csv"])
    if stage >= 21:
        state.add_deltas([E/"remaining_large_native_triplets_application_20261007/accepted_identity_edge_delta.csv"], [E/"remaining_large_native_triplets_application_20261007/accepted_point_use_delta.csv"])
    if stage >= 22:
        state.add_deltas(point_paths=[E/"remaining_large_own_points_followup_application_20261007/accepted_point_use_delta.csv"])
    if stage >= 23:
        state.add_deltas([E/"old_native_from_existing_secondary_binding_application_20261007/accepted_identity_edge_delta.csv"], [E/"old_native_from_existing_secondary_binding_application_20261007/accepted_point_use_delta.csv"])
    if stage >= 24:
        state.reject_point_uses(E/"full3_conflicting_modern_point_recovery_application_20261007/accepted_point_rejection_delta.csv")
        state.add_deltas(point_paths=[E/"full3_conflicting_modern_point_recovery_application_20261007/accepted_point_use_delta.csv"])
    if stage >= 25:
        state.add_deltas([E/"old_year_remaining_mass_rule_application_20261008/accepted_identity_edge_delta.csv"], [E/"old_year_remaining_mass_rule_application_20261008/accepted_point_use_delta.csv"])
    if stage >= 26:
        state.add_deltas([E/"old_year_spatial_competitor_resolution_application_20261008/accepted_identity_edge_delta.csv", E/"moscow_three_stable_native_application_20261008/accepted_identity_edge_delta.csv"], [E/"old_year_spatial_competitor_resolution_application_20261008/accepted_point_use_delta.csv", E/"moscow_three_stable_native_application_20261008/accepted_point_use_delta.csv"])
        state.reject_point_uses(E/"current_large_component_point_recovery_application_20261008/accepted_point_rejection_delta.csv")
        state.add_deltas(point_paths=[E/"current_large_component_point_recovery_application_20261008/accepted_point_use_delta.csv"])
    if stage >= 27:
        state.reject_point_uses(E/"large_native_suffix_and_former_name_application_20261008/accepted_point_rejection_delta.csv")
        state.add_deltas([E/"large_native_suffix_and_former_name_application_20261008/accepted_identity_edge_delta.csv"], [E/"large_native_suffix_and_former_name_application_20261008/accepted_point_use_delta.csv"])
    if stage >= 28:
        state.add_deltas([E/"native_alias_remaining_mass_20261008/accepted_identity_edge_delta.csv"], [E/"native_alias_remaining_mass_20261008/accepted_point_use_delta.csv"])
    if stage >= 29:
        state.add_deltas([E/"cached_wikipedia_history_mass_20261008/refreshed_2010_context/application/accepted_identity_edge_delta.csv"], [E/"cached_wikipedia_history_mass_20261008/refreshed_2010_context/application/accepted_point_use_delta.csv"])
    if stage >= 30:
        state.reject_point_uses(E/"native_alias_remaining_mass_20261008/followup/accepted_point_rejection_delta.csv")
        state.add_deltas([E/"native_alias_remaining_mass_20261008/followup/accepted_identity_edge_delta.csv"], [E/"native_alias_remaining_mass_20261008/followup/accepted_point_use_delta.csv"])
    if stage >= 31:
        state.add_deltas([E/"chechnya_native_mass_20261008/accepted_identity_edge_delta.csv"], [E/"chechnya_native_mass_20261008/accepted_point_use_delta.csv"])
    if stage >= 32:
        state.add_deltas([E/"individual_sourcecounty_homonym_application_20261008/accepted_identity_edge_delta.csv"], [E/"individual_sourcecounty_homonym_application_20261008/accepted_point_use_delta.csv"])
    if stage >= 33:
        state.add_deltas([E/"native_alias_remaining_mass_20261008/nationwide_dated_count_native_bindings/accepted_identity_edge_delta.csv"], [E/"native_alias_remaining_mass_20261008/nationwide_dated_count_native_bindings/accepted_point_use_delta.csv"])
    if stage >= 34:
        state.reject_point_uses(E/"native_alias_remaining_mass_20261008/nationwide_dated_count_native_bindings_followup/accepted_point_rejection_delta.csv")
        state.add_deltas([E/"native_alias_remaining_mass_20261008/nationwide_dated_count_native_bindings_followup/accepted_identity_edge_delta.csv"], [E/"native_alias_remaining_mass_20261008/nationwide_dated_count_native_bindings_followup/accepted_point_use_delta.csv"])
    if stage >= 35:
        state.add_deltas([E/"native_alias_remaining_mass_20261008/native_missing2002_alias_bindings/accepted_identity_edge_delta.csv"], [E/"native_alias_remaining_mass_20261008/native_missing2002_alias_bindings/accepted_point_use_delta.csv"])
    if stage >= 36:
        state.add_deltas([E/"absorbed_native_event_mass_20261008/purpe_sourcecounty_native_application/accepted_identity_edge_delta.csv"], [E/"absorbed_native_event_mass_20261008/purpe_sourcecounty_native_application/accepted_point_use_delta.csv"])
    if stage >= 37:
        state.add_deltas([E/"native_alias_remaining_mass_20261008/all_components_native2002_bindings/accepted_identity_edge_delta.csv"], [E/"native_alias_remaining_mass_20261008/all_components_native2002_bindings/accepted_point_use_delta.csv"])
    if stage >= 38:
        state.add_deltas([E/"native_missing2010_all_components_20261008/accepted_identity_edge_delta.csv.gz"], [E/"native_missing2010_all_components_20261008/accepted_point_use_delta.csv"])
    if stage >= 39:
        state.add_deltas([E/"native_alias_remaining_mass_20261008/all_cached_native2002_context_followup/accepted_identity_edge_delta.csv"], [E/"native_alias_remaining_mass_20261008/all_cached_native2002_context_followup/accepted_point_use_delta.csv"])
    if stage >= 40:
        state.add_deltas([E/"native_alias_remaining_mass_20261008/existing_ownpoint_native02_mass/accepted_identity_edge_delta.csv"], [E/"native_alias_remaining_mass_20261008/existing_ownpoint_native02_mass/accepted_point_use_delta.csv"])
    if stage >= 41:
        state.add_deltas([E/"native_missing2010_residual_context_20261008/accepted_identity_edge_delta.csv.gz"], [E/"native_missing2010_residual_context_20261008/accepted_point_use_delta.csv.gz"])
    if stage >= 42:
        state.add_deltas([E/"native_alias_remaining_mass_20261008/whole_region_type_unique_followup/accepted_identity_edge_delta.csv"], [E/"native_alias_remaining_mass_20261008/whole_region_type_unique_followup/accepted_point_use_delta.csv"])
    if stage >= 43:
        state.add_deltas([E/"native_alias_remaining_mass_20261008/aramil_independent_ownpoint_supplement/accepted_identity_edge_delta.csv"], [E/"native_alias_remaining_mass_20261008/aramil_independent_ownpoint_supplement/accepted_point_use_delta.csv"])
    if stage >= 44:
        state.add_deltas([E/"ownlegacy_ownpoint_route_gap_mass_20261008/accepted_identity_edge_delta.csv"], [E/"ownlegacy_ownpoint_route_gap_mass_20261008/accepted_point_use_delta.csv"])
    if stage >= 45:
        state.add_deltas([E/"native2010_whole_region_name_type_mass_20261008/accepted_identity_edge_delta.csv.gz"], [E/"native2010_whole_region_name_type_mass_20261008/accepted_point_use_delta.csv.gz"])
    if stage >= 46:
        state.add_deltas([E/"cached_missing2010_dated_source_mass_20261008/accepted_identity_edge_delta.csv"], [E/"cached_missing2010_dated_source_mass_20261008/accepted_point_use_delta.csv"])
    if stage >= 47:
        state.add_deltas([E/"uncached_missing2010_dated_source_mass_20261008/accepted_identity_edge_delta.csv"], [E/"uncached_missing2010_dated_source_mass_20261008/accepted_point_use_delta.csv"])
    if stage >= 48:
        state.add_deltas([E/"accepted_lifecycle_ownpoint_application_20261008/accepted_identity_edge_delta.csv"], [E/"accepted_lifecycle_ownpoint_application_20261008/accepted_point_use_delta.csv"])
    if stage >= 49:
        state.add_deltas([E/"large2010_residual_native2002_followup_20261008/accepted_identity_edge_delta.csv"], [E/"large2010_residual_native2002_followup_20261008/accepted_point_use_delta.csv"])
    if stage >= 50:
        state.add_deltas([E/"native2010_remaining_county_rule_mass_20261008/accepted_identity_edge_delta.csv.gz"], [E/"native2010_remaining_county_rule_mass_20261008/accepted_point_use_delta.csv.gz"])
    if stage >= 51:
        apply_source_namespace_interpretations(state, E/"eaoregion_source_namespace_mass_20261008/source_namespace_interpretation_delta.csv")
        state.add_deltas([E/"eaoregion_source_namespace_mass_20261008/accepted_identity_edge_delta.csv"], [E/"eaoregion_source_namespace_mass_20261008/accepted_point_use_delta.csv"])
    if stage >= 52:
        state.add_deltas([E/"native_rural_type_alias_mass_20261008/accepted_identity_edge_delta.csv.gz"], [E/"native_rural_type_alias_mass_20261008/accepted_point_use_delta.csv.gz"])
    if stage >= 53:
        state.add_deltas([E/"native_singleton_rural_mass_20261008/accepted_identity_edge_delta.csv.gz"], [E/"native_singleton_rural_mass_20261008/accepted_point_use_delta.csv.gz"])
    if stage >= 54:
        state.add_deltas([E/"cached_historical_name_alias_mass_20261008/accepted_identity_edge_delta.csv.gz"], [E/"cached_historical_name_alias_mass_20261008/accepted_point_use_delta.csv.gz"])
    if stage >= 55:
        state.add_deltas([E/"absorbed_remaining2010_direct_mass_20261008/accepted_separate_native_identity_edge_delta.csv"], [E/"absorbed_remaining2010_direct_mass_20261008/accepted_separate_native_point_use_delta.csv"])
    if stage >= 56:
        state.add_deltas([E/"current_component_name_alias_mass_20261008/accepted_identity_edge_delta.csv.gz"], [E/"current_component_name_alias_mass_20261008/accepted_point_use_delta.csv.gz"])
    return state
