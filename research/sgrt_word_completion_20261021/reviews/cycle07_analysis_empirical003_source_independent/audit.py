from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd
B=Path('/workspace/russian-settlements-research/research/sgrt_word_completion_20261021');R=B.parents[1];O=B/'reviews/cycle07_analysis_empirical003_source_independent';S=B/'analysis/cycle07_newsource_empirical_aggregates_v1';C=B/'analysis/cycle07_tools/newsource_empirical_input_contract_v1.json';c=json.loads(C.read_text());rec=json.loads((S/'receipt.json').read_text());checks=[]
def path(x):
 p=Path(x);return p if p.is_absolute()else R/p if p.parts[0]=='research'else B/p
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ck(k,v,d=None):checks.append({'check':k,'passed':bool(v),'detail':d})
watch={path(p):h for p,h in rec['source_inputs_sha256'].items()};watch.update({S/p:h for p,h in rec['outputs_sha256'].items()})
for p,h in watch.items():ck('source_actual_SHA_'+str(p),sha(p)==h)
v=c['views'][3];f=pd.read_parquet(S/'cap_120_analysis_features.parquet').set_index('unit_id');idx=f.index;N=len(idx);u=pd.read_parquet(path(v['raw_units']));u=u[u.partition_role.eq('candidate_knee_or_fallback')].set_index('unit_id').loc[idx];m=pd.read_parquet(path(v['raw_memberships']));m=m[m.partition_role.eq('candidate_knee_or_fallback')];ck('complete_exact_actual_unitIDs',f.index.is_unique and set(f.index)==set(u.index) and N==23279);ck('all173858memberIDs_once',len(m)==173858 and m.id.is_unique)
cols=['id','_population_axis_row','accepted_statistical_rural_role2021'];n=pd.read_parquet(path(c['nodes']),columns=cols).set_index('id');p=pd.read_parquet(path(c['population_view']),columns=['id','population_2010','population_2021','population_value_quality_2010','population_value_quality_2021']).set_index('id');n=n.join(p,validate='one_to_one');a=m.join(n,on='id',validate='one_to_one');a['core']=a.unit_id.map(u.core_id);ix=pd.Categorical(a.unit_id,categories=idx).codes;assert (ix>=0).all()
add=a._population_axis_row.eq(True).fillna(False).to_numpy(bool);external=a.id.ne(a.core).to_numpy(bool);rural=add&external&a.accepted_statistical_rural_role2021.eq(True).fillna(False).to_numpy(bool);unknown=add&external&a.accepted_statistical_rural_role2021.isna().to_numpy(bool);focal=~external
count=lambda z:np.bincount(ix,weights=np.asarray(z,dtype=float),minlength=N)
def sums(x,mask):
 x=np.asarray(x,float);ok=np.asarray(mask,bool)&np.isfinite(x);v=np.bincount(ix,weights=np.where(ok,x,0),minlength=N);v[count(ok)==0]=np.nan;return v
def compare(k,expected):
 got=f[k].to_numpy();e=np.asarray(expected);ok=np.isclose(got.astype(float),e.astype(float),atol=1e-8,rtol=1e-11,equal_nan=True)if e.dtype.kind in 'ifbu'else ((pd.Series(got).fillna('__NA').to_numpy())==(pd.Series(e).fillna('__NA').to_numpy()));ck('ALL23279_'+k,np.all(ok),{'mismatches':int((~ok).sum())})
for k,z in [('focal_membership_count',focal),('rural_unknown_role_external_n',unknown),('rural_members_n',rural),('additive_members_n',add)]:compare(k,count(z))
quality=json.loads(path(c['source_regression_design']).read_text());P={};complete={};metro=a.id.isin(['ctx:RU-FED-MOW','ctx:RU-FED-SPB']).to_numpy(bool)
for year in (2010,2021):
 value=pd.to_numeric(a[f'population_{year}'],errors='coerce').to_numpy(float);value[~np.isfinite(value)|(value<0)]=np.nan;P[year]=value;ownknown=count(focal&np.isfinite(value))==1;compare(f'analysis_focal_own_population_complete_{year}',ownknown);unknownctx=count(metro&~np.isfinite(value));compare(f'unknown_metropolitan_member_count_{year}',unknownctx)
 for scope,mask in [('system',add),('rural_external',rural)]:
  ns=count(mask);known=count(mask&np.isfinite(value));total=sums(value,mask);total=np.where(ns==0,0,total)if scope=='rural_external'else total;ok=(known==ns)&((ns>0)if scope=='system'else(count(unknown)==0));complete[scope,year]=ok;compare(f'{scope}_population_known_sum_{year}',total);compare(f'{scope}_population_complete_{year}',ok)
  q=a[f'population_value_quality_{year}'];primary=q.isin(quality[f'primary_population_quality_{year}']).to_numpy(bool);supported=q.isin(quality.get('primary_supported_population_quality_2010',quality['primary_population_quality_2010'])if year==2010 else quality['primary_population_quality_2021']).to_numpy(bool)
  compare(f'analysis_{scope}{year}_primary_source_only',(count(mask&np.isfinite(value)&primary)==ns)&(ns>0));compare(f'analysis_{scope}{year}_primary_supported_only',(count(mask&np.isfinite(value)&supported)==ns)&(ns>0))
  if year==2010:
   sec=q.eq(quality['secondary_population_quality_2010']).to_numpy(bool);num=np.nan_to_num(sums(value,mask&sec),nan=0);compare(f'analysis_{scope}2010_secondary_share_of_known_population',np.divide(num,total,out=np.full(N,np.nan),where=total>0))
 whole=complete['system',year]&ownknown&(unknownctx==0);complete['whole',year]=whole;compare(f'analysis_whole_population_complete_{year}',whole)
norm=pd.read_parquet(path(v['normalized_units']),columns=['unit_id','center_id','system_population_known_sum_2010','system_population_known_sum_2021']).set_index('unit_id').loc[idx]
for obj,scope,gate in [('system','system',complete['whole',2010]&complete['whole',2021]),('rural','rural_external',complete['rural_external',2010]&complete['rural_external',2021])]:
 x=f[f'{scope}_population_known_sum_2010'].to_numpy(float);y=f[f'{scope}_population_known_sum_2021'].to_numpy(float);valid=gate&(x>0)&(y>=0);ratio=np.divide(y,x,out=np.full(N,np.nan),where=x>0);compare(f'outcome_{obj}_change_pct',np.where(valid,100*(ratio-1),np.nan))
 if obj=='system':compare('outcome_system_log_change_100',np.where(valid&(y>0),100*np.log(np.where(ratio>0,ratio,np.nan)),np.nan))
features={}
for alias,src in c['context_features'].items():
 t=pd.read_parquet(path(src['path']),columns=['id']+src['fields']).set_index('id');values=t[src['fields']].apply(pd.to_numeric,errors='coerce');s=values.mean(axis=1).where(values.notna().all(axis=1));features[alias]=a.id.map(s).to_numpy(float)
pairs=pd.read_parquet(path(c['direct_focal_pairs']['path']));pairs=pairs[pairs.candidate_cap.eq(120)].rename(columns={'core_id':'core','direct_network_minutes':'minutes'});ck('directpair_member_keys_unique',not pairs.duplicated(['unit_id','id']).any());joined=a[['unit_id','id','core']].merge(pairs[['unit_id','id','core','minutes']],on=['unit_id','id'],how='left',validate='one_to_one',suffixes=('','_pair'));ck('all_observed_directpair_focals_exact',joined.loc[joined.minutes.notna(),'core'].eq(joined.loc[joined.minutes.notna(),'core_pair']).all());features['rural_own_center_minutes']=joined.minutes.to_numpy(float)
w=P[2010];den=sums(w,rural);nr=count(rural);knownweights=count(rural&np.isfinite(w));goodweights=(knownweights==nr)&(count(unknown)==0)&(count(focal)==1)
for name,values in features.items():
 valid=rural&np.isfinite(w)&np.isfinite(values);observed=sums(w,valid);num=sums(w*values,valid);cov=np.divide(observed,den,out=np.full(N,np.nan),where=den>0);mean=np.divide(num,observed,out=np.full(N,np.nan),where=observed>0);mean[~(goodweights&(cov>=.8))]=np.nan;compare(name,mean)
 for suffix,values0 in [('population_coverage2010',cov),('known_population2010_denominator',den),('observed_feature_population2010_numerator',observed),('rural_members',nr),('known_weight_members',knownweights),('feature_observed_members',count(rural&np.isfinite(values))),('all_rural_weights_known',knownweights==nr),('unknown_role_external_members',count(unknown)),('affirmative_complete_role_and_weights',goodweights)]:compare(name+'_'+suffix,values0)
mass=pd.read_parquet(path(c['own_mass']),columns=['id','own_positive_mass']).set_index('id').own_positive_mass;compare('own_positive_mass',u.core_id.map(mass).to_numpy(float));inv=[]
for row in u.itertuples():
 ids=json.loads(row.original_provider_seed_ids);z=mass.reindex(ids).to_numpy(float);valid=len(z)>0 and np.isfinite(z).all()and(z>0).all();fm=mass.get(row.core_id,np.nan);fok=np.isfinite(fm)and fm>0;inv.append([len(z),int((~np.isfinite(z)|(z<=0)).sum()),bool(valid and fok),int((z>=.5*fm).sum())if valid and fok else np.nan,float(np.sum((z/z.sum())**2))if valid else np.nan])
for k,val in zip(['observed_provider_seed_count','observed_provider_missing_or_nonpositive_mass_count','observed_provider_inventory_complete','comparable_provider_count','observed_provider_mass_hhi'],np.asarray(inv).T):compare(k,val)
for target,source,op in [('log_own_mass2021','own_positive_mass','log'),('log_baseline_system_population2010','system_population_known_sum_2010','log'),('log_rural_own_center_minutes','rural_own_center_minutes','log1p'),('log_rural_large_city_minutes','rural_large_city_minutes','log1p'),('log_agro_grain_yield2010','agro_grain_yield2010','log1p'),('log_agro_grain_yield2021','agro_grain_yield2021','log1p'),('log_comparable_provider_count','comparable_provider_count','log1p')]:
 z=f[source].to_numpy(float);e=np.log(np.where(z>0,z,np.nan))if op=='log'else np.log1p(np.where(z>=0,z,np.nan));compare(target,e)
compare('mass_x_suburban',f.log_own_mass2021*f.rural_suburban_share)
for p,h in watch.items():ck('immutable_actual_SHA_'+str(p),sha(p)==h)
out={'status':'ACCEPTED'if all(x['passed']for x in checks)else'REJECTED','all_checks_passed':all(x['passed']for x in checks),'n_checks':len(checks),'n_failed':sum(not x['passed']for x in checks),'checks':checks,'accepted_source_receipt_sha256':sha(S/'receipt.json'),'accepted_analysis_features_sha256':sha(S/'all_caps_analysis_features.parquet'),'accepted_source_contract_sha256':sha(C),'scope':'Independent NEWEMPIRICAL003 all23279 source aggregates: source SHA, exact onefocal/rural/additive frames, source-quality completeness, anyunknown-context whole/outcomes, all2010weighted numeric exposures/coverage/unknownroles/ownfocaldirectpairs, allprovider fixed-Mi HHI/counts and derived predictors. No producer adapter imported. This is source computation admission, not actual regressions/causality/empirical-level promotion.'};(O/'audit.json').write_text(json.dumps(out,indent=2)+'\n');print(out['status'],out['n_checks'],out['n_failed']);print([x for x in checks if not x['passed']])
