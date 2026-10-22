"""Recoverable SGRT geometry. NOT evidence of observed flows. All census source zeros retained."""
from pathlib import Path
import argparse,json,hashlib,time,os
import numpy as np,pandas as pd
from scipy.spatial import cKDTree
EARTH=6371.0088

def xyz(lat,lon):
 la,lo=np.radians(lat),np.radians(lon)
 return np.column_stack((np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)))
def chord(km):return 2*np.sin(km/(2*EARTH))
def km(ch):return 2*EARTH*np.arcsin(np.clip(ch/2,0,1))
def candidates(d,year,radius=10):
 coords=xyz(d.lat,d.lon);mass=d[f'population_{year}'].to_numpy(float);tree=cKDTree(coords);sel=np.zeros(len(d),bool)
 for i,nb in enumerate(tree.query_ball_point(coords,chord(radius),workers=2)):
  mx=mass[nb].max();best=min(j for j in nb if mass[j]==mx)
  sel[i]=mass[i]>0 and i==best
 col=f'settlement_type_{year}' if f'settlement_type_{year}' in d else 'type'
 sel|=d[col].fillna('').str.lower().isin(['город','пгт','посёлок городского типа','рабочий посёлок']).to_numpy()&(mass>0)
 sel|=d.external_anchor.to_numpy(bool)
 return np.flatnonzero(sel)
def nearest(coords,ci,radius):
 dist,j=cKDTree(coords[ci]).query(coords,workers=2);out=ci[j];out[km(dist)>radius]=-1;out[ci]=ci
 return out,km(dist)
def edges(coords,ci,radius):
 a=cKDTree(coords);b=cKDTree(coords[ci]);m=a.sparse_distance_matrix(b,chord(radius),output_type='coo_matrix')
 return m.row.astype(np.int32),m.col.astype(np.int32),km(m.data)
def huff(coords,ci,mass,radius=100,beta=2,d0=5,graph=None):
 row,col,dist=edges(coords,ci,radius) if graph is None else graph
 take=dist<=radius;row=row[take];col=col[take];dist=dist[take];w=mass[ci[col]]/(dist+d0)**beta;n=len(coords)
 sums=np.bincount(row,weights=w,minlength=n);mx=np.zeros(n);np.maximum.at(mx,row,w);first=np.full(n,len(ci),int)
 tied=(w==mx[row])&(w>0);np.minimum.at(first,row[tied],col[tied]);win=np.full(n,-1,int);valid=first<len(ci);win[valid]=ci[first[valid]]
 w2=w.copy();w2[col==first[row]]=0;secondmx=np.zeros(n);np.maximum.at(secondmx,row,w2);second=np.full(n,len(ci),int);tied2=(w2==secondmx[row])&(w2>0);np.minimum.at(second,row[tied2],col[tied2]);runner=np.full(n,-1,int);valid2=second<len(ci);runner[valid2]=ci[second[valid2]]
 p=np.divide(mx,sums,out=np.zeros(n),where=sums>0);p2=np.divide(secondmx,sums,out=np.zeros(n),where=sums>0)
 return dict(raw_huff_winner=win,raw_huff_runner=runner,raw_huff_pmax=p,raw_huff_psecond=p2,potential=sums,n_competitors=np.bincount(row,minlength=n),ambiguity_gap_lt_point1=(p-p2<.1)&(sums>0))
def idlabels(d,x):return np.array([d.id.iloc[i] if i>=0 else 'UNASSIGNED' for i in x],object)
def export(df,path):
 p=Path(path);tmp=p.with_name(p.stem+'.tmp.parquet');df.to_parquet(tmp,index=False);assert len(pd.read_parquet(tmp))==len(df);os.replace(tmp,p.with_suffix('.parquet'));tmp=p.with_name(p.stem+'.tmp.csv.gz');df.to_csv(tmp,index=False,compression='gzip');assert len(pd.read_csv(tmp))==len(df);os.replace(tmp,p.with_suffix('.csv.gz'))
def aggregate(d,n,assignment):
 z=d.iloc[:n].copy();z['center_id']=idlabels(d,assignment[:n]);ag=z.groupby('center_id',dropna=False).agg(n_settlements=('id','size'),population_2002=('population_2002','sum'),population_2010=('population_2010','sum'),population_2021=('population_2021','sum')).reset_index()
 ix=d.set_index('id');
 for field in ['name','region','lat','lon']:ag['center_'+field if field in ['name','region'] else field]=ag.center_id.map(ix[field])
 for year in [2002,2010,2021]:
  own=ag.center_id.map(ix[f'population_{year}']).fillna(0);own[ag.center_id.isin(d.loc[d.external_anchor,'id'])]=0;ag[f'center_population_{year}']=own;ag[f'environment_population_{year}']=ag[f'population_{year}']-own
 for part,pre in [('total',''),('center','center_'),('environment','environment_')]:
  for base in [2002,2010]:
   b=ag[f'{pre}population_{base}'];f=ag[f'{pre}population_2021'];ag[f'{part}_growth_{base}_2021']=f/b.replace(0,np.nan)-1
   ag[f'{part}_absolute_change_{base}_2021']=f-b;ag[f'{part}_log1p_change_{base}_2021']=np.log1p(f)-np.log1p(b)
   ag[f'{part}_transition_{base}_2021']=np.select([(b==0)&(f>0),(b>0)&(f==0),(b==0)&(f==0)],['zero_to_positive_observed','positive_to_zero_observed','zero_both_observed'],default='positive_both_observed')
 c=ag.center_growth_2010_2021;e=ag.environment_growth_2010_2021
 ag['trajectory']=np.select([ag.center_population_2010.eq(0),ag.environment_transition_2010_2021.eq('zero_to_positive_observed'),e.isna(),(c<0)&(e<0),(c<0)&(e>=0),(c>=0)&(e<0),(c>=0)&(e>=0)],['center_outcome_undefined','environment_zero_to_positive_observed','no_environment','joint_decline','center_decline_environment_non_decline','center_non_decline_environment_decline','joint_non_decline'],default='undefined')
 for base in [2002,2010,2021]:ag[f'center_share_{base}']=ag[f'center_population_{base}']/ag[f'population_{base}'].replace(0,np.nan)
 ag['center_share_change']=ag.center_share_2021-ag.center_share_2010
 return ag

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--panel',type=Path,default=Path(__file__).resolve().parent.parent/'data/panel.parquet');parser.add_argument('--out',type=Path,default=Path(__file__).resolve().parent);parser.add_argument('--skip-sensitivity',action='store_true');args=parser.parse_args();O=args.out;O.mkdir(parents=True,exist_ok=True);t=time.time();d=pd.read_parquet(args.panel).sort_values('id').reset_index(drop=True);n=len(d)
 assert d.id.is_unique and d[['lat','lon','population_2002','population_2010','population_2021']].notna().all().all();assert (d[['population_2002','population_2010','population_2021']]>=0).all().all()
 d['external_anchor']=False;repo=Path(__file__).resolve().parents[3];ext=pd.read_csv(repo/'publication/stage71/accepted_common_federal_territory_axis.csv');rows=[]
 for key,g in ext.groupby('territory_key'):
  row=dict(id=key,name=g.territory_name.iloc[0],type='external_territory_anchor',region=g.region_norm.iloc[0],lat=g.latitude.iloc[0],lon=g.longitude.iloc[0],external_anchor=True)
  row.update({f'population_{y}':g.loc[g.census_year==y,'territory_population'].iloc[0] for y in [2002,2010,2021]});rows.append(row)
 d=pd.concat([d,pd.DataFrame(rows)],ignore_index=True);coords=xyz(d.lat,d.lon);mass=d.population_2010.to_numpy(float);ci=candidates(d,2010);print('primary centres',len(ci),'rows',n,flush=True)
 near,dist=nearest(coords,ci,100);g=edges(coords,ci,200);h=huff(coords,ci,mass,graph=g)
 s=d.iloc[:n][[c for c in ['id','name','type','region','lat','lon','population_2002','population_2010','population_2021','municipality_upper_2021','municipality_oktmo8_2021'] if c in d]].copy();s['center_id']=idlabels(d,near[:n]);s['distance_km']=dist[:n];s['center_anchored']=np.isin(np.arange(n),ci)
 for k,v in h.items():s[k]=idlabels(d,v[:n]) if k in ['raw_huff_winner','raw_huff_runner'] else v[:n]
 dd,jj=cKDTree(coords[ci]).query(coords,k=2,workers=2);rr=ci[jj[:,1]];rr[km(dd[:,1])>100]=-1;s['nearest_runner_id']=idlabels(d,rr[:n]);s['nearest_margin_km']=np.where(km(dd[:n,1])<=100,km(dd[:n,1])-km(dd[:n,0]),np.nan);s['raw_huff_probability_margin']=s.raw_huff_pmax-s.raw_huff_psecond
 s['assignment_method']='nearest_spherical_center_within100km';s['score_interpretation']='Huff scores describe separate potential field; not nearest assignment probability';export(s,O/'nearest_membership.parquet');export(aggregate(d,n,near),O/'zone_trajectories.parquet')
 # Bottom-up parent selection retains low units and links to the strongest larger-mass field.
 # Stronger-than-own-field criterion allows independent roots; every admitted edge increases mass.
 cc=coords[ci];ct=cKDTree(cc);parent=np.full(len(ci),-1,int);ratio=np.zeros(len(ci))
 for k,nb in enumerate(ct.query_ball_point(cc,chord(100),workers=2)):
  nb=np.array([j for j in nb if mass[ci[j]]>mass[ci[k]]],int)
  if len(nb):
   ds=km(np.linalg.norm(cc[nb]-cc[k],axis=1));w=mass[ci[nb]]/(ds+5)**2;j=np.argmax(w);ratio[k]=w[j]/(mass[ci[k]]/25)
   if ratio[k]>1:parent[k]=nb[j]
 chains=[]
 for k in range(len(ci)):
  ch=[k]
  while parent[ch[-1]]>=0:ch.append(parent[ch[-1]]);assert len(ch)<=len(ci)
  chains.append(ch)
 centers=d.iloc[ci][['id','name','type','region','lat','lon','population_2002','population_2010','population_2021','external_anchor']].copy().reset_index(drop=True);col='settlement_type_2010' if 'settlement_type_2010' in d else 'type';urban=d.iloc[ci][col].fillna('').str.lower().isin(['город','пгт','посёлок городского типа','рабочий посёлок']).to_numpy();centers['center_origin']=np.where(centers.external_anchor,'external_territorial_anchor',np.where(urban,'urban2010','rural_local_maximum_candidate_not_verified_admin'));centers['settlement_type_2010']=d.iloc[ci][col].to_numpy();centers['parent_id']=[centers.id.iloc[j] if j>=0 else None for j in parent];centers['root_id']=[centers.id.iloc[ch[-1]] for ch in chains];centers['depth_to_root']=[len(ch)-1 for ch in chains];centers['chain_ids']=['|'.join(centers.id.iloc[j] for j in ch) for ch in chains];centers['external_to_self_field_ratio']=ratio;export(centers,O/'centers.parquet')
 s['root_id']=s.center_id.map(dict(zip(centers.id,centers.root_id))).fillna('UNASSIGNED');s['center_origin']=s.center_id.map(dict(zip(centers.id,centers.center_origin))).fillna('UNASSIGNED')
 b=s.population_2010;f=s.population_2021;s['transition_2010_2021']=np.select([(b==0)&(f>0),(b>0)&(f==0),(b==0)&(f==0)],['zero_to_positive_observed','positive_to_zero_observed','zero_both_observed'],default='positive_both_observed');s['log1p_change_2010_2021']=np.log1p(f)-np.log1p(b);export(s,O/'nearest_membership.parquet')
 nested=[];rootmap=dict(zip(centers.id,centers.root_id));lookup=dict(zip(centers.id,range(len(centers))))
 for step in range(max(len(ch) for ch in chains)):
  mp={centers.id.iloc[k]:centers.id.iloc[ch[min(step,len(ch)-1)]] for k,ch in enumerate(chains)};z=s[['id','center_id','population_2002','population_2010','population_2021']].copy();z['nested_unit']=z.center_id.map(mp).fillna('UNASSIGNED');a=z.groupby('nested_unit').agg(n_settlements=('id','size'),**{f'population_{y}':(f'population_{y}','sum') for y in [2002,2010,2021]}).reset_index();a['aggregation_step']=step;nested.append(a)
 export(pd.concat(nested,ignore_index=True),O/'nested_aggregates.parquet')
 # Dynamic2021 center list: raw observed masses/statuses change, coordinates remain fixed.
 c2021=candidates(d,2021);a2021,dist21=nearest(coords,c2021,100);export(pd.DataFrame(dict(id=s.id,center_id=idlabels(d,a2021[:n]),distance_km=dist21[:n])),O/'dynamic2021_membership.parquet')
 # Exact symmetric decomposition includes union of centers and unassigned residual.
 dec=[];a0=idlabels(d,near[:n]);a1=idlabels(d,a2021[:n]);p1=s.population_2021.to_numpy()
 for base in [2002,2010]:
  p0=s[f'population_{base}'].to_numpy()
  for key in sorted(set(a0)|set(a1)):
   z0=(a0==key);z1=(a1==key);demo=((z0.astype(float)+z1)*(p1-p0)/2).sum();realloc=((p0+p1)*(z1.astype(float)-z0)/2).sum();change=(z1*p1-z0*p0).sum();assert abs(demo+realloc-change)<1e-6;dec.append(dict(center_id=key,baseline_year=base,fixed_base_population=float((z0*p0).sum()),fixed2021_population=float((z0*p1).sum()),dynamic2021_population=float((z1*p1).sum()),observed_dynamic_change=float(change),symmetric_demographic_effect=float(demo),symmetric_reallocation_effect=float(realloc)))
 export(pd.DataFrame(dec),O/'fixed_dynamic_decomposition.parquet')
 # Flat gravity remains a benchmark, with forced preservation of lower centers clearly marked.
 flat=h['raw_huff_winner'].copy();flat[ci]=ci;sf=pd.DataFrame(dict(id=s.id,center_id=idlabels(d,flat[:n]),anchor_forced=(flat[:n]!=h['raw_huff_winner'][:n])));export(sf,O/'flat_gravity_membership.parquet');export(aggregate(d,n,flat),O/'flat_zone_trajectories.parquet')
 sens=[]
 def record(label,assignment,base=2010,**params):
  same=assignment[:n]==near[:n];sens.append(dict(scenario=label,n_centers=params.pop('n_centers',len(ci)),membership_agreement_with_primary=float(same.mean()),population2010_weighted_agreement=float(np.average(same,weights=s.population_2010)),unassigned=int((assignment[:n]<0).sum()),**params))
 record('flat_gravity_beta2_d05_R100',flat)
 if not args.skip_sensitivity:
  for beta in [1,2,3]:
   for d0 in [2,5,10]:
    for radius in [50,100,200]:
     hh=huff(coords,ci,mass,radius,beta,d0,g);aa=hh['raw_huff_winner'].copy();aa[ci]=ci;record(f'flat_beta{beta}_d0{d0}_R{radius}',aa,beta=beta,d0=d0,radius=radius)
  for radius in [50,100,200]:aa,_=nearest(coords,ci,radius);record(f'nearest_R{radius}',aa,radius=radius)
  for radius in [5,10,20]:
   c2=ci if radius==10 else candidates(d,2010,radius);aa,_=nearest(coords,c2,100);record(f'nearest_localmax{radius}',aa,maxima_radius=radius,n_centers=len(c2))
 pd.DataFrame(sens).to_csv(O/'parameter_sensitivity.csv',index=False)
 checks=[];ag=pd.read_parquet(O/'zone_trajectories.parquet');nest=pd.read_parquet(O/'nested_aggregates.parquet')
 for y in [2002,2010,2021]:
  total=float(s[f'population_{y}'].sum());assert total==float(ag[f'population_{y}'].sum());checks.append(dict(test=f'full_population_conserved_{y}',passed=True,total=total))
  for step,a in nest.groupby('aggregation_step'):assert total==float(a[f'population_{y}'].sum())
 checks.extend([dict(test='all2010_zeros_retained',passed=int(s.population_2010.eq(0).sum())==int(d.iloc[:n].population_2010.eq(0).sum())),dict(test='strict_mass_parent_acyclic',passed=all(parent[k]<0 or mass[ci[parent[k]]]>mass[ci[k]] for k in range(len(ci)))),dict(test='own_centers_retained',passed=bool((near[ci]==ci).all()))]);assert all(c['passed'] for c in checks)
 for base,a in pd.DataFrame(dec).groupby('baseline_year'):assert abs(a.symmetric_reallocation_effect.sum())<1e-6;assert a.observed_dynamic_change.sum()==float((s.population_2021-s[f'population_{base}']).sum())
 summary=dict(n_rows=n,n_centers=len(ci),n_dynamic2021_centers=len(c2021),zeros2010=int(s.population_2010.eq(0).sum()),unassigned=int((near[:n]<0).sum()),n_parent_edges=int((parent>=0).sum()),max_depth=max(len(ch)-1 for ch in chains),flat_nearest_agreement=float((flat[:n]==near[:n]).mean()),trajectory_counts=ag.trajectory.value_counts().to_dict(),population_sums={str(y):float(s[f'population_{y}'].sum()) for y in [2002,2010,2021]},wall_seconds=time.time()-t,interpretation='Calculated geometric membership, not direct observed flows; external federal masses excluded from outcome sums')
 (O/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False));(O/'invariants.json').write_text(json.dumps(checks,indent=2));manifest=dict(panel_sha256=hashlib.sha256(args.panel.read_bytes()).hexdigest(),federal_axis_sha256=hashlib.sha256((repo/'publication/stage71/accepted_common_federal_territory_axis.csv').read_bytes()).hexdigest(),script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in O.glob('*') if p.suffix in ['.parquet','.gz','.csv'] and '.tmp.' not in p.name});(O/'manifest.json').write_text(json.dumps(manifest,indent=2));(O/'FINISHED.json').write_text(json.dumps(dict(status='finished',membership_sha256=hashlib.sha256((O/'nearest_membership.parquet').read_bytes()).hexdigest(),summary=summary),indent=2,ensure_ascii=False));print(json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
