#!/usr/bin/env python3
"""Stage candidate-only Wikidata/census-key temporal corroboration.

No edge or population is admitted.  A secondary P1082 integer is used only as
corroboration for an exact, unique selected census name/region key; dates and
historical scope remain source-reported/unknown.
"""
from __future__ import annotations

import hashlib, json, re, unicodedata
from pathlib import Path
import duckdb
import pandas as pd

BASE=Path('/workspace/settlements-work/continuation_20261004')
OUT=BASE/'root/R4/history_application/temporal_corroboration_candidate_reserve'
LONG=BASE/'accepted_mass_batch/settlements_long.parquet'
POINTS=BASE/'accepted_mass_extensions/accepted_point_uses.parquet'
EDGES=BASE/'accepted_mass_extensions/accepted_identity_edges.parquet'
HIST=BASE/'root/R4/history_application/reviewed_secondary_history_observations.parquet'
ELIG=BASE/'root/R4/history_application/current_place_other_year_history_eligibility.parquet'

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for x in iter(lambda:f.read(1024*1024),b''): h.update(x)
 return h.hexdigest()

def norm(x):
 if pd.isna(x): return ''
 x=unicodedata.normalize('NFKC',str(x)).casefold().replace('ё','е')
 return re.sub(r'\s+',' ',x).strip()

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 con=duckdb.connect()
 cols='source_record_id,entity_id,settlement_name,settlement_type,region_raw,population_value,population_value_quality,population_value_quality_original_tag,source_sha256,source_path,source_locator,legacy_is_federal_aggregate,census_full_chain,census_2002_status,census_2010_status,census_2021_status,spatial_identity_status'
 old=con.execute(f"select {cols},observation_year from read_parquet(?) where record_type='census' and observation_year in (2002,2010)",[str(LONG)]).df()
 cur=con.execute(f"select {cols},source_native_id as raw_2021_native_id from read_parquet(?) where record_type='census' and observation_year=2021",[str(LONG)]).df()
 eligible=con.execute('select current_source_record_id,eligible_for_secondary_observed_year_display,has_current_coordinate_carrier from read_parquet(?)',[str(ELIG)]).df()
 cur=cur.merge(eligible[['current_source_record_id','has_current_coordinate_carrier']],left_on='source_record_id',right_on='current_source_record_id',how='left')
 cur=cur[cur.census_full_chain.eq(False)].copy()
 old=old[~old.legacy_is_federal_aggregate.fillna(False)].copy()
 for df in (old,cur):
  df['name_key']=df.settlement_name.map(norm); df['region_key']=df.region_raw.map(norm)
  df['name_region_key']=df.name_key+'\x1f'+df.region_key
 old=old[(old.name_key!='')&(old.region_key!='')].copy()
 cur=cur[(cur.name_key!='')&(cur.region_key!='')].copy()
 old_counts=old.groupby('name_region_key').source_record_id.nunique()
 cur_counts=cur.groupby('name_region_key').source_record_id.nunique()
 old=old[old.name_region_key.map(old_counts).eq(1)]
 cur=cur[cur.name_region_key.map(cur_counts).eq(1)]
 pairs=old.merge(cur,on='name_region_key',suffixes=('_old','_current'))
 pairs=pairs[pairs.source_record_id_old.ne(pairs.source_record_id_current)].copy()
 # Component equality already means the selected rows share an admitted path;
 # do not stage redundant evidence as a new possible recovery.
 pairs=pairs[pairs.entity_id_old.ne(pairs.entity_id_current)].copy()
 pairs['year']=pairs.observation_year.astype(int)
 # Full QID-bound series overlay, exact statement-year labels only, conflict-held
 # rows removed by quantitative_year_eligible.
 h=con.execute("""select current_source_record_id,current_wikidata_qid,wikidata_statement_id,
     try_cast(quantitative_year_label as integer) as history_year,
     try_cast(population_value_raw_for_secondary_display as decimal(18,4)) as wd_population,
     population_value_raw_for_secondary_display,history_source_tier,date_precision,
     date_literal_flat_tsv,full_year_prefixes_json,date_raw_full_statement,
     history_raw_source_sha256,history_raw_record_locator,raw_reference_payload_json,
     raw_statement_json,date_variant_conflict,population_variant_conflict
     from read_parquet(?) where quantitative_year_eligible and population_value_raw_for_secondary_display is not null""",[str(HIST)]).df()
 h=h[h.history_year.isin([2002,2010])].copy()
 h['wd_int']=h.wd_population.map(lambda x: int(x) if pd.notna(x) and float(x).is_integer() else None)
 h=h[h.wd_int.notna()].copy(); h['wd_int']=h.wd_int.astype('int64')
 # Unique old census→current source key is necessary but not sufficient. A true
 # single-valued P1082 observation for the precise labeled year is also required.
 h['year_value_n']=h.groupby(['current_source_record_id','history_year']).wd_int.transform('nunique')
 h=h[h.year_value_n.eq(1)]
 pairs=pairs.merge(h,left_on=['source_record_id_current','year'],right_on=['current_source_record_id','history_year'],how='inner')
 pairs['census_int']=pairs.population_value_old.map(lambda x:int(x) if pd.notna(x) and float(x).is_integer() else None)
 pairs=pairs[pairs.census_int.notna()].copy(); pairs['census_int']=pairs.census_int.astype('int64')
 pairs['abs_difference']=(pairs.wd_int-pairs.census_int).abs()
 pairs['protected_2010']=(pairs.year.eq(2010)
   & pairs.population_value_quality_old.eq('secondary_confidentiality_protected_value_exact_scope_unverified')
   & pairs.population_value_quality_original_tag_old.eq('confidentiality_perturbed_within_ten'))
 pairs['corroboration_class']='not_match'
 pairs.loc[pairs.abs_difference.eq(0),'corroboration_class']='exact_numeric_match_secondary_only'
 pairs.loc[pairs.protected_2010 & pairs.abs_difference.between(1,10),'corroboration_class']='protected_2010_within_10_secondary_only'
 pairs=pairs[pairs.corroboration_class.ne('not_match')].copy()
 # Historical current-P625 binding must also have an accepted point carrier.
 point_ids=set(con.execute('select distinct target_source_record_id from read_parquet(?) where target_year=2021',[str(POINTS)]).df().target_source_record_id)
 pairs=pairs[pairs.source_record_id_current.isin(point_ids)].copy()
 # Remove already accepted direct identity pairs and endpoints in unresolved
 # candidate-only/pending edge proposals. This reserve is strictly review-only.
 e=con.execute("select * from read_parquet(?)",[str(EDGES)]).df()
 def pairkey(a,b): return tuple(sorted((str(a),str(b))))
 accepted=set(); blocked=set()
 for r in e.itertuples(index=False):
  a,b=getattr(r,'from_source_record_id'),getattr(r,'to_source_record_id')
  if a is None or b is None: continue
  rel=str(getattr(r,'relation',''))
  status=' '.join(str(getattr(r,k,'')) for k in ['admission_status','graph_add_status','proposal_status','candidate_status']).lower()
  cand=getattr(r,'candidate_only',False)
  cand_true=(False if pd.isna(cand) else bool(cand))
  if rel=='same_place' and ('accepted' in status or status.strip()=='') and not cand_true: accepted.add(pairkey(a,b))
  if cand_true or 'pending' in status or 'not_admitted' in status: blocked.update((str(a),str(b)))
 pairs=pairs[~pairs.apply(lambda r:pairkey(r.source_record_id_old,r.source_record_id_current) in accepted,axis=1)]
 pairs=pairs[~pairs.source_record_id_old.isin(blocked)&~pairs.source_record_id_current.isin(blocked)].copy()
 # Candidate relevance: rows already missing the matched year while the other
 # census year is observed; this is a potential full-chain reserve, not a claim.
 pairs['could_fill_missing_full_chain_year']=pairs.apply(lambda r:
    (r.year==2002 and r.census_2002_status_current=='unknown_no_record' and r.census_2010_status_current=='observed') or
    (r.year==2010 and r.census_2010_status_current=='unknown_no_record' and r.census_2002_status_current=='observed'),axis=1)
 # Keep type-change candidates visible and explicit rather than discarding them.
 pairs['type_relation']=pairs.apply(lambda r:'exact_type_label' if norm(r.settlement_type_old)==norm(r.settlement_type_current) else 'type_label_changed_review_required',axis=1)
 pairs['candidate_status']='candidate_only_independent_identity_review_required'
 pairs['old_source_file_hash']=pairs.source_sha256_old
 pairs['old_source_locator']=pairs.source_locator_old
 pairs['current_source_file_hash']=pairs.source_sha256_current
 pairs['current_source_locator']=pairs.source_locator_current
 pairs['history_witness_sha256']=pairs.history_raw_source_sha256
 pairs['history_witness_locator']=pairs.history_raw_record_locator
 pairs['historical_scope_status']='unknown; no exact census date or identity assertion from year label'
 pairs['historical_coordinate_status']='no historical coordinate asserted; current accepted point is context only'
 pairs['population_use_status']='secondary P1082 integer corroboration only; selected census population unchanged'
 pairs['history_binding_status']='reviewed current QID binding; historical identity remains unverified'
 keep=['corroboration_class','could_fill_missing_full_chain_year','year','history_year','current_source_record_id','current_wikidata_qid','wikidata_statement_id','wd_int','population_value_raw_for_secondary_display','history_source_tier','date_precision','date_literal_flat_tsv','full_year_prefixes_json','date_raw_full_statement','history_raw_source_sha256','history_raw_record_locator','raw_reference_payload_json','raw_statement_json','source_record_id_old','source_record_id_current','entity_id_old','entity_id_current','settlement_name_old','settlement_name_current','settlement_type_old','settlement_type_current','type_relation','region_raw_old','region_raw_current','population_value_old','population_value_current','population_value_quality_old','population_value_quality_original_tag_old','census_int','abs_difference','current_2021_population','census_2002_status_current','census_2010_status_current','census_full_chain_current','has_current_coordinate_carrier','source_sha256_old','source_locator_old','source_sha256_current','source_locator_current','historical_scope_status','historical_coordinate_status','population_use_status','history_binding_status','candidate_status']
 # Ensure current pop rows are anchored to current selected population; this column
 # originates from the 2021 candidate crosswalk, but restrict to source id→row.
 pairs['current_2021_population']=pairs.population_value_current
 pairs['current_source_record_id']=pairs.source_record_id_current
 out=pairs[keep].copy()
 out.to_parquet(OUT/'staged_temporal_corroboration_candidates.parquet',index=False)
 out.to_csv(OUT/'staged_temporal_corroboration_candidates.csv',index=False)
 summary=[]
 for label,df in [('all_staged',out),('exact',out[out.corroboration_class.eq('exact_numeric_match_secondary_only')]),('protected_2010_plusminus10',out[out.corroboration_class.eq('protected_2010_within_10_secondary_only')])]:
  for fill in [False,True]:
   x=df[df.could_fill_missing_full_chain_year.eq(fill)]
   summary.append({'scenario':label,'could_fill_missing_full_chain_year':fill,'candidate_rows':len(x),'old_census_source_rows':x.source_record_id_old.nunique(),'current_2021_source_rows':x.source_record_id_current.nunique(),'potential_current_2021_population_once_per_current_source':int(x.drop_duplicates('source_record_id_current').current_2021_population.sum()),'type_changed_candidate_rows':int(x.type_relation.ne('exact_type_label').sum()),'interpretation':'candidate-only potential; no identity edge/population or census-chain status admitted'})
 pd.DataFrame(summary).to_csv(OUT/'potential_full_chain_gain_scenarios.csv',index=False)
 rec={'status':'candidate_only_temporal_corroboration_staged_not_applied','rule':'unique normalized exact settlement name+region old census row and current 2021 row; current QID has one nonconflict exact-year P1082 integer; exact integer equality, or 2010 protected perturbation only within ±10; current accepted point; no conflicting direct/pending endpoint edge','source_inputs':{str(p):sha(p) for p in [LONG,POINTS,EDGES,HIST,ELIG]},'output_counts':{'candidate_rows':len(out),'exact_rows':int(out.corroboration_class.eq('exact_numeric_match_secondary_only').sum()),'protected_2010_near_rows':int(out.corroboration_class.eq('protected_2010_within_10_secondary_only').sum()),'distinct_current_sources':int(out.source_record_id_current.nunique()),'distinct_old_sources':int(out.source_record_id_old.nunique()),'type_changed_rows':int(out.type_relation.ne('exact_type_label').sum()),'potential_fill_rows':int(out.could_fill_missing_full_chain_year.sum())},'files':{p.name:sha(p) for p in [OUT/'staged_temporal_corroboration_candidates.parquet',OUT/'staged_temporal_corroboration_candidates.csv',OUT/'potential_full_chain_gain_scenarios.csv']},'limitations':['historical exact-date census identity is not inferred','no population count is replaced or admitted','the P1082 reported year and scope remain source-reported/unknown','candidate row counts do not prove identity and overlapping candidates are not additive','type changes are retained as explicit review flags'],'final_2021_population_eligibility_not_recomputed_here':'Use final accepted source ID→place map when integrating; join authority is current_source_record_id, not snapshot component entity_id.'}
 (OUT/'receipt.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(rec['output_counts'],indent=2))

if __name__=='__main__': main()
