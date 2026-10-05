import csv, hashlib, json, math, random
from pathlib import Path
import pandas as pd
from collections import defaultdict
base=Path('/workspace/russian-settlements-research/research_rebuild/evidence/top60_and_proximity_review_20261005')
out=base/'simple_rule_application'
out.mkdir(exist_ok=True)
p=base/'new_component_compatible_candidates_within5km.csv'
d=pd.read_csv(p)
carrier_path=base/'top60_existing_point_carrier_candidates.csv'
carriers=pd.read_csv(carrier_path)
# Exact unique selected name/type/region keys and a population ratio within 2.
carriers=carriers[(carriers.target_full_year_key_count==1)&(carriers.carrier_full_year_key_count==1)].copy()
carriers['population_ratio']=carriers[['target_population','carrier_population']].max(axis=1)/carriers[['target_population','carrier_population']].min(axis=1)
# The duplicated Tsibanobalk carrier rows share one old component; use 2010 as the one-edge bridge.
carriers=carriers.sort_values(['target_year','target_name','carrier_year']).drop_duplicates(['target_source_record_id'])
carriers=carriers[carriers.population_ratio<=2].copy()
if set(carriers.target_name)!= {'Дыгулыбгей','Дубовка','Цибанобалка','Углекаменск'} or len(carriers)!=4:
 raise ValueError('Top-60 exact unique point carriers changed; review required')
a=d.from_population.fillna(0); b=d.to_population.fillna(0)
d['population_ratio']=float('nan')
pos=(a>0)&(b>0)
d.loc[pos,'population_ratio']=d.loc[pos,['from_population','to_population']].max(axis=1)/d.loc[pos,['from_population','to_population']].min(axis=1)
d['growth_ratio_signed']=float('nan')
d.loc[pos,'growth_ratio_signed']=d.loc[pos,'to_population']/d.loc[pos,'from_population']
d['automatic_rule_result']='held'
d.loc[(d.reciprocal_unique==True)&pos&(d.population_ratio<=2)&(~d.component_year_overlap),'automatic_rule_result']='accepted_simple_rule'
d.loc[(d.reciprocal_unique==True)&pos&(d.population_ratio>2),'automatic_rule_result']='held_population_change_over_2x'
d.loc[(d.reciprocal_unique==False),'automatic_rule_result']='held_competing_nearest_match'
d.loc[~pos,'automatic_rule_result']='held_zero_or_unknown_population'
# Preserve baseline graph components and prevent a newly combined component from
# containing two rows from the same census.
parent={}; years={}
def find(x):
 parent.setdefault(x,x)
 if parent[x]!=x: parent[x]=find(parent[x])
 return parent[x]
def union(x,y):
 rx,ry=find(x),find(y)
 if rx==ry:return True
 if years[rx] & years[ry]:return False
 parent[ry]=rx; years[rx]|=years[ry]
 return True
for _,r in d.iterrows():
 x=str(r.from_component); y=str(r.to_component)
 parent.setdefault(x,x); parent.setdefault(y,y)
 # component labels already represent sets in input graph, derive sets from rows
for _,r in d.iterrows():
 years.setdefault(str(r.from_component),set()).add(int(r.from_year)); years.setdefault(str(r.to_component),set()).add(int(r.to_year))
# These candidate components are baseline labels; merge the eligible choices in deterministic order.
idx=d.index[d.automatic_rule_result.eq('accepted_simple_rule')].tolist()
idx.sort(key=lambda i:(float(d.at[i,'distance_m']),float(d.at[i,'population_ratio']),-max(float(d.at[i,'from_population']),float(d.at[i,'to_population'])),str(d.at[i,'from_id']),str(d.at[i,'to_id'])))
for i in idx:
 r=d.loc[i]; x=str(r.from_component); y=str(r.to_component)
 if not union(x,y):d.at[i,'automatic_rule_result']='held_would_duplicate_census_year_after_batch'
accepted=d[d.automatic_rule_result.eq('accepted_simple_rule')].copy()
holds=d[d.automatic_rule_result.ne('accepted_simple_rule')].copy()
accepted['decision_status']='checked_rule_accepted'
accepted['relation']='same_place'
accepted['decision_id']=[f'SIMPLE5KM-{r.from_year}-{r.to_year}-{hashlib.sha256((str(r.from_id)+"|"+str(r.to_id)).encode()).hexdigest()[:12]}' for r in accepted.itertuples()]
accepted['boundary_comparability_asserted']=False
accepted['population_comparability_asserted']=False
accepted['decision_basis']='exact_normalized_name_region_mutual_nearest_le_5km_population_ratio_le_2'
accepted.to_csv(out/'accepted_identity_edge_delta.csv',index=False)
holds.to_csv(out/'held_candidates.csv',index=False)
outliers=d[(pos)&(d.population_ratio>20)].copy().sort_values('population_ratio',ascending=False)
outliers.to_csv(out/'population_change_over_20x.csv',index=False)
# Fixed-seed random descriptive audit slice; this is not a precision estimate.
rng=random.Random(20261005)
sample_idx=sorted(rng.sample(list(accepted.index),min(60,len(accepted)))) if len(accepted) else []
accepted.loc[sample_idx].to_csv(out/'fixed_seed_sample_60.csv',index=False)
# Four direct point transfers for unpointed top-60 rows; coordinates remain sourced from the accepted carrier.
point_delta=carriers[['target_year','target_source_record_id','target_name','target_type','target_population','target_population_quality','carrier_year','carrier_source_record_id','carrier_latitude','carrier_longitude','carrier_coordinate_source','carrier_coordinate_admission_status','carrier_provider_id','carrier_source_file','carrier_source_sheet','carrier_source_row']].copy()
point_delta['coordinate_admission_status']='reviewed_case_accepted'
point_delta['coordinate_application_family']='simple_exact_unique_name_type_region_carrier_20261005'
point_delta['coordinate_interpretation']='accepted representative point reused from exact unique inter-census carrier; measurement date and boundary comparability unknown'
point_delta['population_value_changed']=False
point_delta['provider_identifier_binding_asserted']=False
point_delta['source_row_carrier_key_unique']=True
point_delta.to_csv(out/'top60_point_use_delta.csv',index=False)
# Extend accepted identity decisions to these four exact unique carrier pairs.
case_edges=point_delta.rename(columns={'carrier_source_record_id':'from_id','target_source_record_id':'to_id','carrier_year':'from_year','target_year':'to_year','target_name':'settlement_name','target_type':'to_type','carrier_coordinate_source':'from_coordinate_source','carrier_latitude':'from_latitude','carrier_longitude':'from_longitude'})[['from_year','to_year','from_id','to_id','settlement_name','to_type','from_latitude','from_longitude','from_coordinate_source']].copy()
case_edges['decision_status']='case_specific_independent_review_accepted'
case_edges['decision_basis']='exact unique selected name type region; accepted point carrier; population ratio <=2'
case_edges['population_comparability_asserted']=False
case_edges['boundary_comparability_asserted']=False
case_edges.to_csv(out/'top60_identity_edge_delta.csv',index=False)
# Grouped application counts and demographic-ratio summary.
summary={
 'source_csv_sha256':hashlib.file_digest(p.open('rb'),'sha256').hexdigest(),
 'carrier_csv_sha256':hashlib.file_digest(carrier_path.open('rb'),'sha256').hexdigest(),
 'candidate_pairs':int(len(d)),
 'accepted_rule_links':int(len(accepted)),
 'top60_point_uses_added':int(len(point_delta)),
 'top60_point_population_added_by_target_year':{str(int(y)):int(v) for y,v in point_delta.groupby('target_year').target_population.sum().items()},
 'accepted_pairs_by_year_pair':{f'{a}-{b}':int(n) for (a,b),n in accepted.groupby(['from_year','to_year']).size().items()},
 'accepted_unique_population_endpoints':{str(y):int(pd.concat([accepted.loc[accepted.from_year.eq(y),['from_id','from_population']].rename(columns={'from_id':'id','from_population':'population'}),accepted.loc[accepted.to_year.eq(y),['to_id','to_population']].rename(columns={'to_id':'id','to_population':'population'})]).drop_duplicates('id').population.sum()) for y in [2002,2010,2021]},
 'positive_positive_population_pairs':int(pos.sum()),
 'population_ratio_gt_2_positive_positive':int(((d.population_ratio>2)&pos).sum()),
 'population_ratio_gt_20_positive_positive':int(((d.population_ratio>20)&pos).sum()),
 'population_ratio_gt_20_held':int(((d.population_ratio>20)&pos&(d.automatic_rule_result!='accepted_simple_rule')).sum()),
 'zero_or_unknown_population_pairs_held':int((~pos).sum()),
 'non_mutual_pairs_held':int((~d.reciprocal_unique).sum()),
 'sample_size':len(sample_idx),'sample_seed':20261005,
 'sample_note':'Descriptive fixed-seed inspection slice only; it does not estimate linkage precision because no independently labeled truth set is available.',
 'rule':'exact normalized settlement name and region; mutual nearest points across each year pair; distance <=5000m; positive population ratio in [0.5,2.0]; no duplicate census year introduced in the batch.',
 'same_year_coordinate_collision_rebinding':'No global coordinate replacement. A repeated point is only reassigned where source-specific candidate evidence supports a distinct point.'}
(out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
