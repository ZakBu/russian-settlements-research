import sys,json,collections
from pathlib import Path
import pandas as pd,numpy as np
O=Path(__file__).parent;R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from frozen_working_state51 import load
from current_chain_state_20261007 import sha
from frozen_finite import finite
r=json.loads((O/'application_receipt.json').read_text())
for p,h in r['input_pins'].items():assert sha(Path(p))==h,p
for p,h in r['output_pins'].items():assert sha(O/p)==h,p
s=load(51);bf=finite(s);assert bf==r['before_finite_all3_all_points']
def ids(s):
 bad=set(s.obs.loc[~s.obs.source_record_id.isin(s.point_rows)|~np.isfinite(s.obs.population),'root'])|{s.uf.find(i) for i in s.conflicting_point_targets}
 return set(s.obs.loc[s.obs.root.map(lambda x:s.years[x]=={2002,2010,2021} and x not in bad)&s.obs.is_additive_settlement_record.fillna(False)&~s.obs.region_norm.isin(['москва','санкт петербург','севастополь'])&~(s.obs.census_year.eq(2021)&s.obs.region_norm.eq('крым')),'source_record_id'])
before=ids(s);pop=s.obs[['source_record_id','population','population_value_quality','settlement_name','settlement_type']].copy()
s.add_deltas([O/'accepted_identity_edge_delta.csv.gz'],[O/'accepted_point_use_delta.csv.gz']);af=finite(s);assert af==r['after_finite_all3_all_points'];pd.testing.assert_frame_equal(pop,s.obs[pop.columns]);after=ids(s)
ext=set()
for p in sorted((R/'research_rebuild/evidence/native2010_remaining_county_rule_mass_20261008').glob('baseline49_union_*.csv.gz')):
 f=pd.read_csv(p,keep_default_na=False)
 for col in f:
  if 'source_record_id' in col and not col.endswith('json'):ext.update(f[col].astype(str))
new=s.obs[s.obs.source_record_id.isin(after-before)].copy();new['already_baseline49_qualified_native_credit']=new.source_record_id.isin(ext);new['exclusive_native_ID_net_gain']=~new.already_baseline49_qualified_native_credit
out=O/'exact_net_native_source_ID_union_gain.csv.gz';new[['source_record_id','census_year','settlement_name','population','population_value_quality','already_baseline49_qualified_native_credit','exclusive_native_ID_net_gain']].to_csv(out,index=False,compression={'method':'gzip','mtime':0})
proof=pd.read_csv(O/'accepted_native_source_binding_witnesses.csv.gz');assert not proof.native2010_source_record_id.isin(ext|before).any()
from scan import cn,ty
rv=pd.read_csv(O/'all_2010_regional_name_type_rivals.csv.gz',keep_default_na=False)
ctx=pd.read_csv(R/'research_rebuild/evidence/secondary_2010_county_context_application_20261007/all_selected_competitor_county_context.csv.gz',keep_default_na=False).set_index('source_record_id').inferred_county_key.map(cn)
rv['effective_county']=rv.county_key.where(rv.county_key.ne(''),rv.source_record_id.map(ctx).fillna(''))
z=rv.merge(proof[['native2010_source_record_id','county_key','type']],left_on='target2010_source_record_id',right_on='native2010_source_record_id')
samecounty=z.effective_county.eq(z.county_key_y)&z.source_record_id.ne(z.target2010_source_record_id)&z.settlement_type.map(ty).isin(['село','деревня','посёлок','хутор'])
assert not (samecounty&z.settlement_type.map(ty).ne(z.type.map(ty))).any()
nameids=set(z.loc[samecounty,'target2010_source_record_id']);candidate=pd.read_csv(O/'positive_literal_native_county_ownpoint_candidates.csv.gz',keep_default_na=False)
candidate=candidate[candidate.native2010_source_record_id.isin(nameids)]
assert candidate.old_native_two_sided_source_bracket_json.map(lambda x:bool(json.loads(x))).all()
assert candidate.current_native_two_sided_source_bracket_json.map(lambda x:bool(json.loads(x))).all()
assert not proof.native2002_source_record_id.duplicated().any() and not proof.native2021_source_record_id.duplicated().any()
receipt={'status':'actual51 independent State replay and exact exclusive native ID union passed','before_finite':bf,'after_finite':af,'net_finite_histories':af['histories']-bf['histories'],'net_finite_population_by_year':{y:af['populations_by_year'][y]-bf['populations_by_year'][y] for y in bf['populations_by_year']},'gross_new_native_population_by_year':{str(int(y)):int(v.population.sum()) for y,v in new.groupby('census_year')},'exclusive_new_native_population_by_year':{str(int(y)):int(v.loc[v.exclusive_native_ID_net_gain,'population'].sum()) for y,v in new.groupby('census_year')},'accepted_cases':len(proof),'same_county_2010_namesake_cases_independently_resolved_by_both_native2002_and2021_source_brackets':len(nameids),'accepted_same_county_other_compatible_rural_class2010_rivals':0,'shared_historical_or_current_physical_candidate_targets_accepted':0,'all_native_values_quality_names_unchanged':True,'exact_native_union_gain_sha256':sha(out),'application_receipt_sha256':sha(O/'application_receipt.json')}
(O/'native_ID_union_marginal_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt,ensure_ascii=False))
