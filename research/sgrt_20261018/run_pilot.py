"""Coordinate-based SGRT pilot, not observed commuting regions. Immutable inputs only."""
from pathlib import Path
import json, collections, hashlib, time
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error,adjusted_rand_score
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pyproj import Transformer
ROOT=Path('pilot');ROOT.mkdir(exist_ok=True);R=6371.0088;SEED=20261018
B=Path('in/base');E=Path('in/economic');X=Path('in/extra')
def log(*a):print(*a,flush=True)
def xyz(lat,lon):
 a=np.deg2rad(np.asarray(lat,float));b=np.deg2rad(np.asarray(lon,float));return np.column_stack((np.cos(a)*np.cos(b),np.cos(a)*np.sin(b),np.sin(a)))
def km(ch):return 2*R*np.arcsin(np.clip(np.asarray(ch)/2,0,1))
def assign(pts,cp,mass,radius=75,beta=2,alpha=1):
 tree=cKDTree(cp);kk=min(48,len(cp));d,j=tree.query(pts,k=kk);ds=km(d);gg=mass[j]**alpha/(ds+1)**beta;gg[ds>radius]=0
 rows=np.arange(len(pts));a=gg.argmax(1);s=gg.sum(1);z=j[rows,a];w=np.divide(gg[rows,a],s,out=np.zeros(len(s)),where=s>0);dist=ds[rows,a]
 gg[rows,a]=0;gap=w-np.divide(gg.max(1),s,out=np.zeros(len(s)),where=s>0);z[s==0]=-1;dist[s==0]=np.nan
 for i in np.flatnonzero(ds[:,-1]<radius):
  jj=np.asarray(tree.query_ball_point(pts[i],2*np.sin(radius/(2*R))),int);dd=km(np.linalg.norm(cp[jj]-pts[i],axis=1));g=mass[jj]**alpha/(dd+1)**beta;order=np.argsort(g)[::-1]
  z[i]=jj[order[0]];dist[i]=dd[order[0]];w[i]=g[order[0]]/g.sum();gap[i]=(g[order[0]]-(g[order[1]] if len(jj)>1 else 0))/g.sum()
 return z,dist,w,gap
cols=['entity_uid','source_record_id_2021']
for y in [2002,2010,2021]:cols += [f'{a}_{y}' for a in ['settlement_name','settlement_type','population','latitude','longitude','effective_region_norm','district_raw','population_value_quality','oktmo']]
d=pd.read_csv(B/'ordinary_full3_with_primary_population_sources.csv.gz',usecols=cols,dtype={'oktmo_2021':str},low_memory=False)
d=d.rename(columns={'latitude_2002':'lat','longitude_2002':'lon','settlement_name_2002':'name','settlement_type_2002':'type','effective_region_norm_2002':'region'})
br=pd.read_csv(X/'municipal_bridge.csv.gz',usecols=['source_record_id','root','municipality_role','municipality_oktmo_code8','context_status'],dtype={'municipality_oktmo_code8':str})
br=br[br.municipality_role.eq('upper')];assert not br.source_record_id.duplicated().any()
d=d.merge(br,left_on='source_record_id_2021',right_on='source_record_id',how='left',validate='one_to_one')
h=pd.read_csv(E/'population_1979_1989_long.parquet.csv.gz',usecols=['root','year','population','population_basis','historical_boundary_comparability'])
h=h[h.year.eq(1989)].drop(columns='year').rename(columns={'population':'population_1989','population_basis':'basis_1989','historical_boundary_comparability':'boundary_1989'})
assert not h.root.duplicated().any();d=d.merge(h,on='root',how='left',validate='many_to_one')
d['urban']=d.type.isin(['город','пгт']);d['candidate']=d.urban|d.population_2002.ge(5000);d['reason']=np.where(d.urban,'urban_2002',np.where(d.population_2002.ge(5000),'rural_5000','none'))
for _,g in d[d.district_raw_2002.notna()].groupby(['region','district_raw_2002']):
 if not g.candidate.any():
  ix=g.population_2002.idxmax()
  if d.at[ix,'population_2002']>0:d.at[ix,'candidate']=True;d.at[ix,'reason']='largest_historical_district_provisional'
c=d.loc[d.candidate&d.population_2002.gt(0),['entity_uid','name','type','region','lat','lon','population_2002','reason']].copy();c['obs_index']=c.index;c['federal_context']=False;c=c.reset_index(drop=True)
f=pd.read_csv(E/'accepted_common_federal_territory_axis.csv');f=f[f.census_year.eq(2002)]
for _,r in f.iterrows():c.loc[len(c)]=[r.territory_key,r.territory_name,'territorial_context',r.region_norm,r.latitude,r.longitude,r.territory_population,'federal_context_only',-1,True]
c['center_id']=np.arange(len(c));d['center_index']=-1;real=c.obs_index.ge(0);d.loc[c.loc[real,'obs_index'].astype(int),'center_index']=c.loc[real,'center_id'].values
pts=xyz(d.lat,d.lon);cp=xyz(c.lat,c.lon);mass=c.population_2002.to_numpy();z,dist,w,gap=assign(pts,cp,mass)
anchor=d.center_index.ge(0);z[anchor]=d.loc[anchor,'center_index'];dist[anchor]=0;w[anchor]=1;gap[anchor]=1
d['sgrt']=z;d['distance_center_km']=dist;d['weight']=w;d['gap']=gap;d['rural_surround']=(~d.urban)&(~anchor)
s=c.set_index('center_id').copy();valid=d[d.sgrt.ge(0)];g=valid.groupby('sgrt');s['n_settlements']=g.size();s['n_rural']=valid[valid.rural_surround].groupby('sgrt').size().reindex(s.index,fill_value=0)
for y in [2002,2010,2021]:
 s[f'population_{y}']=g[f'population_{y}'].sum(min_count=1);s[f'core_{y}']=d[anchor].set_index('center_index')[f'population_{y}'];s[f'outside_{y}']=s[f'population_{y}']-s[f'core_{y}'];s[f'rural_{y}']=valid[valid.rural_surround].groupby('sgrt')[f'population_{y}'].sum().reindex(s.index,fill_value=0)
 s[f'share_{y}']=s[f'core_{y}']/s[f'population_{y}']
for a,b in [(2002,2010),(2010,2021),(2002,2021)]:
 for part in ['population','rural','core']:
  u=s[f'{part}_{a}'].where(s[f'{part}_{a}']>0);v=s[f'{part}_{b}'].where(s[f'{part}_{b}']>0);s[f'{part}_annual_{a}_{b}']=100*np.log(v/u)/(b-a)
 s[f'share_change_{a}_{b}']=100*(s[f'share_{b}']-s[f'share_{a}'])
pr=valid[valid.rural_surround & valid.population_value_quality_2010.fillna('').str.contains('confidentiality')]
s['rural_protected2010_share']=pr.groupby('sgrt').population_2010.sum().reindex(s.index,fill_value=0)/s.rural_2010.replace(0,np.nan)
hv=valid[valid.population_1989.notna()];s['historical_n']=hv.groupby('sgrt').size();s['historical_1989']=hv.groupby('sgrt').population_1989.sum();s['historical_matched2002']=hv.groupby('sgrt').population_2002.sum();s['historical_support_share2002']=s.historical_matched2002/s.population_2002
s['historical_boundary_verified']=False
np_tree=cKDTree(pts);pot=[]
for i,r in c.iterrows():
 jj=np.asarray(np_tree.query_ball_point(cp[i],2*np.sin(100/(2*R))),int)
 if r.obs_index>=0:jj=jj[jj!=int(r.obs_index)]
 dd=km(np.linalg.norm(pts[jj]-cp[i],axis=1));pot.append(float(np.sum(d.population_2002.to_numpy()[jj]/(dd+1)**2)))
s['external_potential100']=pot;large=c.population_2002.ge(250000).to_numpy();dl,_=cKDTree(cp[large]).query(cp,k=2);dl=km(dl);s['distance_large_km']=np.where(large,dl[:,1],dl[:,0])
current=np.arange(len(c));edges=[]
for level,(threshold,radius) in enumerate([(50000,100),(250000,150),(1000000,200)],2):
 cand=np.flatnonzero(mass>=threshold);new=current.copy()
 for ch in np.unique(current):
  if ch in cand:continue
  elig=cand[mass[cand]>mass[ch]];dd=km(np.linalg.norm(cp[elig]-cp[ch],axis=1));gg=mass[elig]/(dd+1)**2;gg[dd>radius]=0
  if len(gg) and gg.max()>0:new[current==ch]=elig[gg.argmax()]
 for ch in np.unique(current):edges.append({'level':level,'child':int(ch),'parent':int(new[np.flatnonzero(current==ch)[0]])})
 s[f'parent_L{level}']=new;current=new
pd.DataFrame(edges).to_csv(ROOT/'hierarchy.csv',index=False)
log('STAGE1',len(d),len(c),int((d.sgrt>=0).sum()))
# Agriculture streamed: retain actual totals only, no crop/subtotal double count.
ag_parts=[];ag_rows=0
use=['indicator_code','kategor','mun_level','oktmo','year','indicator_value','indicator_unit','indicator_period','oktmo_history']
for a in pd.read_csv(E/'agriculture.csv.gz',usecols=use,chunksize=200000,dtype={'oktmo':str},low_memory=False):
 ag_rows+=len(a);a.kategor=a.kategor.str.strip();a.mun_level=a.mun_level.str.strip()
 sel=a.year.isin([2008,2009,2010,2021]) & a.kategor.eq('Хозяйства всех категорий') & a.mun_level.eq('Муниципальное образование верхнего уровня') & a.indicator_code.isin(['Y48007010','Y48007011','Y48007012','Y48007013'])
 ag_parts.append(a[sel].copy())
a=pd.concat(ag_parts,ignore_index=True);a=a[~a.oktmo_history.fillna('').str.contains('Объединение|Выделение|территориаль',case=False)].copy();key=['oktmo','year','indicator_code'];conf=a.groupby(key).indicator_value.nunique();bad=set(conf[conf>1].index);a=a[~a[key].apply(tuple,axis=1).isin(bad)].drop_duplicates(key)
aw=a.pivot(index=['oktmo','year'],columns='indicator_code',values='indicator_value').reset_index();aw['crop_share']=aw.Y48007011/aw.Y48007010;err=(aw.Y48007011+aw.Y48007012-aw.Y48007010).abs()/(aw.Y48007010.abs()+1);aw=aw[(aw.Y48007010>0)&aw.crop_share.between(0,1)&err.le(.02)]
cross=valid.groupby(['sgrt','municipality_oktmo_code8']).population_2002.sum().rename('weight').reset_index();cross['share_sgrt']=cross.weight/cross.groupby('sgrt').weight.transform('sum');cross['share_municipality']=cross.weight/cross.groupby('municipality_oktmo_code8').weight.transform('sum');dom=cross.sort_values('weight',ascending=False).drop_duplicates('sgrt').set_index('sgrt');s=s.join(dom[['municipality_oktmo_code8','share_sgrt','share_municipality']]);s['mutual80']=s.share_sgrt.ge(.8)&s.share_municipality.ge(.8)
ag0=aw[aw.year.le(2010)].groupby('oktmo')[['Y48007010','crop_share']].median().rename(columns={'Y48007010':'ag_output','crop_share':'crop_share'});s=s.join(ag0,on='municipality_oktmo_code8');den=d.groupby('municipality_oktmo_code8').population_2002.sum();s['ag_context_intensity']=s.ag_output/s.municipality_oktmo_code8.map(den)
aw.to_csv(ROOT/'agriculture_clean.csv',index=False);cross.to_csv(ROOT/'municipality_overlap.csv',index=False);log('STAGE2',ag_rows,len(aw),int(s.crop_share.notna().sum()),int(s.mutual80.sum()))
# Unambiguous modern territorial-code crosswalk. Historical membership is NOT asserted.
k=d[['oktmo_2021','municipality_oktmo_code8']].dropna().copy();k['code8']=k.oktmo_2021.str.replace(r'\.0$','',regex=True).str.zfill(11).str[:8];nu=k.groupby('code8').municipality_oktmo_code8.nunique();mp=k[k.code8.isin(nu[nu.eq(1)].index)].drop_duplicates('code8').set_index('code8').municipality_oktmo_code8;direct=set(d.municipality_oktmo_code8.dropna())
rf_cov={};rf_stats={}
for year in [2011,2021]:
 agg=[];sectors=[];coverage=collections.Counter()
 uc=['inn','oktmo','outlier','imputed','okved_section','line_2110','lon','lat','geocoding_quality']
 for f in pd.read_csv(E/f'rfsd_{year}_selected.csv.gz',usecols=uc,chunksize=150000,dtype={'inn':str,'oktmo':str,'okved_section':str},low_memory=False):
  coverage['source_rows']+=len(f);coverage['source_geocoded']+=int(f.lat.notna().sum())
  if year==2011:
   code=f.oktmo.str.replace(r'\.0$','',regex=True).str[:8];f['unit']=code.map(mp);directmatch=f.unit.isna()&code.isin(direct);f.loc[directmatch,'unit']=code[directmatch]
  else:
   ok=f.geocoding_quality.isin(['house','street'])&f.lat.between(40,85)&f.lon.between(-180,180);f=f[ok].copy()
   dd,ix=np_tree.query(xyz(f.lat,f.lon),k=1);dd=km(dd);f['unit']=d.sgrt.to_numpy()[ix];f.loc[(dd>10)|f.unit.lt(0),'unit']=np.nan
  coverage['linked_rows']+=int(f.unit.notna().sum());f=f[f.unit.notna()].copy();f['reported']=(f.line_2110.notna()&f.outlier.eq(0)).astype(int);f['rev']=f.line_2110.where(f.reported.eq(1)&f.line_2110.ge(0));f['strict_rev']=f.rev.where(f.imputed.eq(0));f['imputed_n']=f.imputed.eq(1).astype(int)
  agg.append(f.groupby('unit').agg(n_firms=('inn','size'),n_reported=('reported','sum'),revenue=('rev','sum'),strict_revenue=('strict_rev','sum'),max_revenue=('rev','max'),n_imputed=('imputed_n','sum')))
  sectors.append(f.groupby(['unit','okved_section']).rev.sum())
 aa=pd.concat(agg);maxr=aa.groupby(level=0).max_revenue.max();aa=aa.drop(columns='max_revenue').groupby(level=0).sum();aa['max_share']=maxr/aa.revenue.replace(0,np.nan);aa['reporting_share']=aa.n_reported/aa.n_firms
 ss=pd.concat(sectors).groupby(level=[0,1]).sum();denom=ss.groupby(level=0).sum();hhi=(ss/ss.index.get_level_values(0).map(denom))**2;aa['diversity']=1-hhi.groupby(level=0).sum();aa.loc[aa.revenue.le(0),'diversity']=np.nan
 aa.to_csv(ROOT/f'rfsd_{year}_aggregates.csv');rf_stats[year]=aa;rf_cov[year]=dict(coverage);log('STAGE3',year,rf_cov[year])
 if year==2011:s=s.join(aa.add_suffix('_2011'),on='municipality_oktmo_code8')
 else:s=s.join(aa.add_suffix('_2021'))
s['firm_context_density']=s.n_firms_2011/s.municipality_oktmo_code8.map(den)*1000
# Typology based on demographic outcomes only; functional descriptors are independent.
s['demographic_type']=np.select([s.population_annual_2002_2021<-.25,s.population_annual_2002_2021>.25],['Сокращение','Рост'],default='Стабильность');s['spatial_type']=np.select([s.share_change_2002_2021<-2,s.share_change_2002_2021>2],['Деконцентрация','Концентрация'],default='Стабильная доля');s['type_label']=s.demographic_type+' / '+s.spatial_type;s.loc[s.federal_context,'type_label']='Контекстный федеральный центр'
# Statistical pilot, same rows for all model comparisons, region-clustered errors.
for new,col in [('log_core','core_2002'),('log_outside','outside_2002'),('log_distance','distance_large_km'),('log_potential','external_potential100'),('log_ag','ag_context_intensity'),('log_firms','firm_context_density')]:s[new]=np.log1p(s[col].clip(lower=0))
f1=['log_core','log_outside','log_distance','log_potential'];f2=f1+['log_ag','crop_share'];f3=f2+['log_firms','diversity_2011','reporting_share_2011']
model_tables=[];cv=[];morans=[];rng=np.random.default_rng(SEED)
for target in ['rural_annual_2010_2021','rural_annual_2002_2021']:
 sample=s[(~s.federal_context)&s.mutual80&s.n_rural.ge(2)&s.rural_2002.ge(100)].dropna(subset=f3+[target]).copy();sample=sample[np.isfinite(sample[target])]
 sample[['name','region',target]+f3].to_csv(ROOT/f'model_sample_{target}.csv')
 if len(sample)<30:log('STAT_INSUFFICIENT',target,len(sample));continue
 for name,features in [('M1',f1),('M2',f2),('M3',f3)]:
  mat=sample[features];std=(mat-mat.mean())/mat.std(ddof=0);dd=pd.get_dummies(sample.region,drop_first=True,dtype=float);design=sm.add_constant(pd.concat([std,dd],axis=1)).astype(float);fit=sm.OLS(sample[target],design).fit(cov_type='cluster',cov_kwds={'groups':sample.region})
  ci=fit.conf_int();pv=fit.pvalues.loc[features];qv=multipletests(pv,method='fdr_bh')[1]
  for i,feat in enumerate(features):model_tables.append({'target':target,'model':name,'n':len(sample),'regions':sample.region.nunique(),'feature':feat,'coef_per_sd':fit.params[feat],'ci_low':ci.loc[feat,0],'ci_high':ci.loc[feat,1],'p':pv[feat],'q_bh':qv[i],'r2_in_sample':fit.rsquared})
  for fold,(train,test) in enumerate(GroupKFold(n_splits=5).split(mat,sample[target],sample.region)):
   est=make_pipeline(StandardScaler(),Ridge(alpha=10));est.fit(mat.iloc[train],sample[target].iloc[train]);pred=est.predict(mat.iloc[test]);cv.append({'target':target,'model':name,'fold':fold,'n_test':len(test),'rmse':float(np.sqrt(mean_squared_error(sample[target].iloc[test],pred)))})
  coords=xyz(sample.lat,sample.lon);_,nb=cKDTree(coords).query(coords,k=min(9,len(sample)));nb=nb[:,1:];r=np.asarray(fit.resid);r-=r.mean()
  def moran(v):return float(np.sum(v*np.mean(v[nb],axis=1))/np.sum(v*v))
  observed=moran(r);perms=np.array([moran(rng.permutation(r)) for _ in range(199)]);expected=-1/(len(r)-1);pval=(1+np.sum(np.abs(perms-expected)>=abs(observed-expected)))/200
  morans.append({'target':target,'model':name,'I':observed,'p_two_sided_199_permutations':float(pval),'neighbors':nb.shape[1]})
pd.DataFrame(model_tables).to_csv(ROOT/'model_coefficients.csv',index=False);pd.DataFrame(cv).to_csv(ROOT/'spatial_cv.csv',index=False);pd.DataFrame(morans).to_csv(ROOT/'residual_moran.csv',index=False)
# Prespecified sensitivity; zero-growth quality caveat remains independent of this exercise.
sensitivity=[];switch=np.zeros(len(d));pop=d.population_2002.to_numpy()
for alpha in [.5,1]:
 for beta in [1,1.5,2,3]:
  for radius in [50,75,100]:
   zz,_,_,_=assign(pts,cp,mass,radius,beta,alpha);zz[anchor]=d.loc[anchor,'center_index'];changed=zz!=z;switch+=changed;sensitivity.append({'alpha':alpha,'beta':beta,'radius':radius,'switched_rows':int(changed.sum()),'switched_population_share':float(pop[changed].sum()/pop.sum()),'adjusted_rand':float(adjusted_rand_score(z,zz))})
d['assignment_stability']=1-switch/len(sensitivity);pd.DataFrame(sensitivity).to_csv(ROOT/'sensitivity.csv',index=False)
s['assignment_stability']=d[d.sgrt.ge(0)].groupby('sgrt').apply(lambda g:np.average(g.assignment_stability,weights=g.population_2002) if g.population_2002.sum()>0 else np.nan,include_groups=False)
s.to_csv(ROOT/'sgrt_results.csv');d[['entity_uid','root','name','region','lat','lon','sgrt','distance_center_km','weight','gap','assignment_stability','population_1989','population_2002','population_2010','population_2021','municipality_oktmo_code8']].to_csv(ROOT/'settlement_assignments.csv.gz',index=False)
# Maps preserve aspect; Natural Earth is background, not proof of historical jurisdiction.
world=json.loads((X/'world_countries.geojson').read_text());tr=Transformer.from_crs('EPSG:4326','+proj=aea +lat_1=50 +lat_2=70 +lat_0=60 +lon_0=100 +datum=WGS84 +units=m',always_xy=True)
polys=[]
for ft in world['features']:
 prop=ft['properties'];name=prop.get('ADMIN',prop.get('admin',''))
 if name=='Russia':
  geom=ft['geometry'];p=geom['coordinates'] if geom['type']=='MultiPolygon' else [geom['coordinates']]
  for poly in p:
   ring=np.asarray(poly[0]);xx,yy=tr.transform(ring[:,0],ring[:,1]);polys.append((np.asarray(xx)/1000,np.asarray(yy)/1000))
xx,yy=tr.transform(s.lon.to_numpy(),s.lat.to_numpy());xx=np.asarray(xx)/1000;yy=np.asarray(yy)/1000
for col,title in [('population_annual_2002_2021','Динамика населения модельных СГРТ, 2002–2021'),('crop_share','Доля растениеводства: муниципальный контекст 2008–2010'),('diversity_2021','Отраслевая диверсификация зарегистрированных организаций, 2021'),('assignment_stability','Устойчивость принадлежности при 24 вариантах модели')]:
 fig,ax=plt.subplots(figsize=(16,10))
 for px,py in polys:ax.plot(px,py,linewidth=.35)
 vals=s[col].to_numpy(float);ok=np.isfinite(vals)&(~s.federal_context.to_numpy(bool))
 vmin,vmax=(np.nanquantile(vals[ok],[.02,.98]) if col=='population_annual_2002_2021' else (None,None))
 sc=ax.scatter(xx[ok],yy[ok],c=vals[ok],s=8,vmin=vmin,vmax=vmax,rasterized=True);fig.colorbar(sc,ax=ax,shrink=.65,label=col)
 ax.set_aspect('equal');ax.set_title(title,fontsize=16,pad=16);ax.set_xlabel('км, равновеликая проекция');ax.set_ylabel('км');ax.text(.01,.01,'Потенциальное районирование; не наблюдаемые поездки. Белые зоны не означают нулевое население.',transform=ax.transAxes,fontsize=9)
 fig.tight_layout();fig.savefig(ROOT/(col+'.png'),dpi=300);fig.savefig(ROOT/(col+'.pdf'));fig.savefig(ROOT/(col+'.svg'));plt.close(fig)
# Audit is a separate executable check of persisted tables, not an independent LLM review.
test=pd.read_csv(ROOT/'settlement_assignments.csv.gz');assert not test.entity_uid.duplicated().any();summ=test[test.sgrt.ge(0)].groupby('sgrt').population_2002.sum();assert np.allclose(summ.sort_index(),s.population_2002.reindex(summ.index),equal_nan=True)
assert (s.federal_context.sum()==2);assert np.all((d.sgrt>=-1)&(d.sgrt<len(c)));assert np.all(d.assignment_stability.between(0,1));assert np.isclose(s.population_2002.sum(),d.loc[d.sgrt.ge(0),'population_2002'].sum())
receipt={'status':'computed_pilot_not_functionally_validated','ordinary_rows':len(d),'centers':len(c),'provisional_centers':int(c.reason.str.contains('provisional').sum()),'federal_context_centers':2,'assigned_rows':int((z>=0).sum()),'unassigned_rows':int((z<0).sum()),'assigned_population_share2002':float(pop[z>=0].sum()/pop.sum()),'ordinary_population':{str(y):float(d[f'population_{y}'].sum()) for y in [2002,2010,2021]},'historical_linked_rows':int(d.population_1989.notna().sum()),'agricultural_raw_rows':ag_rows,'agricultural_clean_rows':len(aw),'ag_context_sgrt':int(s.crop_share.notna().sum()),'mutual80_sgrt':int(s.mutual80.sum()),'rfsd':rf_cov,'statistical_rows':len(model_tables),'sensitivity_variants':len(sensitivity),'mass_conservation_test':True,'independent_geographic_validation':False,'independent_agent_review':False,'limitations':['ordinary fixed-place subset, not full national census','federal aggregate anchors context-only, no comparable federal totals','1989 heterogeneous count types and unknown boundaries','protected 2010 values remain uncertain','2011 firms located by inferred modern municipality codes, no point coordinates','2021 firm addresses are registration, not production','primary distance/candidate calibration not externally validated','spatial CV holds out regions but has no explicit boundary buffer','stronger source-restricted statistical sensitivity and independently checked rural centers remain required']}
(ROOT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));log('FINAL_RECEIPT',json.dumps(receipt,ensure_ascii=False))
manifest=[{'file':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in ROOT.iterdir() if p.is_file()];(ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2))
