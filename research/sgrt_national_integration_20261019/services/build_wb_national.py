"""Mass location crosswalk, retaining strict and coordinate-candidate layers."""
from pathlib import Path
import json,hashlib,time
import numpy as np,pandas as pd
from sklearn.neighbors import BallTree
R=Path(__file__).resolve().parent;B=R.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 t=time.time();axispath=B/'anchor_research_20261019/data/point_axis.parquet';source=B/'functional_dynamics_20261019/marketplaces/wb_delivery_locations_ru_20261019.parquet'
 a=pd.read_parquet(axispath,columns=['id','name','region','lat','lon','population_2021']);d=pd.read_parquet(source);assert a.id.is_unique and d.object_id.is_unique
 assert len(a)==142570 and len(d)==91136
 address=d.address.fillna('').str.lower().str.replace('ё','е');mos=address.str.contains(r'(?:^|,\s*)(?:г(?:ород)?\.?\s*)?москва\b',regex=True);spb=address.str.contains(r'(?:^|,\s*)(?:г(?:ород)?\.?\s*)?санкт[ -]петербург\b',regex=True)
 mgeo=d.latitude.between(54.9,56.4)&d.longitude.between(36.7,38.4);sgeo=d.latitude.between(59.5,60.5)&d.longitude.between(29,31.5)
 fed=np.select([mos&mgeo,spb&sgeo],['RU-FED-MOW','RU-FED-SPB'],default='')
 d['wb_federal_address_candidate']=fed;d['wb_federal_address_geometry_conflict']=(mos&~mgeo)|(spb&~sgeo)
 d['wb_strict_uid']=d.settlement_uid.where(d.settlement_uid.isin(a.id)&d.link_status.eq('name_coordinate_concordance'))
 d['wb_source_federal_address_label']=fed
 d['wb_coarse_federal_address_with_finer_named_uid']=(fed!='')&d.wb_strict_uid.notna()
 fed=np.where(d.wb_strict_uid.notna(),'',fed)
 d['wb_federal_address_candidate']=fed
 # Spatial coordinates locate an object; they do not establish its external service catchment.
 good=np.isfinite(d.latitude)&np.isfinite(d.longitude)&d.latitude.between(-90,90)&d.longitude.between(-180,180)
 tree=BallTree(np.deg2rad(a[['lat','lon']].to_numpy()),metric='haversine');dist,ix=tree.query(np.deg2rad(d.loc[good,['latitude','longitude']].to_numpy()),k=3);dist*=6371.0088
 links=[];origidx=np.flatnonzero(good.to_numpy())
 for rank in range(3):
  links.append(pd.DataFrame({'object_id':d.object_id.to_numpy()[origidx],'candidate_id':a.id.to_numpy()[ix[:,rank]],'rank':rank+1,'distance_km':dist[:,rank],'candidate_region':a.region.to_numpy()[ix[:,rank]],'is_external_federal_address':fed[origidx]!='','evidence':'coordinate_neighbour_candidate_not_service_assignment'}))
 edges=pd.concat(links,ignore_index=True);edges.to_parquet(R/'wb_coordinate_candidates.parquet',index=False)
 d['wb_nearest_axis_id']=None;d['wb_nearest_axis_distance_km']=np.nan;d.loc[good,'wb_nearest_axis_id']=a.id.to_numpy()[ix[:,0]];d.loc[good,'wb_nearest_axis_distance_km']=dist[:,0]
 # Explicit foreign geography already identified in the frozen provider snapshot.
 d['wb_known_outside_research_country']=d.source_object_id.astype(str).eq('50080949')|address.str.contains('баренцбург|barentsburg|svalbard',regex=True)
 assert not (a.lat.between(44.2,46.4)&a.lon.between(32.4,36.65)).any(), 'Coverage envelope must contain no frozen-axis point'
 unsupported_crimea_envelope=d.latitude.between(44.2,46.4)&d.longitude.between(32.4,36.65)&d.wb_strict_uid.isna()
 unsupported_baikonur=address.str.contains('байконур|baikonur',regex=True)&d.latitude.between(45,47)&d.longitude.between(62,64)&d.wb_strict_uid.isna()
 d['wb_outside_common_axis_geography']=np.select([unsupported_baikonur,unsupported_crimea_envelope],['baikonur_no_frozen_axis_entry','crimea_envelope_no_nearby_axis_entry'],default='')
 d['wb_candidate_uid']=d.wb_nearest_axis_id.where((fed=='')&~d.wb_known_outside_research_country&d.wb_outside_common_axis_geography.eq(''))
 d['wb_enhanced_location_id']=d.wb_strict_uid.fillna(d.wb_candidate_uid);d.loc[fed!='','wb_enhanced_location_id']=fed[fed!='']
 d['wb_location_quality']=np.select([d.wb_known_outside_research_country,d.wb_outside_common_axis_geography.ne(''),fed!='',d.wb_strict_uid.notna(),d.wb_candidate_uid.notna()],['known_outside_research_country','outside_common_axis_geography','external_federal_source_address','name_coordinate_concordance','nearest_coordinate_candidate'],default='unresolved')
 edges=edges.merge(d[['object_id','wb_location_quality','wb_outside_common_axis_geography']],on='object_id',validate='many_to_one');edges.to_parquet(R/'wb_coordinate_candidates.parquet',index=False)
 d['wb_type_focus']=d.typePoint.isin([8,34]);d['wb_type_expanded']=d.typePoint.isin([8,34,28,53,54]);d['wb_technical_type']=d.typePoint.isin([2,85]);d.to_parquet(R/'wb_objects_crosswalk.parquet',index=False)
 f=a[['id']].copy().set_index('id');feature_columns=[]
 for label,col in [('strict','wb_strict_uid'),('coordinate_candidate','wb_candidate_uid')]:
  z=d[d[col].notna()];gr=z.groupby(col,sort=False)
  count=gr.size();f[f'wb_{label}_all_types_locations']=count.reindex(f.index,fill_value=0).astype('int32')
  for field,mask in [('focus_types',z.wb_type_focus),('expanded_types',z.wb_type_expanded),('technical_types',z.wb_technical_type)]:
   cnt=z[mask].groupby(col).size();f[f'wb_{label}_{field}_locations']=cnt.reindex(f.index,fill_value=0).astype('int32')
  for typ in sorted(d.typePoint.unique()):
   cnt=z[z.typePoint.eq(typ)].groupby(col).size();f[f'wb_{label}_type_{typ}_locations']=cnt.reindex(f.index,fill_value=0).astype('int32')
  if label=='coordinate_candidate':
   for threshold in [.25,1,2,5,20]:
    cnt=z[z.wb_nearest_axis_distance_km<=threshold].groupby(col).size();f[f'wb_candidate_within_{str(threshold).replace(".","p")}km_locations']=cnt.reindex(f.index,fill_value=0).astype('int32')
   f['wb_candidate_distance_km_max']=gr.wb_nearest_axis_distance_km.max().reindex(f.index)
 f['wb_snapshot_date']='2026-10-19';f['wb_observation_scope']='published_delivery_locations_all_source_types';f['wb_zero_means']='no_linked_source_record_not_proven_absence';f['wb_external_catchments_measured']=False
 f=f.reset_index();f.to_parquet(R/'wb_settlement_features.parquet',index=False)
 fedtable=d[fed!=''].groupby(['wb_federal_address_candidate','typePoint']).size().rename('locations').reset_index();fedtable.to_csv(R/'wb_federal_summary.csv',index=False)
 d[d.wb_location_quality.ne('name_coordinate_concordance')][['object_id','address','typePoint','latitude','longitude','link_status','candidate_uids','wb_federal_address_candidate','wb_nearest_axis_id','wb_nearest_axis_distance_km','wb_location_quality','wb_outside_common_axis_geography']].to_parquet(R/'wb_review_queue.parquet',index=False)
 checks={'axis_rows_retained':len(f)==142570,'unique_id':f.id.is_unique,'all_objects_retained':len(d)==91136,'no_federal_rural_assignment':d.loc[fed!='','wb_candidate_uid'].isna().all(),'no_known_foreign_rural_assignment':d.loc[d.wb_known_outside_research_country,'wb_candidate_uid'].isna().all(),'no_unsupported_axis_geography_assignment':d.loc[d.wb_outside_common_axis_geography.ne(''),'wb_candidate_uid'].isna().all(),'strict_balance':int(f.wb_strict_all_types_locations.sum())==d.wb_strict_uid.notna().sum(),'candidate_balance':int(f.wb_coordinate_candidate_all_types_locations.sum())==d.wb_candidate_uid.notna().sum(),'type_balance_strict':int(f.filter(regex=r'^wb_strict_type_\d+_locations$').sum().sum())==d.wb_strict_uid.notna().sum(),'three_nearest_per_valid_object':len(edges)==3*int(good.sum())}
 assert all(checks.values()),checks
 audit={'status':'PASS','seconds':time.time()-t,'axis_rows':len(f),'features':len(f.columns),'source_locations':len(d),'strict_objects':int(d.wb_strict_uid.notna().sum()),'strict_points':int(f.wb_strict_all_types_locations.gt(0).sum()),'candidate_points':int(f.wb_coordinate_candidate_all_types_locations.gt(0).sum()),'location_quality_counts':d.wb_location_quality.value_counts().to_dict(),'federal_objects':int((fed!='').sum()),'source_federal_prefix_with_finer_named_uid':int(d.wb_coarse_federal_address_with_finer_named_uid.sum()),'unsupported_common_axis_geography':d.wb_outside_common_axis_geography.value_counts().to_dict(),'candidate_distance_quantiles':d.loc[d.wb_candidate_uid.notna(),'wb_nearest_axis_distance_km'].quantile([0,.5,.9,.95,.99,1]).to_dict(),'checks':{k:bool(v)for k,v in checks.items()},'inputs':{str(p.relative_to(B)):sha(p)for p in [axispath,source]},'interpretation':'Strict and coordinate candidate feature layers are separate; all types retained; no consumer OD/catchment inferred; federal source addresses kept outside ordinary-settlement axis.'}
 (R/'AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n');print(json.dumps(audit,ensure_ascii=False))
if __name__=='__main__':main()
