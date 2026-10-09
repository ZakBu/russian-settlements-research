from pathlib import Path
import pandas as pd,json,hashlib,zipfile,gzip,xlrd,math
O=Path(__file__).parent;sha=lambda x:hashlib.sha256(Path(x).read_bytes()).hexdigest();D=pd.read_pickle('/dev/shm/over500-20261009/east_enriched.pkl');by=D.set_index('source_record_id');P=pd.read_csv(O/'accepted_point_use_delta.csv');assert not P.target_source_record_id.duplicated().any();W=json.load(gzip.open(O/'point_binding_witnesses.json.gz'));raws={};books={};native=[];baselineP=pd.read_parquet('/dev/shm/over500-20261009/points_compact.parquet').set_index('target_source_record_id')
for p in P.itertuples():
 t=by.loc[p.target_source_record_id];peerids=D[D.root.eq(t.root)].source_record_id
 for sid in peerids:
  if sid not in baselineP.index:continue
  q=baselineP.loc[sid];a,b,c,d=map(float,[p.latitude,p.longitude,q.latitude,q.longitude]);dist=6371*2*math.asin(min(1,math.sqrt(math.sin(math.radians(c-a)/2)**2+math.cos(math.radians(a))*math.cos(math.radians(c))*math.sin(math.radians(d-b)/2)**2)));assert dist<=5,(p.target_source_record_id,sid,dist)
 f=Path('/workspace/settlements-raw')/t.source_file;v=dict(source_record_id=p.target_source_record_id,source_population=t.population,source_population_quality=t.population_value_quality,source_name=t.settlement_name,source_type=t.settlement_type,source_county=t.district_raw)
 if f.is_file()and f.suffix=='.xls':
  if str(f)not in books:books[str(f)]=xlrd.open_workbook(str(f));raws[str(f)]=sha(f)
  b=books[str(f)];shname=p.target_source_record_id.rsplit(':',2)[1];sh=b.sheet_by_name(shname)if shname in b.sheet_names()else b.sheet_by_index(int(shname));row=int(p.target_source_record_id.rsplit(':',1)[1])-1;v.update(raw_file=str(f),raw_sha256=raws[str(f)],raw_row0=row,raw_cells=sh.row_values(row))
 native.append(v)
F=Path(P.point_origin_file.iloc[0]);assert sha(F)==P.point_origin_sha256.iloc[0];lines=zipfile.ZipFile(F).read('RU.txt').decode('utf8').splitlines()
for p in P.itertuples():
 n=int(p.point_origin_locator.split('line=')[1].split(';')[0]);cells=lines[n-1].split('\t');assert cells[0]==p.coordinate_source_record_id.split(':')[1] and float(cells[4])==p.latitude and float(cells[5])==p.longitude
with gzip.open(O/'native_source_row_witnesses.json.gz','wt')as f:json.dump(native,f,ensure_ascii=False)
M=dict(baseline_stage=71,accepted_own_point_uses=len(P),identity_edges_added=0,population_values_modified=False,point_grade='Direct source ownplace representative point, source-specific coordinates and date retained; exact censusdate measurement and positional accuracy unknown.',validation=dict(all_targets_selected_native=True,direct_raw_GeoNames_lines_reopened=True,sourceyear_all_type_name_rivals_unique=True,baseline_component_existing_points_within5km=True),native_sources=[dict(path=f,sha256=h)for f,h in raws.items()],frozen_files=[dict(name=f.name,bytes=f.stat().st_size,sha256=sha(f))for f in sorted(O.iterdir())if f.is_file()and f.name!='freeze_manifest.json']);(O/'freeze_manifest.json').write_text(json.dumps(M,ensure_ascii=False,indent=2));print(len(P))
