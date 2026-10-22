#!/usr/bin/env python3
"""Mass independent parcel-location audit: identity, tiers, geometry, balances.

All 91,136 source records and all 142,570 settlement rows are checked. Coordinate
candidates are not accepted service catchments or evidence of consumer trips.
"""
from pathlib import Path
import re,hashlib,json,unicodedata
import numpy as np,pandas as pd
from scipy.spatial import cKDTree
H=Path(__file__).resolve().parent;N=H.parent;B=N.parent;O=H/'independent_sources/wb';O.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def xyz(lat,lon):
 a=np.deg2rad(np.asarray(lat));b=np.deg2rad(np.asarray(lon));return np.column_stack([np.cos(a)*np.cos(b),np.cos(a)*np.sin(b),np.sin(a)])
def norm(s):return ' '.join(re.sub(r'[^\w\s-]',' ',unicodedata.normalize('NFKC',str(s)).casefold().replace('ё','е')).split())
def main():
 paths=[B/'anchor_research_20261019/data/point_axis.parquet',B/'functional_dynamics_20261019/marketplaces/wb_delivery_locations_ru_20261019.parquet',N/'services/wb_objects_crosswalk.parquet',N/'services/wb_settlement_features.parquet',N/'services/wb_coordinate_candidates.parquet'];before={str(p):sha(p) for p in paths};axis=pd.read_parquet(paths[0]);raw=pd.read_parquet(paths[1]);d=pd.read_parquet(paths[2]);f=pd.read_parquet(paths[3]).set_index('id').reindex(axis.id);edges=pd.read_parquet(paths[4]);checks=[];risks=[]
 def ck(n,v,detail=None):checks.append({'name':n,'pass':bool(v),'detail':detail})
 ck('source_all_91136_unique_ids',len(raw)==len(d)==91136 and raw.object_id.is_unique and d.object_id.is_unique and set(raw.object_id)==set(d.object_id))
 r=raw.set_index('object_id',drop=False).reindex(d.object_id);r.index=d.index
 for c in raw:
  try:pd.testing.assert_series_equal(r[c],d[c],check_names=False,check_dtype=False,check_exact=True);ok=True
  except AssertionError:ok=False
  ck('source_field_preserved_'+c,ok)
 expected=r.settlement_uid.where(r.settlement_uid.isin(axis.id)&r.link_status.eq('name_coordinate_concordance'));ck('strict_uid_exactly_preserves_named_baseline',expected.fillna('').eq(d.wb_strict_uid.fillna('')).all());ck('strict_objects_74849',expected.notna().sum()==74849)
 # Independently compute the spherical nearest ranks with a Cartesian tree.
 vectors=xyz(axis.lat,axis.lon);objects=xyz(d.latitude,d.longitude);tree=cKDTree(vectors);chord,ix=tree.query(objects,k=3);nearest=2*6371.0088*np.arcsin(np.clip(chord/2,0,1));ck('all_three_nearest_rows',len(edges)==3*len(d))
 lookup=axis.set_index('id');source_index=pd.Series(np.arange(len(d)),index=d.object_id);positions=edges.object_id.map(source_index).to_numpy();ranks=edges['rank'].to_numpy(dtype=int)-1
 named=lookup.loc[edges.candidate_id];v1=objects[positions];v2=xyz(named.lat,named.lon);angle=np.arctan2(np.linalg.norm(np.cross(v1,v2),axis=1),np.einsum('ij,ij->i',v1,v2));dist=6371.0088*angle
 ck('all_claimed_candidate_geometries',np.allclose(dist,edges.distance_km.to_numpy(),rtol=0,atol=1e-8));ck('all_nearest_rank_distances',np.allclose(nearest[positions,ranks],edges.distance_km.to_numpy(),rtol=0,atol=1e-8));ck('first_neighbour_distance',np.allclose(nearest[:,0],d.wb_nearest_axis_distance_km,rtol=0,atol=1e-8))
 ties=np.isclose(nearest[:,0],nearest[:,1],rtol=0,atol=1e-10);ck('nearest_uid_distance_valid_despite_ties',np.isclose(nearest[:,0],d.wb_nearest_axis_distance_km,rtol=0,atol=1e-8).all())
 address=d.address.fillna('').str.lower().str.replace('ё','е');mos=address.str.contains(r'(?:^|,\s*)(?:г(?:ород)?\.?\s*)?москва\b',regex=True);spb=address.str.contains(r'(?:^|,\s*)(?:г(?:ород)?\.?\s*)?санкт[ -]петербург\b',regex=True);mgeo=d.latitude.between(54.9,56.4)&d.longitude.between(36.7,38.4);sgeo=d.latitude.between(59.5,60.5)&d.longitude.between(29,31.5);coarse=np.where(mos&mgeo,'RU-FED-MOW',np.where(spb&sgeo,'RU-FED-SPB',''));fed=np.where(expected.notna(),'',coarse)
 ck('effective_federal_tier_not_overriding_finer_named_uid',pd.Series(fed).eq(d.wb_federal_address_candidate.fillna('')).all());ck('five_finer_named_uids_with_coarse_federal_prefix',int(((coarse!='')&expected.notna()).sum())==5)
 foreign=d.source_object_id.astype(str).eq('50080949')|address.str.contains('баренцбург|barentsburg|svalbard',regex=True);crimea=d.latitude.between(44.2,46.4)&d.longitude.between(32.4,36.65)&expected.isna();baikonur=address.str.contains('байконур|baikonur',regex=True)&d.latitude.between(45,47)&d.longitude.between(62,64)&expected.isna();outside=crimea|baikonur
 ck('outside_geography_and_foreign_not_ordinary_candidates',d.loc[foreign|outside|(fed!=''),'wb_candidate_uid'].isna().all());ck('all_1666_outside_common_axis_geographies',int(outside.sum())==1666);ck('excluded_crimea_bbox_contains_no_frozen_axis_entry',not (axis.lat.between(44.2,46.4)&axis.lon.between(32.4,36.65)).any());ck('single_barentsburg',int(foreign.sum())==1);ck('effective_federal_7972',int((fed!='').sum())==7972)
 permitted=(fed=='')&~foreign&~outside;ck('candidate_presence_exactly_declared_scope',np.array_equal(permitted.to_numpy() if isinstance(permitted,pd.Series) else permitted,d.wb_candidate_uid.notna().to_numpy()))
 # Recompute every subtype and scenario count from all source objects.
 for tier,key in [('strict','wb_strict_uid'),('coordinate_candidate','wb_candidate_uid')]:
  groups={'all_types':pd.Series(True,index=d.index),'focus_types':d.typePoint.isin([8,34]),'expanded_types':d.typePoint.isin([8,34,28,53,54]),'technical_types':d.typePoint.isin([2,85])}
  groups.update({f'type_{typ}':d.typePoint.eq(typ) for typ in sorted(d.typePoint.unique())})
  for label,mask in groups.items():
   cnt=d.loc[mask&d[key].notna()].groupby(key).object_id.nunique().reindex(axis.id,fill_value=0);column=f'wb_{tier}_{label}_locations';ck('all_point_counts_'+column,np.array_equal(cnt.to_numpy(),f[column].to_numpy()))
  if tier=='coordinate_candidate':
   for threshold in [.25,1,2,5,20]:
    cnt=d.loc[d[key].notna()&(nearest[:,0]<=threshold)].groupby(key).object_id.nunique().reindex(axis.id,fill_value=0);ck('distance_threshold_'+str(threshold),np.array_equal(cnt.to_numpy(),f[f'wb_candidate_within_{str(threshold).replace(".","p")}km_locations'].to_numpy()))
 # Literal name/coordinate audit for every strict object, not a few examples.
 named_ids=d.wb_strict_uid.dropna();strict=d.loc[named_ids.index];place=lookup.loc[named_ids];v1=objects[named_ids.index];v2=xyz(place.lat,place.lon);distance=6371.0088*np.arctan2(np.linalg.norm(np.cross(v1,v2),axis=1),np.einsum('ij,ij->i',v1,v2));ck('all_strict_coordinates_within_original_10km_link_rule',bool((distance<=10.0001).all()))
 for (_,row),(_,p),km in zip(strict.iterrows(),place.iterrows(),distance):
  head=re.split(r'\b(?:улица|ул\.?|проспект|пр-кт|переулок|пер\.?|шоссе|бульвар|площадь|проезд|набережная)\b',norm(row.address),maxsplit=1)[0];name=' '.join(norm(p['name']).split())
  if not re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)',head):risks.append({'object_id':row.object_id,'id':row.wb_strict_uid,'kind':'strict_name_not_reproduced_in_pre_street_address','address':row.address,'place':p['name'],'distance_km':km})
 ck('strict_literal_names_reproduced',len(risks)==0,{'unreproduced':len(risks)})
 for idx in np.flatnonzero((nearest[:,0]>20)&d.wb_candidate_uid.notna().to_numpy()):risks.append({'object_id':d.iloc[idx].object_id,'id':d.iloc[idx].wb_candidate_uid,'kind':'coordinate_candidate_over_20km_not_identity','address':d.iloc[idx].address,'distance_km':float(nearest[idx,0])})
 pd.DataFrame(risks).to_csv(O/'review_queue.csv',index=False)
 stable=all(sha(Path(path))==digest for path,digest in before.items());ck('inputs_stable_during_independent_audit',stable)
 summary={'source_objects':len(d),'axis_UIDs':len(f),'strict_objects':int(expected.notna().sum()),'strict_UIDs':int(f.wb_strict_all_types_locations.gt(0).sum()),'coordinate_candidate_UIDs':int(f.wb_coordinate_candidate_all_types_locations.gt(0).sum()),'effective_federal_objects':int((fed!='').sum()),'finer_named_with_coarse_federal_prefix':int(((coarse!='')&expected.notna()).sum()),'outside_common_axis_objects':int(outside.sum()),'foreign_objects':int(foreign.sum()),'nearest_first_second_ties':int(ties.sum()),'review_queue_objects':len(risks)}
 result={'status':'PASS' if all(x['pass'] for x in checks) else 'FAIL_OR_CHANGED_INPUT','checks':checks,'summary':summary,'input_SHA256':before,'code_SHA256':sha(Path(__file__)),'interpretation':'Mass source-preservation and identity/coordinate-tier audit; nearest candidates do not establish identity, service centres, OD flows or SGRT.'};(O/'AUDIT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'status':result['status'],'checks':len(checks),'summary':summary},ensure_ascii=False),flush=True);assert all(x['pass'] for x in checks)
if __name__=='__main__':main()
