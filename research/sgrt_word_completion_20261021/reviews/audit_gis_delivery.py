from pathlib import Path
import json,hashlib,sqlite3,zipfile,struct
import pandas as pd,numpy as np
H=Path(__file__).resolve().parent;R=H.parents[2];D=H.parent/'delivery';r=json.loads((D/'SGRT_output_word_ci_2021_baseline.receipt.json').read_text());G=D/r['path'];Z=D/r['archive'];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();checks=[]
def ck(k,v):checks.append(dict(check=k,pass_=bool(v)))
ck('gpkg_exact_export_sha',sha(G)==r['sha256']);ck('zip_exact_export_sha',sha(Z)==r['archive_sha256'])
with zipfile.ZipFile(Z) as z:ck('zip_CRC',z.testzip() is None);ck('zip_member_same_actual_gpkg',hashlib.sha256(z.read(G.name)).hexdigest()==sha(G))
for k,v in r['input_sha256'].items():p=Path(k);p=p if p.is_absolute() else R/p;ck('source_sha:'+k,p.exists() and sha(p)==v)
c=sqlite3.connect(f'file:{G}?mode=ro',uri=True);ck('sqlite_integrity',c.execute('pragma integrity_check').fetchall()==[('ok',)]);ck('foreign_keys',not c.execute('pragma foreign_key_check').fetchall());meta=c.execute('select table_name,data_type,srs_id from gpkg_contents').fetchall();counts={}
for layer in r['layers']:
 name=layer['layer'];count=c.execute(f'select count(*) from "{name}"').fetchone()[0];counts[name]=count;ck(name+':rowcount',count==layer['rows'])
for table,datatype,srid in meta:
 if datatype!='features':continue
 ck(table+':crs4326',srid==4326);ck(table+':POINTschema',c.execute('select geometry_type_name from gpkg_geometry_columns where table_name=?',(table,)).fetchone()[0]=='POINT');good=True
 for geom,lon,lat in c.execute(f'select geom,lon,lat from "{table}"'):
  if not geom or geom[:2]!=b'GP':good=False;break
  flags=geom[3];endian='<' if flags&1 else '>';header=8+{0:0,1:32,2:48,3:48,4:64}[(flags>>1)&7];wkb=geom[header:];we='<' if wkb[0]==1 else '>';typ,x,y=struct.unpack(we+'Idd',wkb[1:]);srs=struct.unpack(endian+'i',geom[4:8])[0]
  if typ!=1 or srs!=4326 or not np.isclose(x,lon,rtol=0,atol=1e-10) or not np.isclose(y,lat,rtol=0,atol=1e-10):good=False;break
 ck(table+':all_geometry_matches_attributes',good)
M=H.parent/'model/output_word_ci_2021_baseline';nodes=pd.read_parquet(M/'nodes.parquet');gids=set(v[0] for v in c.execute('select id from settlements'));uids=set(v[0] for v in c.execute('select id from unlocated_source_entities'));ck('every_modelid_once_located_or_unlocated',not gids&uids and gids|uids==set(nodes.id));canon=pd.read_parquet(H.parent/'typology/canonical/output_word_ci_2021_baseline/operational_type_candidates.parquet');actual=[]
for lev in [1,2,3,4]:
 table=f'systems_level{lev}'
 for typ in range(1,10):
  values=c.execute(f'select center_id from {table} where word_type{typ}_operational_hypothesis=1').fetchall();actual.extend((lev,v[0],typ) for v in values)
ck('all22_canonical_type_attributes_exact',set(actual)==set(map(tuple,canon[['level','center_id','word_type']].to_numpy())) and len(actual)==22);ck('broad64_separate',counts['broad_prototypes_not_literal_word_types']==64);out=dict(status='PORTABLE_GIS_INDEPENDENTLY_VERIFIED' if all(v['pass_'] for v in checks) else 'RETURN_TO_REPAIR_LOOP',n_checks=len(checks),n_failed=sum(not v['pass_'] for v in checks),checks=checks,layer_counts=counts,canonical_type_attributes=len(actual),source_sha256={str(p):sha(p) for p in [G,Z,D/'SGRT_output_word_ci_2021_baseline.receipt.json']},scope='Independent SQLite/ZIP/WKB decode ofeverygeometry andallcanonicaltype flags/sourcebindings. POINT membership geography, not independently observedterritorialboundaries.');(H/'gis_delivery_independent_audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ['checks','source_sha256']},ensure_ascii=False,indent=2))
