#!/usr/bin/env python3
"""All-row preservation audit: axis/source ledger, zeros/nulls, original provenance."""
from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd
H=Path(__file__).resolve().parent;ROOT=H.parent;REPO=H.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
paths=[ROOT/'axis/full_settlement_axis.parquet',ROOT/'axis/source_observations_all.parquet',ROOT.parent/'sgrt_national_integration_20261019/core/feature_master.parquet',ROOT/'axis/inherited_reviewed_population2010_provenance_bridge.parquet'];before={str(p.relative_to(REPO)):sha(p) for p in paths};a=pd.read_parquet(paths[0]).set_index('id');o=pd.read_parquet(paths[1]);old=pd.read_parquet(paths[2]).set_index('id');bridge=pd.read_parquet(paths[3]).set_index('id');checks=[];metrics={};source_files={}
def check(name,ok):checks.append({'check':name,'pass':bool(ok)})
check('source_ledger_unique_settlement_year',not o.duplicated(['id','census_year']).any());check('all_ledger_ids_represented_in_axis',o.id.isin(a.index).all());check('axis_entities_exact_union_ledger_ids',set(o.id)==set(a.index));legacy=a.reindex(old.index)
for c in ['lat','lon']:check('legacy_'+c+'_exactly_preserved',np.array_equal(old[c],legacy[c],equal_nan=True))
for y in [2002,2010,2021]:
 col=f'population_{y}';sc=f'source_record_id_{y}';p=a[col];source=o[o.census_year.eq(y)].set_index('id').reindex(a.index);check(f'all{y}_nonnegative_integer_or_missing',p.dropna().ge(0).all() and p.dropna().mod(1).eq(0).all());check(f'legacy{y}_population_exact',np.array_equal(old[col],legacy[col],equal_nan=True));check(f'legacy{y}_zero_mask_exact',old[col].eq(0).equals(legacy[col].eq(0)));check(f'legacy{y}_missing_mask_exact',old[col].isna().equals(legacy[col].isna()));check(f'legacy{y}_source_record_exact',old[sc].astype('string').fillna('<NULL>').equals(legacy[sc].astype('string').fillna('<NULL>')))
 mismatch=~(p.eq(source.population)|(p.isna()&source.population.isna()))
 if y==2010:
  check('bridge_exactly_all5719_raw_vs_accepted_discrepancies',bridge.index.is_unique and len(bridge)==5719 and set(bridge.index)==set(a.index[mismatch]));check('bridge_preserves_raw_values',np.array_equal(bridge.raw_observation_population,source.reindex(bridge.index).population,equal_nan=True));check('bridge_binds_accepted_values',np.array_equal(bridge.accepted_axis_population,a.reindex(bridge.index).population_2010,equal_nan=True));check('bridge_binds_original_source_record',bridge.raw_source_record_id.astype('string').equals(a.reindex(bridge.index).source_record_id_2010.astype('string')))
  claim_good=[]
  for uid,row in bridge.iterrows():
   claims=json.loads(row.accepted_source_claims_json);claim_good.append(bool(claims) and all(c['effective_primary_value']==row.accepted_axis_population and c['decision_status']=='accepted_population_publication_binding' and c['official_source_record_id'] and c['verified_current_source_sha256']==c['official_source_sha256'] for c in claims))
   for c in claims:source_files[c['verified_current_source_path']]=c['verified_current_source_sha256']
  check('every_bridge_claim_explicit_accepted_unique_value_and_source',all(claim_good));check('bridge_does_not_claim_new_source_reading',not bridge.new_primary_reading_claimed.any());check('all_primary_source_bytes_recovered_and_sha_verified',all(Path(p).is_file() and sha(Path(p))==digest for p,digest in source_files.items()))
 else:check(f'all{y}_population_matches_source_ledger',not mismatch.any())
 check(f'all{y}_source_record_matches_ledger',a[sc].astype('string').fillna('<NULL>').equals(source.source_record_id.astype('string').fillna('<NULL>')))
 metrics[str(y)]={'known':int(p.notna().sum()),'zero':int(p.eq(0).sum()),'missing':int(p.isna().sum()),'ledger_rows':int(o.census_year.eq(y).sum())}
check('inputs_stable_during_review',before=={str(p.relative_to(REPO)):sha(p) for p in paths})
r={'status':'AXIS_PRESERVATION_VERIFIED' if all(c['pass'] for c in checks) else 'RETURN_TO_REPAIR_LOOP','n_checks':len(checks),'n_failed':sum(not c['pass'] for c in checks),'checks':checks,'metrics':metrics,'axis_rows':len(a),'source_ledger_rows':len(o),'source_sha256':before,'verified_primary_source_files':source_files,'scope':'All-row retention of provided census observations and provenance, not independent proof of historic territorial equivalence or primary truth of secondary-source values. Reviewed modelprimary overrides remain separately versioned with originalvalues retained.','scientific_final_allowed':False};(H/'axis_preservation_independent_audit.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k not in ['checks','source_sha256']},ensure_ascii=False,indent=2))
