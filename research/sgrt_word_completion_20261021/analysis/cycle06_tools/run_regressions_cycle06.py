#!/usr/bin/env python3
"""Comparable descriptive Word M1/M2/M3; refuses to fabricate pending road outputs."""
from pathlib import Path
import argparse,hashlib,json,datetime
import numpy as np,pandas as pd,pyarrow.parquet as pq
from scipy import sparse,stats
from scipy.spatial import cKDTree
from sklearn.model_selection import GroupKFold
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[3];ROOT=None;INPUT_PATH=None
OLD_SOURCE=HERE.parent/'run_regressions.py'
MODEL_HELPERS=[HERE.parents[1]/'model/large_city_accessibility_cycle05.py',HERE.parents[1]/'model/configuration_cycle06.py']
def resolve(value):
 p=Path(value);return p if p.is_absolute() else REPO/p
def label(p):
 try:return str(p.relative_to(REPO))
 except ValueError:return str(p)
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
 directory=resolve(config['context_directory']);model=resolve(config['model_output']);tables={}
 for alias,spec in config['rural_features'].items():
  path=resolve(spec['path']) if 'path' in spec else (model if spec['table'] in ['network_accessibility.parquet','nodes.parquet'] else directory)/spec['table'];tables.setdefault(path,set()).update(spec.get('fields',[spec.get('field')]))
 return tables

def source_coverage(config):
 axis=read(resolve(config['axis']),['id','population_2010','population_2021','population_value_quality_2010','population_value_quality_2021']);rows=[];hashes={str(resolve(config['axis'])):sha(resolve(config['axis']))}
 for path,fields in bindings(config).items():
  if not path.exists():
   rows.extend(dict(source=label(path),feature=f,status='PENDING_MODEL_OUTPUT',nonnull=None,axis_rows=len(axis)) for f in fields);continue
  d=read(path,['id']+sorted(fields));assert d.id.is_unique;z=axis[['id']].merge(d,on='id',how='left',validate='one_to_one');hashes[label(path)]=sha(path)
  rows.extend(dict(source=label(path),feature=f,status='ACTUALLY_PRESENT',nonnull=int(z[f].notna().sum()),axis_rows=len(axis)) for f in fields)
 pd.DataFrame(rows).to_csv(ROOT/'source_coverage_summary.csv',index=False)
 q=axis.copy();q['population_value_quality_2010']=q.population_value_quality_2010.fillna('UNKNOWN_SOURCE_QUALITY');q.groupby('population_value_quality_2010').agg(entity_rows=('id','size'),known_population2010_rows=('population_2010','count')).reset_index().to_csv(ROOT/'original_axis_population2010_source_quality_counts.csv',index=False)
 dump(ROOT/'source_coverage_receipt.json',dict(status='SOURCE_COVERAGE_ONLY_NOT_REGRESSION_RESULTS',source_sha256=hashes,selected_model_output=config['model_output'],observed_axis_rows=len(axis),original_axis_complete_population_pair_rows=int(axis[['population_2010','population_2021']].notna().all(axis=1).sum()),primary_design='all M1/M2/M3 same system sample per hierarchy level and scenario; no missing=zero'))

def apply_whole_system_population_scope(systems,nodes):
 """Source-member completeness cannot replace missing own-center population."""
 out=systems.copy();centers=nodes.set_index('id')
 out['analysis_center_is_nonadditive_external_context']=out.center_id.map(centers.axis_kind).eq('external_service_provider')&~out.center_id.map(centers.is_additive_source_unit).eq(True)
 known=[]
 for year in [2010,2021]:
  pop=pd.to_numeric(out.center_id.map(centers[f'population_{year}']),errors='coerce')
  ok=pop.notna()&np.isfinite(pop)&pop.ge(0);known.append(ok)
  out[f'analysis_center_own_population_observed_{year}']=ok
  out[f'analysis_whole_including_center_population_complete_{year}']=out[f'system_population_complete_{year}'].eq(True)&ok
 out['analysis_whole_system_excluded_unknown_or_invalid_center_population']=~(known[0]&known[1])
 return out

def prepare(config):
 model=resolve(config['model_output']);required=['systems.parquet','memberships.parquet','nodes.parquet','own_mass_components.parquet','network_accessibility.parquet','system_configurations.parquet','run_receipt.json'];absent=[f for f in required if not (model/f).exists()]
 if absent:raise FileNotFoundError('ROUTED_FINAL_MODEL_PENDING:'+','.join(absent))
 modelreceipt=json.loads((model/'run_receipt.json').read_text())
 if modelreceipt.get('status')!='COMPUTED_PENDING_STRICT_SCIENTIFIC_DATA_REVIEW':raise ValueError('Full routed model receipt not computed:'+modelreceipt.get('status','unknown'))
 ownspec=config['own_center_network'];pairpath=resolve(ownspec['path']);pairreceipt=resolve(ownspec['receipt']);pr=json.loads(pairreceipt.read_text())
 if pr.get('status')!='ACTUALLY_COMPUTED_ALL_LEVEL_DIRECT_NETWORK_DEMOGRAPHIC_GRADIENTS':raise ValueError('Own-center direct route receipt is not complete')
 for file in ['nodes.parquet','memberships.parquet']:
  if pr.get('source_sha256',{}).get(label(model/file))!=sha(model/file):raise ValueError('Own-center direct routes belong to different model '+file)
 if pr.get('outputs',{}).get(pairpath.name)!=sha(pairpath):raise ValueError('Own-center direct route pairs differ from source receipt')
 pairdata=read(pairpath,['id','level','center_id','direct_network_minutes'])
 if pairdata.duplicated(['level','id']).any():raise ValueError('Duplicated own-center direct route pairs')
 if (pairdata.direct_network_minutes.dropna()<0).any():raise ValueError('Negative own-center network time')
 watched=[model/f for f in required]+[pairpath,pairreceipt]+list(bindings(config))+[resolve(config['axis']),INPUT_PATH,ROOT/'effective_analysis_inputs.json',Path(__file__),OLD_SOURCE,resolve(config['model_inputs'])]+[resolve(x) for x in config.get('provenance_sidecars',[])]+[HERE.parents[1]/'model/run_word_model_cycle06.py',*MODEL_HELPERS];hashes_before={label(p):sha(p) for p in watched}
 systems=pd.read_parquet(model/'systems.parquet');assert not systems.duplicated(['level','center_id']).any()
 ns=pq.read_schema(model/'nodes.parquet').names;recovery_columns=[c for c in ns if c in ['original_population_2010','original_population_value_quality_2010'] or c.startswith('recovered2010_')]
 if recovery_columns:read(model/'nodes.parquet',['id','population_2010','population_value_quality_2010']+recovery_columns).to_parquet(ROOT/'node_source2010_recovery_audit.parquet',index=False)
 nodes=read(model/'nodes.parquet',['id','type','region','_population_axis_row','population_2010','population_2021','population_value_quality_2010','population_value_quality_2021','lat','lon','accepted_statistical_rural_role2021','axis_kind','is_additive_source_unit'])
 if config['rural_volume_policy']!=modelreceipt.get('statistical_rural_volume_policy'):raise ValueError('Analysis and selected model statistical rural policies differ')
 if not nodes.accepted_statistical_rural_role2021.dropna().isin([True,False]).all():raise ValueError('Nonboolean V3 rural role')
 for path,fields in bindings(config).items():nodes=nodes.merge(read(path,['id']+sorted(fields)),on='id',how='left',validate='one_to_one')
 for alias,spec in config['rural_features'].items():
  fs=spec.get('fields',[spec.get('field')]);nodes[alias]=nodes[fs].astype(float).mean(axis=1).where(nodes[fs].notna().all(axis=1)) if len(fs)>1 else pd.to_numeric(nodes[fs[0]],errors='coerce').astype(float)
 paired_bonitet=nodes[['bonitet_experimental_lower','bonitet_experimental_upper']].notna().all(axis=1)&nodes.bonitet_experimental_lower.ge(0)&nodes.bonitet_experimental_upper.le(125)&nodes.bonitet_experimental_lower.le(nodes.bonitet_experimental_upper)
 nodes.loc[~paired_bonitet,['bonitet_experimental_lower','bonitet_experimental_upper']]=np.nan
 memberschema=pq.read_schema(model/'memberships.parquet').names;assignment_columns=[f'center_id_l{int(l)}' for l in sorted(systems.level.unique())]
 members=read(model/'memberships.parquet',['id']+assignment_columns);nodes=nodes.merge(members,on='id',validate='one_to_one')
 role=nodes.accepted_statistical_rural_role2021.astype('boolean');selected=role.fillna(False)
 if config['rural_volume_policy']=='unknown_as_rural_upperbound':selected=selected|role.isna()
 rural=nodes._population_axis_row.eq(True)&selected;features=list(config['rural_features'])+['rural_own_center_minutes'];aggregates=[];quality_composition=[];quality_unit_rows=[]
 native=nodes[nodes._population_axis_row.eq(True)].copy();native['rural']=role.loc[native.index];native['rural_role_unknown']=native.rural.isna();native['source_quality']=native.population_value_quality_2010.fillna('UNKNOWN_SOURCE_QUALITY')
 national_quality=native.groupby(['region','rural','source_quality'],dropna=False).agg(source_rows=('id','size'),known_population_rows=('population_2010','count'),known_population_value_sum=('population_2010',lambda v:v.sum(min_count=1))).reset_index();national_quality['scope']='final_model_population_axis_after_reviewed2010_recovery';national_quality.to_csv(ROOT/'node_2010_sourcequality_by_region_and_rural.csv',index=False)

 for level in sorted(systems.level.unique()):
  col=f'center_id_l{int(level)}'
  unitnodes=nodes[nodes._population_axis_row.eq(True)&nodes[col].notna()].copy();unitnodes['center_id']=unitnodes[col];unitnodes['rural_external']=selected.loc[unitnodes.index]&unitnodes.id.ne(unitnodes.center_id);unitnodes['unknown_role_external']=role.loc[unitnodes.index].isna()&unitnodes.id.ne(unitnodes.center_id)
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
  z=nodes.loc[rural&nodes[col].notna()&nodes.id.ne(nodes[col]),['id',col,'population_2010']+list(config['rural_features'])].copy();z=z.rename(columns={col:'center_id'})
  ownpairs=pairdata[pairdata.level.eq(level)].drop(columns='level').rename(columns={'direct_network_minutes':'rural_own_center_minutes'});expected=nodes[['id',col]].rename(columns={col:'center_id'});check=ownpairs[['id','center_id']].merge(expected,on='id',how='left',suffixes=('_route','_model'),validate='one_to_one')
  if not check.center_id_route.eq(check.center_id_model).all():raise ValueError('Own-center direct route identity differs from this hierarchy level')
  z=z.merge(ownpairs,on=['id','center_id'],how='left',validate='one_to_one')
  # Resident context, not farmland mean. A missing population weight contributes no known weight.
  z['weight']=pd.to_numeric(z.population_2010,errors='coerce').where(z.population_2010.ge(0));total=z.groupby('center_id').weight.sum(min_count=1);observed_n=z.groupby('center_id').size();knownweight_n=z.groupby('center_id').weight.count();agg=pd.DataFrame({'rural_weight_total2010':total,'rural_members_n':observed_n,'rural_members_known_population2010_n':knownweight_n});agg['level']=level;unknown=unitnodes.unknown_role_external.groupby(unitnodes.center_id).sum();agg['rural_unknown_role_external_n']=unknown.reindex(agg.index,fill_value=0)
  for feature in features:
   valid=z[feature].notna()&np.isfinite(z[feature])&z.weight.notna();num=(z[feature]*z.weight).where(valid).groupby(z.center_id).sum(min_count=1);den=z.weight.where(valid).groupby(z.center_id).sum(min_count=1);coverage=den/total.where(total.gt(0));agg[feature+'_population_coverage']=coverage;agg[feature]=(num/den.where(den.gt(0))).where(coverage.ge(config['minimum_weighted_feature_coverage'])&observed_n.eq(knownweight_n))
  aggregates.append(agg.reset_index())
 systems=systems.merge(pd.concat(aggregates,ignore_index=True),on=['level','center_id'],how='left',validate='one_to_one')
 assert np.allclose(systems.bonitet_experimental_lower_population_coverage.fillna(-1),systems.bonitet_experimental_upper_population_coverage.fillna(-1));systems['bonitet_bounds_share_identical_population_weights_and_coverage']=True
 systems=systems.merge(pd.concat(quality_unit_rows,ignore_index=True),on=['level','center_id'],how='left',validate='one_to_one');pd.concat(quality_composition,ignore_index=True).to_parquet(ROOT/'system_population_source_quality_composition.parquet',index=False)
 mass=read(model/'own_mass_components.parquet',['id','own_positive_mass']).rename(columns={'id':'center_id'})
 if 'own_positive_mass' in systems:systems=systems.rename(columns={'own_positive_mass':'model_system_own_positive_mass'})
 systems=systems.merge(mass,on='center_id',how='left',validate='many_to_one')
 if 'model_system_own_positive_mass' in systems:assert np.allclose(systems.model_system_own_positive_mass,systems.own_positive_mass,equal_nan=True,rtol=1e-12,atol=1e-12),'SYSTEM_MASS_COMPONENT_REFERENCE_MISMATCH'
 configs=read(model/'system_configurations.parquet',['level','center_id','modeled_configuration','own_order_shared_origin_fraction','nested_child_configuration','nested_shared_origin_fraction']);systems=systems.merge(configs,on=['level','center_id'],how='left',validate='one_to_one')
 allowed_labels={'polycentric_peer_field_potential','monocentric_field_potential','structural_assignment_unit','configuration_unknown'}
 if not set(systems.modeled_configuration.dropna())<=allowed_labels:raise ValueError('Unrecognized cycle06 own-order configuration label')
 for field in ['own_order_shared_origin_fraction','nested_shared_origin_fraction']:
  if not systems[field].dropna().between(0,1).all():raise ValueError('Configuration source fraction outside0..1')
 systems['polycentric_potential']=systems.modeled_configuration.map({'polycentric_peer_field_potential':1.,'monocentric_field_potential':0.})
 systems['configuration_shared_origin_fraction']=systems.own_order_shared_origin_fraction.where(systems.polycentric_potential.notna())
 systems['configuration_observed']=systems.polycentric_potential.notna()
 systems['nested_child_polycentric_potential']=systems.nested_child_configuration.map({'polycentric_child_complex_potential':1.,'monocentric_child_field_potential':0.})
 # Structural L1 and unresolved fields are unknown, never mono; child complexes do not fill own-order missingness.
 if systems.loc[systems.level.eq(1),'polycentric_potential'].notna().any():raise ValueError('Level1 structural units cannot have an own-order mono/poly regressor')
 systems.groupby(['level','modeled_configuration'],dropna=False).size().rename('systems').reset_index().to_csv(ROOT/'configuration_source_coverage.csv',index=False)
 systems['log_own_mass2021']=np.log(systems.own_positive_mass.where(systems.own_positive_mass.gt(0)))
 systems['log_baseline_system_population2010']=np.log(systems.system_population_known_sum_2010.where(systems.system_population_known_sum_2010.gt(0)))
 systems['log_rural_own_center_minutes']=np.log1p(systems.rural_own_center_minutes.where(systems.rural_own_center_minutes.ge(0)))
 systems['log_rural_large_city_minutes']=np.log1p(systems.rural_large_city_minutes.where(systems.rural_large_city_minutes.ge(0)))
 systems['log_agro_grain_yield2010']=np.log1p(systems.agro_grain_yield2010.where(systems.agro_grain_yield2010.ge(0)))
 systems['log_agro_grain_yield2021']=np.log1p(systems.agro_grain_yield2021.where(systems.agro_grain_yield2021.ge(0)))
 systems['mass_x_suburban']=systems.log_own_mass2021*systems.rural_suburban_share;systems['yield2010_x_polycentric']=systems.log_agro_grain_yield2010*systems.polycentric_potential;systems['yield2021_x_polycentric']=systems.log_agro_grain_yield2021*systems.polycentric_potential
 systems=apply_whole_system_population_scope(systems,nodes)
 scope_columns=['level','center_id','analysis_center_is_nonadditive_external_context','analysis_center_own_population_observed_2010','analysis_center_own_population_observed_2021','system_population_complete_2010','system_population_complete_2021','analysis_whole_including_center_population_complete_2010','analysis_whole_including_center_population_complete_2021','analysis_whole_system_excluded_unknown_or_invalid_center_population']
 systems[scope_columns].to_csv(ROOT/'whole_system_outcome_scope.csv',index=False)
 complete=systems.analysis_whole_including_center_population_complete_2010.eq(True)&systems.analysis_whole_including_center_population_complete_2021.eq(True)&systems.system_population_known_sum_2010.gt(0)&systems.system_population_known_sum_2021.ge(0)
 systems['outcome_system_change_pct']=((systems.system_population_known_sum_2021/systems.system_population_known_sum_2010-1)*100).where(complete)
 systems['outcome_system_log_change_100']=100*np.log((systems.system_population_known_sum_2021/systems.system_population_known_sum_2010).where(complete&systems.system_population_known_sum_2021.gt(0)))
 complete_rural=systems.rural_external_population_complete_2010.eq(True)&systems.rural_external_population_complete_2021.eq(True)&systems.rural_external_population_known_sum_2010.gt(0)&systems.rural_external_population_known_sum_2021.ge(0)
 systems['outcome_rural_change_pct']=((systems.rural_external_population_known_sum_2021/systems.rural_external_population_known_sum_2010-1)*100).where(complete_rural)
 systems['system_id']=systems.level.astype(str)+':'+systems.center_id.astype(str);systems.to_parquet(ROOT/'system_analysis_features.parquet',index=False)
 hashes_after={label(p):sha(p) for p in watched}
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
  eligible=d.loc[finite].copy().sort_values('system_id');n=len(eligible);regions=eligible.region.nunique();gate=dict(configuration_unknown_systems=int((~d.configuration_observed).sum()),comparison_family=scenario.split('__')[0],scenario=scenario,outcome=outcome,level=int(level),all_systems=len(d),outcome_observed=int(d[outcome].notna().sum()),common_sample=n,regions=int(regions),pure_primary_units_among_all=int((d.analysis_system2010_primary_source_only.eq(True)&d.analysis_system2021_primary_source_only.eq(True)).sum()),primary_supported_units_among_all=int((d.analysis_system2010_primary_supported_only.eq(True)&d.analysis_system2021_primary_source_only.eq(True)).sum()),common_sample_median_system2010_secondary_population_share=float(eligible.analysis_system2010_secondary_share_of_known_population.median()) if n and eligible.analysis_system2010_secondary_share_of_known_population.notna().any() else None,common_sample_median_rural2010_secondary_population_share=float(eligible.analysis_rural_external2010_secondary_share_of_known_population.median()) if n and eligible.analysis_rural_external2010_secondary_share_of_known_population.notna().any() else None);gates.append(gate)
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
 basis=str(metrics.iloc[0].get('grid_basis','unspecified'))
 for level in sorted(metrics.level.unique()):
  z=coef[(coef.scenario=='B_M1_M2_M3_configuration_observed__primary')&coef.level.eq(level)&coef.model.eq('M3')&coef.term.ne('intercept')];fig,ax=plt.subplots(figsize=(9,max(4,len(z)*.35)))
  if len(z):ax.errorbar(z.beta,np.arange(len(z)),xerr=[z.beta-z.ci95_lower,z.ci95_upper-z.beta],fmt='o',capsize=3);ax.set_yticks(np.arange(len(z)),z.term);ax.axvline(0,color='gray',lw=.8);ax.set_xlabel('Descriptive coefficient / predictor SD; 95% region-cluster CI');ax.set_title(f'M3, level{level}, {basis}, common sample\nConditional on source2010 values; soil is an explicit proxy; descriptive association')
  fig.tight_layout();fig.savefig(ROOT/f'coefficients_level{level}.png',dpi=160);plt.close(fig)
  z=predictions[(predictions.scenario=='B_M1_M2_M3_configuration_observed__primary')&predictions.level.eq(level)&predictions.model.eq('M3')].copy()
  if len(z):
   z['plot_lon']=np.where(z.lon<0,z.lon+360,z.lon);lim=float(np.quantile(np.abs(z.group_oof_residual),.95));fig,ax=plt.subplots(figsize=(12,5));sc=ax.scatter(z.plot_lon,z.lat,c=z.group_oof_residual,s=8,cmap='RdBu_r',vmin=-lim,vmax=lim,alpha=.8);ax.set_xlabel('Longitude (negative longitudes wrapped +360)');ax.set_ylabel('Latitude');ax.set_title(f'M3 level{level}, {basis}: held-out-region residual geography\nMixed primary/secondary2010 source values; color clipped at95th abs percentile');fig.colorbar(sc,ax=ax,label='Source-valued outcome minus grouped-CV prediction, percentage points');fig.tight_layout();fig.savefig(ROOT/f'residual_geography_level{level}.png',dpi=160);plt.close(fig)


def base_scenario_design(config):
 terms=config['model_terms']
 proxy={m:list(v)+(['sown_farmland2008_source_harmonized'] if m in ['M2','M3'] else []) for m,v in terms.items()}
 scenarios=[('primary','outcome_system_change_pct',terms,False,False),('source_harmonized_agro2008_sensitivity','outcome_system_change_pct',proxy,False,False),('rural_outcome_sensitivity','outcome_rural_change_pct',terms,False,False),('positive_population_logratio_sensitivity','outcome_system_log_change_100',terms,False,False)]
 land={m:list(v)+(['regional_sown_farmland2021'] if m in ['M2','M3'] else []) for m,v in terms.items()};scenarios.append(('regional_actual_land2021_sensitivity','outcome_system_change_pct',land,False,False))
 for bound in ['lower','upper']:
  t={m:list(v)+(['bonitet_experimental_'+bound] if m in ['M2','M3'] else []) for m,v in terms.items()};scenarios.append(('experimental_bonitet_'+bound+'_bound_sensitivity','outcome_system_change_pct',t,False,False))
 scenarios.extend([('pure_primary_population_source_sensitivity','outcome_system_change_pct',terms,True,False),('reviewed_primary_supported_population_source_sensitivity','outcome_system_change_pct',terms,False,True)])
 census={m:list(v)+(['municipal_actual_sown_farmland2021'] if m in ['M2','M3'] else []) for m,v in terms.items()};scenarios.append(('ten_region_municipal_agrocensus2021_separate_sensitivity','outcome_system_change_pct',census,False,False))
 historical={m:[c.replace('grain_yield2021','grain_yield2010').replace('yield2021_x_polycentric','yield2010_x_polycentric') for c in v] for m,v in terms.items()};scenarios.append(('historical_grain2010_primary2021_parent_boundary_unproven_sensitivity','outcome_system_change_pct',historical,False,False))
 return scenarios

def scenario_design(config):
 # Distinct cohorts: compare scores only within a family, never full M2 against subset M3.
 result=[]
 for name,outcome,terms,pure,supported in base_scenario_design(config):
  result.append(('A_M1_M2__'+name,outcome,{m:terms[m] for m in ['M1','M2']},pure,supported))
  result.append(('B_M1_M2_M3_configuration_observed__'+name,outcome,terms,pure,supported))
 return result

def validate_config(config):
 if config.get('rural_volume_policy') not in {'known_rural_lowerbound','unknown_as_rural_upperbound'}:raise ValueError('Explicit corrected model rural policy required')
 if config.get('whole_system_outcome_scope_policy')!='require_observed_own_center_population_both_years_no_external_aggregate_injection':raise ValueError('Whole-including-center outcomes require independent own-center population, not source-member completeness')
 if config.get('configuration_design')!='cycle06_own_order_peer_field_two_comparison_families':raise ValueError('Explicit corrected cycle06 configuration design required')
 if 'configuration_shared_origin_fraction' not in config['model_terms']['M3'] or 'configuration_ambiguity' in config['model_terms']['M3']:raise ValueError('Use the declared own-order shared-origin fraction, not obsolete ambiguity')
 if set(config['model_terms'])!={'M1','M2','M3'}:raise ValueError('Exactly M1/M2/M3 are required')
 if not set(config['model_terms']['M1'])<=set(config['model_terms']['M2'])<=set(config['model_terms']['M3']):raise ValueError('Declared nested model terms are not nested')
 if config['cluster_bootstrap_replicates']<199:raise ValueError('At least199 region-bootstrap replicates must be preregistered')
 if not config.get('soil_proxy_semantics'):raise ValueError('Explicit soil/experimental bonitet proxy semantics required')
 if config['rural_features']['rural_large_city_minutes'].get('field')!='nearest_large_city_network_minutes':raise ValueError('Large-city contextual modifier must retain the corrected estimand')
 if not all(k in config.get('own_center_network',{}) for k in ['path','receipt']):raise ValueError('Primary center-access requires every-level direct route pairs and exact source receipt')
 if any('log_rural_own_center_minutes' not in config['model_terms'][m] for m in ['M1','M2','M3']):raise ValueError('All primary models must include own-center direct access')
 for key in ['municipal_actual_sown_farmland2021','regional_sown_farmland2021']:
  if key not in config['rural_features']:raise ValueError('Separate agricultural denominator definitions required')

def preregistration(config):
 modelconfig=resolve(config['model_inputs']);base=HERE.parents[1];model=resolve(config['model_output']);sources=[Path(__file__),OLD_SOURCE,modelconfig,base/'model/run_word_model_cycle06.py',*MODEL_HELPERS]+[resolve(x) for x in config.get('provenance_sidecars',[])]+[model/f for f in ['systems.parquet','memberships.parquet','nodes.parquet','own_mass_components.parquet','network_accessibility.parquet','system_configurations.parquet','configuration_preregistration.json','run_receipt.json','output_manifest.json']]+[resolve(config['axis']),*bindings(config),resolve(config['own_center_network']['path']),resolve(config['own_center_network']['receipt'])]
 return {'status':'PREREGISTERED_DESIGN_NO_MODEL_METRICS','analysis_inputs_sha256':sha(INPUT_PATH),'analysis_code_sha256':sha(Path(__file__)),'selected_model_output':config['model_output'],'model_inputs':label(modelconfig),'source_code_and_design_provenance':{label(p):sha(p) for p in sources},'rural_volume_policy':config['rural_volume_policy'],'primary_access_estimand':'2010 resident-population weighted direct rural member to its own system center at each hierarchy level on dated2021 roads; not nearest large city','own_center_network':config['own_center_network'],'base_design_models_per_level_before_sample_gates':45,'separately_named_additional_models_per_level_before_gates':10,'comparison_families':{'A':'M1/M2 complete-source common rows and folds','B':'M1/M2/M3 observed-own-order-configuration common rows and folds'},'cross_family_score_comparison_is_added_context_effect':False,'whole_system_outcome_scope_policy':config['whole_system_outcome_scope_policy'],'whole_system_outcome_scope':'Bothowncenterpopulations must be observedfinite nonnegative as well as source-membercohortcomplete; ctxMOW/SPB unknownowncityP excluded from whole-including-center outcomes. Rural-only outcomes/context/directpairledgers retained. Federalterritorypopulation never injected.','baseline_population_control_scope':'Source-membercohort published population; on externalctxrural sensitivity this is knownsource-members only, not invented wholecity population.','level1_configuration':'structural_assignment_unit maps to NA, never mono','configuration_regressor':'own-order peer-field potential plus own_order_shared_origin_fraction; no actual multicenter service-flow claim','nested_child_configuration':'preserved separately, never a fallback for own-order configuration','scenarios':[{'name':n,'outcome':o,'terms':t,'pure_primary_only':pure,'reviewed_primary_supported_only':sup} for n,o,t,pure,sup in scenario_design(config)],'same_sample_and_region_folds_within_each_M1_M2_M3_comparison':True,'region_bootstrap_replicates':config['cluster_bootstrap_replicates'],'bootstrap_scope':'resample whole regions; coefficient scale fixed to original common-sample predictor SD; no upstream recalibration','soil_proxy_semantics':config['soil_proxy_semantics'],'causal_claim':False,'model_metrics_read':False}

def verify_preregistration(config,review_path):
 p=ROOT/'preregistration.json'
 if not p.exists():raise FileNotFoundError('Run --stage preregister and obtain independent guardian review first')
 actual=json.loads(p.read_text());expected=preregistration(config)
 if actual!=expected:raise ValueError('Preregistered config/code/model provenance changed; create a new version and re-review before metrics')
 r=json.loads(review_path.read_text())
 if r.get('status')!='ACCEPTED' or r.get('preregistration_sha256')!=sha(p) or r.get('analysis_code_sha256')!=sha(Path(__file__)) or r.get('analysis_inputs_sha256')!=sha(INPUT_PATH) or r.get('checked_before_analysis_metrics') is not True:raise ValueError('Independent guardian preregistration approval missing or does not match this frozen design')
 return {label(p):sha(p),label(review_path):sha(review_path)}

def region_bootstrap(frame,metrics,predictions,config):
 rows=[]
 if metrics.empty:return pd.DataFrame(columns=['scenario','level','model','term','status'])
 specs={n:t for n,_,t,_,_ in scenario_design(config)}
 for (scenario,outcome,level),part in metrics.groupby(['scenario','outcome','level']):
  pp=predictions[(predictions.scenario==scenario)&(predictions.outcome==outcome)&predictions.level.eq(level)];ids=sorted(pp.system_id.unique());d=frame.set_index('system_id').loc[ids];y=d[outcome].to_numpy(float);g=d.region.astype(str);regions=sorted(g.unique());codes=pd.Categorical(g,categories=regions).codes;seed=config['seed']+int(hashlib.sha256(f'{scenario}|{outcome}|{level}'.encode()).hexdigest()[:8],16);rng=np.random.default_rng(seed);draws=rng.multinomial(len(regions),np.full(len(regions),1/len(regions)),size=config['cluster_bootstrap_replicates'])
  for r in part.itertuples(index=False):
   dropped=set(str(r.dropped_constant_terms).split('|'))|set(str(r.dropped_collinear_terms).split('|'));columns=[c for c in specs[scenario][r.model] if c not in dropped];x=d[columns].to_numpy(float);design,_,_=standardize(x);samples=[]
   for draw in draws:
    weights=np.sqrt(draw[codes]);wx=design*weights[:,None];wy=y*weights
    if np.linalg.matrix_rank(wx)<wx.shape[1]:continue
    samples.append(np.linalg.lstsq(wx,wy,rcond=None)[0])
   accepted=len(samples)>=config['minimum_successful_bootstrap_fraction']*len(draws);bounds=np.quantile(np.asarray(samples),[.025,.975],axis=0) if accepted else None
   for j,term in enumerate(['intercept']+columns):rows.append({'scenario':scenario,'outcome':outcome,'level':int(level),'model':r.model,'term':term,'status':'COMPUTED' if accepted else 'INSUFFICIENT_FULL_RANK_CLUSTER_DRAWS','requested_replicates':len(draws),'full_rank_replicates':len(samples),'cluster_regions':len(regions),'ci95_lower':float(bounds[0,j]) if accepted else None,'ci95_upper':float(bounds[1,j]) if accepted else None,'scale':'outcome units per original common-sample predictor SD','paired_region_draws_shared_across_M1_M2_M3':True,'upstream_catchment_uncertainty_propagated':False})
 result=pd.DataFrame(rows)
 if 'scenario' in result:result['comparison_family']=result.scenario.str.split('__').str[0]
 return result

def main():
 global ROOT,INPUT_PATH
 ap=argparse.ArgumentParser();ap.add_argument('--model-output',required=True);ap.add_argument('--output',required=True);ap.add_argument('--inputs',required=True);ap.add_argument('--stage',choices=['preregister','coverage','full'],default='preregister');ap.add_argument('--preregistration-review');a=ap.parse_args();ROOT=resolve(a.output).resolve();INPUT_PATH=resolve(a.inputs).resolve();model=resolve(a.model_output).resolve()
 if ROOT in {HERE.resolve(),HERE.parent.resolve(),model} or 'history' in ROOT.parts:raise ValueError('Output must be a new dedicated cycle06 analysis folder')
 if ROOT.exists() and ((ROOT/'model_metrics.csv').exists() or (ROOT/'regression_started_guard.json').exists()):raise FileExistsError('Analysis output already used; create a versioned output directory')
 allowed={'preregistration.json','effective_analysis_inputs.json','source_coverage_summary.csv','original_axis_population2010_source_quality_counts.csv','source_coverage_receipt.json'}
 if ROOT.exists() and any(p.name not in allowed for p in ROOT.iterdir()):raise FileExistsError('Refusing to write into a nonempty or frozen existing directory')
 config=json.loads(INPUT_PATH.read_text());config['model_output']=label(model);validate_config(config);ROOT.mkdir(parents=True,exist_ok=True)
 if a.stage=='preregister':
  proposed=preregistration(config);p=ROOT/'preregistration.json'
  if p.exists() and json.loads(p.read_text())!=proposed:raise ValueError('Existing preregistration differs; use a new version')
  dump(p,proposed);print(json.dumps({'status':'PREREGISTERED_NO_MODEL_METRICS','path':str(p),'sha256':sha(p)}));return
 if a.stage=='coverage':source_coverage(config);print('SOURCE_COVERAGE_ONLY_NO_REGRESSION_METRICS');return
 review=resolve(a.preregistration_review or config['preregistration_review']);approval=verify_preregistration(config,review)
 dump(ROOT/'effective_analysis_inputs.json',config);dump(ROOT/'regression_started_guard.json',{'status':'STARTED_AFTER_INDEPENDENT_PREREG_ACCEPTANCE','approval':approval});source_coverage(config);frame,hashes=prepare(config);hashes.update(approval)
 modelreceipt=json.loads((model/'run_receipt.json').read_text())
 if modelreceipt['configuration_sha256']!=sha(resolve(config['model_inputs'])):raise ValueError('Selected model was not computed with the preregistered exact model config')
 if modelreceipt['model_code_sha256']!=sha(HERE.parents[1]/'model/run_word_model_cycle06.py'):raise ValueError('Selected model code differs from preregistered code')
 for helper in MODEL_HELPERS:
  if modelreceipt.get('source_sha256',{}).get(label(helper))!=sha(helper):raise ValueError('Selected model helper differs from preregistered helper: '+helper.name)
 results=[[] for _ in range(7)]
 for name,outcome,terms,pure,supported in scenario_design(config):
  for target,values in zip(results,fit_scenario(frame,name,outcome,terms,config,pure,supported)):target.extend(values)
 names=['model_metrics.csv','coefficient_intervals.csv','system_predictions.parquet','spatial_residual_diagnostics.csv','common_sample_membership.parquet','grouped_cv_folds.csv','sample_gates.csv'];dfs=[]
 for name,values in zip(names,results):
  d=pd.DataFrame(values)
  if 'scenario' in d:d['comparison_family']=d.scenario.str.split('__').str[0]
  d['selected_model_output']=config['model_output'];d['grid_basis']=config['grid_basis'];dfs.append(d);d.to_parquet(ROOT/name,index=False) if name.endswith('.parquet') else d.to_csv(ROOT/name,index=False)
 samples=dfs[4];lo=samples[samples.scenario.str.endswith('__experimental_bonitet_lower_bound_sensitivity')].assign(family=lambda z:z.scenario.str.split('__').str[0]).set_index(['family','system_id']).in_common_sample;hi=samples[samples.scenario.str.endswith('__experimental_bonitet_upper_bound_sensitivity')].assign(family=lambda z:z.scenario.str.split('__').str[0]).set_index(['family','system_id']).in_common_sample
 if not lo.sort_index().equals(hi.sort_index()):raise ValueError('Experimental proxy interval endpoints have different samples')
 if len(dfs[2]):
  counts=dfs[2].groupby(['scenario','outcome','level','system_id']).model.nunique()
  assert all(n==(2 if key[0].startswith('A_') else 3) for key,n in counts.items()) and dfs[2].groupby(['scenario','outcome','level','system_id']).cv_fold.nunique().eq(1).all()
 if len(dfs[2]):
  residuals=dfs[2].groupby(['scenario','level','model','region']).agg(n=('residual','size'),mean_residual=('residual','mean'),mean_oof_residual=('group_oof_residual','mean'),rmse_oof=('group_oof_residual',lambda v:np.sqrt(np.mean(v*v)))).reset_index();residuals['comparison_family']=residuals.scenario.str.split('__').str[0];residuals.to_csv(ROOT/'regional_residual_summary.csv',index=False)
 comparisons=[]
 if len(dfs[0]):
  for key,g in dfs[0].groupby(['scenario','outcome','level']):
   g=g.set_index('model');assert g.n.nunique()==1
   for before,after in ([('M1','M2')] if key[0].startswith('A_') else [('M1','M2'),('M2','M3')]):comparisons.append({'comparison_family':key[0].split('__')[0],'scenario':key[0],'outcome':key[1],'level':int(key[2]),'before':before,'after':after,'common_n':int(g.loc[before,'n']),'stable_group_cv_design':bool(g.loc[before,'cv_training_rank_deficient_folds']==0 and g.loc[after,'cv_training_rank_deficient_folds']==0),'before_rank_deficient_folds':int(g.loc[before,'cv_training_rank_deficient_folds']),'after_rank_deficient_folds':int(g.loc[after,'cv_training_rank_deficient_folds']),'selected_model_output':config['model_output'],'grid_basis':config['grid_basis'],'delta_training_r2':float(g.loc[after,'r2']-g.loc[before,'r2']),'delta_group_oof_rmse':float(g.loc[after,'group_oof_rmse']-g.loc[before,'group_oof_rmse']),'delta_group_oof_r2':float(g.loc[after,'group_oof_r2_train_mean_baseline']-g.loc[before,'group_oof_r2_train_mean_baseline'])})
 pd.DataFrame(comparisons).to_csv(ROOT/'same_sample_model_comparisons.csv',index=False);region_bootstrap(frame,dfs[0],dfs[2],config).to_csv(ROOT/'region_cluster_bootstrap_intervals.csv',index=False);figures(dfs[0],dfs[1],dfs[2]);after={p:sha(resolve(p)) for p in hashes};assert hashes==after,'SOURCE_CHANGED_DURING_ANALYSIS'
 receipt={'status':'ACTUALLY_COMPUTED_DESCRIPTIVE_REGRESSIONS' if len(dfs[0]) else 'NO_LEVEL_PASSED_SAMPLE_GATE','computed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'models_computed':len(dfs[0]),'system_rows':len(frame),'selected_model_output':config['model_output'],'source_sha256':hashes,'source_unchanged_verified':True,'analysis_code_sha256':sha(Path(__file__)),'analysis_inputs_sha256':sha(INPUT_PATH),'code_sha256':sha(Path(__file__)),'config_sha256':sha(INPUT_PATH),'effective_config_sha256':sha(ROOT/'effective_analysis_inputs.json'),'source_sha256_before':hashes,'source_sha256_after':after,'grid_basis':config['grid_basis'],'strict_bonitet_available':False,'preregistration_review_sha256':sha(review),'same_sample_and_folds_checked':True,'soil_proxy_semantics':config['soil_proxy_semantics'],'rural_volume_policy':config['rural_volume_policy'],'causal_claim':False,'limitations':['2021 Mi, grain and dated2021 roads define a descriptive retrospective2010–2021 comparison, not independent causal prediction.','GroupedCV refits OLS/scaling, not the full nationwide catchment/rank pipeline.','Regional cluster bootstrap conditions on fixed source values and catchments; routing, linkage and boundary uncertainty are not propagated.','Grain2010 and2008 land sensitivity join via observed2021 primary-source parent; historical boundary equivalence is unproven.','2021 agricultural-census municipal producer farmland and Rosreestr all-landstock regional ratios have different universes and appear only in separate sensitivities.','Unknown rural roles and missing populations are not silently reclassified or zero-imputed.','Coarse GAEZ soil ratings and experimental Atlas intervals do not establish NP Russian bonitet.']};dump(ROOT/'run_receipt.json',receipt);dump(ROOT/'output_manifest.json',{'files':{p.name:sha(p) for p in ROOT.iterdir() if p.is_file() and p.name!='output_manifest.json'}});print(json.dumps({'status':receipt['status'],'models':len(dfs[0])}))
if __name__=='__main__':main()
