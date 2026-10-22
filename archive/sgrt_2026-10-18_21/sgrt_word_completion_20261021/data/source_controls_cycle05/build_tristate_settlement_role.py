#!/usr/bin/env python3
"""2021 rural/urban classification from primary normative native-NP codes and dated law.

An unqualified 'поселок' is not inherently rural. Unresolved source conflicts and
missing dated observations stay unknown; neither population size nor model output
is used to infer a role. Frozen source types/axis are never overwritten.
"""
from pathlib import Path
import json,hashlib,re
import numpy as np,pandas as pd
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[3];ROOT=REPO/'research/sgrt_word_completion_20261021'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
axispath=HERE/'full_settlement_axis_cycle05_federal_children.parquet';rosterpath=HERE/'latest2021_np_roster_complete_accounting.parquet';addpath=HERE/'federal_np2021_axis_addendum.parquet';normpath=ROOT/'administration2021_cycle05/sources/VvedOKTMO.docx';normextract=ROOT/'administration2021_cycle05/normative_oktmo_structure_extract.json';lawpath=HERE/'sevastopol_legal2019/official_9200201907240006_law518.pdf'
paths=[axispath,rosterpath,addpath,normpath,normextract,lawpath];before={str(p.relative_to(REPO)):sha(p) for p in paths}
axis=pd.read_parquet(axispath);r=pd.read_parquet(rosterpath);r=r[r.id.notna()][['id','native_np_oktmo11']];add=pd.read_parquet(addpath)
codes=pd.concat([r,add[['id','oktmo_2021']].rename(columns={'oktmo_2021':'native_np_oktmo11'})],ignore_index=True).set_index('id').native_np_oktmo11
assert codes.index.is_unique
urban={'город','пгт','посёлок городского типа','поселок городского типа','рабочий посёлок','рабочий поселок','курортный посёлок','курортный поселок','дачный посёлок','дачный поселок','городской посёлок','городской поселок','рп','кп','дп','гп'}
rural={'деревня','село','хутор','станица','аул','аал','улус','починок','арбан','выселок','заимка','кордон','кишлак','слобода','погост'}
# Visually read actual adopted law518-ZS published24.07.2019, PDFp2 appendix3.
# Its declared urban/rural NP lists are independent from the anonymised census provider.
overrides=[dict(id='np2021supp:67362000001',source_name='Балаклава',source2021_effective_settlement_type='город',rural_role=False,law_locator='PDFp2; appendix3; §1urbanNP; item2',legal_name='город Балаклава'),dict(id='np2021supp:67362000103',source_name='1-ое отделение Золотой Балки',source2021_effective_settlement_type='посёлок',rural_role=True,law_locator='PDFp2; appendix3; §2ruralNP; item6',legal_name='поселок 1-е отделение Золотой Балки'),dict(id='np2021supp:67362000104',source_name='3-е отделение Золотой Балки',source2021_effective_settlement_type='посёлок',rural_role=True,law_locator='PDFp2; appendix3; §2ruralNP; item7',legal_name='поселок 3-е отделение Золотой Балки'),dict(id='np2021supp:67366000051',source_name='Кача',source2021_effective_settlement_type='пгт',rural_role=False,law_locator='PDFp2; appendix3; §1urbanNP; item4; NPcode051corroboratesPGT',legal_name='поселок Кача')]
legal=pd.DataFrame(overrides);legal['primary_source_sha256']=sha(lawpath);legal['effective_since']='2019-08-03';legal['source_actual_adopted_law_not_draft']=True;legal.to_csv(HERE/'primary_legal_role_overrides2019.csv',index=False);legal=legal.set_index('id')
rows=[]
for row in axis.itertuples():
 sourcecode=codes.get(row.id);code_role=None
 if pd.notna(sourcecode) and re.fullmatch(r'\d{11}',str(sourcecode)):
  suffix=int(str(sourcecode)[-3:])
  if 1<=suffix<=49:code_role='urban_city'
  elif 51<=suffix<=99:code_role='urban_pgt'
  elif 101<=suffix<=999:code_role='rural'
 typ=str(row.type).strip().lower().replace('ё','е') if pd.notna(row.type) else ''
 text_role='urban' if typ in {v.replace('ё','е') for v in urban} else ('rural' if typ in rural else None)
 latest_rural=True if text_role=='rural' else (False if text_role=='urban' else None)
 observed2021=pd.notna(row.source_record_id_2021)
 additive=bool(row.is_additive_source_unit and not re.search('territory|external_service',str(row.axis_kind),re.I))
 conflict=(code_role is not None and text_role is not None and (code_role=='rural')!=(text_role=='rural'))
 role=None;effective=None
 if not additive:status='nonadditive_source_or_federal_territorial_context'
 elif row.id in legal.index:
  lr=legal.loc[row.id];role=bool(lr.rural_role);effective=lr.source2021_effective_settlement_type;status='primary_law2019_explicit_urban_rural_NP_list'
 elif not observed2021:status='no_dated2021_source_no_historical_type_backcast'
 elif conflict:status='native2021_code_vs_explicit_source_type_conflict_unknown'
 elif code_role is not None:
  role=code_role=='rural';effective=('город' if code_role=='urban_city' else ('пгт' if code_role=='urban_pgt' else row.type));status='primary_OK033_2013_native2021_NPcode_role_with_no_explicit_type_conflict'
 elif text_role is not None:role=text_role=='rural';effective=row.type;status='explicit_dated2021_type_no_admitted_native_NPcode'
 else:status='no_proven2021_settlement_role'
 rows.append(dict(id=row.id,source2021_native_NP_oktmo11=sourcecode,source2021_native_code_role=code_role,source_latest_explicit_type_role=text_role,source_latest_type_rural_role=latest_rural,source2021_rural_role=role,source2021_urban_role=None if role is None else not role,source2021_effective_settlement_type=effective,source2021_role_evidence=status,source2021_type_code_conflict=bool(conflict),source2021_role_has_dated_source=observed2021,source2021_population_additive_role=additive,source2021_role_population_2021=row.population_2021,source2021_role_original_type=row.type,source2021_role_original_name=row.name,source2021_role_region=row.region,source2021_role_located=bool(pd.notna(row.lat) and pd.notna(row.lon)),source2021_role_latest_observation_year=row.latest_observation_year))
roles=pd.DataFrame(rows)
for col in ['source_latest_type_rural_role','source2021_rural_role','source2021_urban_role']:roles[col]=pd.array(roles[col],dtype='boolean')
roles.to_parquet(HERE/'source_settlement_role_tristate_cycle05.parquet',index=False)
roles[roles.source2021_type_code_conflict].to_csv(HERE/'source_role_2021_native_type_conflicts.csv',index=False)
profile=roles.groupby(['source2021_role_original_type','source2021_role_evidence'],dropna=False).agg(rows=('id','size'),known2021_population_rows=('source2021_role_population_2021','count'),population2021_sum=('source2021_role_population_2021',lambda x:x.sum(min_count=1))).reset_index();profile.to_csv(HERE/'source_role_2021_all_type_profile.csv',index=False)
unknown=roles[roles.source2021_population_additive_role&roles.source2021_rural_role.isna()&roles.source2021_role_population_2021.gt(0)].copy()
# This is only the previous main-run final L1 attribution, not a replay of newCi.
m=pd.read_parquet(ROOT/'model/output_word_ci_2021_baseline/memberships.parquet');cols=m.columns.tolist();origin='id' if 'id' in cols else 'settlement_id'
m=m[m.level.eq(1)] if 'level' in cols else m
if origin in cols:
 keep=[v for v in [origin,'center_id','assignment_status'] if v in cols];unknown=unknown.merge(m[keep],left_on='id',right_on=origin,how='left',validate='one_to_one')
unknown.to_csv(HERE/'source_role_2021_unknown_positive_population_impact.csv',index=False)
# Independent source-table population decomposition of Balaklava municipality.
t=pd.read_parquet(ROOT/'typology/sources/allsettlements_20260925/data_allsettlements_anon_156_v20260925.parquet',columns=['object_level','object_name','oktmo','region','population']);t['source_row_1based']=np.arange(len(t))+1
b=t[t.region.eq('Севастополь')&t.oktmo.astype('string').str.startswith('67362')].copy();b.to_csv(HERE/'Balaklava_municipality2021_source_NP_decomposition.csv',index=False)
pop=b.loc[b.object_level.eq('Населенный пункт'),'population'].sum();parent=b[b.object_level.ne('Населенный пункт')]
checks=[]
def check(name,v):checks.append(dict(check=name,passed=bool(v)))
check('all173862_axis_ids_exact_order_and_unique',roles.id.equals(axis.id) and roles.id.is_unique)
check('native2021_code_bridge_exact155746NP_no_municipality8digit_inference',len(codes)==155746 and codes.astype('string').str.fullmatch(r'\d{11}').all())
check('four_legal_role_overrides_match_actual_native_code_role',all(bool(legal.loc[v,'rural_role'])==(roles.set_index('id').loc[v,'source2021_native_code_role']=='rural') for v in legal.index))
check('Balaklava11distinctNP_sum_exact_published_parent48494',len(b[b.object_level.eq('Населенный пункт')])==11 and len(parent)==1 and int(pop)==int(parent.population.iloc[0])==48494)
check('native_type_conflicts_not_silently_rural_or_urban',roles.loc[roles.source2021_type_code_conflict&~roles.id.isin(legal.index),'source2021_rural_role'].isna().all())
check('all_nonadditive_territories_have_no_own_rural_role',roles.loc[~roles.source2021_population_additive_role,'source2021_rural_role'].isna().all())
check('missing2021_type_status_not_backcast_from_2010',roles.loc[~roles.source2021_role_has_dated_source,'source2021_rural_role'].isna().all())
check('frozen_inputs_unchanged',before=={str(p.relative_to(REPO)):sha(p) for p in paths})
receipt=dict(status='PRIMARY_NORMATIVE_CODE_AND_DATED_LEGAL_TRISTATE_ROLES_COMPUTED',n_checks=len(checks),n_failed=sum(not c['passed'] for c in checks),checks=checks,axis_rows=len(roles),native2021_NP_code_rows=len(codes),role_counts={str(k):int(v) for k,v in roles.source2021_rural_role.value_counts(dropna=False).items()},conflicts=len(roles[roles.source2021_type_code_conflict]),unknown_positive_additive2021_NP=len(unknown),unknown_positive_population2021=int(unknown.source2021_role_population_2021.sum()),unknown_positive_located=int(unknown.source2021_role_located.sum()),primary_legal_overrides=4,Balaklava_parent_population2021=48494,Balaklava_distinct_NP_children=11,no_own_NP_or_history_population_imputed=True,inputs_sha256=before,outputs={n:dict(sha256=sha(HERE/n),bytes=(HERE/n).stat().st_size) for n in ['build_tristate_settlement_role.py','source_settlement_role_tristate_cycle05.parquet','source_role_2021_native_type_conflicts.csv','source_role_2021_all_type_profile.csv','source_role_2021_unknown_positive_population_impact.csv','primary_legal_role_overrides2019.csv','Balaklava_municipality2021_source_NP_decomposition.csv']})
(HERE/'source_role_2021_admission_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k not in ['outputs','inputs_sha256']},ensure_ascii=False,indent=2))
