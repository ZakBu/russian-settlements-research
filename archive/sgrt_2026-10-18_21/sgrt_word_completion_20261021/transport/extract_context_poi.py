#!/usr/bin/env python3
from pathlib import Path
import osmium,pandas as pd,numpy as np,json,time
ROOT=Path(__file__).resolve().parent;RAW=Path('/workspace/scratch/sgrt_transport');start=time.time();idx=osmium.index.create_map(f'sparse_file_array,{RAW}/node_locations.idx');rows=[];ferries=[];count=0
processor=osmium.FileProcessor(str(RAW/'russia.osm.pbf')).with_filter(osmium.filter.KeyFilter('tourism','landuse','man_made','industrial','route'))
for ob in processor:
 tags={t.k:t.v for t in ob.tags};tourism=tags.get('tourism') in {'hotel','motel','guest_house','hostel','chalet','camp_site','caravan_site','attraction','museum','resort','apartment','alpine_hut','wilderness_hut'};landuse=tags.get('landuse') in {'allotments','industrial','quarry'};mine=tags.get('man_made') in {'mineshaft','adit','works'} or tags.get('industrial') in {'mine','mining','oil','oil_refinery','oil_well','gas','gas_processing'};ferry=tags.get('route')=='ferry'
 if not (tourism or landuse or mine or ferry) or not(ob.is_node() or ob.is_way()):continue
 try:
  if ob.is_node():lat,lon=ob.location.lat,ob.location.lon;role='source_node';coords=None;refs=None
  else:
   refs=[x.ref for x in ob.nodes];loc=[]
   for ref in refs:
    try:l=idx.get(ref);loc.append((l.lat,l.lon))
    except Exception:pass
   if len(loc)<2:continue
   lat,lon=np.mean(np.array(loc),axis=0);role='vertex_mean_not_interior_point';coords=loc
  if not np.isfinite(lat+lon):continue
  if ferry and ob.is_way():ferries.append({'osm_id':ob.id,'refs':refs,'lat':[a for a,b in coords],'lon':[b for a,b in coords],'tags_json':json.dumps(tags,ensure_ascii=False)})
  if tourism or landuse or mine:rows.append({'osm_type':'node' if ob.is_node() else 'way','osm_id':ob.id,'lat':float(lat),'lon':float(lon),'geometry_role':role,'name':tags.get('name'),'tourism':tags.get('tourism'),'landuse':tags.get('landuse'),'man_made':tags.get('man_made'),'industrial':tags.get('industrial'),'tourism_signal':tourism,'allotment_signal':tags.get('landuse')=='allotments','industrial_or_mining_signal':mine or tags.get('landuse') in {'industrial','quarry'},'tags_json':json.dumps(tags,ensure_ascii=False)})
 except Exception:continue
 if len(rows)>=20000:
  pd.DataFrame(rows).to_parquet(RAW/f'context_poi_{count:09d}.parquet',index=False);count+=len(rows);rows=[];print('contextpoi',count,'seconds',round(time.time()-start),flush=True)
if rows:pd.DataFrame(rows).to_parquet(RAW/f'context_poi_{count:09d}.parquet',index=False);count+=len(rows)
pd.DataFrame(ferries).to_parquet(ROOT/'ferry_way_inventory.parquet',index=False)
(ROOT/'context_poi_receipt.json').write_text(json.dumps({'status':'EXTRACTED','context_point_assertions':count,'ferry_way_records':len(ferries),'seconds':time.time()-start,'source':'GeofabrikRussiaOSM2026-10-19','geometry':'source_node_or_vertex_mean_not_certified_interior','industrial_landuse_not_workplaces':True,'tourism_not_measured_visitors':True,'allotments_not_proven_second_home_population':True,'ferry_timetable_observed':False},ensure_ascii=False,indent=2));print('CONTEXT_DONE',count,len(ferries),flush=True)
