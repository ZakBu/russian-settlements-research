"""Replay every emitted literal statement and its current UID/root against frozen inputs."""
from pathlib import Path
from decimal import Decimal
import gzip,hashlib,json,collections
import pyarrow.parquet as pq
H=Path(__file__).resolve().parent;O=Path('/workspace/scratch/extended_population_history_20261013')
r=json.loads((H/'receipt.json').read_text());rows=pq.read_table(O/'population_history_long.parquet').to_pylist();bindings={v['wikidata_qid']:v for v in pq.read_table(O/'current_physical_bindings.parquet').to_pylist()}
source=next(p for p in r['inputs'] if p.endswith('integrated_spatial_temporal_records.parquet'));current={v['source_record_id']:v for v in pq.read_table(source,columns=['source_record_id','root','census_year','accepted_latitude','accepted_longitude']).to_pylist()}
def sha(p):
 with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
for p,s in r['inputs'].items():assert sha(p)==s,p
assert len({v['statement_guid'] for v in rows})==len(rows)
byfile=collections.defaultdict(list)
for v in rows:byfile[v['source_file']].append(v)
for file,subset in byfile.items():
 assert sha(file)==subset[0]['source_sha256'];data=json.loads(gzip.decompress(Path(file).read_bytes()) if file.endswith('.gz') else Path(file).read_bytes())
 for v in subset:
  b=bindings[v['wikidata_qid']];cur=current[v['anchor_source_record_id']];assert cur['census_year']==2021 and cur['root']==v['root']==b['root'];assert cur['accepted_latitude']==v['current_own_latitude'] and cur['accepted_longitude']==v['current_own_longitude']
  obj=data
  for key in v['source_locator'].split('/')[:-1]:obj=obj[key]
  statements=obj;st=next(z for z in statements if z['id']==v['statement_guid']);assert json.dumps(st,ensure_ascii=False)==v['raw_statement_json'];assert st['rank'] in ('normal','preferred')
  assert not any(st.get('qualifiers',{}).get(p) for p in ['P518','P642','P21']);dt=st['qualifiers']['P585'];assert len(dt)==1
  d=dt[0]['datavalue']['value'];a=st['mainsnak']['datavalue']['value'];assert d['time']==v['raw_date_literal'] and d['precision']==v['date_precision'];assert Decimal(a['amount'])==v['population_value'] and a['unit']=='1'
  assert v['primary_verification']=='primary_unverified' and v['boundary_comparability']=='UNKNOWN' and v['do_not_override_native_census'] and not v['historical_coordinates_observed']
validation={'status':'PASS','actual_rows_replayed':len(rows),'current_UID_root_and_coordinate_reference_checked':True,'raw_GUID_rank_date_precision_quantity_qualifiers_statement_checked':True,'all_input_hashes_unchanged':True,'all_GUIDs_unique':True,'historical_primary_or_boundary_verification_asserted':False,'prior_GUID_net_gain_verified':False}
(H/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n');print(json.dumps(validation))
