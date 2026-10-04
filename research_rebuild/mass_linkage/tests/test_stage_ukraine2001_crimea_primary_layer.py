from __future__ import annotations

import pytest

from research_rebuild.mass_linkage import stage_ukraine2001_crimea_primary_layer as stage


def test_27_official_present_population_claims_remain_unbound_with_existing_paths_separate():
    observations, mappings, paths, points, _ = stage.build_layer()
    assert len(observations) == len(mappings) == len(paths) == len(points) == 27
    assert int(observations.population_value.sum()) == 845627
    assert observations.source_type.value_counts().to_dict() == {"urban_type_settlement": 16, "city": 11}
    assert observations.population_unit.eq("persons").all()
    assert observations.population_measure.eq("present_population").all()
    assert observations.reference_date.eq("2001-12-05").all()
    assert observations.P1082_literal_date.eq("+2001-00-00T00:00:00Z").all()
    assert observations.P1082_date_precision.eq(9).all()
    assert observations.population_assertion_admitted.all()
    assert not observations.population_to_current_entity_binding_admitted.any()
    assert observations.entity_id.isna().all()
    assert observations.native_2001_OKTMO_raw.isna().all()
    assert not observations.native_2001_code_binding_asserted.any()
    assert observations.population_male.isna().all() and observations.population_female.isna().all()
    assert paths.path_status.str.contains("no 2001-to-2014/2021 continuity assertion").all()
    assert not paths.three_year_same_place_chain_admitted.any()
    assert mappings.mapping_status.eq("already_present_in_frozen_long_baseline_not_newly_admitted").all()
    assert mappings.does_not_admit_2001_identity.all()
    assert points.point_role.eq("accepted_current_2021_representative_point_context_only").all()
    assert not points.historical_2001_coordinate_use_claimed.any()
    assert points.latitude.notna().all() and points.longitude.notna().all()
    assert points.point_origin_sha256.notna().all()


def test_official_workbook_population_change_is_rejected():
    observations = stage.read_csv(stage.PINS["observations"][0])
    observations.loc[0, "population_raw_table5"] = "1"
    with pytest.raises(ValueError, match="raw Table5 population mismatch"):
        stage.replay_workbook(observations)
