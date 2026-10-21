#!/usr/bin/env python3
"""Re-link frozen 2021 source objects; reads no model results or agreements."""
from pathlib import Path
import argparse,hashlib,json,re,unicodedata,time
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
AXIS=ROOT/'data/source_controls_cycle05/full_settlement_axis_cycle05_federal_children.parquet'
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def xyz(a,b):
 a=np.radians(a);b=np.radians(b);return np.column_stack((np.cos(a)*np.cos(b),np.cos(a)*np.sin(b),np.sin(a)))
def distance(v):return 12742.0176*np.arcsin(np.clip(v/2,0,1))
def en(x):return re.sub(r'[^а-яa-z0-9]+',' ',str(x).lower().replace('ё','е')).strip()
def mn(x):
 if pd.isna(x):return ''
 s=unicodedata.normalize('NFKC',str(x)).lower().replace('ё','е');s=re.sub(r'^(город|г\.|село|с\.|деревня|д\.|пос[её]лок|п\.|пгт\.?|рп\.?|станица|ст-ца)\s*','',s);return re.sub('[^a-zа-я0-9]','',s)
def links(d,axis,medical=False):
 valid=np.isfinite(axis.lat)&np.isfinite(axis.lon)&axis.population_2021.notna()&axis.is_additive_source_unit.eq(True)&~axis.axis_kind.fillna('').str.contains('territory',case=False)
 ref=axis[valid].reset_index(drop=True);coords=xyz(ref.lat.values,ref.lon.values);tree=cKDTree(coords);ids=ref.id.to_numpy();names=ref.name.map(mn if medical else en).to_numpy()
 tags=[json.loads(x or '{}') for x in d.tags_json];keys=['addr:city','addr:village','addr:hamlet'] if medical else ['addr:city','addr:village','addr:hamlet','addr:place','is_in:city']
 local=[next((t[k] for k in keys if t.get(k)),None) for t in tags]
 literal=np.array([mn(x) if medical else re.sub(r'^(город|село|деревня|поселок|г|с|д|п)\s+','',en(x)) if x else '' for x in local],dtype=object)
 geom=np.isfinite(d.lat)&np.isfinite(d.lon)&d.lat.between(-90,90)&d.lon.between(-180,180);gi=np.flatnonzero(geom);pts=xyz(d.loc[geom,'lat'].values,d.loc[geom,'lon'].values)
 dd,ii=tree.query(pts,k=2,workers=1);dd=distance(dd);n=len(d)
 nearest=np.full(n,None,object);nd=np.full(n,np.nan);sd=nd.copy();nearname=np.full(n,'',object);nearest[gi]=ids[ii[:,0]];nd[gi]=dd[:,0];sd[gi]=dd[:,1];nearname[gi]=names[ii[:,0]]
 base=np.full(n,None,object);conditional=base.copy();candidate=base.copy();linked=np.full(n,np.nan);status=np.full(n,'unlocated_source',object)
 status[gi]='no_accepted_source_locality_link' if medical else 'unresolved_no_locality_identity'
 byname={k:np.asarray(v) for k,v in ref.groupby(pd.Series(names)).indices.items()};radius=10 if medical else 5
 # A same-name KD tree gives the same <=radius candidate set multiplicity as the original full ball query.
 for key,indices in pd.Series(literal[gi],index=gi).groupby(literal[gi],sort=False).groups.items():
  if not key:continue
  ix=np.asarray(indices);rr=byname.get(key)
  status[ix]='no_accepted_source_locality_link' if medical else 'explicit_locality_not_resolved_within5km'
  if rr is None:continue
  pp=xyz(d.loc[ix,'lat'].values,d.loc[ix,'lon'].values);sub=cKDTree(coords[rr]);v,j=sub.query(pp,k=2);v=distance(v);found=v[:,0]<=radius;amb=found&(v[:,1]<=radius);unique=found&~amb
  status[ix[amb]]='address_locality_homonym_conflict' if medical else 'ambiguous_same_address_locality'
  for q in np.flatnonzero(unique):
   row=ix[q];uid=ids[rr[j[q,0]]];dist=float(v[q,0]);linked[row]=dist
   if medical and dist>5:conditional[row]=uid;status[row]='exact_source_address_locality_unique_within10km_distance5to10km'
   else:base[row]=uid;status[row]='exact_source_address_locality_unique_within10km_distance_le5km' if medical else 'explicit_address_locality_unique_within5km'
 if medical:
  candidate[geom&(nd<=10)]=nearest[geom&(nd<=10)]
  free=geom&pd.isna(base)&pd.isna(conditional)&(status!='address_locality_homonym_conflict')
  status[free&(nd>10)]='outside10km_reference_candidate_radius'
  conflict=(literal!='')&(literal!=nearname)
  status[free&(nd<=10)]='coordinate_candidate_le10km_not_identity_accepted'
  strong=(nd<=1)&((sd>=2*np.maximum(nd,.05))|(sd-nd>=1))
  status[free&strong]='strong_coordinate_candidate_le1km_not_identity_accepted'
  status[free&(nd<=10)&conflict]='source_address_locality_conflicts_with_nearest_candidate'
 else:
  pick=geom&pd.isna(base)&(nd<=2.5)&(sd>=np.maximum(nd*1.5,nd+.25))&((literal=='')|(literal==nearname))&~np.isin(literal,['москва','санкт петербург','санктпетербург','севастополь'])
  candidate[pick]=nearest[pick];linked[pick]=nd[pick];status[pick]='spatial_candidate_within2_5km_separated_not_identity_proof'
 result={'baseline_uid':base,'conditional_uid' if medical else 'candidate_uid':conditional if medical else candidate,'link_status':status,'nearest_distance_km':nd,'second_nearest_distance_km':sd,'source_address_locality':local,'nearest_id_unaccepted' if medical else 'nearest_uid_unaccepted':nearest}
 if medical:result['coordinate_candidate_uid']=candidate
 else:result['linked_distance_km']=linked
 for k,v in result.items():
  if k in d:d['previous_axis_'+k]=d[k]
  d[k]=v
 d['current2021_reference_only']=True
 return d,int(valid.sum())
def count_policy(d,canonical,channels,eligible):
 """Single global identity per canonical site; baseline precedes sensitivity channels."""
 remaining=set(d.loc[eligible,canonical]);conflicts=[]
 for mode,col in channels:
  out='count_'+mode+'_uid';d[out]=None
  a=d.loc[eligible&d[canonical].isin(remaining)&d[col].notna(),[canonical,col]].drop_duplicates()
  nu=a.groupby(canonical)[col].nunique();bad=set(nu[nu>1].index);good=set(nu[nu==1].index)
  pick=eligible&d[canonical].isin(good)&d[col].notna();d.loc[pick,out]=d.loc[pick,col]
  for c in bad:conflicts.append({'canonical_site_id':c,'channel':mode,'uids':json.dumps(a.loc[a[canonical].eq(c),col].tolist()),'decision':'exclude_canonical_all_channels_no_identity_guess'})
  remaining-=bad|good
 allc=pd.concat([d[[canonical,'count_'+m+'_uid']].rename(columns={'count_'+m+'_uid':'uid'}).dropna() for m,_ in channels]);assert allc.groupby(canonical).uid.nunique().le(1).all()
 return pd.DataFrame(conflicts,columns=['canonical_site_id','channel','uids','decision'])
def counts(f,a,key,canonical,col):
 s=a.drop_duplicates([key,canonical]).groupby(key).size();f[col]=f.id.map(s).fillna(0).astype('int32')
def run(family):
 t=time.monotonic();medical=family=='medical';p=ROOT/({'education':'education_cycle05/education_objects_2021_repaired.parquet','commerce':'commerce_cycle05/services_2021_objects_repaired.parquet','medical':'medical/history_20210101/osm_medical_inventory.parquet'}[family]);inputs={str(p):sha(p),str(AXIS):sha(AXIS)};axis=pd.read_parquet(AXIS);d=pd.read_parquet(p)
 if medical:
  q=ROOT/'validation/cycle05_medical/osm_quality_v2/all64976_medical_object_quality_sidecar.parquet';inputs[str(q)]=sha(q);side=pd.read_parquet(q);cols=['object_id','revised_broad_function','predicate_review_reason','source_site_canonical_object_id'];d=d.merge(side[cols],on='object_id',validate='one_to_one')
  # Preserve source canonical IDs, but apply source-proven multipolygon geometry identity globally for counting.
  ep=ROOT/'validation/cycle05_medical/osm_quality_v2/medical_relation_member_object_audit.parquet';inputs[str(ep)]=sha(ep);edges=pd.read_parquet(ep);parent={k:k for k in d.object_id}
  def find(k):
   while parent[k]!=k:k=parent[k]
   return k
  for e in edges[edges.source_geometry_duplicate_assertion].itertuples(index=False):parent[find(e.member_object_id)]=find(e.parent_object_id)
  d['count_canonical_site_id']=d.object_id.map(lambda x:find(x));canonical='count_canonical_site_id';eligible=~d.inactive_source_assertion
 else:canonical='canonical_site_id';eligible=d.count_eligible.fillna(False)
 d,nref=links(d,axis,medical);channels=[('baseline','baseline_uid')]+([('conditional_additional','conditional_uid'),('coordinate_candidate','coordinate_candidate_uid')] if medical else [('candidate_additional','candidate_uid')]);conf=count_policy(d,canonical,channels,eligible)
 f=axis[['id','name','type','region','lat','lon']].copy()
 if medical:
  # A name assertion never overrides an explicit pharmacy/dental/nonclinical source tag.
  d['repaired_medical_class']=d.medical_class
  for group,cls in [('dentistry','dentist_source_tag'),('pharmacy','pharmacy_source_tag')]:d.loc[d.revised_broad_function.eq(group),'repaired_medical_class']=cls
  d.loc[~d.revised_broad_function.isin(['healthcare','dentistry','pharmacy']),'repaired_medical_class']='unverified_or_nonclinical_source_object'
  classes=sorted(set(d.medical_class)|set(d.repaired_medical_class))
  for mode,col in channels:
   key='count_'+mode+'_uid';a=d[eligible&d[key].notna()]
   for cls in classes:counts(f,a[a.repaired_medical_class.eq(cls)],key,canonical,f'medical_osm_{mode}_{cls}_count')
   counts(f,a,key,canonical,f'medical_osm_{mode}_all_sites_count')
   for g in sorted(d.revised_broad_function.unique()):counts(f,a[a.revised_broad_function.eq(g)],key,canonical,f'medical_osm_{mode}_typed_{g}_sites_count')
   counts(f,a[a.revised_broad_function.eq('healthcare')],key,canonical,f'medical_osm_{mode}_healthcare_sites_count')
   counts(f,a[a.revised_broad_function.isin(['healthcare','dentistry'])],key,canonical,f'medical_osm_{mode}_general_and_dental_clinical_sites_count')
   hospital=a[a.revised_broad_function.eq('healthcare')&((a.amenity=='hospital')|(a.healthcare=='hospital'))];counts(f,hospital,key,canonical,f'medical_osm_{mode}_explicit_hospital_sites_count')
   generic=a[a.predicate_review_reason.eq('explicit_generic_healthcare_yes_unspecified_clinical_level')];counts(f,generic,key,canonical,f'medical_osm_{mode}_generic_healthcare_yes_unspecified_level_sites_count')
   explicit=a[a.predicate_review_reason.eq('positive_human_healthcare_function_tag_including_documented_legacy_enum')];counts(f,explicit,key,canonical,f'medical_osm_{mode}_explicit_clinical_function_sites_count')
  a=d[eligible&d.count_coordinate_candidate_uid.notna()&d.link_status.eq('strong_coordinate_candidate_le1km_not_identity_accepted')&d.revised_broad_function.eq('healthcare')];counts(f,a,'count_coordinate_candidate_uid',canonical,'medical_osm_strong_coordinate_candidate_healthcare_sites_count')
  f['medical_osm_no_accepted_record_does_not_mean_no_service']=True;f['medical_source_snapshot_date']='2021-01-01';f['medical_osm_complete_extract']=True
 else:
  groupcol='education_group' if family=='education' else 'service_group';prefix='education_osm2021' if family=='education' else 'services_osm2021'
  for group in sorted(d[groupcol].unique()):
   for mode,col in channels:
    key='count_'+mode+'_uid';a=d[eligible&d[key].notna()&d[groupcol].eq(group)];d['count_'+mode+'_eligible']=eligible&d[key].notna();counts(f,a,key,canonical,f'{prefix}_{group}_{mode}_count')
    if family=='education':
     v=pd.to_numeric(a.source_capacity,errors='coerce');b=a.assign(_v=v.where(v.ge(0))).groupby([key,canonical])._v.max().reset_index();b=b[b._v.notna()];f[f'{prefix}_{group}_{mode}_capacity_observed_campuses']=f.id.map(b.groupby(key).size()).fillna(0).astype('int32');f[f'{prefix}_{group}_{mode}_partial_capacity_sum']=f.id.map(b.groupby(key)._v.sum(min_count=1))
   total=f[f'{prefix}_{group}_baseline_count']+f[f'{prefix}_{group}_candidate_additional_count'];f[f'{prefix}_{group}_observed_presence']=pd.array(np.where(total>0,True,None),dtype='boolean')
  f[family+'_cycle05_source_version']='repaired_2021_relinked_current_axis_v2'
  if family=='education':f['education_history_comparison_scope']='2021 mapped node/way/relation assertions; absence and snapshot change are not physical absence/closure; no census completeness'
  else:
   f['service_absence_means_unknown']=True;f['service_cycle05_source_version']='repaired_2021_relinked_current_axis_v2';f['service_source_scope']='2021-01-01 historical node/way/relation assertions; no census completeness, source absence is unknown function'
 oldaxis=pd.read_parquet(ROOT/'axis/full_settlement_axis.parquet',columns=['id']);newids=set(axis.id)-set(oldaxis.id);d['baseline_changed_from_previous_axis']=d.baseline_uid.fillna('').ne(d.previous_axis_baseline_uid.fillna(''))
 output=OUT/family;output.mkdir(exist_ok=True)
 comparison=[]
 for group,a in d[eligible].groupby('revised_broad_function' if medical else groupcol):
  before=a[a.previous_axis_baseline_uid.notna()].drop_duplicates(['previous_axis_baseline_uid',canonical]).groupby('previous_axis_baseline_uid').size()
  after=a[a.count_baseline_uid.notna()].drop_duplicates(['count_baseline_uid',canonical]).groupby('count_baseline_uid').size()
  union=before.index.union(after.index)
  for uid in union:
   old=int(before.get(uid,0));new=int(after.get(uid,0))
   if old!=new:comparison.append({'id':uid,'group':group,'previous_axis_eligible_canonical_baseline_count':old,'new_axis_eligible_canonical_baseline_count':new,'difference':new-old,'is_new335':uid in newids})
 pd.DataFrame(comparison).to_parquet(output/'baseline_count_changes.parquet',index=False)
 d.to_parquet(output/'source_objects_relinked.parquet',index=False,compression='zstd');f.to_parquet(output/'settlement_features_full_axis.parquet',index=False,compression='zstd');conf.to_parquet(output/'canonical_conflicts.parquet',index=False);d.loc[d.baseline_changed_from_previous_axis].to_parquet(output/'changed_baseline_links.parquet',index=False,compression='zstd');f[f.id.isin(newids)].to_parquet(output/'new335_features.parquet',index=False)
 receipt={'family':family,'axis_rows':len(axis),'reference_rows':nref,'source_rows':len(d),'new_axis_ids':len(newids),'new335_strict_source_rows':int(d.count_baseline_uid.isin(newids).sum()),'new335_strict_positive_NPs':int(d.loc[d.count_baseline_uid.isin(newids),'count_baseline_uid'].nunique()),'changed_baseline_raw_objects':int(d.baseline_changed_from_previous_axis.sum()),'canonical_conflicts':len(conf),'single_canonical_one_counted_UID_check':True,'inputs':inputs,'outputs':{p.name:sha(p) for p in output.glob('*.parquet')},'code_sha256':sha(Path(__file__)),'reference_policy':'finite coordinates & own population2021 observed & additive source unit & !territory; root expressly approved prior to comparison','medical_coordinate_counts':'ADDITIONAL ONLY after strict/conditional canonical precedence; raw nearest coordinate_candidate_uid diagnostic preserved','source_objects_are_not_verified_operating_census':True,'model_assignments_or_agreements_read':False,'seconds':round(time.monotonic()-t,2)}
 assert all(sha(Path(k))==v for k,v in inputs.items());(output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k not in ['inputs','outputs']},ensure_ascii=False),flush=True)
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--family',choices=['education','commerce','medical','all'],default='all');v=a.parse_args();
 for family in (['education','commerce','medical'] if v.family=='all' else [v.family]):run(family)
