#!/usr/bin/env python3
"""Apply 177 independently reviewed current physical-point seeds.

Streams an append-only accepted point ledger. The accepted identity graph and
selected census observations remain read-only; historical coordinates, where
added, are retrospective representative-point inferences through that graph.
"""
from __future__ import annotations

import argparse, csv, hashlib, json, math, sys, time, zipfile
from collections import defaultdict, deque
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path: sys.path.insert(0, str(REPO))
import pyarrow as pa
import pyarrow.parquet as pq
from research_rebuild.mass_linkage.build_long_table import ACCEPTED_COORDINATE_STATUSES, ACCEPTED_EDGE_STATUSES
from research_rebuild.mass_linkage.propagate_continuation_points import load_source_evidence, read_blocked_targets, stage_point_use
from research_rebuild.mass_linkage.apply_reviewed_current_point_retrospective_20261004 import cast_addition_to_schema

REVIEW = Path('/workspace/settlements-work/continuation_20261004/independent_review/type_false_zero_177_review')
BASE = Path('/workspace/settlements-work/continuation_20261004/root/accepted_point_gap_five_reviewed_origin_reconciled')
FROZEN = Path('/workspace/settlements-delivery/continuation-consolidated-20261003')
BLOCK = Path('/workspace/settlements-work/continuation_20261003/blocked_point_reuse_targets_v1.json')
OUT = Path('/workspace/settlements-work/continuation_20261004/root/accepted_type_false_zero_177_points')
RAW = Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet')
GNZIP = Path('/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip')
EXPECTED = {
 'review_receipt':'9f74b15607810e2643cebd4b37e7f3296275b1e508681aace57af338624aebbb',
 'eligible':'7b8c4ceef9e59c1e8331de276731f8244aee96f15d9971a1e900969ff7187aba',
 'base_points':'5c91a4725e7de4e19a510a47998f6a8d3085ce064bacba8896972360b07ca925',
 'graph':'a9fec4648d24afc7345ae23fca9f45058c0962e8fd41d9124deaf01839ef58b6',
 'selected':'4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657',
 'evidence':'e915df1c3533e104d15e55d1063036ea76a0ac0ace28591b18d4d05c28d45327',
 'raw':'86c197cd522e0b63669e9c6e7f43fd3d82b3704c6a126c800a9968ecd16cae14',
 'gn':'9bf299daaff13de75ddbf610e113469aae80537d66a7de3437967576c6509ff4',
 'block':'7a715254f965d996541001d08d3422828299f5c300dfae4cbe78b79f9a5b0e70',
}
SEL_COLS=['source_record_id','census_year','settlement_name','settlement_type','source_name_raw','source_file','source_sheet','source_row','source_sha256','source_locator','source_native_id','source_path','population','population_scope','population_value_quality','is_additive_settlement_record','entity_grain_status','region_raw','region_norm','district_raw','municipality_raw','okato','oktmo']
GRAPH_COLS=['from_source_record_id','to_source_record_id','from_year','to_year','relation','decision_status','decision_id']
POINT_COLS=['target_source_record_id','target_year','latitude','longitude','coordinate_admission_status']
RAW_COLS=['object_level','object_name','oktmo','region','settlement','population','latitude_dadata','longitude_dadata']

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''): h.update(b)
 return h.hexdigest()
def readcsv(p):
 with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def num(v):
 x=float(v)
 if not math.isfinite(x): raise ValueError('non-finite numeric')
 return x
def hav(a,b,c,d):
 r=math.pi/180; p1=a*r;p2=c*r;dp=(c-a)*r;dl=(d-b)*r
 return 6371.0088*2*math.asin(math.sqrt(math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2))
def components(gpath):
 t=pq.read_table(gpath,columns=GRAPH_COLS); adj=defaultdict(list); years={}
 for e in t.to_pylist():
  if e['relation']!='same_place' or e['decision_status'] not in ACCEPTED_EDGE_STATUSES: continue
  a,b=str(e['from_source_record_id']),str(e['to_source_record_id'])
  for sid,y in ((a,int(e['from_year'])),(b,int(e['to_year']))):
   if sid in years and years[sid]!=y:raise ValueError('endpoint year conflict')
   years[sid]=y
  adj[a].append((b,str(e['decision_id'])));adj[b].append((a,str(e['decision_id'])))
 for a in adj:adj[a].sort()
 return adj,years
def comp_paths(seed,adj):
 paths={seed:[]};q=deque([seed])
 while q:
  a=q.popleft()
  for b,d in adj.get(a,[]):
   if b not in paths:paths[b]=paths[a]+[d];q.append(b)
 return set(paths),paths
def raw_by_rows(path, row_numbers):
 pf=pq.ParquetFile(path); rgmap={}; offset=0
 for i in range(pf.metadata.num_row_groups):
  n=pf.metadata.row_group(i).num_rows
  for rn in row_numbers:
   if offset < rn <= offset+n: rgmap.setdefault(i,[]).append((rn,offset))
  offset+=n
 result={}
 for i, vals in rgmap.items():
  tb=pf.read_row_group(i,columns=RAW_COLS)
  for rn,base in vals: result[rn]=tb.slice(rn-base-1,1).to_pylist()[0]
 return result
def gn_by_rows(path, rows):
 wanted={int(r['GeoNames_line_1based']):r for r in rows}; got={}
 with zipfile.ZipFile(path) as z:
  with z.open('RU.txt') as f:
   line_no=0; pos=0
   while len(got)<len(wanted):
    raw=f.readline()
    if not raw:break
    line_no+=1; end=pos+len(raw)
    if line_no in wanted:
     r=wanted[line_no]
     if pos!=int(r['GeoNames_byte_start_0based']) or end!=int(r['GeoNames_byte_end_0based']):raise ValueError('GN byte locator mismatch')
     if hashlib.sha256(raw).hexdigest()!=r['GeoNames_line_sha256']:raise ValueError('GN raw line hash mismatch')
     fields=raw.decode('utf-8').rstrip('\r\n').split('\t')
     if fields[0]!=r['geonames_witness_geonameid'].split('.')[0] or fields[1]!=r['GeoNames_raw_name'] or fields[6]!='P' or fields[7]!=r['geonames_feature_code'] or fields[8]!='RU':raise ValueError('GN feature/name witness mismatch')
     got[line_no]={'lat':float(fields[4]),'lon':float(fields[5]),'id':fields[0],'raw':raw,'start':pos,'end':end}
    pos=end
 return got
def hardflags(ev):
 if not ev: return ['missing_source_evidence']
 out=[]
 if ev.get('is_additive_settlement_record') is not True:out.append('not_additive')
 if ev.get('is_federal_aggregate') is not False:out.append('federal_or_unknown')
 if ev.get('legacy_same_year_collision') is not False:out.append('same_year_collision')
 if ev.get('legacy_verified_successor_settlement_id') not in (None,'','null'):out.append('verified_successor')
 if ev.get('population_scope') not in {'settlement','settlement_population'}:out.append('nonsettlement_scope')
 if any(x in str(ev.get('entity_grain_status') or '').lower() for x in ('aggregate','municipal_total','shared_okato','parent_row')):out.append('aggregate_grain')
 return out

def run():
 start=time.monotonic()
 if OUT.exists():raise FileExistsError(f'immutable output already exists: {OUT}')
 recpath=REVIEW/'independent_review_receipt.json'; seedpath=REVIEW/'independently_eligible_point_seed_list.csv'
 graph=Path('/workspace/settlements-work/continuation_20261004/accepted_mass_ninth_reviewed_legacy202/accepted_identity_edges.parquet')
 base=BASE/'accepted_point_uses.parquet'; selected=FROZEN/'selected_observations.parquet'; evidence=FROZEN/'source_evidence.parquet'
 paths={'review_receipt':recpath,'eligible':seedpath,'base_points':base,'graph':graph,'selected':selected,'evidence':evidence,'raw':RAW,'gn':GNZIP,'block':BLOCK}
 pins={}
 for k,p in paths.items():
  got=sha(p)
  if got!=EXPECTED[k]:raise ValueError(f'{k} SHA mismatch {got}')
  pins[k]={'path':str(p),'sha256':got}
 review=json.loads(recpath.read_text()); seeds=readcsv(seedpath)
 if review['status']!='independent_type_helper_false_zero_point_review_complete_candidate_only' or len(seeds)!=177 or review['independently_eligible_rows']!=177:raise ValueError('review packet count/status mismatch')
 if len({r['target_source_record_id'] for r in seeds})!=177:raise ValueError('duplicate direct target')
 if review['mutations']['accepted_point_ledger'] or review['mutations']['canonical_graph']:raise ValueError('review packet claims mutation')
 blocked=read_blocked_targets(BLOCK)
 adj,yearmap=components(graph)
 comps={};paths_by_seed={}
 for r in seeds: comps[r['target_source_record_id']],paths_by_seed[r['target_source_record_id']]=comp_paths(r['target_source_record_id'],adj)
 if len({tuple(sorted(x)) for x in comps.values()})!=177:raise ValueError('seed components overlap')
 allids=set().union(*comps.values()); needyears={int(yearmap.get(s,-1)) for s in allids}
 selrows=pq.read_table(selected,columns=SEL_COLS,filters=[('source_record_id','in',sorted(allids))]).to_pylist(); sels={str(r['source_record_id']):r for r in selrows}
 if set(sels)!=allids:raise ValueError('missing selected endpoints')
 evs=load_source_evidence(evidence,allids)
 pt=pq.read_table(base,columns=POINT_COLS,filters=[('target_source_record_id','in',sorted(allids))]).to_pylist()
 existing={}
 for r in pt:
  if r['coordinate_admission_status'] in ACCEPTED_COORDINATE_STATUSES:
   sid=str(r['target_source_record_id'])
   if sid in existing:raise ValueError(f'duplicate accepted point {sid}')
   existing[sid]=r
 targetids=set(comps)
 if targetids & set(existing):raise ValueError('one or more direct seeds already have accepted point')
 # All raw publisher rows are replayed at their exact selected parquet row locator.
 rownums={int(float(r['selected_source_row'])) for r in seeds}
 rawrows=raw_by_rows(RAW,rownums)
 for r in seeds:
  rn=int(float(r['selected_source_row'])); raw=rawrows[rn]
  for field,expected in [('oktmo',r['raw_publisher_native_code_literal']),('object_name',r['raw_object_name']),('region',r['raw_publisher_region'])]:
   if str(raw[field]).strip()!=str(expected).strip():raise ValueError(f'raw Tochno row mismatch {rn} field={field}')
  if num(raw['population'])!=num(r['population']):raise ValueError(f'raw Tochno row population mismatch {rn}')
  if num(raw['latitude_dadata'])!=num(r['source_raw_latitude']) or num(raw['longitude_dadata'])!=num(r['source_raw_longitude']): raise ValueError(f'raw source coordinate mismatch {rn}')
 gn=gn_by_rows(GNZIP,seeds)
 additions=[];summary=[]; seed_by_id={r['target_source_record_id']:r for r in seeds}
 for seedid in sorted(seed_by_id):
  row=seed_by_id[seedid]; sel=sels[seedid]; ev=evs.get((seedid,2021))
  if seedid in blocked:raise ValueError('direct seed is blocklisted')
  if int(sel['census_year'])!=2021 or not str(sel['is_additive_settlement_record']).lower()=='true':raise ValueError('invalid current source seed')
  if str(sel['settlement_name'])!=row['settlement_name'] or str(sel['settlement_type'])!=row['settlement_type'] or str(sel['oktmo'])!=row['source_native_oktmo_raw']:raise ValueError('selected source key mismatch')
  if hardflags(ev):raise ValueError(f'direct source hard flags {seedid}: {hardflags(ev)}')
  p=gn[int(row['GeoNames_line_1based'])]; loc=f"member=RU.txt;line={row['GeoNames_line_1based']};byte_start={p['start']};byte_end={p['end']};raw_line_sha256={row['GeoNames_line_sha256']}"
  carrier={'target_source_record_id':seedid,'target_year':2021,'latitude':p['lat'],'longitude':p['lon'],'coordinate_quality':'independently_reviewed_named_physical_place_point','coordinate_source':'GeoNames RU named physical feature; independent physical-name corroboration; not a provider identity binding','coordinate_source_record_id':None,'coordinate_provider':'GeoNames','coordinate_provider_id':None,'coordinate_provider_family':'gazetteer','coordinate_provenance':f"Independent review {EXPECTED['review_receipt']}; raw Tochno source row {RAW} SHA {EXPECTED['raw']} parquet row {row['selected_source_row']} preserves publisher coordinates; selected representative point is the independently reviewed GeoNames RU feature {p['id']} at {p['lat']},{p['lon']}; no provider-ID binding, measurement date, or historical measurement asserted.",'admission_rule':'independent_type_false_zero_177_named_physical_point_20261004','provider_binding_status':'GeoNames external identifier binding not asserted','coordinate_measurement_date_unknown':True,'boundary_comparability_asserted':False,'population_scope_comparability_asserted':False,'coordinate_admission_status':'reviewed_extension_rule_accepted','coordinate_source_sha256':EXPECTED['gn'],'coordinate_source_locator':loc,'coordinate_source_file':str(GNZIP),'coordinate_source_origin':'GeoNames RU.txt literal physical place row','coordinate_source_latitude_raw':p['lat'],'coordinate_source_longitude_raw':p['lon'],'point_origin_file':str(GNZIP),'point_origin_sha256':EXPECTED['gn'],'point_origin_locator':loc,'point_origin_kind':'geonames_RU_literal_physical_feature_row','coordinate_application_review_sha256':EXPECTED['review_receipt'],'geonames_source_file':str(GNZIP),'geonames_source_sha256':EXPECTED['gn'],'geonames_geonameid':p['id'],'geonames_record_locator':loc,'geonames_source_name_raw':row['GeoNames_raw_name'],'geonames_feature_class':'P','geonames_feature_code':row['geonames_feature_code'],'geonames_country_code':'RU','geonames_admin1_raw':row['GeoNames_admin1_code'],'geonames_raw_line_sha256':row['GeoNames_line_sha256'],'provider_id_binding_asserted':False,'native_id_binding_asserted':False,'modern_provider_binding_claimed':False,'historical_measurement_claimed':False,'candidate_only':False}
  direct=stage_point_use(SimpleNamespace(**sel),ev,carrier,seedid,ev,[])
  direct.update(carrier); direct.update({'target_source_record_id':seedid,'target_year':2021,'point_use_id':f'type-false-zero-177-seed:{seedid}','coordinate_application_family':'type_false_zero_177_reviewed_seed_20261004','application_inference_kind':'direct_reviewed_current_point_seed','coordinate_admission_status':'reviewed_extension_rule_accepted','admission_allowed':True,'coordinate_admitted':True,'point_admitted':True,'historical_propagation_allowed':True,'identity_edge_admitted':False,'direct_historical_coordinate_measurement':False,'coordinate_uncertainty_flags_json':json.dumps({'measurement_date_unknown':True,'geo_point_id_binding_not_asserted':True,'historical_measurement_not_asserted':True,'retrospective_use_requires_accepted_same_place_path':True},sort_keys=True),'supporting_source_coordinate_provider':'Tochno/DaData raw fields preserved as source evidence; GeoNames coordinates are selected current point','source_raw_point_latitude':row['source_raw_latitude'],'source_raw_point_longitude':row['source_raw_longitude'],'source_raw_point_origin_file':str(RAW),'source_raw_point_origin_sha256':EXPECTED['raw'],'source_raw_point_origin_locator':row['point_origin_locator'],'review_id':'independent_type_false_zero_177_review'})
  additions.append(direct)
  comp=comps[seedid]; cyears=[yearmap[x] for x in comp]
  if len(comp)!=3 or set(cyears)!={2002,2010,2021}: raise ValueError(f'not unique 3-year component for {seedid}')
  oldpts=[existing[x] for x in comp if x in existing]
  for old in oldpts:
   if hav(p['lat'],p['lon'],num(old['latitude']),num(old['longitude']))>5:raise ValueError(f'existing point spread over 5km in {seedid} component')
  transfer=[]
  for target in sorted(comp,key=lambda x:yearmap[x]):
   year=yearmap[target]
   if year==2021 or target in existing:continue
   if target in blocked:continue
   oldev=evs.get((target,year)); hard=hardflags(oldev)
   if hard:continue
   pathids=paths_by_seed[seedid].get(target)
   if not pathids:raise ValueError('accepted identity path missing')
   use=stage_point_use(SimpleNamespace(**sels[target]),oldev,carrier,seedid,ev,pathids)
   use.update({'coordinate_admission_status':'reviewed_extension_rule_accepted','coordinate_quality':'independently_reviewed_named_physical_place_point_retrospective','coordinate_source_record_id':None,'coordinate_provider_id':None,'coordinate_measurement_date_unknown':True,'boundary_comparability_asserted':False,'population_scope_comparability_asserted':False,'direct_historical_coordinate_measurement':False,'application_inference_kind':'modern_representative_point_retrospective_continuity_inference','coordinate_application_family':'type_false_zero_177_graph_continuation_20261004','coordinate_application_review_sha256':EXPECTED['review_receipt'],'admission_rule':'independent_reviewed_2021_physical_point_plus_accepted_unique_three_year_same_place_graph_path','admission_allowed':True,'coordinate_admitted':True,'point_admitted':True,'historical_propagation_allowed':True,'identity_edge_admitted':False,'historical_measurement_claimed':False,'modern_provider_binding_claimed':False,'provider_binding_status':'GeoNames external identifier binding not asserted','provider_fias_binding_status':'not_asserted_by_graph_continuity','coordinate_provenance':carrier['coordinate_provenance']+'; retrospectively used for this historical source row through canonical accepted same_place graph path; no historical measurement or boundary/population comparability asserted','review_id':'independent_type_false_zero_177_review','point_use_id':f'type-false-zero-177-retrospective:{target}','target_source_record_id':target,'target_year':year,'supporting_carrier_source_record_id':seedid,'inference_modern_point_use_target_source_record_id':seedid,'inference_identity_path_from_source_record_id':target,'inference_identity_path_to_source_record_id':seedid,'inference_identity_path_decision_ids_json':json.dumps(pathids),'inference_identity_path_edge_count':len(pathids),'coordinate_uncertainty_flags_json':json.dumps({'measurement_date_unknown':True,'historical_provider_binding_not_asserted':True,'population_boundary_comparability_not_asserted':True,'retrospective_same_place_path_decision_ids':pathids},sort_keys=True)})
   additions.append(use);existing[target]={'target_source_record_id':target,'coordinate_admission_status':'reviewed_extension_rule_accepted','latitude':p['lat'],'longitude':p['lon']};transfer.append({'id':target,'year':year,'population':float(sels[target]['population'])})
  summary.append({'seed':seedid,'name':row['settlement_name'],'component':sorted(comp),'transferred':transfer})
 # All additions satisfy ledger schema; point identity uniqueness is enforced.
 schema=pq.read_schema(base); casted=[cast_addition_to_schema(x,schema) for x in additions]
 ids=[str(r['target_source_record_id']) for r in casted]
 if len(ids)!=len(set(ids)):raise ValueError('duplicate output point target')
 addtable=pa.Table.from_pylist(casted,schema=schema);addtable.validate(full=True)
 OUT.mkdir(parents=True)
 out=OUT/'accepted_point_uses.parquet'; source=pq.ParquetFile(base)
 with pq.ParquetWriter(out,schema,compression='zstd') as w:
  for b in source.iter_batches(batch_size=4096):w.write_batch(b)
  w.write_table(addtable,row_group_size=len(casted))
 # Verify row count and exact baseline prefix with small projected hashes by record batches.
 op=pq.ParquetFile(out); oi=iter(op.iter_batches(batch_size=4096)); ob=next(oi,None); off=0; rows=0
 for old in source.iter_batches(batch_size=4096):
  rem=old.num_rows; pieces=[]
  while rem:
   if ob is None:raise ValueError('output ended before baseline prefix')
   n=min(rem,ob.num_rows-off);pieces.append(ob.slice(off,n));off+=n;rem-=n
   if off==ob.num_rows:ob=next(oi,None);off=0
  new=pa.Table.from_batches(pieces,schema=schema)
  if not pa.Table.from_batches([old],schema=schema).equals(new):raise ValueError('baseline prefix changed')
  rows+=old.num_rows
 if rows!=source.metadata.num_rows or op.metadata.num_rows!=rows+len(casted):raise ValueError('output row counts mismatch')
 byyear=defaultdict(lambda:{'rows':0,'population':0.0})
 for r in additions:
  y=int(r['target_year']); sid=str(r['target_source_record_id']); byyear[y]['rows']+=1;byyear[y]['population']+=float(sels[sid]['population'])
 # Small audit tables
 with (OUT/'appended_point_uses.csv').open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=['target_source_record_id','target_year','latitude','longitude','supporting_carrier_source_record_id','population','application_inference_kind','point_origin_file','point_origin_sha256','point_origin_locator']);w.writeheader()
  for r in additions:
   sid=str(r['target_source_record_id']);w.writerow({k:r.get(k) if k!='population' else sels[sid]['population'] for k in w.fieldnames})
 (OUT/'component_transfer_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 receipt={'status':'root_authorized_point_only_application_complete','review_receipt_sha256':EXPECTED['review_receipt'],'input_pins':pins,'direct_seed_count':177,'appended_point_use_rows':len(additions),'retrospective_transfer_rows':len(additions)-177,'baseline_point_rows':source.metadata.num_rows,'output_point_rows':op.metadata.num_rows,'baseline_prefix_rows_verified':rows,'baseline_prefix_all_columns_equal':True,'added_population_by_year':{str(y):v for y,v in sorted(byyear.items())},'conditional_seed_source_population_sum':89733,'identity_graph_mutated':False,'selected_observations_mutated':False,'global_blocklist_mutated':False,'provider_identifier_binding_claimed':False,'historical_measurement_claimed':False,'code_sha256':sha(Path(__file__)),'output_sha256':sha(out),'output_path':str(out),'component_summary_sha256':sha(OUT/'component_transfer_summary.json'),'elapsed_seconds':round(time.monotonic()-start,3)}
 (OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 return receipt

if __name__=='__main__':
 print(json.dumps(run(),ensure_ascii=False,indent=2))
