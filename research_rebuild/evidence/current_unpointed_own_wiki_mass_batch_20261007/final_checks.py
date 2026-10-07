from pathlib import Path
import sys,json,gzip,hashlib
import pandas as pd
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;W=R/'research_rebuild/work/current_unpointed_own_wiki_mass_batch_20261007';A=R/'research_rebuild/evidence/current_unpointed_own_wiki_mass_application_20261007';sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha,distance_km,normalize
s=load(17);ps=pd.read_csv(A/'accepted_point_use_delta.csv').fillna('');q=pd.read_csv(A/'accepted_qualified_physical_observations.csv').fillna('');checks=[];inputs={str(p):sha(p) for p in s.inputs};inputs[str(Path('/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_entities.tsv'))]=sha(Path('/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_entities.tsv'))
for r in ps.to_dict('records'):
 assert r['target_source_record_id'] not in s.point_rows
 assert -90<=r['latitude']<=90 and -180<=r['longitude']<=180
 inputs[r['point_origin_file']]=sha(Path(r['point_origin_file']));assert inputs[r['point_origin_file']]==r['point_origin_sha256']
 # Existing identity transfer must not contradict an independently active component point.
 component=s.obs[s.obs.root==s.uf.find(r['target_source_record_id'])]
 for sid in component.source_record_id:
  if sid in s.point_rows:assert distance_km((r['latitude'],r['longitude']),(s.point_rows[sid]['latitude'],s.point_rows[sid]['longitude']))<=5
assert not ps.target_source_record_id.duplicated().any()
for i,r in q.iterrows():
 if not r.source_record_id:continue
 b=s.by_id.loc[r.source_record_id];assert float(r.population_source_value)==float(b.population);assert r.population_quality==b.population_value_quality
 path=Path(r.source_path);h=sha(path);inputs[str(path)]=h;q.at[i,'source_sha256']=h
 if not r.source_locator:q.at[i,'source_locator']='selected source_record_id='+r.source_record_id
 if int(r.year)<2021:
  sheet,row=r.source_record_id.rsplit(':',2)[-2:];row=int(row)
  if sheet=='0':sheet=0
  d=pd.read_excel(path,sheet_name=sheet,header=None).iloc[row-1];text=' | '.join(str(z) for z in d if pd.notna(z));nums=pd.to_numeric(d.astype(str).str.replace(' ','',regex=False),errors='coerce')
  # Protected2010 values can differ from primary source; preserve selected value and expose exact direct cells.
  checks.append({'sid':r.source_record_id,'year':int(r.year),'selected_population_preserved':float(b.population),'population_quality':b.population_value_quality,'raw_value_matches':bool(nums.eq(b.population).any()),'own_name_in_native_row':normalize(b.settlement_name) in normalize(text),'raw_row_excerpt':text[:700],'source_file':str(path),'source_sha256':h,'source_locator':sheet.__str__()+'!row='+str(row)})
q.to_csv(A/'accepted_qualified_physical_observations.csv',index=False);pd.DataFrame(checks).to_csv(O/'historic_native_source_row_checks.csv',index=False)
assert all(c['own_name_in_native_row'] for c in checks)
for tid,g in q.groupby('trajectory_id'):assert set(g.year.astype(int))=={2002,2010,2021}
# No exact coordinate shared by differently bound accepted point objects within each year.
assert not ps.groupby(['target_year','latitude','longitude']).coordinate_source_record_id.nunique().gt(1).any()
for p in W.iterdir():
 if p.is_file():inputs[str(p)]=sha(p)
inputs[str(O/'all_current_own_binding_checks.csv')]=sha(O/'all_current_own_binding_checks.csv')
(O/'source_manifest.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2));receipt=json.loads((A/'application_receipt.json').read_text());receipt['validation']={'new_point_targets_not_already_active':True,'point_duplicates_distinct_objects':0,'active_component_coordinate_conflicts_over5km':0,'all_native_populations_and_qualities_preserved':True,'all_full3_exact_yearsets':True,'historic_native_raw_rows_checked':len(checks),'historical_raw_count_difference_exposed_not_overwritten':sum(not c['raw_value_matches'] for c in checks)};receipt['outputs']={str(p.name):sha(p) for p in A.glob('*.csv')};(A/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt['validation']))
# Compress our own initial exploratory full-row output; no external cache removed.
p=W/'unpointed.csv'
if p.exists():p.with_suffix('.csv.gz').write_bytes(gzip.compress(p.read_bytes()));p.unlink()
