#!/usr/bin/env python3
"""Independent route scan/minimum, finite raw-provider geography and full-axis counts."""
from pathlib import Path
import pandas as pd,numpy as np,json,hashlib,math
H=Path(__file__).resolve().parent;ROOT=H.parents[2];REPO=next(p for p in H.parents if (p/'.git').exists());checks=[];pins={}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rd(p,**kw):pins[str(p)]=sha(p);return pd.read_parquet(p,**kw) if p.suffix=='.parquet' else pd.read_csv(p,**kw)
def js(p):pins[str(p)]=sha(p);return json.loads(p.read_text())
def check(s,v,d=None):checks.append(dict(check=s,pass_=bool(v),detail=d));assert v,s+' '+str(d)
def near(a,b):return (pd.isna(a) and pd.isna(b)) or (pd.notna(a) and pd.notna(b) and abs(float(a)-float(b))<1e-6)
def ari(a,b):
 f=pd.DataFrame({'a':a,'b':b});p=lambda x:float(np.sum(x*(x-1)/2));counts=f.groupby(['a','b'],observed=True).size().to_numpy(dtype=float);l=f.a.value_counts().to_numpy(dtype=float);r=f.b.value_counts().to_numpy(dtype=float);n=len(f);total=n*(n-1)/2;expected=p(l)*p(r)/total;den=(p(l)+p(r))/2-expected;return (p(counts)-expected)/den if den else 1.
def run():
 model=ROOT/'model/output_cycle06_access_v2_baseline';diag=rd(ROOT/'validation/cycle06_access_v2_external52/all52_label_diagnostics.parquet');cfg=js(ROOT/'model_inputs_cycle06/final_access_v2/config_baseline_final.json');nodes=rd(model/'nodes.parquet').set_index('id');mass=rd(model/'own_mass_components.parquet').set_index('id');memb=rd(model/'memberships.parquet').set_index('id');old=rd(ROOT/'model/output_cycle05_v4_baseline/memberships.parquet').set_index('id');manifestpath=REPO/cfg['travel_manifest'];manifest=js(manifestpath);aliases=cfg.get('route_id_aliases',{})
 om=rd(manifestpath.parent/manifest['origin_mapping']['path']);dm=rd(manifestpath.parent/manifest['destination_mapping']['path']);om['id']=om.id.replace(aliases);dm['id']=dm.id.replace(aliases);originids=set(diag.origin_id);indices=om.loc[om.id.isin(originids),'origin_index'].tolist();parts=[]
 for item in manifest['parts']:
  p=manifestpath.parent/item['path'];check('actual_routepart_SHA:'+item['path'],sha(p)==item['sha256']);x=pd.read_parquet(p,filters=[('origin_index','in',indices)]);pins[str(p)]=item['sha256']
  if len(x):parts.append(x)
 routes=pd.concat(parts,ignore_index=True);originmap=om.set_index('origin_index');destmap=dm.set_index('destination_index');routes['oid']=routes.origin_index.map(originmap.id);routes['pid']=routes.destination_index.map(destmap.id);routes['minutes']=routes.network_minutes.astype('float64')+4*routes.origin_index.map(originmap.snap_km)+4*routes.destination_index.map(destmap.snap_km);routes.loc[routes.oid.eq(routes.pid),'minutes']=0.;lookup=routes.groupby(['oid','pid']).minutes.min()
 providers={f:set(mass.index[mass['physical_'+f+'_count_proxy'].gt(0)]) for f in ['education','healthcare']};nearest={}
 for q in diag.itertuples():
  for field,pid in [('label_directed_road_minutes',q.provider_id),('function_prediction_directed_road_minutes',q.function_predicted_provider_id),('integral_prediction_directed_road_minutes',q.integral_predicted_provider_id)]:
   val=lookup.get((q.origin_id,pid),np.nan) if pd.notna(pid) else np.nan
   if pid==q.origin_id:val=0.
   check('directed_time:'+field+':'+str(q.label_id),near(val,getattr(q,field)))
  z=routes[routes.oid.eq(q.origin_id)&routes.pid.isin(providers[q.function_group])&routes.minutes.le(180+1e-4)][['pid','minutes']].copy()
  if q.origin_id in providers[q.function_group]:z=pd.concat([z,pd.DataFrame([dict(pid=q.origin_id,minutes=0.)])])
  z=z.sort_values(['minutes','pid']).drop_duplicates('pid');pid=z.iloc[0].pid if len(z) else None;minutes=z.iloc[0].minutes if len(z) else np.nan
  check('nearest_rawmatrix_ID:'+str(q.label_id),(pid==q.nearest_provider_id) if pd.notna(pid) else pd.isna(q.nearest_provider_id));check('nearest_rawmatrix_time:'+str(q.label_id),near(minutes,q.nearest_provider_road_minutes));check('nearest_availability:'+str(q.label_id),bool(q.nearest_prediction_available)==bool(pd.notna(pid)))
  check('prediction_availability:'+str(q.label_id),bool(q.function_prediction_available)==pd.notna(q.function_predicted_provider_id) and bool(q.integral_prediction_available)==pd.notna(q.integral_predicted_provider_id))
 # Full source-axis supplement: the six nonadditive source records remain in this
 # denominator; external model-only context IDs are excluded by exact source set.
 sup=js(ROOT/'robustness/cycle06_access_v2_full_source_axis_supplement/receipt.json');axis=rd(ROOT/'data/source_controls_cycle05/full_settlement_axis_cycle05_federal_children.parquet');ids=axis.id;check('complete_sourceIDframe',len(ids)==173862 and ids.is_unique and set(ids)<=set(memb.index))
 for row in sup['metrics']:
  a=old.loc[ids,'center_id_l'+str(row['level'])];b=memb.loc[ids,'center_id_l'+str(row['level'])];both=a.notna()&b.notna();counts={'total_axis_records':len(ids),'old_assigned':int(a.notna().sum()),'new_assigned':int(b.notna().sum()),'both_assigned':int(both.sum()),'old_only_assigned':int((a.notna()&b.isna()).sum()),'new_only_assigned':int((a.isna()&b.notna()).sum()),'neither_assigned':int((a.isna()&b.isna()).sum()),'exact_center_retained':int((both&a.eq(b)).sum()),'different_center_both_assigned':int((both&a.ne(b)).sum()),'missing_or_unavailable_excluded_from_ARI':len(ids)-int(both.sum())};check('fullaxis_counts:L'+str(row['level']),all(row[k]==v for k,v in counts.items()));check('fullaxis_ARI:L'+str(row['level']),abs(ari(a[both].to_numpy(),b[both].to_numpy())-row['ARI_common_assigned_only'])<1e-12)
 support=js(ROOT/'validation/cycle06_access_v2_external52_provider_support/receipt.json');raw={f:rd(ROOT/f'model_inputs_cycle05/relinked_v4/{f}/source_objects_relinked.parquet') for f in ['education','medical']};saved=rd(ROOT/'validation/cycle06_access_v2_external52_provider_support/all_raw_sector_assertions_within3km_of_documented_providerNP.parquet');geocounts=[]
 for row in support['provider_support']:
  pid=row['provider_id'];fn=diag.loc[diag.provider_id.eq(pid),'function_group'].iloc[0];x=raw['education' if fn=='education' else 'medical'];lat=float(nodes.at[pid,'lat']);lon=float(nodes.at[pid,'lon']);lat1=np.radians(pd.to_numeric(x.lat,errors='coerce'));lon1=np.radians(pd.to_numeric(x.lon,errors='coerce'));a=np.sin((lat1-np.radians(lat))/2)**2+np.cos(lat1)*np.cos(np.radians(lat))*np.sin((lon1-np.radians(lon))/2)**2;dist=2*6371.0088*np.arcsin(np.sqrt(a.clip(0,1)));nearby=x[dist.le(3)].copy();tag=nearby.education_group.eq('school') if fn=='education' else nearby.revised_broad_function.isin(['healthcare','dentistry']);check('raw3km_all:'+pid,len(nearby)==row['raw_any_sector_assertions_within3km']);check('raw3km_school_clinical:'+pid,int(tag.sum())==row['raw_school_or_clinical_assertions_within3km']);z=saved[saved.label_provider_id.eq(pid)];check('raw3km_savedrows:'+pid,len(z)==len(nearby));geocounts.append(dict(provider_id=pid,name=nodes.at[pid,'name'],function_group=fn,raw3km_count=len(nearby),school_or_clinical=int(tag.sum()),positive_model_source_witness=bool(mass.at[pid,'physical_'+fn+'_count_proxy']>0)))
 pd.DataFrame(geocounts).to_csv(H/'independent_provider_source_coverage.csv',index=False);out=dict(status='INDEPENDENT_ROUTE_NEAREST_FINITE_SOURCE_AND_FULL_AXIS_MATH_ACCEPTED',all_checks_passed=True,n_checks=len(checks),n_failed=0,checks=checks,source_sha256=pins,scope='Actual directed compact matrix for all52origins, nearest declared positive provider inventory; raw finite3km OSM assertions; exact173862sourceID denominator',not_observed_trips=True,raw3km_is_not_verified_provider_identity_or_absence=True,code_sha256=sha(Path(__file__)));(H/'phase2_audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(len(checks))
if __name__=='__main__':run()
