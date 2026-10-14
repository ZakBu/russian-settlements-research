"""Bind source-backed historical locality rows to earliest unique native census record.
No fuzzy acceptance, population interpolation, aggregate allocation, or graph mutation.
"""
import argparse,collections,hashlib,json,math,re,unicodedata
from pathlib import Path
import pandas as pd
import numpy as np
ap=argparse.ArgumentParser();ap.add_argument('--facts',required=True);ap.add_argument('--output',required=True);a=ap.parse_args()
CORE=Path('/workspace/scratch/tochno-enrichment-20261013/applied/integrated_spatial_temporal_records.parquet')
out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
def norm(v):
 if v is None or pd.isna(v):return ''
 return re.sub(r'[^а-яa-z0-9]+',' ',unicodedata.normalize('NFKC',str(v)).lower().replace('ё','е')).strip()
def reg(v):
 s=norm(v)
 for x in ['киров','марий','удмурт','татар','твер','калинин']:
  if x in s:return {'киров':'кировская','марий':'марий эл','удмурт':'удмуртская','татар':'татарстан','твер':'тверская','калинин':'тверская'}[x]
 return re.sub(r'\b(область|край|республика|асср)\b','',s).strip()
def dist(v):
 s=re.sub(r'\b(район|р н|муниципальный|муниципального|района|округ|городской|горсовет|г с)\b','',norm(v)).strip()
 return 'орловский' if s=='халтуринский' else s
def tp(v):
 s=norm(v)
 return {'дер':'деревня','д':'деревня','с':'село','пос':'поселок','п':'поселок','поселок городского типа':'пгт'}.get(s,s)
def code(v):
 if v is None or pd.isna(v):return ''
 z=re.sub(r'\.0$','',str(v).strip())
 return z.zfill(11) if z.isdigit() and len(z) in [10,11] else ''
def km(x,y):
 la,lo,lb,lp=map(math.radians,[*x,*y]);return 6371*2*math.asin(min(1,math.sqrt(math.sin((lb-la)/2)**2+math.cos(la)*math.cos(lb)*math.sin((lp-lo)/2)**2)))
f=pd.read_parquet(a.facts);f=f.where(pd.notna(f),None)
c=pd.read_parquet(CORE);c=c[c.is_additive_settlement_record.fillna(False) & c.region_norm.map(reg).isin(set(f.region.map(reg)))].copy()
c['rk']=c.region_norm.map(reg);c['dk']=c.district_raw.map(dist);c['nk']=c.settlement_name.map(norm);c['tk']=c.settlement_type.map(tp)
indices={};code_indices={}
for yr in [2002,2010,2021]:
 ix=collections.defaultdict(list)
 for r in c[c.census_year==yr].to_dict('records'):ix[(r['rk'],r['dk'],r['nk'])].append(r)
 indices[yr]=ix
 ci=collections.defaultdict(list)
 for r in c[c.census_year==yr].to_dict('records'):
  if code(r.get('okato')):ci[(r['rk'],r['nk'],r['tk'],code(r['okato']))].append(r)
 code_indices[yr]=ci
years=c.groupby('root').census_year.agg(lambda x:'|'.join(map(str,sorted(set(x))))).to_dict()
pp=c[c.accepted_point_present.fillna(False)].sort_values('census_year').copy()
pp=pp[np.isfinite(pp.accepted_latitude.astype(float)) & np.isfinite(pp.accepted_longitude.astype(float))]
first=pp.drop_duplicates('root').set_index('root');la=np.radians(pp.accepted_latitude.astype(float).to_numpy());lo=np.radians(pp.accepted_longitude.astype(float).to_numpy());lb=np.radians(pp.root.map(first.accepted_latitude).astype(float).to_numpy());lp=np.radians(pp.root.map(first.accepted_longitude).astype(float).to_numpy())
pp['spread_km']=6371*2*np.arcsin(np.minimum(1,np.sqrt(np.sin((lb-la)/2)**2+np.cos(la)*np.cos(lb)*np.sin((lp-lo)/2)**2)))
bad=set(pp.loc[pp.spread_km>5,'root']);points={r['root']:r for r in pp.drop_duplicates('root').to_dict('records') if r['root'] not in bad}
historical_keys=collections.defaultdict(set)
for r in f.to_dict('records'): historical_keys[(int(r['year']),reg(r['region']),dist(r.get('district')),norm(r['name']),tp(r['settlement_type']))].add(str(r['provider_id']))
accepted=[];held=[]
for r in f.to_dict('records'):
 key=(reg(r['region']),dist(r.get('district')),norm(r['name']))
 match=None;why='no_exact_name_district_match'
 if r.get('admission_block') is True:
  held.append(dict(r,hold_reason='source_flagged_composition_or_new_place_event'));continue
 coded_match=None
 for yr in [2002,2010,2021]:
  z=code_indices[yr].get((key[0],key[2],tp(r['settlement_type']),code(r.get('okato'))),[]) if code(r.get('okato')) else []
  if z:
   if len({v['root'] for v in z})==1 and z[0]['root'] in points:coded_match=z[0]
   break
 if coded_match is None and len(historical_keys[(int(r['year']),*key,tp(r['settlement_type']))])>1:
  held.append(dict(r,hold_reason='competing_historical_locality_codes_same_name_district_type'));continue
 if coded_match is not None:match=coded_match
 elif not key[1]:why='missing_historical_district'
 else:
  for yr in [2002,2010,2021]:
   choices=indices[yr].get(key,[])
   if not choices:continue
   roots={v['root'] for v in choices}
   if len(roots)!=1:why='competing_native_roots_same_name_district';break
   q=choices[0]
   if tp(r['settlement_type'])!=q['tk']:why='type_change_requires_separate_binding';break
   if q['root'] not in points:why='no_accepted_consistent_own_point';break
   match=q;break
 if match is None:held.append(dict(r,hold_reason=why));continue
 q=points[match['root']]
 r.update(official_code_binding=bool(coded_match),root=match['root'],anchor_source_record_id=match['source_record_id'],anchor_census_year=int(match['census_year']),latitude=float(q['accepted_latitude']),longitude=float(q['accepted_longitude']),coordinate_source_record_id=q['source_record_id'],binding_status='automatically_accepted_unique_official_okato_name_type_region' if coded_match else 'automatically_accepted_exact_unique_name_type_historical_district_region_earliest_native_record',retrospective_current_point_inference=True,historical_boundary_comparability='UNKNOWN',linked_census_years=years[match['root']],current_full3_chain=years[match['root']]=='2002|2010|2021',external_identity_asserted=False)
 accepted.append(r)
pd.DataFrame(accepted).to_parquet(out/'accepted_bindings.parquet',index=False);pd.DataFrame(held).to_parquet(out/'held_bindings.parquet',index=False)
receipt={'rule':'exact_unique_name_type_historical_district_region_earliest_native_record_with_accepted_own_point_no_competing_native_roots_in_anchor_year','facts_sha256':hashlib.sha256(Path(a.facts).read_bytes()).hexdigest(),'core_sha256':hashlib.sha256(CORE.read_bytes()).hexdigest(),'input_rows':len(f),'accepted_rows':len(accepted),'held_rows':len(held),'holds':dict(collections.Counter(r['hold_reason'] for r in held)),'core_mutated':False,'population_inferred_or_allocated':False}
(out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False,indent=2))
