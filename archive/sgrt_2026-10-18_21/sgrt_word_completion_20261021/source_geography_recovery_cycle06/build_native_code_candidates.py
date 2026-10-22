from pathlib import Path
import pandas as pd,numpy as np,json,collections,re,hashlib,datetime
H=Path(__file__).resolve().parent;R=H.parent
P=json.loads((H/'exact_native_code_linkage_protocol.json').read_text())
def norm(x):return ' '.join(str(x).casefold().replace('ё','е').replace('–','-').replace('—','-').split())
def main():
 source=pd.read_parquet(H/'osm2021_inventory');target=pd.read_parquet(H/'all1767_native2021_geography_gaps_source_frame.parquet');raw=pd.read_parquet(R/'data/source_controls_cycle05/latest2021_np_roster_complete_accounting.parquet');rawcount=raw.native_np_oktmo11.value_counts();targets=set(target.native_np_oktmo11.astype(str));lookup=collections.defaultdict(list);vocab=collections.Counter();tagged=0
 for row in source.itertuples():
  t=json.loads(row.tags_json);codes={str(t[k]).strip() for k in P['source_code_keys'] if k in t}
  for c in codes:
   vocab['11digits' if re.fullmatch(r'[0-9]{11}',c) else 'other_grain_or_literal']+=1
   if c in targets and re.fullmatch(r'[0-9]{11}',c):lookup[c].append((row,t))
 out=[];ledger=[]
 for r in target.itertuples():
  code=str(r.native_np_oktmo11);hits=lookup.get(code,[]);nodes=[(row,t) for row,t in hits if row.osm_type=='node' and t.get('place') in P['place_values'] and np.isfinite(row.lat) and np.isfinite(row.lon)];matching=[(row,t) for row,t in nodes if norm(r.name) in {norm(t[k]) for k in P['name_keys'] if k in t}];status='no_exact_source_native11_code'
  if hits:status='exact_code_no_unique_own_named_node'
  if len(matching)==1 and len(nodes)==1 and rawcount.get(code,0)==1:status='A1_unique_coded_source_node_candidate' if len(hits)==1 else 'A2_multiple_code_source_objects_review'
  for row,t in hits:
   ownnamed=norm(r.name) in {norm(t[k]) for k in P['name_keys'] if k in t};out.append(dict(id=r.id,native_np_oktmo11=code,native_source_parent_oktmo8=r.native_source_parent_oktmo8,census_name=r.name,census_type=r.type,census_parent=r.mun_upper,census_region=r.region_source,population_2021=r.population_2021,coordinate_missing=r.coordinate_missing,existing_lat=r.lat,existing_lon=r.lon,source_osm_type=row.osm_type,source_osm_id=row.osm_id,source_version=row.osm_version,source_object_timestamp=row.object_timestamp,source_snapshot_utc='2021-01-01T21:42:03Z',coordinate_measurement_date_unknown=True,source_lat=row.lat,source_lon=row.lon,source_place=t.get('place'),source_name=t.get('name'),source_name_ru=t.get('name:ru'),source_official_name=t.get('official_name'),source_region=t.get('addr:region'),source_parent=t.get('addr:district'),source_subparent=t.get('addr:subdistrict'),source_tags_json=row.tags_json,source_all_tags_sha256=row.all_source_tags_sha256,exact_own_name=ownnamed,status=status,current_accepted_axis_modified=False))
  ledger.append(dict(id=r.id,native_np_oktmo11=code,name=r.name,population_2021=r.population_2021,coordinate_missing=r.coordinate_missing,source_code_objects=len(hits),source_coordinate_place_nodes=len(nodes),source_exact_named_place_nodes=len(matching),native_code_source_roster_count=int(rawcount.get(code,0)),status=status,adopted=False))
 pd.DataFrame(out).to_parquet(H/'all_exact_native11_osm2021_source_assertions.parquet',index=False);l=pd.DataFrame(ledger);l.to_parquet(H/'all1767_native_code_candidate_unknown_ledger.parquet',index=False);receipt=dict(status='SOURCE_ONLY_EXACT_NATIVE_CODE_CANDIDATE_EXTRACTION',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),protocol_sha256=hashlib.sha256((H/'exact_native_code_linkage_protocol.json').read_bytes()).hexdigest(),target_rows=len(target),source_code_object_assertions=len(out),literal_grain_counts=dict(vocab),status_counts=l.status.value_counts().to_dict(),coordinate_missing_status_counts=l[l.coordinate_missing].status.value_counts().to_dict(),no_axis_or_point_adoption=True);(H/'exact_native_code_candidate_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)
if __name__=='__main__':main()
