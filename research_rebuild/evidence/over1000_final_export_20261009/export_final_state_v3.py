"""Call inside the final successful root recipe; never replay a guessed stage."""
from pathlib import Path
import sys,json,csv,gzip,io,hashlib,math,shutil
import pandas as pd
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]; E=ROOT/'research_rebuild/evidence'; BASE=E/'main_axis_residual_application68_20261008'
sys.path.insert(0,str(BASE));sys.path.insert(0,str(HERE))
from stream_point_snapshot import write_point_snapshot_from_active_rows
import export_full3_final_adapter as wide
YEARS=(2002,2010,2021)
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def gziprows(path,fields,rows):
 with Path(path).open('wb') as raw,gzip.GzipFile(fileobj=raw,mode='wb',filename='',mtime=0,compresslevel=9) as z,io.TextIOWrapper(z,encoding='utf8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
def export_final_state(state,credited_ids,output_dir,recipe_output_dir,pins,stage_label,event_ids=(),joint=None,scope=None,expected_coverage=None):
 """Export final accepted graph PLUS typed source-year credit and scope overlays."""
 out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
 assert not (out/'release-assets-manifest.json').exists(),'Refuse overwrite of a certified export'
 ids=set(credited_ids);eventids=set(event_ids); assert state.obs.source_record_id.is_unique
 obs=state.obs.copy();obs['root']=obs.source_record_id.map(state.uf.find)
 assert ids<=set(obs.source_record_id)
 obs.to_parquet(out/'applied_state_observations.parquet',index=False,compression='zstd')
 components=obs[['source_record_id','root']].copy();components['component_years']=components.root.map(lambda r:','.join(map(str,sorted(state.years[r]))))
 components.to_csv(out/'applied_component_snapshot.csv.gz',index=False,compression={'method':'gzip','mtime':0})
 write_point_snapshot_from_active_rows(state.point_rows,out/'applied_point_snapshot.parquet')
 ordinary=obs[obs.is_additive_settlement_record.fillna(False)&~obs.region_norm.isin(['москва','санкт петербург','севастополь'])&~((obs.census_year==2021)&obs.region_norm.eq('крым'))].copy()
 # Exclude typed wrong-grain rows only from ordinary wide eligibility; retain
 # complete State observations and their explicit source-scope overlay.
 if scope is not None and len(scope):
  ordinary=ordinary[~ordinary.source_record_id.isin(set(scope.source_record_id))].copy()
 groups={}
 for sid,y,r,pop in ordinary[['source_record_id','census_year','root','population']].itertuples(index=False,name=None):groups.setdefault(r,[]).append((sid,int(y),pop))
 full3={r for r,g in groups.items() if len(g)==3 and {x[1] for x in g}==set(YEARS) and all(sid in state.point_rows and pd.notna(pop) and math.isfinite(float(pop)) for sid,y,pop in g)}
 componentpoints={sid for sid,y,r in ordinary[['source_record_id','census_year','root']].itertuples(index=False,name=None) if r in full3}
 assert componentpoints<=ids,'Every strict ordinary wide ID must be in final primary credit union'
 primary_overlay=ROOT/'publication/stage68/applied_primary_population_source_overlay_2010.csv.gz'
 overlay=pd.read_csv(primary_overlay,keep_default_na=False).set_index('original_source_record_id');assert overlay.index.is_unique
 credit=obs[obs.source_record_id.isin(ids)].copy();credit['component_root']=credit.root;credit['finite_ordinary_full3_all_ownpoints']=credit.root.isin(full3)
 credit['final_typed_available_year_or_event_credit']=credit.source_record_id.isin(eventids);credit['effective_population']=credit.population
 credit['joint_reporting_scope_association']=credit.source_record_id.isin(set(joint.source_record_id) if joint is not None and len(joint) else set())
 credit['point_presence']=credit.source_record_id.isin(state.point_rows)
 for idx,r in credit[credit.census_year.eq(2010)].iterrows():
  if r.source_record_id in overlay.index:
   q=overlay.loc[r.source_record_id];assert float(r.population)==float(q.original_population)
   credit.loc[idx,'effective_population']=float(q.population)
 baseline_credit=pd.read_csv(BASE/'applied_primary_credited_UID_roster.csv.gz',keep_default_na=False).set_index('source_record_id')
 for column in baseline_credit.columns:
  if column.startswith('explicit_') or column=='supplemental_secondary2002_source_observation':
   credit[column]=credit.source_record_id.map(baseline_credit[column]).map(lambda value: str(value).lower() in {'true','1','1.0'})
 credit.to_csv(out/'applied_primary_credited_UID_roster.csv.gz',index=False,compression={'method':'gzip','mtime':0})
 credit_full=credit.copy()
 for field in wide.POINT_FIELDS:
  credit_full['accepted_point_'+field]=credit.source_record_id.map(lambda sid:str(wide.clean(state.point_rows.get(sid,{}).get(field,''))))
 credit_full.to_parquet(out/'primary_credited_source_year_full.parquet',index=False,compression='zstd')
 del credit_full
 # Raw ordinary export uses the existing deterministic entity UID/provenance recipe.
 wide.DEST=out
 pins=dict(pins)
 for p in state.inputs:
  p=Path(p);pins[str(p)]={'sha256':sha(p),'bytes':p.stat().st_size}
 exportreceipt=wide.build(state,ordinary,componentpoints,int(stage_label.split("_",1)[0]),dict(pins),HERE,reuse=False)
 # build writes small receipts next to adapter; move those to delivered bundle.
 for name in ['export_receipt.json','export_source_hash_manifest.json','export_recipe.md']:
  shutil.move(str(HERE/name),str(out/name))
 fields=json.loads((HERE/'wide135_schema.json').read_text());assert len(fields)==135
 main=out/'ordinary_full3_all_own_points_complete_numbers.csv.gz'
 sums={y:0 for y in YEARS};rows=0
 def transformed():
  nonlocal rows
  with gzip.open(main,'rt',encoding='utf8',newline='') as f:
   for row in csv.DictReader(f):
    sid=row['source_record_id_2010']
    if sid in overlay.index:
     q=overlay.loc[sid];assert float(row['population_2010'])==float(q.original_population)
     for k in fields:
      if k.startswith('original_') and k.endswith('_2010'):
       base=k[len('original_'):];row[k]=row.get(base,'')
     row['original_source_record_id_2010']=sid
     for a,b in {'population':'population','population_value_quality':'population_value_quality','source_file':'population_source_path','source_path':'population_source_path','source_sha256':'population_source_sha256','source_locator':'population_source_locator','source_actual_path':'population_source_path','source_actual_sha256':'population_source_sha256'}.items():row[a+'_2010']=Path(q[b]).name if a=='source_file' else q[b]
     row['source_actual_resolution_status_2010']='reviewed_primary_population_source_overlay_cached_provenance'
     for a,b in {'population_source_record_id':'population_source_record_id','population_source_name_raw':'population_source_name_raw','population_source_type_raw':'population_source_type_raw','population_source_census_date':'census_date','population_source_publication_date':'publication_date','population_source_binding_status':'population_source_binding_status','population_source_application_status':'population_source_application_status','population_source_context_method':'binding_context_method'}.items():row[a+'_2010']=q[b]
     row['population_source_binding_native_record_id_2010']=sid;row['population_source_overlay_input_sha256_2010']=sha(primary_overlay)
    rows+=1
    for y in YEARS:sums[y]+=int(float(row[f'population_{y}']))
    yield row
 gziprows(out/'ordinary_full3_with_primary_population_sources.csv.gz',fields,transformed())
 main.unlink()  # Raw values remain in State obs and per-year original overlay columns; avoid duplicate wide download.
 rawreceipt=json.loads((out/'export_receipt.json').read_text());rawreceipt['file_is_intermediate_not_release_asset']=True
 (out/'export_receipt.json').write_text(json.dumps(rawreceipt,ensure_ascii=False,indent=2)+'\n')
 # These records are overlays, not deletions or graph unions. Copy complete final axis outputs.
 sourceout=Path(recipe_output_dir)
 for p in sourceout.glob('*'):
  if p.is_file() and any(x in p.name for x in ['scope','joint','exclusion','application_receipt']):shutil.copyfile(p,out/p.name)
 shutil.copyfile(primary_overlay,out/primary_overlay.name)
 effective={str(int(y)):int(g.effective_population.sum()) for y,g in credit.groupby('census_year')}
 fedpath=E/'federal_territory_spatial_overlay_20261005/federal_territory_observations.csv'
 fed=pd.read_csv(fedpath,keep_default_na=False)
 fed=fed[fed.region_norm.isin(['москва','санкт петербург'])].copy()
 assert len(fed)==6 and fed.territory_key.nunique()==2 and not fed[['territory_key','census_year']].duplicated().any()
 federal={str(y):int(fed.loc[fed.census_year.eq(y),'territory_population'].sum()) for y in YEARS}
 assert list(federal.values())==[15043973,16383067,18612023]
 assert not ids.intersection(set(fed.population_source_record_id))
 assert not credit.region_norm.isin(['москва','санкт петербург']).any(),'Federal children must not be added twice'
 fed.to_csv(out/'accepted_common_federal_territory_axis.csv',index=False)
 combined={y:effective[y]+federal[y] for y in effective}
 if expected_coverage:
  assert combined=={str(y):int(v['population']) for y,v in expected_coverage.items()},(combined,expected_coverage)
 assert set(pd.read_csv(out/'applied_primary_credited_UID_roster.csv.gz',usecols=['source_record_id']).source_record_id)==ids
 assert len(pd.read_parquet(out/'applied_state_observations.parquet',columns=['source_record_id']))==len(obs)
 receipt=dict(status='final_state_full_export',working_stage=stage_label,selected_observation_rows=len(obs),active_point_rows=len(state.point_rows),primary_UID_rows=len(credit),ordinary_wide_rows=rows,ordinary_wide_columns=135,ordinary_effective_population=sums,primary_native_UID_effective_population=effective,federal_territory_population=federal,primary_effective_population_including_federal=combined,federal_axis_source_sha256=sha(fedpath),counts_not_imputed=True,typed_routes_not_forced_into_ordinary_full3=True,source_scope_corrections_retained_as_overlays=True,recipe_output_dir=str(sourceout))
 (out/'full_export_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 manifest=dict(status='verified_final_full_assets',working_stage=stage_label,assets=[dict(name=p.name,bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(out.iterdir()) if p.is_file() and p.name!='release-assets-manifest.json'])
 (out/'release-assets-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');return receipt
