"""Finite positive thematic source relink to independently admitted new coordinates."""
from pathlib import Path
import json,hashlib,re,time
import numpy as np,pandas as pd
from sklearn.neighbors import BallTree
H=Path(__file__).resolve().parent;ROOT=H.parents[1];R=6371.0088;EPS=1e-7

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def norm(s):return re.sub('[^а-яa-z0-9]+',' ',str(s or'').casefold().replace('ё','е')).strip()
def main():
 start=time.monotonic();proto=json.loads((H/'preregistration.json').read_text());assert all(sha(ROOT/p)==s for p,s in proto['inputs_sha256'].items())
 axis=pd.read_parquet(ROOT/'data/source_controls_cycle05/full_settlement_axis_cycle05_federal_children.parquet');patch=pd.read_parquet(ROOT/'source_geography_recovery_cycle07/approved_coordinate_patch.parquet').set_index('id');assert len(patch)==477
 basegood=axis.population_2021.notna()&axis.is_additive_source_unit.fillna(False)&~axis.axis_kind.fillna('').str.contains('territory',case=False);oldref=axis[basegood&np.isfinite(axis[['lat','lon']].to_numpy(float)).all(axis=1)];assert len(oldref)==154132
 new=axis[axis.id.isin(patch.index)].copy();assert len(new)==477 and new[['lat','lon']].isna().all().all() and basegood.loc[new.index].all();new['lat']=new.id.map(patch.new_lat);new['lon']=new.id.map(patch.new_lon);new=new.sort_values('id').reset_index(drop=True);ref=pd.concat([oldref,new],ignore_index=True);assert len(ref)==154609 and ref.id.is_unique;ntree=BallTree(np.radians(new[['lat','lon']]),metric='haversine');ledger=[]
 def relink(z,family):
  z=z.copy();z['previous_nearest_axis_id']=z.nearest_axis_id;z['previous_nearest_distance_km']=z.nearest_distance_km;good=np.isfinite(z[['lat','lon']].to_numpy(float)).all(axis=1);dd,ii=ntree.query(np.radians(z.loc[good,['lat','lon']]),k=1);goodix=z.index[good]
  for idx,d,j in zip(goodix,dd[:,0]*R,ii[:,0]):
   row=z.loc[idx];old=float(row.nearest_distance_km) if pd.notna(row.nearest_distance_km) else np.inf
   if d>old+EPS:continue
   inds,ds=ntree.query_radius(np.radians([[row.lat,row.lon]]),r=(d+EPS)/R,return_distance=True);hits=sorted([{'id':new.id.iloc[k],'distance_km':float(v*R)} for k,v in zip(inds[0],ds[0])],key=lambda x:x['id']);chosen=hits[0];change=d<old-EPS
   if change:z.at[idx,'nearest_axis_id']=chosen['id'];z.at[idx,'nearest_distance_km']=chosen['distance_km']
   ledger.append({'family':family,'site_id':row.site_id,'canonical_site_id':row.canonical_site_id,'previous_uid':row.nearest_axis_id,'previous_distance_km':old if np.isfinite(old) else None,'new477_min_distance_km':float(d),'all_new477_minimum_ties_json':json.dumps(hits,ensure_ascii=False),'selected_uid':z.at[idx,'nearest_axis_id'],'selected_distance_km':z.at[idx,'nearest_distance_km'],'changed':bool(change),'old_owner_preserved_on_numerical_tie':bool(not change)})
  return z
 oldi=pd.read_parquet(ROOT/'typology2021_cycle05/industry_resource/settlement_industry_resource_features_2021.parquet');obj=relink(pd.read_parquet(ROOT/'typology2021_cycle05/industry_resource/industry_resource_objects_2021.parquet'),'industry_resource');sites=obj[obj.site_id.eq(obj.canonical_site_id)];fi=oldi.copy()
 for pred,col,lim in [('source_resource_predicate','osm_resource_site_geometries_within5km',5),('source_industrial_predicate','osm_industrial_geometries_within3km',3)]:
  for tab,cc in [(sites,col),(obj,col+'_raw_assertions')]:
   counts=tab[tab[pred]&tab.nearest_distance_km.le(lim)&~tab.inactive_source_asserted].groupby('nearest_axis_id').size();fi[cc]=fi.id.map(counts).fillna(0).astype('int32')
 for flag,col in [('mapped_resource_site_context_evidence','osm_resource_site_geometries_within5km'),('mapped_industrial_site_context_evidence','osm_industrial_geometries_within3km')]:fi[flag]=pd.array(np.where(fi[col].gt(0),True,None),dtype='boolean')
 obj.to_parquet(H/'industry_resource_objects_relinked.parquet',index=False);fi.to_parquet(H/'settlement_industry_resource_features_2021.parquet',index=False)
 oldr=pd.read_parquet(ROOT/'model_inputs_cycle05/thematic2021/settlement_recreation_features_full_axis.parquet');rec=relink(pd.read_parquet(ROOT/'model_inputs_cycle05/thematic2021/recreation_canonical_site_links.parquet'),'recreation');rec['count_eligible']=rec.nearest_distance_km.le(3)&~rec.inactive_source_asserted;fr=oldr.copy()
 for group,col in [('accommodation','osm_accommodation_points_within3km'),('allotments','osm_allotment_geometries_within3km')]:
  counts=rec[rec.count_eligible&rec.source_group.eq(group)].groupby('nearest_axis_id').size();fr[col]=fr.id.map(counts).fillna(0).astype('int32')
 for flag,col in [('recreation_facility_evidence','osm_accommodation_points_within3km'),('dacha_landuse_evidence','osm_allotment_geometries_within3km')]:fr[flag]=pd.array(np.where(fr[col].gt(0),True,None),dtype='boolean')
 fr['recreation_dacha_evidence']=pd.array(np.where(fr[['osm_accommodation_points_within3km','osm_allotment_geometries_within3km']].sum(axis=1).gt(0),True,None),dtype='boolean');rec.to_parquet(H/'recreation_canonical_site_links.parquet',index=False);fr.to_parquet(H/'settlement_recreation_features_2021.parquet',index=False)
 z=pd.read_parquet(ROOT/'typology2021_cycle05/own_function_rules/agro_processing_v1/literal_processing_source_assertions.parquet');tree=BallTree(np.radians(ref[['lat','lon']]),metric='haversine');names=ref.name.map(norm).to_numpy();links=[]
 for row in z.itertuples():
  t=json.loads(row.source_tags_json);local=next((t[k]for k in ['addr:city','addr:village','addr:hamlet','addr:place','is_in:city']if t.get(k)),None);lit=re.sub(r'^(город|село|деревня|поселок|г|с|д|п)\s+','',norm(local));hits=[];uid=None;dist=None;status='no_explicit_source_locality'
  if lit and np.isfinite(row.lat) and np.isfinite(row.lon):
   ix,ds=tree.query_radius(np.radians([[row.lat,row.lon]]),r=5/R,return_distance=True);hits=[{'id':ref.id.iloc[j],'name':ref.name.iloc[j],'type':ref.type.iloc[j],'distance_km':float(d*R)}for j,d in zip(ix[0],ds[0])if names[j]==lit];hits=sorted(hits,key=lambda h:h['id']);status='explicit_source_locality_unresolved_within5km'
   if len(hits)==1:uid=hits[0]['id'];dist=hits[0]['distance_km'];status='explicit_source_locality_unique_within5km'
   elif len(hits)>1:status='ambiguous_explicit_source_locality_homonyms'
  links.append((uid,dist,status,json.dumps(hits,ensure_ascii=False)))
 z['previous_strict_explicit_uid']=z.strict_explicit_uid;z['strict_explicit_uid']=[x[0]for x in links];z['strict_source_distance_km']=[x[1]for x in links];z['explicit_locality_link_status']=[x[2]for x in links];z['all_same_name_candidate_UIDs_json']=[x[3]for x in links];eligible=~z.explicit_lifecycle_or_nonoperating_source&~z.inactive_source_asserted;nu=z[eligible&z.strict_explicit_uid.notna()].groupby('canonical_site_id').strict_explicit_uid.nunique();z['canonical_explicit_identity_conflict']=z.canonical_site_id.isin(nu[nu>1].index);z['count_eligible_processing_witness']=eligible&z.strict_explicit_uid.notna()&~z.canonical_explicit_identity_conflict;z.to_parquet(H/'literal_processing_source_assertions.parquet',index=False)
 olda=pd.read_parquet(ROOT/'typology2021_cycle05/own_function_rules/agro_processing_v1/settlement_literal_agro_processing_evidence_2021.parquet');fa=olda.copy();cnt=z[z.count_eligible_processing_witness].drop_duplicates(['strict_explicit_uid','canonical_site_id']).groupby('strict_explicit_uid').size();col='own2021_strict_literal_agroprocessing_source_sites';fa[col]=fa.id.map(cnt).fillna(0).astype('int32');fa['agro_processing_function_evidence']=pd.array(np.where(fa[col].gt(0),True,None),dtype='boolean');fa.to_parquet(H/'settlement_literal_agro_processing_evidence_2021.parquet',index=False)
 changes=[]
 for family,old,cur in [('industry_resource',oldi,fi),('recreation',oldr,fr),('agro_processing',olda,fa)]:
  assert old.id.equals(cur.id)
  for col in old.columns.drop('id'):
   same=old[col].eq(cur[col]).fillna(False)|(old[col].isna()&cur[col].isna())
   for i in np.flatnonzero(~same.to_numpy()):changes.append({'family':family,'id':cur.id.iloc[i],'field':col,'old_value':str(old[col].iloc[i]),'new_value':str(cur[col].iloc[i]),'is_new477':cur.id.iloc[i]in patch.index})
 pd.DataFrame(ledger).to_parquet(H/'all_competitive_new_sourcepoint_links.parquet',index=False);pd.DataFrame(changes,columns=['family','id','field','old_value','new_value','is_new477']).to_parquet(H/'all_changed_feature_cells.parquet',index=False);assert all(sha(ROOT/p)==s for p,s in proto['inputs_sha256'].items())
 receipt={'status':'ACTUAL_FINITE_THEMATIC_RELINK_PENDING_INDEPENDENT_REVIEW','preregistration_sha256':sha(H/'preregistration.json'),'old_reference_rows':len(oldref),'new_reference_rows':len(ref),'new477':len(new),'competitive_link_rows':len(ledger),'changed_links':sum(r['changed']for r in ledger),'changed_feature_cells':len(changes),'changed_NPs':len(set(c['id']for c in changes)),'own_mass_changed':False,'source_predicates_and_physical_partition_fixed':True,'unknown_is_not_absence':True,'decline_and_shiftwork_not_inferred':True,'seconds':time.monotonic()-start,'outputs_sha256':{p.name:sha(p)for p in H.glob('*.parquet')}};(H/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt),flush=True)
if __name__=='__main__':main()
