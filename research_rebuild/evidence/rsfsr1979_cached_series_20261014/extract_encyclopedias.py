import pandas as pd,re,json,hashlib
from pathlib import Path
BASE=Path('/workspace/russian-settlements-research/research_rebuild/evidence')
OUT=Path('/workspace/shared/rsfsr1979_cached_series');OUT.mkdir(exist_ok=True)
selected=BASE/'rsfsr1989_integration_20261013/population_1989_selected_long.parquet'
a=pd.read_parquet(selected)
lookup={u:g for u,g in a.groupby('source_url')}
files=[BASE/'rsfsr1989_rural_volga_20261013'/f for f in ['tatarica_rural_1989.csv','bashenc_rural_1989.csv']]+[BASE/'rsfsr1989_rural_bashenc_delta_20261013/bashenc_rural_1989_delta_final_frozen.csv']
rows=[];receipts=[]
for f in files:
 receipts.append(dict(path=str(f),sha256=hashlib.sha256(f.read_bytes()).hexdigest()))
 for r in pd.read_csv(f).fillna('').to_dict('records'):
  s=r['source_population_section'];hits=list(re.finditer(r'(?<!\d)1979\s*(?:г\.)?\s*[—–-]\s*(\d[\d \u00a0]*)(?![\d.]|,\d)(?=\s*(?:[,;]|чел|жител|$))',s))
  values={int(re.sub(r'\s','',m.group(1))) for m in hits}
  if len(values)!=1:continue
  v=next(iter(values))
  if v<=0:continue
  # Verify frozen source bytes even though the extraction uses the already reviewed population section.
  p=Path(r['source_path'])
  if hashlib.sha256(p.read_bytes()).hexdigest()!=r['source_sha256']:raise ValueError(str(p))
  g=lookup.get(r['source_url']);roots=set() if g is None else set(g.root)
  accepted=len(roots)==1
  anchor={} if not accepted else g.iloc[0].to_dict()
  rows.append(dict(root=next(iter(roots)) if accepted else None,year=1979,population=v,historical_name=r['name_raw'],current_region=r['region_norm'],district=r['district_raw'],source_record_id=r['source_record_id']+':1979',source_kind='secondary_encyclopedia_census_series' if r['source_record_id'].startswith('tatarica:') else 'secondary_encyclopedia_literal_year',source_tier='secondary',source_url=r['source_url'],source_sha256=r['source_sha256'],source_locator=r['source_path']+'#population_section;year=1979',literal_fact=hits[0].group(0),population_basis='presence_permanent_not_specified',population_scope='individual_named_settlement',census_method_verification='TATARICA_Volume1_p3_census_series_statement' if r['source_record_id'].startswith('tatarica:') else 'census_attribution_inferred_not_source_method_verified',decision_status='accepted' if accepted else 'candidate',binding_status='exact_source_url_existing_accepted_1989_root' if accepted else 'not_selected_1989_url',latitude=anchor.get('latitude'),longitude=anchor.get('longitude'),anchor_source_record_id=anchor.get('anchor_source_record_id'),retrospective_current_point_inference=True,historical_boundary_comparability='UNKNOWN',licensing=r['licensing']))
d=pd.DataFrame(rows).drop_duplicates(['source_url','population']);d.to_parquet(OUT/'encyclopedia_candidate_facts.parquet',index=False);acc=d[d.decision_status.eq('accepted')];acc.to_parquet(OUT/'encyclopedia_accepted_facts.parquet',index=False)
summary={'candidates':len(d),'accepted_observations':len(acc),'accepted_roots':acc.root.nunique(),'source_kinds':acc.source_kind.value_counts().to_dict(),'selected1989_sha256':hashlib.sha256(selected.read_bytes()).hexdigest(),'inputs':receipts,'all_source_bytes_verified':True,'zero_or_negative_rows':int((d.population<=0).sum()),'note':'Observation counts only; no marginal coverage claim. Identity follows accepted source URL; 1979 boundary continuity remains inference.'}
(BASE/'rsfsr1979_cached_series_20261014/encyclopedia_receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(summary)
