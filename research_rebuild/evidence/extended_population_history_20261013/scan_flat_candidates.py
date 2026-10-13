"""Bounded flat-cache inventory for ALREADY bound QIDs; never promotes lost scope/unit/precision."""
from pathlib import Path
import gzip,json,re,hashlib,collections
import pyarrow as pa,pyarrow.parquet as pq
H=Path(__file__).resolve().parent;O=Path('/workspace/scratch/extended_population_history_20261013');P=Path('/workspace/settlements-raw/data/raw/wikipedia_statistical/module_qid_population.jsonl.gz')
b={r['wikidata_qid']:r for r in pq.read_table(O/'current_physical_bindings.parquet').to_pylist()}
def guid(v):
 x=v.rsplit('/',1)[-1];x=re.sub(r'^(Q\d+)-',r'\1$',x);return x.casefold()
known={guid(r['statement_guid']) for r in pq.read_table(O/'population_history_long.parquet',columns=['statement_guid']).to_pylist()};seen=set();rows=[];count=collections.Counter()
with gzip.open(P,'rt') as f:
 for i,line in enumerate(f,1):
  if not line.strip():continue
  count['flat_rows_scanned']+=1;r=json.loads(line);q=r.get('item','').rsplit('/',1)[-1]
  if q not in b:continue
  count['rows_for_already_bound_QIDs']+=1;s=guid(r.get('statement',''));rank=r.get('rank','')
  if s in known:count['existing_GUID_excluded']+=1;continue
  if not s or s in seen:count['duplicate_or_missing_statement']+=1;continue
  if rank.rsplit('#',1)[-1] not in ('NormalRank','PreferredRank'):count['deprecated_or_unknown_rank']+=1;continue
  date=r.get('date');m=re.match(r'^\+?(\d{4,})-',str(date or ''))
  if not m:count['undated']+=1;continue
  seen.add(s);v=b[q];rows.append({'wikidata_qid':q,'statement_uri_raw':r['statement'],'canonical_statement_key':s,'anchor_source_record_id':v['anchor_source_record_id'],'root':v['root'],'source_date_raw':date,'literal_year_component':int(m[1]),'source_population_raw':str(r.get('population')),'source_rank_raw':rank,'date_precision':None,'quantity_unit':None,'whole_item_scope':'UNKNOWN_flat_query_not_preserved','candidate_status':'not_promoted_missing_scope_precision_unit_reference_provenance','primary_verification':'primary_unverified','boundary_comparability':'UNKNOWN','historical_coordinates_observed':False,'source_file':str(P),'source_line_1based':i,'raw_flat_record_json':json.dumps(r,ensure_ascii=False)})
if rows:pq.write_table(pa.Table.from_pylist(rows),O/'flat_P1082_candidates_not_admitted.parquet',compression='zstd')
receipt={'source_path':str(P),'source_sha256':hashlib.sha256(P.read_bytes()).hexdigest(),'bound_QIDs_only':len(b),'known_GUIDs':len(known),'candidate_rows':len(rows),'counts':dict(count),'candidates_promoted_to_observations':0,'output':str(O/'flat_P1082_candidates_not_admitted.parquet') if rows else None};(H/'flat_candidate_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt,ensure_ascii=False))
