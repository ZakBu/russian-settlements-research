from pathlib import Path
import json,hashlib,pandas as pd,xlrd,gzip
O=Path(__file__).parent;sha=lambda x:hashlib.sha256(Path(x).read_bytes()).hexdigest();D=pd.read_pickle('/dev/shm/over500-20261009/east_enriched.pkl');by=D.set_index('source_record_id');E=pd.concat([pd.read_csv(O.parent/'accepted_identity_edge_delta.csv'),pd.read_csv(O.parent/'subbatch2/accepted_identity_edge_delta.csv'),pd.read_csv(O/'accepted_identity_edge_delta.csv')]);par={}
def find(a):
 if a not in par:par[a]=a
 if par[a]!=a:par[a]=find(par[a])
 return par[a]
for e in E.itertuples():par[find(by.loc[e.from_source_record_id,'root'])]=find(by.loc[e.to_source_record_id,'root'])
g=D[D.root.isin(par)].copy();g['newroot']=g.root.map(find);assert not(g.groupby(['newroot','census_year']).size()>1).any()
A=pd.read_csv(O/'accepted_available_year_statuses.csv');T=pd.read_csv(O/'accepted_typed_lifecycle_event_delta.csv');e=pd.read_csv(O/'accepted_identity_edge_delta.csv');p=pd.read_csv(O/'accepted_point_use_delta.csv');ids=set(e.from_source_record_id)|set(e.to_source_record_id)|set(p.target_source_record_id)|set(A.target_source_record_id);books={};assets={};w=[]
for sid in sorted(ids):
 r=by.loc[sid];v=dict(source_record_id=sid,name_raw=r.settlement_name,type_raw=r.settlement_type,county_raw=r.district_raw,population_published=r.population,source_value_modified=False)
 f=Path('/workspace/settlements-raw')/r.source_file
 if f.is_file()and f.suffix=='.xls':
  if str(f)not in books:books[str(f)]=xlrd.open_workbook(str(f));assets[str(f)]=sha(f)
  ordinal=int(sid.rsplit(':',1)[1]);shname=sid.rsplit(':',2)[1];b=books[str(f)];sh=b.sheet_by_name(shname)if shname in b.sheet_names()else b.sheet_by_index(int(shname));v.update(source_path=str(f),source_sha256=assets[str(f)],raw_row_0based=ordinal-1,raw_cells=sh.row_values(ordinal-1))
 w.append(v)
with gzip.open(O/'native_source_row_witnesses.json.gz','wt')as f:json.dump(w,f,ensure_ascii=False)
d=[]
for sid in sorted(ids):d.append(dict(source_record_id=sid,region_norm=by.loc[sid,'region_norm'],settlement_name=by.loc[sid,'settlement_name'],census_year=by.loc[sid,'census_year'],disposition='accepted_separate_dated_abolition_available_year_path'if sid in set(A.target_source_record_id)else'accepted_sourcecounty_own_article_native_spelling_continuity',source_population_value_preserved=True,source_population_quality_preserved=True))
pd.DataFrame(d).to_csv(O/'record_dispositions.csv',index=False)
M={'baseline_stage':71,'depends_on':[{'path':str(z),'sha256':sha(z)}for z in [O.parent/'freeze_manifest.json',O.parent/'subbatch2/freeze_manifest.json']],'accepted_edge_rows':len(e),'accepted_point_rows':len(p),'accepted_lifecycle_events':len(T),'available_year_status_rows':len(A),'affected_native_UIDs':len(ids),'all_three_batches_component_year_unique':True,'separate_lifecycle_not_ordinary_same_place':True,'dates_are_cited_act_dates_exact_physical_cessation_not_asserted':True,'native_source_assets':[dict(path=f,sha256=h)for f,h in assets.items()],'frozen_files':[dict(name=f.name,bytes=f.stat().st_size,sha256=sha(f))for f in sorted(O.iterdir())if f.is_file()and f.name!='freeze_manifest.json']};(O/'freeze_manifest.json').write_text(json.dumps(M,ensure_ascii=False,indent=2));print(M['affected_native_UIDs'])
