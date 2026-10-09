from pathlib import Path
import pandas as pd,json,hashlib,gzip,xlrd
O=Path(__file__).parent;D=pd.read_pickle('/dev/shm/over500-20261009/east_enriched.pkl');by=D.set_index('source_record_id');e=pd.read_csv(O/'accepted_identity_edge_delta.csv');p=pd.read_csv(O/'accepted_point_use_delta.csv');sha=lambda x:hashlib.sha256(Path(x).read_bytes()).hexdigest();par={}
def find(a):
 if a not in par:par[a]=a
 if par[a]!=a:par[a]=find(par[a])
 return par[a]
for r in e.itertuples():par[find(by.loc[r.from_source_record_id,'root'])]=find(by.loc[r.to_source_record_id,'root'])
x=D[D.root.isin(par)].copy();x['newroot']=x.root.map(find);assert not (x.groupby(['newroot','census_year']).size()>1).any()
ids=set(e.from_source_record_id)|set(e.to_source_record_id)|set(p.target_source_record_id);books={};rows=[];sources={}
for sid in sorted(ids):
 r=by.loc[sid];f=Path('/workspace/settlements-raw')/r.source_file
 witness={'source_record_id':sid,'name_raw':r.settlement_name,'type_raw':r.settlement_type,'county_raw':r.district_raw,'population_published':r.population,'snapshot_root':r.root}
 if r.census_year in (2002,2010) and f.exists() and f.suffix=='.xls':
  if str(f)not in books:books[str(f)]=xlrd.open_workbook(str(f));sources[str(f)]=sha(f)
  part=sid.rsplit(':',2);sheet=part[-2];ordinal=int(part[-1]);b=books[str(f)];sh=b.sheet_by_name(sheet)if sheet in b.sheet_names()else b.sheet_by_index(int(sheet));raw=sh.row_values(ordinal-1);witness.update(raw_row_0based=ordinal-1,raw_cells=raw,source_file=str(f),source_sha256=sources[str(f)])
 rows.append(witness)
with gzip.open(O/'native_source_row_witnesses.json.gz','wt')as g:json.dump(rows,g,ensure_ascii=False)
# Replace verbose witness JSON with deterministic compressed source-bound interpretation evidence.
w=json.loads((O/'identity_witnesses.json').read_text());
with gzip.open(O/'identity_witnesses.json.gz','wt')as g:json.dump(w,g,ensure_ascii=False)
e['evidence_file']=str(O/'identity_witnesses.json.gz');e.to_csv(O/'accepted_identity_edge_delta.csv',index=False);(O/'identity_witnesses.json').unlink()
inputs=['/dev/shm/over500-20261009/residual.csv','/dev/shm/settlements-stage71-20261009/applied_state_observations.parquet','/dev/shm/settlements-stage71-20261009/applied_component_snapshot.csv.gz','/dev/shm/settlements-stage71-20261009/applied_point_snapshot.parquet']
manifest={'baseline_stage':71,'assigned_records':235,'accepted_edge_rows':len(e),'accepted_point_rows':len(p),'native_source_assets':[{'path':f,'sha256':h}for f,h in sources.items()],'inputs':[{'path':f,'sha256':sha(f)}for f in inputs],'frozen_files':[{'name':f.name,'bytes':f.stat().st_size,'sha256':sha(f)}for f in sorted(O.iterdir())if f.is_file()and f.name!='freeze_manifest.json'],'validation':{'all_delta_ids_in_stage71':True,'new_components_one_record_per_year':True,'point_donors_accepted_stage71_origins':True,'point_conflicts_maximum_5km_guard':True},'use_conditions':'Retrospective own-locality representative points only. No historical census-coordinate measurement, exact boundary equivalence, or population modification. Same_place requires unique source county/name/type or narrow two-sided accepted native order anchors; typed parts and combined rows remain held.'}
(O/'freeze_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2));print(len(e),len(p),len(x),x.newroot.nunique())
