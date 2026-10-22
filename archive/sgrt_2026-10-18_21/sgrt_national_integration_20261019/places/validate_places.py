"""Cold readback, foreign keys, count balances and independent spherical distances."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

R=Path(__file__).resolve().parent
AXIS=R.parents[1]/'anchor_research_20261019/data/point_axis.parquet'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    a=pd.read_parquet(AXIS).set_index('id')
    d=pd.read_parquet(R/'places_objects_and_crosswalk.parquet')
    f=pd.read_parquet(R/'places_settlement_features.parquet').set_index('id')
    checks=[]
    def ck(name,value,detail=''):checks.append({'check':name,'pass':bool(value),'detail':detail})
    ck('entire_reference_axis_once',f.index.is_unique and len(f)==142570 and set(f.index)==set(a.index))
    ck('source_identifiers_unique',d.source_place_id.is_unique and len(d)==648242)
    input_ids=[];selected=[]
    for p in sorted((R/'selected').glob('*.parquet')):
        meta=json.loads((p.parent/(p.stem.split('_')[-1]+'_acquisition.json')).read_text())
        t=pq.read_table(p)
        ck('cold_read_and_sha_'+p.name,len(t)==meta['selected_rows'] and p.stat().st_size==meta['selected_bytes'] and sha(p)==meta['selected_sha256'])
        input_ids.extend(t.column('id').to_pylist());selected.append(p)
    ck('all_selected_GERS_ids_retained',len(input_ids)==len(d) and set(input_ids)==set(d.source_place_id))
    manifest=json.loads((R/'metadata/source_manifest.json').read_text())
    total=0
    for item in manifest['files']:
        p=R/'metadata'/(Path(item['key']).name+'.metadata.json');info=json.loads(p.read_text());foot=p.with_name(p.name.replace('.metadata.json','.footer'))
        ck('inspected_footer_'+Path(item['key']).name,info['schema_inspected_before_data'] and sha(foot)==info['footer_sha256']);total+=info['rows']
    ck('all16world_files_scoped',len(manifest['files'])==16 and total==81455423)
    ck('exclusive_object_link_modes',d[['baseline_uid','conditional_uid','nearest_candidate_uid']].notna().sum(axis=1).le(1).all())
    ext=d.source_geography_scope.ne('axis_linkage_eligible')
    ck('external_geography_not_assigned',d.loc[ext,['baseline_uid','conditional_uid','nearest_candidate_uid']].isna().all().all())
    ck('countries_and_polygon_flags_not_identical',not d.source_country_ru.equals(d.coarse_naturalearth_rus_inside))
    ck('all_unclassified999_retained',d.loc[d.function_group_code.eq(999),'function_group'].eq('unknown_999').all())
    ck('no_source_zero_or_closed_claimed_open',d.loc[d.source_confidence.eq(0),'source_operating_status'].eq('permanently_closed').all())
    functions=['school','preschool','other_education','hospital','healthcare','veterinary','pharmacy','bank','atm','post_office','postal_collection_point','market','retail_store','food_service','unknown_999']
    max_error=0.0
    for mode,col in [('baseline','baseline_uid'),('conditional','conditional_uid'),('nearest_candidate','nearest_candidate_uid')]:
        z=d[d[col].notna()]
        ck(mode+'_foreign_keys',set(z[col])<=set(a.index))
        ck(mode+'_all_published_count_balance',f[f'places_{mode}_all_categories_count'].equals(z.groupby(col).size().reindex(f.index,fill_value=0).astype('int32')))
        eligible=z[z.source_operating_status.ne('permanently_closed')&z.source_confidence.ne(0)]
        grouped=eligible.groupby([col,'function_group']).size()
        for family in functions:
            e=(grouped.xs(family,level=1) if family in grouped.index.get_level_values(1) else pd.Series(dtype='int64')).reindex(f.index,fill_value=0).astype('int32')
            ck(mode+'_family_balance_'+family,f[f'places_{mode}_{family}_count'].equals(e))
        target=eligible[~eligible.function_group.isin(['outside_requested_functions','unknown_999'])]
        ck(mode+'_target_count_balance',f[f'places_{mode}_requested_function_count'].equals(target.groupby(col).size().reindex(f.index,fill_value=0).astype('int32')))
        ck(mode+'_target_diversity_balance',f[f'places_{mode}_requested_function_diversity'].equals(target.groupby(col).function_group.nunique().reindex(f.index,fill_value=0).astype('int16')))
        for signal in ['fap','school','market','ozon','wildberries']:
            e=eligible[eligible['name_signal_'+signal]].groupby(col).size().reindex(f.index,fill_value=0).astype('int32')
            ck(mode+'_name_signal_balance_'+signal,f[f'places_{mode}_name_signal_{signal}_count'].equals(e))
        # Independent haversine formula; producer used chord distances in XYZ.
        q=a.loc[z[col],['lat','lon']]
        la0=np.deg2rad(z.latitude.to_numpy());la1=np.deg2rad(q.lat.to_numpy());dl=np.deg2rad(z.longitude.to_numpy()-q.lon.to_numpy())
        hav=np.sin((la1-la0)/2)**2+np.cos(la0)*np.cos(la1)*np.sin(dl/2)**2
        e=6371.0088*2*np.arctan2(np.sqrt(np.clip(hav,0,1)),np.sqrt(np.clip(1-hav,0,1)))
        error=np.max(np.abs(e-z.linked_distance_km.to_numpy())) if len(z) else 0
        ck(mode+'_linked_distance_haversine',error<1e-6,f'max_abs_error_km={error}');max_error=max(max_error,float(error))
    ck('all_operation_statuses_preserved',d.source_operating_status.value_counts().to_dict()=={'unknown':648214,'open':26,'permanently_closed':2})
    ck('no_flow_or_operation_verification_invented',not d.external_service_catchment_observed.any() and not d.physical_operation_independently_verified.any())
    ck('no_true_zero_invented',not f.places_true_function_absence_established.any())
    files=[R/'places_settlement_features.parquet',R/'places_objects_and_crosswalk.parquet',R/'places_external_geography.parquet']
    result={'status':'PASS' if all(c['pass'] for c in checks) else 'FAIL','checks_total':len(checks),'checks_passed':sum(c['pass'] for c in checks),'checks':checks,'max_linked_haversine_error_km':max_error,'source_rows':len(d),'axis_rows':len(f),'source_files_cold_read':len(selected),'data_sha256':{p.name:sha(p) for p in files},'code_sha256':sha(Path(__file__)),'scope':'Author invariants/readback; actual external coverage and category correctness require independent validation. No national facility completeness or service-flow claim.'}
    (R/'VALIDATION.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['status','checks_total','checks_passed','max_linked_haversine_error_km']},ensure_ascii=False))
    assert result['status']=='PASS',[c for c in checks if not c['pass']]
    freeze={p.name:sha(p) for p in files+[R/'build_places_features.py',R/'extract_ru_places.py',R/'acquire_overture.py',R/'AUDIT.json',R/'CONFIDENCE_ZERO_AUDIT.json',R/'VALIDATION.json']}
    (R/'PLACES_FREEZE.json').write_text(json.dumps(freeze,indent=2)+'\n')
if __name__=='__main__':main()
