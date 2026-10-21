#!/usr/bin/env python3
"""Independent finite-access overlay census and exact retained raw geometry subset."""
from pathlib import Path
import pandas as pd,numpy as np,pyarrow as pa,pyarrow.parquet as pq,json,hashlib,datetime,collections
HERE=Path(__file__).resolve().parent;BASE=HERE.parents[2];OLD=BASE/'transport/cycle06_network2021';NEW=BASE/'transport/cycle06_network2021_access_v2';REVIEW=BASE/'reviews/cycle05/network2021_geometry_profile_independent';checks=[]
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb')as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def ck(n,v,detail=None):checks.append({'check':n,'pass':bool(v),'detail':detail})
policy=json.loads((REVIEW/'finite_access_policy_proposal.json').read_text());admission=json.loads((BASE/'reviews/cycle06/network2021_access_v2_finite_policy_admission.json').read_text());receipt=json.loads((NEW/'road_extraction_receipt.json').read_text());pins={str(NEW/'road_extraction_receipt.json'):sha(NEW/'road_extraction_receipt.json'),str(REVIEW/'finite_access_policy_proposal.json'):sha(REVIEW/'finite_access_policy_proposal.json')};permit=set(policy['permit_normalized_literals']);deny=set(policy['deny_normalized_literals']);removed=pd.read_parquet(REVIEW/'all158_expected_access_quarantine.parquet');exclude=set(removed.way_id);ck('policy_complete42literal_frozen_before_rebuild',policy['unique_effective_access_literals']==42 and len(exclude)==158 and sha(REVIEW/'finite_access_policy_proposal.json')=='ba574904411bb07bb24a90a65619ea0e6786c96d5dcda120a561670229c8e897');ck('newgeometry_SHA_bound_to_source_receipt',sha('/tmp/sgrt_network2021_access_v2/road_ways.parquet')==receipt['working_geometry_sha256']);ck('oldgeometry_SHA_bound_unchanged',sha('/tmp/sgrt_network2021/road_ways.parquet')==receipt['prior_geometry_sha256'])
counts=collections.Counter();literals=collections.Counter();actual_removed=[];decision_errors=[];reason_errors=[]
for part in receipt['profile_ledger_parts']:
 newpath=NEW/part['path'];ck('newledger_part_SHA:'+part['path'],sha(newpath)==part['sha256']);a=pd.read_parquet(OLD/part['path']);b=pd.read_parquet(newpath);n=len(a);raw=a.effective_car_access.fillna('');norm=raw.str.strip().str.casefold();cat=norm.map(lambda x:'permit'if x in permit else'deny'if x in deny else'uncertain');accepted=a.accepted&cat.eq('permit');ok=np.array_equal(a.way_id,b.way_id)and np.array_equal(a.accepted,b.old_accepted)and np.array_equal(raw,b.effective_car_access_raw)and np.array_equal(norm,b.effective_car_access_normalized)and np.array_equal(cat,b.access_category)and np.array_equal(accepted,b.accepted)and b.source_ledger_part.eq(part['path']).all()and np.array_equal(b.source_ledger_row_0based,np.arange(n))
 if not ok:decision_errors.append(part['path'])
 # Reason order is presentation only; compare the full multiset, retaining
 # duplicate reasons rather than dropping evidence through set conversion.
 for wid,oldtext,newtext,category,normalized in zip(a.way_id,a.exclusion_reasons_json,b.exclusion_reasons_json,cat,norm):
  oldrs=json.loads(oldtext);oldother=[x for x in oldrs if not x.startswith('effective_car_access_')];rs=([f'effective_car_access_{category}_{normalized}']if category!='permit'else[])+oldother
  if sorted(rs)!=sorted(json.loads(newtext)):reason_errors.append(wid)
 counts['source_rows']+=n;counts['old_accepted']+=int(a.accepted.sum());counts['new_accepted']+=int(b.accepted.sum());counts['additions']+=int((b.accepted&~a.accepted).sum());actual_removed.extend(a.loc[a.accepted&~b.accepted,'way_id'].tolist());literals.update(raw.tolist());counts['deny_removed']+=int((a.accepted&cat.eq('deny')).sum());counts['uncertain_removed']+=int((a.accepted&cat.eq('uncertain')).sum())
ck('all5663409_source_overlay_decisions_metadata_locators_exact',not decision_errors and counts['source_rows']==5663409,{'bad_parts':decision_errors,'counts':dict(counts)});ck('all_old_nonaccess_exclusions_unchanged_and_new_category_reasons_exact',not reason_errors,{'bad_wayIDs':reason_errors[:20]});ck('all42raw_accessvalues_match_independent_census',len(literals)==42 and all(literals[x['effective_access_literal']]==x['all_source_ways']for x in pd.read_csv(REVIEW/'complete_effective_access_literal_census.csv',keep_default_na=False).to_dict('records')));ck('exact158excluded_21deny137uncertain_0additions',set(actual_removed)==exclude and len(actual_removed)==158 and counts['deny_removed']==21 and counts['uncertain_removed']==137 and counts['additions']==0 and counts['new_accepted']==5591746)
# Compare every value of every retained assertion, including all source geometry
# vertices, speed/direction/rawtags/version/time/hash, without producer filtering code.
newiter=iter(pq.ParquetFile('/tmp/sgrt_network2021_access_v2/road_ways.parquet').iter_batches(batch_size=20000));buffer=None;cursor=0;compared=0;bad_batches=[];sample_removed=[]
def take(n):
 global buffer,cursor
 result=[]
 while n:
  if buffer is None or cursor==len(buffer):buffer=pa.Table.from_batches([next(newiter)]);cursor=0
  k=min(n,len(buffer)-cursor);result.append(buffer.slice(cursor,k));cursor+=k;n-=k
 return pa.concat_tables(result)
for bi,batch in enumerate(pq.ParquetFile('/tmp/sgrt_network2021/road_ways.parquet').iter_batches(batch_size=20000)):
 ids=batch.column(batch.schema.get_field_index('way_id')).to_numpy();mask=~pd.Series(ids).isin(exclude).to_numpy();expected=pa.Table.from_batches([batch.filter(pa.array(mask))]);actual=take(len(expected))
 if not expected.equals(actual,check_metadata=False):bad_batches.append(bi)
 compared+=len(expected)
 if not mask.all():sample_removed.append(pa.Table.from_batches([batch.filter(pa.array(~mask))]).to_pandas())
trailing=(0 if buffer is None else len(buffer)-cursor)+sum(len(b)for b in newiter);ck('all5591746_retainedrows_everygeometry_tag_speed_direction_metadatafield_exact',not bad_batches and compared==5591746 and trailing==0,{'compared_rows':compared,'bad_batches':bad_batches[:10]});actual_removed_geometry=pd.concat(sample_removed,ignore_index=True).sort_values('way_id').reset_index(drop=True);exported=pd.read_parquet(NEW/'removed_source_way_witnesses.parquet').sort_values('way_id').reset_index(drop=True);common=[c for c in actual_removed_geometry if c in exported];ok=True
try:pd.testing.assert_frame_equal(actual_removed_geometry[common],exported[common],check_dtype=False)
except AssertionError:ok=False
ck('all158_removed_source_geometry_witnesses_exact',ok and set(exported.way_id)==exclude and len(common)==len(actual_removed_geometry.columns))
# Fixed point/target configuration stays intact while graph/matrix is rebuilt.
for name in ['routing_points.parquet','point_configuration.snapshot.json']:
 ck('protected_point_configuration_unchanged:'+name,(NEW/name).exists()and sha(NEW/name)==sha(OLD/name))
oldmanifest=json.loads((OLD/'artifact_manifest.json').read_text());oldbad=[]
for name,record in oldmanifest['files'].items():
 if sha(OLD/name)!=record['sha256']:oldbad.append(name)
ck('all315_original_frozen_source_graph_matrixfiles_unchanged',len(oldmanifest['files'])==315 and not oldbad,oldbad)
for p,h in pins.items():ck('newsource_freeze_still_same:'+p,sha(p)==h)
result={'status':'INDEPENDENT_ACCESS_V2_SOURCE_SUBSET_ACCEPTED'if all(c['pass']for c in checks)else'REJECT_ACCESS_V2_SOURCE_SUBSET','all_checks_passed':all(c['pass']for c in checks),'n_checks':len(checks),'n_failed':sum(not c['pass']for c in checks),'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_extraction_receipt_sha256':pins[str(NEW/'road_extraction_receipt.json')],'audit_code_sha256':sha(Path(__file__)),'counts':dict(counts),'checks':checks,'scope':'All5663409finiteaccessdecisions/42literals/158quarantines and exactall5591746rawgeometryrows retained from independent76+3admittedbaseline; all315oldfiles unchanged. New compressedgraph/CSR/snaps/matrix not reviewed here and require separate admission.','policy_scope':'Public ordinary static-car scenario; uncertain restrictions omitted without asserting physical roadclosure. Priorgeometry/source metadata admission retained. Turn/ferry/destination-through limitations unchanged.'};(HERE/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps({'status':result['status'],'n_checks':len(checks),'n_failed':result['n_failed'],'counts':dict(counts),'failures':[c for c in checks if not c['pass']]},ensure_ascii=False,indent=2))
