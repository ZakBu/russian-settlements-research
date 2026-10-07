"""Admit two source-checked printed settlement-type prefix aliases."""
import json
from pathlib import Path
import pandas as pd
from current_chain_state_20261007 import sha,normalize,distance_km
from working_state_20261007 import load,E
from apply_unique_county_name_bridge_20261007 import county_key

REVIEW=E/'native_type_prefix_mass_bridge_20261007'
OUT=E/'native_type_prefix_application_20261007'

def main():
    state=load(stage=11)
    before=state.metrics()
    edges=pd.read_csv(REVIEW/'candidate_identity_edge_delta.csv',keep_default_na=False)
    points=pd.read_csv(REVIEW/'candidate_point_use_delta.csv',keep_default_na=False)
    checks=pd.read_csv(REVIEW/'sampled_raw_source_checks.csv',keep_default_na=False)
    checked={r['source_record_id']:r for r in checks.to_dict('records')}
    origins={}
    for r in edges.to_dict('records'):
        a,b=r['from_source_record_id'],r['to_source_record_id']
        aa,bb=state.by_id.loc[a],state.by_id.loc[b]
        if normalize(bb.settlement_type)!='поселок' or not normalize(bb.settlement_name).startswith('п '):raise ValueError('Unsupported prefix/type')
        if normalize(aa.settlement_name)!=normalize(bb.settlement_name)[2:] or normalize(aa.region_norm)!=normalize(bb.region_norm):raise ValueError('Exact alias or region differs')
        if county_key(aa.district_raw)!=county_key(bb.district_raw) or county_key(aa.district_raw)!=r['county_key']:raise ValueError('County mismatch')
        for sid in (a,b):
            c=checked[sid]
            if c['status']!='literal_name_hash_county_pass':raise ValueError('Raw evidence missing')
            path=Path('/workspace/settlements-raw')/c['source_file']
            origins.setdefault(str(path),sha(path))
            if origins[str(path)]!=c['raw_source_sha256']:raise ValueError('Raw source changed')
        if state.uf.find(a)==state.uf.find(b):raise ValueError('Already connected')
        state.union(a,b)
    for r in points.to_dict('records'):
        sid,donor=r['target_source_record_id'],r['coordinate_source_record_id']
        if sid in state.point_rows or state.uf.find(sid)!=state.uf.find(donor):raise ValueError('Point transfer identity mismatch')
        path=Path(r['coordinate_origin_ledger'])
        origins.setdefault(str(path),sha(path))
        if origins[str(path)]!=r['coordinate_origin_ledger_sha256']:raise ValueError('Donor ledger changed')
        dp=state.point_rows[donor];pair=float(r['latitude']),float(r['longitude'])
        if distance_km(pair,(dp['latitude'],dp['longitude']))>0.00001:raise ValueError('Donor point mismatch')
        target=state.by_id.loc[sid]
        if pd.notna(target.latitude) and pd.notna(target.longitude) and distance_km(pair,(target.latitude,target.longitude))>5:raise ValueError('Current coordinate contradicts donor')
    OUT.mkdir(parents=True,exist_ok=True)
    edges['decision_status']='checked_rule_accepted'
    points['coordinate_admission_status']='reviewed_extension_rule_accepted'
    edges.to_csv(OUT/'accepted_identity_edge_delta.csv',index=False)
    points.to_csv(OUT/'accepted_point_use_delta.csv',index=False)
    state.add_deltas(point_paths=[OUT/'accepted_point_use_delta.csv'])
    after=state.metrics()
    receipt={'status':'applied_source_checked_native_type_prefix_aliases','stage_before':11,'new_edges':len(edges),'new_point_uses':len(points),'before':before,'after':after,'population_gain':{y:after[y]['covered_population']-before[y]['covered_population'] for y in before},'source_population_values_modified':False,'boundary_comparability_asserted':False,'native_code_binding_asserted':False,'inputs':{str(p):sha(p) for p in state.inputs+list(REVIEW.glob('*.csv'))+list(REVIEW.glob('*.json'))},'origin_hashes':origins,'outputs':{p.name:sha(p) for p in OUT.glob('*.csv')}}
    (OUT/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:receipt[k] for k in ['new_edges','new_point_uses','population_gain','after']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
