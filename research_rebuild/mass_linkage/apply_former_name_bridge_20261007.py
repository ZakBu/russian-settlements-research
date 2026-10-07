"""Apply source-backed own-entity former names against the current working graph."""
import json
from collections import Counter
from pathlib import Path
import pandas as pd
import xlrd
from current_chain_state_20261007 import sha,normalize,distance_km
from working_state_20261007 import load,E
from apply_unique_county_name_bridge_20261007 import county_key

REVIEW=E/'wikidata_former_name_bridge_20261007'
OUT=E/'wikidata_former_name_application_20261007'

def main():
    state=load(stage=12);before=state.metrics()
    review=json.loads((REVIEW/'run_receipt.json').read_text())
    hashes={str(p):sha(p) for p in state.inputs}
    for path,expected in review['inputs'].items():
        actual=sha(Path(path));hashes[path]=actual
        if actual!=expected:raise ValueError('Former-name input changed: '+path)
    proof=json.loads((REVIEW/'Q27556529_county_context_supplement.json').read_text())
    source=Path(proof['source_path'])
    if sha(source)!=proof['source_sha256']:raise ValueError('Supplement source changed')
    sheet=xlrd.open_workbook(str(source)).sheet_by_name('Sib')
    if sheet.cell_value(3,3)!='район' or sheet.cell_value(3627,3)!='Осинский' or sheet.cell_value(3646,4)!='д. Мольта' or float(sheet.cell_value(3646,5))!=504 or any(sheet.cell_value(n-1,3) for n in range(3629,3666)):
        raise ValueError('Literal supplementary county block differs')
    edges=pd.read_csv(REVIEW/'candidate_identity_edges.csv',dtype=str,keep_default_na=False)
    points=pd.read_csv(REVIEW/'candidate_point_uses.csv',dtype=str,keep_default_na=False)
    redundant=0
    admitted=[];held=[]
    component_members=state.obs.groupby('root').source_record_id.apply(list).to_dict()
    for r in edges.to_dict('records'):
        a,b=r['from_source_record_id'],r['to_source_record_id'];aa,bb=state.by_id.loc[a],state.by_id.loc[b]
        members=component_members.get(state.uf.find(a),[a])+component_members.get(state.uf.find(b),[b])
        if any('железнодорожный объект' in normalize(state.by_id.loc[sid].settlement_type) for sid in members):
            held.append({'from_source_record_id':a,'to_source_record_id':b,'reason':'component_contains_unresolved_railway_feature_grain'})
            continue
        if normalize(aa.settlement_name)!=r['former_name'] or aa.region_norm!=bb.region_norm:raise ValueError('Former-name literal or region differs')
        if not all(bool(x.is_additive_settlement_record) for x in (aa,bb)) or any('(часть' in normalize(x.settlement_name) for x in (aa,bb)):raise ValueError('Not whole physical locality')
        if any('железнодорожный объект' in normalize(x.settlement_type) for x in (aa,bb)):raise ValueError('Wrong physical grain')
        ca,cb=county_key(aa.district_raw),county_key(bb.district_raw)
        transfer=r['qid']=='Q4230262' and ca=='грозненский' and cb=='аргун' and r['county_transfer_secondary_witness'].lower()=='true'
        if not ca or (ca!=cb and not transfer):raise ValueError('Unexplained county change')
        if str(bb.oktmo)!=r['current_native_code']:raise ValueError('Current own-entity code differs')
        witness=Path(r['witness_file'])
        if str(witness) not in hashes:hashes[str(witness)]=sha(witness)
        bp=state.point_rows[b]
        if any(distance_km((p['latitude'],p['longitude']),(bp['latitude'],bp['longitude']))>5 for sid in members if (p:=state.point_rows.get(sid)) is not None):
            held.append({'from_source_record_id':a,'to_source_record_id':b,'reason':'existing_component_points_disagree_over_5km'})
            continue
        p625=json.loads(r['current_P625_witness'])
        if not p625 or min(distance_km((bp['latitude'],bp['longitude']),(float(p['latitude']),float(p['longitude']))) for p in p625)>5:raise ValueError('Own entity point does not corroborate locality')
        if a in state.point_rows:
            ap=state.point_rows[a]
            if distance_km((ap['latitude'],ap['longitude']),(bp['latitude'],bp['longitude']))>5:raise ValueError('Accepted point contradiction')
        if state.uf.find(a)==state.uf.find(b):redundant+=1
        else:
            state.union(a,b)
            component_members[state.uf.find(a)]=list(set(members))
        admitted.append(r)
    admitted_points=[]
    for r in points.to_dict('records'):
        sid,donor=r['target_source_record_id'],r['coordinate_source_record_id']
        if state.uf.find(sid)!=state.uf.find(donor):continue
        if sid in state.point_rows or state.uf.find(sid)!=state.uf.find(donor):raise ValueError('Transfer is not a new same-identity use')
        dp=state.point_rows[donor]
        if distance_km((float(r['latitude']),float(r['longitude'])),(dp['latitude'],dp['longitude']))>0.00001:raise ValueError('Donor point mismatch')
        origin=Path(r['coordinate_origin_ledger']);hashes.setdefault(str(origin),sha(origin))
        if hashes[str(origin)]!=r['coordinate_origin_ledger_sha256']:raise ValueError('Point origin changed')
        admitted_points.append(r)
    edges=pd.DataFrame(admitted,columns=edges.columns)
    points=pd.DataFrame(admitted_points,columns=points.columns)
    OUT.mkdir(parents=True,exist_ok=True)
    edges['decision_status']='checked_rule_accepted';edges['admission_allowed']=True
    edges['admission_rule']='own_entity_exact_former_name_explicit_or_documented_historical_county_own_code_point_checked_v1'
    points['coordinate_admission_status']='reviewed_extension_rule_accepted';points['admission_allowed']=True
    points['native_provider_binding_asserted']=False
    edges.to_csv(OUT/'accepted_identity_edge_delta.csv',index=False)
    points.to_csv(OUT/'accepted_point_use_delta.csv',index=False)
    pd.DataFrame(held,columns=['from_source_record_id','to_source_record_id','reason']).to_csv(OUT/'root_held_candidates.csv',index=False)
    state.add_deltas(point_paths=[OUT/'accepted_point_use_delta.csv'])
    after=state.metrics()
    inputs={**hashes,**{str(p):sha(p) for p in REVIEW.glob('*') if p.is_file()}}
    result={'status':'applied_checked_own_entity_former_names','stage_before':12,'new_edges':len(edges),'new_unique_unions':len(edges)-redundant,'redundant_connectivity_confirmations':redundant,'new_point_uses':len(points),'candidate_edges':review['eligible_edges'],'held_candidates':len(held),'hold_reasons':dict(Counter(r['reason'] for r in held)),'before':before,'after':after,'population_gain':{y:after[y]['covered_population']-before[y]['covered_population'] for y in before},'source_population_values_modified':False,'boundary_comparability_asserted':False,'primary_legal_rename_verification_claimed':False,'secondary_admin_transfer_case':'Q4230262 Berdykel retains village identity while county changes; own dated secondary history','sampling':'fixed20 and separately top5; supplemental original XLS district-column proof resolves one literal county check','inputs':inputs,'outputs':{p.name:sha(p) for p in OUT.glob('*.csv')}}
    (OUT/'application_receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['new_edges','new_unique_unions','new_point_uses','population_gain','after']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
