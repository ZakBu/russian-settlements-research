import json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'mass_linkage'))
from current_chain_state_20261007 import sha
from build_long_table import ACCEPTED_COORDINATE_STATUSES,ACCEPTED_EDGE_STATUSES
out=Path(__file__).resolve().parent;cache=Path('/dev/shm/settlements-stage71-20261009');obs=pd.read_parquet(cache/'applied_state_observations.parquet');by=obs.set_index('source_record_id');root=by.root.to_dict();years=obs.groupby('root').census_year.agg(lambda x:set(x)).to_dict();e=pd.read_csv(out/'accepted_identity_edge_delta.csv');p=pd.read_csv(out/'accepted_point_use_delta.csv');d=pd.read_csv(out/'dispositions.csv');original=pd.read_csv('/dev/shm/over500-20261009/residual.csv');m=json.loads((out/'manifest.json').read_text());redundant=0;kept=[]
assert set(e.decision_status)<=ACCEPTED_EDGE_STATUSES;assert set(p.coordinate_admission_status)<=ACCEPTED_COORDINATE_STATUSES;assert p.target_source_record_id.is_unique;assert d.source_record_id.is_unique;assert set(d.source_record_id)==set(original[original.region_norm.isin(m['regions'])].source_record_id)
for i,q in e.iterrows():
 a,b=root[q.from_source_record_id],root[q.to_source_record_id]
 if a==b:redundant+=1;continue
 assert not(years[a]&years[b]),(q.from_source_record_id,q.to_source_record_id,years[a],years[b]);years[a]|=years.pop(b)
 for k,v in list(root.items()):
  if v==b:root[k]=a
 kept.append(i)
e=e.loc[kept];e.to_csv(out/'accepted_identity_edge_delta.csv',index=False)
assert p.latitude.between(-90,90).all() and p.longitude.between(-180,180).all()
for q in p.to_dict('records'):
 assert q['target_source_record_id'] in by.index
 source=q.get('point_origin_file')
 if pd.notna(source) and source:assert sha(Path(source))==q['point_origin_sha256']
for i,q in d.iterrows():d.loc[i,'component_years_after']=','.join(map(str,sorted(years[root[q.source_record_id]])))
d.to_csv(out/'dispositions.csv',index=False)
for file,digest in m['inputs_sha256'].items():assert sha(Path(file))==digest,file
m['accepted_identity_edges']=len(e);m['outputs_sha256']={f.name:sha(f) for f in out.iterdir() if f.suffix in ['.csv','.gz']};m['builder_sha256']={f.name:sha(f) for f in out.glob('*.py')};m['validation']={'canonical_statuses_pass':True,'unique_point_targets_pass':True,'all_assigned_source_ids_disposed':True,'frozen_input_hashes_pass':True,'graph_census_year_conflicts':0,'effective_component_merges':len(e),'already_connected_redundant_rows_removed':redundant,'population_values_modified':False};(out/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n');print(json.dumps(m['validation']))
