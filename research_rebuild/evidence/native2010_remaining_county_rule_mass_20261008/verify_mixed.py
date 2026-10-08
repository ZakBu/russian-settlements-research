import sys,json
from pathlib import Path
import pandas as pd,numpy as np
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha
from apply import apply
s=load(49)
def finite_ids(state):
 obs=state.obs;bad=~obs.source_record_id.isin(state.point_rows)|~np.isfinite(obs.population);badroots=set(obs.loc[bad,'root']);badroots.update(state.uf.find(i) for i in state.conflicting_point_targets);roots={r for r in obs.root.unique() if state.years[r]=={2002,2010,2021} and r not in badroots};return set(obs.loc[obs.root.isin(roots),'source_record_id'])
previous=json.loads((O/'native_ID_union_marginal_receipt.json').read_text()) if (O/'native_ID_union_marginal_receipt.json').exists() else {}
basefinite=finite_ids(s);orig=set(basefinite);direct=set();formation=set();pins={};provenance=[]
for n,target in [('complete_publisher_partition_members.csv',orig),('qualified_scope_source_id_credit_union.csv',orig),('named_merger_lineage_constituents.csv',orig),('complete_territorial_scope_constituents.csv',orig),('direct_inclusion_transformation_path_native_credit_union.csv',direct),('formation_path_native_credit_union.csv',formation)]:
 p=R/'research_rebuild/evidence/working_full_chain_20261007'/n
 if not p.exists():continue
 out=O/('baseline49_union_'+n+'.gz')
 if out.exists():
  f=pd.read_csv(out,keep_default_na=False);pins[str(out)]=sha(out);prior=next((v for v in previous.get('scope_credit_snapshot_provenance',[]) if v['frozen_snapshot']==str(out)),None);assert prior and prior['frozen_snapshot_sha256']==pins[str(out)];provenance.append(prior)
 else:
  f=pd.read_csv(p,keep_default_na=False);f.to_csv(out,index=False,compression={'method':'gzip','mtime':0});pins[str(out)]=sha(out);provenance.append({'original_path':str(p),'original_read_sha256':sha(p),'frozen_snapshot':str(out),'frozen_snapshot_sha256':pins[str(out)]})
 if 'source_record_id' in f:target.update(f.source_record_id.astype(str))
ordinary=s.obs[s.obs.is_additive_settlement_record.fillna(False)&~s.obs.region_norm.isin(['москва','санкт петербург','севастополь'])];ordinary=ordinary[~(ordinary.census_year.eq(2021)&ordinary.region_norm.eq('крым'))]
axes={'finite_native_full3':basefinite,'original_mixed_native_ID_union':orig,'direct_lifecycle_native_ID_union':orig|direct,'direct_lifecycle_plus_formation_native_ID_union':orig|direct|formation};before={name:{str(int(y)):int(g[g.source_record_id.isin(ids)].population.sum()) for y,g in ordinary.groupby('census_year')} for name,ids in axes.items()};s=apply(s);newfinite=finite_ids(s);rows=[];after={};nets={}
for axis,ids in axes.items():
 now=ids|newfinite;after[axis]={str(int(y)):int(g[g.source_record_id.isin(now)].population.sum()) for y,g in ordinary.groupby('census_year')};nets[axis]={y:after[axis][y]-before[axis][y] for y in before[axis]}
 for row in ordinary[ordinary.source_record_id.isin(now-ids)].itertuples():rows.append({'axis':axis,'source_record_id':row.source_record_id,'year':row.census_year,'native_population':row.population,'native_quality':row.population_value_quality,'native_name':row.settlement_name})
pd.DataFrame(rows).to_csv(O/'exact_net_native_source_ID_union_gain.csv.gz',index=False,compression={'method':'gzip','mtime':0});r={'baseline_stage':49,'status':'exclusive actual49 finite/originalmixed/direct/formation native_ID marginal unions verified in one State replay','before_selected_ordinary_native_population_by_axis':before,'after_selected_ordinary_native_population_by_axis':after,'net_selected_ordinary_native_population_by_axis':nets,'scope_credit_snapshot_provenance':provenance,'input_pins':pins,'output_pin':sha(O/'exact_net_native_source_ID_union_gain.csv.gz'),'no_extra_federal_or_auxiliary_population_in_native_net':True};
for k in ['ROOT49_original_mixed_direct_formation_population_axes_exactly_reproduced','root_coverage_snapshot','root_coverage_snapshot_sha256']:
 if k in previous:r[k]=previous[k]
if previous.get('root_coverage_snapshot'):
 p=Path(previous['root_coverage_snapshot']);r['input_pins'][str(p.resolve())]=sha(p)
(O/'native_ID_union_marginal_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(nets,ensure_ascii=False))
