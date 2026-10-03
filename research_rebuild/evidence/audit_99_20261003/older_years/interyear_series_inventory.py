#!/usr/bin/env python3
"""Compact inventory from existing shared point-origin identity artifacts."""
from pathlib import Path
import json
import pandas as pd
OUT=Path('/workspace/settlements-work/continuation_20261003/audit_99_20261003/older_years')
WORK=Path('/workspace/settlements-work/continuation_20261003')
DELIVERY=Path('/workspace/settlements-delivery/continuation-consolidated-20261003')

def main():
    pairs=pd.read_parquet(WORK/'shared_named_point_origin_identity_probe_hardened_v3/candidate_pairs.parquet')
    edges=pd.read_parquet(DELIVERY/'accepted_identity_edges.parquet')
    direct=set(zip(edges.from_source_record_id.astype(str),edges.to_source_record_id.astype(str)))
    direct|={(b,a) for a,b in direct}
    pairs['current_same_place_edge']= [((str(a),str(b)) in direct) for a,b in zip(pairs.from_source_record_id,pairs.to_source_record_id)]
    alias=pd.read_parquet(WORK/'shared_named_point_region_profile_probe_v1/ordinary_region_alias_profile_pairs.parquet')
    alias['current_same_place_edge']=[((str(a),str(b)) in direct) for a,b in zip(alias.from_source_record_id,alias.to_source_record_id)]
    alias['2021_counterpart_with_current_point']=alias.current_2021_point_kind.notna()
    alias['small_locality_in_either_old_year']=alias.population_2002.le(100)|alias.population_2010.le(100)
    alias['zero_record_in_either_old_year']=alias.population_2002.eq(0)|alias.population_2010.eq(0)
    cols=['from_source_record_id','to_source_record_id','name_norm_2002','type_norm_2002','region_norm_2002','name_norm_2010','type_norm_2010','region_norm_2010','raw_2010_label','allowed_region_norm','source_2010_file','source_2010_sheet','source_2010_row','source_2010_sha256','population_2002','population_2010','point_origin_file','point_origin_sha256','point_origin_locator','classifier_code','classifier_line','geo_okato','geo_record','geo_offset','latitude','longitude','event_gate','graph_competitor_gate','current_same_place_edge','current_2021_row_count','current_2021_source_record_id','current_2021_population','current_2021_point_kind','current_2021_point_locator','current_2021_point_sha256','current_2021_point_same_geo_object','small_locality_in_either_old_year','zero_record_in_either_old_year']
    # Cross-check the exact 2021 signature IDs against the current source-evidence
    # collision fields; this is candidate prioritization, not an identity veto.
    sev=pd.read_parquet(DELIVERY/'source_evidence.parquet')
    sid=set(alias.current_2021_source_record_id.dropna().astype(str))
    evid=sev[sev.source_record_id.astype(str).isin(sid)].copy()
    evrows=[]
    for z in evid.itertuples(index=False):
        v=json.loads(z.source_evidence_json)
        evrows.append({'current_2021_source_record_id':z.source_record_id,'census_year':z.census_year,'legacy_same_year_collision':v.get('legacy_same_year_collision'),'legacy_identity_conflict':v.get('legacy_identity_conflict'),'grain_review_flag':v.get('grain_review_flag'),'source_record_population':v.get('population')})
    evdf=pd.DataFrame(evrows)
    alias.merge(evdf,on='current_2021_source_record_id',how='left').to_csv(OUT/'interyear_2021_continuation_priorities.csv',index=False)
    # Current graph-connected 2002/2010 pairs and residual pairs from the existing probe.
    unresolved=pairs[~pairs.current_same_place_edge].copy()
    unresolved.to_csv(OUT/'interyear_origin_pairs_still_unlinked.csv',index=False)
    holds=pd.read_parquet(WORK/'shared_named_point_region_profile_probe_v1/all_retained_hold_pairs.parquet')
    holds.to_csv(OUT/'interyear_source_event_holds.csv',index=False)
    # Include the source-family hold outside the original point-pair file.
    cp=set(zip(pairs.from_source_record_id.astype(str),pairs.to_source_record_id.astype(str)))
    hs=set(zip(holds.from_source_record_id.astype(str),holds.to_source_record_id.astype(str)))
    extra=holds[[ (str(a),str(b)) not in cp for a,b in zip(holds.from_source_record_id,holds.to_source_record_id) ]]
    summary={'status':'existing_evidence_inventory_no_new_identity_or_point_admission','current_delivery':str(DELIVERY),'shared_origin_probe_pairs':int(len(pairs)),'current_graph_connected_shared_origin_pairs':int(pairs.current_same_place_edge.sum()),'still_unlinked_probe_pairs':int((~pairs.current_same_place_edge).sum()),'hold_profile_register_rows_not_comparable_to_probe_pair_rows':int(len(holds)),'hold_register_pairs_not_in_probe_pair_file':int(len(hs-cp)),'newly_accepted_shared_object_edges':1120,'newly_accepted_explicit_region_alias_edges':1139,'total_current_shared_origin_edges':2259,'coordinate_population_boundary_admissions_from_these_edges':0,'ordinary_alias_2021_context':{'rows':int(len(alias)),'exact_2021_signature_counterparts':int(alias.current_2021_row_count.eq(1).sum()),'exact_2021_counterparts_with_current_accepted_points':int(alias.current_2021_point_kind.notna().sum()),'point_kinds':alias.current_2021_point_kind.value_counts(dropna=False).to_dict(),'same_geo_object_points':int(alias.current_2021_point_same_geo_object.fillna(False).sum()),'small_locality_either_old_year_pop_le_100_rows':int(alias.small_locality_in_either_old_year.sum()),'zero_population_either_old_year_rows':int(alias.zero_record_in_either_old_year.sum()),'exact_2021_counterpart_source_evidence_rows':int(len(evdf)),'2021_same_year_collision_rows':int(evdf.legacy_same_year_collision.fillna(False).sum()),'2021_identity_conflict_rows':int(evdf.legacy_identity_conflict.fillna(False).sum()),'2021_concordance_is_candidate_context_only':True},'remaining_hold_register':holds.profile_class.value_counts().to_dict(),'remaining_changed_normalized_types':int(holds.type_norm_2002.ne(holds.type_norm_2010).sum()),'extra_hold_rows_outside_candidate_pair_artifact':extra[['from_source_record_id','to_source_record_id','profile_class','hold_reason_json']].to_dict('records'),'source_comparability_status':'Identity edges do not assert population scope, population comparability, or boundary equivalence. The old point-origin probe asserted none.'}
    (OUT/'interyear_series_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
