from __future__ import annotations

import pandas as pd
import pytest

from research_rebuild.mass_linkage import stage_large_current4_official_primary as stage


def test_reviewed_five_official_observations_seven_links_and_aliases_are_staged_separately():
    obs, links, mappings, points, projection, policy = stage.build_layer()
    assert len(obs) == 5
    values = dict(zip(obs.source_record_id, obs.population_value.astype(int)))
    assert values == {
        "ROSSTAT2002:T4:01-04:r4338": 29533,
        "ROSSTAT2010:T5:p33:l120": 26359,
        "ROSSTAT2002:T4:01-04:r1212": 23873,
        "ROSSTAT2010:T5:p36:l82": 21774,
        "ROSSTAT2010:T5:p199:l277": 18522,
    }
    assert len(links) == 7
    assert set(links.admission_status) == {"root_approved_scoped_physical_continuity_for_integration"}
    assert len(mappings) == 7
    assert set(mappings.mapping_id).issubset({f"same-census-source-map:{i:02d}" for i in range(1, 8)})
    assert not mappings.identity_merge_performed.any()
    assert not mappings.population_replacement_performed.any()
    assert len(points) == 4
    assert len(projection) == 2
    assert int(projection.child_population_value.sum()) == 29533
    assert not projection.child_counted_in_addition_to_parent.any()
    assert policy["child_parts_counted_in_addition_to_parent"] is False
    assert not obs.historical_provider_binding_asserted.any()
    assert not obs.historical_coordinate_asserted.any()
    assert not obs.boundary_comparability_asserted.any()
    assert obs.latitude.notna().all() and obs.longitude.notna().all()
    assert obs.point_origin_sha256.notna().all()
    kalinin = obs[obs.settlement_name.eq("Калининец")]
    assert set(kalinin.qid_context) == {"Q1125953"}
    assert not kalinin.qid_native_identifier_binding_asserted.any()
    assert not obs[obs.settlement_name.eq("Власиха")].observation_year.eq(2002).any()


def test_source_row_replay_rejects_changed_official_count():
    replay = stage.read_csv(stage.PINS["source_row_replay"][0])
    replay.loc[replay.source_record_id.eq("ROSSTAT2002:T4:01-04:r4338"), "population"] = "29534"
    with pytest.raises(ValueError, match="official Table4 raw row changed"):
        stage.replay_official_rows(replay)


def test_partition_projection_is_exclusive_and_exact():
    policy = stage.replay_kush_partition()
    assert policy["parent_population_value"] == 29533
    assert [x["population_value"] for x in policy["child_parts"]] == [22680, 6853]
    assert sum(x["population_value"] for x in policy["child_parts"]) == policy["parent_population_value"]
    assert policy["child_parts_counted_in_addition_to_parent"] is False
    assert policy["child_parts_identity_merged"] is False
