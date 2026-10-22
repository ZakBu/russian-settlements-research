#!/usr/bin/env python3
"""National fixed-axis functional gravity experiment; no outcome-trained masses."""
from pathlib import Path
import argparse, hashlib, json, time
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.spatial import cKDTree

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[1]
OLD=REPO/'research/sgrt_national_integration_20261019'
MASTER=OLD/'core/feature_master.parquet'
PROFILE=OLD/'screening/support_point_profiles.parquet'
EXPECTED='8c98d5a113eec4c3bf131232b1d7e5c6362dc3a50ee484e964420de58c377f85'
GROUPS=['trade_access','food_service','education','healthcare','social_care','repair','personal','veterinary','pharmacy','banking','postal_service']
LEGAL={'trade_access':'retail47','food_service':'food56','education':'education85','healthcare':'health86','social_care':'social8788','repair':'repair95','personal':'personal96'}
PHYSICAL={'trade_access':['retail_store','market'],'food_service':['food_service'],'education':['school','preschool','other_education'],'healthcare':['hospital','healthcare'],'veterinary':['veterinary'],'pharmacy':['pharmacy'],'banking':['bank','atm'],'postal_service':['post_office','postal_collection_point']}

def digest(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def xyz(lat,lon):
 a,b=np.radians(lat),np.radians(lon)
 return np.column_stack([np.cos(a)*np.cos(b),np.cos(a)*np.sin(b),np.sin(a)])
def km(chord):return 6371.0088*2*np.arcsin(np.clip(chord/2,0,1))
def counts(d,mode='baseline',year=2025,physical_only=False):
 out={}
 for g in GROUPS:
  legal=np.zeros(len(d))
  if g in LEGAL and not physical_only:legal=d[f'econ_native_{year}_{LEGAL[g]}_legal_entities'].to_numpy(float)
  physical=np.zeros(len(d))
  for cat in PHYSICAL.get(g,[]):
   x=d[f'places_baseline_{cat}_count'].to_numpy(float)
   if mode=='conditional':x=x+d[f'places_conditional_{cat}_count'].to_numpy(float)
   physical+=x
  # Different subcategories are source records, not certified distinct facilities.
  if g=='trade_access':physical=np.maximum(physical,d['wb_strict_focus_types_locations'].to_numpy(float))
  out[g]=np.maximum(legal,physical)
 return pd.DataFrame(out,index=d.index).fillna(0)
def mass(c):
 z=np.log1p(c.to_numpy(float));caps=[]
 for j in range(z.shape[1]):
  pos=z[:,j][z[:,j]>0];cap=float(np.quantile(pos,.99)) if len(pos) else 0
  z[:,j]=np.minimum(z[:,j],cap);caps.append(cap)
 return z.sum(axis=1),caps

def assign(points,centers,masses,radius=75,scale=15,kernel='exp',k=64,pin=True):
 # Exact all-candidates-in-radius search, chunked to bound memory. No top-k approximation.
 n=len(points);idx=np.asarray(centers);tree=cKDTree(points[idx])
 result=dict(center=np.full(n,-1,int),second=np.full(n,-1,int),distance=np.full(n,np.nan),second_ratio=np.zeros(n),top_weight=np.zeros(n),entropy=np.zeros(n),pinned=np.zeros(n,bool),truncated=np.zeros(n,bool))
 chord_radius=2*np.sin(radius/(2*6371.0088))
 for start in range(0,n,4096):
  end=min(start+4096,n);neighbors=tree.query_ball_point(points[start:end],chord_radius,workers=1)
  lengths=np.array([len(a) for a in neighbors]);rr=np.repeat(np.arange(end-start),lengths)
  if not len(rr):continue
  cc=np.concatenate([np.asarray(a,int) for a in neighbors if len(a)])
  dd=km(np.linalg.norm(points[start:end][rr]-points[idx[cc]],axis=1))
  ww=masses[idx[cc]].copy()
  if kernel=='exp':ww*=np.exp(-dd/scale)
  elif kernel=='power':ww/=np.square(dd+1)
  elif kernel=='nearest':ww=1/(dd+1)
  valid=ww>0;rr,cc,dd,ww=rr[valid],cc[valid],dd[valid],ww[valid]
  if not len(rr):continue
  order=np.lexsort((idx[cc],-ww,rr));r,c,dist,w=rr[order],cc[order],dd[order],ww[order]
  first=np.r_[0,np.flatnonzero(np.diff(r))+1];row=r[first];tot=np.bincount(rr,weights=ww,minlength=end-start)
  globalrow=start+row
  result['center'][globalrow]=idx[c[first]];result['distance'][globalrow]=dist[first];result['top_weight'][globalrow]=w[first]/tot[row]
  second=first+1;has=(second<len(r));has[has]&=r[second[has]]==row[has]
  result['second'][globalrow[has]]=idx[c[second[has]]];result['second_ratio'][globalrow[has]]=w[second[has]]/w[first[has]]
  prob=ww/tot[rr];entropy=np.bincount(rr,weights=-prob*np.log(np.maximum(prob,1e-300)),minlength=end-start)
  result['entropy'][start:end]=entropy
 result['unconstrained_center']=result['center'].copy()
 if pin:
  result['center'][idx]=idx;result['distance'][idx]=0;result['pinned'][idx]=True
 return result

def hierarchy(points,candidates,masses,base):
 active=np.array(sorted(set(base[base>=0])));current=base.copy();rows=[];levels={1:current.copy()}
 caps=[float(np.quantile(masses[candidates],q)) for q in [.5,.9,.98]]
 for level,(threshold,radius) in enumerate(zip(caps,[100,200,400]),2):
  eligible=active[masses[active]>=threshold]
  mapping={int(x):int(x) for x in active}
  if len(eligible):
   tree=cKDTree(points[eligible])
   neighbors=tree.query_ball_point(points[active],2*np.sin(radius/(2*6371.0088)),workers=1)
   for i,u in enumerate(active):
    if masses[u]>=threshold:continue
    other=np.array(neighbors[i],int)
    if not len(other):continue
    provider=eligible[other];dist=km(np.linalg.norm(points[u]-points[provider],axis=1))
    ok=masses[provider]>masses[u]
    if not ok.any():continue
    provider,dist=provider[ok],dist[ok];score=masses[provider]*np.exp(-dist/(radius/3))
    order=np.lexsort((provider,-score));mapping[int(u)]=int(provider[order[0]])
  for child,parent in mapping.items():
   dd=float(km(np.linalg.norm(points[child]-points[parent])))
   rows.append(dict(level=level,child_index=child,parent_index=parent,self_retained=child==parent,distance_km=dd,mass_threshold=threshold,search_radius_km=radius,child_mass=float(masses[child]),parent_mass=float(masses[parent])))
  current=np.array([mapping.get(int(x),-1) if x>=0 else -1 for x in current])
  levels[level]=current.copy();active=np.array(sorted(set(current[current>=0])))
 return levels,pd.DataFrame(rows)

def typology(total0,total1,center0,center1,years=19,rate_eps=.0025,share_eps=.02):
 rate=np.where((total0>0)&(total1>0),np.expm1(np.log(np.maximum(total1,1)/np.maximum(total0,1))/years),np.nan)
 share=np.divide(center1,total1,out=np.full_like(np.asarray(total1,float),np.nan),where=total1>0)-np.divide(center0,total0,out=np.full_like(np.asarray(total0,float),np.nan),where=total0>0)
 trend=np.where(~np.isfinite(rate),'zero_endpoint_or_unknown',np.where(rate>rate_eps,'growth',np.where(rate<-rate_eps,'decline','stable')))
 concentration=np.where(~np.isfinite(share),'unknown',np.where(share>share_eps,'concentration',np.where(share<-share_eps,'deconcentration','stable_share')))
 return rate,share,np.char.add(np.char.add(trend,':'),concentration)

def aggregate(d,levels,centermass,output):
 tables=[];balances=[]
 rural=~d.type.fillna('').isin(['город','пгт','посёлок городского типа','рабочий посёлок'])
 ordinary=d.axis_kind.eq('ordinary').to_numpy()
 for level,assignment in levels.items():
  mask=(assignment>=0)&ordinary;indexes=np.flatnonzero(mask);grp=assignment[mask]
  centers=np.array(sorted(set(grp)));t=pd.DataFrame({'center_index':centers}).set_index('center_index')
  t['center_id']=d.iloc[centers].id.values;t['name']=d.iloc[centers].name.values;t['region']=d.iloc[centers].region.values
  t['center_axis_kind']=d.iloc[centers].axis_kind.values;t['lat']=d.iloc[centers].lat.values;t['lon']=d.iloc[centers].lon.values;t['own_functional_mass']=centermass[centers]
  n=pd.Series(grp).value_counts();t['n_ordinary_settlements']=n
  t['n_rural_external_settlements']=pd.Series(assignment[mask & rural.to_numpy() & (np.arange(len(d))!=assignment)]).value_counts().reindex(t.index,fill_value=0)
  for y in [2002,2010,2021]:
   pop=d[f'population_{y}'].to_numpy(float)
   sums=pd.Series(pop[mask]).groupby(grp).sum(min_count=1);missing=pd.Series(~np.isfinite(pop[mask])).groupby(grp).sum()
   t[f'system_population_{y}']=sums;t[f'n_missing_population_{y}']=missing
   cp=pop[centers].copy();cp[~ordinary[centers]]=0
   t[f'center_population_{y}']=cp
   t[f'external_population_{y}']=t[f'system_population_{y}']-cp
   rm=mask & rural.to_numpy() & (np.arange(len(d))!=assignment)
   t[f'rural_external_population_{y}']=pd.Series(pop[rm]).groupby(assignment[rm]).sum(min_count=1).reindex(t.index,fill_value=0)
   t[f'n_observed_zeros_{y}']=pd.Series(pop[mask]==0).groupby(grp).sum().reindex(t.index,fill_value=0)
   balances.append(dict(level=level,year=y,total_ordinary=float(np.nansum(pop[ordinary])),assigned=float(t[f'system_population_{y}'].sum()),unassigned=float(np.nansum(pop[ordinary & ~mask])),n_assigned=int(mask.sum()),n_unassigned=int((ordinary & ~mask).sum()),sum_conserved=bool(np.isclose(np.nansum(pop[ordinary]),t[f'system_population_{y}'].sum()+np.nansum(pop[ordinary&~mask]),rtol=0,atol=.01))))
  rates,shares,types=typology(t.system_population_2002.values,t.system_population_2021.values,t.center_population_2002.values,t.center_population_2021.values)
  t['annual_change_2002_2021']=rates;t['center_share_change_2002_2021']=shares;t['demographic_type']=types
  t.loc[t.center_axis_kind.ne('ordinary'),'demographic_type']='federal_context_center_not_comparable'
  t['has_rural_periphery']=t.n_rural_external_settlements.gt(0)
  # Always carry a population-quality diagnostic for the intermediate census.
  protected=d.population_value_quality_2010.fillna('').astype(str).str.contains('protected|confidential',case=False).to_numpy()
  v=d.population_2010.to_numpy(float)
  prot=pd.Series(v[mask & protected]).groupby(assignment[mask & protected]).sum()
  t['protected_population_2010']=prot.reindex(t.index,fill_value=0)
  t['protected_share_2010']=t.protected_population_2010/t.system_population_2010.replace(0,np.nan)
  known=mask & d.population_1989.notna().to_numpy()
  t['n_known_1989']=pd.Series(assignment[known]).value_counts().reindex(t.index,fill_value=0)
  for y in [1989,2002]:t[f'paired_known1989_population_{y}']=pd.Series(d[f'population_{y}'].to_numpy(float)[known]).groupby(assignment[known]).sum().reindex(t.index,fill_value=0)
  t['paired_known1989_coverage_of2002']=t.paired_known1989_population_2002/t.system_population_2002.replace(0,np.nan)
  t['level']=level;tables.append(t.reset_index())
 allrows=pd.concat(tables,ignore_index=True)
 allrows.to_parquet(output/'systems_all_levels.parquet',index=False);allrows.to_csv(output/'systems_all_levels.csv.gz',index=False)
 pd.DataFrame(balances).to_csv(output/'population_balances.csv',index=False)
 return allrows,balances

def municipal_context(d,assignment,systems,out):
 ordinary=d.axis_kind.eq('ordinary').to_numpy();mask=ordinary&(assignment>=0)
 x=d.loc[mask,['id','municipality_oktmo8_2021','population_2002']].copy();x['center_index']=assignment[mask]
 pairs=x.groupby(['center_index','municipality_oktmo8_2021'],dropna=False).population_2002.sum().rename('overlap_population2002').reset_index()
 pairs['share_of_system']=pairs.overlap_population2002/pairs.groupby('center_index').overlap_population2002.transform('sum').replace(0,np.nan)
 # Whole-municipality denominator includes unassigned ordinary settlements too.
 mun=d.loc[ordinary].groupby('municipality_oktmo8_2021').population_2002.sum()
 pairs['share_of_municipality']=pairs.overlap_population2002/pairs.municipality_oktmo8_2021.map(mun).replace(0,np.nan)
 pairs['mutual80']=pairs.share_of_system.ge(.8)&pairs.share_of_municipality.ge(.8)
 pairs.to_parquet(out/'municipal_overlap.parquet',index=False)
 dominant=pairs.sort_values(['center_index','overlap_population2002','municipality_oktmo8_2021'],ascending=[True,False,True]).drop_duplicates('center_index')
 cols=['agri_grain_share_2021','agri_fodder_share_2021','agri_total_ha_2021','agri_production_nominal_thousand_rub_2010','agri_total_ha_2010_native_code','agri_profile2021_complete','agri_profile2021_inconsistent']
 # Check repeated context, never add hectares replicated on settlements.
 context=d.loc[ordinary,['municipality_oktmo8_2021']+cols].groupby('municipality_oktmo8_2021',dropna=False).first().reset_index()
 dominant=dominant.merge(context,on='municipality_oktmo8_2021',how='left',validate='many_to_one')
 dominant['municipal_values_are_context_not_system_production']=True
 dominant.to_csv(out/'municipal_dominant_context.csv',index=False)
 return dominant

def gradients(d,assignment,out):
 ix=np.arange(len(d));mask=(assignment>=0)&(assignment!=ix)&d.axis_kind.eq('ordinary').to_numpy()&~d.type.isin(['город','пгт']).to_numpy()
 x=d.loc[mask,['id','population_2002','population_2021']].copy();x['center_index']=assignment[mask]
 pts=xyz(d.lat.values,d.lon.values)
 x['distance_km']=km(np.linalg.norm(pts[mask]-pts[assignment[mask]],axis=1))
 positive=x.population_2002.gt(0)&x.population_2021.gt(0)
 x['annual_log_change']=np.nan;x.loc[positive,'annual_log_change']=np.log(x.loc[positive,'population_2021']/x.loc[positive,'population_2002'])/19
 x['zero_endpoint']=~positive
 rows=[]
 for center,g in x.groupby('center_index'):
  v=g.dropna(subset=['annual_log_change'])
  if len(v)>=5 and v.distance_km.max()-v.distance_km.min()>1:
   slope=np.polyfit(v.distance_km,v.annual_log_change,1)[0]
   rows.append(dict(center_index=center,n_positive=len(v),n_zero_endpoints=int(g.zero_endpoint.sum()),slope_annual_log_change_per_km=float(slope),distance_measure='great_circle_not_travel_time'))
 x.to_parquet(out/'rural_gradient_points.parquet',index=False);pd.DataFrame(rows).to_csv(out/'rural_gradients.csv',index=False)

def run(output):
 start=time.monotonic();output.mkdir(parents=True,exist_ok=True)
 assert digest(MASTER)==EXPECTED
 cols=pq.ParquetFile(MASTER).schema.names
 keep=[c for c in cols if c in ['id','name','type','region','lat','lon','municipality_oktmo8_2021','population_1989','population_value_quality_2010'] or c.startswith(('population_2002','population_2010','population_2021','places_baseline_','places_conditional_','econ_native_2011_','econ_native_2021_','econ_native_2025_','agri_','wb_strict_focus'))]
 d=pd.read_parquet(MASTER,columns=keep);assert len(d)==142570 and d.id.is_unique
 d['axis_kind']='ordinary'
 # Federal territory anchors use their own registered function counts; populations are context only.
 fed=pd.read_csv(OLD/'core/external_federal_features.csv')
 for y in [2011,2021,2025]:
  for code in LEGAL.values():
   source=f'econ_legacy_federal_2021_federal_coded_baseline_{code}_legal_entities'
   fed[f'econ_native_{y}_{code}_legal_entities']=fed[source] if source in fed else 0
 # This is a named 2021 source proxy, never a fabricated 2011/2025 history.
 fed['axis_kind']='federal_territory_context';fed['population_1989']=np.nan
 for c in keep:
  if c not in fed:fed[c]=0 if c.startswith(('places_','wb_','econ_')) else None
 d=pd.concat([d,fed[d.columns]],ignore_index=True);nordinary=142570
 pts=xyz(d.lat.values,d.lon.values)
 cp=counts(d);m,caps=mass(cp);div=cp.gt(0).sum(axis=1).to_numpy()
 anchors=(d.places_baseline_school_count.fillna(0).to_numpy()>0)|(d.places_baseline_hospital_count.fillna(0).to_numpy()>0)
 candidate=(div>=2)|anchors;candidate[nordinary:]=True
 candidates=np.flatnonzero(candidate)
 base=assign(pts,candidates,m)
 levels,edges=hierarchy(pts,candidates,m,base['center'])
 member=d[['id','name','type','region','lat','lon','axis_kind','population_2002','population_2010','population_2021']].copy()
 member['own_functional_mass']=m;member['n_observed_function_groups']=div;member['candidate_center']=candidate
 ids=d.id.to_numpy();names=d.name.to_numpy()
 for level,ix in levels.items():
  member[f'center_index_l{level}']=ix
  member[f'center_id_l{level}']=[ids[j] if j>=0 else None for j in ix]
  member[f'center_name_l{level}']=[names[j] if j>=0 else None for j in ix]
 for k in ['distance','pinned','truncated']:member[k]=base[k]
 for k in ['second_ratio','top_weight','entropy']:member['unconstrained_'+k]=base[k]
 member['unconstrained_winner_id']=[ids[j] if j>=0 else None for j in base['unconstrained_center']]
 member['unconstrained_second_center_id']=[ids[j] if j>=0 else None for j in base['second']]
 member['membership_evidence']='modeled_contemporary_function_gravity_not_observed_trip'
 member['boundary_historical_presence_asserted']=False
 edge=edges.copy();edge['child_id']=ids[edge.child_index];edge['parent_id']=ids[edge.parent_index]
 edge.to_csv(output/'hierarchy.csv',index=False)
 scenarios={};variants=[('radius50','baseline',50,15,'exp',2025,False),('radius100','baseline',100,15,'exp',2025,False),('scale10','baseline',75,10,'exp',2025,False),('scale25','baseline',75,25,'exp',2025,False),('power','baseline',75,15,'power',2025,False),('nearest','baseline',75,15,'nearest',2025,False),('conditional','conditional',75,15,'exp',2025,False),('physical_only','baseline',75,15,'exp',2025,True),('registered2021','baseline',75,15,'exp',2021,False),('population2002','baseline',75,15,'exp',2025,False),('mixed_population2002','baseline',75,15,'exp',2025,False)]
 audit=[];same=np.zeros(len(d),int)
 for label,mode,radius,scale,kernel,year,phys in variants:
  c=counts(d,mode,year,phys)
  if label=='registered2021':
   for g in GROUPS:c[g]=d[f'econ_native_2021_{LEGAL[g]}_legal_entities'].fillna(0) if g in LEGAL else 0
  mm,_=mass(c)
  if label=='population2002':mm=np.log1p(d.population_2002.fillna(0).to_numpy(float))
  if label=='mixed_population2002':mm=mm+np.log1p(d.population_2002.fillna(0).to_numpy(float))
  dd=c.gt(0).sum(axis=1).to_numpy();cand=(dd>=2)|anchors;cand[nordinary:]=True
  rr=assign(pts,np.flatnonzero(cand),mm,radius,scale,kernel)
  scenarios[label]=rr['center'];same+=(rr['center']==base['center'])
  audit.append(dict(scenario=label,candidate_centers=int(cand[:nordinary].sum()),assigned=int((rr['center'][:nordinary]>=0).sum()),same_center_as_baseline=int((rr['center'][:nordinary]==base['center'][:nordinary]).sum()),changed=int((rr['center'][:nordinary]!=base['center'][:nordinary]).sum()),assigned_population2021=float(d.population_2021.iloc[:nordinary][rr['center'][:nordinary]>=0].sum()),max_distance_km=float(np.nanmax(rr['distance'])),k64_search_truncated=int(rr['truncated'][:nordinary].sum())))
  print(label,audit[-1],flush=True)
 member['same_center_across11_scenarios']=same
 for label,ix in scenarios.items():member['scenario_'+label+'_center_id']=[ids[j] if j>=0 else None for j in ix]
 # Function-specific fields retain all single-function providers, including local self service.
 for g in ['education','healthcare','trade_access']:
  a=cp[g].to_numpy();cc=np.flatnonzero(a>0);fm=np.log1p(a)
  r=assign(pts,cc,fm,75,15)
  member[g+'_potential_provider_id']=[ids[j] if j>=0 else None for j in r['center']]
  member[g+'_potential_distance_km']=r['distance']
 member.iloc[:nordinary].to_parquet(output/'memberships.parquet',index=False);member.iloc[:nordinary].to_csv(output/'memberships.csv.gz',index=False)
 member.iloc[nordinary:].to_csv(output/'federal_context_assignments.csv',index=False)
 d[['id','name','region','axis_kind']].assign(own_mass=m,diversity=div,candidate_center=candidate).to_csv(output/'center_mass_components.csv.gz',index=False)
 cp.assign(id=d.id).to_parquet(output/'functional_count_components.parquet',index=False)
 systems,balances=aggregate(d,levels,m,output)
 context=municipal_context(d,base['center'],systems,output);gradients(d,base['center'],output)
 pd.DataFrame(audit).to_csv(output/'sensitivity.csv',index=False)
 ts=[]
 low=systems[(systems.level==1)&systems.has_rural_periphery&systems.center_axis_kind.eq('ordinary')]
 for re in [.001,.0025,.005]:
  for se in [.01,.02,.05]:
   _,_,types=typology(low.system_population_2002.values,low.system_population_2021.values,low.center_population_2002.values,low.center_population_2021.values,rate_eps=re,share_eps=se)
   for typ,count in pd.Series(types).value_counts().items():ts.append(dict(annual_rate_threshold=re,center_share_threshold=se,type=typ,n_systems=int(count)))
 pd.DataFrame(ts).to_csv(output/'typology_threshold_sensitivity.csv',index=False)
 summary={'status':'COMPUTED_NOT_YET_INDEPENDENTLY_ACCEPTED','master_sha256':EXPECTED,'master_shape':[142570,914],'ordinary_rows':nordinary,'federal_context_nodes':len(d)-nordinary,'candidate_centers_ordinary':int(candidate[:nordinary].sum()),'ordinary_assigned':int((base['center'][:nordinary]>=0).sum()),'ordinary_unassigned':int((base['center'][:nordinary]<0).sum()),'candidate_self_cores':int(base['pinned'][:nordinary].sum()),'near_tie_noncore':int(((base['second_ratio']>=.8)&~base['pinned'])[:nordinary].sum()),'k64_truncated':int(base['truncated'][:nordinary].sum()),'levels':{str(l):int((systems.level==l).sum()) for l in levels},'systems_with_rural_periphery_l1':len(low),'type_counts_l1_rural':{str(k):int(v) for k,v in low.demographic_type.value_counts().items()},'population_balances':balances,'mass_log_caps':dict(zip(GROUPS,caps)),'mass_uses_population':False,'mass_trained_on_catchments':False,'modern_function_dates':'RFSD2025;Places2026-09-23.1;WB2026-10-19','federal_function_proxy':'own registered2021counts; not2025history','transport_proxy':'great_circle_distance_not_network_minutes','historical_boundary_equivalence_asserted':False,'seconds':round(time.monotonic()-start,3)}
 dump(output/'model_receipt.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=ROOT/'results');args=ap.parse_args();run(args.output)
