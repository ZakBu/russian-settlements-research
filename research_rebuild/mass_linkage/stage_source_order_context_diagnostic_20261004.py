"""Bounded, non-admissive source-order context diagnostic for 2002/2010.

Row order is used only to test whether source lists contain exact typed-name
runs anchored by existing accepted links. This script emits no identity edges.
"""
from __future__ import annotations

import hashlib, json, sys
from pathlib import Path
import duckdb
import pandas as pd
from scipy.stats import kendalltau

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO))
from research_rebuild.mass_linkage.apply_identity_rules import _source_label_key,_source_region_key

F=Path('/workspace/settlements-delivery/continuation-consolidated-20261003')
BASE=Path('/workspace/settlements-work/continuation_20261004/accepted_mass_extensions')
OUT=Path('/workspace/settlements-work/continuation_20261004/root/R4/source_order_context_diagnostic')
RAW=Path('/workspace/settlements-raw')
STATUSES={'checked_rule_accepted','checked_rule_accepted_redundant_graph_connectivity_effect','accepted_rule_family_after_independent_sample_review','case_specific_independent_review_accepted','case_review_accepted','independent_case_review_accepted','accepted_case_specific'}

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()

def main():
 if OUT.exists() and any(OUT.iterdir()): raise FileExistsError(OUT)
 OUT.mkdir(parents=True,exist_ok=True)
 selected=F/'selected_observations.parquet'; evidence=F/'source_evidence.parquet'; graph=BASE/'accepted_identity_edges.parquet'
 pins={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in [selected,evidence,graph]}
 c=duckdb.connect()
 s=c.execute(f"""select source_record_id,census_year,settlement_name,settlement_type,region_raw,district_raw,population,source_file,source_sheet,source_row,source_sha256,source_locator from read_parquet('{selected}') where census_year in (2002,2010)""").df()
 ev=c.execute(f"""select source_record_id,census_year,json_extract_string(source_evidence_json,'$.legacy_identity_reasons') reasons from read_parquet('{evidence}') where census_year=2010""").df()
 g=c.execute(f"""select relation,decision_status,from_source_record_id,try_cast(from_year as int) from_year,to_source_record_id,try_cast(to_year as int) to_year from read_parquet('{graph}')""").df()
 g=g[(g.relation=='same_place') & g.decision_status.isin(STATUSES) & g.from_year.isin([2002,2010]) & g.to_year.isin([2002,2010]) & (g.from_year!=g.to_year)].copy()
 g['id02']=g.apply(lambda r:r.from_source_record_id if r.from_year==2002 else r.to_source_record_id,axis=1)
 g['id10']=g.apply(lambda r:r.from_source_record_id if r.from_year==2010 else r.to_source_record_id,axis=1)
 s['rid']=s.region_raw.map(_source_region_key); s['nk']=s.settlement_name.map(_source_label_key); s['tk']=s.settlement_type.map(_source_label_key)
 s['source_row_num']=pd.to_numeric(s.source_row,errors='coerce')
 s=s.dropna(subset=['source_row_num'])
 ix=s.set_index('source_record_id',drop=False)
 anchors=[]
 for r in g.itertuples(index=False):
  if r.id02 not in ix.index or r.id10 not in ix.index: continue
  a,b=ix.loc[r.id02],ix.loc[r.id10]
  # avoid ambiguous/migrated duplicate IDs from contributing multiple anchors
  if isinstance(a,pd.DataFrame) or isinstance(b,pd.DataFrame): continue
  if a.rid!=b.rid or not a.nk or not a.tk or (a.nk,a.tk)!=(b.nk,b.tk): continue
  anchors.append({'id02':r.id02,'id10':r.id10,'region':a.rid,'f02':a.source_file,'f10':b.source_file,'r02':int(a.source_row_num),'r10':int(b.source_row_num),'nk':a.nk,'tk':a.tk,'district02':str(a.district_raw or ''),'district10':str(b.district_raw or '')})
 adf=pd.DataFrame(anchors)
 # Verify the anchors are actual exact source-name/type rows in pinned selected
 # inputs; raw workbook byte hashes are separately recorded per source file.
 def rawmeta(rel):
  p=RAW/str(rel)
  return {'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size} if p.is_file() else {'path':str(p),'missing':True}
 srcfiles=sorted(set(adf.f02.astype(str))|set(adf.f10.astype(str))) if len(adf) else []
 source_pins={f:rawmeta(f) for f in srcfiles}
 align=[]; runs=[]
 reason_counts=ev.reasons.value_counts(dropna=False).to_dict()
 cohort_ids=set(ev.loc[ev.reasons.eq('["ordinal_historical_identifier_hypothesis"]'),'source_record_id'].astype(str))
 cohort=s[s.source_record_id.astype(str).isin(cohort_ids)].copy()
 # Source-order candidate context: exact five-record typed-name windows in
 # a same-province 2002/2010 source-file pair, with >=2 current accepted links
 # among the five positions. These are diagnostics, never proposed identities.
 potential_ids=set(); potential_pop=0; window_count=0
 for (region,f02,f10),an in adf.groupby(['region','f02','f10'],dropna=False):
  d02=s[(s.census_year==2002)&(s.rid==region)&(s.source_file==f02)].sort_values('source_row_num').reset_index(drop=True)
  d10=s[(s.census_year==2010)&(s.rid==region)&(s.source_file==f10)].sort_values('source_row_num').reset_index(drop=True)
  if len(d02)==0 or len(d10)==0: continue
  amap={(a.id02,a.id10) for a in an.itertuples(index=False)}
  loc02={str(x.source_record_id):i for i,x in enumerate(d02.itertuples(index=False))}
  loc10={str(x.source_record_id):i for i,x in enumerate(d10.itertuples(index=False))}
  # Measure whole-list accepted anchor order (descriptive only).
  valid=an[(an.id02.isin(loc02))&(an.id10.isin(loc10))].copy()
  pos02=valid.id02.map(loc02); pos10=valid.id10.map(loc10)
  tau=float(kendalltau(pos02,pos10).statistic) if len(valid)>1 else None
  aligned=0
  seq02=list(zip(d02.nk,d02.tk))
  window_index={}
  for j in range(max(0,len(seq02)-4)):
   tok=tuple(seq02[j:j+5])
   if all(n and t for n,t in tok): window_index.setdefault(tok,[]).append(j)
  for i in range(len(d10)):
   if i+4>=len(d10): break
   tokens10=tuple(zip(d10.nk.iloc[i:i+5],d10.tk.iloc[i:i+5]))
   if any(not n or not t for n,t in tokens10): continue
   for j in window_index.get(tokens10,[]):
    pairs=[(str(d02.source_record_id.iloc[j+k]),str(d10.source_record_id.iloc[i+k])) for k in range(5)]
    nanchor=sum(p in amap for p in pairs)
    if nanchor<2: continue
    aligned+=1; window_count+=1
    for k,(_,sid10) in enumerate(pairs):
     if sid10 in cohort_ids:
      potential_ids.add(sid10)
      val=d10.population.iloc[i+k]
      if pd.notna(val): potential_pop+=int(val)
      sid02=pairs[k][0]
      runs.append({'region_key':region,'source_file_2002':f02,'source_file_2010':f10,'row_2002_start':int(d02.source_row_num.iloc[j]),'row_2010_start':int(d10.source_row_num.iloc[i]),'run_length_typed_names':5,'accepted_independent_anchor_count':nanchor,'focal_2002_id':sid02,'focal_2010_id':sid10,'focal_population':None if pd.isna(val) else int(val),'status':'context_diagnostic_only_no_identity_admission'})
  align.append({'region_key':region,'source_file_2002':f02,'source_file_2010':f10,'accepted_anchor_count':len(valid),'kendall_order_tau':tau,'exact_typed_name_five_record_runs_with_two_accepted_anchors':aligned,'focal_ordinal_rows_in_run':sum(1 for x in runs if x['region_key']==region and x['source_file_2002']==f02 and x['source_file_2010']==f10)})
 pd.DataFrame(align).to_csv(OUT/'accepted_anchor_source_order_alignment.csv',index=False)
 pd.DataFrame(runs).to_csv(OUT/'anchored_exact_name_run_context_candidates.csv',index=False)
 run_df=pd.DataFrame(runs)
 mapping_counts=run_df.groupby('focal_2010_id').focal_2002_id.nunique() if len(run_df) else pd.Series(dtype=int)
 n_unique=int((mapping_counts==1).sum()); n_ambiguous=int((mapping_counts>1).sum())
 # Independently inventory changes/reorders: correlations well below 1 imply
 # order is not a universal identity key; high tau alone remains diagnostic.
 tauvals=[x['kendall_order_tau'] for x in align if x['kendall_order_tau'] is not None]
 summary={'status':'source_order_context_diagnostic_only','source_order_used_as_identity_proof':False,'fixed_position_used_as_acceptance_evidence':False,'legacy_ordinal_or_manufactured_code_used_as_acceptance_evidence':False,'candidate_identity_admissions':0,'candidate_relation':'none; diagnostic associations only','ordinal_2010_focal_rows':len(cohort),'ordinal_2010_population':int(cohort.population.fillna(0).sum()),'accepted_cross_year_anchor_pairs_in_selected_sources':len(adf),'source_file_pairs':len(align),'source_file_pairs_with_at_least_10_anchors':sum(x['accepted_anchor_count']>=10 for x in align),'source_file_pairs_tau_below_0_8':sum(x['kendall_order_tau'] is not None and x['kendall_order_tau']<0.8 for x in align),'source_file_pairs_tau_below_0_5':sum(x['kendall_order_tau'] is not None and x['kendall_order_tau']<0.5 for x in align),'median_kendall_tau':float(pd.Series(tauvals).median()) if tauvals else None,'exact_5_record_runs_with_at_least_2_accepted_anchors':window_count,'distinct_focal_ordinal_rows_in_runs':len(potential_ids),'focal_population_rows_in_runs_with_repeats_possible':potential_pop,'distinct_focal_population_in_runs':int(cohort.loc[cohort.source_record_id.astype(str).isin(potential_ids),'population'].fillna(0).sum()),'focal_rows_with_exactly_one_2002_mapping_across_runs':n_unique,'focal_rows_with_multiple_2002_mappings_across_runs':n_ambiguous,'population_with_exactly_one_2002_mapping':int(cohort.loc[cohort.source_record_id.astype(str).isin(set(mapping_counts[mapping_counts==1].index)),'population'].fillna(0).sum()),'population_with_multiple_2002_mappings':int(cohort.loc[cohort.source_record_id.astype(str).isin(set(mapping_counts[mapping_counts>1].index)),'population'].fillna(0).sum()),'interpretation':'Exact typed-name runs with current accepted anchors are descriptive context only. Duplicate/repeated runs and cross-district boundaries require independent raw review; this script asserts no source block hierarchy, county consistency, identity or population comparability.','inputs':pins,'raw_source_files':source_pins,'outputs':{},'builder_sha256':sha(Path(__file__))}
 for f in sorted(OUT.iterdir()): summary['outputs'][f.name]={'sha256':sha(f),'bytes':f.stat().st_size}
 (OUT/'receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
