from pathlib import Path
import json,gzip,zipfile,duckdb,pandas as pd,hashlib
O=Path(__file__).parent;F=O/'source_positive_geographic_candidates.csv.gz';f=pd.read_csv(F,dtype=str,keep_default_na=False);RAW='/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet';c=duckdb.connect();raw=c.execute('select row_number() over() rn,object_level,object_name,oktmo,region,mun_upper,mun_lower from read_parquet(?)',[RAW]).fetchdf().set_index('rn');c.close();need={};livechecks=0
for z in f.to_dict('records'):
 n=json.loads(z['native_primary_row_json']);rn=int(z['source_record_id'].rsplit(':',1)[1]);literal=raw.loc[rn].to_dict();assert all(str(literal[k])==str(v) for k,v in n.items() if k!='rn'),(rn,n,literal)
 q=json.loads(z['chosen_raw_source_json'])
 if 'raw' in q:need[(q['member'],q['line'])]=(q,z)
 else:
  r=json.load(gzip.open(q['source_response_file'],'rt'));i=int(q['source_locator'].split('[')[1].split(']')[0]);p=r[i] if isinstance(r,list) else r['results'][i];assert p==q['raw_ownplace_result'];assert float(p['lat'])==float(z['latitude']) and float(p['lon'])==float(z['longitude']);livechecks+=1
cachechecks=0
with zipfile.ZipFile('/workspace/settlements-work/coordinate_first_20261008/sources/osm_geoapify_ru.zip') as zp:
 for member in {m for m,ln in need}:
  with zp.open(member) as fh:
   for ln,line in enumerate(fh,1):
    if (member,ln) not in need:continue
    q,z=need[(member,ln)];assert line.decode().rstrip()==q['raw_line'];assert json.loads(line)==q['raw'];p=q['raw'];assert float(p['location'][1])==float(z['latitude']) and float(p['location'][0])==float(z['longitude']);cachechecks+=1
assert cachechecks+livechecks==len(f)
(O/'source_literal_verification.json').write_text(json.dumps({'native_rows_reopened_equal':len(f),'cached_OSM_full_rawlines_reopened_equal':cachechecks,'live_complete_raw_results_reopened_equal':livechecks,'literal_coordinates_equal':len(f),'source_positive_count_not_admission':len(f)},indent=2));print(cachechecks,livechecks)
