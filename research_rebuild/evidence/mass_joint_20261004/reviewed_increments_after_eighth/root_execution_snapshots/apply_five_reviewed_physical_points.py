from pathlib import Path
import hashlib,json,csv,time
import duckdb,pyarrow as pa,pyarrow.parquet as pq
from research_rebuild.mass_linkage.apply_reviewed_current_point_retrospective_20261004 import cast_addition_to_schema,_assert_physical_source_flags
C=Path('/workspace/settlements-work/continuation_20261004');D=C/'R4/reviewed_physical_points_5';BASE=C/'root/accepted_large_point_increment_35_v2/accepted_point_uses.parquet';SEL=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');EV=SEL.parent/'source_evidence.parquet';O=C/'root/accepted_reviewed_mezhgorye_points3';O.mkdir(exist_ok=False)
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
assert sha(BASE)=='78089d67b5b4556e44f8c23eec1e689430f8d5b9074d73ebf153c476cc06ecb8'
assert sha(SEL)=='4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657' and sha(EV)=='e915df1c3533e104d15e55d1063036ea76a0ac0ace28591b18d4d05c28d45327'
frag=D/'manifest_fragment.json';assert sha(frag)=='5784ac4a7ae96c08148f133135f077670368b689b644d3afdc5774e65b1a99d3';m=json.loads(frag.read_text())
for x in m['input_pins'].values():assert sha(x['path'])==x['sha256']
spec=m['point_source'];assert sha(spec['candidate']['path'])==spec['candidate']['sha256'] and sha(spec['approved']['path'])==spec['approved']['sha256']
with Path(m['input_pins']['independent_eligible_csv']['path']).open(newline='') as f:original={r['target_source_record_id']:r for r in csv.DictReader(f)}
rows=pq.read_table(spec['candidate']['path']).to_pylist();exceptions={r['target_source_record_id']:r for r in spec['reviewed_global_block_exceptions_exact_tuple_only']};assert len(rows)==len(original)==len(exceptions)==5
blocked=json.loads(Path(m['input_pins']['global_blocklist']['path']).read_text())['blocked_target_source_record_ids'];assert set(original)<=set(blocked)
con=duckdb.connect(config={'threads':1,'memory_limit':'512MB'});ids=list(original)
selected=con.execute('select * from read_parquet(?) where source_record_id in (select unnest(?))',[str(SEL),ids]).fetchdf().set_index('source_record_id');assert len(selected)==5
flags=dict(con.execute('select source_record_id,source_evidence_json from read_parquet(?) where source_record_id in (select unnest(?))',[str(EV),ids]).fetchall())
existing={r[0] for r in con.execute('select target_source_record_id from read_parquet(?) where target_source_record_id in (select unnest(?))',[str(BASE),ids]).fetchall()}
assert existing=={'2010:012_5c339c0d0e_4._20Vologod_pskov_2010.xls:Data Sheet:4806'}
held_scope_unknown={'2002:022_862ad8a69d_02c_Vologodskaya.xls:2C:5142'}
rows=[r for r in rows if r['target_source_record_id'] not in existing|held_scope_unknown];assert len(rows)==3
ids=[r['target_source_record_id'] for r in rows]
schema=pq.read_schema(BASE);new=[]
for r in rows:
 sid=r['target_source_record_id'];q=original[sid];ex=exceptions[sid];s=selected.loc[sid];_assert_physical_source_flags(json.loads(flags[sid]),sid)
 for k in ['latitude','longitude']:assert float(r[k])==float(q[k])==float(ex[k])
 for a,b in [('point_origin_sha256','origin_sha256'),('point_origin_locator','origin_locator')]:assert r[a]==ex[b]
 assert r['point_origin_file']==q['point_origin_file'] and ex['origin_file']==m['input_pins']['raw_GeoKLADR_2011_DBf']['path']
 raw_alias=r['point_origin_file'];assert raw_alias=='geokladr_okato_2011_raw_parsed.parquet; raw asset geokladr_okato_2011/okato.dbf'
 r['point_origin_file']=ex['origin_file']
 assert r['point_origin_sha256']==q['point_origin_sha256'] and r['point_origin_locator']==q['point_origin_locator'];assert r['point_origin_sha256']==sha(r['point_origin_file'])
 assert int(s.census_year)==int(q['census_year']) and s.settlement_name==q['settlement_name'] and s.settlement_type==q['settlement_type'] and s.region_norm==q['region_norm']
 r.update(target_year=int(s.census_year),coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_admission_rule='independently reviewed exact named typed DBF physical point with historical classifier/current-native context; exact point-only quarantine exception',coordinate_quality='independently reviewed physical point; disputed provider alternatives retained',coordinate_provenance=json.dumps({'basis':'2011 named typed raw DBF and independent 2009 classifier/current exact publisher-row replay; spatial continuity inference','original_review_point_origin_label':raw_alias,'actual_hash_pinned_asset':r['point_origin_file'],'review_receipt_sha256':m['input_pins']['independent_review_receipt']['sha256']},ensure_ascii=False),coordinate_provider_id=None,provider_identifier_binding_claimed=False,provider_id_binding_claimed=False,historical_provider_binding_asserted=False,direct_historical_coordinate_measurement=False,census_date_point_measurement_proven=False,coordinate_measurement_date_unknown=True,boundary_comparability_asserted=False,population_scope_comparability_asserted=False,source_record_id=sid,source_name=s.settlement_name,source_type=s.settlement_type,source_region=s.region_norm,source_file=r['point_origin_file'],source_sha256=r['point_origin_sha256'],source_locator=r['point_origin_locator'],source_row=str(s.source_row),target_population=float(s.population),target_source_record_json=s.to_json(force_ascii=False),target_source_evidence_json=flags[sid],candidate_only=False,admission_allowed=True,point_admitted=True,blocked_conflict_resolution_approved=True,blocked_conflict_resolution_rationale=json.dumps(ex,ensure_ascii=False),review_id='fullchain134_points_review_exact5',application_candidate_source_path=spec['candidate']['path'],application_candidate_source_sha256=spec['candidate']['sha256'],historical_propagation_allowed=True)
 new.append(cast_addition_to_schema(r,schema))
addition=pa.Table.from_pylist(new,schema=schema);before=pq.ParquetFile(BASE);dest=O/'accepted_point_uses.parquet';t=time.monotonic()
with pq.ParquetWriter(dest,schema,compression='zstd') as w:
 for b in before.iter_batches(batch_size=8192):w.write_batch(b)
 w.write_table(addition)
additionpath=O/'point_use_additions.parquet';pq.write_table(addition,additionpath,compression='zstd')
# Exact full-column prefix readback, aligned by batches, independent of row-group layout.
a=before.iter_batches(batch_size=8192);after=pq.ParquetFile(dest);b=after.iter_batches(batch_size=8192);n=0
for old in a:
 got=next(b);assert old.equals(got.slice(0,old.num_rows));n+=old.num_rows
assert after.metadata.num_rows==before.metadata.num_rows+3
outkeys=con.execute('select target_source_record_id,latitude,longitude from read_parquet(?) where target_source_record_id in (select unnest(?))',[str(dest),ids]).fetchall();assert len(outkeys)==3 and {r[0] for r in outkeys}==set(ids)
assert con.execute('select count(*)-count(distinct target_source_record_id) from read_parquet(?)',[str(dest)]).fetchone()[0]==0
r={'status':'applied_mezhgorye_exact3_of5_reviewed_physical_point_uses','already_accepted_target_preserved_with_alternative_candidate_only':sorted(existing),'held_nullable_population_scope_in_specific_ordinary_point_route':sorted(held_scope_unknown),'point_rows_before':before.metadata.num_rows,'point_rows_after':after.metadata.num_rows,'all_baseline_fields_and_values_exact_prefix_equal':True,'global_blocklist_unchanged':True,'exception_scope':'Only exact target+origin+locator+coordinate tuples in pinned independently eligible5; every other point route remains blocked','identity_graph_modified':False,'selected_population_modified':False,'provider_binding_asserted':False,'historic_measurement_or_boundary_comparability_asserted':False,'input_pins':{str(p):sha(p) for p in [frag,BASE,SEL,EV]+[Path(x['path']) for x in m['input_pins'].values()]},'outputs':{str(p):sha(p) for p in [dest,additionpath]},'script_sha256':sha(__file__),'elapsed_seconds':time.monotonic()-t};(O/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps(r,ensure_ascii=False))
