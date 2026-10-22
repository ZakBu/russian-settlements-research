#!/usr/bin/env python3
"""Reconcile every NP in a separately retrieved version of 2021 census data.

The full federal territorial totals are retained as control, so their children
are never summed again into the national population. New children are a real
unmodelled source roster, not geographic identities automatically accepted.
"""
from pathlib import Path
import hashlib,json,re
import numpy as np,pandas as pd
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[3];ROOT=REPO/'research/sgrt_word_completion_20261021'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def code(v,n=11):return str(v).strip().removesuffix('.0').zfill(n)
def norm(v):return re.sub('[^а-яa-z0-9]+',' ',str(v).lower().replace('ё','е')).strip()
source=ROOT/'typology/sources/allsettlements_20260925/data_allsettlements_anon_156_v20260925.parquet'
axis=ROOT/'axis/full_settlement_axis.parquet';raw=REPO/'publication/stage71/applied_state_observations.parquet'
checks=[]
def check(name,v):checks.append(dict(check=name,passed=bool(v)))
t=pd.read_parquet(source,columns=['object_level','object_name','oktmo','region','mun_upper','population','latitude','longitude','qc_geo_dadata'])
t['source_row_1based']=np.arange(len(t))+1
np=t[t.object_level.eq('Населенный пункт')].copy();np['native_np_oktmo11']=np.oktmo.map(code)
s=pd.read_parquet(raw);s=s[s.census_year.eq(2021)&s.population_scope.eq('settlement')].copy();s['native_np_oktmo11']=s.oktmo.map(code)
a=pd.read_parquet(axis,columns=['id','source_record_id_2021'])
s=s.merge(a.dropna(subset=['source_record_id_2021']),left_on='source_record_id',right_on='source_record_id_2021',how='left',validate='one_to_one')
check('latest_np_native_codes_unique',np.native_np_oktmo11.is_unique)
check('accepted2021_np_native_codes_unique',s.native_np_oktmo11.is_unique)
r=np.merge(s[['id','source_record_id','native_np_oktmo11','settlement_name','population']].rename(columns={'population':'axis_population2021'}),on='native_np_oktmo11',how='left',validate='one_to_one')
r['population_signature_matches']=r.population.eq(r.axis_population2021)
r['literal_name_containment']=r.apply(lambda x:bool(pd.notna(x.settlement_name) and re.search(r'(?:^| )'+re.escape(norm(x.settlement_name))+r'(?: |$)',norm(x.object_name))),axis=1)
r['federal_child_source']=r.region.isin(['Москва','Санкт-Петербург','Севастополь'])
r['source_roster_status']=r.apply(lambda x:('accepted_axis2021_native_code_population_match' if pd.notna(x.id) and x.population_signature_matches else 'accepted_axis_code_population_conflict') if pd.notna(x.id) else ('federal_territory_child_not_separately_modelled_do_not_add_to_territory_total' if x.federal_child_source else 'additional_nonfederal_nested_or_scope_conflict_requires_source_review'),axis=1)
r.to_parquet(HERE/'latest2021_np_roster_complete_accounting.parquet',index=False)
extra=r[r.id.isna()].copy();extra.to_parquet(HERE/'latest2021_extra_np_source_queue.parquet',index=False)
extra.groupby(['region','source_roster_status']).agg(source_entities=('population','size'),population=('population','sum'),zero_population_entities=('population',lambda x:int(x.eq(0).sum()))).reset_index().to_csv(HERE/'latest2021_extra_np_region_controls.csv',index=False)
check('every_accepted2021_np_in_independent_latest_roster',set(s.native_np_oktmo11)<=set(r.native_np_oktmo11))
check('every_accepted2021_population_exact_latest_raw',r.loc[r.id.notna(),'population_signature_matches'].all())
check('all155747_latest_np_rows_explicitly_accounted',len(r)==len(np) and r.source_roster_status.notna().all())
# Source-native municipality relation is explicit in this version. A municipality
# with exactly one source NP and equal census totals is a useful restricted bridge,
# but not independent proof of legal boundary identity or physical house location.
upper=t[t.object_level.eq('Муниципалитет верхнего уровня')][['region','object_name','oktmo','population']].copy()
upper['native_municipality_oktmo8']=upper.oktmo.map(lambda x:code(x,8))
upper=upper.rename(columns={'object_name':'mun_upper','population':'municipality_census_population'})
ambiguous=upper.duplicated(['region','mun_upper'],False)
upper[ambiguous].to_csv(HERE/'ambiguous_municipality_name_controls.csv',index=False)
upper=upper[~ambiguous].copy()
check('upper_bridge_uses_only_unique_region_and_source_name',not upper.duplicated(['region','mun_upper']).any())
link=r.merge(upper[['region','mun_upper','native_municipality_oktmo8','municipality_census_population']],on=['region','mun_upper'],how='left',validate='many_to_one')
agg=link.dropna(subset=['native_municipality_oktmo8']).groupby('native_municipality_oktmo8').agg(source_np_count=('native_np_oktmo11','size'),np_census_population_sum=('population','sum'),municipality_census_population=('municipality_census_population','first')).reset_index()
agg['census_mass_control_matches']=agg.np_census_population_sum.eq(agg.municipality_census_population)
agg.to_csv(HERE/'municipality_np_roster_count_controls.csv',index=False)
single=agg[agg.source_np_count.eq(1)&agg.census_mass_control_matches]
one=link[link.native_municipality_oktmo8.isin(single.native_municipality_oktmo8)&link.id.notna()].copy()
q=pd.read_parquet(HERE/'housing_native_year_rate_audit.parquet');q=q[q.year.eq(2021)]
q=q[['housing_native_code','housing_value','strict_native_year_rate','eligibility_status']]
q=q[q.housing_native_code.notna()&~q.housing_native_code.duplicated(False)]
one=one.merge(q,left_on='native_municipality_oktmo8',right_on='housing_native_code',how='left',validate='one_to_one')
one['housing_own_scope_status']='conditional_single_source_np_municipality_not_independent_legal_or_physical_location_proof'
one['own_settlement_housing_verified']=False
one.to_parquet(HERE/'single_np_municipality_housing_candidate_bridge.parquet',index=False)
summary=dict(status='LATEST2021_SOURCE_ROSTER_FULLY_ACCOUNTED_WITH_UNMODELLED_FEDERAL_CHILDREN',n_checks=len(checks),n_failed=sum(not v['passed'] for v in checks),checks=checks,latest_np_rows=len(r),accepted_axis_np_matches=int(r.id.notna().sum()),accepted_name_containment=int(r.loc[r.id.notna(),'literal_name_containment'].sum()),extra_source_np_rows=len(extra),extra_federal_children=int(extra.federal_child_source.sum()),extra_nonfederal_scope_conflicts=int((~extra.federal_child_source).sum()),unmodelled_federal_population_already_in_territory_totals=int(extra.loc[extra.federal_child_source,'population'].sum()),single_source_np_municipalities_with_census_mass_control=len(one),single_np_with_strict_housing2021=int(one.strict_native_year_rate.notna().sum()),no_automatic_new_identity_or_geography_acceptance=True,no_population_double_count=True,own_settlement_housing_verified=False,inputs_sha256={str(p.relative_to(REPO)):sha(p) for p in [source,axis,raw,HERE/'housing_native_year_rate_audit.parquet']})
(HERE/'latest_roster_receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False,indent=2))
