"""One current-state entry point; frozen base plus explicit accepted deltas."""
from pathlib import Path

from current_chain_state_20261007 import State

ROOT = Path(__file__).resolve().parents[2]
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


def load(stage=14):
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
    """
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
    return state
