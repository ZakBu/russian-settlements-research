#!/usr/bin/env python3
"""Mass link the real dated2021 schedule by exact names/regions/types only."""
from pathlib import Path
import re,json,hashlib,unicodedata
import numpy as np
import pandas as pd

H=Path(__file__).resolve().parent;R=H.parent;W=R.parent
S=W/'functional_dynamics_20261019/marketplaces/pickpoint_extracted_202102.csv'
P=W/'anchor_research_20261019/data/point_axis.parquet'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def norm(x):return re.sub(r'[^а-яa-z0-9]+',' ',str(x).lower().replace('ё','е')).strip() if pd.notna(x) else ''
def region(x):
    z=norm(x)
    z=' '.join(t for t in z.split() if t not in {'респ','республика','обл','область','край','авт','автономный','автономная','округ'})
    return {'ингушская':'ингушетия','чечня':'чеченская','чувашия':'чувашская'}.get(z,z)

TYPE_RULES=[(r'(?:пгт|п\.?\s*г\.?\s*т\.?|рп|рабочий поселок)','urban_settlement'),(r'(?:город|г\.)','city'),(r'(?:деревня|д\.)','village'),(r'(?:село|с\.)','selo'),(r'(?:станица|ст-ца|стца)','stanitsa'),(r'(?:поселок|пос\.|п\.)','settlement_unspecified')]
TYPE_FAMILIES={'city':{'город'},'village':{'деревня'},'selo':{'село'},'stanitsa':{'станица'},'urban_settlement':{'пгт'},'settlement_unspecified':{'посёлок','поселок','пгт','населённый пункт','населенный пункт'}}

def literal_type(address,name):
    target=norm(name)
    for segment in str(address).lower().replace('ё','е').split(','):
        s=segment.strip()
        for pat,typ in TYPE_RULES:
            m=re.fullmatch(r'\s*'+pat+r'\s+(.+?)\s*',s)
            if m and norm(m.group(1))==target:return typ,segment.strip()
            m=re.fullmatch(r'\s*(.+?)\s+'+pat+r'\s*',s)
            if m and norm(m.group(1))==target:return typ,segment.strip()
    return 'not_explicit',''

def build():
    H.mkdir(exist_ok=True)
    d=pd.read_csv(S);p=pd.read_parquet(P)
    assert len(d)==3005 and d.object_id.is_unique and p.id.is_unique and len(p)==142570
    p['_name']=p.name.map(norm);p['_region']=p.region.map(region)
    index={k:g for k,g in p.groupby(['_name','_region'])}
    regs=[]
    for r in sorted(d.source_region.dropna().unique()):
        z=region(r);regs.append(dict(source_region=r,normalized_region=z,present_in_common_axis=z in set(p._region),normalization='explicit_administrative_token_removal_plus3_named_aliases'))
    rows=[]
    for _,r in d.iterrows():
        n=norm(r.settlement_name);rr=region(r.source_region);typ,literal=literal_type(r.address,r.settlement_name)
        dest=None;status='unresolved_exact_name_region';candidates=[]
        federal={'москва':'RU-FED-MOW','санкт петербург':'RU-FED-SPB'}
        if n in federal:
            dest=federal[n];status='explicit_federal_city_name_territory_not_point'
        else:
            g=index.get((n,rr))
            if g is not None:
                if typ!='not_explicit':g=g[g.type.isin(TYPE_FAMILIES[typ])]
                candidates=g.id.tolist()
                if len(g)==1:dest=g.iloc[0].id;status='exact_full_name_region_and_explicit_type_if_present'
                elif len(g)>1:status='ambiguous_exact_name_region_type_not_resolved'
                elif typ!='not_explicit':status='explicit_type_conflict_not_resolved'
        z=r.to_dict();z.update(settlement_uid=dest if dest and not dest.startswith('RU-FED-') else None,federal_territory_uid=dest if dest and dest.startswith('RU-FED-') else None,link_status=status,region_normalized=rr,settlement_name_normalized=n,source_explicit_type=typ,source_type_literal=literal,candidate_count=len(candidates),candidate_uids='|'.join(candidates),identity_rule='exact_name_region_type_if_present_no_population_or_nearest_tiebreak',address_key=unicodedata.normalize('NFKC',str(r.address)).strip().lower().replace('ё','е'),operator_group=re.sub(r'^ПВЗ:\s*','',str(r.operator_label)).split(':')[0].strip(),physical_opening_date_inferred=False,consumer_origin_flows_measured=False)
        rows.append(z)
    x=pd.DataFrame(rows)
    assert len(x)==len(d) and x.object_id.is_unique
    x.to_csv(H/'pickpoint_objects_crosswalk.csv',index=False);x.to_parquet(H/'pickpoint_objects_crosswalk.parquet',index=False)
    resolved=x[x.settlement_uid.notna()]
    grouped=resolved.groupby('settlement_uid').agg(pickpoint2021_source_schedule_rows=('object_id','size'),pickpoint2021_distinct_exact_address_keys=('address_key','nunique'),pickpoint2021_distinct_operator_labels=('operator_group','nunique'))
    features=p[['id']].merge(grouped,left_on='id',right_index=True,how='left',validate='one_to_one')
    for c in grouped:features[c]=features[c].fillna(0).astype('int32')
    features['pickpoint2021_snapshot_date']='2021-02-20'
    features['pickpoint2021_zero_means']='no_accepted_dated_source_witness_not_function_absence'
    features['pickpoint2021_evidence_scope']='one_partner_network_schedule_not_complete_all_operator_network'
    features['pickpoint2021_comparable_time_series_with_WB2026']=False
    features['pickpoint2021_external_catchment_measured']=False
    features.to_parquet(H/'pickpoint_settlement_features.parquet',index=False);features.to_csv(H/'pickpoint_settlement_features.csv.gz',index=False,compression='gzip')
    federal_rows=[]
    for uid in ['RU-FED-MOW','RU-FED-SPB']:
        q=x[x.federal_territory_uid.eq(uid)]
        federal_rows.append(dict(id=uid,pickpoint2021_source_schedule_rows=len(q),pickpoint2021_distinct_exact_address_keys=q.address_key.nunique(),pickpoint2021_distinct_operator_labels=q.operator_group.nunique(),axis_kind='federal_city_territory_aggregate',snapshot_date='2021-02-20'))
    fed=pd.DataFrame(federal_rows);fed.to_csv(H/'pickpoint_federal_features.csv',index=False);fed.to_parquet(H/'pickpoint_federal_features.parquet',index=False)
    x[x.settlement_uid.isna()&x.federal_territory_uid.isna()].to_csv(H/'pickpoint_review_queue.csv',index=False)
    x[x.duplicated('address_key',keep=False)].to_csv(H/'pickpoint_shared_address_audit.csv',index=False)
    pd.DataFrame(regs).to_csv(H/'region_normalization.csv',index=False)
    assert pd.read_parquet(H/'pickpoint_settlement_features.parquet').equals(features)
    checks={'all3005_source_rows_preserved':len(x)==3005,'all142570_reference_uid_preserved':len(features)==142570 and features.id.equals(p.id),'no_duplicate_uid':features.id.is_unique,'no_federal_rural_assignment':not set(resolved.settlement_uid)&{'RU-FED-MOW','RU-FED-SPB'},'source_rows_conserved_after_aggregation':features.pickpoint2021_source_schedule_rows.sum()==len(resolved),'unresolved_not_assigned_nearest':not x.loc[x.link_status.str.startswith(('unresolved','ambiguous','explicit_type_conflict')),'settlement_uid'].notna().any(),'no_opening_inference':not x.physical_opening_date_inferred.any(),'no_observed_external_flow_claim':not x.consumer_origin_flows_measured.any(),'partner_networks_not_fake_time_series':not features.pickpoint2021_comparable_time_series_with_WB2026.any()}
    checks={k:bool(v) for k,v in checks.items()}
    assert all(checks.values())
    audit={'status':'PASS','source_rows':len(x),'exact_address_keys':x.address_key.nunique(),'ordinary_linked_source_rows':len(resolved),'ordinary_linked_uid':resolved.settlement_uid.nunique(),'federal_source_rows':int(x.federal_territory_uid.notna().sum()),'unresolved_or_ambiguous_rows':int((x.settlement_uid.isna()&x.federal_territory_uid.isna()).sum()),'link_status_counts':x.link_status.value_counts().to_dict(),'feature_rows':len(features),'feature_columns':len(features.columns),'nearest_identity_assignment_used':False,'source_not_whole_market_network':True,'inputs':{str(S.relative_to(W)):sha(S),str(P.relative_to(W)):sha(P)},'checks':checks,'actual_command':'python national_integration_20261019/services_pickpoint/build_pickpoint.py'}
    (H/'AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2));print(json.dumps(audit,ensure_ascii=False,indent=2))

if __name__=='__main__':build()
