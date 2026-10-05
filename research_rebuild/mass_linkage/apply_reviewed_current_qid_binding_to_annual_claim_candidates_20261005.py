#!/usr/bin/env python3
"""Apply narrow current-row QID binding review to annual claim display rows only.

Does not accept a historical population value, coordinates, census identity edge,
source scope, or boundary/population comparability.
"""
import argparse, hashlib, json
from pathlib import Path
import pandas as pd

EXPECTED_CANDIDATES = '21356c64a01cc56d1f8caaebc413b2e4acf8cdd9cf1741f7c8149e1bf1ae3275'
REQUIRED = ['source_row_qid_unique','exact_source_oktmo_p764','current_source_name_exact',
            'current_source_type_exact','current_source_region_exact','source_code_unique_qid',
            'qid_unique_current_source_code','native_competition_clear','physical_p31_lineage',
            'no_contradictory_admin_region']

def sha(p):
 h=hashlib.sha256();
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()

def run(source:Path, review:Path, output:Path):
 if output.exists(): raise FileExistsError(output)
 if sha(source)!=EXPECTED_CANDIDATES: raise ValueError('base candidate JSONL SHA mismatch')
 r=json.loads(review.read_text())
 if r['decision_summary']['accepted_current_QID_binding_only']!=17 or r['decision_summary']['held']!=0: raise ValueError('unexpected review decision')
 df=pd.read_json(source, lines=True)
 rows={x['qid']:x for x in r['per_qid_review']}
 if len(rows)!=17 or set(df.wikidata_qid.astype(str))!=set(rows): raise ValueError('QID set mismatch')
 for q,g in df.groupby('wikidata_qid'):
  rec=rows[str(q)]; checks=rec['competition_and_identity_checks']
  for col,key in [('current_source_record_id_candidate','source_record_id'),('current_source_native_OKTMO_candidate','native_oktmo'),('current_name_candidate','name'),('current_type_candidate','type'),('current_region_candidate','region')]:
   review_key={'native_oktmo':'source_native_code_exact_digits','name':'source_name','type':'source_type','region':'source_region'}.get(key,key)
   if g[col].astype(str).nunique()!=1 or str(g[col].iloc[0])!=str(rec[review_key]): raise ValueError(f'{q} changed mapping: {col}')
  check_key={'exact_source_oktmo_p764':'truthy_exact_P764_matches_native_code','current_source_name_exact':'current_source_name_exact','current_source_type_exact':'current_source_type_exact','current_source_region_exact':'current_source_region_exact','physical_p31_lineage':'physical_P31_lineage','source_row_qid_unique':'source_row_QID_unique','source_code_unique_qid':'source_code_unique_QID','qid_unique_current_source_code':'QID_unique_current_source_code','native_competition_clear':'native_competition_clear','no_contradictory_admin_region':'no_contradictory_admin_region'}
  check_key['source_row_qid_unique']='source_row_QID_unique'
  if not all(checks.get(check_key[k]) is True for k in REQUIRED): raise ValueError(f'{q} review check missing')
 df['current_binding_status']='accepted_current_qid_binding_narrow_exact_code_and_typed_identity_rule'
 df['observation_status']='secondary_Wikidata_assertion_for_currently_bound_place_historical_scope_unknown'
 df['current_binding_decision_scope']='selected_current_record_QID_binding_only'
 df['population_value_accepted']=False
 df['coordinate_attached']=False
 df['census_identity_edge_asserted']=False
 df['population_scope_comparability']='unknown'
 output.parent.mkdir(parents=True,exist_ok=True)
 df.sort_values(['wikidata_qid','observed_year']).to_json(output,orient='records',lines=True,force_ascii=False)
 return {'status':'narrow_current_qid_binding_applied_to_secondary_display_only','claims':len(df),'qids':int(df.wikidata_qid.nunique()),'accepted_current_bindings':len(rows),'accepted_population_values':0,'coordinates_attached':0,'census_identity_edges':0,'output_sha256':sha(output),'output_bytes':output.stat().st_size,'inputs':{'candidate_claims':{'path':str(source),'sha256':sha(source)},'review_receipt':{'path':str(review),'sha256':sha(review)}}}

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--source',type=Path,required=True); ap.add_argument('--review',type=Path,required=True); ap.add_argument('--output',type=Path,required=True); a=ap.parse_args(); print(json.dumps(run(a.source,a.review,a.output),ensure_ascii=False,indent=2))
if __name__=='__main__': main()
