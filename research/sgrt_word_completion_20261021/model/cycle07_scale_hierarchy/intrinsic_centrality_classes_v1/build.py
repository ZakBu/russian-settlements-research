"""Finite source-only own-centrality classes, not intrinsic functional orders."""
from pathlib import Path
import argparse,json,hashlib,time
import numpy as np,pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score
HERE=Path(__file__).resolve().parent;BASE=next(p for p in HERE.parents if (p/'model').is_dir()and(p/'transport').is_dir())
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb')as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def elbow(curve):
 y=np.array([r['sse']for r in curve],float);ks=np.array([r['K']for r in curve],float)
 if len(y)!=10 or not np.isfinite(y).all()or y[0]<=1e-20:return {'status':'no_elbow_degenerate_curve','K':None}
 y=y/y[0]
 if np.any(np.diff(y)>1e-9):return {'status':'no_elbow_nonmonotonic_optimizer_curve','K':None}
 Z=np.c_[np.ones(10),ks];single=float(np.sum((y-Z@np.linalg.lstsq(Z,y,rcond=None)[0])**2))
 if single<=1e-16:return {'status':'no_elbow_linear_curve','K':None}
 # Kneedle/chord distance is primary; hinge regression is an adequacy check.
 chord=1+(y[-1]-1)*(ks-1)/9;gap=chord-y;interior=np.arange(1,9);largest=float(np.max(gap[interior]));selected=next(i for i in interior if gap[i]>=largest-1e-12);k=int(ks[selected])
 X=np.c_[Z,np.maximum(0,ks-k)];b=np.linalg.lstsq(X,y,rcond=None)[0];s=float(np.sum((y-X@b)**2));gain=1-s/single
 valid=largest>=.1 and gain>=.25 and b[1]<0 and b[2]>0 and abs(b[1]+b[2])<abs(b[1])
 if not valid:return {'status':'no_elbow_shape_or_gain','K':None,'relative_gain':gain,'normalized_chord_gap':largest}
 if min(curve[k-1]['positive_provider_class_counts'])<10:return {'status':'no_elbow_selected_class_too_small','K':None,'candidate_K':k,'relative_gain':gain}
 return {'status':'meaningful_engineering_elbow','K':k,'relative_gain':gain,'singleline_sse':single,'hinge_sse':s,'normalized_chord_gap':largest}
def fit_spectrum(x,weights):
 curve=[];fits={}
 for k in range(1,11):
  model=KMeans(n_clusters=k,n_init=10,max_iter=300,tol=1e-6,random_state=20261021+k,algorithm='lloyd').fit(x[:,None],sample_weight=weights)
  means=np.sort(model.cluster_centers_.ravel());bounds=(means[:-1]+means[1:])/2;label=np.searchsorted(bounds,x,side='left');sse=float(np.sum(weights*(x-means[label])**2));sizes=np.bincount(label[weights>0],minlength=k)
  curve.append({'K':k,'sse':sse,'positive_provider_class_counts':sizes.tolist(),'centroid_logMi_json':json.dumps(means.tolist())});fits[k]=(means,bounds,label)
 return curve,elbow(curve),fits

def source_binding():
 handoff=BASE/'model_inputs_cycle07/cycle07_source_mass_pool_admitted_handoff.json';h=json.loads(handoff.read_text());paths=[handoff,BASE/h['paths']['all173864_provider_eligibility'],BASE/h['paths']['fixed_own_mass'],BASE/h['paths']['effective_full_nodes'],BASE/h['independent_admission_path'],HERE/'PROTOCOL.json',Path(__file__),BASE/'model/cycle07_scale_hierarchy/empirical_registry_source477_v1/all_empirical_raw_units.parquet',BASE/'reviews/cycle07_empirical_registry_independent/audit.json']
 for key in ['all173864_provider_eligibility','fixed_own_mass','effective_full_nodes']:
  if sha(BASE/h['paths'][key])!=h['sha256'][key]:raise ValueError('admittedsource changed')
 admit=json.loads((BASE/h['independent_admission_path']).read_text())
 if admit.get('all_checks_passed')is not True:raise ValueError('source not independentlyadmitted')
 return {'status':'PREPARED_SOURCE_ONLY_NO_CLUSTER_METRICS','code_sha256':sha(Path(__file__)),'protocol_sha256':sha(HERE/'PROTOCOL.json'),'source_pins':{str(p):sha(p)for p in paths}}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--prepare-only',action='store_true');ap.add_argument('--output',type=Path,required=True);ap.add_argument('--admission',type=Path);a=ap.parse_args();out=a.output;bind=source_binding()
 if a.prepare_only:
  if out.exists():raise ValueError('freshoutputrequired')
  out.mkdir(parents=True);(out/'pre_execution_binding.json').write_text(json.dumps(bind,indent=2));return
 if json.loads((out/'pre_execution_binding.json').read_text())!=bind:raise ValueError('sourcebinding changed')
 ad=json.loads(a.admission.read_text())
 if ad.get('all_checks_passed')is not True or ad.get('accepted_pre_execution_binding_sha256')!=sha(out/'pre_execution_binding.json'):raise ValueError('independent exact admission required')
 if(out/'receipt.json').exists():raise ValueError('immutablecompletedoutput')
 start=time.monotonic();h=json.loads((BASE/'model_inputs_cycle07/cycle07_source_mass_pool_admitted_handoff.json').read_text());d=pd.read_parquet(BASE/h['paths']['all173864_provider_eligibility']);d=d.loc[d.eligible_source_provider.fillna(False)].sort_values('id').reset_index(drop=True);ctx=d.documented_external_context_anchor.fillna(False);ordinary=d.loc[~ctx].copy().reset_index(drop=True)
 if len(d.loc[ctx])!=2 or ordinary.id.duplicated().any():raise ValueError('invalideligible source identity/scope')
 if not np.isfinite(ordinary.own_positive_mass).all() or not ordinary.own_positive_mass.gt(0).all():raise ValueError('invalid fixed ownMi')
 assert d.loc[ctx,'id'].isin(['ctx:RU-FED-MOW','ctx:RU-FED-SPB']).all() and len(d.loc[ctx])==2
 x=np.log(ordinary.own_positive_mass.to_numpy(float));assert np.isfinite(x).all();weights=np.ones(len(x));curve,base,fits=fit_spectrum(x,weights);pd.DataFrame(curve).to_parquet(out/'baseline_allK_scree.parquet',index=False)
 regions=sorted(ordinary.region.dropna().astype(str).unique());codes=pd.Categorical(ordinary.region.astype(str),categories=regions).codes;assert(codes>=0).all();rng=np.random.default_rng(20261021);boot=[];allcurves=[];bounds=[];ar=[]
 for rep in range(50):
  draw=rng.multinomial(len(regions),np.full(len(regions),1/len(regions)));w=draw[codes].astype(float);c,e,f=fit_spectrum(x,w);same=base.get('K')is not None and e.get('K')==base['K'];positive=w>0;ari=float(adjusted_rand_score(fits[base['K']][2][positive],f[e['K']][2][positive]))if same else None
  if same:bounds.append(f[e['K']][1]);ar.append(ari)
  boot.append({'replicate_id':rep,**e,'same_baseline_K':same,'ari_positive_weight_providers':ari,'n_positive_weight_providers':int(positive.sum()),'region_weights_json':json.dumps(draw.tolist())});allcurves.extend({'replicate_id':rep,**r}for r in c)
 pd.DataFrame(boot).to_parquet(out/'all50_region_stability.parquet',index=False);pd.DataFrame(allcurves).to_parquet(out/'all500_replicate_K_curves.parquet',index=False)
 bIQR=(np.quantile(bounds,.75,axis=0)-np.quantile(bounds,.25,axis=0))/(x.max()-x.min())if bounds else np.array([]);accepted=base.get('K')is not None and len(ar)>=40 and np.median(ar)>=.8 and np.quantile(ar,.1)>=.6 and (bIQR<=.15).all()
 ordinary['intrinsic_centrality_class']=pd.array(fits[base['K']][2]if accepted else[None]*len(ordinary),dtype='Int64');ordinary['intrinsic_class_scope']='ordinary_eligible_source_provider';ordinary['functional_order_status']='UNASSIGNED';ordinary['class_status']='conditionally_stable_engineering_classes'if accepted else'UNASSIGNED_no_stable_empirical_elbow'
 groups={'education':['physical_education_positive_witness','physical_higher_education_positive_witness','physical_preschool_positive_witness'],'health':['physical_healthcare_positive_witness','physical_hospital_positive_witness'],'trade':['physical_trade_positive_witness'],'finance':['physical_finance_positive_witness'],'physical_administration':['physical_administration_positive_witness']}
 for name,cols in groups.items():ordinary['observed_positive_'+name]=ordinary[cols].fillna(False).any(axis=1)
 ordinary['observed_positive_institution_domain_breadth']=ordinary[['observed_positive_'+k for k in groups]].sum(axis=1);ordinary['breadth_zero_is_NOT_absence']=True;external=d.loc[ctx].copy();external['intrinsic_centrality_class']=pd.array([None]*len(external),dtype='Int64');external['intrinsic_class_scope']='external_context_unfitted_noncomparable_mass_proxy';external['functional_order_status']='UNASSIGNED';external['class_status']='SEPARATE_EXTERNAL_CONTEXT_OWN_P_UNKNOWN';pd.concat([ordinary,external],ignore_index=True).to_parquet(out/'all_eligible_source_provider_classes.parquet',index=False)
 if accepted:pd.DataFrame({'boundary_after_class':np.arange(base['K']-1),'logMi_midpoint':fits[base['K']][1],'Mi_midpoint':np.exp(fits[base['K']][1]),'conditional_boundary_logrange_IQR':bIQR}).to_csv(out/'accepted_source_class_boundaries.csv',index=False)
 reg=BASE/'model/cycle07_scale_hierarchy/empirical_registry_source477_v1/all_empirical_raw_units.parquet';units=pd.read_parquet(reg,columns=['unit_id','empirical_level','core_id']);cross=units.merge(pd.concat([ordinary,external],ignore_index=True)[['id','intrinsic_centrality_class','intrinsic_class_scope','class_status']],left_on='core_id',right_on='id',how='left',validate='many_to_one');cross.to_parquet(out/'existing_resolution_unit_focal_class_crosswalk.parquet',index=False)
 if source_binding()!=bind:raise ValueError('source/code changed during fit')
 r={'status':'SOURCE_ONLY_INTRINSIC_CENTRALITY_CLASSES_COMPUTED_NO_FUNCTIONAL_ORDERS','n_ordinary_eligible_fit':len(ordinary),'n_external_unfitted':len(external),'baseline_elbow':base,'accepted_stable_classes':bool(accepted),'n_same_K_assessable_replicates':len(ar),'median_ARI':float(np.median(ar))if ar else None,'p10_ARI':float(np.quantile(ar,.1))if ar else None,'boundary_IQR_fraction_logrange':bIQR.tolist(),'seconds':time.monotonic()-start,'geographic_partitions_not_changed':True,'institutionbreadth_not_fitted':True,'population_bins_not_fitted':True,'pre_execution_binding_sha256':sha(out/'pre_execution_binding.json'),'independent_admission_sha256':sha(a.admission),'crosswalk_registry_unit_source_sha256':sha(reg),'files':{p.name:sha(p)for p in out.iterdir()if p.is_file()}};(out/'receipt.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))
if __name__=='__main__':main()
