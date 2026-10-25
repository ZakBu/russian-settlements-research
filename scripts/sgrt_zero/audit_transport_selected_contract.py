#!/usr/bin/env python3
"""Read-only audit of selected-provider aliases, local-zero assumptions and access risk.

The metadata projection updates only final-candidate aliases, never published
files, provider selections, minutes, geography or pre-local physical searches.
Topology and straight connector diagnostics do not establish real driveways.
"""
from pathlib import Path
import argparse,hashlib,json
import numpy as np
import pandas as pd


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(4<<20),b''):h.update(block)
    return h.hexdigest()


def audit(bundle,output):
    output.mkdir(parents=True,exist_ok=True);rows=[];deltas=[];inputs=[];affected=set()
    columns=['origin_id','name','region','service_code','selected_provider_id','provider_site_id','provider_id',
        'primary_candidate_id','cost_minutes','primary_cost_minutes','zero_cost_np_assumption','known_local_supply',
        'provider_input_kind','point_separation_km','unconstrained_nearest_provider_id','unconstrained_nearest_cost_minutes',
        'snap_km','provider_snap_km','road_endpoint_accepted','origin_is_additional_context']
    for folder in ['routes','routes_wb','routes_yandex']:
        for path in sorted((bundle/folder/'nearest').glob('*.parquet')):
            before=sha(path);d=pd.read_parquet(path,columns=columns)
            identity=d.selected_provider_id.fillna('<missing>');local=d.zero_cost_np_assumption.fillna(False)
            physical=d.provider_input_kind.eq('sites');external=~local&d.cost_minutes.gt(0)&d.point_separation_km.notna()
            speed=d.point_separation_km.div(d.cost_minutes).mul(60)
            mismatch=d.provider_id.fillna('<missing>').ne(identity)|d.primary_candidate_id.fillna('<missing>').ne(identity)
            if mismatch.any():
                q=d.loc[mismatch,columns[:10]].copy();q['old_provider_id']=q.provider_id;q['old_primary_candidate_id']=q.primary_candidate_id
                q['projected_provider_id']=q.selected_provider_id;q['projected_primary_candidate_id']=q.selected_provider_id
                deltas.append(q);affected.update(q.origin_id)
            # Demonstrate the exact metadata-only projection, retaining physical
            # pre-local choices and all selection/minute columns untouched.
            projected=d.copy();projected['provider_id']=projected.selected_provider_id
            projected['primary_candidate_id']=projected.selected_provider_id;projected['primary_cost_minutes']=projected.cost_minutes
            unchanged=[c for c in columns if c not in {'provider_id','primary_candidate_id','primary_cost_minutes'}]
            pd.testing.assert_frame_equal(d[unchanged],projected[unchanged],check_exact=True)
            after=sha(path);assert before==after,'Published input mutated during read-only audit'
            inputs.append({'path':str(path.relative_to(bundle)),'sha256_before':before,'sha256_after':after,'unchanged':True})
            rows.append({'service':path.stem,'rows':len(d),'provider_alias_mismatches':int(d.provider_id.fillna('<missing>').ne(identity).sum()),
                'primary_candidate_alias_mismatches':int(d.primary_candidate_id.fillna('<missing>').ne(identity).sum()),
                'provider_site_alias_mismatches':int(d.provider_site_id.fillna('<missing>').ne(identity).sum()),
                'metadata_projection_changed_rows':int(mismatch.sum()),'all_alias_mismatches_are_local':bool(local[mismatch].all()),
                'primary_cost_alias_mismatches':int((~(d.primary_cost_minutes.eq(d.cost_minutes)|d.primary_cost_minutes.isna()&d.cost_minutes.isna())).sum()),
                'local_zero_records':int(local.sum()),'local_zero_with_physical_representative':int((local&physical).sum()),
                'local_zero_physical_separation_gt1km':int((local&physical&d.point_separation_km.gt(1)).sum()),
                'local_zero_physical_raw_search_gt20min':int((local&physical&d.unconstrained_nearest_cost_minutes.gt(20)).sum()),
                'local_zero_physical_raw_search_unknown':int((local&physical&d.unconstrained_nearest_cost_minutes.isna()).sum()),
                'external_zero_cost':int((~local&d.cost_minutes.eq(0)).sum()),
                'external_straight_speed_gt130_kmh':int((external&speed.gt(130.00001)).sum()),
                'max_external_straight_speed_kmh':float(speed[external].max()),
                'external_origin_connector_gt2km':int((external&d.snap_km.gt(2)).sum()),
                'external_provider_connector_gt1km':int((external&d.provider_snap_km.gt(1)).sum()),
                'selected_ids_minutes_and_unconstrained_search_unchanged_by_projection':True})
    delta=pd.concat(deltas,ignore_index=True) if deltas else pd.DataFrame()
    if len(delta):delta.to_parquet(output/'provider_alias_metadata_delta.parquet',index=False,compression='zstd')
    summary={'table_count':len(rows),'service_records':sum(r['rows'] for r in rows),
        'alias_metadata_rows_to_correct':sum(r['metadata_projection_changed_rows'] for r in rows),
        'tables_with_alias_metadata_correction':sum(r['metadata_projection_changed_rows']>0 for r in rows),
        'distinct_origins_with_alias_metadata_correction':len(affected),'published_inputs_mutated':False,
        'selection_or_minutes_changed_by_projection':False,'physical_pre_local_search_is_not_renamed_as_final':True,
        'alias_contract_explanation':'nearest_for_sites sets primary_candidate_id/provider_id after its local rule; wrapper then reranks local evidence. These are final-candidate aliases and must follow the reranked selected_provider_id. Explicit unconstrained_nearest_* remains the pre-local physical search.',
        'scope':'Zero is an explicit NP-presence assumption, not measured intra-NP travel. Speed/connector tests do not prove real access across water, fences, slopes, turn restrictions or missing roads.',
        'tables':rows,'input_sha256':inputs,'audit_code_sha256':sha(Path(__file__)),
        'examples':json.loads(delta.head(8).to_json(orient='records',force_ascii=False)) if len(delta) else []}
    (output/'contract_and_access_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'tables':len(rows),'metadata_rows':summary['alias_metadata_rows_to_correct'],'origins':len(affected),'changed_selections_or_minutes':False}))
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();audit(a.bundle,a.output)
