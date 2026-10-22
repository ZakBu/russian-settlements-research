"""Conditional supplement: literal place name + coordinates, relaxed address type."""
from pathlib import Path
import importlib.util,re,json,hashlib,time
import pandas as pd,numpy as np
from sklearn.neighbors import BallTree
R=Path(__file__).resolve().parent;B=R.parents[1]
def main():
 t=time.time();p=B/'functional_dynamics_20261019/marketplaces/build_marketplaces.py';spec=importlib.util.spec_from_file_location('frozen_wb_parser',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 a=pd.read_parquet(B/'anchor_research_20261019/data/point_axis.parquet',columns=['id','name','type','lat','lon']);d=pd.read_parquet(R/'wb_objects_crosswalk.parquet');a['name_norm']=a.name.map(m.norm);patterns={n:re.compile(r'(?<!\w)'+re.escape(n)+r'(?!\w)')for n in a.name_norm.unique()if len(n)>=3}
 z=d[d.wb_location_quality.eq('nearest_coordinate_candidate')].copy();tree=BallTree(np.deg2rad(a[['lat','lon']].to_numpy()),metric='haversine');ii,dd=tree.query_radius(np.deg2rad(z[['latitude','longitude']].to_numpy()),r=10/6371,return_distance=True,sort_results=True)
 records=[]
 for row,inds,dist in zip(z.itertuples(),ii,dd):
  head=m.address_head(row.address);matched=[(k,km*6371)for k,km in zip(inds,dist)if len(a.iloc[k].name_norm)>=3 and patterns[a.iloc[k].name_norm].search(head)]
  if matched:
   longest=max(len(a.iloc[k].name_norm)for k,_ in matched);matched=[(k,km)for k,km in matched if len(a.iloc[k].name_norm)==longest]
  if len(matched)!=1:continue
  k,km=matched[0];q=a.iloc[k];records.append({'object_id':row.object_id,'candidate_id':q.id,'candidate_name':q['name'],'candidate_census_type':q.type,'address':row.address,'distance_km':km,'typePoint':row.typePoint,'evidence':'conditional_literal_name_coordinates_address_type_relaxed','does_not_establish_external_service':True})
 new=pd.DataFrame(records,columns=['object_id','candidate_id','candidate_name','candidate_census_type','address','distance_km','typePoint','evidence','does_not_establish_external_service']);new.to_parquet(R/'wb_type_relaxed_object_links.parquet',index=False);new.to_csv(R/'wb_type_relaxed_object_links.csv',index=False)
 combined=d[['object_id','wb_strict_uid','typePoint']].merge(new[['object_id','candidate_id']],on='object_id',how='left',validate='one_to_one');combined['id']=combined.wb_strict_uid.fillna(combined.candidate_id)
 f=a[['id']].copy().set_index('id');g=combined.dropna(subset=['id']);f['wb_name_relaxed_inclusive_all_types_locations']=g.groupby('id').size().reindex(f.index,fill_value=0).astype('int32');f['wb_name_relaxed_additional_locations']=new.groupby('candidate_id').size().reindex(f.index,fill_value=0).astype('int32')
 for typ in sorted(d.typePoint.unique()):f[f'wb_name_relaxed_inclusive_type_{typ}_locations']=g[g.typePoint.eq(typ)].groupby('id').size().reindex(f.index,fill_value=0).astype('int32')
 for label,types in [('focus',[8,34]),('expanded',[8,34,28,53,54])]:f[f'wb_name_relaxed_inclusive_{label}_locations']=g[g.typePoint.isin(types)].groupby('id').size().reindex(f.index,fill_value=0).astype('int32')
 f=f.reset_index();f.to_parquet(R/'wb_name_relaxed_features.parquet',index=False)
 checks={'all_original_UID_retained':len(f)==142570 and f.id.is_unique,'no_replacement_of_existing_strict':not set(new.object_id)&set(d.loc[d.wb_strict_uid.notna(),'object_id']),'object_partition_balance':int(f.wb_name_relaxed_inclusive_all_types_locations.sum())==74849+len(new),'conditional_single_candidate_each':new.object_id.is_unique,'all_distances_within_coordinate_check':bool(new.distance_km.le(10).all()),'excluded_geographies_not_reintroduced':set(new.object_id)<=set(z.object_id)};assert all(checks.values())
 report={'status':'PASS','seconds':time.time()-t,'source_objects':len(d),'reviewed_unresolved_or_ambiguous_objects':len(z),'new_conditional_links':len(new),'new_conditional_settlements':int(new.candidate_id.nunique()),'inclusive_linked_objects':len(g),'inclusive_linked_settlements':int(g.id.nunique()),'checks':{k:bool(v)for k,v in checks.items()},'coordinate_rule_km':10,'rule_meaning':'same-location geocoding plausibility inherited from baseline, not service radius; settlement type mismatch relaxed conditionally, not a native identity assertion','inputs_sha256':{str(q.relative_to(B)):hashlib.sha256(q.read_bytes()).hexdigest()for q in [p,R/'wb_objects_crosswalk.parquet',B/'anchor_research_20261019/data/point_axis.parquet']}}
 (R/'NAME_RELAXATION_AUDIT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
