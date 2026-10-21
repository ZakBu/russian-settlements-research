#!/usr/bin/env python3
"""Independent haversine BallTree and full-radius source linkage/count replay.
Does not import the producer or read model predictions. Unit is source assertion;
canonical identity receives at most one counting locality across all channels.
"""
from pathlib import Path
import pandas as pd,numpy as np,json,re,unicodedata,hashlib,datetime
from sklearn.neighbors import BallTree
HERE=Path(__file__).resolve().parent;BASE=HERE.parents[1];TARGET=BASE/'model_inputs_cycle07/institutional_relink477_v1';R=6371.0088
checks=[];summary={}
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb')as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def ck(n,v,detail=None):
 checks.append({'check':n,'pass':bool(v),'detail':detail})
 if not v:print('FAILED',n,str(detail)[:1000],flush=True)
def same(a,b):return pd.Series(a).astype(object).fillna('<NA>').astype(str).equals(pd.Series(b).astype(object).fillna('<NA>').astype(str))
def clean(s,medical=False):
 if s is None or pd.isna(s):return ''
 s=unicodedata.normalize('NFKC',str(s)) if medical else str(s)
 s=s.lower().replace('ё','е')
 if medical:
  s=re.sub(r'^(город|г\.|село|с\.|деревня|д\.|пос[её]лок|п\.|пгт\.?|рп\.?|станица|ст-ца)\s*','',s)
  return re.sub('[^a-zа-я0-9]','',s)
 return re.sub('[^а-яa-z0-9]+',' ',s).strip()
def eqarray(a,b):return np.allclose(np.asarray(a,dtype=float),np.asarray(b,dtype=float),atol=1e-7,rtol=1e-9,equal_nan=True)
manifest=json.loads((TARGET/'source_freeze_manifest.json').read_text());initial_manifest_sha=sha(TARGET/'source_freeze_manifest.json')
for p,h in manifest['files_sha256'].items():ck('frozen_output_sha:'+p,sha(BASE/p)==h)
axis=pd.read_parquet(TARGET/'settlement_axis_2021_coordinate477.parquet')
patch=pd.read_parquet(BASE/'source_geography_recovery_cycle07/approved_coordinate_patch.parquet');newids=set(patch.id)
valid=np.isfinite(axis.lat)&np.isfinite(axis.lon)&axis.population_2021.notna()&axis.is_additive_source_unit.eq(True)&~axis.axis_kind.fillna('').str.contains('territory',case=False)
ref=axis[valid].reset_index(drop=True);tree=BallTree(np.radians(ref[['lat','lon']].to_numpy()),metric='haversine')
ck('axis173862_reference154609_new477',len(axis)==173862 and axis.id.is_unique and len(ref)==154609 and len(newids)==477)
for fam,src in [('education','education_cycle05/education_objects_2021_repaired.parquet'),('commerce','commerce_cycle05/services_2021_objects_repaired.parquet'),('medical','medical/history_20210101/osm_medical_inventory.parquet')]:
 print('START',fam,flush=True);medical=fam=='medical';orig=pd.read_parquet(BASE/src);d=pd.read_parquet(TARGET/fam/'source_objects_relinked.parquet');f=pd.read_parquet(TARGET/fam/'settlement_features_full_axis.parquet');receipt=json.loads((TARGET/fam/'receipt.json').read_text());n=len(d)
 ck(fam+':all_original_rows',len(d)==len(orig) and (d.osm_id.tolist()==orig.osm_id.tolist()) and same(d.osm_type,orig.osm_type))
 mutated=[]
 
 for fp,fh in receipt['inputs'].items():ck(fam+':actual_input_sha:'+fp,sha(fp)==fh)
 for fp,fh in receipt['outputs'].items():ck(fam+':actual_output_sha:'+fp,sha(TARGET/fam/fp)==fh)
 # Every source column is unchanged or explicitly preserved under previous_axis_.
 linkcols=['baseline_uid','candidate_uid','conditional_uid','coordinate_candidate_uid','link_status','nearest_distance_km','second_nearest_distance_km','source_address_locality','nearest_uid_unaccepted','nearest_id_unaccepted','linked_distance_km']
 skip=['current2021_reference_only','count_baseline_eligible','count_candidate_additional_eligible']
 for col in orig:
  target='previous_axis_'+col if col in linkcols else col
  if col in skip:continue
  try:pd.testing.assert_series_equal(orig[col].reset_index(drop=True),d[target].reset_index(drop=True),check_names=False)
  except AssertionError:mutated.append(col)
 ck(fam+':all_source_and_previous_link_fields_preserved',not mutated,mutated)
 ts=[json.loads(x or '{}')for x in orig.tags_json];keys=['addr:city','addr:village','addr:hamlet']+([]if medical else['addr:place','is_in:city'])
 loc=[next((t[k]for k in keys if t.get(k)),None)for t in ts]
 lit=[clean(x,medical)for x in loc]
 if not medical:lit=[re.sub(r'^(город|село|деревня|поселок|г|с|д|п)\s+','',s)for s in lit]
 names=ref.name.map(lambda x:clean(x,medical)).to_numpy();geom=np.isfinite(d.lat)&np.isfinite(d.lon)&d.lat.between(-90,90)&d.lon.between(-180,180);gi=np.flatnonzero(geom)
 distances,nearest_ix=tree.query(np.radians(d.loc[geom,['lat','lon']].to_numpy()),k=2);distances*=R
 nd=np.full(n,np.nan);sd=nd.copy();near=np.full(n,None,object);nearname=np.full(n,'',object);nd[gi]=distances[:,0];sd[gi]=distances[:,1];near[gi]=ref.id.to_numpy()[nearest_ix[:,0]];nearname[gi]=names[nearest_ix[:,0]]
 ck(fam+':all_haversine_first_second_distances',eqarray(nd,d.nearest_distance_km)and eqarray(sd,d.second_nearest_distance_km))
 nearcol='nearest_id_unaccepted'if medical else'nearest_uid_unaccepted'
 tie_ix=np.flatnonzero(pd.Series(near).fillna('').ne(d[nearcol].fillna('')))
 # Different nearest algorithms may choose different members of exact-distance ties.
 # Prove the source-selected diagnostic is itself a haversine minimizer; keep
 # independently selected IDs for count-policy replay, so counted ambiguity fails.
 tie_ok=True
 for j in tie_ix:
  rr=ref[ref.id.eq(d.at[j,nearcol])]
  if len(rr)!=1:tie_ok=False;continue
  p0=np.radians(d.loc[j,['lat','lon']].to_numpy(dtype=float));p1=np.radians(rr[['lat','lon']].to_numpy(dtype=float)[0]);a=np.sin((p1[0]-p0[0])/2)**2+np.cos(p0[0])*np.cos(p1[0])*np.sin((p1[1]-p0[1])/2)**2;dist=2*R*np.arcsin(np.sqrt(a));tie_ok=tie_ok and abs(dist-nd[j])<1e-7
 ck(fam+':all_nearest_UID_haversine_or_verified_exact_tie',tie_ok,{'tied_diagnostic_UIDs':len(tie_ix)})
 base=np.full(n,None,object);cond=base.copy();cand=base.copy();linked=np.full(n,np.nan);status=np.full(n,'unlocated_source',object);status[gi]='no_accepted_source_locality_link'if medical else'unresolved_no_locality_identity'
 explicit=np.array([i for i in gi if lit[i]],dtype=int);rad=10 if medical else 5
 # Full-reference radius query, independent of producer's name-specific KD trees.
 balls,ball_distances=tree.query_radius(np.radians(d.loc[explicit,['lat','lon']].to_numpy()),r=rad/R,return_distance=True)
 ambiguous=0;unique=0
 for row,ix,ds in zip(explicit,balls,ball_distances):
  status[row]='no_accepted_source_locality_link'if medical else'explicit_locality_not_resolved_within5km'
  take=np.array([q for q,j in enumerate(ix)if names[j]==lit[row]],dtype=int)
  if len(take)>1:status[row]='address_locality_homonym_conflict'if medical else'ambiguous_same_address_locality';ambiguous+=1
  elif len(take)==1:
   q=take[0];uid=ref.id.iloc[ix[q]];dist=ds[q]*R;linked[row]=dist;unique+=1
   if medical and dist>5:cond[row]=uid;status[row]='exact_source_address_locality_unique_within10km_distance5to10km'
   else:base[row]=uid;status[row]='exact_source_address_locality_unique_within10km_distance_le5km'if medical else'explicit_address_locality_unique_within5km'
 la=np.array(lit,object)
 if medical:
  cand[geom&(nd<=10)]=near[geom&(nd<=10)];free=geom&pd.isna(base)&pd.isna(cond)&(status!='address_locality_homonym_conflict');status[free&(nd>10)]='outside10km_reference_candidate_radius';status[free&(nd<=10)]='coordinate_candidate_le10km_not_identity_accepted';strong=(nd<=1)&((sd>=2*np.maximum(nd,.05))|(sd-nd>=1));status[free&strong]='strong_coordinate_candidate_le1km_not_identity_accepted';status[free&(nd<=10)&(la!='')&(la!=nearname)]='source_address_locality_conflicts_with_nearest_candidate'
 else:
  pick=geom&pd.isna(base)&(nd<=2.5)&(sd>=np.maximum(nd*1.5,nd+.25))&((la=='')|(la==nearname))&~np.isin(la,['москва','санкт петербург','санктпетербург','севастополь']);cand[pick]=near[pick];linked[pick]=nd[pick];status[pick]='spatial_candidate_within2_5km_separated_not_identity_proof'
 for col,values in [('baseline_uid',base),('conditional_uid',cond)]if medical else[('baseline_uid',base),('candidate_uid',cand)]:ck(fam+':full_radius_'+col,same(values,d[col]))
 if medical:
  rawcand=np.where(geom&(nd<=10),d.nearest_id_unaccepted.to_numpy(),None)
  ck(fam+':coordinate_raw_candidate_is_verified_nearest_diagnostic',same(rawcand,d.coordinate_candidate_uid))
  exacttie=np.isfinite(nd)&np.isfinite(sd)&(np.abs(sd-nd)<=1e-7)
  ck('medical:all_exact_nearest_tie_flags_recomputed',np.array_equal(exacttie,d.coordinate_nearest_distance_tie_ambiguous))
  tielist_ok=True
  for row in np.flatnonzero(exacttie):
   pp=np.radians(d.loc[[row],['lat','lon']].to_numpy(float));ix,ds=tree.query_radius(pp,r=(nd[row]+1e-7)/R,return_distance=True);possible=set(ref.id.iloc[ix[0][np.abs(ds[0]*R-nd[row])<=1e-7]])
   tielist_ok=tielist_ok and possible==set(json.loads(d.at[row,'coordinate_tied_possible_uid_json']))
  ck('medical:all195_full_haversine_ball_tied_UID_sets',tielist_ok,{'all_tied_assertions':int(exacttie.sum())})
  cand[exacttie]=None

 else:ck(fam+':all_linked_distances',eqarray(linked,d.linked_distance_km))
 ck(fam+':all_link_statuses',same(status,d.link_status));ck(fam+':all_address_literals_actual_tags',same(loc,d.source_address_locality))
 if medical:
  side=pd.read_parquet(BASE/'validation/cycle05_medical/osm_quality_v3/all64976_medical_object_quality_sidecar.parquet').set_index('object_id');ck('medical:classified_source_same_accepted_v3',all(same(d[c],d.object_id.map(side[c]))for c in ['revised_broad_function','predicate_review_reason','source_site_canonical_object_id']))
  edges=pd.read_parquet(BASE/'validation/cycle05_medical/osm_quality_v3/medical_relation_member_object_audit.parquet');parent=dict(zip(d.object_id,d.object_id))
  def find(x):
   while parent[x]!=x:x=parent[x]
   return x
  for e in edges[edges.source_geometry_duplicate_assertion].itertuples():parent[find(e.member_object_id)]=find(e.parent_object_id)
  canon=d.object_id.map(lambda x:find(x));ck('medical:global_geometric_identity_preserves_sourcecanonical',same(canon,d.count_canonical_site_id));eligible=~d.inactive_source_assertion.to_numpy();channels=[('baseline',base),('conditional_additional',cond),('coordinate_candidate',cand)]
 else:canon=d.canonical_site_id;eligible=d.count_eligible.fillna(False).to_numpy();channels=[('baseline',base),('candidate_additional',cand)]
 unresolved=set(canon[eligible]);countuids={};conflicts=[]
 for mode,uids in channels:
  a=pd.DataFrame({'canon':canon,'uid':uids});a=a[eligible&a.canon.isin(unresolved)&a.uid.notna()].drop_duplicates();sizes=a.groupby('canon').uid.nunique();bad=set(sizes[sizes>1].index);good=set(sizes[sizes==1].index);expected=np.full(n,None,object);sel=eligible&canon.isin(good)&pd.notna(uids);expected[sel]=uids[sel];countuids[mode]=expected;ck(fam+':global_precedence_'+mode,same(expected,d['count_'+mode+'_uid']));unresolved-=good|bad;conflicts.extend(bad)
 
 if medical:ck('medical:no_ambiguous_tie_counted_as_coordinate_identity',d.loc[exacttie,'count_coordinate_candidate_uid'].isna().all())
 ck(fam+':zero_canonical_conflicts',not conflicts and len(pd.read_parquet(TARGET/fam/'canonical_conflicts.parquet'))==0)
 alluids=pd.concat([pd.DataFrame({'canon':canon,'uid':v}).dropna()for v in countuids.values()]);ck(fam+':canonical_max_one_NP_all_channels',alluids.groupby('canon').uid.nunique().le(1).all())
 ck(fam+':axis_metadata_exact',f[['id','name','type','region','lat','lon']].equals(axis[['id','name','type','region','lat','lon']]))
 calc={};idx=f.id
 def count(col,mode,selection):
  a=pd.DataFrame({'uid':countuids[mode],'canon':canon});a=a[eligible&selection&a.uid.notna()].drop_duplicates();calc[col]=idx.map(a.groupby('uid').size()).fillna(0).to_numpy()
 if not medical:
  gc='education_group'if fam=='education'else'service_group';prefix='education_osm2021'if fam=='education'else'services_osm2021'
  for g in sorted(d[gc].unique()):
   for mode,_ in channels:
    selection=d[gc].eq(g).to_numpy();count(f'{prefix}_{g}_{mode}_count',mode,selection)
    if fam=='education':
     a=pd.DataFrame({'uid':countuids[mode],'canon':canon,'v':pd.to_numeric(d.source_capacity,errors='coerce')});a=a[eligible&selection&a.uid.notna()&a.v.ge(0)];a=a.groupby(['uid','canon']).v.max().reset_index();calc[f'{prefix}_{g}_{mode}_capacity_observed_campuses']=idx.map(a.groupby('uid').size()).fillna(0).to_numpy();calc[f'{prefix}_{g}_{mode}_partial_capacity_sum']=idx.map(a.groupby('uid').v.sum(min_count=1)).to_numpy()
   total=calc[f'{prefix}_{g}_baseline_count']+calc[f'{prefix}_{g}_candidate_additional_count'];ck(fam+':nullable_presence_'+g,same(pd.array(np.where(total>0,True,None),dtype='boolean'),f[f'{prefix}_{g}_observed_presence']))
 else:
  repaired=d.medical_class.copy();repaired[d.revised_broad_function.eq('dentistry')]='dentist_source_tag';repaired[d.revised_broad_function.eq('pharmacy')]='pharmacy_source_tag';repaired[~d.revised_broad_function.isin(['healthcare','dentistry','pharmacy'])]='unverified_or_nonclinical_source_object';ck('medical:typed_medical_class_not_name_override',same(repaired,d.repaired_medical_class))
  for mode,_ in channels:
   for c in sorted(set(d.medical_class)|set(repaired)):count(f'medical_osm_{mode}_{c}_count',mode,repaired.eq(c).to_numpy())
   count(f'medical_osm_{mode}_all_sites_count',mode,np.ones(n,bool))
   for g in sorted(d.revised_broad_function.unique()):count(f'medical_osm_{mode}_typed_{g}_sites_count',mode,d.revised_broad_function.eq(g).to_numpy())
   for suffix,selection in [('healthcare',d.revised_broad_function.eq('healthcare')),('general_and_dental_clinical',d.revised_broad_function.isin(['healthcare','dentistry'])),('explicit_hospital',d.revised_broad_function.eq('healthcare')&((d.amenity=='hospital')|(d.healthcare=='hospital'))),('generic_healthcare_yes_unspecified_level',d.predicate_review_reason.eq('explicit_generic_healthcare_yes_unspecified_clinical_level')),('explicit_clinical_function',d.predicate_review_reason.eq('positive_human_healthcare_function_tag_including_documented_legacy_enum'))]:count(f'medical_osm_{mode}_{suffix}_sites_count',mode,selection.to_numpy())
  count('medical_osm_strong_coordinate_candidate_healthcare_sites_count','coordinate_candidate',d.link_status.eq('strong_coordinate_candidate_le1km_not_identity_accepted').to_numpy()&d.revised_broad_function.eq('healthcare').to_numpy())
 mismatches=[c for c,v in calc.items()if c not in f or not eqarray(v,f[c])];ck(fam+':every_feature_count_capacity_all173862rows',not mismatches,{'recomputed_columns':len(calc),'mismatch_columns':mismatches})
 othernumeric=set(f.select_dtypes('number').columns)-{'lat','lon'}-set(calc);ck(fam+':no_unreviewed_numeric_features',not othernumeric,sorted(othernumeric))
 new=f[f.id.isin(newids)];ck(fam+':all335_feature_subset_exact',new.reset_index(drop=True).equals(pd.read_parquet(TARGET/fam/'new477_features.parquet').reset_index(drop=True)))
 v4=pd.read_parquet(BASE/'model_inputs_cycle05/relinked_v4'/fam/'source_objects_relinked.parquet'); changed=d.baseline_uid.fillna('').ne(v4.baseline_uid.fillna(''));ck(fam+':changed_baseline_flag_exact',same(changed,d.baseline_changed_from_previous_axis));ck(fam+':changed_baseline_rows_exact',d[changed].reset_index(drop=True).equals(pd.read_parquet(TARGET/fam/'changed_baseline_links.parquet').reset_index(drop=True)))
 ck(fam+':receipt_actual_counts',receipt['source_rows']==len(d)and receipt['reference_rows']==len(ref)and receipt['changed_baseline_raw_objects']==int(changed.sum())and receipt['new477_strict_source_rows']==int(pd.Series(countuids['baseline']).isin(newids).sum())and receipt['new477_strict_positive_NPs']==pd.Series(countuids['baseline'])[pd.Series(countuids['baseline']).isin(newids)].nunique())
 summary[fam]={'objects':n,'address_full_radius_queries':len(explicit),'ambiguous_address_objects':ambiguous,'unique_address_objects':unique,'numeric_feature_columns':len(calc),'new335_strict_rows':receipt['new477_strict_source_rows'],'new335_positive_NPs':receipt['new477_strict_positive_NPs'],'changed_baseline_objects':int(changed.sum())};print('DONE',fam,flush=True)
ck('source_freeze_manifest_unchanged_during_review',sha(TARGET/'source_freeze_manifest.json')==initial_manifest_sha)
for p,h in manifest['files_sha256'].items():ck('final_output_still_frozen:'+p,sha(BASE/p)==h)
result={'status':'ACCEPTED'if all(c['pass']for c in checks)else'REJECTED','all_checks_passed':all(c['pass']for c in checks),'n_checks':len(checks),'n_failed':sum(not c['pass']for c in checks),'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'independent_reviewer':'continuation_guardian; current linkage author education_functions_cycle05','source_manifest_sha256':initial_manifest_sha,'accepted_source_manifest_sha256':initial_manifest_sha,'audit_code_sha256':sha(Path(__file__)),'source_objects_summary':summary,'checks':checks,'model_predictions_read':False,'scope':'Current2021reference/all3sources/rawaddress and full-radius haversine replay, canonicalcount precedence/all173862countfeatures. Sourceclassification accepted separately; modelagreement not reviewed.'};(HERE/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps({k:result[k]for k in ['status','n_checks','n_failed','source_objects_summary']},ensure_ascii=False,indent=2))
