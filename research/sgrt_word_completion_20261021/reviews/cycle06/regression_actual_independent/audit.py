#!/usr/bin/env python3
"""Independent source aggregate, all-fit CV/CR1 and paired region-bootstrap replay.
No producer import. Bootstrap is independently expanded rows (not sqrt weights).
"""
from pathlib import Path
import pandas as pd,numpy as np,json,hashlib,datetime
from scipy.stats import t as student_t
HERE=Path(__file__).resolve().parent;BASE=HERE.parents[2];REPO=BASE.parents[1];OUT=BASE/'analysis/cycle06_access_v2_baseline';checks=[];recomputations=[];bootstrap_rows=[]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def path(p):p=Path(p);return p if p.is_absolute()else REPO/p
def ck(n,v,detail=None):
 checks.append({'check':n,'pass':bool(v),'detail':detail})
 if not v:print('FAIL',n,str(detail)[:800],flush=True)
def close(a,b,tol=1e-7):return np.allclose(np.asarray(a,dtype=float),np.asarray(b,dtype=float),atol=tol,rtol=1e-8,equal_nan=True)
def std_design(x):
 mu=x.mean(axis=0);sd=x.std(axis=0);sd=np.where(sd>1e-12,sd,1.);return np.column_stack([np.ones(len(x)),(x-mu)/sd]),mu,sd
r=json.loads((OUT/'run_receipt.json').read_text());manifest=json.loads((OUT/'output_manifest.json').read_text());pins=r['source_sha256'];manifest_sha=sha(OUT/'output_manifest.json')
for p,h in pins.items():ck('actual_source_sha:'+p,sha(path(p))==h)
for p,h in manifest['files'].items():ck('actual_output_sha:'+p,sha(OUT/p)==h)
cfg=json.loads((OUT/'effective_analysis_inputs.json').read_text());pre=json.loads((OUT/'preregistration.json').read_text());adm=json.loads((BASE/'reviews/cycle06/cycle06_access_v2_regression_preregistration_independent_admission.json').read_text());ck('preregistered_design_admitted_before_metrics',adm['status']=='ACCEPTED'and adm['checked_before_analysis_metrics']is True and adm['preregistration_sha256']==sha(OUT/'preregistration.json')and adm['analysis_code_sha256']==r['analysis_code_sha256']and adm['analysis_inputs_sha256']==r['analysis_inputs_sha256']);model=path(cfg['model_output']);mr=json.loads((model/'run_receipt.json').read_text());ck('model_config_exactactualbound',mr['configuration_sha256']==sha(path(cfg['model_inputs']))and mr['model_code_sha256']==sha(BASE/'model/run_word_model_cycle06.py'))
frame=pd.read_parquet(OUT/'system_analysis_features.parquet');metrics=pd.read_csv(OUT/'model_metrics.csv');coef=pd.read_csv(OUT/'coefficient_intervals.csv');pred=pd.read_parquet(OUT/'system_predictions.parquet');foldtable=pd.read_csv(OUT/'grouped_cv_folds.csv');gates=pd.read_csv(OUT/'sample_gates.csv');membership=pd.read_parquet(OUT/'common_sample_membership.parquet');boot=pd.read_csv(OUT/'region_cluster_bootstrap_intervals.csv');ck('30actualfits_8504systems_183intervals',len(metrics)==30 and len(frame)==8504 and len(boot)==183 and len(gates)==88)
# Rebuild every rural weighted context from original nodes, corrected source role,
# membership IDs and actual direct route pairs, never raw settlement type.
columns=['id','population_2010','population_2021','_population_axis_row','accepted_statistical_rural_role2021','population_value_quality_2010','population_value_quality_2021','axis_kind','is_additive_source_unit'];nodes=pd.read_parquet(model/'nodes.parquet',columns=columns);members=pd.read_parquet(model/'memberships.parquet');members=members[['id']+[c for c in members if c.startswith('center_id_l')]];nodes=nodes.merge(members,on='id',validate='one_to_one');roles=pd.read_parquet(BASE/'data/source_controls_cycle05/statistical_role_primary/source_settlement_statistical_role_primary2021_v3.parquet').set_index('id').source2021_rural_role;expected_role=nodes.id.map(roles);ck('accepted_statistical_role_exactV3_notrawtype',nodes.accepted_statistical_rural_role2021.astype('string').fillna('<NA>').equals(expected_role.astype('string').fillna('<NA>')))
for alias,spec in cfg['rural_features'].items():
 p=path(spec['path'])if 'path'in spec else (model if spec['table']in['nodes.parquet','network_accessibility.parquet']else path(cfg['context_directory']))/spec['table'];cols=spec.get('fields',[spec.get('field')]);z=pd.read_parquet(p,columns=['id']+cols).set_index('id');values=np.column_stack([pd.to_numeric(nodes.id.map(z[c]),errors='coerce').to_numpy(float)for c in cols]);nodes[alias]=np.where(np.isfinite(values).all(axis=1),np.mean(values,axis=1),np.nan)
paired=nodes.bonitet_experimental_lower.notna()&nodes.bonitet_experimental_upper.notna()&nodes.bonitet_experimental_lower.ge(0)&nodes.bonitet_experimental_upper.le(125)&nodes.bonitet_experimental_lower.le(nodes.bonitet_experimental_upper);nodes.loc[~paired,['bonitet_experimental_lower','bonitet_experimental_upper']]=np.nan
pairs=pd.read_parquet(path(cfg['own_center_network']['path']));ck('directpairs_unique_level_origin',not pairs.duplicated(['level','id']).any());role=nodes.accepted_statistical_rural_role2021.astype('boolean').fillna(False)
aggchecks=[]
for lev in sorted(frame.level.unique()):
 key=f'center_id_l{int(lev)}';sub=nodes[nodes._population_axis_row.eq(True)&role&nodes[key].notna()&nodes.id.ne(nodes[key])].copy().rename(columns={key:'center_id'});pp=pairs[pairs.level.eq(lev)][['id','center_id','direct_network_minutes']];sub=sub.merge(pp,on=['id','center_id'],how='left',validate='one_to_one');sub['rural_own_center_minutes']=sub.direct_network_minutes;sub['weight']=pd.to_numeric(sub.population_2010,errors='coerce').where(sub.population_2010.ge(0));total=sub.groupby('center_id').weight.sum(min_count=1);count=sub.groupby('center_id').size();known=sub.groupby('center_id').weight.count();actual=frame[frame.level.eq(lev)].set_index('center_id')
 for alias in list(cfg['rural_features'])+['rural_own_center_minutes']:
  ok=np.isfinite(sub[alias])&sub.weight.notna();numer=(sub[alias]*sub.weight).where(ok).groupby(sub.center_id).sum(min_count=1);den=sub.weight.where(ok).groupby(sub.center_id).sum(min_count=1);coverage=den/total.where(total.gt(0));value=(numer/den.where(den.gt(0))).where(coverage.ge(.8)&count.eq(known));aggchecks.append({'level':int(lev),'feature':alias,'value_matches':close(actual.index.map(value),actual[alias]),'coverage_matches':close(actual.index.map(coverage),actual[alias+'_population_coverage'])})
ck('all4levels_all_rural_aggregates_owncenterdirectminutes',all(x['value_matches']and x['coverage_matches']for x in aggchecks),aggchecks);pd.DataFrame(aggchecks).to_csv(HERE/'all_rural_aggregate_checks.csv',index=False)
# Outcomes are reconstructed directly from source-valued published model totals.
centerpop=nodes.set_index('id');knowncenter={y:pd.to_numeric(frame.center_id.map(centerpop[f'population_{y}']),errors='coerce').ge(0)&np.isfinite(pd.to_numeric(frame.center_id.map(centerpop[f'population_{y}']),errors='coerce')) for y in [2010,2021]};complete=frame.system_population_complete_2010.eq(True)&frame.system_population_complete_2021.eq(True)&knowncenter[2010]&knowncenter[2021]&frame.system_population_known_sum_2010.gt(0)&frame.system_population_known_sum_2021.ge(0);ratio=frame.system_population_known_sum_2021/frame.system_population_known_sum_2010;ck('all8504_primary_outcome_from_complete_sourcepopulation_and_owncenter_guard',close(((ratio-1)*100).where(complete),frame.outcome_system_change_pct));ck('logratio_positivepopulation_notzeroimputed',close((100*np.log(ratio.where(ratio.gt(0)))).where(complete),frame.outcome_system_log_change_100))
# Independent full source/member and derived predictor replay, without producer imports.
quality_checks=[];population_checks=[]
for lev,actual0 in frame.groupby('level'):
 actual=actual0.set_index('center_id');key=f'center_id_l{int(lev)}';native=nodes[nodes._population_axis_row.eq(True)&nodes[key].notna()].copy();native['center_id']=native[key]
 for year in [2010,2021]:
  v=f'population_{year}';qual=f'population_value_quality_{year}'
  for label,mask in [('system',pd.Series(True,index=native.index)),('rural_external',native.accepted_statistical_rural_role2021.eq(True)&native.id.ne(native.center_id))]:
   q=native.loc[mask];g=q.groupby('center_id',observed=True)[v];sums=g.sum(min_count=1);complete0=g.count().eq(g.size());counts=g.size().reindex(actual.index,fill_value=0);sums=sums.reindex(actual.index);complete0=complete0.reindex(actual.index);sums.loc[counts.eq(0)]=0.;sums=sums.fillna(0.) if label=='rural_external' else sums;complete0.loc[counts.eq(0)]=True;unknownroles=(native.accepted_statistical_rural_role2021.isna()&native.id.ne(native.center_id)).groupby(native.center_id,observed=True).any().reindex(actual.index,fill_value=False);complete0=complete0&~unknownroles if label=='rural_external' else complete0;population_checks.append({'level':int(lev),'year':year,'scope':label,'sum_exact':close(actual.index.map(sums),actual[f'{label}_population_known_sum_{year}']),'completeness_exact':actual[f'{label}_population_complete_{year}'].astype('boolean').fillna(False).equals(pd.Series(actual.index.map(complete0),index=actual.index).astype('boolean').fillna(False))})
  primary=native[qual].isin(cfg[f'primary_population_quality_{year}']).groupby(native.center_id).all();quality_checks.append({'level':int(lev),'field':f'analysis_system{year}_primary_source_only','matches':actual[f'analysis_system{year}_primary_source_only'].astype('boolean').fillna(False).equals(pd.Series(actual.index.map(primary),index=actual.index).astype('boolean').fillna(False))})
  if year==2010:
   supported=native[qual].isin(cfg['primary_supported_population_quality_2010']).groupby(native.center_id).all();quality_checks.append({'level':int(lev),'field':'analysis_system2010_primary_supported_only','matches':actual.analysis_system2010_primary_supported_only.astype('boolean').fillna(False).equals(pd.Series(actual.index.map(supported),index=actual.index).astype('boolean').fillna(False))})
 for year in [2010,2021]:
  ck(f'whole_center_observation_guard:{lev}:{year}',np.array_equal(actual0[f'analysis_center_own_population_observed_{year}'].to_numpy(),knowncenter[year].loc[actual0.index].to_numpy()))
 ck(f'ctx_and_missing_owncenter_whole_outcomes_are_unknown:{lev}',actual0.loc[~(knowncenter[2010].loc[actual0.index]&knowncenter[2021].loc[actual0.index]),['outcome_system_change_pct','outcome_system_log_change_100']].isna().all().all())
ck('all_source_member_population_sums_and_completeness',all(x['sum_exact']and x['completeness_exact']for x in population_checks),population_checks)
ck('all_source_quality_sensitivity_masks',all(x['matches']for x in quality_checks),quality_checks)
pd.DataFrame(population_checks).to_csv(HERE/'population_member_reconstruction.csv',index=False);pd.DataFrame(quality_checks).to_csv(HERE/'source_quality_reconstruction.csv',index=False)
ownconfig=pd.read_parquet(model/'system_configurations.parquet').set_index(['level','center_id']);ix=pd.MultiIndex.from_frame(frame[['level','center_id']]);cl=ownconfig.reindex(ix);poly=cl.modeled_configuration.map({'polycentric_peer_field_potential':1.,'monocentric_field_potential':0.}).to_numpy(float);shared=cl.own_order_shared_origin_fraction.where(np.isfinite(poly)).to_numpy(float)
ck('configuration_ownorder_source_exact_NA_structural_never_mono',close(poly,frame.polycentric_potential)and close(shared,frame.configuration_shared_origin_fraction)and frame.loc[frame.level.eq(1),'polycentric_potential'].isna().all()and np.array_equal(frame.configuration_observed.to_numpy(),np.isfinite(poly)))
ownm=pd.read_parquet(model/'own_mass_components.parquet',columns=['id','own_positive_mass']).set_index('id').own_positive_mass
derived={'log_own_mass2021':np.log(frame.center_id.map(ownm).where(frame.center_id.map(ownm).gt(0))),'log_baseline_system_population2010':np.log(frame.system_population_known_sum_2010.where(frame.system_population_known_sum_2010.gt(0)))}
for target,raw in [('log_rural_own_center_minutes','rural_own_center_minutes'),('log_rural_large_city_minutes','rural_large_city_minutes'),('log_agro_grain_yield2010','agro_grain_yield2010'),('log_agro_grain_yield2021','agro_grain_yield2021')]:derived[target]=np.log1p(frame[raw].where(frame[raw].ge(0)))
derived.update(mass_x_suburban=derived['log_own_mass2021']*frame.rural_suburban_share,yield2010_x_polycentric=derived['log_agro_grain_yield2010']*poly,yield2021_x_polycentric=derived['log_agro_grain_yield2021']*poly)
ck('all_derived_predictors_and_interactions_source_exact',all(close(v,frame[k])for k,v in derived.items()))
cr=frame.rural_external_population_complete_2010.eq(True)&frame.rural_external_population_complete_2021.eq(True)&frame.rural_external_population_known_sum_2010.gt(0)&frame.rural_external_population_known_sum_2021.ge(0)
ck('rural_outcome_independent_scope_retained',close(((frame.rural_external_population_known_sum_2021/frame.rural_external_population_known_sum_2010-1)*100).where(cr),frame.outcome_rural_change_pct))
ck('two_comparison_families_model_counts_no_fabricated_M3',metrics.scenario.str.startswith('A_M1_M2__').all()and not metrics.model.eq('M3').any()and len(pre['scenarios'])==22)
for spec in pre['scenarios']:
 scenario=spec['name'];outcome=spec['outcome'];terms=spec['terms'];required=list(dict.fromkeys(c for v in terms.values()for c in v))
 for lev,d in frame.groupby('level'):
  finite=np.isfinite(d[required+[outcome,'lat','lon']].to_numpy(float)).all(axis=1)&d.region.notna()
  if spec['pure_primary_only']:finite&=d.analysis_system2010_primary_source_only.eq(True)&d.analysis_system2021_primary_source_only.eq(True)
  if spec['reviewed_primary_supported_only']:finite&=d.analysis_system2010_primary_supported_only.eq(True)&d.analysis_system2021_primary_source_only.eq(True)
  e=d[finite].sort_values('system_id');ng=e.region.nunique();gate=gates[gates.scenario.eq(scenario)&gates.level.eq(lev)].iloc[0];passed=len(e)>=max(cfg['minimum_sample'],10*(len(required)+1))and ng>=cfg['minimum_regions'];ck(f'samplegate:{scenario}:{lev}',int(gate.common_sample)==len(e)and gate.regions==ng and (gate.status=='COMPUTED')==passed)
  sm=membership[membership.scenario.eq(scenario)&membership.level.eq(lev)].set_index('system_id');ck(f'all_common_sample_members:{scenario}:{lev}',np.array_equal(d.system_id.map(sm.in_common_sample).to_numpy(),np.asarray(finite)))
  mm=metrics[metrics.scenario.eq(scenario)&metrics.level.eq(lev)];ck(f'exact_family_model_count_or_unfabricatedfailedgate:{scenario}:{lev}',len(mm)==(len(terms) if passed else 0))
  if not passed:continue
  y=e[outcome].to_numpy(float);group=e.region.astype(str).to_numpy();regions,code,region_n=np.unique(group,return_inverse=True,return_counts=True);assigned=np.zeros(ng,int);loads=np.zeros(5,int)
  for ri in np.argsort(region_n)[::-1]:fold=np.argmin(loads);assigned[ri]=fold;loads[fold]+=region_n[ri]
  folds=assigned[code];reglist=sorted(regions);bcodes=pd.Categorical(group,categories=reglist).codes;seed=cfg['seed']+int(hashlib.sha256(f'{scenario}|{outcome}|{lev}'.encode()).hexdigest()[:8],16);draws=np.random.default_rng(seed).multinomial(ng,np.full(ng,1/ng),size=499)
  for modelname,cols in terms.items():
   varied=[];constant=[];collinear=[];current=np.ones((len(e),1));rank=1
   for col in cols:
    vals=e[col].to_numpy(float)
    if vals.std()<=1e-12:constant.append(col);continue
    candidate=np.column_stack([current,(vals-vals.mean())/vals.std()]);nr=np.linalg.matrix_rank(candidate)
    if nr>rank:varied.append(col);current=candidate;rank=nr
    else:collinear.append(col)
   x=e[varied].to_numpy(float);D,mu,sd=std_design(x);beta=np.linalg.lstsq(D,y,rcond=None)[0];res=y-D@beta;bread=np.linalg.inv(D.T@D);scores=np.vstack([D[group==g].T@res[group==g]for g in regions]);cov=bread@(scores.T@scores)@bread*(ng/(ng-1))*((len(e)-1)/(len(e)-D.shape[1]));se=np.sqrt(np.maximum(np.diag(cov),0));critical=student_t.ppf(.975,ng-1);ci=np.column_stack([beta-critical*se,beta+critical*se]);oof=np.full(len(e),np.nan);null=np.full(len(e),np.nan)
   for fold in range(5):
    train=folds!=fold;test=~train;dx,tm,ts=std_design(x[train]);testx=np.column_stack([np.ones(test.sum()),(x[test]-tm)/ts]);oof[test]=testx@np.linalg.lstsq(dx,y[train],rcond=None)[0];null[test]=y[train].mean()
   cp=coef[coef.scenario.eq(scenario)&coef.level.eq(lev)&coef.model.eq(modelname)].set_index('term').loc[['intercept']+varied];pr=pred[pred.scenario.eq(scenario)&pred.level.eq(lev)&pred.model.eq(modelname)].set_index('system_id').loc[e.system_id];row=mm[mm.model.eq(modelname)].iloc[0]
   ck(f'OLS_CR1_allcoefficients:{scenario}:{lev}:{modelname}',close(beta,cp.beta)and close(se,cp.se_cluster_region)and close(ci[:,0],cp.ci95_lower)and close(ci[:,1],cp.ci95_upper));ck(f'all_predictions_same_groupfolds:{scenario}:{lev}:{modelname}',close(D@beta,pr.fitted)and close(res,pr.residual)and close(oof,pr.group_oof_prediction)and np.array_equal(folds,pr.cv_fold))
   vals={'r2':1-res@res/np.sum((y-y.mean())**2),'group_oof_rmse':np.sqrt(np.mean((y-oof)**2)),'group_oof_mae':np.mean(np.abs(y-oof)),'group_oof_r2_train_mean_baseline':1-np.sum((y-oof)**2)/np.sum((y-null)**2)};ck(f'all_metrics:{scenario}:{lev}:{modelname}',all(close(v,row[k])for k,v in vals.items())and row.n==len(e)and row.regions==ng)
   samples=[]
   for draw in draws:
    ix=np.repeat(np.arange(len(e)),draw[bcodes]);dx=D[ix]
    if np.linalg.matrix_rank(dx)<dx.shape[1]:continue
    samples.append(np.linalg.lstsq(dx,y[ix],rcond=None)[0])
   bb=np.quantile(samples,[.025,.975],axis=0);reported=boot[boot.scenario.eq(scenario)&boot.level.eq(lev)&boot.model.eq(modelname)].set_index('term').loc[['intercept']+varied];ck(f'all499_expandedregion_bootstrap_CIs:{scenario}:{lev}:{modelname}',len(samples)==reported.full_rank_replicates.iloc[0]and close(bb[0],reported.ci95_lower)and close(bb[1],reported.ci95_upper),{'full_rank_draws':len(samples),'terms':len(varied)+1})
   for j,term in enumerate(['intercept']+varied):bootstrap_rows.append({'scenario':scenario,'level':int(lev),'model':modelname,'term':term,'full_rank_draws':len(samples),'ci95_lower':float(bb[0,j]),'ci95_upper':float(bb[1,j])})
   recomputations.append({'scenario':scenario,'level':int(lev),'model':modelname,'n':len(e),'regions':ng,**{k:float(v)for k,v in vals.items()}})
print('RECOMPUTED_ALL',len(recomputations),flush=True);pd.DataFrame(recomputations).to_csv(HERE/'all30_independent_metrics.csv',index=False);pd.DataFrame(bootstrap_rows).to_csv(HERE/'all183_independent_bootstrap_intervals.csv',index=False)
ck('all30fits_all183intervals_recomputed',len(recomputations)==30 and len(bootstrap_rows)==183)
for p,h in pins.items():ck('final_source_still_frozen:'+p,sha(path(p))==h)
ck('output_manifest_still_frozen',sha(OUT/'output_manifest.json')==manifest_sha)
result={'status':'INDEPENDENT_ACTUAL_REGRESSION_MATH_ACCEPTED'if all(c['pass']for c in checks)else'REJECT_ACTUAL_REGRESSION_PENDING_REPAIR','all_checks_passed':all(c['pass']for c in checks),'n_checks':len(checks),'n_failed':sum(not c['pass']for c in checks),'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_receipt_sha256':sha(OUT/'run_receipt.json'),'output_manifest_sha256':manifest_sha,'audit_code_sha256':sha(Path(__file__)),'scope':'All30OLS coefficients andregionCR1 CIs/allgroupedCVpointpredictions,88samplegates,all183499pairedregionbootstrap CIs, whole-systemowncenter guard, separateA/Bfamilies; all4hierarchy-level13ruralcontexts plus owncenter directminutes rebuilt fromsource; fixedsourcepop/catchments. SpatialMoran/figures notindependentlyreplayed.','checks':checks,'limits':['Descriptive retrospective association, not causal prediction. Fullcatchment/routing/linkage uncertainty not propagated.','TrainingR2 gain does not ensure heldoutregion improvement; report both.','Source2010secondaryvalues, regionalcropcontexts, GAEZsoilproxy and experimentalunadoptedbonitet retain original limitations.']};(HERE/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps({'status':result['status'],'n_checks':len(checks),'n_failed':result['n_failed'],'failures':[q for q in checks if not q['pass']]},ensure_ascii=False,indent=2))
