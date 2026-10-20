#!/usr/bin/env python3
"""Comparable descriptive Word M1/M2/M3; refuses to fabricate pending road outputs."""
from pathlib import Path
import argparse,hashlib,json,datetime
import numpy as np,pandas as pd,pyarrow.parquet as pq
from scipy import sparse,stats
from scipy.spatial import cKDTree
from sklearn.model_selection import GroupKFold
ROOT=Path(__file__).resolve().parent;REPO=ROOT.parents[2]
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def dump(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False))
def read(path,cols):
 schema=pq.read_schema(path).names;missing=set(cols)-set(schema)
 if missing:raise ValueError(f'{path.name}:missing exact fields{sorted(missing)}')
 return pd.read_parquet(path,columns=cols)
def bindings(config):
 directory=REPO/config['context_directory'];model=REPO/config['model_output'];tables={}
 for alias,spec in config['rural_features'].items():
  path=REPO/spec['path'] if 'path' in spec else (model if spec['table']=='network_accessibility.parquet' else directory)/spec['table'];tables.setdefault(path,set()).update(spec.get('fields',[spec.get('field')]))
 return tables

def source_coverage(config):
 axis=read(REPO/config['axis'],['id','population_2010','population_2021','population_value_quality_2010','population_value_quality_2021']);rows=[];hashes={str(REPO/config['axis']):sha(REPO/config['axis'])}
 for path,fields in bindings(config).items():
  if not path.exists():
   rows.extend(dict(source=str(path.relative_to(REPO)),feature=f,status='PENDING_MODEL_OUTPUT',nonnull=None,axis_rows=len(axis)) for f in fields);continue
  d=read(path,['id']+sorted(fields));assert d.id.is_unique;z=axis[['id']].merge(d,on='id',how='left',validate='one_to_one');hashes[str(path.relative_to(REPO))]=sha(path)
  rows.extend(dict(source=str(path.relative_to(REPO)),feature=f,status='ACTUALLY_PRESENT',nonnull=int(z[f].notna().sum()),axis_rows=len(axis)) for f in fields)
 pd.DataFrame(rows).to_csv(ROOT/'source_coverage_summary.csv',index=False)
 q=axis.copy();q['population_value_quality_2010']=q.population_value_quality_2010.fillna('UNKNOWN_SOURCE_QUALITY');q.groupby('population_value_quality_2010').agg(entity_rows=('id','size'),known_population2010_rows=('population_2010','count')).reset_index().to_csv(ROOT/'original_axis_population2010_source_quality_counts.csv',index=False)
 dump(ROOT/'source_coverage_receipt.json',dict(status='SOURCE_COVERAGE_ONLY_NOT_REGRESSION_RESULTS',source_sha256=hashes,observed_axis_rows=len(axis),original_axis_complete_population_pair_rows=int(axis[['population_2010','population_2021']].notna().all(axis=1).sum()),primary_design='all M1/M2/M3 same system sample per hierarchy level and scenario; no missing=zero'))

def prepare(config):
 model=REPO/config['model_output'];required=['systems.parquet','memberships.parquet','nodes.parquet','own_mass_components.parquet','network_accessibility.parquet','system_configurations.parquet','run_receipt.json'];absent=[f for f in required if not (model/f).exists()]
 if absent:raise FileNotFoundError('ROUTED_FINAL_MODEL_PENDING:'+','.join(absent))
 modelreceipt=json.loads((model/'run_receipt.json').read_text())
 if modelreceipt.get('status')!='COMPUTED_PENDING_STRICT_SCIENTIFIC_DATA_REVIEW':raise ValueError('Full routed model receipt not computed:'+modelreceipt.get('status','unknown'))
 watched=[model/f for f in required]+list(bindings(config))+[REPO/config['axis'],ROOT/'analysis_inputs.json',Path(__file__)];hashes_before={str(p.relative_to(REPO)):sha(p) for p in watched}
 systems=pd.read_parquet(model/'systems.parquet');assert not systems.duplicated(['level','center_id']).any()
 ns=pq.read_schema(model/'nodes.parquet').names;recovery_columns=[c for c in ns if c in ['original_population_2010','original_population_value_quality_2010'] or c.startswith('recovered2010_')]
 if recovery_columns:read(model/'nodes.parquet',['id','population_2010','population_value_quality_2010']+recovery_columns).to_parquet(ROOT/'node_source2010_recovery_audit.parquet',index=False)
 nodes=read(model/'nodes.parquet',['id','type','region','_population_axis_row','population_2010','population_2021','population_value_quality_2010','population_value_quality_2021','lat','lon'])
 for path,fields in bindings(config).items():nodes=nodes.merge(read(path,['id']+sorted(fields)),on='id',how='left',validate='one_to_one')
 for alias,spec in config['rural_features'].items():
  fs=spec.get('fields',[spec.get('field')]);nodes[alias]=nodes[fs].astype(float).mean(axis=1).where(nodes[fs].notna().all(axis=1)) if len(fs)>1 else pd.to_numeric(nodes[fs[0]],errors='coerce').astype(float)
 paired_bonitet=nodes[['bonitet_experimental_lower','bonitet_experimental_upper']].notna().all(axis=1)&nodes.bonitet_experimental_lower.ge(0)&nodes.bonitet_experimental_upper.le(125)&nodes.bonitet_experimental_lower.le(nodes.bonitet_experimental_upper)
 nodes.loc[~paired_bonitet,['bonitet_experimental_lower','bonitet_experimental_upper']]=np.nan
 memberschema=pq.read_schema(model/'memberships.parquet').names;assignment_columns=[f'center_id_l{int(l)}' for l in sorted(systems.level.unique())]
 members=read(model/'memberships.parquet',['id']+assignment_columns);nodes=nodes.merge(members,on='id',validate='one_to_one')
 rural=nodes._population_axis_row.eq(True)&~nodes.type.fillna('').isin(config['rural_excluded_types']);features=list(config['rural_features']);aggregates=[];quality_composition=[];quality_unit_rows=[]
 native=nodes[nodes._population_axis_row.eq(True)].copy();native['rural']=rural.loc[native.index];native['source_quality']=native.population_value_quality_2010.fillna('UNKNOWN_SOURCE_QUALITY')
 national_quality=native.groupby(['region','rural','source_quality'],dropna=False).agg(source_rows=('id','size'),known_population_rows=('population_2010','count'),known_population_value_sum=('population_2010',lambda v:v.sum(min_count=1))).reset_index();national_quality['scope']='final_model_population_axis_after_reviewed2010_recovery';national_quality.to_csv(ROOT/'node_2010_sourcequality_by_region_and_rural.csv',index=False)

 for level in sorted(systems.level.unique()):
  col=f'center_id_l{int(level)}'
  unitnodes=nodes[nodes._population_axis_row.eq(True)&nodes[col].notna()].copy();unitnodes['center_id']=unitnodes[col];unitnodes['rural_external']=~unitnodes.type.fillna('').isin(config['rural_excluded_types'])&unitnodes.id.ne(unitnodes.center_id)
  qsummary=pd.DataFrame(index=unitnodes.groupby('center_id').size().index);qsummary['level']=level
  for year in [2010,2021]:
   qualitycol=f'population_value_quality_{year}';popcol=f'population_{year}';valid_quality=unitnodes[qualitycol].isin(config[f'primary_population_quality_{year}'])
   qsummary[f'analysis_system{year}_primary_source_only']=valid_quality.groupby(unitnodes.center_id).all()
   if year==2010:qsummary['analysis_system2010_primary_supported_only']=unitnodes[qualitycol].isin(config['primary_supported_population_quality_2010']).groupby(unitnodes.center_id).all()
   for scope,mask in [('system',pd.Series(True,index=unitnodes.index)),('rural_external',unitnodes.rural_external)]:
    q=unitnodes[mask].copy();q[qualitycol]=q[qualitycol].fillna('UNKNOWN_SOURCE_QUALITY');g=q.groupby(['center_id',qualitycol]).agg(source_rows=('id','size'),nonnull_population_rows=(popcol,'count'),known_population_sum=(popcol,lambda v:v.sum(min_count=1))).reset_index().rename(columns={qualitycol:'source_quality'});g['level']=level;g['year']=year;g['scope']=scope;g['weighted_sum_is_published_or_secondary_values_not_exact_groundtruth']=True;quality_composition.append(g)
    if year==2010:
     secondary=q[qualitycol].eq(config['secondary_population_quality_2010']);den=q.groupby('center_id')[popcol].sum(min_count=1);num=q[popcol].where(secondary,0).groupby(q.center_id).sum(min_count=1);qsummary[f'analysis_{scope}2010_secondary_share_of_known_population']=num/den.where(den.gt(0));qsummary[f'analysis_{scope}2010_secondary_source_rows']=secondary.groupby(q.center_id).sum()
  quality_unit_rows.append(qsummary.reset_index())
  z=nodes.loc[rural&nodes[col].notna()&nodes.id.ne(nodes[col]),[col,'population_2010']+features].copy();z=z.rename(columns={col:'center_id'})
  # Resident context, not farmland mean. A missing population weight contributes no known weight.
  z['weight']=pd.to_numeric(z.population_2010,errors='coerce').where(z.population_2010.ge(0));total=z.groupby('center_id').weight.sum(min_count=1);observed_n=z.groupby('center_id').size();knownweight_n=z.groupby('center_id').weight.count();agg=pd.DataFrame({'rural_weight_total2010':total,'rural_members_n':observed_n,'rural_members_known_population2010_n':knownweight_n});agg['level']=level
  for feature in features:
   valid=z[feature].notna()&np.isfinite(z[feature])&z.weight.notna();num=(z[feature]*z.weight).where(valid).groupby(z.center_id).sum(min_count=1);den=z.weight.where(valid).groupby(z.center_id).sum(min_count=1);coverage=den/total.where(total.gt(0));agg[feature+'_population_coverage']=coverage;agg[feature]=(num/den.where(den.gt(0))).where(coverage.ge(config['minimum_weighted_feature_coverage'])&observed_n.eq(knownweight_n))
  aggregates.append(agg.reset_index())
 systems=systems.merge(pd.concat(aggregates,ignore_index=True),on=['level','center_id'],how='left',validate='one_to_one')
 assert np.allclose(systems.bonitet_experimental_lower_population_coverage.fillna(-1),systems.bonitet_experimental_upper_population_coverage.fillna(-1));systems['bonitet_bounds_share_identical_population_weights_and_coverage']=True
 systems=systems.merge(pd.concat(quality_unit_rows,ignore_index=True),on=['level','center_id'],how='left',validate='one_to_one');pd.concat(quality_composition,ignore_index=True).to_parquet(ROOT/'system_population_source_quality_composition.parquet',index=False)
 mass=read(model/'own_mass_components.parquet',['id','own_positive_mass']).rename(columns={'id':'center_id'});systems=systems.merge(mass,on='center_id',how='left',validate='many_to_one')
 configs=read(model/'system_configurations.parquet',['level','center_id','n_peer_centers_highest_rank','ambiguous_origin_fraction','modeled_configuration']);systems=systems.merge(configs,on=['level','center_id'],how='left',validate='one_to_one')
 systems['polycentric_potential']=systems.modeled_configuration.map({'polycentric_potential_candidate':1.,'monocentric_potential_candidate':0.});systems['configuration_ambiguity']=systems.ambiguous_origin_fraction
 systems['log_own_mass2021']=np.log(systems.own_positive_mass.where(systems.own_positive_mass.gt(0)))
 systems['log_baseline_system_population2010']=np.log(systems.system_population_known_sum_2010.where(systems.system_population_known_sum_2010.gt(0)))
 systems['log_rural_road_minutes']=np.log1p(systems.rural_road_minutes.where(systems.rural_road_minutes.ge(0)))
 systems['log_agro_grain_yield2010']=np.log1p(systems.agro_grain_yield2010.where(systems.agro_grain_yield2010.ge(0)))
 systems['mass_x_suburban']=systems.log_own_mass2021*systems.rural_suburban_share;systems['yield_x_polycentric']=systems.log_agro_grain_yield2010*systems.polycentric_potential
 complete=systems.system_population_complete_2010.eq(True)&systems.system_population_complete_2021.eq(True)&systems.system_population_known_sum_2010.gt(0)&systems.system_population_known_sum_2021.ge(0)
 systems['outcome_system_change_pct']=((systems.system_population_known_sum_2021/systems.system_population_known_sum_2010-1)*100).where(complete)
 systems['outcome_system_log_change_100']=100*np.log((systems.system_population_known_sum_2021/systems.system_population_known_sum_2010).where(complete&systems.system_population_known_sum_2021.gt(0)))
 complete_rural=systems.rural_external_population_complete_2010.eq(True)&systems.rural_external_population_complete_2021.eq(True)&systems.rural_external_population_known_sum_2010.gt(0)&systems.rural_external_population_known_sum_2021.ge(0)
 systems['outcome_rural_change_pct']=((systems.rural_external_population_known_sum_2021/systems.rural_external_population_known_sum_2010-1)*100).where(complete_rural)
 systems['system_id']=systems.level.astype(str)+':'+systems.center_id.astype(str);systems.to_parquet(ROOT/'system_analysis_features.parquet',index=False)
 hashes_after={str(p.relative_to(REPO)):sha(p) for p in watched}
 if hashes_before!=hashes_after:dump(ROOT/'source_integrity_failure.json',dict(stage='prepare',before=hashes_before,after=hashes_after));raise RuntimeError('SOURCE_CHANGED_DURING_PREPARATION')
 return systems,hashes_before

def standardize(x,mean=None,sd=None):
 mean=np.mean(x,axis=0) if mean is None else mean;sd=np.std(x,axis=0) if sd is None else sd;sd=np.where(sd>1e-12,sd,1.);return np.column_stack([np.ones(len(x)),(x-mean)/sd]),mean,sd

def fit_ols(x,y,groups):
 design,mean,sd=standardize(x);beta=np.linalg.lstsq(design,y,rcond=None)[0];resid=y-design@beta;n,p=design.shape;unique=np.unique(groups);g=len(unique);pinv_design=np.linalg.pinv(design);bread=pinv_design@pinv_design.T;meat=np.zeros((p,p))
 for region in unique:
  score=design[groups==region].T@resid[groups==region];meat+=np.outer(score,score)
 cov=(g/(g-1))*((n-1)/(n-p))*bread@meat@bread;se=np.sqrt(np.maximum(np.diag(cov),0));critical=stats.t.ppf(.975,g-1);rss=float(resid@resid);tss=float(np.sum((y-y.mean())**2));hat=np.einsum('ij,ji->i',design,pinv_design);mse=rss/(n-p);cooks=(resid**2/(p*mse))*hat/np.maximum(1-hat,1e-8)**2 if mse>0 else np.zeros(n)
 return dict(beta=beta,se=se,ci_lower=beta-critical*se,ci_upper=beta+critical*se,residual=resid,fitted=y-resid,hat=hat,cooks=cooks,r2=1-rss/tss if tss>0 else None,adj_r2=1-(rss/(n-p))/(tss/(n-1)) if tss>0 else None,rank=int(np.linalg.matrix_rank(design)),p=p,condition_number=float(np.linalg.cond(design)),cluster_regions=g,mean=mean,sd=sd)

def spatial_weights(lat,lon,k):
 a=np.radians(lat);b=np.radians(lon);xyz=np.column_stack([np.cos(a)*np.cos(b),np.cos(a)*np.sin(b),np.sin(a)]);distance,index=cKDTree(xyz).query(xyz,k=min(k+1,len(lat)));distance,index=distance[:,1:],index[:,1:];rows=np.repeat(np.arange(len(lat)),index.shape[1]);adj=sparse.coo_matrix((np.ones(index.size),(rows,index.ravel())),shape=(len(lat),len(lat))).tocsr();adj=adj.maximum(adj.T);adj.setdiag(0);adj.eliminate_zeros();weights=sparse.diags(1/np.asarray(adj.sum(axis=1)).ravel())@adj;km=2*np.arcsin(np.minimum(distance/2,1))*6371.;return weights,dict(k=int(index.shape[1]),median_neighbor_km=float(np.median(km)),p95_neighbor_km=float(np.quantile(km,.95)),metric='greatcircle3Dnearest,symmetricunion,row-standardized')

def moran(values,weights,permutations,seed):
 z=values-values.mean();den=z@z
 if den<=0:return dict(status='CONSTANT_RESIDUALS')
 value=float(z@(weights@z)/den);rng=np.random.default_rng(seed);sim=[]
 for _ in range(permutations):
  zz=rng.permutation(z);sim.append(float(zz@(weights@zz)/den))
 sim=np.asarray(sim);expected=-1/(len(z)-1);p=(1+np.sum(np.abs(sim-expected)>=abs(value-expected)))/(permutations+1)
 return dict(status='COMPUTED',moran_i=value,randomization_expected_i=expected,two_sided_permutation_p=float(p),permutations=permutations,spatial_design='pointknn,notadministrativecontiguity;diagnostic only')

def fit_scenario(frame,scenario,outcome,terms,config,pure_only=False,supported_only=False):
 rows=[];coefficients=[];predictions=[];spatial=[];samples=[];foldrows=[];gates=[]
 required=list(dict.fromkeys(v for columns in terms.values() for v in columns))
 for level,d in frame.groupby('level',sort=True):
  finite=d[required+[outcome,'lat','lon']].apply(pd.to_numeric,errors='coerce').replace([np.inf,-np.inf],np.nan).notna().all(axis=1)&d.region.notna()
  if pure_only:finite&=d.analysis_system2010_primary_source_only.eq(True)&d.analysis_system2021_primary_source_only.eq(True)
  if supported_only:finite&=d.analysis_system2010_primary_supported_only.eq(True)&d.analysis_system2021_primary_source_only.eq(True)
  eligible=d.loc[finite].copy().sort_values('system_id');n=len(eligible);regions=eligible.region.nunique();gate=dict(scenario=scenario,outcome=outcome,level=int(level),all_systems=len(d),outcome_observed=int(d[outcome].notna().sum()),common_sample=n,regions=int(regions),pure_primary_units_among_all=int((d.analysis_system2010_primary_source_only.eq(True)&d.analysis_system2021_primary_source_only.eq(True)).sum()),primary_supported_units_among_all=int((d.analysis_system2010_primary_supported_only.eq(True)&d.analysis_system2021_primary_source_only.eq(True)).sum()),common_sample_median_system2010_secondary_population_share=float(eligible.analysis_system2010_secondary_share_of_known_population.median()) if n and eligible.analysis_system2010_secondary_share_of_known_population.notna().any() else None,common_sample_median_rural2010_secondary_population_share=float(eligible.analysis_rural_external2010_secondary_share_of_known_population.median()) if n and eligible.analysis_rural_external2010_secondary_share_of_known_population.notna().any() else None);gates.append(gate)
  samples.extend(dict(system_id=row.system_id,level=int(level),scenario=scenario,outcome=outcome,in_common_sample=bool(ok)) for (_,row),ok in zip(d.iterrows(),finite))
  if n<max(config['minimum_sample'],10*(len(required)+1)) or regions<config['minimum_regions']:gate['status']='INSUFFICIENT_COMMON_SAMPLE_OR_REGIONS';continue
  gate['status']='COMPUTED';group=eligible.region.astype(str).values;y=eligible[outcome].to_numpy(float);folds=list(GroupKFold(n_splits=min(config['cv_folds'],regions)).split(eligible,y,group));foldbyrow=np.full(n,-1)
  for fold,(_,test) in enumerate(folds):foldbyrow[test]=fold
  weight,spmeta=spatial_weights(eligible.lat.values,eligible.lon.values,config['moran_neighbors'])
  for name,columns in terms.items():
   # Constant columns are structurally unavailable effects, not estimated zeros.
   varied0=[c for c in columns if eligible[c].std(ddof=0)>1e-12];dropped=sorted(set(columns)-set(varied0));varied=[];collinear=[];current=np.ones((n,1));rank=1
   for column in varied0:
    values=eligible[column].to_numpy(float);candidate=np.column_stack([current,(values-values.mean())/values.std()]);newrank=np.linalg.matrix_rank(candidate)
    if newrank>rank:varied.append(column);current=candidate;rank=newrank
    else:collinear.append(column)
   x=eligible[varied].to_numpy(float);fit=fit_ols(x,y,group);assert fit['rank']==fit['p'];pred=np.full(n,np.nan);nullpred=np.full(n,np.nan)
   for fold,(train,test) in enumerate(folds):
    assert set(group[train]).isdisjoint(set(group[test]))
    trainx,mean,sd=standardize(x[train]);testx,_,_=standardize(x[test],mean,sd);beta=np.linalg.lstsq(trainx,y[train],rcond=None)[0];pred[test]=testx@beta;nullpred[test]=np.mean(y[train]);foldrows.append(dict(scenario=scenario,outcome=outcome,level=int(level),model=name,fold=fold,n_train=len(train),n_test=len(test),train_regions=len(np.unique(group[train])),train_design_rank=int(np.linalg.matrix_rank(trainx)),train_design_parameters=trainx.shape[1],test_regions=len(np.unique(group[test])),rmse=float(np.sqrt(np.mean((y[test]-pred[test])**2))),mae=float(np.mean(np.abs(y[test]-pred[test])))))
   for j,term in enumerate(['intercept']+varied):coefficients.append(dict(scenario=scenario,outcome=outcome,level=int(level),model=name,term=term,beta=float(fit['beta'][j]),se_cluster_region=float(fit['se'][j]),ci95_lower=float(fit['ci_lower'][j]),ci95_upper=float(fit['ci_upper'][j]),predictor_mean=None if j==0 else float(fit['mean'][j-1]),predictor_sd=None if j==0 else float(fit['sd'][j-1]),unit='Yunits per1SD predictor;interceptatpredictormeans',ci_dof=regions-1,ci_conditional_on_recorded_population_values=True))
   oof_sse=float(np.sum((y-pred)**2));nullsse=float(np.sum((y-nullpred)**2));rows.append(dict(scenario=scenario,outcome=outcome,level=int(level),model=name,n=n,regions=int(regions),parameters=fit['p'],rank=fit['rank'],condition_number=fit['condition_number'],outcome_min=float(np.min(y)),outcome_max=float(np.max(y)),outcome_median=float(np.median(y)),max_cooks_distance=float(np.max(fit['cooks'])),n_cooks_above_descriptive_4_over_n=int(np.sum(fit['cooks']>4/n)),r2=fit['r2'],adjusted_r2=fit['adj_r2'],group_oof_rmse=float(np.sqrt(np.mean((y-pred)**2))),group_oof_mae=float(np.mean(np.abs(y-pred))),group_oof_r2_train_mean_baseline=1-oof_sse/nullsse if nullsse>0 else None,dropped_constant_terms='|'.join(dropped),dropped_collinear_terms='|'.join(collinear),cv_training_rank_deficient_folds=int(sum(r['train_design_rank']<r['train_design_parameters'] for r in foldrows if r['scenario']==scenario and r['level']==int(level) and r['model']==name)),ci='regionclusterCR1,tcriticalG-1',interpretation='descriptiveassociation,notcausal'))
   mi=moran(fit['residual'],weight,config['moran_permutations'],config['seed']);oofmi=moran(y-pred,weight,config['moran_permutations'],config['seed']);spatial.append(dict(scenario=scenario,outcome=outcome,level=int(level),model=name,**mi,**{'group_oof_'+k:v for k,v in oofmi.items()},**spmeta))
   for i,row in enumerate(eligible.itertuples()):predictions.append(dict(scenario=scenario,outcome=outcome,level=int(level),model=name,system_id=row.system_id,center_id=row.center_id,name=row.name,region=row.region,lat=row.lat,lon=row.lon,source_valued_outcome=float(y[i]),fitted=float(fit['fitted'][i]),residual=float(fit['residual'][i]),group_oof_prediction=float(pred[i]),group_oof_residual=float(y[i]-pred[i]),cv_fold=int(foldbyrow[i]),leverage=float(fit['hat'][i]),cooks_distance=float(fit['cooks'][i])))
 return rows,coefficients,predictions,spatial,samples,foldrows,gates

def figures(metrics,coef,predictions):
 import matplotlib;matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 if metrics.empty:return
 for level in sorted(metrics.level.unique()):
  z=coef[(coef.scenario=='primary')&coef.level.eq(level)&coef.model.eq('M3')&coef.term.ne('intercept')];fig,ax=plt.subplots(figsize=(9,max(4,len(z)*.35)))
  if len(z):ax.errorbar(z.beta,np.arange(len(z)),xerr=[z.beta-z.ci95_lower,z.ci95_upper-z.beta],fmt='o',capsize=3);ax.set_yticks(np.arange(len(z)),z.term);ax.axvline(0,color='gray',lw=.8);ax.set_xlabel('Descriptive coefficient / predictor SD; 95% region-cluster CI');ax.set_title(f'M3, level{level}, common sample\nConditional on mixed primary/secondary2010 values; descriptive association')
  fig.tight_layout();fig.savefig(ROOT/f'coefficients_level{level}.png',dpi=160);plt.close(fig)
  z=predictions[(predictions.scenario=='primary')&predictions.level.eq(level)&predictions.model.eq('M3')].copy()
  if len(z):
   z['plot_lon']=np.where(z.lon<0,z.lon+360,z.lon);lim=float(np.quantile(np.abs(z.group_oof_residual),.95));fig,ax=plt.subplots(figsize=(12,5));sc=ax.scatter(z.plot_lon,z.lat,c=z.group_oof_residual,s=8,cmap='RdBu_r',vmin=-lim,vmax=lim,alpha=.8);ax.set_xlabel('Longitude (negative longitudes wrapped +360)');ax.set_ylabel('Latitude');ax.set_title(f'M3 level{level}: held-out-region residual geography\nMixed primary/secondary2010 source values; color clipped at95th abs percentile');fig.colorbar(sc,ax=ax,label='Source-valued outcome minus grouped-CV prediction, percentage points');fig.tight_layout();fig.savefig(ROOT/f'residual_geography_level{level}.png',dpi=160);plt.close(fig)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--stage',choices=['coverage','full'],default='coverage');a=ap.parse_args();config=json.loads((ROOT/'analysis_inputs.json').read_text());source_coverage(config)
 if a.stage=='coverage':print('ACTUAL_SOURCE_COVERAGE_WRITTEN_NO_REGRESSION_RESULTS');return
 try:frame,hashes=prepare(config)
 except (FileNotFoundError,ValueError,RuntimeError) as e:dump(ROOT/'run_receipt.json',dict(status='BLOCKED_FINAL_ROUTED_MODEL_PENDING_OR_SCHEMA_ERROR',error=str(e),invented_results=False));raise
 terms=config['model_terms'];proxy={m:list(v)+(['sown_farmland2008_source_harmonized'] if m in ['M2','M3'] else []) for m,v in terms.items()}
 scenarios=[('primary','outcome_system_change_pct',terms),('source_harmonized_agro2008_sensitivity','outcome_system_change_pct',proxy),('rural_outcome_sensitivity','outcome_rural_change_pct',terms),('positive_population_logratio_sensitivity','outcome_system_log_change_100',terms)]
 for bound in ['lower','upper']:
  bt={m:list(v)+(['bonitet_experimental_'+bound] if m in ['M2','M3'] else []) for m,v in terms.items()};scenarios.append(('experimental_bonitet_'+bound+'_bound_sensitivity','outcome_system_change_pct',bt))
 results=[[] for _ in range(7)]
 # Pure-primary quality gate uses the same full unit frame; even n=0 emits sample gates.
 for scenario,outcome,t in scenarios:
  for target,values in zip(results,fit_scenario(frame,scenario,outcome,t,config)):target.extend(values)
 for target,values in zip(results,fit_scenario(frame,'pure_primary_population_source_sensitivity','outcome_system_change_pct',terms,config,pure_only=True)):target.extend(values)
 for target,values in zip(results,fit_scenario(frame,'reviewed_primary_supported_population_source_sensitivity','outcome_system_change_pct',terms,config,supported_only=True)):target.extend(values)
 names=['model_metrics.csv','coefficient_intervals.csv','system_predictions.parquet','spatial_residual_diagnostics.csv','common_sample_membership.parquet','grouped_cv_folds.csv','sample_gates.csv'];dfs=[]
 for name,values in zip(names,results):
  d=pd.DataFrame(values);dfs.append(d);d.to_parquet(ROOT/name,index=False) if name.endswith('.parquet') else d.to_csv(ROOT/name,index=False)
 # Experimental lower/upper are coherent source-interval endpoints, never independent per-NP draws.
 sampletable=dfs[4];lo=sampletable[sampletable.scenario.eq('experimental_bonitet_lower_bound_sensitivity')].set_index('system_id').in_common_sample;hi=sampletable[sampletable.scenario.eq('experimental_bonitet_upper_bound_sensitivity')].set_index('system_id').in_common_sample;assert lo.sort_index().equals(hi.sort_index())
 # Same sample and folds must hold for every fitted M1/M2/M3 comparison.
 predictions=dfs[2]
 if len(predictions):
  assert predictions.groupby(['scenario','outcome','level','system_id']).model.nunique().eq(3).all();assert predictions.groupby(['scenario','outcome','level','system_id']).cv_fold.nunique().eq(1).all()
  residuals=predictions.groupby(['scenario','level','model','region']).agg(n=('residual','size'),mean_residual=('residual','mean'),mean_oof_residual=('group_oof_residual','mean'),rmse_oof=('group_oof_residual',lambda v:np.sqrt(np.mean(v*v)))).reset_index();residuals.to_csv(ROOT/'regional_residual_summary.csv',index=False)
 if len(dfs[0]):
  metrics=dfs[0];comparisons=[]
  for key,g in metrics.groupby(['scenario','outcome','level']):
   g=g.set_index('model');assert g.n.nunique()==1
   for before,after in [('M1','M2'),('M2','M3')]:
    assert g.loc[after,'r2']+1e-9>=g.loc[before,'r2']
    comparisons.append(dict(scenario=key[0],outcome=key[1],level=int(key[2]),before=before,after=after,common_n=int(g.loc[before,'n']),stable_group_cv_design=bool(g.loc[before,'cv_training_rank_deficient_folds']==0 and g.loc[after,'cv_training_rank_deficient_folds']==0),before_rank_deficient_folds=int(g.loc[before,'cv_training_rank_deficient_folds']),after_rank_deficient_folds=int(g.loc[after,'cv_training_rank_deficient_folds']),delta_training_r2=float(g.loc[after,'r2']-g.loc[before,'r2']),delta_group_oof_rmse=float(g.loc[after,'group_oof_rmse']-g.loc[before,'group_oof_rmse']),delta_group_oof_r2=float(g.loc[after,'group_oof_r2_train_mean_baseline']-g.loc[before,'group_oof_r2_train_mean_baseline'])))
  pd.DataFrame(comparisons).to_csv(ROOT/'same_sample_model_comparisons.csv',index=False)
 figures(dfs[0],dfs[1],dfs[2]);hashes_after={p:sha(REPO/p) for p in hashes};changed=[p for p in hashes if hashes[p]!=hashes_after[p]]
 if changed:dump(ROOT/'run_receipt.json',dict(status='INVALID_SOURCE_CHANGED_DURING_ANALYSIS',changed_sources=changed,source_sha256_before=hashes,source_sha256_after=hashes_after));raise RuntimeError('SOURCE_CHANGED_DURING_ANALYSIS')
 dump(ROOT/'run_receipt.json',dict(status='ACTUALLY_COMPUTED_DESCRIPTIVE_REGRESSIONS' if len(dfs[0]) else 'NO_LEVEL_PASSED_SAMPLE_GATE',computed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),source_sha256=hashes,source_sha256_before=hashes,source_sha256_after=hashes_after,source_unchanged_verified=True,config_sha256=sha(ROOT/'analysis_inputs.json'),code_sha256=sha(Path(__file__)),system_rows=len(frame),models_computed=len(dfs[0]),same_sample_and_cv_folds_verified=True,causal_claim=False,strict_bonitet_available=False,limitations=['2021mass and contemporary road delineation used for retrospective2010-2021 descriptive association','Masspopulation2021 creates mechanical/endogenous association with total-system2021outcome;baselinecontrol andruraloutcome sensitivity do not provecausality','2010strictfarmlandshare unavailable;sourceharmonized2008onlyseparate sensitivity','Baseline2010municipalgrainyield uses2021stablebridge;historicalboundaryequivalenceunproven','Soilqualitylowinputmaize isnotRussianbonitet','ExperimentalAtlasbonitetboundscenarios usecoarseunadoptednonblindgeoreference;lower/upperregressionsarenotcompleteuncertaintybounds','Most2010ruralpopulationvalues are secondary confidentiality-protected exactscope-unverified; outcomes andweights are conditional on published/secondary numericvalues, not validated groundtruth','Complete-case sample selection and regiongroupCV are not representative nationalcausalidentification','CI conditional on fixed modeledcatchments and data;doesnotpropagate fullrouting/source-linkage uncertainty']))
 print(json.dumps({'models':len(dfs[0]),'status':'DONE'},ensure_ascii=False))
if __name__=='__main__':main()
