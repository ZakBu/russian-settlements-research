#!/usr/bin/env python3
"""Replay raw 2021 publisher rows for the frozen 2002 hierarchy candidates.

Preserves official/native `oktmo` and hierarchy separately from Dadata helper
columns. This supplements, and never edits, the frozen candidate packet.
"""
import csv,hashlib,json,re
from pathlib import Path
import duckdb,pandas as pd

ROOT=Path('/workspace')
IN=ROOT/'settlements-work/continuation_20261004/R4/raw_2002_residual_admin_hierarchy_candidates_20261004/freeze_v4/identity_edge_point_candidates.csv'
RAW=ROOT/'settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet'
OUT=ROOT/'settlements-work/continuation_20261004/R4/raw_2002_residual_admin_hierarchy_candidates_20261004/current_raw_publisher_row_proofs_v2'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()
def txt(v):return '' if v is None or pd.isna(v) else str(v).strip()
def norm(v):return ' '.join(re.sub(r'[^а-яa-z0-9]+',' ',txt(v).casefold().replace('ё','е')).split())
def type_from_label(v):
 s=txt(v).casefold().replace('ё','е').strip()
 m=re.match(r'^(поселок городского типа|пгт|деревня|село|поселок|город|станица|ст-ца|хутор|аул|слобода|местечко)\s+',s)
 return (m.group(1) if m else '')
def main():
 if OUT.exists() and any(OUT.iterdir()):raise SystemExit(f'output exists: {OUT}')
 OUT.mkdir(parents=True,exist_ok=True)
 cands=pd.read_csv(IN,low_memory=False)
 ids=sorted(set(cands.to_source_record_id.astype(str)))
 rowids=sorted({int(x.rsplit('parquet:',1)[1]) for x in ids})
 con=duckdb.connect();con.execute("SET threads=1");con.execute("SET memory_limit='1GB'")
 # The row_number is the publisher parquet locator used in the selected ID.
 q=f"""SELECT row_number() OVER () AS row_1based,object_level,object_name,oktmo,region,mun_upper,mun_lower,settlement,population,
 settlement_fias_id_dadata,settlement_with_type_dadata,settlement_type_dadata,settlement_type_full_dadata,
 okato_dadata,oktmo_dadata,qc_geo_dadata,qc_dadata,latitude_dadata,longitude_dadata
 FROM read_parquet('{RAW}')"""
 # Use DuckDB's projected scan and fetch only the 2021 census row numbers.
 raw=con.execute(f"SELECT * FROM ({q}) WHERE row_1based IN ({','.join(map(str,rowids))})").df();con.close()
 rawsha=sha(RAW)
 rawmap={int(r.row_1based):r._asdict() for r in raw.itertuples(index=False)}
 out=[]
 for r in cands.drop_duplicates('to_source_record_id').to_dict('records'):
  rid=str(r['to_source_record_id']); row=int(r['to_source_row_1based']); a=rawmap.get(row)
  if a is None: out.append({'to_source_record_id':rid,'raw_row_1based':row,'status':'raw_row_not_found'});continue
  # In selected observations the non-Dadata native OKTMO, region, population,
  # mun_upper/mun_lower and typed publisher label are the current row inputs.
  source_type=txt(r['to_settlement_type']); raw_label=txt(a.get('object_name') or a.get('settlement'))
  out.append({'to_source_record_id':rid,'raw_row_1based':row,'status':'raw_row_replayed',
   'raw_source_file':str(RAW),'raw_source_sha256':rawsha,'raw_object_level':txt(a.get('object_level')),
   'raw_object_name':txt(a.get('object_name')),'raw_settlement_label':txt(a.get('settlement')),'raw_region':txt(a.get('region')),
   'raw_mun_upper_publisher_context':txt(a.get('mun_upper')),'raw_mun_lower_publisher_context':txt(a.get('mun_lower')),
   'raw_native_oktmo_publisher_column':txt(a.get('oktmo')),'raw_population':a.get('population'),
   'raw_dadata_oktmo_helper_separate':txt(a.get('oktmo_dadata')),'raw_dadata_okato_helper_separate':txt(a.get('okato_dadata')),
   'raw_dadata_type_helper_separate':txt(a.get('settlement_type_dadata')),'raw_dadata_coords_helper_separate_json':json.dumps({'latitude_dadata':a.get('latitude_dadata'),'longitude_dadata':a.get('longitude_dadata'),'qc_geo_dadata':a.get('qc_geo_dadata'),'qc_dadata':a.get('qc_dadata')},ensure_ascii=False),
   'selected_native_oktmo_equals_raw_publisher_oktmo':txt(r['to_native_oktmo_raw'])==txt(a.get('oktmo')),
   'selected_raw_name_equals_raw_publisher_object_name':norm(r['to_source_raw_name'])==norm(a.get('object_name')),
   'selected_name_equals_raw_publisher_name_after_type_prefix':norm(r['to_settlement_name'])==norm(re.sub(r'^(?:поселок городского типа|пгт|деревня|село|поселок|город|станица|ст-ца|хутор|аул|слобода|местечко)\s+','',txt(a.get('object_name')),flags=re.IGNORECASE)),
   'selected_type_equals_raw_publisher_type_prefix':norm(r['to_settlement_type'])==norm(type_from_label(a.get('object_name'))),
   'selected_region_equals_raw_publisher_region':norm(r['to_region_raw'])==norm(a.get('region')),
   'selected_district_equals_raw_mun_upper':norm(r['to_district_raw'])==norm(a.get('mun_upper')),
   'selected_municipality_equals_raw_mun_lower':norm(r['to_municipality_raw'])==norm(a.get('mun_lower')),
   'selected_population_equals_raw_publisher_population':int(float(r['to_population'] or 0))==int(a.get('population') or 0),
   'selected_type_raw':source_type,'publisher_typed_label_retained_raw':raw_label,
   'candidate_rule_family':r['rule_family'],'candidate_from_source_record_id':r['from_source_record_id']})
 with (OUT/'raw_2021_publisher_row_proofs.csv').open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(out[0]),extrasaction='raise');w.writeheader();w.writerows(out)
 checks=['selected_raw_name_equals_raw_publisher_object_name','selected_name_equals_raw_publisher_name_after_type_prefix','selected_type_equals_raw_publisher_type_prefix','selected_native_oktmo_equals_raw_publisher_oktmo','selected_region_equals_raw_publisher_region','selected_district_equals_raw_mun_upper','selected_municipality_equals_raw_mun_lower','selected_population_equals_raw_publisher_population']
 summary={'status':'read_only_raw_publisher_row_replay_candidate_only','candidate_file':str(IN),'candidate_file_sha256':sha(IN),'raw_2021_source':str(RAW),'raw_2021_source_sha256':rawsha,'candidate_targets':len(out),'raw_row_replayed':sum(x.get('status')=='raw_row_replayed' for x in out),'consistency_counts':{k:sum(bool(x.get(k)) for x in out) for k in checks},'note':'Official publisher oktmo and mun_upper/mun_lower are captured in distinct fields; Dadata helper columns are preserved separately and are not used as native identifiers or coordinates.'}
 summary['outputs']={'raw_2021_publisher_row_proofs.csv':{'sha256':sha(OUT/'raw_2021_publisher_row_proofs.csv'),'bytes':(OUT/'raw_2021_publisher_row_proofs.csv').stat().st_size}}
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 summary['outputs']['summary.json_sha256']=sha(OUT/'summary.json')
 (OUT/'receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
