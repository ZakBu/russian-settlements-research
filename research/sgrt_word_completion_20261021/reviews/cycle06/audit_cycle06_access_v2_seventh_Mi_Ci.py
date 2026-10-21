"""Independent cycle05 checks; does not import producers or mutate frozen outputs."""
from pathlib import Path
import ast,hashlib,json
import numpy as np
import pandas as pd
D=Path(__file__).resolve().parent;B=D.parents[1];R=B.parents[1]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def receipt(name,checks,sources,**extra):
 out=dict(reviewer='continuation_guardian',n_checks=len(checks),n_failed=sum(not x['pass_'] for x in checks),checks=checks,source_sha256={str(p.relative_to(R)):digest(p) for p in sources},**extra)
 (D/name).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(name,out['n_checks'],out['n_failed'])
def check(checks,label,value,**details):checks.append(dict(check=label,pass_=bool(value),**details))
def eq(a,b):return np.allclose(np.asarray(a,dtype=float),np.asarray(b,dtype=float),rtol=1e-11,atol=1e-12,equal_nan=True)
M=B/'model/output_cycle06_baseline_not_needed';C=B/'model_inputs_cycle06/final_access_v2/config_source_geography_inclusive_final.json';P=B/'model_inputs_cycle06/provisional_access_v2_source_geography_inclusive/word_ci_center_features.parquet';PC=P.parent/'receipt.json';CODE=B/'model/run_word_model_cycle06.py';mc=P.parent/'mass_component_bindings.json';mf=P.parent/'fixed_own_mass_components.parquet'
config=json.loads(C.read_text());components=json.loads(mc.read_text());m=pd.read_parquet(mf);provisional=pd.read_parquet(P);pc=json.loads(PC.read_text());checks=[]
check(checks,'all_mass_rows_have_unique_IDs',m.id.is_unique and len(m)==173864)
check(checks,'every_primary_component_dated2021',all(c['year']==2021 for c in config['components']))
check(checks,'ten_primary_component_names_exact',len(config['components'])==10 and [c['name'] for c in config['components']]==[c['name'] for c in components])
zs={}
for c in components:
 raw=pd.to_numeric(m[c['name']+'_raw'],errors='coerce');v=np.log1p(raw.where(raw.ge(0))) if c['transform']=='log1p' else raw
 z=(v-v.mean())/v.std(ddof=0) if v.std(ddof=0)>1e-12 else pd.Series(np.nan,index=m.index)
 check(checks,'raw_z_recomputed_'+c['name'],eq(z,m[c['name']+'_z']))
 check(checks,'raw_mean_sd_recomputed_'+c['name'],abs(v.mean()-c['mean_transformed'])<1e-10 and abs(v.std(ddof=0)-c['sd_transformed'])<1e-10)
 zs[c['name']]=z
blocks={}
for block in sorted({c['block'] for c in components}):
 val=pd.DataFrame({c['name']:zs[c['name']] for c in components if c['block']==block}).mean(axis=1,skipna=True);blocks[block]=val
 check(checks,'equal_feature_weights_within_block_'+block,eq(val,m['block_'+block+'_z']))
frame=pd.DataFrame(blocks);index=frame.mean(axis=1,skipna=True);positive=np.exp(index.clip(-20,20)).where(frame.notna().sum(axis=1).gt(0))
check(checks,'five_fixed_blocks_equal_weights',len(blocks)==5 and eq(index,m.own_mean_standardized_index))
check(checks,'all173864_positive_masses_independently_recomputed',eq(positive,m.own_positive_mass))
check(checks,'no_primary_mass_declares_own_catchment_fit',m.mass_uses_modeled_catchment.eq(False).all())
check(checks,'no_primary_mass_has_future_dated_component',m.mass_mixes_observation_dates.eq(False).all())
check(checks,'provisional_Mi_exactly_equal_fixed_own_Mi',eq(provisional.set_index('id').own_positive_mass,m.set_index('id').loc[provisional.id,'own_positive_mass']))
check(checks,'provisional_no_mass_refit_and_one_iteration',pc['own_mass_refit'] is False and pc['provisional_iterations']==1 and provisional.own_mass_refitted_on_catchment.eq(False).all() and provisional.provisional_iterations.eq(1).all())
node=next(x for x in ast.parse(CODE.read_text()).body if isinstance(x,ast.FunctionDef) and x.name=='build_mass')
fit_calls=[ast.unparse(x.func) for x in ast.walk(node) if isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute) and x.func.attr in ['fit','fit_transform','predict','score']]
check(checks,'primary_build_mass_has_no_supervised_fit_or_prediction_call',not fit_calls)
check(checks,'component_bindings_exclude_model_zone_features',not any(any(x in z.lower() for x in ['catchment','provisional','rural_population','centrality','wordci_']) for c in config['components'] for z in c.get('columns',[])))
receipt('cycle06_access_v2_seventh_own_mass_independent_audit.json',checks,[C,CODE,mc,mf,P,PC],status='FIXED_OWN_MASS_NONCIRCULAR_CONSTRUCTION_INDEPENDENTLY_RECOMPUTED',scope='Assignment estimand at2021: no supervised target is fitted in primaryMi; observed2021population is a declared predictor. This does NOT remove endogeneity of retrospective demographic regressions nor validate actual attraction.',criterion_assessment={'no_model_catchment_used_to_fit_own_mass':'PASS','no_outcome_or_future_feature_leakage':'PASS_FOR_DECLARED_ASSIGNMENT2021_MASS_CONSTRUCTION; NOT_A_CAUSAL_DEMOGRAPHIC_FORECAST','independent_training_validation_partition':'NO_TRAINING_IN_FIXED_PRIMARY_MASS; any separate fitted calibration must retain independent partition; not retrospectively imposed on deterministic weights'},scientific_completion_accepted=False)

# Independently reconstruct provisional rural bounds and Ci from source roles/axis.
sourceaxis=pd.read_parquet(B/'data/source_controls_cycle05/full_settlement_axis_cycle05_federal_children.parquet');roles=pd.read_parquet(B/'data/source_controls_cycle05/statistical_role_primary/source_settlement_statistical_role_primary2021_v3.parquet');membership=pd.read_parquet(P.parent/'provisional_all_center_memberships.parquet');checks=[]
x=sourceaxis[['id','population_2021','axis_kind','is_additive_source_unit']].merge(roles[['id','source2021_rural_role','source2021_role_has_dated_source']],on='id',validate='one_to_one').merge(membership[['id','assigned_center_id']],on='id',how='left',validate='one_to_one');ordinary=x.is_additive_source_unit.fillna(False)&~x.axis_kind.fillna('').str.contains('territory|external_service',case=False);external=x[ordinary & x.source2021_role_has_dated_source.fillna(False) & x.assigned_center_id.notna() & x.id.ne(x.assigned_center_id)];rural=external[external.source2021_rural_role.fillna(False)];unknown=external[external.source2021_rural_role.isna()];out=provisional.set_index('id')
def grouped(df,mode):
 g=df.groupby('assigned_center_id');return (g.size() if mode=='count' else g.population_2021.sum(min_count=1)).reindex(out.index).fillna(0)
lo=grouped(rural,'sum');un=grouped(unknown,'sum');missing=grouped(rural[rural.population_2021.isna()],'count')+grouped(unknown[unknown.population_2021.isna()],'count');up=(lo+un).where(missing.eq(0));complete=missing.eq(0)&grouped(unknown,'count').eq(0)
for col,expected in {'provisional_observed2021_rural_units':grouped(rural,'count'),'provisional_observed2021_unknown_role_units':grouped(unknown,'count'),'provisional_observed2021_rural_population_known_sum':lo,'provisional_observed2021_unknown_role_population_known_sum':un,'provisional_observed2021_statistical_rural_lower_bound':lo,'provisional_observed2021_statistical_rural_upper_bound':up,'provisional_observed2021_rural_population_complete':complete,'provisional_selected_rural_population_component2021':lo}.items():check(checks,'all9329_'+col,eq(expected,out[col]))
a=np.log(out.own_positive_mass);b=np.log1p(lo);norma=(a-a.min())/(a.max()-a.min());normb=(b-b.min())/(b.max()-b.min());ci=(norma+normb)/2;check(checks,'every9329_Ci_independently_recomputed_no_refit',eq(ci,out.word_centrality_observed2021_frame_0_1));check(checks,'native2021_count155746_exact',int((ordinary & x.source2021_role_has_dated_source.fillna(False)).sum())==155746);check(checks,'unknown_role_oneperson_onecenter_unimputed',len(unknown)==1 and unknown.population_2021.sum()==1 and (~complete).sum()==1);check(checks,'ownMi_not_calibrated_on_rural_bounds',provisional.own_mass_refitted_on_catchment.eq(False).all() and provisional.provisional_iterations.eq(1).all());receipt('cycle06_access_v2_seventh_Ci_independent_audit.json',checks,[C,P.parent/'receipt.json',P,P.parent/'provisional_all_center_memberships.parquet',B/'data/source_controls_cycle05/statistical_role_primary/source_settlement_statistical_role_primary2021_v3.parquet'],status='ALL9329_CI_AND_RURAL_BOUNDS_INDEPENDENTLY_RECONSTRUCTED',scope='Actual fresh cycle06 preliminaryCi using accepted historical2021access_v2 routing. Primaryknownrural lowerbound, not complete truecatchment population. No overallcompletion or truecatchmentvalidation asserted.')
