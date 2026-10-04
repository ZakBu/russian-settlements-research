from pathlib import Path
import json,hashlib,time
import pandas as pd
import duckdb
from research_rebuild.mass_linkage.apply_reviewed_crimea2014_scoped_observations import append_observations_by_name
C=Path('/workspace/settlements-work/continuation_20261004');S=C/'independent_review/crimea_supplemental_application_staged';B=C/'accepted_mass_eighth_reviewed';L=C/'root/eighth_scoped2014_current309_reprojection/full_long_scoped2014_eighth_current309_context.parquet';O=C/'root/accepted_scoped_crimea22';O.mkdir(exist_ok=False)
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
r=json.loads((S/'staged_receipt.json').read_text());assert sha(S/'staged_receipt.json')=='b20d7daba44be6d797f742af1af559091b83d89af9a2e963a27b29a9b0d8cfb0'
obs=pd.read_parquet(S/'scoped_observations.parquet');edges=pd.read_parquet(S/'identity_links.parquet');points=pd.read_parquet(S/'retrospective_point_context.parquet');assert len(obs)==len(edges)==len(points)==22 and obs.population_value.notna().sum()==11 and obs.population_value.isna().sum()==11 and obs.population_value.sum()==207999
con=duckdb.connect(config={'threads':1,'memory_limit':'512MB'});ids=obs.current_2021_source_record_id.tolist();actual=con.execute('select source_record_id,entity_id,population_value from read_parquet(?) where record_type=\'census\' and source_record_id in (select unnest(?))',[str(L),ids]).fetchdf().set_index('source_record_id');assert len(actual)==22
cp=con.execute('select target_source_record_id,latitude,longitude,point_origin_file,point_origin_sha256,point_origin_locator,coordinate_admission_status from read_parquet(?) where target_source_record_id in (select unnest(?))',[str(B/'accepted_point_uses.parquet'),ids]).fetchdf().set_index('target_source_record_id');assert len(cp)==22
old=pd.read_parquet(C/'root/scoped2014_applied/accepted_scoped_observations_2014.parquet');assert not set(ids)&set(old.current_2021_source_record_id)
for x in obs.itertuples():
 a=actual.loc[x.current_2021_source_record_id];p=cp.loc[x.current_2021_source_record_id];assert x.entity_id==a.entity_id and int(x.current_2021_population_context)==int(a.population_value)
 for k in ['latitude','longitude','point_origin_file','point_origin_sha256','point_origin_locator']:assert getattr(x,k)==p[k],(x.observation_id,k)
assert sum(int(actual.loc[s].population_value) for s in ids)==210426
obs['census_2002_status']='outside_coverage_Russian_census_geography';obs['census_2010_status']='outside_coverage_Russian_census_geography';obs['layer_application_status']='accepted_scoped_2014_observation_or_literal_presence';obs['layer_application_basis']='root accepted independently reviewed exact physical place/current-native mapping; no Russian3 or boundary-comparability claim'
for name,frame in [('accepted_scoped_observations.parquet',obs),('accepted_scoped_identity_links.parquet',edges),('accepted_scoped_point_uses.parquet',points)]:frame.to_parquet(O/name,index=False)
con.close();t=time.monotonic();out=O/'eighth_full_long_with_1016scoped2014_current309.parquet';summary=append_observations_by_name(L,obs,out)
receipt={'status':'applied_independently_reviewed22_scoped2014_source_rows_and_identity_point_uses','rows':22,'numeric_population_rows':11,'literal_dash_NULL_rows':11,'numeric2014_population':207999,'current2021_population_new_available_scope_paths':210426,'source_population_modified':False,'Russian3_graph_modified':False,'strict_Russian3_population_gain':0,'input_review_baseline':'seventh; actual8 carrier/entity replay complete','inputs':{str(p):sha(p) for p in [S/'staged_receipt.json',S/'scoped_observations.parquet',S/'identity_links.parquet',S/'retrospective_point_context.parquet',L,B/'accepted_identity_edges.parquet',B/'accepted_point_uses.parquet']},'outputs':{p.name:sha(p) for p in O.glob('*.parquet')},'long_append':summary,'append_elapsed_seconds':time.monotonic()-t,'script_sha256':sha(__file__)};(O/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'status':receipt['status'],'rows':22,'long_append':summary},ensure_ascii=False))
