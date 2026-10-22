"""Independent post-fit municipal diagnostics, finite-block uncertainty and fixed source cases."""
from pathlib import Path
import json,hashlib
import pandas as pd,numpy as np
O=Path(__file__).resolve().parent;R=O.parent;D=R/'data';M=R/'model'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
P=D/'panel.parquet';B=D/'municipality_bridge.parquet';N=M/'nearest_membership.parquet';H=M/'centers.parquet';S=O/'cases_sources.json'
p=pd.read_parquet(P,columns=['id','name','type','region','lat','lon','population_2010','source_record_id_2021'])
b=pd.read_parquet(B,columns=['id','source_record_id','municipality_role','municipality_oktmo_code8','municipality_label_raw','context_status','code_namespace'])
b=b[b.municipality_role.eq('upper')];assert b.id.is_unique and b.source_record_id.is_unique
allowed=['exact_unique_source_context','verified_parent_code_multiple_source_claims']
u=b[b.code_namespace.eq('RU_OKTMO')&b.context_status.isin(allowed)&b.municipality_oktmo_code8.notna()].copy();assert u.id.is_unique
# Rejoin the native source key ourselves, not the model's enriched municipal column.
a=p[['id','source_record_id_2021']].merge(u.drop(columns='id'),left_on='source_record_id_2021',right_on='source_record_id',how='left',validate='1:1')
assert len(a)==len(p)
n=pd.read_parquet(N,columns=['id','center_id','center_anchored','raw_huff_winner','population_2010','lat','lon'])
h=pd.read_parquet(H);assert n.id.is_unique and h.id.is_unique
n=n.rename(columns={'center_id':'nearest_center_id'});n['flat_center_id']=np.where(n.center_anchored,n.id,n.raw_huff_winner)
# The flat benchmark deliberately shares own-center retention. Its raw Huff winner remains separate.
flatfile=M/'flat_gravity_membership.parquet'
if flatfile.exists():
 ff=pd.read_parquet(flatfile,columns=['id','center_id']);check=n[['id','flat_center_id']].merge(ff,on='id',validate='1:1');assert check.flat_center_id.eq(check.center_id).all()
x=n.merge(a[['id','municipality_oktmo_code8','context_status']],on='id',validate='1:1')
labels=a[['id','municipality_oktmo_code8','context_status']]
for stem in ['nearest','flat']:
 lab=labels.rename(columns={'id':f'{stem}_center_id','municipality_oktmo_code8':f'{stem}_admin','context_status':f'{stem}_admin_context'})
 x=x.merge(lab,on=f'{stem}_center_id',how='left',validate='m:1')
x['pair_covered']=x.municipality_oktmo_code8.notna()&x.nearest_admin.notna()&x.flat_admin.notna()
x['noncenter']=~x.center_anchored
excluded=x[x.noncenter&~x.pair_covered].copy();excluded.to_parquet(O/'excluded_noncenters.parquet',index=False)
z=x[x.noncenter&x.pair_covered].copy();assert not z.center_anchored.any() and z.id.is_unique
z['nearest_same_admin']=z.municipality_oktmo_code8.eq(z.nearest_admin);z['flat_same_admin']=z.municipality_oktmo_code8.eq(z.flat_admin);z['delta_nearest_minus_flat']=z.nearest_same_admin.astype(int)-z.flat_same_admin.astype(int)
z.to_parquet(O/'paired_noncenters.parquet',index=False);z.to_csv(O/'paired_noncenters.csv.gz',index=False)
rows=[]
for scope,mask in [('all_paired_noncenters',np.ones(len(z),bool)),('strict_exact_contexts',z.context_status.eq('exact_unique_source_context')&z.nearest_admin_context.eq('exact_unique_source_context')&z.flat_admin_context.eq('exact_unique_source_context'))]:
 t=z[mask];w=t.population_2010.to_numpy(float);rows.append(dict(scope=scope,n=len(t),population2010=float(w.sum()),nearest_admin_concordance=float(t.nearest_same_admin.mean()),flat_admin_concordance=float(t.flat_same_admin.mean()),delta_nearest_minus_flat=float(t.delta_nearest_minus_flat.mean()),population2010_weighted_nearest=float(np.average(t.nearest_same_admin,weights=w)),population2010_weighted_flat=float(np.average(t.flat_same_admin,weights=w)),population2010_weighted_delta=float(np.average(t.delta_nearest_minus_flat,weights=w)),same_assignment_fraction=float(t.nearest_center_id.eq(t.flat_center_id).mean())))
pd.DataFrame(rows).to_csv(O/'administrative_summary.csv',index=False)
# Finite occupied-block resampling: complete blocks move together; point IID errors are never assumed.
def spherical_laea(lon,lat):
 lo,la=np.radians(lon),np.radians(lat);lo0,la0=np.radians(100),np.radians(60)
 den=1+np.sin(la0)*np.sin(la)+np.cos(la0)*np.cos(la)*np.cos(lo-lo0)
 assert np.all(den>0)
 k=np.sqrt(2/den);rr=6371008.8
 return rr*k*np.cos(la)*np.sin(lo-lo0),rr*k*(np.cos(la0)*np.sin(la)-np.sin(la0)*np.cos(la)*np.cos(lo-lo0))
zz=spherical_laea(np.array([100.]),np.array([60.]));assert abs(zz[0][0])+abs(zz[1][0])<1e-8
xx,yy=spherical_laea(z.lon.to_numpy(),z.lat.to_numpy());bs=[]
for km in [250,400,600]:
 t=z.copy();t['bx']=np.floor(xx/(km*1000)).astype(int);t['by']=np.floor(yy/(km*1000)).astype(int);t['weighted_delta']=t.delta_nearest_minus_flat*t.population_2010
 blocks=t.groupby(['bx','by']).agg(n=('id','size'),delta_sum=('delta_nearest_minus_flat','sum'),population_sum=('population_2010','sum'),weighted_delta_sum=('weighted_delta','sum')).reset_index();blocks.to_csv(O/f'blocks_{km}km.csv',index=False)
 rng=np.random.default_rng(20261019+km);draw=rng.integers(0,len(blocks),size=(399,len(blocks)))
 vals=blocks.delta_sum.to_numpy()[draw].sum(1)/blocks.n.to_numpy()[draw].sum(1);wv=blocks.weighted_delta_sum.to_numpy()[draw].sum(1)/blocks.population_sum.to_numpy()[draw].sum(1)
 pd.DataFrame(dict(replicate=np.arange(399),delta=vals,population2010_weighted_delta=wv)).to_csv(O/f'resamples_{km}km.csv',index=False)
 bs.append(dict(block_km=km,n_blocks=len(blocks),n_replicates=399,point_delta=float(z.delta_nearest_minus_flat.mean()),percentile025=float(np.quantile(vals,.025)),percentile975=float(np.quantile(vals,.975)),population2010_weighted_point_delta=float(np.average(z.delta_nearest_minus_flat,weights=z.population_2010)),population2010_weighted_percentile025=float(np.quantile(wv,.025)),population2010_weighted_percentile975=float(np.quantile(wv,.975))))
pd.DataFrame(bs).to_csv(O/'spatial_bootstrap_summary.csv',index=False)
# Geographical source cases are frozen in their catalogue; parameters are not tuned here.
cat=json.loads(S.read_text());lookup=pd.concat([p,h[~h.id.isin(p.id)]],ignore_index=True).set_index('id');nm=lookup.name.to_dict();hi=h.set_index('id');ni=n.set_index('id');cres=[]
def distance(a,b):
 la,lb=np.radians(a.lat),np.radians(b.lat);v=np.sin((lb-la)/2)**2+np.cos(la)*np.cos(lb)*np.sin(np.radians(b.lon-a.lon)/2)**2
 return float(2*6371.0088*np.arcsin(np.sqrt(np.clip(v,0,1))))
for c in cat:
 a0=lookup.loc[c['origin_id']];a1=lookup.loc[c['expected_center_id']];assert a0['name']==c['origin'] and a0.region==c['region']
 if not c['expected_center_id'].startswith('RU-FED-'):assert a1['name']==c['expected_center']
 r=dict(c);r.update(origin_type=a0.type,expected_center_type=a1.type,expected_geodesic_km=distance(a0,a1),expected_beyond100km=distance(a0,a1)>100,origin_is_anchor=bool(ni.loc[c['origin_id'],'center_anchored']))
 for stem in ['nearest','flat']:
  cid=ni.loc[c['origin_id'],f'{stem}_center_id'];chain=hi.loc[cid,'chain_ids'] if cid in hi.index else '';ids=chain.split('|') if isinstance(chain,str) else []
  r.update({f'{stem}_center_id':cid,f'{stem}_center_name':nm.get(cid,cid),f'{stem}_center_match':cid==c['expected_center_id'],f'{stem}_chain_ids':chain,f'{stem}_chain_names':' → '.join(nm.get(i,i) for i in ids),f'{stem}_expected_in_chain':c['expected_center_id'] in ids})
 cres.append(r)
cases=pd.DataFrame(cres);cases.to_csv(O/'case_results.csv',index=False);cases.to_parquet(O/'case_results.parquet',index=False)
cases[~cases.nearest_expected_in_chain].to_csv(O/'negative_cases.csv',index=False)
case_summary=dict(n_cases=len(cases),n_regions=cases.region.nunique(),n_unique_primary_url=cases.source_url.nunique(),nearest_direct_match=int(cases.nearest_center_match.sum()),nearest_chain_match=int(cases.nearest_expected_in_chain.sum()),flat_direct_match=int(cases.flat_center_match.sum()),flat_chain_match=int(cases.flat_expected_in_chain.sum()),direct_observed_OD_cases=0,synchronous2010_cases=0,nonprobability_sample=True)
case_summary['without_qualified_C05_n']=int(cases.case_id.ne('C05').sum());case_summary['without_qualified_C05_nearest_chain_match']=int(cases.loc[cases.case_id.ne('C05'),'nearest_expected_in_chain'].sum())
(O/'case_summary.json').write_text(json.dumps(case_summary,indent=2,ensure_ascii=False))
audit=dict(inputs_sha256={str(i.relative_to(R)):sha(i) for i in ([P,B,N,H,S]+([flatfile] if flatfile.exists() else []))},flat_file_independently_checked=flatfile.exists(),n_model=len(n),n_noncenters=int(x.noncenter.sum()),n_jointly_covered_noncenters=len(z),noncenter_coverage=float(len(z)/x.noncenter.sum()),excluded_noncenters=len(excluded),excluded_flat_external=int(excluded.flat_center_id.str.startswith('RU-FED-',na=False).sum()),excluded_nearest_external=int(excluded.nearest_center_id.str.startswith('RU-FED-',na=False).sum()),excluded_unassigned_either=int((excluded.flat_center_id.eq('UNASSIGNED')|excluded.nearest_center_id.eq('UNASSIGNED')).sum()),n_bridge_upper=len(b),n_admissible_upper=len(u),bridge_context_counts=b.context_status.value_counts().to_dict(),summary=rows,spatial_bootstrap=bs,cases=case_summary,method='Post-fit administrative concordance with source-key rejoin; no model fitting. Native municipal reference2021, exact effective boundary date unknown; not historical2010 membership or observed flows.',uncertainty='Spherical Lambert azimuthal equal-area60N100E,R6371008.8m fixed-origin squares; sample occupied complete blocks with replacement399times. Finite observed spatial ensemble; descriptive percentile envelope, not census-error CI or a probability sample of Russia.')
(O/'validation_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2));print(json.dumps(audit,ensure_ascii=False,indent=2))
