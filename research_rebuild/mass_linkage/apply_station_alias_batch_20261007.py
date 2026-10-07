"""Admit the reviewed physical-locality station designator batch at stage 9."""
import json
from pathlib import Path
import pandas as pd
from current_chain_state_20261007 import sha, normalize, distance_km
from working_state_20261007 import load, E
from apply_unique_county_name_bridge_20261007 import county_key

REVIEW=E/'station_name_alias_batch_20261007'
OUT=E/'station_name_alias_application_20261007'

def main():
    state=load(stage=9)
    before=state.metrics()
    edges=pd.read_csv(REVIEW/'candidate_identity_edge_delta.csv',keep_default_na=False)
    points=pd.read_csv(REVIEW/'candidate_point_use_delta.csv',keep_default_na=False)
    checks=pd.read_csv(REVIEW/'sampled_raw_source_checks.csv',keep_default_na=False)
    checked={r['source_record_id']:r for r in checks.to_dict('records')}
    origin_hashes={}
    for row in edges.to_dict('records'):
        a,b=row['from_source_record_id'],row['to_source_record_id']
        aa,bb=state.by_id.loc[a],state.by_id.loc[b]
        if county_key(aa.district_raw)!=county_key(bb.district_raw) or county_key(aa.district_raw)!=row['county_key']:
            raise ValueError('Explicit county mismatch')
        if any('железнодорожный объект' in str(v) for v in (aa.settlement_type,bb.settlement_type)):
            raise ValueError('Railway feature is not a physical locality')
        for sid in (a,b):
            check=checked[sid]
            if check['status']!='literal_name_and_hash_pass':raise ValueError('Raw check missing')
            source=Path('/workspace/settlements-raw')/check['source_file']
            origin_hashes.setdefault(str(source),sha(source))
            if origin_hashes[str(source)]!=check['raw_source_sha256']:raise ValueError('Raw source changed')
        if a in state.point_rows and b in state.point_rows:
            ap,bp=state.point_rows[a],state.point_rows[b]
            if distance_km((ap['latitude'],ap['longitude']),(bp['latitude'],bp['longitude']))>5:
                raise ValueError('Accepted points contradict identity')
        if state.uf.find(a)==state.uf.find(b):raise ValueError('Already connected at current stage')
        state.union(a,b)
    for row in points.to_dict('records'):
        target,donor=row['target_source_record_id'],row['coordinate_source_record_id']
        if target in state.point_rows or state.uf.find(target)!=state.uf.find(donor):raise ValueError('Point target not eligible')
        origin=Path(row['coordinate_origin_ledger'])
        origin_hashes.setdefault(str(origin),sha(origin))
        if origin_hashes[str(origin)]!=row['coordinate_origin_ledger_sha256']:raise ValueError('Donor ledger changed')
        dp=state.point_rows[donor]
        if distance_km((float(row['latitude']),float(row['longitude'])),(dp['latitude'],dp['longitude']))>0.00001:
            raise ValueError('Donor coordinate differs')
    OUT.mkdir(parents=True,exist_ok=True)
    edges['decision_status']='checked_rule_accepted'
    points['coordinate_admission_status']='reviewed_extension_rule_accepted'
    edges.to_csv(OUT/'accepted_identity_edge_delta.csv',index=False)
    points.to_csv(OUT/'accepted_point_use_delta.csv',index=False)
    state.add_deltas(point_paths=[OUT/'accepted_point_use_delta.csv'])
    after=state.metrics()
    receipt={'status':'applied_station_designator_alias_batch','stage_before':9,'new_edges':len(edges),'new_point_uses':len(points),'before':before,'after':after,'population_gain':{y:after[y]['covered_population']-before[y]['covered_population'] for y in before},'source_population_values_modified':False,'boundary_comparability_asserted':False,'legal_type_transformation_asserted':False,'inputs':{str(p):sha(p) for p in state.inputs+list(REVIEW.glob('*.csv'))+list(REVIEW.glob('*.json'))},'origin_hashes':origin_hashes,'outputs':{p.name:sha(p) for p in OUT.glob('*.csv')}}
    (OUT/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:receipt[k] for k in ['new_edges','new_point_uses','population_gain','after']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
